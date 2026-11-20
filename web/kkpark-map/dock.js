'use strict';
/* dock.js — v0.5.0 前哨：下方固定升級面板（放置掛機手感——手永遠有地方點）
   三分頁：⬆️ 升級（mock 介面，等邏輯層 Sim.getUpgradeTree/buyUpgrade 接上）
         🔧 裝備（真資料：GEAR/S.gearUses 耐久條，買賣走 Sim.buyGear）
         🧾 營運（真資料：Sim.upkeepCost 帳單預覽；壓熱為 mock）
   收合後留 32px 提示條；錢一變動 → 摘要數字跳動（放置遊戲的即時回饋爽點） */

const Dock = (() => {
  const $ = (id) => document.getElementById(id);

  let open = false;
  let tab = 'up';
  let lastMoney = null;
  let mockHeat = 46;            // 壓熱 mock 值（原型示意，等邏輯層的熱度機制）
  const mockLv = {};            // 升級鏈 mock 等級暫存（prototype 用，不進存檔）

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

  /* ===== 資料源 ===== */
  // ⬆️ 升級：mock 介面——邏輯層回報 API 後，把 mockTree/mockBuy 換成 Sim.getUpgradeTree/Sim.buyUpgrade
  // 介面形狀（給寫手 A 的對接規格）：[{ id, icon, name, desc, lv, max, next }]
  function mockTree(S) {
    void S;  // mock 不讀 sim 狀態——等級存在本模組，存檔歸邏輯層管
    return BUILDINGS.map((b) => {
      const lv = mockLv[b.id] || 0;
      const max = 3;
      const next = lv < max ? Math.round((b.price * Math.pow(1.8, lv)) / 500) * 500 : 0;
      return { id: b.id, icon: b.icon, name: b.name, desc: b.desc, lv, max, next };
    });
  }
  function mockBuy(id) {
    mockLv[id] = (mockLv[id] || 0) + 1;
    return mockTree(null).find((u) => u.id === id);
  }

  /* ===== 渲染 ===== */
  function render() {
    if (tab === 'up') renderUp();
    else if (tab === 'gear') renderGear();
    else renderOps();
  }

  function renderUp() {
    const S = Sim.state(); if (!S) return;
    const tree = mockTree(S);
    $('dockBody').innerHTML = `
      <div class="dock-note">🧪 原型：升級鏈資料是 mock，金額不實扣——介面先定版，等寫手 A 的 getUpgradeTree/buyUpgrade</div>
      ${tree.map((u) => `
        <div class="shop-item">
          <span class="gi">${u.icon}</span>
          <div class="gi-body"><b>${u.name}<span class="lv-tag">Lv${u.lv}</span></b><small>${u.desc}</small></div>
          ${u.lv >= u.max
            ? '<span class="owned-tag">MAX</span>'
            : `<button class="mini dock-up" data-up="${u.id}">⬆️ $${u.next.toLocaleString()}</button>`}
        </div>`).join('')}`;
    $('dockBody').querySelectorAll('[data-up]').forEach((b) => {
      b.onclick = () => {
        const u = mockBuy(b.dataset.up);
        UI.toast('⬆️', `${u.name} 升到 Lv${u.lv}（原型：金額沒扣）`);
        renderUp();  // 先重畫（換新節點），再 pulse 新 row——順序反了動畫會被重建吃掉
        pulse(document.querySelector(`#dockBody [data-up="${u.id}"]`)?.closest('.shop-item'));
      };
    });
  }

  function renderGear() {
    const S = Sim.state(); if (!S) return;
    $('dockBody').innerHTML = `
      <div class="dock-note">🔧 真資料——耐久吃 S.gearUses（上限 ${DURABLE_USES} 次，用完要重買）；買賣走 Sim.buyGear</div>
      ${GEAR.map((g) => {
        const owned = !!S.gear[g.id];
        const uses = (S.gearUses || {})[g.id];
        let right;
        if (!owned) {
          right = `<button class="mini" data-gear="${g.id}">$${g.price.toLocaleString()}</button>`;
        } else if (g.durable) {
          const pct = Math.max(0, (uses / DURABLE_USES) * 100);
          const cls = pct <= 40 ? 'low' : pct <= 70 ? 'mid' : '';
          right = `<div class="dur-box">
            <div class="dur-track"><div class="dur-fill ${cls}" style="width:${pct}%"></div></div>
            <small>耐久 ${uses}/${DURABLE_USES}</small></div>`;
        } else {
          right = '<span class="owned-tag">✅</span>';
        }
        return `<div class="shop-item">
          <span class="gi">${g.icon}</span>
          <div class="gi-body"><b>${g.name}</b><small>${g.desc}</small></div>${right}
        </div>`;
      }).join('')}`;
    $('dockBody').querySelectorAll('[data-gear]').forEach((b) => {
      b.onclick = () => { Sim.buyGear(b.dataset.gear); renderGear(); renderSummary(); };
    });
  }

  function renderOps() {
    const S = Sim.state(); if (!S) return;
    const bill = Sim.upkeepCost();
    const trib = (!S.act2 && S.day >= TRIBUTE.FROM_DAY) ? Sim.tributeCost() : 0;
    const total = bill + trib;
    const ok = S.money >= total;
    $('dockBody').innerHTML = `
      <div class="dock-note">🧾 帳單數字是真的（Sim.upkeepCost）；🧯 壓熱是 mock——熱度機制等寫手 A</div>
      <div class="shop-sec">🧾 今晚 21:00 帳單</div>
      <div class="shop-item"><span class="gi">🧾</span>
        <div class="gi-body"><b>園區開銷 $${bill.toLocaleString()}</b>
        <small>成員 ${S.members.length} 人 × $${UPKEEP.PER_MEMBER.toLocaleString()}＋建築 ${Object.keys(S.buildings).length} 棟 × $${UPKEEP.PER_BUILDING.toLocaleString()}</small></div>
      </div>
      ${trib ? `<div class="shop-item"><span class="gi">🏹</span>
        <div class="gi-body"><b>貢金 $${trib.toLocaleString()}</b><small>上頭抽成（第 ${TRIBUTE.FROM_DAY} 天起每晚 21:00）</small></div>
      </div>` : ''}
      <div class="ops-verdict ${ok ? 'ok' : 'bad'}">
        帳上 $${S.money.toLocaleString()}${ok ? '——繳得出' : `——差 $${(total - S.money).toLocaleString()}，快接單`}
      </div>
      <div class="shop-sec">🧯 街頭熱度（mock）</div>
      <div class="heat-track"><div class="heat-fill" style="width:${mockHeat}%"></div></div>
      <div class="shop-item"><span class="gi">🧯</span>
        <div class="gi-body"><b>花錢壓熱</b><small>原型示意：熱度 ${mockHeat}/100——機制與價格等寫手 A 的 Sim API</small></div>
        <button class="mini" id="btnCoolHeat">💸 $8,000</button>
      </div>`;
    $('btnCoolHeat').onclick = () => {
      mockHeat = Math.max(0, mockHeat - 10);
      UI.toast('🧯', `消息沉下去了——熱度 ${mockHeat}/100（原型：錢沒扣、數值是 mock）`);
      renderOps();
    };
  }

  /* ===== 摘要提示條（收合後的 32px 也要有內容看） ===== */
  function renderSummary() {
    const S = Sim.state(); if (!S) return;
    const nexts = mockTree(S).filter((u) => u.lv < u.max).map((u) => u.next);
    const nextUp = nexts.length ? Math.min.apply(null, nexts) : 0;
    $('dockSummary').innerHTML =
      `💰 <b id="dockMoney">$${S.money.toLocaleString()}</b>` +
      (nextUp ? ` · ⬆️ 最低 $${nextUp.toLocaleString()}` : '') +
      ` · 🧾 $${Sim.upkeepCost().toLocaleString()}`;
  }

  /* ===== 每秒：摘要更新＋錢變動跳動（onTick 尾端呼叫） ===== */
  function tick() {
    const S = Sim.state();
    if (!S || $('dock').classList.contains('hidden')) return;
    renderSummary();
    if (lastMoney !== null && S.money !== lastMoney) pulse($('dockMoney'));
    lastMoney = S.money;
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
