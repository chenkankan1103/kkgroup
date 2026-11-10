'use strict';
/* map.js — Leaflet 暗色台灣地圖：瓦片串流、警察 NPC 經緯度偽隨機、任務/派遣標記 */

const GameMap = (() => {
  let map = null;
  let mMissions, mJobs, mPolice, mHQ, mBuild;
  const cb = {}; // 對外回呼：missionClick
  const jobMarkers = {}; // memId -> marker（不重建，才能用 CSS transition 平滑走路）

  // 台灣本島粗略輪廓（只拿來擋掉海面上的警察點）
  const TW_POLY = [
    [25.30, 121.55], [25.05, 121.90], [24.90, 121.82], [24.60, 121.85], [24.20, 121.75],
    [23.85, 121.60], [23.50, 121.50], [23.10, 121.65], [22.85, 121.35], [22.60, 121.00],
    [22.40, 120.70], [22.20, 120.35], [22.00, 120.15], [21.95, 120.10], [22.25, 120.05],
    [22.55, 120.20], [22.80, 120.25], [23.10, 120.05], [23.35, 120.10], [23.65, 120.05],
    [23.85, 120.15], [24.15, 120.35], [24.45, 120.55], [24.75, 120.75],
    [25.00, 121.00], [25.15, 121.25],
  ];
  function inTW(lat, lng) {
    let inside = false;
    for (let i = 0, j = TW_POLY.length - 1; i < TW_POLY.length; j = i++) {
      const yi = TW_POLY[i][0], xi = TW_POLY[i][1];
      const yj = TW_POLY[j][0], xj = TW_POLY[j][1];
      if (((yi > lat) !== (yj > lat)) && (lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi)) inside = !inside;
    }
    return inside;
  }

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

    L.marker([HQ.lat, HQ.lng], {
      icon: divIcon('<div class="mk-hq">🏢<span>園區總部</span></div>', [76, 26]),
    }).addTo(mHQ);

    map.on('moveend zoomend', refreshPolice);
    refreshPolice();
  }

  // ===== 警察 NPC：格子當種子，zoom ≥ 12 才現身 =====
  // 不跑位的關鍵：位置與存在都由固定 400m 格決定，時段只調整數量門檻——
  // 同一格的車永遠停在同一點，深夜變少、白天變多，只會出現/消失，不會瞬移。
  // 低倍率只顯示固定格點的子集（zoom 12 每 4 格取 1、13 每 2 格取 1、14+ 全顯）。
  function refreshPolice() {
    if (!map) return;
    mPolice.clearLayers();
    const z = map.getZoom();
    if (z < 12) return;
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
        if (!inTW(cy * CELL, cx * CELL)) continue;
        for (let k = 0; k < 2; k++) {
          if (hash3(cx, cy, 7 + k) < dens * 0.45) {
            const lat2 = (cy + hash3(cx, cy * 3 + k, 11)) * CELL;
            const lng2 = (cx + hash3(cx * 3 + k, cy, 23)) * CELL;
            L.marker([lat2, lng2], { icon: divIcon('🚔', [20, 20], 'cop-icon'), interactive: false }).addTo(mPolice);
            n++;
          }
        }
      }
    }
  }

  // ===== 任務標記 =====
  function renderMissions(missions) {
    if (!map) return;
    mMissions.clearLayers();
    for (const m of missions) {
      const hot = m.risk >= 0.5 ? ' hot' : '';
      const mk = L.marker([m.lat, m.lng], {
        icon: divIcon(`<div class="mk-mis${hot}">${MISSION_TYPES[m.type].icon}<span>${m.code}</span></div>`, [64, 26]),
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

  function flyTo(lat, lng, z) {
    if (!map) return;
    // 沒指定 zoom → 至少拉近到 13（看任務）；有指定就用指定的（進場用 12 看全區）
    const target = z !== undefined ? z : Math.max(map.getZoom(), 13);
    map.flyTo([lat, lng], Math.max(target, 8), { duration: 0.8 });
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

  return { init, refreshPolice, renderMissions, renderJobs, renderBuildings, flyTo, getCenter, copPositions, cb };
})();
