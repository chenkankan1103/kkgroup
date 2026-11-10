'use strict';
/* game.js — 主循環：狀態機、玩家、敵潮、武器、撿拾、升級、相機與渲染 */

const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d');
const RECORD_KEY = 'kkpark_survival_best';

let dpr = 1, VW = 0, VH = 0;
function resize() {
  VW = innerWidth;
  VH = innerHeight;
  dpr = Math.min(2, devicePixelRatio || 1);
  canvas.width = VW * dpr;
  canvas.height = VH * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

/* ===== 全域狀態 ===== */
const G = {
  state: 'menu', time: 0, kills: 0, gold: 0,
  level: 1, xp: 0, xpNeed: nextXP(1), pendingLevelups: 0,
  player: null, camX: 0, camY: 0, shake: 0,
  enemies: [], bullets: [], rings: [], beams: [],
  gems: [], golds: [], chests: [],
  spawnTimer: 0, bossesSpawned: {},
  weapons: {}, passives: {},
};

/* 音效節流（敵潮量大時防炸裂） */
let hitSfxT = 0, killSfxT = 0, pickSfxT = 0;

/* ===== 輸入 ===== */
const keys = new Set();
addEventListener('keydown', (e) => {
  const k = e.key.toLowerCase();
  if (k === 'escape') { togglePause(); return; }
  if (['arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' '].includes(k)) e.preventDefault();
  keys.add(k);
});
addEventListener('keyup', (e) => keys.delete(e.key.toLowerCase()));

/* ===== 數值輔助 ===== */
const passLv = (k) => G.passives[k] || 0;
const dmgMul = () => 1 + passLv('dmg') * 0.1;
const cdMul = () => 1 - passLv('cd') * 0.07;
const xpMul = () => 1 + passLv('xp') * 0.1;

function recalcStats() {
  const p = G.player;
  p.maxHp = PLAYER_BASE.hp + passLv('hp') * 20;
  p.speed = PLAYER_BASE.speed * (1 + passLv('speed') * 0.08);
  p.pickup = PLAYER_BASE.pickup * (1 + passLv('pickup') * 0.25);
  p.hp = Math.min(p.hp, p.maxHp);
}

/* ===== 紀錄 ===== */
function loadRecord() {
  try { return JSON.parse(localStorage.getItem(RECORD_KEY)) || null; } catch (e) { return null; }
}
function saveRecord() {
  const old = loadRecord();
  const isNew = !old || G.kills > old.kills;
  if (isNew) {
    try {
      localStorage.setItem(RECORD_KEY, JSON.stringify({ kills: G.kills, level: G.level, time: Math.floor(G.time) }));
    } catch (e) { /* 私密模式等，忽略 */ }
  }
  return isNew;
}

/* ===== 開局 ===== */
function resetRun() {
  G.state = 'playing';
  G.time = 0; G.kills = 0; G.gold = 0;
  G.level = 1; G.xp = 0; G.xpNeed = nextXP(1); G.pendingLevelups = 0;
  G.player = {
    x: 0, y: 0, hp: 100, maxHp: 100,
    speed: PLAYER_BASE.speed, pickup: PLAYER_BASE.pickup,
    iframes: 0, face: 1, bobT: 0,
  };
  G.camX = 0; G.camY = 0; G.shake = 0;
  G.enemies = []; G.bullets = []; G.rings = []; G.beams = [];
  G.gems = []; G.golds = []; G.chests = [];
  G.spawnTimer = 0.5; G.bossesSpawned = {};
  G.weapons = { dart: { lv: 1, evolved: false, cd: 0, angle: 0 } };
  G.passives = {};
  UI.showGame();
  refreshChips();
  UI.updateHud(G);
}

/* ===== 玩家移動（鍵盤＋搖桿） ===== */
function playerMove(dt) {
  const p = G.player, j = UI.joy;
  let dx = 0, dy = 0;
  if (keys.has('a') || keys.has('arrowleft')) dx -= 1;
  if (keys.has('d') || keys.has('arrowright')) dx += 1;
  if (keys.has('w') || keys.has('arrowup')) dy -= 1;
  if (keys.has('s') || keys.has('arrowdown')) dy += 1;
  dx += j.dx; dy += j.dy;
  const len = Math.hypot(dx, dy);
  if (len > 1) { dx /= len; dy /= len; }
  if (len > 0.01) {
    p.x += dx * p.speed * dt;
    p.y += dy * p.speed * dt;
    if (dx < -0.05) p.face = -1; else if (dx > 0.05) p.face = 1;
  }
  p.bobT += dt * 10;
}

/* ===== 生成 ===== */
function currentWave() {
  let w = WAVES[0];
  for (const v of WAVES) if (G.time >= v.t) w = v;
  return w;
}
function pickFromPool(pool) {
  let total = 0;
  for (const k in pool) total += pool[k];
  let r = Math.random() * total;
  for (const k in pool) { r -= pool[k]; if (r <= 0) return k; }
  return Object.keys(pool)[0];
}

const TINT_CACHE = {};
function spawnEnemy(key) {
  if (G.enemies.length >= MAX_ENEMIES) return;
  const def = ENEMIES[key];
  let img = null;
  if (def.tint) {
    if (!TINT_CACHE[key]) TINT_CACHE[key] = makeTinted(def.sprite, def.tint);
    img = TINT_CACHE[key];
  }
  const dist = Math.max(VW, VH) / 2 + 60;
  const a = Math.random() * Math.PI * 2;
  G.enemies.push({
    key,
    x: G.player.x + Math.cos(a) * dist, y: G.player.y + Math.sin(a) * dist,
    hp: def.hp, maxHp: def.hp, spd: def.spd, dmg: def.dmg, xp: def.xp,
    scale: def.scale, radius: def.radius, sprite: def.sprite, img,
    elite: !!def.elite, boss: def.boss || null,
    dead: false, kx: 0, ky: 0, orbitCd: 0,
  });
}

function updateSpawns(dt) {
  const wave = currentWave();
  G.spawnTimer -= dt;
  if (G.spawnTimer <= 0) {
    G.spawnTimer = wave.interval;
    for (let i = 0; i < wave.burst; i++) spawnEnemy(pickFromPool(wave.pool));
  }
  if (wave.elite && Math.random() < dt / 30) spawnEnemy('elite'); // 約 30 秒一隻
  for (const b of BOSS_TIMES) {
    if (G.time >= b.t && !G.bossesSpawned[b.t]) {
      G.bossesSpawned[b.t] = true;
      spawnEnemy(b.key);
      Sfx.boss();
    }
  }
  let boss = null;
  for (const e of G.enemies) {
    if (e.boss && !e.dead) { boss = e; break; }
  }
  UI.updateBoss(boss ? { name: boss.boss, hp: boss.hp, maxHp: boss.maxHp } : null);
}

/* ===== 敵人 ===== */
function updateEnemies(dt) {
  const p = G.player;
  for (const e of G.enemies) {
    if (e.dead) continue;
    const dx = p.x - e.x, dy = p.y - e.y;
    const d = Math.hypot(dx, dy) || 1;
    e.x += ((dx / d) * e.spd + e.kx) * dt;
    e.y += ((dy / d) * e.spd + e.ky) * dt;
    e.kx *= Math.max(0, 1 - 6 * dt);
    e.ky *= Math.max(0, 1 - 6 * dt);
    if (e.orbitCd > 0) e.orbitCd -= dt;
    if (d < e.radius + 12 && p.iframes <= 0) {
      p.hp -= e.dmg;
      p.iframes = PLAYER_BASE.iframes;
      G.shake = Math.min(12, G.shake + 6);
      Sfx.hurt();
      floatAt(p.x, p.y - 20, '-' + e.dmg, 'hurt');
      if (p.hp <= 0) { gameOver(false); return; }
    }
  }
}

function nearestEnemies(n) {
  const p = G.player;
  const arr = G.enemies.filter((e) => !e.dead);
  arr.sort((a, b) => {
    const da = (a.x - p.x) * (a.x - p.x) + (a.y - p.y) * (a.y - p.y);
    const db = (b.x - p.x) * (b.x - p.x) + (b.y - p.y) * (b.y - p.y);
    return da - db;
  });
  return arr.slice(0, n);
}

/* ===== 武器 ===== */
function updateWeapons(dt) {
  const p = G.player;
  const dm = dmgMul(), cm = cdMul();
  for (const [id, w] of Object.entries(G.weapons)) {
    const st = WEAPONS[id].lv[w.lv - 1];
    if (id === 'dart') {
      w.cd -= dt;
      if (w.cd > 0) continue;
      const count = st.count + (w.evolved ? 2 : 0);
      const targets = nearestEnemies(count);
      if (!targets.length) continue; // 沒目標就等（不重置冷卻）
      w.cd = st.cd * cm;
      const dmg = st.dmg * dm * (w.evolved ? 2 : 1);
      for (const t of targets) {
        G.bullets.push({
          x: p.x, y: p.y,
          ang: Math.atan2(t.y - p.y, t.x - p.x),
          spd: st.spd, dmg, life: 2,
          homing: w.evolved, target: t,
        });
      }
      Sfx.shoot();
    } else if (id === 'glowstick') {
      // 常駐軌道武器：無冷卻，只旋轉＋碰撞
      w.angle += st.spd * dt;
      const n = st.n * (w.evolved ? 2 : 1);
      const size = st.size * (w.evolved ? 1.6 : 1);
      for (let i = 0; i < n; i++) {
        const a = w.angle + (i / n) * Math.PI * 2;
        const gx = p.x + Math.cos(a) * st.r;
        const gy = p.y + Math.sin(a) * st.r;
        for (const e of G.enemies) {
          if (e.dead || e.orbitCd > 0) continue;
          if (Math.hypot(e.x - gx, e.y - gy) < e.radius + 14 * size) {
            damageEnemy(e, st.dmg * dm, false);
            e.orbitCd = 0.4;
          }
        }
      }
    } else if (id === 'sonic') {
      w.cd -= dt;
      if (w.cd > 0) continue;
      w.cd = st.cd * cm;
      G.rings.push({
        x: p.x, y: p.y, r: 8,
        maxR: st.r * (w.evolved ? 1.4 : 1),
        dmg: st.dmg * dm,
        knock: st.knock * (w.evolved ? 1.5 : 1),
        hit: new Set(),
      });
      Sfx.hit();
    } else if (id === 'laser') {
      w.cd -= dt;
      if (w.cd > 0) continue;
      const t = nearestEnemies(1)[0];
      if (!t) continue; // 沒目標就等
      w.cd = st.cd * cm;
      const dmg = st.dmg * dm * (w.evolved ? 1.8 : 1);
      const ang = Math.atan2(t.y - p.y, t.x - p.x);
      const angles = w.evolved ? [ang, ang + Math.PI] : [ang];
      for (const a of angles) {
        G.beams.push({ x: p.x, y: p.y, ang: a, len: st.len, w: st.w, dmg, life: 0.12, hit: new Set() });
      }
    }
  }
}

/* ===== 子彈／光束／音波 ===== */
function updateBullets(dt) {
  for (const b of G.bullets) {
    if (b.homing && b.target && !b.target.dead) {
      b.ang = Math.atan2(b.target.y - b.y, b.target.x - b.x);
    }
    b.x += Math.cos(b.ang) * b.spd * dt;
    b.y += Math.sin(b.ang) * b.spd * dt;
    b.life -= dt;
    if (b.life <= 0) continue;
    for (const e of G.enemies) {
      if (e.dead) continue;
      if (Math.hypot(e.x - b.x, e.y - b.y) < e.radius + 8) {
        damageEnemy(e, b.dmg, true);
        b.life = 0;
        break;
      }
    }
  }
  G.bullets = G.bullets.filter((b) => b.life > 0);
}

function distToSegment(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay;
  const l2 = dx * dx + dy * dy;
  if (!l2) return Math.hypot(px - ax, py - ay);
  let t = ((px - ax) * dx + (py - ay) * dy) / l2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function updateBeams(dt) {
  for (const b of G.beams) {
    b.life -= dt;
    if (b.life <= 0) continue;
    const ex = b.x + Math.cos(b.ang) * b.len;
    const ey = b.y + Math.sin(b.ang) * b.len;
    for (const e of G.enemies) {
      if (e.dead || b.hit.has(e)) continue;
      if (distToSegment(e.x, e.y, b.x, b.y, ex, ey) < e.radius + b.w) {
        b.hit.add(e);
        damageEnemy(e, b.dmg, true);
      }
    }
  }
  G.beams = G.beams.filter((b) => b.life > 0);
}

function updateRings(dt) {
  for (const r of G.rings) {
    r.r += 320 * dt;
    for (const e of G.enemies) {
      if (e.dead || r.hit.has(e)) continue;
      const d = Math.hypot(e.x - r.x, e.y - r.y);
      if (d < r.r && d > r.r - 40) {
        r.hit.add(e);
        const a = Math.atan2(e.y - r.y, e.x - r.x);
        e.kx += Math.cos(a) * r.knock;
        e.ky += Math.sin(a) * r.knock;
        damageEnemy(e, r.dmg, true);
      }
    }
  }
  G.rings = G.rings.filter((r) => r.r < r.maxR);
}

/* ===== 傷害與擊殺 ===== */
function damageEnemy(e, dmg, float = false) {
  if (e.dead) return; // 防同幀重複擊殺
  e.hp -= dmg;
  if (e.hp <= 0) {
    floatAt(e.x, e.y - e.radius - 10, Math.round(dmg) + '', 'crit');
    killEnemy(e);
    return;
  }
  if (e.elite || e.boss || float) {
    floatAt(e.x, e.y - e.radius - 10, Math.round(dmg) + '', '');
  }
  if (hitSfxT <= 0 && Math.random() < 0.4) {
    Sfx.hit();
    hitSfxT = 0.08;
  }
}

function killEnemy(e) {
  G.kills++;
  e.dead = true;
  if (e.boss || e.elite || killSfxT <= 0) { Sfx.kill(); killSfxT = 0.15; }
  // 經驗寶石
  const n = e.boss ? 20 : e.elite ? 8 : 1;
  for (let i = 0; i < n; i++) {
    const a = Math.random() * Math.PI * 2;
    const d = n > 1 ? 6 + Math.random() * 30 : 0;
    G.gems.push({ x: e.x + Math.cos(a) * d, y: e.y + Math.sin(a) * d, v: Math.max(1, Math.ceil(e.xp / n)) });
  }
  // 金幣與寶箱
  if (e.boss) {
    for (let i = 0; i < 30; i++) {
      const a = Math.random() * Math.PI * 2, d = 8 + Math.random() * 54;
      G.golds.push({ x: e.x + Math.cos(a) * d, y: e.y + Math.sin(a) * d, v: 1 });
    }
  } else if (e.elite) {
    for (let i = 0; i < 12; i++) {
      const a = Math.random() * Math.PI * 2, d = 8 + Math.random() * 40;
      G.golds.push({ x: e.x + Math.cos(a) * d, y: e.y + Math.sin(a) * d, v: 1 });
    }
    G.chests.push({ x: e.x, y: e.y });
  } else if (Math.random() < 0.12) {
    G.golds.push({ x: e.x, y: e.y, v: 1 + Math.floor(Math.random() * 3) });
  }
}

function sweepDead() {
  if (G.enemies.some((e) => e.dead)) G.enemies = G.enemies.filter((e) => !e.dead);
}

/* ===== 撿拾 ===== */
function updatePickups(dt) {
  const p = G.player;
  for (const g of G.gems) {
    const dx = p.x - g.x, dy = p.y - g.y;
    const d = Math.hypot(dx, dy);
    if (d < 16) {
      g.got = true;
      gainXP(g.v);
      if (pickSfxT <= 0) { Sfx.pickup(); pickSfxT = 0.06; }
      continue;
    }
    if (d < p.pickup) {
      const spd = 240 + (p.pickup - d) * 4;
      g.x += (dx / d) * spd * dt;
      g.y += (dy / d) * spd * dt;
    }
  }
  G.gems = G.gems.filter((g) => !g.got);
  while (G.gems.length > 300) gainXP(G.gems.shift().v); // 太遠沒撿到的自動吸收

  for (const g of G.golds) {
    const dx = p.x - g.x, dy = p.y - g.y;
    const d = Math.hypot(dx, dy);
    if (d < 14) {
      g.got = true;
      G.gold += g.v;
      Sfx.gold();
      floatAt(p.x, p.y - 24, '+' + g.v + ' 🪙', 'xp');
      continue;
    }
    if (d < p.pickup * 0.8) {
      g.x += (dx / (d || 1)) * 300 * dt;
      g.y += (dy / (d || 1)) * 300 * dt;
    }
  }
  G.golds = G.golds.filter((g) => !g.got);

  for (const c of G.chests) {
    if (Math.hypot(p.x - c.x, p.y - c.y) < 26) {
      G.chests.splice(G.chests.indexOf(c), 1);
      openChest();
      break;
    }
  }
}

/* ===== 經驗與升級 ===== */
function gainXP(v) {
  G.xp += v * xpMul();
  while (G.xp >= G.xpNeed) {
    G.xp -= G.xpNeed;
    G.level++;
    G.xpNeed = nextXP(G.level);
    G.pendingLevelups++;
  }
}

function openLevelup() {
  G.state = 'levelup';
  Sfx.levelup();
  UI.showLevelup(rollChoices(), (c) => {
    c.apply();
    G.pendingLevelups--;
    if (c.kind === 'weapon' || c.kind === 'evo') refreshChips();
    if (G.pendingLevelups > 0) openLevelup();
    else G.state = 'playing';
  });
}

function rollChoices() {
  const out = [];
  // 1) 進化（武器滿級＋對應被動滿級）
  for (const [id, w] of Object.entries(G.weapons)) {
    const data = WEAPONS[id];
    if (w.evolved || w.lv < data.lv.length) continue;
    if (passLv(data.evoWith) < 5) continue;
    out.push({
      kind: 'evo', icon: data.evoIcon, name: data.evoName,
      lvText: '進化！', desc: data.evoDesc,
      apply: () => { w.evolved = true; Sfx.evolve(); },
    });
  }
  // 2) 武器升級
  for (const [id, w] of Object.entries(G.weapons)) {
    const data = WEAPONS[id];
    if (w.evolved || w.lv >= data.lv.length) continue;
    out.push({
      kind: 'weapon', icon: data.icon, name: data.name,
      lvText: `Lv.${w.lv} → Lv.${w.lv + 1}`,
      desc: lvDeltaDesc(id, w.lv),
      apply: () => { w.lv++; },
    });
  }
  // 3) 新武器（最多 4 把）
  if (Object.keys(G.weapons).length < 4) {
    for (const id of Object.keys(WEAPONS)) {
      if (G.weapons[id]) continue;
      const data = WEAPONS[id];
      out.push({
        kind: 'weapon', icon: data.icon, name: data.name + '（新武器）',
        lvText: 'Lv.1', desc: data.desc,
        apply: () => { G.weapons[id] = { lv: 1, evolved: false, cd: 0, angle: Math.random() * Math.PI * 2 }; },
      });
    }
  }
  // 4) 被動
  for (const [k, pd] of Object.entries(PASSIVES)) {
    const lv = passLv(k);
    if (lv >= pd.max) continue;
    out.push({
      kind: 'passive', icon: pd.icon, name: pd.name,
      lvText: `Lv.${lv} → Lv.${lv + 1}`,
      desc: pd.desc,
      apply: () => {
        G.passives[k] = lv + 1;
        recalcStats();
        if (k === 'hp') G.player.hp = Math.min(G.player.maxHp, G.player.hp + 20);
      },
    });
  }
  // 洗牌取 3；不足補小蛋糕
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  const picked = out.slice(0, 3);
  while (picked.length < 3) {
    picked.push({
      kind: 'passive', icon: '🧁', name: '小蛋糕',
      lvText: '', desc: '回復 25 HP',
      apply: () => { G.player.hp = Math.min(G.player.maxHp, G.player.hp + 25); },
    });
  }
  return picked;
}

function lvDeltaDesc(id, curLv) {
  const a = WEAPONS[id].lv[curLv - 1], b = WEAPONS[id].lv[curLv];
  const parts = [];
  if (b.dmg > a.dmg) parts.push(`傷害 ${a.dmg}→${b.dmg}`);
  if (b.count > a.count) parts.push(`彈數 ${a.count}→${b.count}`);
  if (b.n > a.n) parts.push(`棒數 ${a.n}→${b.n}`);
  if (b.cd < a.cd) parts.push(`冷卻 ${a.cd.toFixed(1)}→${b.cd.toFixed(1)}s`);
  if (b.r > a.r) parts.push(`範圍 ${a.r}→${b.r}`);
  if (b.knock > a.knock) parts.push('擊退增強');
  if (b.len > a.len) parts.push(`長度 ${a.len}→${b.len}`);
  if (b.w > a.w) parts.push('變粗');
  if (b.size > a.size) parts.push('變大');
  if (b.spd > a.spd && id !== 'glowstick') parts.push(`彈速 ${a.spd}→${b.spd}`);
  return parts.join('、') || WEAPONS[id].desc;
}

function refreshChips() {
  UI.updateWeaponChips(Object.entries(G.weapons).map(([id, w]) => ({
    icon: w.evolved ? WEAPONS[id].evoIcon : WEAPONS[id].icon,
    name: w.evolved ? WEAPONS[id].evoName : WEAPONS[id].name,
    lv: w.lv, evolved: w.evolved,
  })));
}

/* ===== 寶箱 ===== */
function openChest() {
  G.state = 'chest';
  Sfx.chest();
  const bonusGold = 10 + Math.floor(Math.random() * 21);
  G.gold += bonusGold;
  const ups = [];
  for (const [id, w] of Object.entries(G.weapons)) {
    if (!w.evolved && w.lv < WEAPONS[id].lv.length) ups.push({ type: 'weapon', id });
  }
  for (const [k, pd] of Object.entries(PASSIVES)) {
    if (passLv(k) < pd.max) ups.push({ type: 'passive', id: k });
  }
  let text;
  if (ups.length) {
    const u = ups[Math.floor(Math.random() * ups.length)];
    if (u.type === 'weapon') {
      const w = G.weapons[u.id];
      w.lv++;
      text = `${WEAPONS[u.id].icon} ${WEAPONS[u.id].name} 升到 Lv.${w.lv}！`;
    } else {
      const pd = PASSIVES[u.id];
      G.passives[u.id] = passLv(u.id) + 1;
      recalcStats();
      G.player.hp = Math.min(G.player.maxHp, G.player.hp + 20);
      text = `${pd.icon} ${pd.name} 升到 Lv.${G.passives[u.id]}！`;
    }
  } else {
    G.gold += 40;
    text = '🎉 全部滿級！額外獲得 40 🪙';
  }
  UI.showChest(`${text}<small>另外撿到 ${bonusGold} 🪙</small>`, () => {
    G.state = 'playing';
    refreshChips();
  });
}

/* ===== 結束與暫停 ===== */
function gameOver(win) {
  if (G.state !== 'playing') return;
  G.state = win ? 'victory' : 'gameover';
  if (win) Sfx.win(); else Sfx.gameover();
  UI.updateBoss(null);
  const isNew = saveRecord();
  UI.showGameOver({ win, kills: G.kills, gold: G.gold, level: G.level, time: G.time, isNew });
}

function togglePause() {
  if (G.state === 'playing') {
    G.state = 'paused';
    const lines = [];
    for (const [id, w] of Object.entries(G.weapons)) {
      const d = WEAPONS[id];
      lines.push(`${w.evolved ? d.evoIcon : d.icon} <b>${w.evolved ? d.evoName : d.name}</b> Lv.${w.lv}${w.evolved ? ' ★進化' : ''}`);
    }
    for (const [k, lv] of Object.entries(G.passives)) {
      lines.push(`${PASSIVES[k].icon} ${PASSIVES[k].name} Lv.${lv}`);
    }
    UI.showPause(lines.join('<br>') || '還沒有裝備');
  } else if (G.state === 'paused') {
    UI.hidePause();
    G.state = 'playing';
  }
}

/* ===== 相機與飛字 ===== */
function updateCamera(dt) {
  const p = G.player;
  const k = 1 - Math.pow(0.0015, dt);
  G.camX += (p.x - G.camX) * k;
  G.camY += (p.y - G.camY) * k;
  G.shake *= Math.max(0, 1 - 8 * dt);
  if (G.shake < 0.1) G.shake = 0;
}

function floatAt(wx, wy, text, cls) {
  const sx = wx - G.camX + VW / 2;
  const sy = wy - G.camY + VH / 2;
  if (sx < -40 || sx > VW + 40 || sy < -40 || sy > VH + 40) return;
  UI.floatText(sx, sy, text, cls);
}

/* ===== 渲染 ===== */
function drawGrid() {
  const size = 64;
  ctx.strokeStyle = 'rgba(125,249,255,.06)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  const ox = (((-G.camX + VW / 2) % size) + size) % size;
  const oy = (((-G.camY + VH / 2) % size) + size) % size;
  for (let x = ox; x <= VW; x += size) { ctx.moveTo(x, 0); ctx.lineTo(x, VH); }
  for (let y = oy; y <= VH; y += size) { ctx.moveTo(0, y); ctx.lineTo(VW, y); }
  ctx.stroke();
}

function drawHpBar(e) {
  const w = Math.max(26, e.radius * 1.8);
  const spr = SPRITES[e.sprite];
  const top = e.y - (spr.height * e.scale) / 2 - 9;
  const frac = Math.max(0, e.hp / e.maxHp);
  ctx.fillStyle = 'rgba(0,0,0,.5)';
  ctx.fillRect(e.x - w / 2 - 1, top - 1, w + 2, 5);
  ctx.fillStyle = (e.boss || e.elite) ? '#ff4d6d' : '#3dff8f';
  ctx.fillRect(e.x - w / 2, top, w * frac, 3);
}

function render() {
  ctx.clearRect(0, 0, VW, VH);
  drawGrid();
  const shx = G.shake ? (Math.random() - 0.5) * G.shake : 0;
  const shy = G.shake ? (Math.random() - 0.5) * G.shake : 0;
  ctx.save();
  ctx.translate(VW / 2 - G.camX + shx, VH / 2 - G.camY + shy);
  const p = G.player;

  // 撿拾物
  for (const g of G.gems) drawSprite(ctx, 'gem', g.x, g.y, { scale: 3 });
  for (const g of G.golds) drawSprite(ctx, 'gold', g.x, g.y, { scale: 3 });
  for (const c of G.chests) drawSprite(ctx, 'chest', c.x, c.y, { scale: 4 });

  if (p) {
    // 敵人
    for (const e of G.enemies) {
      if (e.dead) continue;
      drawSprite(ctx, e.sprite, e.x, e.y, { scale: e.scale, flip: e.x > p.x, img: e.img });
      if (e.hp < e.maxHp) drawHpBar(e);
    }
    // 玩家（無敵幀閃爍＋走路上下擺動）
    if (!(p.iframes > 0 && Math.floor(p.iframes * 12) % 2 === 0)) {
      const bob = Math.sin(p.bobT) * 2;
      drawSprite(ctx, 'player', p.x, p.y + bob, { scale: 3, flip: p.face < 0 });
    }
    // 飛鏢
    for (const b of G.bullets) {
      drawSprite(ctx, 'dart', b.x, b.y, { scale: 3, rot: b.ang });
    }
    // 螢光棒軌道
    for (const [id, w] of Object.entries(G.weapons)) {
      if (id !== 'glowstick') continue;
      const st = WEAPONS.glowstick.lv[w.lv - 1];
      const n = st.n * (w.evolved ? 2 : 1);
      const size = st.size * (w.evolved ? 1.6 : 1);
      for (let i = 0; i < n; i++) {
        const a = w.angle + (i / n) * Math.PI * 2;
        drawSprite(ctx, 'glowstick', p.x + Math.cos(a) * st.r, p.y + Math.sin(a) * st.r, {
          scale: 3 * size, rot: a + Math.PI / 2,
        });
      }
    }
    // 音波環
    for (const r of G.rings) {
      ctx.strokeStyle = 'rgba(125,249,255,.8)';
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.arc(r.x, r.y, r.r, 0, Math.PI * 2);
      ctx.stroke();
    }
    // 雷射（黃條＋白芯）
    for (const b of G.beams) {
      const ex = b.x + Math.cos(b.ang) * b.len;
      const ey = b.y + Math.sin(b.ang) * b.len;
      ctx.lineCap = 'round';
      ctx.strokeStyle = 'rgba(255,225,77,.85)';
      ctx.lineWidth = b.w * 2;
      ctx.beginPath(); ctx.moveTo(b.x, b.y); ctx.lineTo(ex, ey); ctx.stroke();
      ctx.strokeStyle = 'rgba(255,255,255,.9)';
      ctx.lineWidth = b.w * 0.6;
      ctx.beginPath(); ctx.moveTo(b.x, b.y); ctx.lineTo(ex, ey); ctx.stroke();
    }
  }
  ctx.restore();

  // 低血量紅暈脈動
  if (p && G.player.hp / G.player.maxHp < 0.3 && (G.state === 'playing' || G.state === 'levelup')) {
    const a = 0.14 + Math.sin(G.time * 6) * 0.08;
    const grad = ctx.createRadialGradient(VW / 2, VH / 2, Math.min(VW, VH) * 0.35, VW / 2, VH / 2, Math.max(VW, VH) * 0.7);
    grad.addColorStop(0, 'rgba(255,77,109,0)');
    grad.addColorStop(1, `rgba(255,77,109,${a.toFixed(3)})`);
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, VW, VH);
  }
}

/* ===== 主循環 ===== */
let lastT = performance.now();
function loop(now) {
  requestAnimationFrame(loop);
  const dt = Math.min(0.05, (now - lastT) / 1000);
  lastT = now;
  hitSfxT = Math.max(0, hitSfxT - dt);
  killSfxT = Math.max(0, killSfxT - dt);
  pickSfxT = Math.max(0, pickSfxT - dt);

  if (G.state === 'playing' && G.player) {
    G.time += dt;
    playerMove(dt);
    updateSpawns(dt);
    updateEnemies(dt);
    if (G.state === 'playing') { // updateEnemies 可能觸發死亡
      updateWeapons(dt);
      updateBullets(dt);
      updateBeams(dt);
      updateRings(dt);
      updatePickups(dt);
      sweepDead();
      updateCamera(dt);
      if (G.player.iframes > 0) G.player.iframes = Math.max(0, G.player.iframes - dt);
      UI.updateHud(G);
      if (G.pendingLevelups > 0 && G.state === 'playing') openLevelup();
      if (G.state === 'playing' && G.time >= RUN_TIME) gameOver(true);
    }
  }
  render();
}

/* ===== 按鈕 ===== */
function bindButtons() {
  const $ = (id) => document.getElementById(id);
  $('btnStart').onclick = () => { Sfx.unlock(); resetRun(); };
  $('btnRetry').onclick = () => { Sfx.unlock(); resetRun(); };
  $('btnMenu').onclick = () => { G.state = 'menu'; UI.updateBoss(null); UI.showMenu(loadRecord()); };
  $('btnQuit').onclick = () => { G.state = 'menu'; UI.updateBoss(null); UI.showMenu(loadRecord()); };
  $('btnResume').onclick = () => togglePause();
  $('btnPause').onclick = () => togglePause();
  $('btnMute').onclick = () => {
    Sfx.unlock();
    $('btnMute').textContent = Sfx.toggleMute() ? '🔇' : '🔊';
  };
}

/* ===== 啟動 ===== */
bindButtons();
resize();
addEventListener('resize', resize);
UI.showMenu(loadRecord());
requestAnimationFrame(loop);
