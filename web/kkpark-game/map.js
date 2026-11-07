/* KK 園區 · 地圖版 — 走動引擎
 *
 * 純 DOM：地圖是一顆被 transform 推著走的大 div（當鏡頭用），
 * 角色沿用 maplestory.io 的 GIF。碰撞、BFS 尋路、紅包掉落在這裡；
 * 錢和派遣等遊戲邏輯在 game.js，兩邊只透過 window.KKMap 的
 * 幾個方法和 callback 溝通，互不伸手進對方的狀態。
 */
(function () {
  'use strict';

  const T = MAP.tile;
  const grid = MAP.grid;
  const ROWS = grid.length;
  const COLS = grid[0].length;
  const WORLD_W = COLS * T;
  const WORLD_H = ROWS * T;

  /* 開局出生點：主幹道中間 */
  const SPAWN = { x: 9, y: 5 };

  /* 站點字元 → JOBS.prop */
  const STATION_CHAR = { D: 'desk', P: 'phone', V: 'vault', S: 'server' };

  let blocked = [];          // [y][x] = true 擋路
  let stations = {};         // prop → 站點資料
  let viewport, world, dollEl, glowEl, btnInteract;
  let vw = 0, vh = 0;

  const doll = {
    x: 0, y: 0,              // 腳底中心（世界 px）
    speed: 140,              // px/s，大約一格 0.3 秒
    facing: 1,               // 1 = 面左（GIF 原方向），-1 = 面右（CSS 鏡射）
    locked: false,           // 派遣中／自動走路時，吃掉玩家輸入
    working: false,          // 站在派遣站工作
    workAnim: 'stand1',
    anim: 'stand1',
  };

  const held = {};           // 玩家按住的方向
  let path = null;           // BFS 自動走路的 waypoint（世界 px）
  let pathDone = null;

  let interactTarget = null;
  let opts = null;           // { getDollCsv, onInteract, onCoin, onDollReady }

  /* ================= 地圖解析 ================= */

  function buildMap() {
    blocked = [];
    for (let y = 0; y < ROWS; y++) {
      const row = [];
      for (let x = 0; x < COLS; x++) {
        const ch = grid[y][x];
        row.push(ch === '#' || ch === 't' || ch === 'l' || ch === 'b');
      }
      blocked.push(row);
    }

    for (let y = 0; y < ROWS; y++) {
      for (let x = 0; x < COLS; x++) {
        const ch = grid[y][x];

        const tile = document.createElement('div');
        tile.className = 'tile ' + tileClass(ch, x, y);
        tile.style.left = x * T + 'px';
        tile.style.top = y * T + 'px';
        world.appendChild(tile);

        const sc = STATION_CHAR[ch];
        if (sc) buildStation(sc, x, y);
      }
    }
  }

  function tileClass(ch, x, y) {
    /* 固定雜訊：同一格每次長出來都一樣，畫面才不會一直閃 */
    const v = (x * 7 + y * 13) % 3;
    if (ch === '#') return 'tile-wall';
    if (ch === '~') return 'tile-pool';
    if (ch === 't') return 'tile-tree';
    if (ch === 'l') return 'tile-lamp';
    if (ch === 'b') return 'tile-cone';
    if (ch === '.') return v < 2 ? 'tile-r0' : 'tile-r1';
    return 'tile-g' + v;
  }

  function buildStation(prop, c, r) {
    const meta = MAP.stations[prop];
    for (let dy = 0; dy < 2; dy++) {
      for (let dx = 0; dx < 3; dx++) blocked[r + dy][c + dx] = true;
    }

    /* 在主幹道上方的站，門朝下（互動格在腳印下面一格）；反之朝上 */
    const north = r < ROWS / 2;
    const doorRow = north ? r + 2 : r - 1;
    const workTile = { x: c + 1, y: doorRow };

    const el = document.createElement('div');
    el.className = 'bld bld-' + prop;
    el.style.left = c * T + 'px';
    el.style.top = (r * T - 44) + 'px';    /* 屋頂往上長一格 */
    el.style.zIndex = (r + 1) * 10;        /* 依腳印最底列做 y-sort */
    el.style.setProperty('--neon', meta.neon);
    el.innerHTML =
      '<div class="bld-body"><div class="bld-door"></div><span class="bld-emoji">' +
      meta.emoji + '</span></div>' +
      '<div class="bld-sign">' + meta.sign + '</div>' +
      '<div class="bld-bubble hidden"></div>';
    world.appendChild(el);

    stations[prop] = {
      doorX: (c + 1.5) * T,
      doorY: (doorRow + 0.5) * T,
      workTile: workTile,
      el: el,
      bubble: el.querySelector('.bld-bubble'),
    };
  }

  /* ================= 碰撞 ================= */

  function blockedAtPx(px, py) {
    const tx = Math.floor(px / T), ty = Math.floor(py / T);
    if (tx < 0 || ty < 0 || tx >= COLS || ty >= ROWS) return true;
    return blocked[ty][tx];
  }

  /* 角色的腳底佔一小塊矩形，四個角都不踩牆才准走 */
  function boxBlocked(cx, cy) {
    const hw = 11, top = cy - 8, bot = cy + 4;
    return blockedAtPx(cx - hw, top) || blockedAtPx(cx + hw, top) ||
           blockedAtPx(cx - hw, bot) || blockedAtPx(cx + hw, bot);
  }

  function tryMove(dx, dy) {
    /* 兩軸分開試：撞牆時另一軸還能滑 */
    if (dx !== 0) {
      const nx = doll.x + dx;
      if (!boxBlocked(nx, doll.y)) doll.x = nx;
    }
    if (dy !== 0) {
      const ny = doll.y + dy;
      if (!boxBlocked(doll.x, ny)) doll.y = ny;
    }
  }

  /* ================= BFS 尋路 ================= */

  function findPath(sx, sy, tx, ty) {
    if (sx === tx && sy === ty) return [];
    if (tx < 0 || ty < 0 || tx >= COLS || ty >= ROWS) return null;
    if (blocked[ty][tx]) return null;

    const prev = new Int32Array(COLS * ROWS).fill(-1);
    const start = sy * COLS + sx;
    const q = [start];
    prev[start] = start;
    const DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1]];
    let found = -1;

    for (let qi = 0; qi < q.length && found < 0; qi++) {
      const cur = q[qi];
      const cx = cur % COLS, cy = (cur - cx) / COLS;
      for (let i = 0; i < 4; i++) {
        const nx = cx + DIRS[i][0], ny = cy + DIRS[i][1];
        if (nx < 0 || ny < 0 || nx >= COLS || ny >= ROWS) continue;
        if (blocked[ny][nx]) continue;
        const nk = ny * COLS + nx;
        if (prev[nk] !== -1) continue;
        prev[nk] = cur;
        if (nx === tx && ny === ty) { found = nk; break; }
        q.push(nk);
      }
    }
    if (found < 0) return null;

    const tiles = [];
    let k = found;
    while (k !== prev[k]) { tiles.push(k); k = prev[k]; }
    tiles.reverse();
    return tiles.map(function (k) {
      const x = k % COLS;
      return { x: (x + 0.5) * T, y: ((k - x) / COLS + 0.5) * T };
    });
  }

  /* ================= 紙娃娃 ================= */

  let dollCsv = '';
  const loaded = {};
  let dollSeq = 0;
  let firstLoad = true;

  function dollUrl(anim) {
    return API.base + '/animated/' + API.skin + '/' + dollCsv + '/' + anim +
           '/0?showears=false&resize=' + API.resize + '&flipX=true';
  }

  function dollReady() {
    if (!firstLoad) return;
    firstLoad = false;
    if (opts.onDollReady) opts.onDollReady();
  }

  /* maplestory.io 的圖是即時生成的，第一次要等好幾秒；
   * 先用 Image() 探好，載完才真的換上去，角色不會中途消失 */
  function applyDoll(url) {
    if (dollEl.getAttribute('src') === url) return;
    if (loaded[url]) { dollEl.src = url; dollReady(); return; }

    const seq = ++dollSeq;
    const im = new Image();
    im.onload = function () {
      loaded[url] = true;
      if (seq !== dollSeq) return;      // 中途又換動作了，這次的結果作廢
      dollEl.src = url;
      dollReady();
    };
    im.onerror = function () {
      /* 造型組合被伺服器拒絕時退回純身體，至少不要整張破圖 */
      if (seq !== dollSeq) return;
      const fb = API.base + '/animated/' + API.skin + '/' + API.body + '/' +
                 doll.anim + '/0?resize=' + API.resize;
      loaded[fb] = true;
      dollEl.src = fb;
      dollReady();
    };
    im.src = url;
  }

  function setAnim(a) {
    if (doll.anim === a) return;
    doll.anim = a;
    applyDoll(dollUrl(a));
  }

  function refreshDoll() {
    dollCsv = opts.getDollCsv();
    applyDoll(dollUrl(doll.anim));
  }

  function preload() {
    for (let i = 0; i < PRELOAD_ANIMS.length; i++) {
      const u = dollUrl(PRELOAD_ANIMS[i]);
      const im = new Image();
      im.onload = function () { loaded[u] = true; };
      im.src = u;
    }
  }

  function paintDoll() {
    dollEl.style.transform =
      'translate3d(' + (doll.x - 39) + 'px,' + (doll.y - 126) + 'px,0)' +
      (doll.facing === -1 ? ' scaleX(-1)' : '');
    glowEl.style.transform =
      'translate3d(' + (doll.x - 31) + 'px,' + (doll.y - 2) + 'px,0)';
    const z = Math.floor(doll.y / T) * 10;
    dollEl.style.zIndex = z + 6;
    glowEl.style.zIndex = z + 5;
  }

  /* ================= 主迴圈 ================= */

  let lastTs = 0;

  function frame(ts) {
    const dt = Math.min(50, ts - lastTs || 16) / 1000;
    lastTs = ts;
    step(dt);
    updateCamera();
    updateInteract();
    checkCoin();
    requestAnimationFrame(frame);
  }

  function step(dt) {
    let vx = 0, vy = 0;

    if (path) {
      const wp = path[0];
      const dx = wp.x - doll.x, dy = wp.y - doll.y;
      const dist = Math.hypot(dx, dy);
      if (dist < 4) {
        path.shift();
        if (!path.length) {
          path = null;
          const cb = pathDone;
          pathDone = null;
          if (cb) cb();
        }
      } else {
        vx = dx / dist * doll.speed;
        vy = dy / dist * doll.speed;
      }
    } else if (!doll.locked) {
      if (held.up) vy -= doll.speed;
      if (held.down) vy += doll.speed;
      if (held.left) vx -= doll.speed;
      if (held.right) vx += doll.speed;
      if (vx && vy) { vx *= 0.7071; vy *= 0.7071; }   // 斜向等速
    }

    if (vx || vy) {
      tryMove(vx * dt, vy * dt);
      if (vx < 0) doll.facing = 1;
      else if (vx > 0) doll.facing = -1;
      if (!doll.working) setAnim('walk1');
    } else if (!doll.working && !path) {
      setAnim('stand1');
    }
    paintDoll();
  }

  function updateCamera() {
    let cx, cy;
    if (WORLD_W <= vw) cx = -(vw - WORLD_W) / 2;
    else cx = Math.max(0, Math.min(WORLD_W - vw, doll.x - vw / 2));
    if (WORLD_H <= vh) cy = -(vh - WORLD_H) / 2;
    else cy = Math.max(0, Math.min(WORLD_H - vh, doll.y - vh / 2));
    world.style.transform = 'translate3d(' + (-cx) + 'px,' + (-cy) + 'px,0)';
  }

  /* ================= 互動偵測 ================= */

  const INTERACT_DIST = 64;

  function updateInteract() {
    let best = null, bestD = INTERACT_DIST;
    for (const prop in stations) {
      const st = stations[prop];
      const d = Math.hypot(doll.x - st.doorX, doll.y - st.doorY);
      if (d < bestD) { bestD = d; best = prop; }
      /* 工作中不跳 Z 提示，跟進度泡泡疊在一起太吵 */
      st.el.classList.toggle('near', d < INTERACT_DIST && !doll.locked);
    }
    if (best !== interactTarget) {
      interactTarget = best;
      btnInteract.classList.toggle('off', !best);
    }
  }

  function interact() {
    if (interactTarget && opts.onInteract) opts.onInteract(interactTarget);
  }

  /* ================= 輸入 ================= */

  const KEYMAP = {
    ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
    w: 'up', s: 'down', a: 'left', d: 'right',
    W: 'up', S: 'down', A: 'left', D: 'right',
  };
  const INTERACT_KEYS = { z: 1, Z: 1, e: 1, E: 1, Enter: 1, ' ': 1 };

  function clearHeld() {
    for (const k in held) held[k] = false;
  }

  function bindInput() {
    window.addEventListener('keydown', function (e) {
      const dir = KEYMAP[e.key];
      if (dir) { held[dir] = true; e.preventDefault(); return; }
      if (INTERACT_KEYS[e.key]) { e.preventDefault(); interact(); }
    });
    window.addEventListener('keyup', function (e) {
      const dir = KEYMAP[e.key];
      if (dir) held[dir] = false;
    });
    window.addEventListener('blur', clearHeld);
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) clearHeld();
    });

    const dpad = document.getElementById('dpad');
    dpad.addEventListener('pointerdown', function (e) {
      const b = e.target.closest('[data-dir]');
      if (!b) return;
      e.preventDefault();
      held[b.getAttribute('data-dir')] = true;
      if (b.setPointerCapture) b.setPointerCapture(e.pointerId);
    });
    dpad.addEventListener('pointerup', function (e) {
      const b = e.target.closest('[data-dir]');
      if (b) { held[b.getAttribute('data-dir')] = false; b.blur(); }
    });
    dpad.addEventListener('pointercancel', function (e) {
      const b = e.target.closest('[data-dir]');
      if (b) held[b.getAttribute('data-dir')] = false;
    });

    btnInteract.addEventListener('click', function () {
      interact();
      btnInteract.blur();
    });
  }

  /* ================= 派遣站的進出 ================= */

  function goToStation(prop, workAnim) {
    const st = stations[prop];
    if (!st) return;
    doll.working = false;
    doll.workAnim = workAnim || 'stand1';
    doll.locked = true;              // 走路途中也不吃輸入

    const tx = st.workTile.x, ty = st.workTile.y;
    const tiles = findPath(Math.floor(doll.x / T), Math.floor(doll.y / T), tx, ty);

    function arrive() {
      doll.working = true;
      setAnim(doll.workAnim);
      st.el.classList.add('working');
    }

    if (!tiles) {
      /* 走不到就瞬移，別讓派遣卡死 */
      doll.x = (tx + 0.5) * T;
      doll.y = (ty + 0.5) * T;
      arrive();
      return;
    }
    path = tiles;
    pathDone = arrive;
  }

  function placeAtStation(prop, workAnim) {
    /* 載入存檔時直接把人擺在工作崗位上，不播走路 */
    const st = stations[prop];
    if (!st) return;
    doll.x = (st.workTile.x + 0.5) * T;
    doll.y = (st.workTile.y + 0.5) * T;
    doll.working = true;
    doll.locked = true;
    doll.workAnim = workAnim || 'stand1';
    setAnim(doll.workAnim);
    st.el.classList.add('working');
  }

  function goIdle() {
    for (const p in stations) stations[p].el.classList.remove('working');
    doll.working = false;
    doll.locked = false;
    path = null;
    pathDone = null;
    setAnim('stand1');
  }

  function playOnce(anim, ms) {
    setAnim(anim);
    setTimeout(function () {
      if (!doll.working) setAnim('stand1');
    }, ms || 1800);
  }

  function reset() {
    goIdle();
    for (const p in stations) setStationState(p, null);
    doll.x = (SPAWN.x + 0.5) * T;
    doll.y = (SPAWN.y + 0.5) * T;
    paintDoll();
  }

  /* ================= 站點泡泡（進度／收錢） ================= */

  function setStationState(prop, state) {
    const st = stations[prop];
    if (!st) return;
    const b = st.bubble;
    if (!state) {
      b.classList.add('hidden');
      st.el.classList.remove('ready');
      return;
    }
    b.classList.remove('hidden');
    if (state.ready) {
      st.el.classList.add('ready');
      b.classList.add('ready');
      b.textContent = '💰 收錢！';
    } else {
      st.el.classList.remove('ready');
      b.classList.remove('ready');
      b.textContent = '⏳ ' + state.label + ' ' + Math.floor(state.pct || 0) + '%';
    }
  }

  /* ================= 小特效 ================= */

  function cashBurst(prop) {
    const st = stations[prop];
    if (!st) return;
    for (let i = 0; i < 6; i++) {
      const el = document.createElement('span');
      el.className = 'cash';
      el.textContent = '💵';
      el.style.left = (st.doorX - 9) + 'px';
      el.style.top = (st.doorY - 34) + 'px';
      el.style.setProperty('--dx', (Math.random() * 70 - 35) + 'px');
      el.style.setProperty('--rot', (Math.random() * 60 - 30) + 'deg');
      el.style.animationDelay = (i * 60) + 'ms';
      world.appendChild(el);
      setTimeout(function () { el.remove(); }, 1200 + i * 60);
    }
  }

  function floatText(wx, wy, text) {
    const el = document.createElement('div');
    el.className = 'float-text';
    el.textContent = text;
    el.style.left = wx + 'px';
    el.style.top = wy + 'px';
    world.appendChild(el);
    setTimeout(function () { el.remove(); }, 1250);
  }

  /* ================= 紅包掉落 ================= */

  let coinEl = null;
  let coinWX = 0, coinWY = 0;
  let coinLifeTimer = null;

  function coinTick() {
    if (coinEl || doll.locked || document.hidden) return;
    if (Math.random() >= MAP.coin.spawnChance) return;

    let tx, ty, ok = false;
    for (let tries = 40; tries > 0; tries--) {
      tx = 1 + Math.floor(Math.random() * (COLS - 2));
      ty = 1 + Math.floor(Math.random() * (ROWS - 2));
      const wx = (tx + 0.5) * T, wy = (ty + 0.5) * T;
      if (!blocked[ty][tx] && Math.hypot(wx - doll.x, wy - doll.y) > T * 3) {
        ok = true;
        coinWX = wx; coinWY = wy;
        break;
      }
    }
    if (!ok) return;

    coinEl = document.createElement('div');
    coinEl.className = 'coin';
    coinEl.textContent = '🧧';
    coinEl.style.left = (coinWX - 17) + 'px';
    coinEl.style.top = (coinWY - 24) + 'px';
    coinEl.style.zIndex = ty * 10 + 7;
    world.appendChild(coinEl);

    clearTimeout(coinLifeTimer);
    coinLifeTimer = setTimeout(function () {
      if (!coinEl) return;
      const el = coinEl;
      coinEl = null;
      el.classList.add('out');
      setTimeout(function () { el.remove(); }, 800);
    }, MAP.coin.life);
  }

  function checkCoin() {
    if (!coinEl) return;
    if (Math.hypot(coinWX - doll.x, coinWY - doll.y) < 30) {
      const el = coinEl;
      coinEl = null;
      clearTimeout(coinLifeTimer);
      const v = opts.onCoin ? opts.onCoin() : 0;
      if (v > 0) floatText(coinWX, coinWY - 34, '+' + v);
      el.remove();
    }
  }

  /* ================= 對外接口 ================= */

  window.KKMap = {
    init: init,
    goToStation: goToStation,
    placeAtStation: placeAtStation,
    goIdle: goIdle,
    playOnce: playOnce,
    reset: reset,
    refreshDoll: refreshDoll,
    setStationState: setStationState,
    cashBurst: cashBurst,
  };

  /* ================= 初始化 ================= */

  function init(o) {
    opts = o;
    viewport = document.getElementById('mapViewport');
    world = document.getElementById('mapWorld');
    btnInteract = document.getElementById('btnInteract');

    glowEl = document.createElement('div');
    glowEl.className = 'doll-glow';
    world.appendChild(glowEl);

    dollEl = document.createElement('img');
    dollEl.className = 'doll';
    dollEl.alt = '紙娃娃';
    world.appendChild(dollEl);

    buildMap();

    vw = viewport.clientWidth;
    vh = viewport.clientHeight;
    window.addEventListener('resize', function () {
      vw = viewport.clientWidth;
      vh = viewport.clientHeight;
    });

    dollCsv = o.getDollCsv();
    doll.x = (SPAWN.x + 0.5) * T;
    doll.y = (SPAWN.y + 0.5) * T;
    paintDoll();
    applyDoll(dollUrl('stand1'));
    preload();

    bindInput();
    setInterval(coinTick, MAP.coin.checkEvery);
    requestAnimationFrame(frame);
  }
})();
