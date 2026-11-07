/* KK 園區 · 地圖版 — 遊戲邏輯
 *
 * 純前端，存檔在 localStorage，沒有後端。
 * 沒有每秒產出：錢只能靠「派遣 → 時間到 → 收錢」拿到，
 * 一天 24 小時的派遣額度用完就沒了，所以不會有放置遊戲那種無限膨脹。
 *
 * 舞台換成可走動的園區地圖（map.js 負責走動/碰撞/鏡頭），
 * 這裡只管錢、派遣、面板；兩邊透過 window.KKMap 溝通。
 * 掛機三件套：離線歡迎回來、自動派遣（Lv.3 解鎖）、地圖撿紅包。
 */
(function () {
  'use strict';

  const SAVE_KEY = 'kkpark_dispatch_v1';
  const ORDER = ['face', 'hair', 'hat', 'faceAccessory', 'top', 'bottom', 'shoes'];
  const STATION_ORDER = ['desk', 'phone', 'vault', 'server'];

  /* ================= 存檔 ================= */

  function todayKey() {
    const d = new Date();
    return d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate();
  }

  /* 開局穿的囚服＝各部位第一階，直接由 START_OWNED 推出來，不要手抄一份。 */
  function startingEquip() {
    const e = {};
    for (let i = 0; i < SLOTS.length; i++) {
      const t0 = ITEMS[SLOTS[i].id][0];
      if (START_OWNED.indexOf(t0.id) >= 0) e[SLOTS[i].id] = t0.id;
    }
    return e;
  }

  function freshState() {
    return {
      money: 100,
      rank: 0,
      gear: 0,
      crew: 0,
      equip: startingEquip(),
      owned: START_OWNED.slice(),
      dispatch: null,        // { jobId, startAt, endAt, hours }
      hoursUsed: 0,          // 今天已經派掉幾小時
      dayKey: todayKey(),
      lastSave: Date.now(),
      totalEarned: 0,
      autoOn: false,         // 自動派遣開關
      autoJob: null,         // 自動派遣要重派的業務（最後一次派過的）
      seenIntro: false,      // 新手教學彈窗只跳一次
    };
  }

  function load() {
    try {
      const raw = localStorage.getItem(SAVE_KEY);
      if (!raw) return freshState();
      return Object.assign(freshState(), JSON.parse(raw));
    } catch (e) {
      return freshState();   // 存檔壞掉就重來，別讓整個遊戲開不起來
    }
  }

  function save() {
    try {
      S.lastSave = Date.now();
      localStorage.setItem(SAVE_KEY, JSON.stringify(S));
    } catch (e) { /* 無痕模式或空間不足，放棄 */ }
  }

  let S = load();

  /* ================= 數值 ================= */

  const jobById = {};
  JOBS.forEach(function (j) { jobById[j.id] = j; });

  function gearBonus() {
    let b = 0;
    for (let i = 0; i < S.gear && i < GEAR.length; i++) b += GEAR[i].bonus;
    return b;
  }

  function crewBonus() { return S.crew * CREW.bonus; }
  function rankBonus() { return S.rank * RANK_BONUS; }

  /* 某個部位穿的是第幾階（0/1/2），沒穿回 -1。 */
  function tierOf(slotId) {
    const id = S.equip[slotId];
    if (!id) return -1;
    const list = ITEMS[slotId];
    for (let i = 0; i < list.length; i++) if (list[i].id === id) return i;
    return -1;
  }

  function slotBonus(job) {
    const t = job.slot ? tierOf(job.slot) : -1;
    return t < 0 ? 0 : TIER_BONUS[t];
  }

  /* 加成全部用加法堆疊，不做連乘，數字才不會失控。 */
  function multFor(job) {
    return 1 + gearBonus() + rankBonus() + slotBonus(job) + crewBonus();
  }

  function rewardFor(job, hours) {
    return job.base * (hours / BASE_HOURS) * multFor(job);
  }

  function hourly(job) { return job.base / BASE_HOURS * multFor(job); }

  function crewCost() { return Math.floor(CREW.baseCost * Math.pow(CREW.growth, S.crew)); }
  function nextPromoCost() { return S.rank >= 6 ? null : PROMO_COST[S.rank]; }
  function isOwned(id) { return S.owned.indexOf(id) >= 0; }

  function rollDay() {
    const k = todayKey();
    if (S.dayKey === k) return;
    S.dayKey = k;
    S.hoursUsed = 0;
    save();
  }

  /* ================= 格式化 ================= */

  const UNITS = ['', 'K', 'M', 'B'];

  function fmt(n) {
    if (!isFinite(n)) return '∞';
    if (n < 0) return '-' + fmt(-n);
    if (n === 0) return '0';
    if (n < 1000) return n < 10 ? (Math.round(n * 10) / 10).toString() : String(Math.floor(n));
    let i = 0;
    while (n >= 1000 && i < UNITS.length - 1) { n /= 1000; i++; }
    return (Math.round(n * 100) / 100) + UNITS[i];
  }

  function trimH(h) { return h % 1 === 0 ? String(h) : String(Math.round(h * 10) / 10); }

  function fmtHours(h) {
    if (h < 1) return Math.round(h * 60) + ' 分鐘';
    return trimH(h) + ' 小時';
  }

  function fmtLeft(ms) {
    if (ms <= 0) return '已完成';
    const s = Math.ceil(ms / 1000);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 0) return h + ' 小時 ' + m + ' 分';
    if (m > 0) return m + ' 分 ' + (s % 60) + ' 秒';
    return s + ' 秒';
  }

  function $id(id) { return document.getElementById(id); }

  /* ================= 紙娃娃（交給 map.js） ================= */

  function equipCsv() {
    const ids = [API.body];
    for (let i = 0; i < ORDER.length; i++) {
      const it = S.equip[ORDER[i]];
      if (it) ids.push(it);
    }
    return ids.join(',');
  }

  /* ================= 派遣 ================= */

  let selectedJob = null;
  let stationFilter = null;   // 從地圖點建築進來時，只看那一站的業務
  let wasReady = false;

  function activeJob() { return S.dispatch ? jobById[S.dispatch.jobId] : null; }
  function isReady() { return !!S.dispatch && Date.now() >= S.dispatch.endAt; }

  function startDispatch(jobId, hours) {
    rollDay();
    const job = jobById[jobId];
    if (!job || job.lv > S.rank || S.dispatch) return;
    if (S.hoursUsed + hours > DAILY_HOURS + 1e-6) {
      toast('今天的派遣額度不夠了', 'bad');
      return;
    }
    S.hoursUsed += hours;
    const now = Date.now();
    S.dispatch = { jobId: jobId, startAt: now, endAt: now + hours * 3600000, hours: hours };
    S.autoJob = jobId;          // 自動派遣記住最後一次派的
    wasReady = false;
    save();
    paint();
    KKMap.goToStation(job.prop, job.anim);
    toast('派去「' + job.name + '」，' + fmtHours(hours) + '後回來', 'good');
  }

  function collectDispatch() {
    const d = S.dispatch;
    if (!d || !isReady()) return;
    const job = jobById[d.jobId];
    const full = rewardFor(job, d.hours);
    const failed = Math.random() < job.risk;
    const gain = failed ? full * FAIL_KEEP : full;

    S.money += gain;
    S.totalEarned += gain;
    S.dispatch = null;
    wasReady = false;
    save();

    if (failed) {
      const ev = EVENTS[Math.floor(Math.random() * EVENTS.length)];
      toast(ev.name + '：' + ev.text + '　只拿回 ' + fmt(gain), 'bad');
    } else {
      toast('「' + job.name + '」收工，進帳 ' + fmt(gain) + ' KK幣', 'good');
    }

    paint();

    $id('stageMsg').textContent = '收完錢，在園區裡自由活動…';
    KKMap.goIdle();
    KKMap.setStationState(job.prop, null);
    KKMap.playOnce(failed ? API.fail : API.done, failed ? 2000 : 1600);
    if (!failed) KKMap.cashBurst(job.prop);
  }

  /* ================= 掛機：自動派遣 ================= */

  /* 開著的話，額度夠就自動把人派出去；時長挑額度裝得下的最大段。 */
  function maybeAuto() {
    if (!S.autoOn || S.rank < AUTO_UNLOCK_RANK || S.dispatch) return;
    const left = DAILY_HOURS - S.hoursUsed;
    if (left < 0.5 - 1e-6) return;

    let job = (S.autoJob && jobById[S.autoJob] && jobById[S.autoJob].lv <= S.rank)
      ? jobById[S.autoJob] : null;
    if (!job) {
      for (let i = 0; i < JOBS.length; i++) {
        if (JOBS[i].lv <= S.rank) { job = JOBS[i]; break; }
      }
    }
    if (!job) return;

    const hours = left >= 8 ? 8 : left >= 2 ? 2 : 0.5;
    startDispatch(job.id, hours);
  }

  /* ================= 掛機：紅包 ================= */

  function onCoinPickup() {
    const v = MAP.coin.base + S.rank * MAP.coin.perRank;
    S.money += v;
    S.totalEarned += v;
    save();
    paint();
    return v;
  }

  /* ================= 動作 ================= */

  function buyGear() {
    if (S.gear >= GEAR.length) return;
    const g = GEAR[S.gear];
    if (S.money < g.cost) return;
    S.money -= g.cost;
    S.gear++;
    save(); paint();
    toast('設備升級 — ' + g.name, 'good');
  }

  function buyCrew() {
    if (S.crew >= CREW.max) return;
    const c = crewCost();
    if (S.money < c) return;
    S.money -= c;
    S.crew++;
    save(); paint();
  }

  function promote() {
    const c = nextPromoCost();
    if (c === null || S.money < c) return;
    S.money -= c;
    S.rank++;
    save(); paint();
    toast('升職成功 — ' + RANKS[S.rank].title, 'good');
    if (S.rank === AUTO_UNLOCK_RANK) toast('自動派遣解鎖了！到派遣頁打開', 'good');
  }

  /* 點單品：沒買過就買下並穿上，已穿就脫掉。 */
  function pickItem(slot, tier) {
    const it = ITEMS[slot][tier];
    if (!it) return;
    if (S.equip[slot] === it.id) {
      delete S.equip[slot];
    } else if (isOwned(it.id)) {
      S.equip[slot] = it.id;
    } else {
      const c = TIER_COST[tier];
      if (S.money < c) { toast('KK幣不夠，還差 ' + fmt(c - S.money), 'bad'); return; }
      S.money -= c;
      S.owned.push(it.id);
      S.equip[slot] = it.id;
      toast('買下 ' + it.name, 'good');
    }
    save(); paint(); KKMap.refreshDoll();
  }

  /* ================= 渲染 ================= */

  let activeTab = 'dispatch';

  function renderHud() {
    const r = RANKS[S.rank];
    $id('rankTitle').textContent = r.title;
    $id('rankSub').textContent = 'Lv.' + r.lv + ' · 日薪 ' + r.salary.toLocaleString();
    $id('money').textContent = fmt(S.money);
    $id('rate').textContent = '今日額度 ' + trimH(S.hoursUsed) + ' / ' + DAILY_HOURS + 'h';
  }

  function jobsForSlot(slotId) {
    const out = [];
    for (let i = 0; i < JOBS.length; i++) if (JOBS[i].slot === slotId) out.push(JOBS[i].name);
    return out.join(' · ');
  }

  function renderDispatch() {
    const panel = $id('panel-dispatch');
    const job = activeJob();

    if (job) {
      const ready = isReady();
      const d = S.dispatch;
      const full = rewardFor(job, d.hours);
      panel.innerHTML =
        '<div class="dcard' + (ready ? ' ready' : '') + '">' +
          '<div class="dcard-head">' +
            '<span class="dcard-name">' + job.name + '</span>' +
            '<span class="badge">' + fmtHours(d.hours) + '</span>' +
          '</div>' +
          '<div class="dcard-sub">' + (ready ? '回來了，等你收錢' : '剩 ' + fmtLeft(d.endAt - Date.now())) + '</div>' +
          '<div class="dcard-pay">+' + fmt(full) + '<small> 預估（風險 ' +
            Math.round(job.risk * 100) + '%，失敗只拿回 ' + Math.round(FAIL_KEEP * 100) + '%）</small></div>' +
          (ready
            ? '<button class="btn wide" data-collect="1">收錢<small>＋' + fmt(full) + '</small></button>' +
              '<button class="link skip" data-skip="1">（原型用）快轉到完成</button>'
            : '<button class="link skip" data-skip="1">（原型用）快轉到完成</button>') +
        '</div>';
      return;
    }

    /* 預設選中：可接、且在目前篩選的站裡 */
    if (selectedJob === null || jobById[selectedJob].lv > S.rank ||
        (stationFilter && jobById[selectedJob].prop !== stationFilter)) {
      selectedJob = null;
      for (let i = 0; i < JOBS.length; i++) {
        if (JOBS[i].lv <= S.rank && (!stationFilter || JOBS[i].prop === stationFilter)) {
          selectedJob = JOBS[i].id;
          break;
        }
      }
    }

    let html = '';
    if (stationFilter) {
      html += '<div class="stn-filter">篩選：「' + MAP.stations[stationFilter].sign +
              '」　<button class="link" data-clear-filter="1">看全部業務</button></div>';
    }

    /* 業務照派遣站分組：地圖上那棟建築就是它的入口 */
    const groups = stationFilter ? [stationFilter] : STATION_ORDER;
    for (let g = 0; g < groups.length; g++) {
      const prop = groups[g];
      const meta = MAP.stations[prop];
      let rows = '';
      for (let i = 0; i < JOBS.length; i++) {
        const j = JOBS[i];
        if (j.prop !== prop) continue;
        if (j.lv > S.rank) {
          rows +=
            '<div class="job off">' +
              '<div class="row-main">' +
                '<div class="row-name">' + j.name +
                  '<span class="badge">升到「' + RANKS[j.lv].title + '」解鎖</span>' +
                '</div>' +
              '</div>' +
            '</div>';
          continue;
        }
        const sb = slotBonus(j);
        const slotName = j.slot ? slotNameOf(j.slot) : '';
        rows +=
          '<div class="job' + (j.id === selectedJob ? ' sel' : '') + '" data-pick="' + j.id + '">' +
            '<div class="row-main">' +
              '<div class="row-name">' + j.name +
                (sb > 0 ? '<span class="badge ok">部位 +' + Math.round(sb * 100) + '%</span>' : '') +
              '</div>' +
              '<div class="row-sub">每小時 ' + fmt(hourly(j)) +
                '　·　風險 ' + Math.round(j.risk * 100) + '%' +
                (j.slot ? '　·　吃' + slotName : '') +
              '</div>' +
            '</div>' +
          '</div>';
      }
      if (!rows) continue;
      html += '<div class="stn-head" style="color:' + meta.neon + '">' +
              meta.emoji + ' ' + meta.sign + '</div>' + rows;
    }

    const sel = jobById[selectedJob];
    if (!sel) {
      panel.innerHTML = html + '<p class="hint">這裡的業務你還接不了，先去升職。</p>';
      return;
    }

    const left = DAILY_HOURS - S.hoursUsed;
    let btns = '';
    for (let i = 0; i < DURATIONS.length; i++) {
      const h = DURATIONS[i];
      const ok = h <= left + 1e-6;
      btns +=
        '<button class="btn' + (ok ? '' : ' off') + '" data-go="' + h + '"' +
          (ok ? '' : ' disabled') + '>' +
          fmtHours(h) + '<small>+' + fmt(rewardFor(sel, h)) + '</small>' +
        '</button>';
    }

    /* 自動派遣開關 */
    const unlocked = S.rank >= AUTO_UNLOCK_RANK;
    const autoName = S.autoJob && jobById[S.autoJob] ? jobById[S.autoJob].name : null;
    html +=
      '<div class="auto-row">' +
        '<div class="auto-info"><b>自動派遣</b>' +
          '<small>' + (unlocked
            ? (S.autoOn
                ? '運作中：額度內自動重派「' + (autoName || '上次業務') + '」'
                : '打開就會自己接單，額度用完自動停')
            : '升到「' + RANKS[AUTO_UNLOCK_RANK].title + '」解鎖：底下有人跑腿，不用手動派') +
          '</small>' +
        '</div>' +
        '<button class="btn auto-btn' + (unlocked && S.autoOn ? ' on' : '') + '"' +
          (unlocked ? ' data-auto="1"' : ' disabled') + '>' +
          (unlocked ? (S.autoOn ? '開' : '關') : '未解鎖') +
        '</button>' +
      '</div>';

    panel.innerHTML = html +
      '<div class="gobar">' +
        '<div class="gobar-info">派誰去「<b>' + sel.name + '</b>」　·　今日剩 ' + trimH(left) + ' 小時</div>' +
        '<div class="gobar-btns">' + btns + '</div>' +
      '</div>';
  }

  function slotNameOf(id) {
    for (let i = 0; i < SLOTS.length; i++) if (SLOTS[i].id === id) return SLOTS[i].name;
    return id;
  }

  function renderDollPanel() {
    let html = '';
    for (let i = 0; i < SLOTS.length; i++) {
      const s = SLOTS[i];
      const cur = tierOf(s.id);
      let grid = '';
      for (let t = 0; t < ITEMS[s.id].length; t++) {
        const it = ITEMS[s.id][t];
        const owned = isOwned(it.id);
        const on = cur === t;
        grid +=
          '<button class="item' + (on ? ' on' : '') + (owned ? ' has' : '') + '"' +
            ' data-slot="' + s.id + '" data-tier="' + t + '">' +
            '<span class="item-name">' + it.name + '</span>' +
            '<span class="item-sub">' + (on ? '穿著中' :
              owned ? '點一下穿上' : '+' + Math.round(TIER_BONUS[t] * 100) + '%　' + fmt(TIER_COST[t])) +
            '</span>' +
          '</button>';
      }
      html +=
        '<div class="slot">' +
          '<div class="slot-head">' + s.name +
            '<span class="slot-job">加成 ' + jobsForSlot(s.id) + '</span>' +
          '</div>' +
          '<div class="item-grid">' + grid + '</div>' +
        '</div>';
    }
    $id('panel-doll').innerHTML = html +
      '<p class="hint">每個部位只加乘它對應的那個業務。穿對部位再派出去，報酬才會高。</p>';
  }

  function renderGear() {
    let html = '';
    for (let i = 0; i < GEAR.length; i++) {
      const g = GEAR[i];
      const owned = i < S.gear;
      const isNext = i === S.gear;
      html +=
        '<div class="row' + (owned ? ' owned' : '') + '">' +
          '<div class="row-main">' +
            '<div class="row-name">' + g.name + (owned ? '<span class="badge ok">已購</span>' : '') + '</div>' +
            '<div class="row-sub">全部業務 +' + Math.round(g.bonus * 100) + '%</div>' +
          '</div>' +
          (owned ? '' :
            '<button class="btn" data-buy-gear="1"' + (isNext ? '' : ' disabled') + '>' +
              (isNext ? '購買<small>' + fmt(g.cost) + '</small>' : '未解鎖') +
            '</button>') +
        '</div>';
    }
    $id('panel-gear').innerHTML = html +
      '<p class="hint">目前設備加成 +' + Math.round(gearBonus() * 100) + '%。</p>';
  }

  function renderCrew() {
    const maxed = S.crew >= CREW.max;
    $id('panel-crew').innerHTML =
      '<div class="row">' +
        '<div class="row-main">' +
          '<div class="row-name">手下<span class="badge">' + S.crew + ' / ' + CREW.max + ' 人</span></div>' +
          '<div class="row-sub">目前加成 +' + Math.round(crewBonus() * 100) + '%</div>' +
        '</div>' +
        (maxed ? '' :
          '<button class="btn" data-buy-crew="1">招募<small>' + fmt(crewCost()) + '</small></button>') +
      '</div>' +
      '<p class="hint">每多一名手下，全部業務 +' + Math.round(CREW.bonus * 100) +
        '%。成本每次遞增 35%，最多 ' + CREW.max + ' 人。</p>';
  }

  function renderPromo() {
    const cost = nextPromoCost();
    const r = RANKS[S.rank];
    if (cost === null) {
      $id('panel-promo').innerHTML =
        '<div class="promo-top">' +
          '<div class="promo-title">' + r.title + '</div>' +
          '<p class="hint">爬到頂了。這座園區現在歸你管。</p>' +
        '</div>';
      return;
    }
    const next = RANKS[S.rank + 1];
    const can = S.money >= cost;
    $id('panel-promo').innerHTML =
      '<div class="promo-top">' +
        '<div class="promo-now">' + r.title + '<span class="arrow">→</span><b>' + next.title + '</b></div>' +
        '<div class="promo-meta">日薪 ' + r.salary.toLocaleString() + ' → ' + next.salary.toLocaleString() +
          '　·　全部業務 +' + Math.round(RANK_BONUS * 100) + '%</div>' +
      '</div>' +
      '<button class="btn wide' + (can ? '' : ' off') + '" data-promote="1">' +
        (can ? '升職' : '還差 ' + fmt(cost - S.money)) + '<small>' + fmt(cost) + '</small>' +
      '</button>' +
      '<p class="hint">升職會解鎖新的業務，全部業務再加 ' + Math.round(RANK_BONUS * 100) + '%。</p>';
  }

  function renderPanel() {
    if (activeTab === 'dispatch') renderDispatch();
    else if (activeTab === 'doll') renderDollPanel();
    else if (activeTab === 'gear') renderGear();
    else if (activeTab === 'crew') renderCrew();
    else renderPromo();
  }

  function paint() { renderHud(); renderPanel(); refreshAffordability(); }

  /* 錢夠不夠只改 class，不重建 DOM，按鈕才不會在點擊瞬間被換掉。 */
  function refreshAffordability() {
    const m = S.money;
    const gb = document.querySelector('[data-buy-gear]');
    if (gb && S.gear < GEAR.length) gb.classList.toggle('off', m < GEAR[S.gear].cost);
    const cb = document.querySelector('[data-buy-crew]');
    if (cb) cb.classList.toggle('off', m < crewCost());
    const pb = document.querySelector('[data-promote]');
    if (pb) {
      const c = nextPromoCost();
      pb.classList.toggle('off', c === null || m < c);
    }
    const items = document.querySelectorAll('[data-slot]');
    for (let i = 0; i < items.length; i++) {
      const slot = items[i].getAttribute('data-slot');
      const tier = parseInt(items[i].getAttribute('data-tier'), 10);
      const it = ITEMS[slot][tier];
      const owned = isOwned(it.id);
      items[i].classList.toggle('off', !owned && m < TIER_COST[tier]);
    }
  }

  /* ================= 提示 ================= */

  function toast(msg, kind) {
    const el = document.createElement('div');
    el.className = 'toast ' + (kind || '');
    el.textContent = msg;
    $id('toastWrap').appendChild(el);
    setTimeout(function () { el.classList.add('out'); }, 2600);
    setTimeout(function () { el.remove(); }, 3200);
  }

  function showModal(title, body) {
    $id('modalTitle').textContent = title;
    $id('modalBody').textContent = body;   /* CSS 用 pre-line，\n 會真的換行 */
    $id('modal').classList.remove('hidden');
  }

  /* ================= 每幀更新 ================= */

  const WORK_MSGS = [
    '鍵盤敲個不停…', '電話接不完…', '盯著螢幕不眨眼…',
    '今天也要努力…', '樓下在催進度…', '這單不能漏…',
  ];

  function progressPct() {
    const d = S.dispatch;
    return Math.max(0, Math.min(100, (Date.now() - d.startAt) / (d.endAt - d.startAt) * 100));
  }

  function renderProgress() {
    const d = S.dispatch;
    const bar = $id('dbar');
    if (!d) { bar.classList.add('hidden'); return; }
    bar.classList.remove('hidden');
    const pct = progressPct();
    $id('dbarFill').style.width = pct.toFixed(1) + '%';
    $id('dbarText').textContent = isReady()
      ? '完成了'
      : activeJob().name + '　' + fmtLeft(d.endAt - Date.now()) + '　' + Math.floor(pct) + '%';
  }

  /* 把派遣進度同步到地圖上的站點泡泡 */
  function syncBubble() {
    const d = S.dispatch;
    if (!d) return;
    const job = activeJob();
    KKMap.setStationState(job.prop,
      isReady() ? { ready: true } : { label: job.name, pct: progressPct() });
  }

  function tick() {
    rollDay();
    renderProgress();
    syncBubble();
    maybeAuto();

    const d = S.dispatch;
    if (d) {
      if (isReady() && !wasReady) { wasReady = true; renderDispatch(); }
      if (!isReady()) {
        const el = document.querySelector('.dcard-sub');
        if (el) el.textContent = '剩 ' + fmtLeft(d.endAt - Date.now());
      }
    }
  }

  /* ================= 初始化 ================= */

  function switchTab(name) {
    activeTab = name;
    const tabs = document.querySelectorAll('.tab');
    for (let i = 0; i < tabs.length; i++) {
      tabs[i].classList.toggle('active', tabs[i].getAttribute('data-tab') === name);
    }
    const panels = document.querySelectorAll('.panel');
    for (let i = 0; i < panels.length; i++) {
      panels[i].classList.toggle('active', panels[i].id === 'panel-' + name);
    }
    renderPanel();
    refreshAffordability();
  }

  /* 從地圖走進站點：有派遣就收錢／看進度，沒有就打開派遣頁篩那一站 */
  function onInteract(prop) {
    const d = S.dispatch;
    if (d) {
      const job = activeJob();
      if (job.prop === prop) {
        if (isReady()) collectDispatch();
        else toast('「' + job.name + '」還在忙，剩 ' + fmtLeft(d.endAt - Date.now()));
      } else {
        toast('人還在「' + job.name + '」那邊');
      }
      return;
    }
    stationFilter = prop;
    switchTab('dispatch');
    $id('tabs').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function init() {
    rollDay();

    KKMap.init({
      getDollCsv: equipCsv,
      onInteract: onInteract,
      onCoin: onCoinPickup,
      onDollReady: function () {
        if (!S.dispatch) $id('stageMsg').textContent = '在園區裡待命…';
      },
    });

    paint();
    renderProgress();

    if (S.dispatch) {
      const job = activeJob();
      KKMap.placeAtStation(job.prop, job.anim);
      if (Date.now() >= S.dispatch.endAt) {
        showModal('歡迎回來',
          '你不在的時候，「' + job.name + '」已經收工了。\n預估可領 ' +
          fmt(rewardFor(job, S.dispatch.hours)) + ' KK幣（成不成就看運氣）。\n' +
          '到「' + MAP.stations[job.prop].sign + '」門口按互動收錢，或在下面按收錢。');
      }
    } else if (!S.seenIntro) {
      S.seenIntro = true;
      save();
      showModal('歡迎來到 KK 園區',
        '用方向鍵／WASD 或右下搖桿在園區走動。\n走到建築物門口按「互動」（或按 Z）挑業務派遣。\n一天 24 小時額度派完就收工，明天再來。');
    }

    $id('tabs').addEventListener('click', function (e) {
      const b = e.target.closest('.tab');
      if (!b) return;
      switchTab(b.getAttribute('data-tab'));
    });

    document.addEventListener('click', function (e) {
      if (e.target.closest('[data-clear-filter]')) {
        stationFilter = null;
        renderDispatch();
        return;
      }

      const ab = e.target.closest('[data-auto]');
      if (ab && !ab.disabled) {
        S.autoOn = !S.autoOn;
        save(); paint();
        toast(S.autoOn ? '自動派遣開始運作' : '自動派遣關掉了', 'good');
        if (S.autoOn) maybeAuto();
        return;
      }

      const pick = e.target.closest('[data-pick]');
      if (pick) { selectedJob = pick.getAttribute('data-pick'); renderDispatch(); return; }

      const go = e.target.closest('[data-go]');
      if (go && !go.disabled) { startDispatch(selectedJob, parseFloat(go.getAttribute('data-go'))); return; }

      if (e.target.closest('[data-collect]')) { collectDispatch(); return; }

      if (e.target.closest('[data-skip]')) {
        if (S.dispatch) { S.dispatch.endAt = Date.now() - 1; wasReady = false; tick(); }
        return;
      }

      const item = e.target.closest('[data-slot]');
      if (item) {
        pickItem(item.getAttribute('data-slot'), parseInt(item.getAttribute('data-tier'), 10));
        return;
      }

      const t = e.target.closest('[data-buy-gear],[data-buy-crew],[data-promote]');
      if (!t) return;
      if (t.hasAttribute('data-buy-gear')) buyGear();
      else if (t.hasAttribute('data-buy-crew')) buyCrew();
      else promote();
      refreshAffordability();
    });

    $id('btnReset').addEventListener('click', function () {
      if (!confirm('確定要清掉存檔、從頭開始嗎？')) return;
      S = freshState();
      stationFilter = null;
      selectedJob = null;
      save();
      KKMap.reset();
      KKMap.refreshDoll();
      paint();
      toast('已重新開始', 'good');
    });

    $id('modalOk').addEventListener('click', function () {
      $id('modal').classList.add('hidden');
    });

    setInterval(function () {
      if (S.dispatch && !isReady()) {
        $id('stageMsg').textContent = WORK_MSGS[Math.floor(Math.random() * WORK_MSGS.length)];
      }
    }, 6000);

    setInterval(tick, 250);
    setInterval(save, 5000);
    window.addEventListener('beforeunload', save);
    document.addEventListener('visibilitychange', function () { if (document.hidden) save(); });
  }

  init();
})();
