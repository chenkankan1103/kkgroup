'use strict';
/* sim.js — 遊戲狀態核心：成員、任務派遣、事件、三條數值條、結局、存檔 */

const Sim = (() => {
  let S = null;          // 全部可存檔狀態
  let paused = false;    // 事件/結局強制暫停
  const L = {};          // 事件監聽
  function on(k, f) { L[k] = f; }
  function emit(k, a) { if (L[k]) L[k](a); }

  // ===== 遊戲時鐘（S 未初始化時給安全預設，地圖在開場就會問密度）=====
  const gameMin = () => (S ? S.day * 1440 + S.min : 9 * 60);
  const hour = () => (S ? Math.floor(S.min / 60) : 9);
  // 圍籬效果：夜間（20:00–06:00）警力密度打 75 折
  const policeDensity = () => {
    const h = hour();
    let d = POLICE_DENSITY[h];
    if (S && S.buildings && S.buildings.fence && (h >= 20 || h < 6)) d *= 0.75;
    return d;
  };
  const clockStr = () =>
    `第 ${S.day} 天 ${String(hour()).padStart(2, '0')}:${String(S.min % 60).padStart(2, '0')}`;

  function memberById(id) { return S.members.find((m) => m.id === id); }

  function makeMember() {
    // 名字不重複：優先從沒用過的名字挑（用完才允許重複）
    const used = S.members.map((m) => m.name);
    const pool = NAMES.filter((n) => !used.includes(n));
    const pickFrom = pool.length ? pool : NAMES;
    return {
      id: 'm' + (S.nextId++),
      name: pickFrom[(Math.random() * pickFrom.length) | 0],
      avatar: AVATARS[(Math.random() * AVATARS.length) | 0],
      gab: rollStat(), legs: rollStat(), luck: rollStat(),
      state: 'idle', jailUntil: 0, caught: 0, jobsDone: 0,
    };
  }

  function newGame() {
    S = {
      v: 2, day: 1, min: 9 * 60,
      money: START.money, trust: START.trust, police: START.police, sus: START.sus,
      food: START_FOOD, buildings: {}, buildQueue: [],
      gear: {}, members: [], nextId: 1, missions: [], nextMid: 1,
      jobs: {}, nextGen: 0, ended: null,
    };
    for (let i = 0; i < START.members; i++) S.members.push(makeMember());
    for (let i = 0; i < START.missions; i++) genMission();
  }

  // ===== 任務生成：在指定點附近撒（沒給就撒在園區總部附近）=====
  function genMission(center) {
    const c = center || HQ;
    const total = MISSION_POOL.reduce((s, x) => s + x.w, 0);
    let r = Math.random() * total, tk = 'scam';
    for (const x of MISSION_POOL) { r -= x.w; if (r <= 0) { tk = x.k; break; } }
    const t = MISSION_TYPES[tk];
    const heat = 0.35 + Math.random() * 0.65;
    const m = {
      id: 'j' + (S.nextMid++), type: tk,
      lat: Math.min(TW.latR[1], Math.max(TW.latR[0], c.lat + (Math.random() - 0.5) * 0.07)),
      lng: Math.min(TW.lngR[1], Math.max(TW.lngR[0], c.lng + (Math.random() - 0.5) * 0.09)),
      pay: rndInt(t.pay[0], t.pay[1]),
      durMin: rndInt(t.dur[0], t.dur[1]),
      risk: Math.min(0.9, t.risk * (0.6 + heat * 0.8)),
      heat,
      code: String.fromCharCode(65 + ((Math.random() * 26) | 0)) + (100 + ((Math.random() * 900) | 0)),
    };
    S.missions.push(m);
    if (S.missions.length > 6) S.missions.shift();
    emit('missions');
    return m;
  }

  // ===== 派遣：mode 'short'（即時直播＋事件）| 'long'（大活，可離線）=====
  function assign(memberId, missionId, mode) {
    const mem = memberById(memberId);
    const i = S.missions.findIndex((x) => x.id === missionId);
    if (!mem || i < 0 || mem.state !== 'idle') return null;
    const base = S.missions.splice(i, 1)[0];
    const m = Object.assign({}, base);
    const gm = gameMin();
    if (mode === 'long') {
      m.durMin = Math.round(base.durMin * LONG.durMult + LONG.durAdd);
      m.pay = Math.round(base.pay * LONG.payMult);
      m.risk = Math.min(0.92, base.risk + LONG.riskAdd);
    }
    // 趕路：從園區總部走到任務點（贓車將近兩倍速），去＋工作＋回都算進時程
    const dist = Math.hypot(m.lng - HQ.lng, m.lat - HQ.lat);
    const speed = MOVE_DEG * (S.gear.car ? MOVE_CAR_MULT : 1);
    const travelMin = Math.max(1, Math.round(dist / speed));
    const job = {
      m, memId: memberId, mode,
      leg: 'out', pos: { lat: HQ.lat, lng: HQ.lng },
      travelMin,
      arrivedMin: gm + travelMin,
      endMin: gm + travelMin + m.durMin + travelMin,
      evTimes: mode === 'short' ? [0.4, 0.75].map((f) => gm + travelMin + m.durMin * f) : [],
      evDone: 0, bonus: 0, pendingEvent: null, settled: false,
    };
    if (mode === 'long') {
      // 1 遊戲分鐘 = 1 真實秒 → 離線也能跑完（含來回趕路）
      job.endRealMs = Date.now() + (travelMin * 2 + m.durMin) * 1000;
      job.outcome = preRoll(job, mem);
    }
    S.jobs[memberId] = job;
    mem.state = 'onjob';
    emit('missions'); emit('roster');
    Save.write(S);
    return job;
  }

  // 大活預先擲定結果（時間到直接結算）
  function preRoll(job, mem) {
    const t = MISSION_TYPES[job.m.type];
    let p = 0.35 + mem[t.stat] * 0.055;
    if (job.m.type === 'scam' && S.gear.voice) p += 0.10;
    const ok = Math.random() < Math.min(0.95, p);
    return { ok, captured: !ok && failCapture(job.m) };
  }

  // 任務失敗的被逮機率（假車牌幫車手類擋一刀）
  function failCapture(m) {
    let pc = m.risk * 0.55;
    if (S.gear.plate && m.type !== 'scam') pc *= 0.75;
    return Math.random() < pc;
  }

  function addSus(x) { S.sus = clamp100(S.sus + x * (S.gear.vpn ? 0.8 : 1)); }

  function caught(mem, why) {
    mem.state = 'jail';
    mem.jailUntil = Date.now() + rndInt(JAIL_MIN[0], JAIL_MIN[1]) * 60000;
    mem.caught++;
    S.police = clamp100(S.police + 4); // 警方多了一條線索
    addSus(10);
    emit('roster');
  }

  function successPay(m, t, job) {
    if (m.type === 'intel') {
      S.police = clamp100(S.police + 12 + rndInt(0, 8));
      emit('toast', { icon: '🕵️', text: `${m.code} 情報交付成功！警方進度大幅推進` });
    } else {
      const pay = Math.round(m.pay * (1 + (job.bonus || 0)) * (S.buildings.generator ? 1.15 : 1));
      S.money += pay;
      emit('toast', { icon: '💵', text: `${m.code} 任務完成，進帳 $${pay.toLocaleString()}` });
    }
    S.trust = clamp100(S.trust + t.trust);
    addSus(m.risk * 8);
    S.food = Math.min(FOOD_MAX, S.food + 1); // 順手帶一份補給回園區
  }

  function settleFail(m, mem, label) {
    if (m.type === 'intel') { S.police = clamp100(S.police + 4); addSus(15); }
    else { S.trust = clamp100(S.trust - 6); addSus(m.risk * 10); }
    if (failCapture(m)) {
      caught(mem);
      emit('toast', { icon: '🚨', text: `${mem.name} 在${label}中被逮！關進看守所了` });
    } else {
      emit('toast', { icon: '💦', text: `${m.code} ${label}失敗，${mem.name} 溜了回來` });
    }
  }

  // ===== V1.5：移動與結算（趕路 → 工作 → 溜回園區）=====
  function moveToward(j, tLat, tLng) {
    const speed = MOVE_DEG * (S.gear.car ? MOVE_CAR_MULT : 1);
    const dx = tLng - j.pos.lng, dy = tLat - j.pos.lat;
    const d = Math.hypot(dx, dy);
    if (d <= speed) { j.pos = { lat: tLat, lng: tLng }; return true; }
    j.pos = { lat: j.pos.lat + (dy / d) * speed, lng: j.pos.lng + (dx / d) * speed };
    return false;
  }

  // 工作階段結束：結算一次（錢／風險在這裡定案），然後開始走回園區
  function settleJob(job) {
    if (job.settled) return;
    job.settled = true;
    const mem = memberById(job.memId);
    const m = job.m, t = MISSION_TYPES[m.type];
    if (!mem) { job.leg = 'back'; job.pos = { lat: m.lat, lng: m.lng }; return; }
    mem.jobsDone++;
    if (job.mode === 'long') {
      const o = job.outcome || { ok: true, captured: false };
      if (o.ok) successPay(m, t, job);
      else if (o.captured) {
        if (m.type === 'intel') { S.police = clamp100(S.police + 4); addSus(15); }
        else { S.trust = clamp100(S.trust - 6); addSus(m.risk * 10); }
        delete S.jobs[job.memId];
        caught(mem);
        emit('toast', { icon: '🚨', text: `${mem.name} 跑大活被逮！關進看守所了` });
        after(); return;
      } else {
        settleFail(m, mem, '大活');
        if (mem.state === 'jail') { delete S.jobs[job.memId]; after(); return; }
      }
    } else {
      let p = 0.35 + mem[t.stat] * 0.055;
      if (m.type === 'scam' && S.gear.voice) p += 0.10;
      if (Math.random() < Math.min(0.95, p)) successPay(m, t, job);
      else {
        settleFail(m, mem, '任務');
        if (mem.state === 'jail') { delete S.jobs[job.memId]; after(); return; }
      }
    }
    job.leg = 'back';
    job.pos = { lat: m.lat, lng: m.lng };
    after();
  }

  // 走回總部：卸下派遣、恢復待命
  function arriveHome(job) {
    delete S.jobs[job.memId];
    const mem = memberById(job.memId);
    if (mem && mem.state === 'onjob') { mem.state = 'idle'; emit('roster'); }
    Save.write(S);
  }

  // ===== 事件抉擇 =====
  function chooseEvent(idx) {
    let job = null;
    for (const id in S.jobs) if (S.jobs[id].pendingEvent) job = S.jobs[id];
    if (!job) { paused = false; return; }
    const ev = job.pendingEvent;
    job.pendingEvent = null;
    const mem = memberById(job.memId);
    const c = idx === 0 ? ev.A : ev.B;
    paused = false;
    if (c.kind === 'continue') {
      emit('toast', { icon: '😌', text: '見好就收，任務繼續照常跑' });
    } else if (c.kind === 'abandon') {
      delete S.jobs[job.memId];
      if (mem) mem.state = 'idle';
      S.trust = clamp100(S.trust - 8);   // 丟包，組織不爽
      addSus(-3);                        // 但低調撤退，懷疑小降
      emit('toast', { icon: '🤐', text: `${mem ? mem.name : '成員'} 丟包撤退，組織眉頭皺了一下` });
    } else { // risk
      let p = 0.40 + mem[c.stat] * 0.05;
      if (S.gear.voice) p += 0.05;
      if (Math.random() < Math.min(0.95, p)) {
        job.bonus += (c.bonus || 0.3);
        emit('toast', { icon: '🔥', text: `${mem.name} 槓槓的！這趟收穫加碼` });
      } else if (Math.random() < 0.45) {
        delete S.jobs[job.memId];
        caught(mem);
        emit('toast', { icon: '🚨', text: `關鍵時刻破功，${mem.name} 被直接帶回派出所！` });
      } else {
        addSus(8);
        emit('toast', { icon: '😬', text: `${mem.name} 有驚無險脫身，但警方記了一筆` });
      }
    }
    after();
  }

  // ===== 每秒 tick（1 真實秒 = 1 遊戲分鐘）=====
  function tick() {
    if (!S || S.ended || paused) return;
    S.min++;
    if (S.min >= 1440) { S.min = 0; S.day++; }
    const gm = gameMin();

    // 派遣：趕路 → 工作 → 結算 → 溜回園區
    for (const id in S.jobs) {
      const j = S.jobs[id];
      if (j.leg === 'out') {
        if (moveToward(j, j.m.lat, j.m.lng)) j.leg = 'work';
      } else if (j.leg === 'work') {
        const done = j.mode === 'long' ? Date.now() >= j.endRealMs : gm >= j.endMin;
        if (done) settleJob(j);
      } else if (j.leg === 'back') {
        if (moveToward(j, HQ.lat, HQ.lng)) arriveHome(j);
      }
    }

    // 快跑途中跳事件（只在工作階段）
    for (const id in S.jobs) {
      const j = S.jobs[id];
      if (j.leg === 'work' && j.mode === 'short' && !j.pendingEvent && j.evDone < j.evTimes.length && gm >= j.evTimes[j.evDone]) {
        j.evDone++;
        j.pendingEvent = EVENTS[(Math.random() * EVENTS.length) | 0];
        paused = true;
        emit('event', { memId: j.memId, ev: j.pendingEvent });
        break;
      }
    }

    // 工地：到點完工
    for (let i = S.buildQueue.length - 1; i >= 0; i--) {
      const q = S.buildQueue[i];
      if (gm >= q.doneMin) {
        S.buildQueue.splice(i, 1);
        S.buildings[q.id] = true;
        const b = BUILDINGS.find((x) => x.id === q.id);
        emit('toast', { icon: b.icon, text: `${b.name} 蓋好了——${b.desc}` });
        emit('buildings');
      }
    }

    // 清晨六點結算伙食：水塔產出 → 全員開飯 → 斷糧懲罰
    if (S.min === 360) dailyFood();

    for (const mem of S.members) {
      if (mem.state === 'jail' && Date.now() >= mem.jailUntil) {
        mem.state = 'idle'; mem.jailUntil = 0;
        emit('toast', { icon: '🚪', text: `${mem.name} 刑滿出來了` });
        emit('roster');
      }
    }
    if (S.missions.length < 3 && gm >= S.nextGen) { S.nextGen = gm + 30; genMission(); }
    if (S.min % 5 === 0) Save.write(S);
    emit('tick');
  }

  function dailyFood() {
    if (S.buildings.tank) S.food = Math.min(FOOD_MAX, S.food + FOOD_TANK);
    const eat = S.members.length * (S.buildings.kitchen ? 1 : FOOD_EAT);
    S.food -= eat;
    if (S.food < 0) {
      S.food = 0;
      S.trust = clamp100(S.trust - 5);
      emit('toast', { icon: '🍚', text: '伙食見底——餓肚子的成員在抱怨，組織信任 -5' });
    } else if (S.food <= 3) {
      emit('toast', { icon: '🍚', text: `存糧只剩 ${S.food} 份，快去「花錢」補貨` });
    }
  }

  function checkEndings() {
    if (!S || S.ended) return;
    if (S.trust <= 0) S.ended = 'silenced';
    else if (S.sus >= 100) S.ended = 'jailed';
    else if (S.police >= 100) S.ended = 'raid';
    if (S.ended) { paused = true; emit('ending', S.ended); }
  }
  function restart() { Save.clear(); paused = false; newGame(); }

  // ===== 讀檔＋離線回算 =====
  function load() {
    const d = Save.read();
    if (!d || !d.members || !d.members.length) return false;
    S = d;
    // V1.5 存檔遷移：補伙食／建設欄位；舊派遣視為已在工作中（時間到照常結算）
    if (S.food === undefined) S.food = START_FOOD;
    if (!S.buildings) S.buildings = {};
    if (!S.buildQueue) S.buildQueue = [];
    S.v = 2;
    for (const id in S.jobs) {
      const j = S.jobs[id];
      if (!j.leg) { j.leg = 'work'; j.pos = { lat: j.m.lat, lng: j.m.lng }; j.settled = false; }
    }
    for (const id in S.jobs) {
      const j = S.jobs[id];
      if (j.mode === 'long' && Date.now() >= j.endRealMs) {
        settleJob(j);
        // 離線回算的人不用演走路——直接到家
        const jj = S.jobs[j.memId];
        if (jj && jj.leg === 'back') arriveHome(jj);
      }
    }
    for (const mem of S.members) {
      if (mem.state === 'jail' && Date.now() >= mem.jailUntil) { mem.state = 'idle'; mem.jailUntil = 0; }
    }
    checkEndings();
    return true;
  }

  // ===== 花錢四出口 =====
  const bailCost = (mem) =>
    PRICES.bail + Math.max(0, Math.ceil((mem.jailUntil - Date.now()) / 60000)) * PRICES.bailPerMin;

  function bail(id) {
    const mem = memberById(id);
    if (!mem || mem.state !== 'jail') return false;
    const cost = bailCost(mem);
    if (S.money < cost) { emit('toast', { icon: '💸', text: '錢不夠，保不了' }); return false; }
    S.money -= cost;
    mem.state = 'idle'; mem.jailUntil = 0;
    S.trust = clamp100(S.trust + 2);
    after();
    emit('toast', { icon: '⚖️', text: `${mem.name} 交保出來（花了 $${cost.toLocaleString()}）` });
    return true;
  }

  function memberCap() { return MEMBER_CAP_BASE + (S.buildings && S.buildings.dorm ? 3 : 0); }

  function hire() {
    if (S.members.length >= memberCap()) { emit('toast', { icon: '🛖', text: '工寮不夠住——先蓋工寮才招得到人' }); return null; }
    if (S.money < PRICES.hire) { emit('toast', { icon: '💸', text: '錢不夠' }); return null; }
    S.money -= PRICES.hire;
    const mem = makeMember();
    S.members.push(mem);
    after();
    emit('toast', { icon: '🤝', text: `新成員 ${mem.avatar} ${mem.name} 入夥（口才${mem.gab}/腿力${mem.legs}/運氣${mem.luck}）` });
    return mem;
  }

  function buyGear(id) {
    const g = GEAR.find((x) => x.id === id);
    if (!g || S.gear[id]) return false;
    if (S.money < g.price) { emit('toast', { icon: '💸', text: '錢不夠' }); return false; }
    S.money -= g.price;
    S.gear[id] = true;
    after();
    emit('toast', { icon: g.icon, text: `入手 ${g.name}：${g.desc}` });
    return true;
  }

  function buyIntel() {
    if (S.money < PRICES.intel) { emit('toast', { icon: '💸', text: '錢不夠' }); return false; }
    S.money -= PRICES.intel;
    S.police = clamp100(S.police + INTEL_BUY_POLICE);
    after();
    emit('toast', { icon: '🗂️', text: `砸錢買到關鍵情報，警方進度 +${INTEL_BUY_POLICE}` });
    return true;
  }

  // ===== V1.5：園區建設與伙食採買 =====
  function build(id) {
    const b = BUILDINGS.find((x) => x.id === id);
    if (!b || S.buildings[id] || S.buildQueue.some((q) => q.id === id)) return false;
    if (S.money < b.price) { emit('toast', { icon: '💸', text: '錢不夠' }); return false; }
    S.money -= b.price;
    S.buildQueue.push({ id, doneMin: gameMin() + b.buildMin });
    after();
    emit('toast', { icon: '⚒️', text: `開工蓋 ${b.name}——約 ${Math.max(1, Math.round(b.buildMin / 60))} 分鐘好` });
    emit('buildings');
    return true;
  }

  function buyFood() {
    if (S.money < FOOD_PACK.price) { emit('toast', { icon: '💸', text: '錢不夠' }); return false; }
    S.money -= FOOD_PACK.price;
    S.food = Math.min(FOOD_MAX, S.food + FOOD_PACK.amount);
    after();
    emit('toast', { icon: '🍚', text: `補了 ${FOOD_PACK.amount} 份伙食` });
    return true;
  }

  function after() { checkEndings(); Save.write(S); }

  return {
    on, newGame, load, restart, tick,
    assign, chooseEvent, bail, hire, buyGear, buyIntel, genMission,
    build, buyFood, memberCap,
    memberById, bailCost,
    state: () => S,
    isPaused: () => paused,
    hour, policeDensity, clockStr, gameMin,
  };
})();
