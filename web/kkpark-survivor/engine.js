'use strict';
/* engine.js — canvas 渲染＋零配置池＋FPS 自適應降級（97KB 海底 demo 手法） */

const Engine = (() => {
  let cv = null, ctx = null, W = 0, H = 0, dpr = 1;
  let Q = 2;                       // 2 全效 / 1 減特效 / 0 減粒子
  let fpsAcc = 0, fpsN = 0;
  const tex = {};                  // 地紋理（AI 生成，加載失敗就退回網格）

  // 通用零配置池：物件重用，永不 splice/new
  function makePool(create, reset) {
    const free = [];
    return {
      get() { const o = free.length ? free.pop() : create(); reset(o); return o; },
      put(o) { free.push(o); },
    };
  }

  // 幀率取樣（1 秒窗口）：<50 降級、>58 回升
  function fpsTick(dt) {
    fpsAcc += dt; fpsN++;
    if (fpsAcc < 1) return;
    const fps = fpsN / fpsAcc; fpsAcc = 0; fpsN = 0;
    if (fps < 50 && Q > 0) Q--;
    else if (fps > 58 && Q < 2) Q++;
  }

  function init(canvas) {
    cv = canvas;
    ctx = cv.getContext('2d');
    resize();
    window.addEventListener('resize', resize);
  }
  function resize() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = window.innerWidth; H = window.innerHeight;
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    cv.style.width = W + 'px'; cv.style.height = H + 'px';
  }

  // 每幀開頭：世界座標跟著鏡頭＋可選縮放（v0.3.2 視野拉後），transform 一次
  let curZoom = 1;
  function begin(cam, zoom) {
    curZoom = zoom || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#101418';
    ctx.fillRect(0, 0, W, H);
    ctx.save();
    ctx.translate(W / 2, H / 2);
    ctx.scale(curZoom, curZoom);
    ctx.translate(-cam.x, -cam.y);
  }
  function end() { ctx.restore(); }

  // 地板網格（程序化，無圖片）：只畫可視範圍（zoom 感知）
  function drawGrid(cam) {
    const g = 96, vw = W / curZoom, vh = H / curZoom;
    const x0 = Math.floor((cam.x - vw / 2) / g) * g, y0 = Math.floor((cam.y - vh / 2) / g) * g;
    ctx.strokeStyle = 'rgba(255,255,255,0.045)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    const x1 = cam.x + vw / 2 + g, y1 = cam.y + vh / 2 + g;
    for (let x = x0; x < x1; x += g) { ctx.moveTo(x, y0); ctx.lineTo(x, y1); }
    for (let y = y0; y < y1; y += g) { ctx.moveTo(x0, y); ctx.lineTo(x1, y); }
    ctx.stroke();
  }

  // ===== 地面紋理（AI 生成，加載失敗自動退回網格）=====
  function loadTexture(url, onReady) {
    const im = new Image();
    im.onload = () => { onReady(im); };
    im.onerror = () => { onReady(null); };
    im.src = url;
  }
  function loadTextures(onDone) {
    let left = 2;
    const fin = () => { if (--left <= 0) onDone(); };
    loadTexture('assets/ground.png', (im) => { tex.ground = im; fin(); });
    loadTexture('assets/core.png', (im) => { tex.core = im; fin(); });
  }

  // 畫地面：鏡射平鋪（相鄰格翻面拼接——接縫由構造保證連續，AI 紋理不必真無縫）
  // 注意：begin() 已把 transform 設成「世界座標」（translate 到鏡頭），所以這裡直接用世界座標畫
  const TEX_SCALE = 2;               // 1 張 256px 紋理＝世界 512px
  function drawGround(cam, coreR) {
    if (!tex.ground) { drawGrid(cam); return; }
    const TS = 256 * TEX_SCALE;
    const vw = W / curZoom, vh = H / curZoom;
    const x0 = Math.floor((cam.x - vw / 2) / TS) * TS, y0 = Math.floor((cam.y - vh / 2) / TS) * TS;
    for (let gx = x0; gx < cam.x + vw / 2; gx += TS) {
      for (let gy = y0; gy < cam.y + vh / 2; gy += TS) {
        const fx = ((Math.round(gx / TS) % 2) + 2) % 2 === 1;
        const fy = ((Math.round(gy / TS) % 2) + 2) % 2 === 1;
        ctx.save();
        ctx.translate(fx ? gx + TS : gx, fy ? gy + TS : gy);
        ctx.scale(fx ? -1 : 1, fy ? -1 : 1);
        ctx.drawImage(tex.ground, 0, 0, TS, TS);
        ctx.restore();
      }
    }
    // 核心區：疊核心廣場紋理（圓形遮罩；磚縮更細才有地板感）
    if (tex.core && coreR) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(cam.x, cam.y, coreR, 0, Math.PI * 2);
      ctx.clip();
      const CS = 160;
      for (let gx = Math.floor((cam.x - coreR) / CS) * CS - CS; gx < cam.x + coreR; gx += CS) {
        for (let gy = Math.floor((cam.y - coreR) / CS) * CS - CS; gy < cam.y + coreR; gy += CS) {
          const fx = ((Math.round(gx / CS) % 2) + 2) % 2 === 1;
          const fy = ((Math.round(gy / CS) % 2) + 2) % 2 === 1;
          ctx.save();
          ctx.translate(fx ? gx + CS : gx, fy ? gy + CS : gy);
          ctx.scale(fx ? -1 : 1, fy ? -1 : 1);
          ctx.drawImage(tex.core, 0, 0, CS, CS);
          ctx.restore();
        }
      }
      ctx.restore();
    }
  }

  return { init, begin, end, drawGrid, drawGround, loadTextures, fpsTick, makePool,
    get ctx() { return ctx; }, get W() { return W; }, get H() { return H; }, get Q() { return Q; },
    get zoom() { return curZoom; } };
})();
