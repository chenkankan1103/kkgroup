'use strict';
/* dock.js — v0.5.0：下方固定升級面板（放置掛機手感——手永遠有地方點）
   三分頁全吃寫手 A 的真 Sim API：
   ⬆️ 升級 Sim.getUpgradeTree().upgrade／🔧 裝備 .gear＋現有裝備耐久條／🧾 營運 .ops＋帳單預覽＋真 heat
   購買走 Sim.buyUpgrade(id)（缺錢/滿級 sim 自己 toast，UI 只做 disabled 視覺）
   收合後留 32px 提示條；錢一變動 → 摘要數字跳動（放置遊戲的即時回饋爽點） */

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
