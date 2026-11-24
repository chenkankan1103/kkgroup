'use strict';
/* map.js — Leaflet 暗色台灣地圖：瓦片串流、警察 NPC 經緯度偽隨機、任務/派遣標記 */

const GameMap = (() => {
  let map = null;
  let mMissions, mJobs, mPolice, mHQ, mBuild, mRaid, mTurf, mAct2, mPoi, mHl;
  const cb = {}; // 對外回呼：missionClick
  const jobMarkers = {}; // memId -> marker（出勤；不重建，才能用 CSS transition 平滑走路）
  const homeMarkers = {}; // memId -> marker（待命站總部周圍）

  // 台灣本島粗略輪廓與擋海判斷已退役——警車改坐真實路網（roads.js），山裡海上自然沒有車
  // 決定性偽隨機：同一格子、同一時段 → 每個玩家看到同一批警察（零後端）
  function hash3(x, y, salt) {
    let h = (Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263) + Math.imul(salt | 0, 974634211)) | 0;
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    h ^= h >>> 16;
    return (h >>> 0) / 4294967295;
  }

  const CELL = 0.004; // 巡邏格子 ≈ 400m

  function divIcon(html, size, cls) {
    return L.divIcon({ html, className: cls || 'mk-plain', iconSize: size, iconAnchor: [size[0] / 2, size[1] / 2] });
  }

  function init() {
    if (map) return;
    map = L.map('map', {
      zoomControl: true, minZoom: 8, maxZoom: 18,
      maxBounds: TW.bounds, maxBoundsViscosity: 0.8,
    });
    map.setView(TW.center, TW.zoom);
    L.tileLayer('https://services.arcgisonline.com/arcgis/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 18, maxNativeZoom: 16,   // V3.7：17-18 為拉伸放大（貼近模式用），16 以上瓦片不再縮小
      attribution: 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, (c) OpenStreetMap contributors',
    }).addTo(map);

    mPolice = L.layerGroup().addTo(map);
    mHQ = L.layerGroup().addTo(map);
    mMissions = L.layerGroup().addTo(map);
    mJobs = L.layerGroup().addTo(map);
    mBuild = L.layerGroup().addTo(map);
    mRaid = L.layerGroup().addTo(map);
    mTurf = L.layerGroup().addTo(map);
    mAct2 = L.layerGroup().addTo(map);
    mPoi = L.layerGroup().addTo(map);
    mHl = L.layerGroup().addTo(map);

    L.marker([HQ.lat, HQ.lng], {
      icon: divIcon('<div class="mk-hq">🏢<span>園區總部</span></div>', [76, 26]),
    }).addTo(mHQ);

    map.on('moveend zoomend', refreshPolice);
    refreshPolice();
  }

  // ===== 警察 NPC：坐真實路網（roads.js 的 ROAD_NET 路段鏈），只在「角色附近」現身 =====
  // 感知閘門：只有總部、派遣中的成員、任務釘（±2km）周邊的警力「可知」——臥底不會
  // 知道全台警力部署，其他地區是未知。格子的存在由雜湊門檻（時段密度）決定、格內
  // 從路網點挑一台車；車沿所屬路段決定性巡邏（位置是 gameMin 的純函數，暫停即凍結，
  // 跨縮放、跨玩家一致）。zoom ≥ 12 才顯示，低倍率只取格子子集（12 每 4 格、13 每 2 格）。
  let roadIdx = null;
  function buildRoadIndex() {
    roadIdx = new Map();
    ROAD_NET.forEach((chain, ci) => {
      for (let i = 0; i < chain.length; i++) {
        const p = chain[i];
        const key = Math.floor(p[1] / CELL) + ',' + Math.floor(p[0] / CELL);  // lngIdx,latIdx
        let arr = roadIdx.get(key);
        if (!arr) roadIdx.set(key, (arr = []));
        arr.push({ c: ci, i });
      }
    });
  }

  const SENSE_RAD = 0.018;  // 感知半徑（度）≈ 2km
  const SEG_MIN = 25;       // 每個路段取样間隔滑 25 遊戲分鐘（=25 真實秒，約 50km/h）
  let copsLive = [];        // 可視警車：{ mk, ci, i0, dir }

  // 車在路段上的決定性位置：seg = i0 + dir × (gameMin / SEG_MIN)，三角波折返＋線性內插
  function copPos(ci, i0, dir, atMin) {
    const chain = ROAD_NET[ci];
    const L = chain.length;
    const span = Math.max(1, (L - 1) * 2);
    let s = (i0 + dir * (atMin / SEG_MIN)) % span;
    if (s < 0) s += span;
    const u = s < L - 1 ? s : span - s;
    const i = Math.min(L - 2, Math.floor(u));
    const f = u - i;
    return [chain[i][0] + (chain[i + 1][0] - chain[i][0]) * f, chain[i][1] + (chain[i + 1][1] - chain[i][1]) * f];
  }

  // v0.4.2 警察凍結修：clearLayers 銷毀重建會打斷 CSS transition（新元素無起始位置可補間，
  // 全部瞬移＋等下一個 tickCops 節拍才動）——主角移動時 heat 跨檔頻繁觸發，看起來像整隊凍結。
  // 改「對齊式更新」：車的唯一 key = ci:i0:dir:k（決定性），同 key 復用舊 marker（setLatLng 平滑）
  const copMarkerPool = {};   // key -> marker
  function refreshPolice() {
    if (!map) return;
    copsLive = [];
    const seen = {};
    const z = map.getZoom();
    if (z < 12) return;
    if (!roadIdx) { if (typeof ROAD_NET === 'undefined' || !ROAD_NET.length) return; buildRoadIndex(); }
    const S = Sim.state();
    const anch = [HQ];
    if (S) {
      for (const id in S.jobs) if (S.jobs[id].pos) anch.push(S.jobs[id].pos);
      for (const m of S.missions) anch.push(m);
    }
    const step = z >= 14 ? 1 : z === 13 ? 2 : 4;
    const b = map.getBounds();
    const x0 = Math.floor(b.getWest() / CELL) - 1, x1 = Math.ceil(b.getEast() / CELL) + 1;
    const y0 = Math.floor(b.getSouth() / CELL) - 1, y1 = Math.ceil(b.getNorth() / CELL) + 1;
    const dens = Sim.policeDensity();
    let n = 0;
    for (let cy = y0; cy <= y1 && n < 450; cy++) {
      if (cy % step !== 0) continue;
      for (let cx = x0; cx <= x1 && n < 450; cx++) {
        if (cx % step !== 0) continue;
        // 感知閘門：錨點附近才顯示——你不是全知，只有自己人周邊的警力看得到
        let near = false;
        for (const a of anch) {
          if (Math.abs(cy * CELL - a.lat) < SENSE_RAD && Math.abs(cx * CELL - a.lng) < SENSE_RAD) { near = true; break; }
        }
        if (!near) continue;
        const pts = roadIdx.get(cx + ',' + cy);
        if (!pts) continue;
        // V2.7/V2.8：勢力瓣內密度不同——警方瓣車多、我方地盤車少（用 zoneOf 多瓣判定）
        const zone = Sim.zoneOf(cy * CELL, cx * CELL);
        let dens2 = dens;
        if (zone === 'police' || zone === 'contested') dens2 *= TURF.COP_BOOST_POLICE;
        else if (zone === 'park') dens2 *= TURF.COP_SUPPRESS_PARK;
        // v0.4.0 甲：heat 31+ 主角周邊巡查密度上調——「對方盯上你了」，車真的變多；
        // 門檻已飽和（dens2×0.9 命中率極高），乘倍率無效——改用「豁免格子」：heat 越高，
        // 沒過 hash 門檻的格子也有機率強制放行（每 6-2 格一台，決定性、不破 copPos 路線）
        const heat = typeof Sim.heatLevel === 'function' ? Sim.heatLevel() : 0;
        const forceEvery = heat >= HEAT.HUNT_MIN ? 2 : heat >= HEAT.SHIFT_MIN ? 4 : 0;   // 61+ 每 2 格、31+ 每 4 格
        for (let k = 0; k < 2; k++) {
          const roll = hash3(cx, cy, 7 + k);
          const forced = forceEvery > 0 && ((cx * 3 + cy + k) % forceEvery === 0);
          if (roll < dens2 * 0.9 || forced) {  // V3.5：0.45→0.9——主角走動視角下高倍率時視野格子太少，原門檻會開空窗（碰撞互動需要車常駐可見）
            const e = pts[(hash3(cx, cy * 3 + k, 11) * pts.length) | 0];
            const dir = hash3(cx * 3 + k, cy, 29) < 0.5 ? 1 : -1;
            const t = Sim.gameMin();
            const key = e.c + ':' + e.i + ':' + dir + ':' + k;
            seen[key] = true;
            let mk = copMarkerPool[key];
            if (mk) {
              // 復用：setLatLng 平滑補間（transition 不被打斷）
              try { mk.setLatLng(copPos(e.c, e.i, dir, t)); } catch (err) {}
            } else {
              mk = L.marker(copPos(e.c, e.i, dir, t), { icon: divIcon('🚔', [20, 20], 'cop-icon'), interactive: false }).addTo(mPolice);
              copMarkerPool[key] = mk;
            }
            copsLive.push({ mk, ci: e.c, i0: e.i, dir });
            n++;
          }
        }
      }
    }
    // 收掉這輪沒看到的車（出視野／密度變化）——從 pool 與圖層移除
    for (const key in copMarkerPool) {
      if (!seen[key]) { try { mPolice.removeLayer(copMarkerPool[key]); } catch (err) {} delete copMarkerPool[key]; }
    }
  }

  // 每 5 遊戲分鐘（5 真實秒）把可視警車的目標推進到 5 分鐘後的位置，CSS 補間滑過去
  // （v0.4.0：heat 追蹤感改由 refreshPolice 的密度上調承接，這裡維持決定性路線不動）
  function tickCops() {
    if (!copsLive.length) return;
    const t = Sim.gameMin();
    if (t % 5 !== 0) return;
    for (const c of copsLive) {
      try { c.mk.setLatLng(copPos(c.ci, c.i0, c.dir, t + 5)); } catch (e) {}
    }
  }

  // ===== 任務標記 =====
  function renderMissions(missions) {
    if (!map) return;
    mMissions.clearLayers();
    for (const m of missions) {
      const hot = m.risk >= 0.5 ? ' hot' : '';
      const mt = MISSION_TYPES[m.type] || ACT2_MISSION_TYPES[m.type] || { icon: '❓' };
      const mk = L.marker([m.lat, m.lng], {
        icon: divIcon(`<div class="mk-mis${hot}">${mt.icon}<span>${m.code}</span></div>`, [64, 26]),
      });
      mk.on('click', () => { if (cb.missionClick) cb.missionClick(m); });
      mk.addTo(mMissions);
    }
  }

  // ===== 派遣中的成員標記（跟著 job.pos 走：趕路 → 工作 → 回程）=====
  // V3.2：marker 本體是楓之谷小人——綁定成員（主角）穿 DC 造型、NPC 用固定造型池；
  // 趕路放 walk1 走路動畫、工作中站 stand1；URL 到手才替換 emoji，失敗靜默留 emoji
  // V3.2.1：沒派遣的成員（待命）站園區總部周圍——主角在家看得到，不會任務一結束人消失
  function homeSpot(memId, idx, total) {
    let h = 0;
    for (let i = 0; i < memId.length; i++) h = (h * 31 + memId.charCodeAt(i)) | 0;
    // 均勻圓圈打底（idx/total），memId hash 只做 ±40° 微調——人多也不疊點
    const ang = (idx / Math.max(1, total)) * Math.PI * 2 + ((Math.abs(h) % 80) - 40) * Math.PI / 180;
    const r = 0.0007 + (Math.abs(h >> 3) % 3) * 0.0004;  // ~78–155m 三層圈
    return [HQ.lat + Math.sin(ang) * r, HQ.lng + Math.cos(ang) * r];
  }

  function dollSrc(memId) {
    const b = Avatar.getBind(memId);
    return b ? 'b' + b : 'npc';
  }

  function attachDoll(mk, memId, pose, registry) {
    const srcNow = dollSrc(memId);
    const el0 = mk.getElement();
    if (el0) el0.dataset.dollSrc = srcNow;
    Avatar.jobIconUrl(memId, pose, (url, isBound) => {
      if (!url || registry[memId] !== mk) return;
      const el = mk.getElement();
      if (!el || el.dataset.dollSrc !== srcNow) return;  // 已有更新的掛載請求，這筆作廢
      const slot = el.querySelector('.mk-doll-slot');
      if (!slot) return;
      if (isBound && el) el.classList.add('me');  // 主角金框
      const img = document.createElement('img');
      img.className = 'mk-doll';
      img.alt = '';
      img.decoding = 'async';
      img.onload = () => { slot.textContent = ''; slot.appendChild(img); };  // 載完才收 emoji
      img.onerror = () => { img.remove(); };  // 失敗靜默留 emoji
      img.src = url;
    });
  }

  // 綁定狀態變了（雙擊綁定／解綁）：還原 emoji、拆金框、重掛造型
  function rebindDoll(mk, memId, emoji, pose, registry) {
    const el = mk.getElement();
    if (!el || el.dataset.dollSrc === dollSrc(memId)) return;
    el.classList.remove('me');
    const slot = el.querySelector('.mk-doll-slot');
    if (slot) slot.innerHTML = emoji;
    attachDoll(mk, memId, pose, registry);
  }

  function renderJobs(jobs, members) {
    if (!map) return;
    if (members.length && typeof Avatar.setProtagonist === 'function') Avatar.setProtagonist(members[0].id);  // 主角＝名冊第一位
    for (const id in jobMarkers) {
      if (!jobs[id]) { mJobs.removeLayer(jobMarkers[id]); delete jobMarkers[id]; }
    }
    for (const id in jobs) {
      const j = jobs[id];
      const mem = members.find((m) => m.id === id);
      if (!mem || !j.pos) continue;
      const emoji = j.leg === 'work' ? '📍' : '🛵';
      const moving = j.leg !== 'work';
      const pose = moving ? 'walk1' : 'stand1';
      if (!jobMarkers[id]) {
        const mk = L.marker([j.pos.lat, j.pos.lng], {
          icon: divIcon(`<div class="mk-job"><span class="mk-doll-slot">${mem.avatar}</span><i>${emoji}</i></div>`, [40, 28], 'mk-job-wrap'),
          interactive: false,
        }).addTo(mJobs);
        jobMarkers[id] = mk;
        attachDoll(mk, id, pose, jobMarkers);
      } else {
        jobMarkers[id].setLatLng([j.pos.lat, j.pos.lng]);
        const el = jobMarkers[id].getElement();
        if (el) {
          el.classList.toggle('mv', moving);
          const ic = el.querySelector('.mk-job i');
          if (ic) ic.textContent = emoji;
          if (el.dataset.dollSrc !== dollSrc(id)) {
            rebindDoll(jobMarkers[id], id, mem.avatar, pose, jobMarkers);
          } else {
            const img = el.querySelector('.mk-doll');
            if (img && !img.src.includes('/' + pose + '/')) {
              // 走路↔站立換圖（靜態/動畫由 jobIconUrl 依身分決定；同 URL 瀏覽器快取）
              Avatar.jobIconUrl(id, pose, (url) => { if (url && img.isConnected) img.src = url; });
            }
          }
        }
      }
    }
    // 待命成員站總部周圍（站位由 memId 決定、永不變；出勤即收掉）
    for (const mid in homeMarkers) {
      const mem = members.find((m) => m.id === mid);
      if (!mem || jobs[mid] || mem.state !== 'idle') {
        mJobs.removeLayer(homeMarkers[mid]); delete homeMarkers[mid];
      }
    }
    const idleMems = members.filter((m) => !jobs[m.id] && m.state === 'idle');
    idleMems.forEach((mem, idx) => {
      const hm = homeMarkers[mem.id];
      if (!hm) {
        const [hlat, hlng] = homeSpot(mem.id, idx, idleMems.length);
        const mk = L.marker([hlat, hlng], {
          icon: divIcon(`<div class="mk-job"><span class="mk-doll-slot">${mem.avatar}</span><i>🟢</i></div>`, [40, 28], 'mk-job-wrap'),
          interactive: false,
        }).addTo(mJobs);
        homeMarkers[mem.id] = mk;
        attachDoll(mk, mem.id, 'stand1', homeMarkers);
      } else {
        rebindDoll(hm, mem.id, mem.avatar, 'stand1', homeMarkers);
      }
    });
  }

  // ===== 園區建設：蓋好的設施與工地排在總部四周 =====
  const B_SPOTS = [
    [0.0018, 0.0018], [0.0018, -0.0018], [-0.0018, 0.0018],
    [-0.0018, -0.0018], [0.0028, 0],
  ];
  function renderBuildings(S) {
    if (!map) return;
    mBuild.clearLayers();
    BUILDINGS.forEach((b, i) => {
      const built = S.buildings[b.id];
      const inQueue = S.buildQueue.some((q) => q.id === b.id);
      if (!built && !inQueue) return;
      const [dLat, dLng] = B_SPOTS[i % B_SPOTS.length];
      const html = built
        ? `<div class="mk-build">${b.icon}<span>${b.name}</span></div>`
        : `<div class="mk-build site">⚒️<span>${b.name}</span></div>`;
      L.marker([HQ.lat + dLat, HQ.lng + dLng], {
        icon: divIcon(html, [64, 24]), interactive: false,
      }).addTo(mBuild);
    });
  }

  // ===== V2.7/V2.8：勢力範圍——瓣狀淡色圓疊加，疊出有機形狀 =====
  // 詐團瓣＝總部＋每棟建築（地盤是蓋出來的形狀）；警方瓣＝分局＋派出所點。
  // 每瓣是 fill 5% 的獨立圓，重疊處自然變濃；半徑變動 >20m 才重設，減少重繪。
  let parkPetalsCircles = [], policePetalsCircles = [];
  function renderTurf() {
    if (!map) return;
    const pp = Sim.parkPetals(), qp = Sim.policePetals();
    const pr = Sim.parkRadius() * 111320, qr = Sim.policeRadius() * 111320;
    // 詐團瓣：數量對齊建築狀態（蓋好→多一瓣；被拆→收回），半徑跟信任
    parkPetalsCircles = syncPetals(parkPetalsCircles, pp, pr, 'turf-park', (c, i) => c._r !== pr);
    policePetalsCircles = syncPetals(policePetalsCircles, qp, qr, 'turf-police', (c, i) => c._r !== qr);
  }
  function syncPetals(circles, pts, radiusM, cls, needsUpdate) {
    // 收多餘的
    while (circles.length > pts.length) { mTurf.removeLayer(circles.pop()); }
    for (let i = 0; i < pts.length; i++) {
      let c = circles[i];
      if (!c) {
        c = L.circle([pts[i].lat, pts[i].lng], { radius: radiusM, className: cls, interactive: false }).addTo(mTurf);
        c._r = -1; c._pos = '';
        circles.push(c);
      } else {
        const posKey = pts[i].lat.toFixed(5) + ',' + pts[i].lng.toFixed(5);
        if (c._pos !== posKey) { c.setLatLng([pts[i].lat, pts[i].lng]); c._pos = posKey; }
      }
      if (Math.abs(radiusM - c._r) > 20) { c.setRadius(radiusM); c._r = radiusM; }
    }
    return circles;
  }

  // ===== V3.0：第二幕——詐團總部標記（一幕後期）與 NPC 據點紅瓣（二幕） =====
  let hqMarker = null, cellMarkers = {};
  function renderAct2(S) {
    if (!map) return;
    const hqPos = Sim.act2HqPos;
    // 總部：一幕、進度解鎖後出現；反轉後消失
    const showHq = !S.act2 && S.police >= ACT2.UNLOCK_POLICE;
    if (showHq && !hqMarker) {
      hqMarker = L.marker([hqPos.lat, hqPos.lng], {
        icon: divIcon('<div class="mk-hqact">🏚️<span>詐團總部</span></div>', [86, 26]),
      }).addTo(mAct2);
      hqMarker.on('click', () => { if (cb.hqClick) cb.hqClick(); });
    } else if (!showHq && hqMarker) {
      mAct2.removeLayer(hqMarker); hqMarker = null;
    }
    // 據點：二幕才存在——紅瓣（跟勢力瓣同一套淡色語言，但更濃）＋標記
    const cells = S.act2 ? (S.cells || []) : [];
    for (const id in cellMarkers) {
      if (!cells.some((c) => c.id === id)) {
        mAct2.removeLayer(cellMarkers[id].mk);
        mAct2.removeLayer(cellMarkers[id].petal);
        delete cellMarkers[id];
      }
    }
    for (const c of cells) {
      if (!cellMarkers[c.id]) {
        const petal = L.circle([c.lat, c.lng], { radius: 1, className: 'turf-cell', interactive: false }).addTo(mAct2);
        const mk = L.marker([c.lat, c.lng], {
          icon: divIcon(`<div class="mk-cell">🏭<span>${c.name}·${c.boss}</span></div>`, [120, 26]),
        }).addTo(mAct2);
        mk.on('click', () => { if (cb.cellClick) cb.cellClick(c); });
        cellMarkers[c.id] = { mk, petal };
      }
      cellMarkers[c.id].petal.setRadius(TURF.POLICE_BASE * 111320 * 0.9);
    }
  }

  // ===== V2：攻堅集結——警車紅藍閃爍從四面八方圍向總部；結算後撤走 =====
  // 放獨立圖層，不會被 refreshPolice 的 clearLayers() 掃掉
  let raidCars = [];
  // ===== V3.5：主角（玩家化身）marker——操控走動、鏡頭跟隨、碰警車盤查 =====
  let heroMarker = null;
  let heroPose = 'stand1';  // stand1 / walk1（img.src 切換）
  // ===== v0.5.3 主角路網滑行：rAF 每幀沿 ROAD_NET 鏈推進（跟巡查車同款「沿路滑行」）=====
  // 狀態：heroNet = { ci, pi }（在鏈 ci 的節點 pi 與 pi+1 之間）——運行期狀態，pos 照存座標
  // 按鍵 → 選「與移動方向最對齊」的相鄰段 → 每幀沿段推進 heroSpeed()/fps 度 → 寫 S.hero.pos
  // 離路（該方向無路網可續）→ 退回自由行走（寫 moveDir 讓 sim 舊路徑？不——自由行走也用 rAF 直線推進）
  let heroNet = null;          // { ci, pi, prev } 或 null（不在路上）
  let heroRaf = null;
  let heroLastTs = null;       // v0.5.3：dt 補償——背景分頁 rAF 節流時靠 renderHero 同步呼叫推進
  let heroWasOffRoad = false;  // v0.5.4：頓挫邊緣判定（map.js 自己的狀態，渲染層擁有）

  // 找離 pos 最近的路網「節點」：回 { ci, pi, lat, lng }
  // v0.5.4：格子索引（400m 格，一次建）——原本每幀線性掃 70k 點把 rAF 拖死
  const NET_CELL = 0.004;
  let netGrid = null;
  function buildNetGrid() {
    netGrid = new Map();
    for (let ci = 0; ci < ROAD_NET.length; ci++) {
      const chain = ROAD_NET[ci];
      for (let pi = 0; pi < chain.length; pi++) {
        const key = Math.floor(chain[pi][0] / NET_CELL) + ',' + Math.floor(chain[pi][1] / NET_CELL);
        let arr = netGrid.get(key);
        if (!arr) netGrid.set(key, (arr = []));
        arr.push({ ci, pi, lat: chain[pi][0], lng: chain[pi][1] });
      }
    }
  }
  function nearestNetNode(lat, lng) {
    if (!netGrid && typeof ROAD_NET !== 'undefined' && ROAD_NET.length) buildNetGrid();
    if (!netGrid) return null;
    const gy = Math.floor(lat / NET_CELL), gx = Math.floor(lng / NET_CELL);
    let best = null, bestD = Infinity;
    for (const r of [1, 2, 3]) {
      for (let yy = gy - r; yy <= gy + r; yy++) {
        for (let xx = gx - r; xx <= gx + r; xx++) {
          const arr = netGrid.get(yy + ',' + xx);
          if (!arr) continue;
          for (const node of arr) {
            const d = (node.lat - lat) ** 2 + (node.lng - lng) ** 2;
            if (d < bestD) { bestD = d; best = node; }
          }
        }
      }
      if (best) return best;   // 由內向外擴，第一圈有就回
    }
    return null;
  }
  // 從 (ci,pi) 出發，選與移動方向 (dLat,dLng) 最對齊的相鄰節點；回 { ci, pi } 新位置
  // 選下一段：排名制（選 dot 最大），prev 只在「有其他 dot>0 候選」時才排除——
  // v0.5.3 回歸修：原本 dot>0.05 門檻在「鏈延伸方向與輸入相反」時殺掉唯一候選（主角折返同街）、
  // avoid 無條件排除 prev 會擋掉路口掉頭、鏈尾沒有跨鏈連接＝斷鏈盡頭必折返
  function nextNetNode(ci, pi, dLat, dLng, avoid) {
    const cands = [];
    const atEnd = pi - 1 < 0 || pi + 1 >= ROAD_NET[ci].length;   // 鏈端：找跨鏈接續
    for (const [dci, dpi] of [[ci, pi - 1], [ci, pi + 1]]) {
      if (dpi < 0 || dpi >= ROAD_NET[dci].length) continue;
      const key = dci + ':' + dpi;
      const p = ROAD_NET[dci][dpi];
      const len = Math.hypot(p[0] - ROAD_NET[ci][pi][0], p[1] - ROAD_NET[ci][pi][1]) || 1e-9;
      const dot = ((p[0] - ROAD_NET[ci][pi][0]) / len) * dLat + ((p[1] - ROAD_NET[ci][pi][1]) / len) * dLng;
      cands.push({ ci: dci, pi: dpi, key, dot });
    }
    if (atEnd) {
      // 鏈端跨鏈：全域找其他鏈的接續節點（<0.002° ≈220m——資料切鏈有間隙，33m 太小會誤判死路折返）
      const here = ROAD_NET[ci][pi];
      for (let cj = 0; cj < ROAD_NET.length; cj++) {
        if (cj === ci) continue;
        let bestJ = null, bestD = 0.002;
        for (let pj = 0; pj < ROAD_NET[cj].length; pj++) {
          const q = ROAD_NET[cj][pj];
          const d = Math.hypot(q[0] - here[0], q[1] - here[1]);
          if (d < bestD) { bestD = d; bestJ = pj; }
        }
        if (bestJ !== null) {
          const q = ROAD_NET[cj][bestJ];
          const len = bestD || 1e-9;
          const dot = ((q[0] - here[0]) / len) * dLat + ((q[1] - here[1]) / len) * dLng;
          cands.push({ ci: cj, pi: bestJ, key: cj + ':' + bestJ, dot });
        }
      }
    }
    const forward = cands.filter((c) => c.dot > 0 && c.key !== avoid);
    if (forward.length) return forward.sort((a, b) => b.dot - a.dot)[0];   // 前進候選擇 dot 最大（prev 可被擠掉＝路口能掉頭）
    const any = cands.filter((c) => c.key !== avoid);
    if (any.length) return any.sort((a, b) => b.dot - a.dot)[0];           // 全背向：掉頭（dot 最大那條）
    return cands.length ? cands[0] : null;                                 // 單候選且是 prev：只能回頭（斷鏈盡頭）
  }
  // 主角滑行主迴圈：每幀沿鏈推進；按鍵全空→急停在原地；無路網→沿移動方向自由推進
  function heroGlideTick() {
    const now = performance.now();
    const dt = heroLastTs === null ? 0 : Math.min(1000, now - heroLastTs);   // 秒；上限 1s 防瞬移
    heroLastTs = now;
    const S = Sim.state();
    if (!S || !S.hero) { heroRaf = null; return; }
    const keys = ['up', 'down', 'left', 'right'].filter((d) => Sim.isKeyDown(d));
    if (!keys.length || Sim.isPaused()) {
      S.hero.moving = false;
      heroNet = null;   // 停步：路段狀態清掉（下次走重新對齊）
      heroRaf = requestAnimationFrame(heroGlideTick);
      return;
    }
    // 移動方向：螢幕 up=緯度+（Leaflet y 向下、緯度向上）
    let dLat = 0, dLng = 0;
    if (keys.includes('up')) dLat += 1;
    if (keys.includes('down')) dLat -= 1;
    if (keys.includes('right')) dLng += 1;
    if (keys.includes('left')) dLng -= 1;
    const dl = Math.hypot(dLat, dLng) || 1;
    dLat /= dl; dLng /= dl;
    const p = S.hero.pos;

    // v0.5.4 重設計——道路是幫助不是牢籠：每幀重判模式，輸入永遠優先
    // ① 離路（dist>OFFROAD_DIST）：自由行走直線＋減速（heroSpeed 已含打折）＋進入頓挫
    // ② 路上：移動方向與當前路段對齊（dot>0.3）→ 沿段滑（吸附增益）；玩家轉向瞬間（對齊消失）→ 即時脫離自由走
    const near = nearestNetNode(p.lat, p.lng);
    const nearDist = near ? Math.hypot(near.lat - p.lat, near.lng - p.lng) : Infinity;
    const offRoad = nearDist > OFFROAD_DIST;
    S.hero.offRoad = offRoad;

    const step = (typeof Sim.heroSpeed === 'function' ? Sim.heroSpeed() : 0) * (dt / 1000);
    // 頓挫：從路上跨進離路的第一拍停一拍（進建築的黏感——v0.4.2 行為回歸）
    if (offRoad && !heroWasOffRoad) {
      heroWasOffRoad = true;
      heroNet = null;
      heroRaf = requestAnimationFrame(heroGlideTick);
      return;   // 這一幀不動
    }
    if (!offRoad) heroWasOffRoad = false;

    if (!offRoad && near) {
      // 路上：吸附增益——當前路段與移動方向對齊（dot>0.3）才沿段滑；對齊消失即時脫離（尊重輸入）
      if (heroNet) {
        const seg = ROAD_NET[heroNet.ci];
        const tgt = seg[heroNet.pi];
        const segLen = Math.hypot(tgt[0] - p.lat, tgt[1] - p.lng) || 1e-9;
        const segDot = ((tgt[0] - p.lat) / segLen) * dLat + ((tgt[1] - p.lng) / segLen) * dLng;
        if (segDot < 0.3) heroNet = null;   // 路段跟輸入脫鉤——放下吸附，即時響應
      }
      if (heroNet) {
        // 沿段滑：朝段端點推進
        const seg = ROAD_NET[heroNet.ci];
        const tgt = seg[heroNet.pi];
        const dSeg = Math.hypot(tgt[0] - p.lat, tgt[1] - p.lng);
        if (dSeg <= step) {
          p.lat = tgt[0]; p.lng = tgt[1];
          const prevKey = heroNet.ci + ':' + heroNet.pi;
          const nxt = nextNetNode(heroNet.ci, heroNet.pi, dLat, dLng, prevKey);
          if (nxt && nxt.dot > 0.3) heroNet = { ci: nxt.ci, pi: nxt.pi, prev: prevKey };
          else heroNet = null;   // 路口沒有順向段——自由走（玩家轉彎）
        } else {
          p.lat += (tgt[0] - p.lat) / dSeg * step;
          p.lng += (tgt[1] - p.lng) / dSeg * step;
        }
        S.hero.moving = true;
      } else {
        // 路上但無對齊段：直線走（方向即時響應）；貼上路網點且新段順向時重新吸附
        p.lat += dLat * step; p.lng += dLng * step;
        const node = nearestNetNode(p.lat, p.lng);
        if (node && Math.hypot(node.lat - p.lat, node.lng - p.lng) < 0.0004) {
          const seg = ROAD_NET[node.ci];
          const fwd = node.pi + 1 < seg.length ? seg[node.pi + 1] : seg[node.pi - 1];
          const fwdLen = Math.hypot(fwd[0] - node.lat, fwd[1] - node.lng) || 1e-9;
          const fwdDot = ((fwd[0] - node.lat) / fwdLen) * dLat + ((fwd[1] - node.lng) / fwdLen) * dLng;
          if (fwdDot > 0.3) { heroNet = { ci: node.ci, pi: node.pi + 1 < seg.length ? node.pi + 1 : node.pi - 1 }; p.lat = node.lat; p.lng = node.lng; }
        }
        S.hero.moving = true;
      }
    } else {
      // 離路：自由行走直線（黏感來自減速與頓挫，不鎖方向）；走回路上自動回吸附模式
      p.lat += dLat * step; p.lng += dLng * step;
      S.hero.moving = true;
    }
    S.hero.stopping = false;
    // 每幀直接推 marker（rAF 60fps 連續）＋離路變暗提示（v0.5.4 修：toggle 從 renderHero 移來——
    // renderHero 每秒一次會被 heroGlideTick 的每幀節奏吃掉，QA 取樣 False 的根因）
    if (heroMarker) {
      const el = heroMarker.getElement();
      if (el) {
        el.style.transition = 'none';
        el.classList.toggle('hero-offroad', offRoad);
        heroMarker.setLatLng([p.lat, p.lng]);
      }
    }
    heroRaf = requestAnimationFrame(heroGlideTick);
  }

  function renderHero() {
    if (!map) return;
    heroGlideTick();   // v0.5.3：路網滑行（每 tick 觸發一次 rAF 迴圈；迴圈自持）
    const S = Sim.state();
    if (!S || !S.hero) return;
    const pos = S.hero.pos;
    if (!heroMarker) {
      heroMarker = L.marker([pos.lat, pos.lng], {
        icon: divIcon('<div class="mk-hero"><span class="mk-doll-slot">🙂</span></div>', [46, 34], 'mk-hero-wrap'),
        interactive: false, zIndexOffset: 1000,
      }).addTo(mJobs);
      // 主角造型：玩家綁的 DC 造型（沒登入就維持 🙂 佔位）
      Avatar.heroIconUrl('stand1', (url) => {
        if (!url || !heroMarker) return;
        const el = heroMarker.getElement();
        const slot = el && el.querySelector('.mk-doll-slot');
        if (!slot) return;
        const img = document.createElement('img');
        img.className = 'mk-doll';
        img.alt = '';
        img.decoding = 'async';
        img.onload = () => { slot.textContent = ''; slot.appendChild(img); };
        img.onerror = () => { img.remove(); };
        img.src = url;
      });
    } else {
      heroMarker.setLatLng([pos.lat, pos.lng]);
    }
    // 走路↔站立換動畫
    const wantPose = S.hero.moving ? 'walk1' : 'stand1';
    if (wantPose !== heroPose) {
      heroPose = wantPose;
      const el = heroMarker.getElement();
      const img = el && el.querySelector('.mk-doll');
      if (img) Avatar.heroIconUrl(wantPose, (url) => { if (url && img.isConnected) img.src = url; });
    }
    // V3.7.1 停步補間：鬆鍵急停 0.4s（走路維持 1s）；再走動由 sim 清 stopping
    const hel = heroMarker && heroMarker.getElement();
    if (hel) {
      // v0.5.4：hero-offroad 兩處都 toggle——heroGlideTick 每幀（前台即時）＋這裡每秒（後台/headless 後備，就地判定不依賴 rAF 寫入的旗標）
      const nr = (typeof nearestNetNode === 'function') ? nearestNetNode(pos.lat, pos.lng) : null;
      const offNow = !nr || Math.hypot(nr.lat - pos.lat, nr.lng - pos.lng) > OFFROAD_DIST;
      hel.classList.toggle('hero-offroad', offNow);
      hel.classList.toggle('hero-stopping', !!S.hero.stopping && !S.hero.moving);
    }
  }

  // ===== V3.6-A 互動地標（POI）：marker 常駐，主角走近才浮出「進去看看？」 =====
  const poiMarkers = {};
  function renderPois() {
    if (!map) return;
    const list = (typeof Sim.poiList === 'function') ? Sim.poiList() : [];
    for (const p of list) {
      let mk = poiMarkers[p.id];
      if (!mk) {
        mk = L.marker([p.lat, p.lng], {
          zIndexOffset: 500,   // 名牌壓過巡查車（預設 0），避免巡邏圖示蓋住地標名
          icon: divIcon(
            `<div class="mk-poi"><span class="poi-ic">${p.icon}</span><span class="poi-nm">${p.name}</span>` +
            `<button class="poi-enter">🚪 進去看看？</button></div>`,
            [104, 30], 'mk-poi-wrap'
          ),
        }).addTo(mPoi);
        mk.on('click', () => { if (cb.poiClick) cb.poiClick(p.id); });
        poiMarkers[p.id] = mk;
      } else {
        mk.setLatLng([p.lat, p.lng]);
      }
    }
  }
  // 距離檢查：主角在 POI 附近 → 顯示按鈕；走遠或冷卻中 → 收起
  function updatePoiButtons() {
    if (!map || !poiMarkers) return;
    const S = Sim.state();
    if (!S || !S.hero) return;
    const near = (typeof Sim.poiNearHero === 'function') ? Sim.poiNearHero() : null;
    for (const id in poiMarkers) {
      const el = poiMarkers[id].getElement();
      if (!el) continue;
      const btn = el.querySelector('.poi-enter');
      if (!btn) continue;
      const show = !!near && near.id === id;
      if (show) btn.classList.remove('hidden'); else btn.classList.add('hidden');
    }
  }

  // ===== V3.7 貼近模式（immersion）：主角進入任務點/POI 互動半徑 → zoom 17＋收 UI；
  // 離開半徑 → 回 zoom 14、UI 回來。純 zoom/UI 切換，不是第二場景 =====
  let immersive = false, immersiveOrigin = null;
  const IMMERSE_ZOOM = 17, WANDER_ZOOM = 14;
  function immersionTick() {
    if (!map) return;
    const S = Sim.state();
    if (!S || !S.hero) return;
    // 目標清單：任務釘＋POI（跟查崗/互動同一組半徑語意，用較寬的進場半徑）
    let near = false;
    const pos = S.hero.pos;
    for (const m of S.missions) {
      if (Math.hypot(m.lat - pos.lat, m.lng - pos.lng) < 0.0016) { near = true; break; }
    }
    if (!near && typeof Sim.poiNearHero === 'function') {
      const p = Sim.poiNearHero();
      if (p) near = true;
    }
    if (near && !immersive) {
      immersive = true;
      immersiveOrigin = { lat: pos.lat, lng: pos.lng };   // v0.3.1 逃生閥：記錄進入點
      document.body.classList.add('immersed');
      // V3.7.1：UI 收合改 inline style 直接寫——CSS class 組 transition 在某些環境下
      // 過渡凍結（computed 恆 1），inline 是任何環境都生效的路；視覺靠 CSS transition 平滑
      setUiDim(true);
      // 跟隨權：只在「玩家沒有主動拖開鏡頭」時跟回主角（尊重拖曳暫停跟隨）
      if (followHero) map.flyTo([pos.lat, pos.lng], IMMERSE_ZOOM, { duration: 1.1 });
    } else if (immersive && (!near || Math.hypot(pos.lat - immersiveOrigin.lat, pos.lng - immersiveOrigin.lng) > 0.02)) {
      // 逃生閥：離所有目標半徑之外，或離「進入點」超過 2.2km（near 判定異常撐住時強制解除）
      immersive = false;
      document.body.classList.remove('immersed');
      setUiDim(false);
      map.flyTo([pos.lat, pos.lng], WANDER_ZOOM, { duration: 1.1 });
    }
  }
  // V3.7.1：HUD/名冊淡入淡出（inline opacity；transition 交給既有 CSS 規則）
  function setUiDim(dim) {
    const hud = document.getElementById('hud');
    const roster = document.getElementById('roster');
    if (hud) hud.style.opacity = dim ? '0.08' : '';
    if (roster) roster.style.opacity = dim ? '0' : '';
    if (hud) hud.style.pointerEvents = dim ? 'none' : '';
    if (roster) roster.style.pointerEvents = dim ? 'none' : '';
  }
  function raidAssembly(on) {
    if (!map) return;
    clearRaid();
    if (!on) return;
    const n = 7;
    for (let i = 0; i < n; i++) {
      const ang = (i / n) * Math.PI * 2 + Math.random() * 0.6;
      const dist = 0.02 + Math.random() * 0.012;
      const mk = L.marker([HQ.lat + Math.sin(ang) * dist, HQ.lng + Math.cos(ang) * dist * 1.25], {
        icon: divIcon('🚓', [24, 24], 'raid-cop-wrap'), interactive: false,
      }).addTo(mRaid);
      raidCars.push(mk);
      // 下一拍 setLatLng 一次到位，CSS transition 補間 1.8 秒慢慢圍上來
      const to = [HQ.lat + Math.sin(ang) * 0.0014, HQ.lng + Math.cos(ang) * 0.0014];
      setTimeout(() => { try { mk.setLatLng(to); } catch (e) {} }, 80);
    }
  }
  function clearRaid() {
    raidCars.forEach((m) => { try { mRaid.removeLayer(m); } catch (e) {} });
    raidCars = [];
  }

  function flyTo(lat, lng, z) {
    if (!map) return;
    // 沒指定 zoom → 至少拉近到 13（看任務）；有指定就用指定的（進場用 12 看全區）
    const target = z !== undefined ? z : Math.max(map.getZoom(), 13);
    // 地圖容器剛建好、尺寸未就緒時 flyTo 內部 pointToLatLng 會算出 NaN——退回 setView
    const size = map.getSize();
    if (!size.x || !size.y || !isFinite(size.x) || !isFinite(size.y)) {
      map.setView([lat, lng], Math.max(target, 8));
      return;
    }
    try {
      map.flyTo([lat, lng], Math.max(target, 8), { duration: 0.8 });
    } catch (e) {
      map.setView([lat, lng], Math.max(target, 8));
    }
  }
  function getCenter() {
    if (!map) return { lat: HQ.lat, lng: HQ.lng };
    const c = map.getCenter();
    return { lat: c.lat, lng: c.lng };
  }
  // 驗證／除錯用：目前畫面上所有警車的經緯度
  function copPositions() {
    return mPolice ? mPolice.getLayers().map((l) => l.getLatLng()) : [];
  }

  // ===== V3.5：鍵盤操控主角＋鏡頭跟隨 =====
  const KEYMAP = {
    ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
    KeyW: 'up', KeyS: 'down', KeyA: 'left', KeyD: 'right',
  };
  let followHero = true;  // 進遊戲後鏡頭跟著主角；玩家手動拖地圖就暫時放開
  function bindKeys() {
    document.addEventListener('keydown', (e) => {
      if (e.repeat) return;
      const dir = KEYMAP[e.code];
      if (!dir) return;
      const tag = (document.activeElement && document.activeElement.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;  // 別搶輸入框
      e.preventDefault();  // 防頁面滾動
      Sim.setKey(dir, true);
      followHero = true;
    });
    document.addEventListener('keyup', (e) => {
      const dir = KEYMAP[e.code];
      if (dir) Sim.setKey(dir, false);
      // v0.3.2 急停時序修正：不看 S.hero.moving（它要等下一個 heroTick 才翻 false，
      // keyup 當下恆 true → 急停分支永遠跳過＝1.8 秒滑尾）。改查「還有沒有其他鍵按著」——
      // Sim.setKey(false) 剛跑完，keys 全空才算停。
      const othersDown = ['up', 'down', 'left', 'right'].some((d) => Sim.isKeyDown(d));
      const S = Sim.state();
      if (heroMarker && !othersDown && S && S.hero) {
        const el = heroMarker.getElement();
        if (el) el.style.transition = 'none';
        heroMarker.setLatLng([S.hero.pos.lat, S.hero.pos.lng]);
        // v0.5.1 順序修正：hero-stopping class 必須在 transition='' 還原「之前」加——
        // 原順序先還原（此時 stylesheet 還是 1s linear）再加 class，A→B 跳轉被 1s 補間＝急停失效
        el.classList.add('hero-stopping');
        el.style.transition = '';
      }
    });
    // 拖動地圖＝暫停跟隨（點主角鍵會再啟動）
    map.on('dragstart', () => { followHero = false; });
  }
  // v0.5.2 鏡頭跟隨平滑化：每秒一次 panTo(硬跳) 會把 marker pane 整個位移——
  // 主角 marker 的 CSS transition 被大跳打斷（使用者實測「地圖一頓一頓＋一次噴一大格」）。
  // 改 rAF 連續跟隨：每幀鏡頭往主角方向推 8%，鏡頭與 marker 都連續
  let rafFollow = null;
  function followTick() {
    if (!map || !followHero) {
      if (rafFollow) { cancelAnimationFrame(rafFollow); rafFollow = null; }
      return;
    }
    if (rafFollow) return;   // 已有 rAF 迴圈在跑
    const step = () => {
      const S = Sim.state();
      if (!map || !followHero || !S || !S.hero) { rafFollow = null; return; }
      const h = S.hero.pos;
      const c = map.getCenter();
      const dLat = h.lat - c.lat, dLng = h.lng - c.lng;
      if (Math.abs(dLat) > 0.0001 || Math.abs(dLng) > 0.0001) {
        map.setView([c.lat + dLat * 0.08, c.lng + dLng * 0.08], map.getZoom(), { animate: false });
      }
      rafFollow = requestAnimationFrame(step);
    };
    rafFollow = requestAnimationFrame(step);
  }

  // ===== v0.6 熱線單：路線高亮 polyline＋取件/交付 pill（hotline-spec §3/§6） =====
  // 未走段＝虛線青（霓虹，光源＝儀表進行中）；已走過＝實線暗灰變淡。每秒找主角最近的
  // 路線節點切分走過/未走，索引不變不重畫。
  let hlLineRem = null, hlLineWalk = null, hlPillUp = null, hlPillDrop = null, hlWalkIdx = -1;
  function renderHotline(route) {
    if (!map) return;
    clearHotline();
    hlWalkIdx = -1;
    if (!route || !route.nodes || !route.nodes.length) return;
    hlLineRem = L.polyline(route.nodes, { className: 'hotline-route', interactive: false, weight: 3 }).addTo(mHl);
    const up = route.pickup, dp = route.drop;
    if (up) {
      hlPillUp = L.marker([up.lat, up.lng], {
        icon: divIcon('<div class="mk-hl">📦<span>取件</span></div>', [58, 24]), zIndexOffset: 500,
      }).addTo(mHl);
    }
    if (dp) {
      hlPillDrop = L.marker([dp.lat, dp.lng], {
        icon: divIcon('<div class="mk-hl drop">🏁<span>交付</span></div>', [58, 24]), zIndexOffset: 500,
      }).addTo(mHl);
    }
  }
  function clearHotline() {
    [hlLineRem, hlLineWalk, hlPillUp, hlPillDrop].forEach((l) => { if (l) { try { mHl.removeLayer(l); } catch (e) {} } });
    hlLineRem = hlLineWalk = hlPillUp = hlPillDrop = null;
    hlWalkIdx = -1;
  }
  function hotlineProgress() {
    if (!map || !hlLineRem) return;
    const S = Sim.state();
    if (!S || !S.hero) return;
    const nodes = hlLineRem.getLatLngs();
    const h = S.hero.pos;
    let best = -1, bestD = Infinity;
    for (let i = 0; i < nodes.length; i++) {
      const d = Math.hypot(nodes[i].lat - h.lat, nodes[i].lng - h.lng);
      if (d < bestD) { bestD = d; best = i; }
    }
    if (best === hlWalkIdx) return;
    hlWalkIdx = best;
    // 重切分：走過＝實線暗灰、未走＝虛線青
    const walked = nodes.slice(0, best + 1);
    const rest = nodes.slice(best);
    if (hlLineWalk) { try { mHl.removeLayer(hlLineWalk); } catch (e) {} }
    hlLineWalk = walked.length > 1
      ? L.polyline(walked, { className: 'hotline-walked', interactive: false }).addTo(mHl)
      : null;
    try { mHl.removeLayer(hlLineRem); } catch (e) {}
    hlLineRem = rest.length > 1
      ? L.polyline(rest, { className: 'hotline-route', interactive: false, weight: 3 }).addTo(mHl)
      : null;
  }

  return { init, refreshPolice, tickCops, renderTurf, renderAct2, renderMissions, renderJobs, renderBuildings, raidAssembly, clearRaid, flyTo, getCenter, copPositions, bindKeys, followTick, renderHero, renderPois, updatePoiButtons, immersionTick, heroGlideTick, renderHotline, clearHotline, hotlineProgress, cb };
})();
