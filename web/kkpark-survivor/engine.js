'use strict';
/* engine.js — canvas 渲染＋零配置池＋FPS 自適應降級（97KB 海底 demo 手法） */

const Engine = (() => {
  let cv = null, ctx = null, W = 0, H = 0, dpr = 1;
  let Q = 2;                       // 2 全效 / 1 減特效 / 0 減粒子
  let fpsAcc = 0, fpsN = 0;

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

  // 每幀開頭：世界座標跟著玩家（鏡頭），transform 一次
  function begin(cam) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#101418';
    ctx.fillRect(0, 0, W, H);
    ctx.save();
    ctx.translate(W / 2 - cam.x, H / 2 - cam.y);
  }
  function end() { ctx.restore(); }

  // 地板網格（程序化，無圖片）：只畫可視範圍
  function drawGrid(cam) {
    const g = 96;
    const x0 = Math.floor((cam.x - W / 2) / g) * g, y0 = Math.floor((cam.y - H / 2) / g) * g;
    ctx.strokeStyle = 'rgba(255,255,255,0.045)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    const x1 = cam.x + W / 2 + g, y1 = cam.y + H / 2 + g;
    for (let x = x0; x < x1; x += g) { ctx.moveTo(x, y0); ctx.lineTo(x, y1); }
    for (let y = y0; y < y1; y += g) { ctx.moveTo(x0, y); ctx.lineTo(x1, y); }
    ctx.stroke();
  }

  return { init, begin, end, drawGrid, fpsTick, makePool,
    get ctx() { return ctx; }, get W() { return W; }, get H() { return H; }, get Q() { return Q; } };
})();
