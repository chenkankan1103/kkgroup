'use strict';
/* map.js — Leaflet 暗色台灣地圖：瓦片串流、警察 NPC 經緯度偽隨機、任務/派遣標記 */

const GameMap = (() => {
  let map = null;
  let mMissions, mJobs, mPolice, mHQ, mBuild, mRaid, mTurf, mAct2;
  const cb = {}; // 對外回呼：missionClick
  const jobMarkers = {}; // memId -> marker（不重建，才能用 CSS transition 平滑走路）

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
      zoomControl: true, minZoom: 8, maxZoom: 16,
      maxBounds: TW.bounds, maxBoundsViscosity: 0.8,
    });
    map.setView(TW.center, TW.zoom);
    L.tileLayer('https://services.arcgisonline.com/arcgis/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 16,
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

  function refreshPolice() {
    if (!map) return;
    mPolice.clearLayers();
    copsLive = [];
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
        for (let k = 0; k < 2; k++) {
          if (hash3(cx, cy, 7 + k) < dens2 * 0.45) {
            const e = pts[(hash3(cx, cy * 3 + k, 11) * pts.length) | 0];
            const dir = hash3(cx * 3 + k, cy, 29) < 0.5 ? 1 : -1;
            const t = Sim.gameMin();
            const mk = L.marker(copPos(e.c, e.i, dir, t), { icon: divIcon('🚔', [20, 20], 'cop-icon'), interactive: false }).addTo(mPolice);
            copsLive.push({ mk, ci: e.c, i0: e.i, dir });
            n++;
          }
        }
      }
    }
  }

  // 每 5 遊戲分鐘（5 真實秒）把可視警車的目標推進到 5 分鐘後的位置，CSS 補間滑過去
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
  function renderJobs(jobs, members) {
    if (!map) return;
    for (const id in jobMarkers) {
      if (!jobs[id]) { mJobs.removeLayer(jobMarkers[id]); delete jobMarkers[id]; }
    }
    for (const id in jobs) {
      const j = jobs[id];
      const mem = members.find((m) => m.id === id);
      if (!mem || !j.pos) continue;
      const emoji = j.leg === 'work' ? '📍' : '🛵';
      const moving = j.leg !== 'work';
      if (!jobMarkers[id]) {
        const mk = L.marker([j.pos.lat, j.pos.lng], {
          icon: divIcon(`<div class="mk-job">${mem.avatar}<i>${emoji}</i></div>`, [34, 26], 'mk-job-wrap'),
          interactive: false,
        }).addTo(mJobs);
        jobMarkers[id] = mk;
      } else {
        jobMarkers[id].setLatLng([j.pos.lat, j.pos.lng]);
        const el = jobMarkers[id].getElement();
        if (el) {
          el.classList.toggle('mv', moving);
          const ic = el.querySelector('.mk-job i');
          if (ic) ic.textContent = emoji;
        }
      }
    }
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

  return { init, refreshPolice, tickCops, renderTurf, renderAct2, renderMissions, renderJobs, renderBuildings, raidAssembly, clearRaid, flyTo, getCenter, copPositions, cb };
})();
