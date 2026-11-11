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
      buried: 0, buriedRefund: 0, raidCount: 0, bribeCount: 0,  // V2.5
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
    const lat = Math.min(TW.latR[1], Math.max(TW.latR[0], c.lat + (Math.random() - 0.5) * 0.07));
    const lng = Math.min(TW.lngR[1], Math.max(TW.lngR[0], c.lng + (Math.random() - 0.5) * 0.09));
    // V2.5：距離參與決策——遠的錢多、風險也高，近的快但薄
    // 生成範圍 lat ±0.035 / lng ±0.045（最大 dist ≈ 0.057），門檻與倍率對齊這個範圍
    const dist = Math.hypot(lng - HQ.lng, lat - HQ.lat);
    const distMult = 0.85 + Math.min(1, dist / 0.055) * 0.55;
    const m = {
      id: 'j' + (S.nextMid++), type: tk,
      lat, lng,
      pay: Math.round(rndInt(t.pay[0], t.pay[1]) * distMult),
      durMin: rndInt(t.dur[0], t.dur[1]),
      risk: Math.min(0.9, t.risk * (0.6 + heat * 0.8) + dist * 1.4),
      heat,
      distTier: dist < 0.02 ? '近' : dist < 0.04 ? '中' : '遠',
      expireMin: gameMin() + rndInt(MISSION_TTL[0], MISSION_TTL[1]),
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
    } else if (c.kind === 'police') {  // V2.5：餵情報的臨場抉擇
      S.police = clamp100(S.police + (c.police || 0));
      S.trust = clamp100(S.trust + (c.trust || 0));
      emit('toast', { icon: '🕵️', text: `情報交出去了——警方進度 +${c.police}，組織信任 ${c.trust}` });
    } else if (c.kind === 'pay') {     // V2.5：花錢／立威型抉擇
      if (S.money >= (c.cost || 0)) {
        S.money -= (c.cost || 0);
        S.trust = clamp100(S.trust + (c.trust || 0));
        if (c.sus) addSus(c.sus);
        emit('toast', { icon: '🤝', text: c.cost ? `花了 $${c.cost.toLocaleString()} 擺平，氣氛維持住了` : '立威成功，但大家心裡都有數了' });
      } else {
        S.trust = clamp100(S.trust - 5);
        emit('toast', { icon: '💸', text: '錢不夠擺平——場面有點難看（信任 -5）' });
      }
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

    // V2：20:00 風聲擲骰 → 02:00 深夜發動攻堅（暫停中鐘不走，不會跳過觸發點）
    if (S.min === RAID.WARN_MIN) rollRaid();
    if (S.min === RAID.HIT_MIN && S.raid && S.raid.phase === 'warn') startRaid();

    // V2.5：任務時效——過期的標記自動熄掉
    let expired = false;
    for (let i = S.missions.length - 1; i >= 0; i--) {
      if (S.missions[i].expireMin && gm >= S.missions[i].expireMin) { S.missions.splice(i, 1); expired = true; }
    }
    if (expired) emit('missions');

    // V2.5：藏錢天亮挖回（磨損一成）
    if (S.buried && gm >= S.buriedRefund) {
      const back = Math.round(S.buried * (1 - BURY_FEE));
      S.money += back; S.buried = 0; S.buriedRefund = 0;
      emit('toast', { icon: '🪙', text: `挖開地板——藏的錢回來了（+${back.toLocaleString()}）` });
    }

    // V2.5：貢金——18:00 預告、21:00 收（錢的長期出口）
    if (S.day >= TRIBUTE.FROM_DAY) {
      if (S.min === TRIBUTE.WARN_MIN) {
        emit('toast', { icon: '🏹', text: `今晚 21:00 上頭要收貢金 $${tributeCost().toLocaleString()}——帳上不夠就等著被教訓` });
      } else if (S.min === TRIBUTE.AT_MIN) {
        const cost = tributeCost();
        if (S.money >= cost) {
          S.money -= cost;
          S.trust = clamp100(S.trust + TRIBUTE.PAID_TRUST);
          emit('toast', { icon: '🏹', text: `上繳貢金 $${cost.toLocaleString()}，上頭滿意（信任 +${TRIBUTE.PAID_TRUST}）` });
        } else {
          S.money = 0;
          S.trust = clamp100(S.trust - TRIBUTE.SHORT_TRUST);
          emit('toast', { icon: '😤', text: `貢金繳不出來——老闆的電話罵了整整一分鐘（信任 -${TRIBUTE.SHORT_TRUST}）` });
        }
        after();
      }
    }

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

  // ===== V2：夜間警方攻堅（風聲 → 深夜突擊 → 策略結算；重傷不致死） =====
  function raidChance() {
    let p = RAID.BASE + Math.min(RAID.DAY_CAP, Math.max(0, S.day - RAID.GRACE_DAYS) * RAID.DAY_RAMP)
      + (S.sus / 100) * RAID.SUS_MULT + (S.police / 100) * RAID.POLICE_MULT;
    if (S.lastRaidDay === S.day) p *= 0.5;  // 凌晨剛被打過，連夜轟炸機率減半
    return Math.max(RAID.P_MIN, Math.min(RAID.P_MAX, p));
  }

  function raidStrength() {
    let s = RAID.STRENGTH_BASE + S.day * RAID.STRENGTH_DAY
      + S.sus * RAID.STRENGTH_SUS + S.police * RAID.STRENGTH_POLICE;
    if (S.buildings.fence) s *= RAID.FENCE_CUT;
    if (!S.raidCount) s *= RAID_FIRST_RELIEF;  // 第一次只是試探規模，打六折
    s *= 0.9 + Math.random() * 0.25;           // 每晚浮動 0.9~1.15×，不吃老本
    return Math.round(s);
  }

  // 花錢消災的當前價（越用越貴）
  function raidBribeCost() {
    return Math.min(RAID.BRIBE_CAP, RAID.BRIBE_PRICE + (S.bribeCount || 0) * RAID.BRIBE_STEP);
  }

  // ===== V2.5：藏錢（風聲期間把一半現金藏進地板，防被抄） =====
  function buryCash() {
    if (!S || S.ended || S.buried) return false;
    if (!S.raid || S.raid.phase !== 'warn') return false;
    const amt = Math.floor(S.money / 2);
    if (amt < 500) { emit('toast', { icon: '🪙', text: '帳上錢太少，不用藏' }); return false; }
    S.money -= amt;                                // 藏的當下就離帳——被抄/貢金都碰不到
    S.buried = amt;
    S.buriedRefund = (S.day + 1) * 1440 + 8 * 60;  // 隔天 08:00 挖回
    after();
    emit('toast', { icon: '🪙', text: `把 $${amt.toLocaleString()} 藏進地板（天亮取回、磨損一成）` });
    return true;
  }

  // ===== V2.5：貢金額度（隨天數成長） =====
  function tributeCost() {
    return Math.min(TRIBUTE.CAP, TRIBUTE.BASE + Math.max(0, S.day - TRIBUTE.FROM_DAY) * TRIBUTE.PER_DAY);
  }

  function rollRaid() {
    if (S.raid || S.ended || S.day <= RAID.GRACE_DAYS) return;
    if (Math.random() >= raidChance()) return;
    S.raid = { phase: 'warn', strength: raidStrength() };
    Save.write(S);
    emit('toast', { icon: '📡', text: '線報：今晚風聲很緊，警方可能在集結突擊——深夜前快做準備！' });
    emit('raidWarn');
  }

  function startRaid() {
    S.raid.phase = 'fight';
    paused = true;
    Save.write(S);
    emit('raid', { strength: S.raid.strength });
  }

  // 玩家選定策略 → 一次結算。不新增結局路徑：攻堅是大失血，死亡仍走信任歸零／懷疑滿百
  function resolveRaid(planId) {
    const raid = S.raid;
    if (!raid || raid.phase !== 'fight') return null;
    if (!RAID_PLANS.some((x) => x.id === planId)) return null;
    if (planId === 'car' && !S.gear.car) return null;
    if (planId === 'bribe' && S.money < RAID.BRIBE_PRICE) return null;

    // 只有在園區的成員參與攻防——出勤中的躲過這劫、看守所裡的本來就進去了
    const home = S.members.filter((m) => m.state === 'idle');
    const r = { plan: planId, win: false, strength: raid.strength, def: 0, seized: 0, caught: [], broken: null, trust: 0, sus: 0 };

    if (planId === 'bribe') {
      const cost = raidBribeCost();
      S.money -= cost;
      S.bribeCount = (S.bribeCount || 0) + 1;
      r.win = true; r.sus = -5; r.bribeCost = cost;
    } else {
      let def, edge;
      if (planId === 'car') {
        S.gear.car = false; r.carLost = true;
        def = 28 + home.length * 3; edge = 0.85;   // 突擊隊分兵追車，判定門檻降低
      } else if (planId === 'hide') {
        def = home.length * 4 + (S.buildings.fence ? 15 : 0); edge = 1;
      } else { // fight
        const best = home.length ? home.reduce((s, m) => s + Math.max(m.gab, m.legs, m.luck), 0) / home.length : 0;
        def = home.length * 8 + best * 2; edge = 1;
      }
      r.def = Math.round(def);
      r.win = def + rndInt(-10, 10) >= raid.strength * edge;
    }

    if (r.win) {
      if (planId === 'fight') { r.trust = 6; r.sus = -10; }   // 硬仗打贏，上頭另眼相看
      else if (planId === 'hide') { r.trust = 2; r.sus = -6; }
    } else {
      // 被抄現金：迎戰敗北最痛，躲藏次之，棄車最輕（突擊隊追車去了）
      const pct = planId === 'fight' ? RAID.SEIZE_PCT : planId === 'hide' ? 0.15 : 0.10;
      const cap = planId === 'fight' ? RAID.SEIZE_CAP : planId === 'hide' ? 20000 : 15000;
      r.seized = Math.min(Math.round(S.money * pct), cap);
      S.money -= r.seized;
      if (planId === 'fight') {
        r.trust = -8; r.sus = 10;
        // 前線成員被逮 1-2 人（可保釋）
        const nCatch = Math.min(home.length, rndInt(1, 2));
        for (let i = 0; i < nCatch; i++) {
          const pool = home.filter((m) => m.state === 'idle');
          if (!pool.length) break;
          const mem = pool[(Math.random() * pool.length) | 0];
          mem.state = 'jail';
          mem.jailUntil = Date.now() + rndInt(JAIL_MIN[0], JAIL_MIN[1]) * 60000;
          mem.caught++;
          r.caught.push(mem.name);
        }
        // 隨機一棟已完工設施被撞壞——拆掉了要重新蓋（施工中的不受影響）
        const built = Object.keys(S.buildings);
        if (built.length) {
          const bid = built[(Math.random() * built.length) | 0];
          delete S.buildings[bid];
          r.broken = bid;
          emit('buildings');
        }
      } else if (planId === 'hide') {
        r.trust = -4; r.sus = 6;
      } else { // car
        r.trust = -6; r.sus = 2;
      }
      emit('roster');
    }
    S.trust = clamp100(S.trust + r.trust);
    S.sus = clamp100(S.sus + r.sus);
    S.lastRaidDay = S.day;
    S.raidCount = (S.raidCount || 0) + 1;
    S.raid = null;
    paused = false;
    after();
    emit('raidResult', r);
    return r;
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
    if (S.raid === undefined) S.raid = null;       // V2 攻堅欄位
    if (!S.lastRaidDay) S.lastRaidDay = 0;
    if (!S.buried) S.buried = 0;                   // V2.5 欄位
    if (!S.buriedRefund) S.buriedRefund = 0;
    if (!S.raidCount) S.raidCount = 0;
    if (!S.bribeCount) S.bribeCount = 0;
    for (const m of S.missions) if (!m.expireMin) m.expireMin = gameMin() + MISSION_TTL[0];
    S.v = 2;
    // 關頁時正好在攻堅決策：恢復暫停，ui 進場後會重彈策略卡
    if (S.raid && S.raid.phase === 'fight') paused = true;
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
    assign, chooseEvent, bail, hire, buyGear, buyIntel, genMission, resolveRaid,
    build, buyFood, memberCap, buryCash, tributeCost, raidBribeCost,
    memberById, bailCost,
    state: () => S,
    isPaused: () => paused,
    hour, policeDensity, clockStr, gameMin,
  };
})();
