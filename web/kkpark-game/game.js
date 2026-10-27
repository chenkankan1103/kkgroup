/* KK 園區 · 派遣版 — 遊戲邏輯
 *
 * 純前端，存檔在 localStorage，沒有後端。
 * 沒有每秒產出：錢只能靠「派遣 → 時間到 → 收錢」拿到，
 * 一天 24 小時的派遣額度用完就沒了，所以不會有放置遊戲那種無限膨脹。
 */
(function () {
  'use strict';

  const SAVE_KEY = 'kkpark_dispatch_v1';
  const ORDER = ['face', 'hair', 'hat', 'faceAccessory', 'top', 'bottom', 'shoes'];
  const IDLE_LEFT = 50;

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

  /* ================= 紙娃娃 ================= */

  function equipCsv() {
    const ids = [API.body];
    for (let i = 0; i < ORDER.length; i++) {
      const it = S.equip[ORDER[i]];
      if (it) ids.push(it);
    }
    return ids.join(',');
  }

  function dollUrl(anim) {
    return API.base + '/animated/' + API.skin + '/' + equipCsv() + '/' + anim +
           '/0?showears=false&resize=' + API.resize + '&flipX=true';
  }

  let dollAnim = API.idle;
  let dollLeft = IDLE_LEFT;
  let dollTimer = null;
  let dollSeq = 0;
  let firstLoad = true;

  /* maplestory.io 是即時生成圖的：每組「造型 × 動作」第一次要 3~8 秒，之後才走 24h 快取。
   * 直接換 img.src 會讓角色先消失好幾秒，所以先用 Image() 探好、載完才真的換上去。 */
  const loaded = {};

  function dollDone() {
    if (!firstLoad) return;
    firstLoad = false;
    $id('stageMsg').textContent = '在園區裡待命…';
  }

  function applyDoll(url) {
    const el = $id('doll');
    if (el.getAttribute('src') === url) return;
    if (loaded[url]) { el.src = url; dollDone(); return; }

    const seq = ++dollSeq;
    const im = new Image();
    im.onload = function () {
      loaded[url] = true;
      if (seq !== dollSeq) return;      // 中途又換動作了，這次的結果作廢
      el.src = url;
      dollDone();
    };
    im.onerror = function () {
      // 造型組合被伺服器拒絕時退回純身體，至少不要整張破圖
      if (seq !== dollSeq) return;
      const fb = API.base + '/animated/' + API.skin + '/' + API.body + '/' + dollAnim +
                 '/0?resize=' + API.resize;
      loaded[fb] = true;
      el.src = fb;
      dollDone();
    };
    im.src = url;
  }

  function setDollAnim(a) {
    if (dollAnim === a) return;
    dollAnim = a;
    applyDoll(dollUrl(a));
  }

  function setDollLeft(p) {
    dollLeft = Math.max(5, Math.min(95, p));
    $id('doll').style.left = dollLeft + '%';
    $id('dollGlow').style.left = dollLeft + '%';
  }

  function propLeft(name) {
    const el = document.querySelector('.prop[data-prop="' + name + '"]');
    return el ? parseFloat(el.style.left) : IDLE_LEFT;
  }

  /* 走到某個物件前面，站定後換成工作動作。 */
  function walkTo(prop, anim) {
    clearTimeout(dollTimer);
    const target = propLeft(prop) - 6;
    if (Math.abs(target - dollLeft) < 1) { setDollAnim(anim); return; }
    setDollAnim(API.walk);
    setDollLeft(target);
    dollTimer = setTimeout(function () { setDollAnim(anim); }, 1200);
  }

  function walkHome() {
    clearTimeout(dollTimer);
    if (Math.abs(IDLE_LEFT - dollLeft) < 1) { setDollAnim(API.idle); return; }
    setDollAnim(API.walk);
    setDollLeft(IDLE_LEFT);
    dollTimer = setTimeout(function () { setDollAnim(API.idle); }, 1200);
  }

  function renderDoll() { applyDoll(dollUrl(dollAnim)); }

  /* 先抓常用動作，派遣當下就不用等。載完的 URL 記進 loaded，之後換裝是秒切。 */
  function preload() {
    for (let i = 0; i < PRELOAD_ANIMS.length; i++) {
      const u = dollUrl(PRELOAD_ANIMS[i]);
      const im = new Image();
      im.onload = function () { loaded[u] = true; };
      im.src = u;
    }
  }

  /* ================= 派遣 ================= */

  let selectedJob = null;
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
    wasReady = false;
    save();
    paint();
    walkTo(job.prop, job.anim);
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

    clearTimeout(dollTimer);
    setDollAnim(failed ? API.fail : API.done);
    if (failed) {
      dollTimer = setTimeout(function () { setDollAnim(API.idle); }, 2000);
    } else {
      dollTimer = setTimeout(walkHome, 1200);
    }
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
    save(); paint(); renderDoll();
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

    if (selectedJob === null || jobById[selectedJob].lv > S.rank) {
      selectedJob = null;
      for (let i = 0; i < JOBS.length; i++) {
        if (JOBS[i].lv <= S.rank) { selectedJob = JOBS[i].id; break; }
      }
    }

    let html = '';
    for (let i = 0; i < JOBS.length; i++) {
      const j = JOBS[i];
      if (j.lv > S.rank) continue;
      const sb = slotBonus(j);
      const slotName = j.slot ? slotNameOf(j.slot) : '';
      html +=
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

    const sel = jobById[selectedJob];
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

    $id('panel-dispatch').innerHTML =
      html +
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

  /* ================= 每幀更新 ================= */

  const WORK_MSGS = [
    '鍵盤敲個不停…', '電話接不完…', '盯著螢幕不眨眼…',
    '今天也要努力…', '樓下在催進度…', '這單不能漏…',
  ];

  function renderProgress() {
    const d = S.dispatch;
    const bar = $id('dbar');
    if (!d) { bar.classList.add('hidden'); return; }
    bar.classList.remove('hidden');
    const total = d.endAt - d.startAt;
    const pct = Math.max(0, Math.min(100, (Date.now() - d.startAt) / total * 100));
    $id('dbarFill').style.width = pct.toFixed(1) + '%';
    $id('dbarText').textContent = isReady()
      ? '完成了'
      : activeJob().name + '　' + fmtLeft(d.endAt - Date.now()) + '　' + Math.floor(pct) + '%';
  }

  function tick() {
    rollDay();
    renderProgress();

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

  function init() {
    rollDay();
    $id('stageMsg').textContent = '正在載入紙娃娃…';
    renderDoll();
    setDollLeft(IDLE_LEFT);
    paint();
    preload();
    renderProgress();

    $id('tabs').addEventListener('click', function (e) {
      const b = e.target.closest('.tab');
      if (!b) return;
      activeTab = b.getAttribute('data-tab');
      const tabs = document.querySelectorAll('.tab');
      for (let i = 0; i < tabs.length; i++) tabs[i].classList.toggle('active', tabs[i] === b);
      const panels = document.querySelectorAll('.panel');
      for (let i = 0; i < panels.length; i++) {
        panels[i].classList.toggle('active', panels[i].id === 'panel-' + activeTab);
      }
      renderPanel();
      refreshAffordability();
    });

    document.addEventListener('click', function (e) {
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
      save();
      renderDoll();
      setDollLeft(IDLE_LEFT);
      setDollAnim(API.idle);
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
