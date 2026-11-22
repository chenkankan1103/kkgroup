'use strict';
/* dock.js — 寫手 2 表現層模組：v0.5.0 下方升級面板（Dock）＋v0.6 熱線單 UI（Hotline）
   Dock 三分頁全吃寫手 A 的真 Sim API：
   ⬆️ 升級 Sim.getUpgradeTree().upgrade／🔧 裝備 .gear＋現有裝備耐久條／🧾 營運 .ops＋帳單預覽＋真 heat
   購買走 Sim.buyUpgrade(id)（缺錢/滿級 sim 自己 toast，UI 只做 disabled 視覺）
   收合後留 32px 提示條；錢一變動 → 摘要數字跳動（放置遊戲的即時回饋爽點）
   Hotline 照 hotline-spec.md §6 實作；Sim API（hotlineOffer/acceptHotline/…）未落地前
   走 HL_MOCK（資料閘 HAPI 偵測存在即自動切真，mock 段屆時整塊可刪） */

const Dock = (() => {
  const $ = (id) => document.getElementById(id);

  let open = false;
  let tab = 'up';
  let lastMoney = null;

  /* ===== 開合與分頁 ===== */
  function init() {
    document.querySelectorAll('#dockStrip .dock-tab').forEach((b) => {
      b.onclick = () => { setTab(b.dataset.tab); if (!open) setOpen(true); };
    });
    $('dockToggle').onclick = () => setOpen(!open);
    setOpen(false);
  }

  function setTab(t) {
    tab = t;
    document.querySelectorAll('#dockStrip .dock-tab').forEach((b) =>
      b.classList.toggle('on', open && b.dataset.tab === tab));
    render();
  }

  function setOpen(v) {
    open = v;
    $('dockBody').classList.toggle('hidden', !open);
    $('dockToggle').textContent = open ? '▼' : '▲';
    $('dockToggle').title = open ? '收合' : '展開';
    document.querySelectorAll('#dockStrip .dock-tab').forEach((b) =>
      b.classList.toggle('on', open && b.dataset.tab === tab));
    liftToasts();
    if (open) render();
  }

  // toast 讓位：量 dock 頂緣把 #toasts 抬上去——「點了→數字跳動→toast」的爽點不被蓋住
  function liftToasts() {
    const r = $('dock').getBoundingClientRect();
    document.body.style.setProperty(
      '--dockLift', open && r.height ? (window.innerHeight - r.top + 6) + 'px' : '0px');
  }

  /* ===== 升級節點列（三頁共用：upgrade/gear/ops 同形） ===== */
  // 節點：{ id, icon, name, desc, max, level, cost, effName, cur, next }（next=null＝滿級）
  function upRow(n) {
    const S = Sim.state();
    const maxed = n.next === null;
    const eff = maxed ? `${n.effName} ${n.cur}` : `${n.effName} ${n.cur} → ${n.next}`;
    const afford = S.money >= n.cost;
    return `<div class="shop-item">
      <span class="gi" title="${n.desc}">${n.icon}</span>
      <div class="gi-body" title="${n.desc}"><b>${n.name}<span class="lv-tag">Lv.${n.level}</span></b>
        <small>${eff}</small></div>
      ${maxed
        ? '<span class="owned-tag">MAX</span>'
        : `<button class="mini dock-up" data-upid="${n.id}" data-cost="${n.cost}"${afford ? '' : ' disabled'}>⬆️ $${n.cost.toLocaleString()}</button>`}
    </div>`;
  }

  function bindUps() {
    $('dockBody').querySelectorAll('[data-upid]').forEach((b) => {
      b.onclick = () => {
        const id = b.dataset.upid;
        if (!Sim.buyUpgrade(id)) return;  // 缺錢/滿級：sim 已 toast，按鈕不動
        render();  // 'upgrades' 事件其實已重畫——這裡 pulse 的是新節點
        pulse(document.querySelector(`#dockBody [data-upid="${id}"]`)?.closest('.shop-item'));
      };
    });
  }

  /* ===== 渲染 ===== */
  function render() {
    if (tab === 'up') renderUp();
    else if (tab === 'gear') renderGear();
    else renderOps();
  }

  function renderUp() {
    const S = Sim.state(); if (!S) return;
    $('dockBody').innerHTML = Sim.getUpgradeTree().upgrade.map(upRow).join('');
    bindUps();
  }

  function renderGear() {
    const S = Sim.state(); if (!S) return;
    $('dockBody').innerHTML = `
      ${Sim.getUpgradeTree().gear.map(upRow).join('')}
      <div class="shop-sec">🛒 添購裝備</div>
      ${GEAR.map((g) => {
        const owned = !!S.gear[g.id];
        const uses = (S.gearUses || {})[g.id];
        let right;
        if (!owned) {
          right = `<button class="mini" data-gear="${g.id}" data-cost="${g.price}"${S.money >= g.price ? '' : ' disabled'}>$${g.price.toLocaleString()}</button>`;
        } else if (g.durable) {
          // v0.5.1 耐久語意（寫手 A 裁決）：起始耐久買入時寫死，分母概念不存在——只顯示剩餘次數文字
          right = `<span class="dur-uses${uses <= 1 ? ' danger' : ''}">剩 ${uses} 次</span>`;
        } else {
          right = '<span class="owned-tag">✅</span>';
        }
        return `<div class="shop-item">
          <span class="gi">${g.icon}</span>
          <div class="gi-body"><b>${g.name}</b><small>${g.desc}</small></div>${right}
        </div>`;
      }).join('')}`;
    bindUps();
    $('dockBody').querySelectorAll('[data-gear]').forEach((b) => {
      b.onclick = () => { Sim.buyGear(b.dataset.gear); renderGear(); };
    });
  }

  function renderOps() {
    const S = Sim.state(); if (!S) return;
    const bill = Sim.upkeepCost();
    const trib = (!S.act2 && S.day >= TRIBUTE.FROM_DAY) ? Sim.tributeCost() : 0;
    const total = bill + trib;
    const ok = S.money >= total;
    const heat = Sim.heatLevel();
    $('dockBody').innerHTML = `
      ${Sim.getUpgradeTree().ops.map(upRow).join('')}
      <div class="shop-sec">🧾 今晚 21:00 帳單</div>
      <div class="shop-item"><span class="gi">🧾</span>
        <div class="gi-body"><b>園區開銷 $${bill.toLocaleString()}</b>
        <small>成員 ${S.members.length} 人 × $${UPKEEP.PER_MEMBER.toLocaleString()}＋建築 ${Object.keys(S.buildings).length} 棟 × $${UPKEEP.PER_BUILDING.toLocaleString()}</small></div>
      </div>
      ${trib ? `<div class="shop-item"><span class="gi">🏹</span>
        <div class="gi-body"><b>貢金 $${trib.toLocaleString()}</b><small>上頭抽成（第 ${TRIBUTE.FROM_DAY} 天起每晚 21:00）</small></div>
      </div>` : ''}
      <div class="ops-verdict ${ok ? 'ok' : 'bad'}" id="dockVerdict"></div>
      <div class="shop-sec">🧯 曝光度（heat）</div>
      <div class="heat-track"><div class="heat-fill" id="dockHeatFill" style="width:${heat}%"></div></div>
      <div class="shop-item"><span class="gi">🧯</span>
        <div class="gi-body"><b>疏通關係（壓熱）</b><small id="dockHeatTxt"></small></div>
        ${heat < 15 ? '<span class="owned-tag">用不上</span>' : `<button class="mini" id="btnCoolHeat">💸 $${HEAT.DECOY_PRICE.toLocaleString()}</button>`}
      </div>`;
    refreshOpsNums();
    bindUps();
    const cool = $('btnCoolHeat');
    if (cool) cool.onclick = () => { Sim.useDecoy(); renderOps(); };
  }

  // 營運頁每秒只更新會動的數字（帳單結論／heat 條），不重建按鈕——點擊不被吃掉
  function refreshOpsNums() {
    const S = Sim.state(); if (!S) return;
    const bill = Sim.upkeepCost();
    const trib = (!S.act2 && S.day >= TRIBUTE.FROM_DAY) ? Sim.tributeCost() : 0;
    const total = bill + trib;
    const ok = S.money >= total;
    const v = $('dockVerdict');
    if (v) v.innerHTML = `帳上 $${S.money.toLocaleString()}${ok ? '——繳得出' : `——差 $${(total - S.money).toLocaleString()}，快接單`}`;
    v.classList.toggle('ok', ok);
    v.classList.toggle('bad', !ok);
    const heat = Sim.heatLevel();
    const fill = $('dockHeatFill');
    if (fill) fill.style.width = heat + '%';
    const txt = $('dockHeatTxt');
    if (txt) txt.textContent = `現有曝光 ${heat}——${heat >= 70 ? '極高' : heat >= 31 ? '偏高' : '安全'}`;
  }

  /* ===== 摘要提示條（收合後的 32px 也要有內容看） ===== */
  function renderSummary() {
    const S = Sim.state(); if (!S) return;
    const tree = Sim.getUpgradeTree();
    let cheapest = Infinity;
    for (const t in tree) for (const n of tree[t]) if (n.next !== null && n.cost < cheapest) cheapest = n.cost;
    $('dockSummary').innerHTML =
      `💰 <b id="dockMoney">$${S.money.toLocaleString()}</b>` +
      (cheapest < Infinity ? ` · ⬆️ 最低 $${cheapest.toLocaleString()}` : '') +
      ` · 🧾 $${Sim.upkeepCost().toLocaleString()}`;
  }

  /* ===== 每秒：摘要更新＋錢變動跳動＋買得起狀態（onTick 尾端呼叫） ===== */
  function tick() {
    const S = Sim.state();
    if (!S || $('dock').classList.contains('hidden')) return;
    renderSummary();
    if (lastMoney !== null && S.money !== lastMoney) pulse($('dockMoney'));
    lastMoney = S.money;
    if (open) {
      // 缺錢按鈕的視覺跟著錢包即時變（sim 已擋，這裡只做樣子）
      $('dockBody').querySelectorAll('[data-cost]').forEach((b) => {
        b.disabled = S.money < Number(b.dataset.cost);
      });
      if (tab === 'ops') refreshOpsNums();
    }
  }

  // 數字跳動：重觸發 CSS 動畫（reflow trick）
  function pulse(el) {
    if (!el) return;
    el.classList.remove('num-jump');
    void el.offsetWidth;
    el.classList.add('num-jump');
  }

  return { init, tick, refresh: render };
})();

/* ======================================================================
   Hotline — v0.6 熱線單 UI（hotline-spec §6 的 11 元素，寫手 2）
   契約（spec §6，寫手 A 的 Sim API）：
   Sim.hotlineOffer() → offer|null {archId,title,desc,pay,durSec,note}
   Sim.acceptHotline(stakePct) → bool（0|25|50）
   Sim.hotlineRemaining() → 秒數；Sim.hotlineRoute() → {nodes,pickup,drop}|null
   Sim.abandonHotline() → bool
   事件：hotlineSignal / hotlineAccepted / hotlineWaypoint / hotlineResult{ok,pay,stake,mercy} / hotlineChase{mode}
   金額顯示一律百位取整（spec §2）；數字字體 Cubic 11（art-bible §3）
   ====================================================================== */
const Hotline = (() => {
  const $ = (id) => document.getElementById(id);
  // 百位取整（spec §2 使用者裁定）：玩家在壓力下讀數字，尾數雜訊是干擾
  const r100 = (x) => Math.round(x / 100) * 100;
  const fmt = (x) => '$' + r100(x).toLocaleString();
  const fmtSec = (s) => {
    const t = Math.max(0, Math.ceil(s));
    return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
  };

  /* ===== HL_MOCK：寫手 A 落地前的假資料源（demo 品質——版面驗收用） ===== */
  const HL_MOCK = (() => {
    // spec §1 卡池樣本（v0.6 本體 1–6；7 escort 後置 v0.6.1、8 cleanup 隨二幕）
    const POOL = [
      { archId: 'flash', title: '閃電快遞', desc: '小東西，現在就要，你離得最近。', pay: 28800, durSec: 150, note: '免押教學卡' },
      { archId: 'pickup', title: '跨區代收', desc: '錢在別人手上，你去把它變成你的。', pay: 34500, durSec: 180, note: '途中有監視點' },
      { archId: 'rush', title: '加急件', desc: '十分鐘後就沒價值了，跑。', pay: 40300, durSec: 120, note: '最緊限時' },
      { archId: 'twostep', title: '雙程貨', desc: '先拿 A，到了再說 B 在哪。', pay: 36800, durSec: 240, note: '中繼點不預告' },
      { archId: 'nightcar', title: '夜車', desc: '這個點才有的生意，車少，眼也少。', pay: 46000, durSec: 240, note: '夜間限定肥單' },
      { archId: 'bighead', title: '頭款', desc: '對方只信現金，你敢押多少，他敢給多少。', pay: 51800, durSec: 210, note: '保證一次攔截' },
    ];
    let offer = null, active = null, poolIdx = 0, timer = null, h = null;

    function schedule(ms) { clearTimeout(timer); timer = setTimeout(signal, ms); }
    // 同時最多 1 張在架上（spec §1）；架上 20 秒沒人接 → 收單，8-15 秒後再響
    function signal() {
      if (active) { schedule(12000); return; }
      if (offer) { offer = null; if (h) h.signal(); schedule(9000); return; }
      offer = POOL[poolIdx++ % POOL.length];
      if (h) h.signal();
      schedule(20000);
    }
    // mock 路線：主角當下位置 → 抽兩個 POI 當取件/交付（demo：直線三點）
    function mockRoute() {
      const S = Sim.state();
      const hero = S && S.hero ? S.hero.pos : HQ;
      const a = POI_DEFS[(Math.random() * POI_DEFS.length) | 0];
      let b = POI_DEFS[(Math.random() * POI_DEFS.length) | 0];
      if (b.id === a.id) b = POI_DEFS[(POI_DEFS.indexOf(a) + 3) % POI_DEFS.length];
      return {
        archId: offer ? offer.archId : '',
        pickup: { lat: a.lat, lng: a.lng, name: a.name },
        drop: { lat: b.lat, lng: b.lng, name: b.name },
        nodes: [[hero.lat, hero.lng], [a.lat, a.lng], [b.lat, b.lng]],
      };
    }
    function settle(ok, mercy) {
      const a = active; active = null;
      const stake = a ? a.stake : 0;
      const mult = a ? (a.stakePct === 50 ? 1.75 : a.stakePct === 25 ? 1.35 : 1) : 1;
      if (h) h.result({
        ok,
        pay: ok ? r100(a.pay * mult) : 0,
        stake,
        mult: ok ? mult : 0,
        mercy: !ok && mercy ? r100(stake / 2) : 0,
        mock: true,
      });
      schedule(9000 + Math.random() * 6000);
    }
    return {
      wire(handlers) { h = handlers; },
      start() { schedule(6000); },          // 進場 6 秒後第一響
      stop() { clearTimeout(timer); },
      offer: () => offer,
      accept(pct) {
        if (!offer) return false;
        const S = Sim.state();
        const stake = r100(offer.pay * pct / 100);
        if (!S || S.money < stake) return false;
        active = { archId: offer.archId, pay: offer.pay, stake, stakePct: pct, deadline: Date.now() + offer.durSec * 1000, durSec: offer.durSec, route: mockRoute() };
        offer = null;
        if (h) h.accepted();
        return true;
      },
      remaining: () => (active ? (active.deadline - Date.now()) / 1000 : 0),
      route: () => (active ? active.route : null),
      abandon() { if (!active) return false; settle(false, false); return true; },
      tick() {
        if (!active) return;
        // 成功路徑（demo）：主角摸到交付點 80m 內 → 結算成功
        const S = Sim.state();
        if (S && S.hero) {
          const d = active.route.drop;
          if (Math.hypot(S.hero.pos.lat - d.lat, S.hero.pos.lng - d.lng) < 0.0007) { settle(true, false); return; }
        }
        // twostep：跑過半程揭示第二段（動態 waypoint，spec §1 卡 5）
        if (active.archId === 'twostep' && !active.wp) {
          const left = (active.deadline - Date.now()) / 1000;
          if (left < active.durSec * 0.5) {
            active.wp = true;
            const b = POI_DEFS[(Math.random() * POI_DEFS.length) | 0];
            active.route.drop = { lat: b.lat, lng: b.lng, name: b.name };
            active.route.nodes.push([b.lat, b.lng]);
            if (h) h.waypoint();
          }
        }
        // 超時：近失寬容（spec §2）——限時 10% 內退一半押金
        if (Date.now() >= active.deadline) {
          const grace = active.durSec * 0.1 * 1000;
          settle(false, Date.now() - active.deadline <= grace);
        }
      },
    };
  })();

  /* ===== HAPI 資料閘：Sim API 存在走真、否則 mock（cutover 零改碼） ===== */
  const has = (fn) => typeof Sim[fn] === 'function';
  const HAPI = {
    offer: () => (has('hotlineOffer') ? Sim.hotlineOffer() : HL_MOCK.offer()),
    accept: (pct) => (has('acceptHotline') ? Sim.acceptHotline(pct) : HL_MOCK.accept(pct)),
    remaining: () => (has('hotlineRemaining') ? Sim.hotlineRemaining() : HL_MOCK.remaining()),
    route: () => (has('hotlineRoute') ? Sim.hotlineRoute() : HL_MOCK.route()),
    abandon: () => (has('abandonHotline') ? Sim.abandonHotline() : HL_MOCK.abandon()),
    real: () => has('hotlineOffer'),
  };

  /* ===== 接單卡 ===== */
  function openCard() {
    const o = HAPI.offer();
    if (!o) return;
    $('hlTitle').textContent = `📡 ${o.title}`;
    $('hlDesc').textContent = o.desc;
    $('hlRows').innerHTML = `
      <div>💰 賞金 <b class="hl-money">${fmt(o.pay)}</b>（含路線浮動）</div>
      <div>⏱ 限時 <b class="hl-time">${fmtSec(o.durSec)}</b>${o.archId === 'rush' ? '——超時零退還' : ''}</div>
      <div>🛵 路線 <b>約 ${(1 + (o.durSec - 150) / 90).toFixed(1)}km</b>（取件→交付）</div>
      <div>📡 備註 <b>${o.note || '——'}</b></div>`;
    // rush 全程大字（spec §4）——accept 後 offer 清空，接單當下先記在 chip
    $('hudHotline').dataset.rush = o.archId === 'rush' ? '1' : '';
    const S = Sim.state();
    const stakes = [
      { pct: 0, name: '平盤', mult: '×1.0', sub: '不押——純拿賞金' },
      { pct: 25, name: '加碼', mult: '×1.35', sub: `押 ${fmt(o.pay * 0.25)}——失敗全沒收` },
      { pct: 50, name: '梭哈', mult: '×1.75', sub: `押 ${fmt(o.pay * 0.5)}——失敗全沒收，會被追擊` },
    ];
    $('hlStakes').innerHTML = stakes.map((s) => {
      const need = r100(o.pay * s.pct / 100);
      const off = need > S.money;
      return `<button class="stake-btn ${s.pct === 50 ? 'bold' : ''}" data-pct="${s.pct}"${off ? ' disabled' : ''}>
        ${s.name} ${s.mult}<small>${s.pct === 0 ? s.sub : `${s.sub} · 帳上 ${fmt(S.money)}`}</small></button>`;
    }).join('');
    $('hlStakes').querySelectorAll('[data-pct]').forEach((b) => {
      b.onclick = () => {
        if (!HAPI.accept(Number(b.dataset.pct))) {
          UI.toast('💸', '錢不夠這一檔（原型：押注扣款等寫手 A 的 Sim API）');
          return;
        }
        $('hotlineModal').classList.add('hidden');
      };
    });
    $('hotlineModal').classList.remove('hidden');
  }

  /* ===== chip 每秒狀態 ===== */
  function tickChip() {
    const chip = $('hudHotline');
    const S = Sim.state();
    if (!chip || !S || S.ended) return;
    const rem = HAPI.remaining();
    const offer = HAPI.offer();
    let state, html;
    if (rem > 0) {
      state = rem <= 30 ? 'low' : 'active';   // 最後 30 秒轉紅脈動（spec §4）
      html = `⏱ <b class="hl-time">${fmtSec(rem)}</b>`;
      chip.classList.toggle('rush', chip.dataset.rush === '1');
    } else if (offer) {
      state = 'offer';
      html = '📡 熱線來電';
      chip.classList.remove('rush');
    } else {
      state = 'idle';
      html = '';
      chip.classList.remove('rush');
    }
    chip.classList.toggle('hidden', state === 'idle');
    ['offer', 'active', 'low'].forEach((c) => chip.classList.toggle(c, c === state));
    if (chip.dataset.s !== state || chip.innerHTML !== html) { chip.innerHTML = html; chip.dataset.s = state; }
    if (state !== 'active') hideQuit();
  }

  /* ===== 放棄確認（進行中 chip 展開） ===== */
  function toggleQuit() {
    const q = $('hotlineQuit');
    if (!q) return;
    q.classList.toggle('hidden');
  }
  function hideQuit() { const q = $('hotlineQuit'); if (q) q.classList.add('hidden'); }

  /* ===== 事件處理（真事件總線與 mock 驅動共用同一組 handler） ===== */
  const HANDLERS = {
    signal() { tickChip(); },
    accepted() {
      const r = HAPI.route();
      GameMap.renderHotline(r);
      if (r && r.pickup) GameMap.flyTo(r.pickup.lat, r.pickup.lng);
      hideQuit();
    },
    waypoint() { GameMap.renderHotline(HAPI.route()); },   // twostep：route 更新 → 重畫揭示第二段
    result(r) {
      GameMap.clearHotline();
      hideQuit();
      const chip = $('hudHotline');
      if (chip) chip.dataset.rush = '';
      // 結算 toast 含押注明細（spec §6）
      let text;
      if (r.ok) {
        text = `熱線單完成 +$${r100(r.pay).toLocaleString()}` +
          (r.stake ? `（押注 ${r.mult ? '×' + r.mult : ''}）` : '（平盤）');
      } else if (r.mercy) {
        text = `熱線單超時——對方念你有誠意，退一半 $${r100(r.mercy).toLocaleString()}`;
      } else {
        text = `熱線單失敗——押金 ${r.stake ? `$${r100(r.stake).toLocaleString()} 全沒收` : '無（平盤）'}`;
      }
      UI.toast(r.ok ? '💰' : '💨', text + (r.mock ? '（原型：錢未實扣）' : ''));
    },
    chase(a) {
      // 追擊警報（art-bible §5）：intercept＝小檔震動、chase＝中檔；紅暈脈衝一次
      const body = document.body;
      const cls = a && a.mode === 'chase' ? 'shake-md' : 'shake-sm';
      body.classList.remove('shake-sm', 'shake-md');
      void body.offsetWidth;
      body.classList.add(cls);
      const vg = $('heat-vignette');
      if (vg) { vg.classList.remove('chase'); void vg.offsetWidth; vg.classList.add('chase'); }
    },
  };

  function init() {
    // 事件總線（寫手 A 落地後 emit 即生效；鍵值先佔同 spec §6）
    Sim.on('hotlineSignal', HANDLERS.signal);
    Sim.on('hotlineAccepted', HANDLERS.accepted);
    Sim.on('hotlineWaypoint', HANDLERS.waypoint);
    Sim.on('hotlineResult', HANDLERS.result);
    Sim.on('hotlineChase', HANDLERS.chase);
    HL_MOCK.wire(HANDLERS);
    const chip = $('hudHotline');
    if (chip) chip.onclick = () => {
      if (HAPI.remaining() > 0) toggleQuit();
      else if (HAPI.offer()) openCard();
    };
    $('btnHlQuitYes').onclick = () => { hideQuit(); HAPI.abandon(); };
    $('btnHlQuitNo').onclick = hideQuit;
  }
  function enterGame() { HL_MOCK.start(); tickChip(); }
  function tick() {
    HL_MOCK.tick();
    tickChip();
  }

  return { init, enterGame, tick, openCard };
})();
