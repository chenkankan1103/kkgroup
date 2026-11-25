'use strict';
/* player.js — 紙娃娃 sprite 載入＋canvas atlas 快取、主角狀態、裝備詞綴統計 */

const Player = (() => {
  // 紙娃娃 URL：跟 kkpark-map avatar.js 同公式（七件組＋pose；每件要帶 region/version，純 ID 必 400）
  function dollUrl(look, pose, animated, resize) {
    const it = (v, def) => `{"itemId":${parseInt(v, 10) || def},"region":"TWMS","version":"256"}`;
    const items = [
      it(look.skin, 12000), `{"itemId":2000,"region":"TWMS","version":"256"}`,
      it(look.face, 20005), it(look.hair, 30120),
      it(look.overall || look.top, 1040014), it(look.bottom, 1060096), it(look.shoes, 1072005),
    ];
    const tail = animated === false ? '0' : 'animated';
    return `https://maplestory.io/api/character/${items.join(',')}/${pose}/${tail}?showears=false&showLefEars=false&showHighLefEars=false&resize=${resize || 3}&flipX=true`;
  }

  // VM 紙娃娃 JSON → look 物件（玩家 DC 造型；快取同 kkpark-map key）
  async function fetchMyLook() {
    let id = '';
    try { id = localStorage.getItem('kkpark_discord_id') || ''; } catch (e) {}
    if (!id) return null;
    try {
      const ck = 'kkpark_survivor_pd_' + id;
      const cached = localStorage.getItem(ck);
      if (cached) return JSON.parse(cached);
      const r = await fetch(`${API_BASE}/api/game/user/${id}/paperdoll`, { mode: 'cors' });
      if (!r.ok) return null;
      const d = await r.json();
      const pd = d && d.paperdoll ? d.paperdoll : null;
      if (!pd) return null;
      const look = {
        skin: pd.skin, body: pd.body, face: pd.face, hair: pd.hair,
        top: pd.overall || pd.top, bottom: pd.bottom, shoes: pd.shoes,
      };
      try { localStorage.setItem(ck, JSON.stringify(look)); } catch (e) {}
      return look;
    } catch (e) { return null; }
  }

  // atlas：把 animated gif 的前 N 幀抓下來切成 canvas 格（戰鬥中零請求）
  // 簡化：動圖直接 <img> 繪製（瀏覽器解 gif 幀，drawImage 抓第一幀會失效——
  // 改抓「靜態單幀」2 個 pose：stand1 / walk1，走路用位移抖動代替逐幀動畫（MVP 夠用）
  const imgCache = new Map();   // key = url
  function loadImage(url) {
    if (imgCache.has(url)) return imgCache.get(url);
    const p = new Promise((res) => {
      const im = new Image();
      im.crossOrigin = 'anonymous';
      im.onload = () => res(im);
      im.onerror = () => res(null);
      im.src = url;
    });
    imgCache.set(url, p);
    return p;
  }
  // 怪/主角共用：預載 stand+walk 兩幀。載不到（離線/headless/CDN 掛）→ 程序化替代：
  // 用 offline canvas 畫一隻簡易小人（頭+身+腳），寫進 doll 物件同欄位，渲染端零改動
  function fallbackDoll(look, tag) {
    const mk = (walkPhase) => {
      const c = document.createElement('canvas');
      c.width = 44; c.height = 60;
      const g = c.getContext('2d');
      g.fillStyle = `hsl(${(hashHue(look.hair || tag) % 360)},45%,55%)`;
      g.beginPath(); g.arc(22, 12, 9, 0, 7); g.fill();               // 頭
      g.fillRect(14, 22, 16, 20);                                     // 身
      const sw = walkPhase ? 6 : 0;
      g.fillRect(16 + sw, 42, 4, 16); g.fillRect(24 - sw, 42, 4, 16); // 腿
      g.fillStyle = '#fff';
      g.fillRect(18, 10, 3, 3); g.fillRect(24, 10, 3, 3);             // 眼
      return c;
    };
    return { stand: mk(0), walk: mk(1), fallback: true };
  }
  function hashHue(n) {
    let h = 0;
    n = String(n);
    for (let i = 0; i < n.length; i++) h = Math.imul(h ^ n.charCodeAt(i), 2654435761) | 0;
    return Math.abs(h);
  }
  // 怪/主角共用：預載 stand+walk 兩幀
  async function preloadDoll(look) {
    const [stand, walk] = await Promise.all([
      loadImage(dollUrl(look, 'stand1', false, 3)),
      loadImage(dollUrl(look, 'walk1', false, 3)),
    ]);
    if (stand && walk) return { stand, walk, fallback: false };
    return fallbackDoll(look, look.hair);
  }

  return { fetchMyLook, preloadDoll, dollUrl };
})();
