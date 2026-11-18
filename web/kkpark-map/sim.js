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
      act2: false, evidence: 0, hqRaidFail: 0, cells: null,     // V3.0 第二幕
      hero: { pos: { lat: HQ.lat + 0.0012, lng: HQ.lng - 0.0009 } },  // V3.5 主角（出生偏移到總部西南側，避開門口巡查熱點）
      poiCd: {}, poiUnlock: false,   // V3.6-A 互動地標：各地標冷卻時間、新任務來源解鎖旗標
    };
    for (let i = 0; i < START.members; i++) S.members.push(makeMember());
    for (let i = 0; i < START.missions; i++) genMission();
    armHeroGrace();  // V3.5：新局進場盤查免疫
  }

  // ===== V2.7/V2.8：勢力範圍——瓣狀形狀，隨建築／信任／警方進度進退 =====
  // 詐團瓣：總部＋每棟已完工建築各一瓣，半徑隨信任（地盤是你蓋出來的形狀）
  // 警方瓣：分局＋附近路網決定性挑出的派出所點，半徑隨警方進度與懷疑
  function parkRadius() { return TURF.PARK_BASE + S.trust * TURF.PARK_TRUST; }
  function policeRadius() { return TURF.POLICE_BASE + S.police * TURF.POLICE_PROG + S.sus * TURF.POLICE_SUS; }

  // 詐團勢力瓣清單 [{lat, lng}]——總部＋建築（B_SPOTS 位移對齊地圖上的建築圖示）
  const B_OFFSETS = [[0.0018, 0.0018], [0.0018, -0.0018], [-0.0018, 0.0018], [-0.0018, -0.0018], [0.0028, 0]];
  function parkPetals() {
    const list = [{ lat: HQ.lat, lng: HQ.lng }];
    BUILDINGS.forEach((b, i) => {
      if (S.buildings[b.id]) {
        const [dLat, dLng] = B_OFFSETS[i % B_OFFSETS.length];
        list.push({ lat: HQ.lat + dLat, lng: HQ.lng + dLng });
      }
    });
    return list;
  }

  // 警方勢力瓣清單——分局核心＋附近路網上決定性挑出的派出所點（同一存檔永遠同一批）
  let policePetalsCache = null;
  function policePetals() {
    if (policePetalsCache) return policePetalsCache;
    const list = [{ lat: TURF.POLICE_CENTER.lat, lng: TURF.POLICE_CENTER.lng }];
    if (typeof ROAD_NET !== 'undefined' && ROAD_NET.length) {
      const c = TURF.POLICE_CENTER, picked = [];
      for (const ch of ROAD_NET) {
        for (const p of ch) {
          const d = Math.hypot(p[1] - c.lng, p[0] - c.lat);
          if (d > 0.012 && d <= 0.03) picked.push({ p, d });
        }
      }
      // 決定性挑選：依距離排序後用固定種子雜湊挑點，並拉開最小間距避免疊成一團
      picked.sort((a, b) => a.d - b.d);
      const want = TURF.POLICE_SUBS, MIN_GAP = 0.014;
      for (const cand of picked) {
        if (list.length >= want + 1) break;
        if (Math.abs(hash3Str(cand.p[0] + ',' + cand.p[1], 7)) % 1000 / 1000 > 0.6) continue;
        if (list.concat(picked).length && list.every((q) => Math.hypot(cand.p[1] - q.lng, cand.p[0] - q.lat) >= MIN_GAP)) {
          list.push({ lat: cand.p[0], lng: cand.p[1] });
        }
      }
      // 補不滿就用方位角均勻補點（保證形狀完整）
      while (list.length < want + 1) {
        const ang = (list.length / (want + 1)) * Math.PI * 2;
        list.push({ lat: c.lat + Math.sin(ang) * 0.022, lng: c.lng + Math.cos(ang) * 0.022 });
      }
    } else {
      for (let i = 1; i <= TURF.POLICE_SUBS; i++) {
        const ang = (i / (TURF.POLICE_SUBS + 1)) * Math.PI * 2;
        list.push({ lat: TURF.POLICE_CENTER.lat + Math.sin(ang) * 0.022, lng: TURF.POLICE_CENTER.lng + Math.cos(ang) * 0.022 });
      }
    }
    policePetalsCache = list;
    return list;
  }

  // 簡易字串雜湊（派出所挑選用，決定性）
  function hash3Str(str, salt) {
    let h = salt | 0;
    for (let i = 0; i < str.length; i++) h = (Math.imul(h ^ str.charCodeAt(i), 2654435761) | 0);
    h ^= h >>> 13;
    return Math.abs(h);
  }

  function zoneOf(lat, lng) {
    let inPark = false, inPolice = false;
    const pr = parkRadius(), qr = policeRadius();
    for (const p of parkPetals()) {
      if (Math.hypot(lng - p.lng, lat - p.lat) <= pr) { inPark = true; break; }
    }
    if (!inPark || true) {
      for (const p of policePetals()) {
        if (Math.hypot(lng - p.lng, lat - p.lat) <= qr) { inPolice = true; break; }
      }
    }
    if (inPark && inPolice) return 'contested';
    if (inPark) return 'park';
    if (inPolice) return 'police';
    return 'none';
  }

  // ===== V3.0：第二幕——破門行動（總部決戰）→ 陣營反轉 → 掃蕩據點 =====
  const ACT2_HQ_POS = { lat: 22.672, lng: 120.318 };  // 詐團總部（東北 ~2.5km）

  function hqRaidReady() { return S.police >= ACT2.UNLOCK_POLICE && S.evidence >= ACT2.EVIDENCE_NEED; }

  // 蒐證任務結算掛點：成功 → evidence+1＋警方進度
  function onEvidenceSuccess() {
    S.evidence++;
    S.police = clamp100(S.police + ACT2.EVIDENCE_POLICE);
    emit('toast', { icon: '🔍', text: `蒐證到手（${S.evidence}/${ACT2.EVIDENCE_NEED}）——總部的帳冊快湊齊了，警方進度 +${ACT2.EVIDENCE_POLICE}` });
    if (S.evidence >= ACT2.EVIDENCE_NEED) {
      emit('toast', { icon: '🚪', text: '破門行動就緒！點地圖上的 🏚️ 詐團總部發動決戰' });
    }
    emit('missions');
  }

  // 總部決戰：三戰法一張卡（同攻堅決策的介面語言），成敗都在這裡定案
  function resolveHqRaid(planId) {
    if (!hqRaidReady() || S.act2) return null;
    const plan = ACT2.HQ_RAID.PLANS.find((x) => x.id === planId);
    if (!plan) return null;
    if (plan.cost && S.money < plan.cost) return null;
    if (plan.cost) S.money -= plan.cost;
    // 判定：警方進度＋蒐證＋戰法修正 vs 固定難度＋失手遞增（詐團愈防愈緊）
    const power = S.police * 0.9 + S.evidence * 6 + (S.gear.vpn ? 4 : 0);
    const need = 55 + S.hqRaidFail * 8;
    const win = power * plan.mod + rndInt(-8, 8) >= need;
    const r = { plan: planId, win, power: Math.round(power * plan.mod), need, name: plan.name };
    if (win) {
      S.police = clamp100(S.police + plan.winPolice);
      startAct2();
      emit('hqRaidResult', r);
    } else {
      S.police = clamp100(S.police + plan.losePolice);
      S.evidence = Math.max(0, S.evidence - 1);   // 打草驚蛇，一份蒐證作廢
      addSus(ACT2.HQ_RAID.LOSE_SUS);
      S.hqRaidFail++;
      after();
      emit('hqRaidResult', r);
    }
    return r;
  }

  // 陣營反轉：同一套系統攻守互換
  function startAct2() {
    S.act2 = true;
    // 數值重鑄：懷疑 → 詐團仇恨（他們知道你反了）；信任 → 警方倚重（安家費）
    S.sus = clamp100(S.sus + 30);
    S.trust = clamp100(S.trust + 10);
    // 生成 NPC 據點（owner 欄位預留未來真人版）
    S.cells = ACT2.CELLS.map((c) => ({ ...c, owner: 'npc', suppress: ACT2.CELL_SUPPRESS_BASE }));
    // 派遣中的舊任務作廢，成員回家
    for (const id in S.jobs) { const mem = memberById(id); if (mem && mem.state === 'onjob') mem.state = 'idle'; }
    S.jobs = {};
    S.missions = [];
    for (let i = 0; i < 4; i++) genMission();
    S.raid = null;
    S.lastRaidDay = 0;
    Save.write(S);
    emit('roster'); emit('missions'); emit('buildings');
    emit('act2');
  }

  // 掃蕩結算：成功壓低目標據點鎮壓條（任務 code 帶 cellId）
  function sweepSettle(job, ok) {
    const cellId = job.m.cellId;
    const cell = (S.cells || []).find((x) => x.id === cellId);
    if (!cell) return;
    if (ok) {
      cell.suppress = Math.max(0, cell.suppress - rndInt(22, 34));
      S.trust = clamp100(S.trust + ACT2.SWEEP_TRUST);
      if (cell.suppress <= 0) {
        S.cells = S.cells.filter((x) => x.id !== cellId);
        S.police = clamp100(S.police + 12);
        emit('toast', { icon: '🏁', text: `${cell.name} 端掉了！${cell.boss} 被移送——警方進度 +12` });
        if (!S.cells.length) {
          S.police = 100;
          emit('toast', { icon: '🌅', text: '最後一個據點倒了——全台收網，塵埃落定' });
        }
        after();
      } else {
        emit('toast', { icon: '🔨', text: `${cell.name} 鎮壓條壓到 ${cell.suppress}%——再掃幾輪就能端掉` });
      }
    } else {
      cell.suppress = Math.min(100, cell.suppress + 6);  // 打草驚蛇，據點回血
      addSus(6);
    }
    emit('missions');
  }

  // ===== 任務生成：在指定點附近撒（沒給就撒在園區總部附近）=====
  // V3.6-A 任務池：解鎖「街頭幫忙」後多出新任務來源（權重 18）
  function missionPool() {
    if (S && S.poiUnlock) return MISSION_POOL.concat([{ k: 'side', w: 18 }]);
    return MISSION_POOL;
  }

  function genMission(center) {
    const c = center || HQ;
    // V3.0：掃蕩撒在存活據點附近、蒐證撒在總部附近，其餘照舊撒園區附近
    let c2 = c;
    if (S.act2 && S.cells && S.cells.length) {
      const cell = S.cells[(Math.random() * S.cells.length) | 0];
      c2 = { lat: cell.lat, lng: cell.lng };
    } else if (!S.act2 && S.police >= ACT2.UNLOCK_POLICE && Math.random() < 0.3) {
      c2 = ACT2_HQ_POS;
    }
    // V3.0：任務池跟著劇幕走——二幕只有掃蕩；一幕後期摻蒐證（進度 ≥ 解鎖值）
    let tk;
    if (S.act2) {
      tk = 'sweep';
    } else if (S.police >= ACT2.UNLOCK_POLICE) {
      const base = missionPool();
      const total = base.reduce((s, x) => s + x.w, 0);
      let r = Math.random() * (total + 25), pool = base.concat([{ k: 'evidence', w: 25 }]);
      tk = 'scam';
      for (const x of pool) { r -= x.w; if (r <= 0) { tk = x.k; break; } }
    } else {
      const pool = missionPool();          // V3.6-A：解鎖後會多出新任務來源
      const total = pool.reduce((s, x) => s + x.w, 0);
      let r = Math.random() * total; tk = 'scam';
      for (const x of pool) { r -= x.w; if (r <= 0) { tk = x.k; break; } }
    }
    const t = MISSION_TYPES[tk] || ACT2_MISSION_TYPES[tk];
    const heat = 0.35 + Math.random() * 0.65;
    // V2.6：任務點坐在路網上——從園區附近的路網取樣點挑一個（沒路網資料則退回隨機）
    let lat = Math.min(TW.latR[1], Math.max(TW.latR[0], c2.lat + (Math.random() - 0.5) * 0.07));
    let lng = Math.min(TW.lngR[1], Math.max(TW.lngR[0], c2.lng + (Math.random() - 0.5) * 0.09));
    if (typeof ROAD_NET !== 'undefined' && ROAD_NET.length) {
      const cand = [];
      for (const ch of ROAD_NET) {
        for (const p of ch) {
          if (Math.abs(p[0] - c2.lat) <= 0.035 && Math.abs(p[1] - c2.lng) <= 0.045) cand.push(p);
        }
      }
      if (cand.length) { const p = cand[(Math.random() * cand.length) | 0]; lat = p[0]; lng = p[1]; }
    }
    // V2.5：距離參與決策——遠的錢多、風險也高，近的快但薄
    // 生成範圍 lat ±0.035 / lng ±0.045（最大 dist ≈ 0.057），門檻與倍率對齊這個範圍
    const dist = Math.hypot(lng - HQ.lng, lat - HQ.lat);
    const distMult = 0.85 + Math.min(1, dist / 0.055) * 0.55;
    // V2.7：落在誰的圈內，風險與報酬就不同（地盤安穩、警方圈高危高報酬）
    const zone = zoneOf(lat, lng);
    const zm = TURF.ZONES[zone];
    const m = {
      id: 'j' + (S.nextMid++), type: tk,
      lat, lng,
      pay: Math.round(rndInt(t.pay[0], t.pay[1]) * distMult * zm.pay),
      durMin: rndInt(t.dur[0], t.dur[1]),
      risk: Math.min(0.9, (t.risk * (0.6 + heat * 0.8) + dist * 1.4) * zm.risk),
      zone,
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
    if (m.type === 'evidence') { onEvidenceSuccess(); }
    else if (m.type === 'sweep') {
      const pay = Math.round(m.pay * (1 + (job.bonus || 0)) * (S.buildings.generator ? 1.15 : 1));
      S.money += pay;
      sweepSettle(job, true);
      emit('toast', { icon: '💵', text: `${m.code} 掃蕩完成，進帳 $${pay.toLocaleString()}` });
    }
    else if (m.type === 'intel') {
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
    if (m.type === 'sweep') { sweepSettle({ m }, false); }
    else if (m.type === 'intel') { S.police = clamp100(S.police + 4); addSus(15); }
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

  // ===== V3.5：主角（玩家化身）——WASD 操控、碰警車觸發盤查 =====
  const keys = {};  // 按住的鍵：{ up, down, left, right }
  function setKey(dir, on) { keys[dir] = !!on; }
  let heroCheckCd = 0;  // 盤查冷卻（gameMin），避免貼著警車連續彈卡
  const OFFROAD_DIST = 0.0004;   // 離最近街道超過此距離（~45m）＝離路狀態
  const OFFROAD_SLOW = 0.5;      // 離路減速係數（速度打 5 折，QA 實玩後再調）
  function armHeroGrace() { heroCheckCd = gameMin() + 12; }  // 進場 12 遊戲分鐘免疫（主角出生在總部，總部周邊必有巡查車）

  // ── V3.5.1 貼路行走：路網點格子索引（400m 格，跟 map.js 同款），最近點查詢 ──
  const ROAD_CELL = 0.004;
  let roadGrid = null;
  function buildRoadGrid() {
    roadGrid = new Map();
    for (const chain of ROAD_NET) {
      for (const p of chain) {
        const key = Math.floor(p[0] / ROAD_CELL) + ',' + Math.floor(p[1] / ROAD_CELL);
        let arr = roadGrid.get(key);
        if (!arr) roadGrid.set(key, (arr = []));
        arr.push(p);
      }
    }
  }
  // 最近路網點：從 3x3 格起步、找不到再擴到 7x7；全空回 null（離路網太遠＝自由行走）
  function nearestRoad(lat, lng) {
    if (!roadGrid && typeof ROAD_NET !== 'undefined' && ROAD_NET.length) buildRoadGrid();
    if (!roadGrid) return null;
    const gy = Math.floor(lat / ROAD_CELL), gx = Math.floor(lng / ROAD_CELL);
    for (const r of [1, 2, 3]) {
      let best = null, bestD = Infinity;
      for (let yy = gy - r; yy <= gy + r; yy++) {
        for (let xx = gx - r; xx <= gx + r; xx++) {
          const arr = roadGrid.get(yy + ',' + xx);
          if (!arr) continue;
          for (const p of arr) {
            const d = (p[0] - lat) * (p[0] - lat) + (p[1] - lng) * (p[1] - lng);
            if (d < bestD) { bestD = d; best = p; }
          }
        }
      }
      if (best) return { lat: best[0], lng: best[1], dist: Math.sqrt(bestD) };
    }
    return null;
  }

  function heroTick() {
    if (!S || !S.hero) return;
    let base = MOVE_DEG * (S.gear.car ? MOVE_CAR_MULT : 1);
    // V3.7 離路減速：離最近街道超過閾值＝在建築/巷弄裡鑽，速度打 5 折（路上全速，
    // 切進建築明顯變黏——用速度對比取代建築遮擋的體感設計；吸附是拉回力度、減速是速度懲罰，兩者獨立）
    const here = nearestRoad(S.hero.pos.lat, S.hero.pos.lng);
    const offRoad = here && here.dist > OFFROAD_DIST;
    if (offRoad) base *= OFFROAD_SLOW;
    S.hero.offRoad = !!offRoad;   // 給視覺提示層（marker 變暗）用
    let dx = 0, dy = 0;
    if (keys.left) dx -= 1; if (keys.right) dx += 1;
    if (keys.up) dy -= 1; if (keys.down) dy += 1;
    if (dx || dy) {
      // 貼路行走：往輸入方向走，但位置吸附到最近的路網點（跟巡查車同一套路網）；
      // 離路網越遠＝在巷弄／建築裡鑽，越慢（街区感），吸附力道隨距離衰減
      const d = Math.hypot(dx, dy);
      const p = S.hero.pos;
      let nlat = p.lat + (-dy / d) * base;   // 螢幕上＝緯度增加（Leaflet y 向下、緯度向上）
      let nlng = p.lng + (dx / d) * base;
      const snap = nearestRoad(nlat, nlng);
      if (snap) {
        const k = snap.dist < 0.0004 ? 0.55 : snap.dist < 0.0012 ? 0.3 : 0.12;  // 路上→小巷→建築區的貼路力
        nlat += (snap.lat - nlat) * k;
        nlng += (snap.lng - nlng) * k;
      }
      p.lat = nlat; p.lng = nlng;
      S.hero.moving = true;
      emit('heroMove', p);
    } else if (S.hero.moving) {
      S.hero.moving = false;
      emit('heroMove', S.hero.pos);
    }
    // 巡查車互動：靠近才「有機率」被攔下問話（冷卻 30 遊戲分鐘；不是每次靠近都攔）
    if (!paused && !S.ended && gameMin() >= heroCheckCd) {
      const pos = GameMap.copPositions();
      for (const c of pos) {
        if (Math.hypot(c.lat - S.hero.pos.lat, c.lng - S.hero.pos.lng) < 0.0004) {
          if (Math.random() < 0.35) {   // 撞上了，但七成機率對方沒注意你——放行
            heroCheckCd = gameMin() + 30;
            paused = true;
            emit('heroCheck', S.hero.pos);
          } else {
            heroCheckCd = gameMin() + 6;  // 這次沒事，短冷卻後再算
          }
          break;
        }
      }
    }
  }

  // 例行查崗抉擇（heroCheck 卡的三個選項）
  function resolveHeroCheck(idx) {
    paused = false;
    if (idx === 0) {           // 低調路過：小機率被記一筆
      if (Math.random() < 0.25) { addSus(5); emit('toast', { icon: '👁️', text: '對方多看了你兩眼，記了一筆（懷疑 +5）' }); }
      else emit('toast', { icon: '🚶', text: '你低頭滑手機走過去，對方沒理你' });
    } else if (idx === 1) {    // 快步離開：速度判定（腿力），失敗被登記
      const mem = S.members[0];
      const p = 0.45 + (mem ? mem.legs : 3) * 0.06 + (S.gear.car ? 0.15 : 0);
      if (Math.random() < Math.min(0.9, p)) emit('toast', { icon: '🏃', text: '你轉進巷子甩掉了這次查崗' });
      else {
        S.police = clamp100(S.police + 4); addSus(10);
        S.hero.pos = { lat: HQ.lat + 0.0012, lng: HQ.lng - 0.0009 };
        emit('toast', { icon: '🚨', text: '沒走成——被登記資料後放回（風聲 +4、懷疑 +10）' });
      }
    } else {                   // 亮出線人身分：風聲微增、組織信任微降
      S.police = clamp100(S.police + 3);
      S.trust = clamp100(S.trust - 2);
      emit('toast', { icon: '🪪', text: '你亮了亮手機裡的聯絡人——對方放行（風聲 +3、組織信任 -2）' });
    }
    after();
  }

  // ===== V3.6-A 互動地標（POI）：主角走近 → 進去看看 → 小事件 =====
  const POI_COOLDOWN = 180;   // 同一個地標的冷卻（遊戲分鐘，約 3 遊戲小時）
  const POI_RANGE = 0.0016;   // 互動距離（度）≈ 180m

  // POI 清單：座標吸附到最近街道節點（跟主角走路同一套路網，POI 就落在街上）
  function poiList() {
    if (!S) return [];
    return POI_DEFS.map((d) => {
      const snap = nearestRoad(d.lat, d.lng);
      return {
        id: d.id, icon: d.icon, name: d.name, kind: d.kind,
        lat: snap ? snap.lat : d.lat, lng: snap ? snap.lng : d.lng,
        cd: (S.poiCd && S.poiCd[d.id]) || 0,
      };
    });
  }
  function poiById(id) {
    for (const p of poiList()) if (p.id === id) return p;
    return null;
  }
  // 主角走近某地標 → 回傳該地標（不在範圍或冷卻中回 null）
  function poiNearHero() {
    if (!S || !S.hero) return null;
    for (const p of poiList()) {
      if (gameMin() < p.cd) continue;
      if (Math.hypot(p.lat - S.hero.pos.lat, p.lng - S.hero.pos.lng) < POI_RANGE) return p;
    }
    return null;
  }

  // 觸發地標事件：依 kind 產生主角事件卡（複用現有事件 modal 的 A/B 兩選項）
  function triggerPoi(poiId) {
    const p = poiById(poiId);
    if (!p || !S.hero) return;
    if (gameMin() < p.cd) { emit('toast', { icon: '⏳', text: `${p.name}——你剛才才來過，等會兒再說` }); return; }
    if (Math.hypot(p.lat - S.hero.pos.lat, p.lng - S.hero.pos.lng) > POI_RANGE) {
      emit('toast', { icon: '🚶', text: `太遠了——走過去一點才能看${p.name}` });
      return;
    }
    S.poiCd = S.poiCd || {};
    S.poiCd[p.id] = gameMin() + POI_COOLDOWN;
    let ev;
    if (p.kind === 'coin') {
      const amt = 400 + ((Math.random() * 1600) | 0);
      ev = {
        icon: p.icon, title: `${p.name}：地上有東西`,
        text: `路邊的紙箱旁邊有張紙鈔，${amt} 元，不像是誰掉的。`,
        A: { label: `撿起來（+$${amt}）`, kind: 'coin', amt },
        B: { label: '不是自己的不拿', kind: 'skip' },
      };
    } else if (p.kind === 'friend') {
      ev = {
        icon: p.icon, title: `${p.name}：有人跟你搭話`,
        text: '一個街坊模樣的人湊過來，問你附近哪裡缺人跑腿。他說他有門路，可以介紹活兒給你。',
        A: { label: '交換號碼（解鎖新任務來源）', kind: 'friend' },
        B: { label: '含糊帶過', kind: 'skip' },
      };
    } else if (p.kind === 'bet') {
      ev = {
        icon: p.icon, title: `${p.name}：試手氣`,
        text: '櫃台上剩幾張沒刮的券。老闆說今天手氣正，要不要來一張？',
        A: { label: '買一張试试手氣', kind: 'bet' },
        B: { label: '看看就好', kind: 'skip' },
      };
    } else {   // random：從主角小事池抽一張
      const pool = [
        {
          icon: '🧋', title: `${p.name}：撞見熟人`,
          text: '一個熟識的傢伙正低頭吃東西，看到你招手要你過去坐。',
          A: { label: '坐下來聊聊（情報 + 信任）', kind: 'chat' },
          B: { label: '假裝沒看見', kind: 'skip' },
        },
        {
          icon: '📦', title: `${p.name}：有人託你帶東西`,
          text: '旁邊有人抱著紙箱問你能不能幫忙送到附近的一戶人家，跑一趟就有酬勞。',
          A: { label: '接下來跑一趟（+錢、信任 +）', kind: 'errand' },
          B: { label: '搖頭拒絕', kind: 'skip' },
        },
        {
          icon: '🕯️', title: `${p.name}：店裡的燈忽然滅了`,
          text: '燈滅了幾秒，恢復的時候櫃台少了一點東西，裡面的人盯著你。',
          A: { label: '裝作什麼都沒看到', kind: 'luck' },
          B: { label: '趁亂離開', kind: 'skip' },
        },
      ];
      ev = pool[(Math.random() * pool.length) | 0];
    }
    S.heroEvent = ev;
    paused = true;
    emit('heroEvent', { ev, poi: p });
    after();
  }

  // 主角事件抉擇（複用事件 modal 的 A/B）
  function chooseHeroEvent(idx) {
    const ev = S.heroEvent;
    S.heroEvent = null;
    paused = false;
    if (!ev) return;
    const c = idx === 0 ? ev.A : ev.B;
    if (c.kind === 'coin') {
      S.money += c.amt;
      emit('toast', { icon: '💰', text: `撿到 $${c.amt}——今天運氣不錯` });
    } else if (c.kind === 'friend') {
      S.poiUnlock = true;                       // 解鎖新任務來源（街頭幫忙）
      emit('toast', { icon: '🤝', text: '你留了個號碼——往後會有人託你跑腿（解鎖新任務來源）' });
    } else if (c.kind === 'bet') {
      const win = Math.random() < 0.3;
      const amt = win ? 3000 + ((Math.random() * 7000) | 0) : -600;
      S.money = Math.max(0, S.money + amt);
      emit('toast', { icon: win ? '🎉' : '😐', text: win ? `手氣不錯！刮出 $${amt}` : '沒中——小輸 $600' });
    } else if (c.kind === 'chat') {
      addSus(-4);
      S.trust = clamp100(S.trust + 2);
      emit('toast', { icon: '💬', text: '你們有一搭沒一搭聊了幾句——好像打聽到一些事（懷疑 -4、信任 +2）' });
    } else if (c.kind === 'errand') {
      const amt = 1200 + ((Math.random() * 2800) | 0);
      S.money += amt;
      S.trust = clamp100(S.trust + 2);
      emit('toast', { icon: '📦', text: `你跑了一趟交貨——拿到 $${amt}（信任 +2）` });
    } else if (c.kind === 'luck') {
      if (Math.random() < 0.5) { addSus(6); emit('toast', { icon: '👀', text: '你裝得太不自然，被多看了一眼（懷疑 +6）' }); }
      else emit('toast', { icon: '😅', text: '沒人注意你——你裝得很像路過而已' });
    } else {
      emit('toast', { icon: '🚶', text: '你沒停下腳步，轉身走開了' });
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

    // 主角：操控移動＋警車盤查（放最後，移動不被暫停邏輯吃掉）
    heroTick();

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

    // V2：20:00 風聲擲骰 → 02:00 深夜發動（一幕＝警方攻堅；二幕＝詐團報復夜襲，同一套攻防）
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

    // V2.5：貢金——18:00 預告、21:00 收（錢的長期出口）；二幕反轉後不用再餵老闆
    if (S.day >= TRIBUTE.FROM_DAY && !S.act2) {
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
    let s;
    if (S.act2) {
      // 二幕：詐團報復——仇恨與剩餘據點撐強度（他們的「營收」也在燒）
      s = 34 + S.day * 1.5 + S.sus * 0.35 + (S.cells || []).length * 7;
    } else {
      s = RAID.STRENGTH_BASE + S.day * RAID.STRENGTH_DAY
        + S.sus * RAID.STRENGTH_SUS + S.police * RAID.STRENGTH_POLICE;
    }
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
    // 二幕：貢金沒了、警方不來了——改成詐團報復夜襲（仇恨＋剩餘據點越多越兇）
    if (S.act2) {
      let p = ACT2.RETALIATE_BASE + S.sus * ACT2.RETALIATE_SUS + (S.cells || []).length * ACT2.RETALIATE_PER_CELL;
      if (S.lastRaidDay === S.day) p *= 0.5;
      p = Math.max(0.08, Math.min(0.65, p));
      if (Math.random() >= p) return;
      S.raid = { phase: 'warn', strength: raidStrength(), kind: 'gang' };
      Save.write(S);
      emit('toast', { icon: '🐍', text: '線報：詐團知道你反水了——今晚可能有自己人來「清理門戶」！' });
      emit('raidWarn');
      return;
    }
    if (Math.random() >= raidChance()) return;
    S.raid = { phase: 'warn', strength: raidStrength(), kind: 'police' };
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
    // V3.0：結局語義跟著劇幕走——一幕：信任歸零滅口／懷疑滿收押／進度滿收網（勝）
    // 二幕：信任歸零＝被警方放棄滅口／懷疑滿（詐團仇恨爆表）＝被清理門戶／進度滿＝全台收網（勝）
    if (S.trust <= 0) S.ended = 'silenced';
    else if (S.sus >= 100) S.ended = S.act2 ? 'purged' : 'jailed';
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
    if (S.act2 === undefined) S.act2 = false;          // V3.0 第二幕欄位
    if (!S.evidence) S.evidence = 0;
    if (!S.hqRaidFail) S.hqRaidFail = 0;
    if (S.cells === undefined) S.cells = null;
    if (S.hero === undefined || !S.hero) S.hero = { pos: { lat: HQ.lat + 0.0012, lng: HQ.lng - 0.0009 } };  // V3.5 主角欄位（出生偏移避開門口巡查熱點）
    if (S.hero && Math.abs(S.hero.pos.lat - HQ.lat) < 1e-9 && Math.abs(S.hero.pos.lng - HQ.lng) < 1e-9) {
      // 舊存檔主角正好在總部原點：一併偏移，避免進場即被盤查
      S.hero.pos = { lat: HQ.lat + 0.0012, lng: HQ.lng - 0.0009 };
    }
    // V3.6-A 舊存檔補 POI 欄位
    if (!S.poiCd) S.poiCd = {};
    if (S.poiUnlock === undefined) S.poiUnlock = false;
    for (const m of S.missions) if (!m.expireMin) m.expireMin = gameMin() + MISSION_TTL[0];
    S.v = 2;
    // 關頁時正好在攻堅決策：恢復暫停，ui 進場後會重彈策略卡
    if (S.raid && S.raid.phase === 'fight') paused = true;
    armHeroGrace();  // V3.5：進場盤查免疫（12 遊戲分鐘）
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
    parkRadius, policeRadius, zoneOf, parkPetals, policePetals,
    hqRaidReady, resolveHqRaid, onEvidenceSuccess, sweepSettle, hqRaidFailCheck: () => S.hqRaidFail,
    act2HqPos: ACT2_HQ_POS,
    memberById, bailCost,
    state: () => S,
    isPaused: () => paused,
    hour, policeDensity, clockStr, gameMin,
    setKey, resolveHeroCheck,  // V3.5 主角操控與盤查
    poiList, poiNearHero, triggerPoi, chooseHeroEvent,  // V3.6-A 互動地標
  };
})();
