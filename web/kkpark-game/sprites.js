'use strict';
/* sprites.js — 全部像素圖用程式繪製（字串列 → offscreen canvas 預繪），零外部圖片依賴
   每個 sprite：map 色碼映射 + rows 字串陣列，'.' 與 ' ' 為透明；列長不需完全一致（左對齊） */

const SPRITE_DEFS = {
  /* 玩家：偶像——青髮＋粉裝＋金星飾 */
  player: {
    map: { c: '#7df9ff', s: '#ffd9b3', k: '#12151d', p: '#ff5ec4', g: '#ffe14d' },
    rows: [
      '...cccccc...',
      '..cccccccc..',
      '.cccccccccc.',
      '.ccsssssssc.',
      '..ssksskss..',
      '..ssssssss..',
      '...pppppp...',
      '..pppppppp..',
      '.pppgppgppp.',
      '.pppppppppp.',
      '..pppppppp..',
      '...kkkkkk...',
      '...kk..kk...',
      '...gg..gg...',
    ],
  },

  /* 黑粉：灰紫臉＋紅眼怒目 */
  fan: {
    map: { k: '#12151d', m: '#8b97b0', r: '#ff4d4d' },
    rows: [
      '..kkkkkk..',
      '.kkmmmmkk.',
      '.mmmmmmmm.',
      'mmrmmmmrmm',
      'mmmmmmmmmm',
      'mmkmmmmkmm',
      '.mmmmmmmm.',
      '..mmmmmm..',
      '..mm..mm..',
      '..mm..mm..',
    ],
  },

  /* 機器人水軍：藍灰機身＋螢光眼 */
  bot: {
    map: { b: '#5a6b8c', l: '#7df9ff', k: '#12151d' },
    rows: [
      '....ll....',
      '..bbbbbb..',
      '.bbbbbbbb.',
      '.blbbbblb.',
      '.bbbbbbbb.',
      '.bbkkkkbb.',
      '.bbbbbbbb.',
      '..bbbbbb..',
      '..b....b..',
      '..b....b..',
    ],
  },

  /* 杠精：高瘦紫皮＋賤笑 */
  troll: {
    map: { u: '#a06bff', w: '#e8f0ff', k: '#12151d' },
    rows: [
      '...uuuu...',
      '..uuuuuu..',
      '.uuuuuuuu.',
      '.uwuuuuwu.',
      '.uuuuuuuu.',
      '.uuukkuuu.',
      '.uuuuuuuu.',
      '..uuuuuu..',
      '..uuuuuu..',
      '..uu..uu..',
      '..uu..uu..',
      '..kk..kk..',
    ],
  },

  /* 精英：黑料卡車（紅警示燈＋車頭燈） */
  truck: {
    map: { T: '#3a4358', t: '#2a3040', r: '#ff4d4d', k: '#12151d', w: '#e8f0ff', y: '#ffe14d' },
    rows: [
      '........................',
      '.....rr.................',
      '....rrrr................',
      '..TTTTTTTTTT............',
      '.TTTTTTTTTTTT...........',
      '.TTTTTTTTTTTT...ttttt...',
      '.TTTTTTTTTTTT..tttttttt.',
      '.TTTTTTTTTTTT..tttwwttt.',
      '.TTTTTTTTTTTT..tttwwttyy',
      '.TTTTTTTTTTTT..tttttttt.',
      '.TTTTTTTTTTTTT.tttttttt.',
      '..TTTTTTTTTTTT.ttttttt..',
      '...kk...kk....kk..kk.kk.',
      '...kk...kk....kk..kk.kk.',
      '........................',
      '........................',
    ],
  },

  /* Boss：灌水機器王（紅角粉魔王，boss2 用 tint 轉紫） */
  boss: {
    map: { P: '#ff5ec4', R: '#ff4d4d', W: '#e8f0ff', K: '#12151d', G: '#8b97b0' },
    rows: [
      '......R..........R......',
      '......R..........R......',
      '.....RRR........RRR.....',
      '....RRRRR......RRRRR....',
      '...RRPPPPPPPPPPPPPPRR...',
      '..RPPPPPPPPPPPPPPPPPPR..',
      '..PPPPPPPPPPPPPPPPPPPP..',
      '..PPWWKPPPPPPPPPPKWWPP..',
      '..PPWWKPPPPPPPPPPKWWPP..',
      '..PPRRKPPPPPPPPPPKRRPP..',
      '..PPPPPPPPPPPPPPPPPPPP..',
      '..PPPKPPPPPPPPPPPPKPPP..',
      '...PPPPPPPPPPPPPPPPPP...',
      '...PKKKKKKKKKKKKKKKKP...',
      '...PKWKKWKKWKKWKKWKKP...',
      '...PKKKKKKKKKKKKKKKKP...',
      '....PPPPPPPPPPPPPPPP....',
      '...PPPPPPPPPPPPPPPPPP...',
      '..PPPPPPPPPPPPPPPPPPPP..',
      '..PPPPGGPPPPPPPPGGPPPP..',
      '.GPPPPPPPPPPPPPPPPPPPPG.',
      '.GGPPPPPPPPPPPPPPPPPPGG.',
      '..GGGGPPPPPPPPPPPPGGGG..',
      '....GGGG......GGGG......',
    ],
  },

  /* 經驗寶石（紫） */
  gem: {
    map: { v: '#a06bff', V: '#d5b8ff' },
    rows: [
      '...v...',
      '..vVv..',
      '.vVVVv.',
      'vvVVVvv',
      '.vvvvv.',
      '..vvv..',
    ],
  },

  /* 金幣 */
  gold: {
    map: { o: '#d9a800', Y: '#ffe14d' },
    rows: [
      '.oooo.',
      'oYYYYo',
      'oYooYo',
      'oYooYo',
      'oYYYYo',
      '.oooo.',
    ],
  },

  /* 寶箱 */
  chest: {
    map: { h: '#d9a800', Y: '#ffe14d' },
    rows: [
      '.hhhhhhhhhh.',
      'hYYYYYYYYYYh',
      'hYYYYYYYYYYh',
      'hhhhhhhhhhhh',
      'hYYYYhhYYYYh',
      'hYYYYhhYYYYh',
      'hYYYYYYYYYYh',
      '.hhhhhhhhhh.',
    ],
  },

  /* 飛鏢 */
  dart: {
    map: { g: '#d9a800', Y: '#ffe14d' },
    rows: [
      '..gg..',
      '.gYYg.',
      'ggYYgg',
      '..gg..',
    ],
  },

  /* 螢光棒 */
  glowstick: {
    map: { p: '#ff5ec4', W: '#ffd9ec', k: '#12151d' },
    rows: [
      '.pp.',
      'pWWp',
      'pWWp',
      'pWWp',
      'pWWp',
      'pWWp',
      'pWWp',
      '.pp.',
      '.kk.',
      '.kk.',
    ],
  },

  /* 愛心（備用） */
  heart: {
    map: { r: '#ff4d6d', R: '#ff9db0' },
    rows: [
      '.rr..rr.',
      'rRrrrrRr',
      'rrrrrrrr',
      'rrrrrrrr',
      '.rrrrrr.',
      '..rrrr..',
      '...rr...',
    ],
  },
};

/* ===== 預繪 ===== */
const SPRITES = {}; // name -> HTMLCanvasElement

function buildSprites() {
  for (const [name, def] of Object.entries(SPRITE_DEFS)) {
    const h = def.rows.length;
    const w = Math.max(...def.rows.map((r) => r.length));
    const cv = document.createElement('canvas');
    cv.width = w;
    cv.height = h;
    const c = cv.getContext('2d');
    def.rows.forEach((row, y) => {
      for (let x = 0; x < row.length; x++) {
        const col = def.map[row[x]];
        if (!col) continue; // '.' ' ' 未知字元 → 透明
        c.fillStyle = col;
        c.fillRect(x, y, 1, 1);
      }
    });
    SPRITES[name] = cv;
  }
}

/* 產生染色副本（boss2 輿論風暴等變體用） */
function makeTinted(name, color, alpha = 0.55) {
  const src = SPRITES[name];
  if (!src) return null;
  const cv = document.createElement('canvas');
  cv.width = src.width;
  cv.height = src.height;
  const c = cv.getContext('2d');
  c.drawImage(src, 0, 0);
  c.globalCompositeOperation = 'source-atop';
  c.globalAlpha = alpha;
  c.fillStyle = color;
  c.fillRect(0, 0, cv.width, cv.height);
  return cv;
}

/* 畫一個 sprite：中心點 (cx, cy)，scale 為每像素放大倍率 */
function drawSprite(ctx, name, cx, cy, { scale = 3, flip = false, rot = 0, alpha = 1, img = null } = {}) {
  const src = img || SPRITES[name];
  if (!src) return;
  const w = src.width * scale;
  const h = src.height * scale;
  ctx.save();
  ctx.translate(cx, cy);
  if (rot) ctx.rotate(rot);
  if (alpha < 1) ctx.globalAlpha = alpha;
  if (flip) ctx.scale(-1, 1);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(src, -w / 2, -h / 2, w, h);
  ctx.restore();
}

buildSprites();
