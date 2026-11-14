'use strict';
/* avatar.js — 成員頭像接楓之谷紙娃娃（V3.1）
   資料源：VM 的 /api/game/user/<discord_id>/paperdoll（CORS 已放行）
   節流原則（避免大量圖片請求）：
   1. JSON 每個 Discord 用戶只抓一次、全站共用（記憶體＋sessionStorage 快取）
   2. 圖片只在成員卡「進入畫面且頁籤可見」時才載（IntersectionObserver＋visibilityState）
   3. 每張圖 URL 只載一次（img.src 設定後不動）；未綁定的成員維持 emoji 零請求 */

const Avatar = (() => {
  const API_BASE = 'https://kkgroup2026.duckdns.org';
  const BIND_KEY = 'kkpark_map_avatar_bind_v1';   // { memId: discordId }
  const CACHE_KEY = 'kkpark_map_avatar_cache_v1'; // { discordId: {face,hair,...} | null }
  const JSON_TTL = 6 * 60 * 60 * 1000;            // 成功資料快取 6 小時
  const JSON_TTL_MISS = 5 * 60 * 1000;            // 失敗（null）只快 5 分鐘，別卡半天

  const jsonCache = new Map();   // discordId -> paperdoll|null|'loading'
  const urlCache = new Map();    // discordId -> img url|null
  let observer = null;
  let bindings = {};

  try { bindings = JSON.parse(localStorage.getItem(BIND_KEY) || '{}'); } catch (e) { bindings = {}; }
  let diskCache = {};
  try { diskCache = JSON.parse(localStorage.getItem(CACHE_KEY) || '{}'); } catch (e) { diskCache = {}; }

  function saveDisk() {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(diskCache)); } catch (e) {}
  }

  function myDiscordId() {
    try { return localStorage.getItem('kkpark_discord_id') || ''; } catch (e) { return ''; }
  }
  function setMyDiscordId(id) {
    try { localStorage.setItem('kkpark_discord_id', id || ''); } catch (e) {}
  }

  // ── JSON：每個 discordId 一個請求，帶 TTL 快取 ──
  function fetchPaperdoll(discordId) {
    if (!discordId || !/^\d{5,25}$/.test(discordId)) return Promise.resolve(null);
    const cached = diskCache[discordId];
    if (cached && cached.t) {
      const ttl = cached.d ? JSON_TTL : JSON_TTL_MISS;
      if (Date.now() - cached.t < ttl) return Promise.resolve(cached.d);
    }
    if (jsonCache.get(discordId) === 'loading') return jsonCache.get(discordId + '#p') || Promise.resolve(null);
    const p = fetch(`${API_BASE}/api/game/user/${discordId}/paperdoll`, { mode: 'cors' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        const pd = d && d.paperdoll ? d.paperdoll : null;
        diskCache[discordId] = { t: Date.now(), d: pd };
        saveDisk();
        jsonCache.delete(discordId);
        return pd;
      })
      .catch(() => { jsonCache.delete(discordId); return null; });
    jsonCache.set(discordId, 'loading');
    jsonCache.set(discordId + '#p', p);
    return p;
  }

  // ── 圖片 URL：用紙娃娃欄位直接組 maplestory.io URL（跟 VM 同一組公式）──
  function buildImgUrl(pd, pose) {
    if (!pd) return null;
    const it = (v, def) => `{"itemId":${parseInt(v, 10) || def},"region":"TWMS","version":"256"}`;
    const items = [
      it(pd.skin, 12000), `{"itemId":2000,"region":"TWMS","version":"256"}`,
      it(pd.face, 20005), it(pd.hair, 30120),
      it(pd.overall || pd.top, 1040014), it(pd.bottom, 1060096), it(pd.shoes, 1072005),
    ];
    return `https://maplestory.io/api/character/${items.join(',')}/${pose || 'stand1'}/animated?showears=false&showLefEars=false&showHighLefEars=false&resize=3&flipX=true`;
  }

  // ── NPC 派遣員造型池（跟 DC 歡迎圖同款的已驗證組合），memId hash 固定分配 ──
  const NPC_LOOKS = [
    { face: 20005, hair: 30120, top: 1040014, bottom: 1060096, shoes: 1072005 },
    { face: 21731, hair: 34410, top: 1041004, bottom: 1061008, shoes: 1072005 },
    { face: 20005, hair: 60006, top: 1042001, bottom: 1060096, shoes: 1070078 },
  ];
  function npcLook(memId) {
    let h = 0;
    for (let i = 0; i < memId.length; i++) h = (h * 31 + memId.charCodeAt(i)) | 0;
    return NPC_LOOKS[Math.abs(h) % NPC_LOOKS.length];
  }

  // ── 地圖派遣小人：綁定成員穿 DC 造型（主角）、NPC 用池子；cb(url, isBound) ──
  function jobIconUrl(memId, pose, cb) {
    const discordId = bindings[memId];
    if (discordId) {
      fetchPaperdoll(discordId).then((pd) => cb(buildImgUrl(pd, pose), true));
    } else {
      cb(buildImgUrl(npcLook(memId), pose), false);
    }
  }

  // ── 懶載入：卡片進入畫面＋頁籤可見才掛 <img> ──
  function ensureObserver() {
    if (observer || typeof IntersectionObserver === 'undefined') return observer;
    observer = new IntersectionObserver((entries) => {
      for (const en of entries) {
        if (!en.isIntersecting) continue;
        observer.unobserve(en.target);
        hydrateCard(en.target);
      }
    }, { rootMargin: '60px' });
    return observer;
  }

  function hydrateCard(card) {
    if (document.visibilityState === 'hidden') {
      // 頁籤在背景：完全不動，等 visibilitychange 再來
      setTimeout(() => { if (document.visibilityState !== 'hidden') hydrateCard(card); }, 3000);
      return;
    }
    const discordId = card.dataset.avatarDiscord;
    if (!discordId) return;
    const holder = card.querySelector('.ava');
    if (!holder) return;
    const img = document.createElement('img');
    img.className = 'ava-doll';
    img.alt = '';
    img.decoding = 'async';
    img.loading = 'lazy';
    img.onload = () => { if (img.isConnected) holder.classList.add('has-doll'); };  // 圖到手才把 emoji 縮成角標
    img.onerror = () => { img.remove(); holder.classList.remove('has-doll'); };    // 失敗復原成正常 emoji
    holder.appendChild(img);
    fetchPaperdoll(discordId).then((pd) => {
      const url = buildImgUrl(pd);
      if (!url) { img.remove(); return; }
      img.src = url;
    });
  }

  // ── 對外：成員卡掛上綁定與懶載入（ui.js renderRoster 每次重建後呼叫）──
  function attachCards(rootEl) {
    if (!rootEl) return;
    const my = myDiscordId();
    rootEl.querySelectorAll('.mem-card').forEach((card) => {
      const memId = card.dataset.mem;
      if (!memId) return;
      const discordId = bindings[memId] || (my && !Object.values(bindings).includes(my) ? my : '');
      if (!discordId) return;
      card.dataset.avatarDiscord = discordId;
      const obs = ensureObserver();
      if (obs) obs.observe(card);
      else hydrateCard(card);  // 無 IO 的老瀏覽器直接載（僅此卡一張）
    });
  }

  function bind(memId, discordId) {
    if (discordId) bindings[memId] = discordId;
    else delete bindings[memId];
    try { localStorage.setItem(BIND_KEY, JSON.stringify(bindings)); } catch (e) {}
  }
  function getBind(memId) { return bindings[memId] || ''; }

  document.addEventListener('visibilitychange', () => {
    // 回到前景：補上背景期間漏掉的卡
    if (document.visibilityState !== 'hidden' && observer) {
      document.querySelectorAll('[data-avatar-discord]').forEach((c) => {
        if (!c.querySelector('.ava-doll')) observer.observe(c);
      });
    }
  });

  return { attachCards, bind, getBind, jobIconUrl, myDiscordId, setMyDiscordId, API_BASE };
})();
