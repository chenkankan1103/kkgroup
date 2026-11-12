'use strict';
/* ui.js — HUD、派遣局名冊、花錢商店、任務面板、事件/結局/開場 + 主循環啟動 */

const UI = (() => {
  const $ = (id) => document.getElementById(id);

  /* ===== 玩法教學（❓ 可隨時重開；看過一次就不自動跳） ===== */
  const TUT_KEY = 'kkpark_map_tut_v1';
  function hasSeenHow() { try { return !!localStorage.getItem(TUT_KEY); } catch (e) { return true; } }
  function showHow() { $('howto').classList.remove('hidden'); }
  function hideHow() {
    $('howto').classList.add('hidden');
    try { localStorage.setItem(TUT_KEY, '1'); } catch (e) {}
    showToast({ icon: '👇', text: '點地圖上的任務標記（小牌子），派人去做事' });
  }

  /* ===== 開場 ===== */
  function boot() {
    GameMap.init();
    Sim.on('tick', onTick);
    Sim.on('missions', renderMissions);
    Sim.on('roster', renderRoster);
    Sim.on('toast', showToast);
    Sim.on('event', showEvent);
    Sim.on('raid', showRaidPlan);
    Sim.on('raidResult', showRaidResult);
    Sim.on('ending', showEnding);
    Sim.on('buildings', onBuildings);
    GameMap.cb.missionClick = openMission;

    const hasSave = !!Save.read();
    $('btnContinue').classList.toggle('hidden', !hasSave);
    if (hasSave) {
      $('introTitle').textContent = '園區還在運轉……';
      $('introStory').innerHTML = '偵測到先前的存檔——你的成員還在待命，看守所與大活都照真實時間在跑。<br>要回去繼續雙面人生嗎？';
    }
    $('btnStartNew').onclick = () => { Sim.newGame(); enterGame(); };
    $('btnContinue').onclick = () => { if (!Sim.load()) Sim.newGame(); enterGame(); };
    $('btnShop').onclick = () => { $('shop').classList.toggle('hidden'); renderShop(); };
    $('hudBury').onclick = () => Sim.buryCash();  // V2.5：風聲期間藏錢
    $('btnShopClose').onclick = () => $('shop').classList.add('hidden');
    $('btnMisClose').onclick = () => $('misPanel').classList.add('hidden');
    $('btnHelp').onclick = showHow;
    $('btnHowClose').onclick = hideHow;
  }

  function enterGame() {
    $('intro').classList.add('hidden');
    $('hud').classList.remove('hidden');
    $('roster').classList.remove('hidden');
    renderAll();
    // 關頁時正好在攻堅決策 → 進場重彈策略卡（sim.load 已恢復暫停）
    const S0 = Sim.state();
    if (S0.raid && S0.raid.phase === 'fight') showRaidPlan();
    GameMap.flyTo(HQ.lat, HQ.lng, 12);
    if (!hasSeenHow()) setTimeout(showHow, 900);
    if (Sim.state().ended) showEnding(Sim.state().ended);
    if (boot.loopId) clearInterval(boot.loopId);
    boot.loopId = setInterval(() => { Sim.tick(); onTick(); }, TICK_MS);
  }

  function renderAll() {
    renderRoster();
    renderMissions();
    GameMap.renderBuildings(Sim.state());
    onTick();
  }

  // 建設異動：重畫地圖工地；商店開著就一併重畫（按鈕會變成施工中）
  function onBuildings() {
    GameMap.renderBuildings(Sim.state());
    if (!$('shop').classList.contains('hidden')) renderShop();
  }

  /* ===== 每秒 HUD 更新 ===== */
  function onTick() {
    const S = Sim.state(); if (!S) return;
    const dens = Sim.policeDensity();
    $('hudClock').textContent = Sim.clockStr() + (dens >= 1.1 ? ' 🚨' : dens <= 0.5 ? ' 🌙' : ' ☀️');
    $('hudMoney').textContent = '💰 $' + S.money.toLocaleString();
    $('hudFood').textContent = '🍚 ' + S.food;
    $('hudFood').classList.toggle('low', S.food <= 3);
    $('fillTrust').style.width = S.trust + '%';
    $('fillPolice').style.width = S.police + '%';
    $('fillSus').style.width = S.sus + '%';
    if (S.min % 60 === 0) GameMap.refreshPolice();
    GameMap.renderJobs(S.jobs, S.members);
    GameMap.tickCops();  // V2.6：警車巡邏滑行（內部自己節流到每 5 遊戲分鐘）
    GameMap.renderTurf();  // V2.7：勢力圈半徑跟著信任／進度走（變動才重繪）
    // V2：風聲預警 chip（發動後由攻堅卡接手）
    $('hudRaid').classList.toggle('hidden', !(S.raid && S.raid.phase === 'warn'));
    // V2.5：藏錢 chip（風聲期間可藏一半現金防抄；藏了顯示凍結額度）
    const bury = $('hudBury');
    if (S.buried) {
      bury.classList.remove('hidden');
      bury.textContent = `🪙 已藏 $${S.buried.toLocaleString()}（天亮取回）`;
      bury.disabled = true;
    } else if (S.raid && S.raid.phase === 'warn') {
      bury.classList.remove('hidden');
      bury.textContent = '🪙 藏一半現金（防抄）';
      bury.disabled = false;
    } else {
      bury.classList.add('hidden');
    }
    // V2.5：貢金 chip（18:00–21:00；錢不夠就紅閃）
    const trib = $('hudTribute');
    const tShow = S.day >= TRIBUTE.FROM_DAY && S.min >= TRIBUTE.WARN_MIN && S.min < TRIBUTE.AT_MIN;
    trib.classList.toggle('hidden', !tShow);
    if (tShow) {
      const c = Sim.tributeCost();
      trib.textContent = '🏹 貢金 $' + c.toLocaleString();
      trib.classList.toggle('low', S.money < c);
    }
    tickBuildProgress();
    tickRoster();
  }

  // 工地進度：只改百分比文字，不重建商店按鈕（避免點擊被吃掉）
  function tickBuildProgress() {
    const S = Sim.state(); if (!S) return;
    document.querySelectorAll('#shopBody .bpct').forEach((el) => {
      const q = S.buildQueue.find((x) => x.id === el.dataset.bq);
      const b = BUILDINGS.find((x) => x.id === el.dataset.bq);
      if (!q || !b) return;
      const left = Math.max(0, q.doneMin - Sim.gameMin()); // 遊戲分鐘 = 真實秒
      el.textContent = left >= 120 ? `⚒️ 施工中 · 剩 ${Math.ceil(left / 60)} 分` : `⚒️ 施工中 · 剩 ${left} 秒`;
    });
  }

  /* ===== 派遣局名冊 ===== */
  function renderRoster() {
    const S = Sim.state(); if (!S) return;
    const el = $('roster');
    el.innerHTML = '<div class="roster-title">🕴️ 派遣局</div>' + S.members.map((mem) => {
      const st = mem.state;
      const stTxt = st === 'idle' ? '🟢 待命' : st === 'onjob' ? '🔵 出勤' : '🚳 看守所';
      return `<div class="mem-card" data-mem="${mem.id}">
        <div class="mem-top"><span class="ava">${mem.avatar}</span><b>${mem.name}</b><span class="st st-${st}">${stTxt}</span></div>
        <div class="mem-stats">🗣️ 口才 ${mem.gab} · 🏃 腿力 ${mem.legs} · 🍀 運氣 ${mem.luck}</div>
        <div class="mem-sub"></div>
        <div class="mem-actions"></div>
      </div>`;
    }).join('');
    tickRoster();
  }

  const fmtClock = (sec) => {
    const s = Math.max(0, Math.ceil(sec));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  };

  // 每秒只更新卡片內的進度/倒數（不重建按鈕，避免點擊被打斷）
  function tickRoster() {
    const S = Sim.state(); if (!S) return;
    document.querySelectorAll('#roster .mem-card').forEach((card) => {
      const mem = Sim.memberById(card.dataset.mem);
      if (!mem) return;
      const sub = card.querySelector('.mem-sub');
      const act = card.querySelector('.mem-actions');
      if (mem.state === 'onjob') {
        const job = S.jobs[mem.id];
        if (!job) return;
        let leftSec;
        if (job.mode === 'long') leftSec = (job.endRealMs - Date.now()) / 1000;
        else leftSec = Math.max(0, job.endMin - Sim.gameMin());
        const totalSec = job.m.durMin + (job.travelMin || 0) * 2; // 含來回趕路
        const pct = Math.min(100, Math.max(0, 100 - (leftSec / totalSec) * 100));
        const phase = job.leg === 'out' ? '🛵 趕路中'
          : job.leg === 'back' ? '🛵 溜回園區'
          : job.mode === 'long' ? '🌙 大活' : '⚡ 快跑';
        sub.innerHTML = `<div class="prog"><div style="width:${pct}%"></div></div>
          <div class="subtxt">${phase}·${MISSION_TYPES[job.m.type].name} · 剩 ${fmtClock(leftSec)}</div>`;
        if (act.childNodes.length) act.innerHTML = '';
      } else if (mem.state === 'jail') {
        const leftSec = (mem.jailUntil - Date.now()) / 1000;
        const cost = Sim.bailCost(mem);
        sub.innerHTML = `<div class="subtxt danger">關在看守所，剩 ${fmtClock(leftSec)} · 洩了一條線索給警方</div>`;
        if (!act.querySelector('button')) {
          const b = document.createElement('button');
          b.className = 'mini bail';
          b.onclick = () => Sim.bail(mem.id);
          act.appendChild(b);
        }
        const b = act.querySelector('button');
        b.textContent = `⚖️ 保釋 $${cost.toLocaleString()}`;
      } else {
        sub.innerHTML = '<div class="subtxt">待命中——點地圖上的任務圖釘派人</div>';
        if (act.childNodes.length) act.innerHTML = '';
      }
    });
  }

  /* ===== 任務面板 ===== */
  let curMissionId = null, curMode = 'short';

  function openMission(m) {
    curMissionId = m.id;
    curMode = 'short';
    GameMap.flyTo(m.lat, m.lng);
    $('misPanel').classList.remove('hidden');
    renderMissionDetail();
  }

  const fmtDur = (min) => `${min} 遊戲分鐘（≈${Math.max(1, Math.round(min / 60))} 分鐘）`;

  function renderMissionDetail() {
    const S = Sim.state(); if (!S) return;
    const m = S.missions.find((x) => x.id === curMissionId);
    if (!m) { $('misPanel').classList.add('hidden'); return; }
    const t = MISSION_TYPES[m.type];
    $('misBody').innerHTML = `
      <div class="mis-head">${t.icon} <b>${t.name}</b><span class="mis-code">${m.code}</span></div>
      <p class="mis-desc">${t.desc}</p>
      <div class="mis-rows">
        <div>💰 賞金 <b>$${m.pay.toLocaleString()}</b></div>
        <div>⏱ 時長 <b>${fmtDur(m.durMin)}</b></div>
        <div>🚨 風險 <b class="risk">${'★'.repeat(1 + Math.round(m.risk * 4))}</b></div>
        <div>🔥 熱度 <b>${m.heat > 0.75 ? '高' : m.heat > 0.45 ? '中' : '低'}</b></div>
        <div>🛵 距離 <b>${m.distTier || '中'}</b>（遠＝錢多）</div>
        <div>⏳ 時限 <b>${m.expireMin ? Math.max(0, Math.round(m.expireMin - Sim.gameMin())) + ' 分' : '不限'}</b></div>
        <div>🗺️ 勢力 <b>${(TURF.ZONES[m.zone] || TURF.ZONES.none).name}</b></div>
      </div>
      <div class="mode-row">
        <button class="mode ${curMode === 'short' ? 'on' : ''}" data-mode="short">⚡ 快跑<small>開著看戲 · 會跳事件</small></button>
        <button class="mode ${curMode === 'long' ? 'on' : ''}" data-mode="long">🌙 大活<small>時間×4 · 錢×2.2 · 可離線</small></button>
      </div>
      <div class="pick-title">派誰去？</div>
      <div class="mem-pick">${idleChips(m)}</div>
    `;
    $('misBody').querySelectorAll('.mode').forEach((b) => {
      b.onclick = () => { curMode = b.dataset.mode; renderMissionDetail(); };
    });
    $('misBody').querySelectorAll('.pick').forEach((b) => {
      b.onclick = () => {
        if (Sim.assign(b.dataset.mem, curMissionId, curMode)) {
          $('misPanel').classList.add('hidden');
          showToast({ icon: '⏳', text: '派出去了——🛵 趕路中，名冊看進度，時間到自動結算' });
        }
      };
    });
  }

  function idleChips(m) {
    const S = Sim.state();
    const idle = S.members.filter((x) => x.state === 'idle');
    if (!idle.length) return '<div class="none">沒有閒人——去招募，或等有人在看守所出來</div>';
    const best = MISSION_TYPES[m.type].stat, statName = MISSION_TYPES[m.type].statName;
    return idle.map((x) =>
      `<button class="pick" data-mem="${x.id}">${x.avatar} ${x.name}<small>${statName} ${x[best]}</small></button>`
    ).join('');
  }

  function renderMissions() {
    const S = Sim.state(); if (!S) return;
    GameMap.renderMissions(S.missions);
    $('misCount').textContent = S.missions.length;
    if (!$('misPanel').classList.contains('hidden') && curMissionId) renderMissionDetail();
  }

  /* ===== 花錢商店（含 🏗️ 建設、🍚 伙食）===== */
  function renderShop() {
    const S = Sim.state(); if (!S) return;
    const cap = Sim.memberCap();
    const full = S.members.length >= cap;
    $('shopBody').innerHTML = `
      <div class="shop-sec">🏗️ 園區建設</div>
      ${BUILDINGS.map((b) => {
        const built = S.buildings[b.id];
        const q = S.buildQueue.find((x) => x.id === b.id);
        return `<div class="shop-item ${built ? 'owned' : ''}">
          <span class="gi">${b.icon}</span>
          <div class="gi-body"><b>${b.name}</b><small>${b.desc}</small></div>
          ${built ? '<span class="owned-tag">✅</span>'
            : q ? `<span class="bpct" data-bq="${b.id}"></span>`
            : `<button class="mini" data-build="${b.id}">$${b.price.toLocaleString()}</button>`}
        </div>`;
      }).join('')}
      <div class="shop-sec">🍚 伙食</div>
      <div class="shop-item"><span class="gi">🍱</span>
        <div class="gi-body"><b>補一箱伙食</b><small>現有 ${S.food} 份 · 每人每天吃 ${S.buildings.kitchen ? 1 : FOOD_EAT} 份</small></div>
        <button class="mini" data-food="1">$${FOOD_PACK.price.toLocaleString()}（+${FOOD_PACK.amount}）</button></div>
      <div class="shop-sec">🔧 裝備</div>
      ${GEAR.map((g) => `<div class="shop-item ${S.gear[g.id] ? 'owned' : ''}">
        <span class="gi">${g.icon}</span>
        <div class="gi-body"><b>${g.name}</b><small>${g.desc}</small></div>
        ${S.gear[g.id] ? '<span class="owned-tag">✅</span>' : `<button class="mini" data-gear="${g.id}">$${g.price.toLocaleString()}</button>`}
      </div>`).join('')}
      <div class="shop-sec">🤝 招募</div>
      <div class="shop-item"><span class="gi">🧍</span>
        <div class="gi-body"><b>找個新人入夥</b><small>口才/腿力/運氣 三維隨機（3-8）· 人數 ${S.members.length}/${cap}</small></div>
        ${full ? '<span class="owned-tag">🛖 滿了</span>' : `<button class="mini" data-hire="1">$${PRICES.hire.toLocaleString()}</button>`}</div>
      <div class="shop-sec">🕵️ 情報管道</div>
      <div class="shop-item"><span class="gi">🗂️</span>
        <div class="gi-body"><b>砸錢買關鍵情報</b><small>警方進度 +${INTEL_BUY_POLICE}，貴，但即時</small></div>
        <button class="mini" data-intel="1">$${PRICES.intel.toLocaleString()}</button></div>
    `;
    $('shopBody').querySelectorAll('[data-build]').forEach((b) => { b.onclick = () => { Sim.build(b.dataset.build); renderShop(); tickBuildProgress(); }; });
    $('shopBody').querySelectorAll('[data-food]').forEach((b) => { b.onclick = () => { Sim.buyFood(); renderShop(); }; });
    $('shopBody').querySelectorAll('[data-gear]').forEach((b) => { b.onclick = () => { Sim.buyGear(b.dataset.gear); renderShop(); }; });
    $('shopBody').querySelectorAll('[data-hire]').forEach((b) => { b.onclick = () => { Sim.hire(); renderShop(); }; });
    $('shopBody').querySelectorAll('[data-intel]').forEach((b) => { b.onclick = () => { Sim.buyIntel(); renderShop(); }; });
  }

  /* ===== 事件視窗 ===== */
  function showEvent(a) {
    const ev = a.ev;
    const mem = Sim.memberById(a.memId);
    $('evIcon').textContent = ev.icon;
    $('evTitle').textContent = ev.title;
    $('evText').textContent = ev.text.replace('你的人', mem ? mem.name : '你的人');
    $('evA').textContent = '👉 ' + ev.A.label;
    $('evB').textContent = ev.B.label;
    $('eventModal').classList.remove('hidden');
    $('evA').onclick = () => { $('eventModal').classList.add('hidden'); Sim.chooseEvent(0); };
    $('evB').onclick = () => { $('eventModal').classList.add('hidden'); Sim.chooseEvent(1); };
  }

  /* ===== V2 警方攻堅：策略決策卡 → 戰報（同一個 modal 換內容） ===== */
  function showRaidPlan() {
    const S = Sim.state(); if (!S) return;
    if (!S.raid || S.raid.phase !== 'fight') return;
    const st = S.raid.strength;
    const lv = st >= 70 ? '★★★ 兇悍' : st >= 55 ? '★★ 堅硬' : '★ 一般';
    const home = S.members.filter((m) => m.state === 'idle').length;
    $('raidText').textContent = '探照燈掃進園區，突擊隊已經包上來了——決定全園的應對：';
    $('raidIntel').innerHTML =
      `<div>🚨 突擊強度評估：<b class="risk">${lv}（${st}）</b></div>` +
      `<div>🧍 在園區成員：<b>${home} 人</b>${home ? '' : '——沒人在，只能靠設施撐'}（出勤中的躲過這劫）</div>` +
      `<div>${S.buildings.fence ? '🚧 圍籬已就位：強度被壓低過' : '🚧 沒有圍籬：強度完整，考慮花錢消災'}</div>` +
      (!S.raidCount ? '<div>👀 第一次突擊只是試探規模——撐住就懂節奏了</div>' : '');
    $('raidPlans').innerHTML = RAID_PLANS.map((p) => {
      const bribeCost = p.id === 'bribe' ? Sim.raidBribeCost() : 0;
      const off = (p.id === 'car' && !S.gear.car) || (p.id === 'bribe' && S.money < bribeCost);
      const desc = p.id === 'bribe'
        ? `付 $${bribeCost.toLocaleString()} 擺平，今晚必定平安（越用越貴）` : p.desc;
      return `<button class="ev-btn plan" data-plan="${p.id}"${off ? ' disabled' : ''}>` +
        `${p.icon} ${p.name}<small>${off ? '（條件不符）' : desc}</small></button>`;
    }).join('');
    $('raidPlans').querySelectorAll('[data-plan]').forEach((b) => {
      b.onclick = () => {
        if (Sim.resolveRaid(b.dataset.plan)) GameMap.clearRaid();  // 結算成立 → 警車散去，戰報由事件接手
      };
    });
    $('raidModal').classList.remove('hidden');
    GameMap.raidAssembly(true);
  }

  function showRaidResult(r) {
    const S = Sim.state(); if (!S || !r) return;
    $('raidText').textContent = r.win
      ? '警笛聲在遠處熄滅——他們撲空了，園區還是你的。'
      : '突擊隊破門而入，園區被翻了一整夜……';
    const planName = (RAID_PLANS.find((p) => p.id === r.plan) || {}).name || '';
    const lines = [];
    if (r.plan === 'bribe') {
      lines.push(`💸 付了 $${(r.bribeCost || RAID.BRIBE_PRICE).toLocaleString()} 擺平，突擊臨時取消`);
    } else {
      lines.push(`${r.win ? '🛡️' : '💥'} ${planName}——防禦 ${r.def} vs 突擊 ${r.strength}`);
      if (r.carLost) lines.push('🏎️ 贓車被拖走了（商店可再買）');
      if (r.seized) lines.push(`💰 被抄走 $${r.seized.toLocaleString()}`);
      if (r.caught.length) lines.push(`🚨 被逮：${r.caught.join('、')}——關進看守所（可保釋）`);
      if (r.broken) {
        const b = BUILDINGS.find((x) => x.id === r.broken);
        if (b) lines.push(`⚒️ ${b.name}被撞壞了——商店重蓋`);
      }
    }
    if (r.trust) lines.push(`🏴 組織信任 ${r.trust > 0 ? '+' : ''}${r.trust}`);
    if (r.sus) lines.push(`👁️ 警方懷疑 ${r.sus > 0 ? '+' : ''}${r.sus}`);
    $('raidIntel').innerHTML = lines.map((l) => `<div>${l}</div>`).join('');
    $('raidPlans').innerHTML = '<button class="ev-btn main" id="btnRaidOk">😤 繼續經營</button>';
    $('btnRaidOk').onclick = () => $('raidModal').classList.add('hidden');
  }

  /* ===== 結局 ===== */
  const ENDINGS = {
    silenced: {
      icon: '🏴', title: '燈熄了',
      text: '老闆的助理把你叫進辦公室。門關上，燈熄了。兩天後，你的便當還放在座位上，沒有人敢動。',
      win: false,
    },
    jailed: {
      icon: '👁️', title: '核心犯收押',
      text: '收網名單上有你的名字——不是線人那份，是核心成員那份。警方當作什麼都沒發生。',
      win: false,
    },
    raid: {
      icon: '🚔', title: '全台收網',
      text: '清晨五點，22 縣市同步收網，新聞快報跑了一整天。你穿上防彈背心，帶著警方指出老闆的房間。',
      win: true,
    },
  };

  function showEnding(key) {
    const e = ENDINGS[key];
    const S = Sim.state();
    if (!e || !S) return;
    $('endIcon').textContent = e.icon;
    $('endTitle').textContent = e.title;
    $('endText').textContent = e.text;
    const caughtN = S.members.reduce((s, m) => s + m.caught, 0);
    $('endStats').innerHTML =
      `<span>撐了 <b>${S.day}</b> 天</span><span>身家 $${S.money.toLocaleString()}</span><span>成員被逮 <b>${caughtN}</b> 次</span>`;
    $('endingModal').classList.remove('hidden');
    $('btnRestart').onclick = () => {
      $('endingModal').classList.add('hidden');
      Sim.restart();
      renderAll();
      GameMap.flyTo(HQ.lat, HQ.lng, 12);
    };
  }

  /* ===== Toast ===== */
  function showToast(t) {
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = `${t.icon} ${t.text}`;
    $('toasts').appendChild(el);
    setTimeout(() => el.remove(), 4200);
  }

  return { boot };
})();

window.addEventListener('DOMContentLoaded', UI.boot);
