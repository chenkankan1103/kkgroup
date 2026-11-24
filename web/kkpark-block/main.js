'use strict';
/* main.js — boot＋主迴圈（寫手 A＝四段日迴圈骨架接縫 §11-13；寫手 2＝Pixi 初始化＋事件掛點）
   日迴圈四段（spec §1）：①開機收帳 ②街上時光（主玩法）③處理帳面 ④睡覺結算
   —— A 的段落狀態機落地前，本檔先常駐「街上時光」段（垂直切片 D1-3）。
   事件掛點照簽名 §7：stars（星星 HUD）／arrest（檢定卡）／money（HUD）。 */

(async () => {
  // 像素 perfect：全域 NEAREST（§9.1）——texture 縮放不吃模糊
  PIXI.TextureSource.defaultOptions.scaleMode = 'nearest';

  const app = new PIXI.Application();
  await app.init({ background: 0x0b0e14, resizeTo: window, antialias: false, preference: 'webgl' });
  document.body.appendChild(app.canvas);

  // Cubic 11 是 web font——canvas Text 用前先等字體就緒（否則中心數字掉 fallback）
  try { await document.fonts.load('13px "Cubic 11"'); } catch (e) {}

  // 素材：Kenney Topdown Shooter（CC0，web/kkpark-map/assets/kenney-topdown/）——跨目錄引用不複製
  const A = '../kkpark-map/assets/kenney-topdown/PNG/';
  const tex = await PIXI.Assets.load([
    { alias: 'tile', src: A + 'Tiles/tile_01.png' },
    { alias: 'man', src: A + 'Man Brown/manBrown_stand.png' },
  ]);

  // ===== 開檔：Save.load() || Save.newGame()（簽名 §6；mock newGame 內含 BlockMap.generate） =====
  window.S = Save.load() || Save.newGame();

  // ===== 地圖生成（簽名 §1）：blocks 進 S，obstacles 餵 walk 碰撞 =====
  const gen = (S.blocks && S.blocks.length) ? { blocks: S.blocks, obstacles: new Uint8Array(Math.ceil(BlockMap.W / BlockMap.TILE) * Math.ceil(BlockMap.H / BlockMap.TILE)) } : BlockMap.generate(S.seed);
  S.blocks = gen.blocks;
  Walk.setObstacles(gen.obstacles);

  // ===== 世界：相機 zoom 固定 2×（§9.1） =====
  const world = new PIXI.Container();
  world.scale.set(2);
  app.stage.addChild(world);
  globalThis.__app = app; globalThis.__world = world;   // QA 探針掛點

  GroundRender.init(world, tex.tile);
  BlockRender.init(world);
  BlockRender.render();
  BaseRender.init(world);
  BaseRender.render();
  Walk.init(app, world, tex.man);

  // ===== HUD 與事件掛點（簽名 §7） =====
  const $ = (id) => document.getElementById(id);
  $('hud').classList.remove('hidden');
  $('hudDay').textContent = `第 ${S.day} 天`;
  $('hudMoney').textContent = '$' + S.money.toLocaleString();

  Bus.on('stars', (n) => {           // 星星三顆（B11 掛點，mock 恆 0）
    document.querySelectorAll('#hudStars .star').forEach((el, i) => el.classList.toggle('on', i < n));
  });
  Bus.on('money', () => { $('hudMoney').textContent = '$' + S.money.toLocaleString(); });
  Bus.on('arrest', (a) => openArrest(a));   // 被捕檢定卡（mock Dice 偏向成功）
  Bus.on('flip', () => BlockRender.render());   // 跳槽翻轉 → 色塊語意全換（渲染碼零改動的驗收點）

  // ===== v0.2.0：踩點（E）／據點點擊（E 近據點）／睡覺結算（T）／晨報（dayEnd） =====
  let reportOpen = false;

  document.addEventListener('keydown', (e) => {
    if (e.code === 'KeyE') act();
    if (e.code === 'KeyT') sleep();
  });

  function act() {
    const p = Walk.pos();
    const near = (S.bases || []).find((b) => {
      const c = S.blocks[b.blk].center;
      return Math.hypot(p.x - c[0], p.y - c[1]) < 28;
    });
    if (near) {                       // 據點互動優先：點擊機 +1 貨（spec §7 主按鈕的切片版）
      Base.click(near);
      floatAt(p.x, p.y - 24, '+1 貨', '#ffe14d');
      return;
    }
    const blk = BlockMap.blockAt(S, p.x, p.y);
    if (!blk) return;
    const r = Faction.scout(S, blk);  // 踩點：站進街區 +8，冷卻 5s（spec §2.2）
    if (r.ok) {
      floatAt(blk.center[0], blk.center[1] - 16, '+8', '#4dff9d');
      BlockRender.render();
    } else {
      floatAt(blk.center[0], blk.center[1] - 16, '…', '#8b97b0');
    }
  }

  function sleep() {
    if (reportOpen) return;
    Save.dayEnd(S);                   // 引擎：收帳→推拉→day+1→存檔→emit dayEnd
  }

  Bus.on('dayEnd', (rep) => {
    reportOpen = true;
    const lines = [];
    if (rep.income > 0) lines.push(`貨 ${rep.goodsSold} → 收帳 $${rep.income.toLocaleString()}`);
    rep.events.forEach((ev) => lines.push(`街區 ${ev.blk + 1} 易手：${ev.from > 0 ? '綠' : '藍'}${ev.from} → ${ev.to > 0 ? '綠' : '藍'}${ev.to}`));
    rep.locks.forEach((lk) => lines.push(`街區 ${lk.blk + 1} 定色成${lk.side === 'park' ? '綠' : '藍'}！`));
    if (!lines.length) lines.push('夜裡無事——街區板面緩慢流動');
    const modal = document.createElement('div');
    modal.id = 'reportModal';
    modal.innerHTML = `
      <div class="arrest-card">
        <h3>🌅 第 ${rep.day} 天早晨</h3>
        ${lines.map((l) => `<p>${l}</p>`).join('')}
        <button class="ev-btn" id="repOk">出門</button>
      </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#repOk').onclick = () => {
      modal.remove();
      reportOpen = false;
      $('hudDay').textContent = `第 ${S.day} 天`;
      BlockRender.render();
      BaseRender.render();
    };
  });

  // 浮字：世界座標 +9 的短命 Cubic 11 文字（900ms 上飄淡出）
  function floatAt(wx, wy, text, color) {
    const t = new PIXI.Text({
      text,
      style: {
        fontFamily: '"Cubic 11", monospace',
        fontSize: 13, fill: color,
        dropShadow: { blur: 2, distance: 0, color: 0x0b0e14, alpha: 0.8 },
      },
    });
    t.anchor.set(0.5);
    t.position.set(wx, wy);
    world.addChild(t);
    const t0 = performance.now();
    const f = () => {
      const k = (performance.now() - t0) / 900;
      if (k >= 1) { app.ticker.remove(f); t.destroy(); return; }
      t.y = wy - k * 22;
      t.alpha = 1 - k;
    };
    app.ticker.add(f);
  }

  // ===== 檢定卡（arrest 三選一——spec §5；mock Dice 直接偏成功） =====
  function openArrest(a) {
    const modal = document.createElement('div');
    modal.id = 'arrestModal';
    modal.innerHTML = `
      <div class="arrest-card">
        <h3>🚨 被攔下了</h3>
        <p>巡查員盯上你——選一條路應對（檢定：d20＋屬性 vs ${a.dc}）</p>
        <button class="ev-btn" data-line="agility">🏃 身手線——掙脫（星星歸零）</button>
        <button class="ev-btn" data-line="guts">💸 賄賂線——花 30% 現金放行</button>
        <button class="ev-btn" data-line="talk">🗣️ 求情線——口才檢定（難度高）</button>
        <div id="arrestResult"></div>
      </div>`;
    document.body.appendChild(modal);
    modal.querySelectorAll('[data-line]').forEach((btn) => {
      btn.onclick = () => {
        const line = btn.dataset.line;
        const attr = line === 'agility' ? 'agility' : line === 'guts' ? 'guts' : 'talk';
        const roll = Dice.roll(attr, a.dc);
        const res = modal.querySelector('#arrestResult');
        res.textContent = `🎲 ${roll.d20}＋${roll.attr}${roll.bonus ? `＋${roll.bonus}` : ''} = ${roll.total} vs ${roll.dc} → ${roll.ok ? '成功' : '失敗'}${roll.crit ? '（大成功！）' : ''}${roll.fumble ? '（大失敗…）' : ''}`;
        modal.querySelectorAll('[data-line]').forEach((b) => { b.disabled = true; });
        setTimeout(() => modal.remove(), 2200);
      };
    });
  }

  // ===== 主迴圈 =====
  // A 的日迴圈接縫（①收帳／②街上／③帳面／④睡覺）在此排程；現階段常駐街上。
  let last = performance.now();
  app.ticker.add(() => {
    const now = performance.now();
    const dtSec = Math.min(0.05, (now - last) / 1000);   // 切窗回來不吃大步（防瞬移）
    last = now;
    Walk.tick(dtSec);
    const st = Star.update(dtSec, { hero: Walk.pos(), cops: [], blocks: S.blocks, obstacles: gen.obstacles });   // 簽名 §4（mock 恆 0 星）
    if (st.stars !== S.stars) { S.stars = st.stars; Bus.emit('stars', st.stars); }
  });
})();
