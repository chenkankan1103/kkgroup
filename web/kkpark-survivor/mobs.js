'use strict';
/* mobs.js — 怪生成（外型表 looks.js）、波次、移動、敵彈
   守塔模式：怪一律瞄核心（CORE），玩家只是守在核心周圍的人。 */

const CORE = { x: 0, y: 0, hp: BAL.core.hp, maxHp: BAL.core.hp, hitCd: 0 };

const Mobs = (() => {
  const MOB_DOLLS = [];    // 預載好的 {stand,walk,hue}，按怪種索引
  const ELITE_DOLL = { stand: null, walk: null, hue: 300 };

  // 怪種 → 外型 look（looks.js）：巡邏員/便衣/制服 三種巡查員外型
  const MOB_LOOK_KEY = { rusher: 'patrol', swarm: 'plainclothes', gunner: 'officer' };

  // 預載：每怪種一份 stand/walk（一次載入，戰鬥零請求）
  async function preload() {
    const keys = Object.keys(MOB_TYPES);
    for (const k of keys) {
      const lookKey = MOB_LOOK_KEY[k] || 'patrol';
      const look = resolveLook(lookKey, 'survivor-' + k);
      const doll = await Player.preloadDoll(look);
      MOB_DOLLS.push({ ...doll, hue: MOB_TYPES[k].hue });
    }
    // 精英：隊長外型（深藍制服＋深色軍帽）
    const eliteLook = resolveLook('commander', 'survivor-elite');
    const ed = await Player.preloadDoll(eliteLook);
    ELITE_DOLL.stand = ed.stand; ELITE_DOLL.walk = ed.walk;
    return MOB_DOLLS.length === keys.length;
  }

  // 怪池（零配置）
  const pool = Engine.makePool(
    () => ({ x: 0, y: 0, vx: 0, vy: 0, hp: 0, maxHp: 0, type: null, elite: false, t: 0, fireT: 0, scale: 1 }),
    (o) => { o.t = 0; o.fireT = 0; o.elite = false; o.scale = 1; }
  );
  const list = [];

  function spawn(t, elite, px, py) {
    const d = MOB_TYPES[t];
    const m = pool.get();
    m.type = t;
    m.elite = !!elite;
    m.maxHp = Math.round(d.hp * WAVE.hpMult(waveIdx()) * (elite ? 10 : 1));
    m.hp = m.maxHp;
    m.scale = elite ? 1.8 : 1;
    // 守塔模式：環繞核心外圈生成（畫面外）
    const ang = Math.random() * Math.PI * 2;
    const R = Math.max(Engine.W, Engine.H) * 0.62 + 40;
    m.x = CORE.x + Math.cos(ang) * R;
    m.y = CORE.y + Math.sin(ang) * R;
    m.vx = 0; m.vy = 0;
    list.push(m);
  }

  let wave = 0, waveT = 0, spawnAcc = 0, eliteDue = false;
  function waveIdx() { return wave; }

  function update(dt, S, onDeath, onShoot) {
    waveT += dt;
    if (waveT >= WAVE.stepSec) { waveT = 0; wave++; if (wave % WAVE.eliteEvery === 0) eliteDue = true; }
    // 生成（上限 240 隻防爆：卡機時少生成而非崩）
    spawnAcc += WAVE.spawnPerSec(wave) * dt;
    while (spawnAcc >= 1) {
      spawnAcc--;
      if (list.length >= 240) continue;
      const w = WAVE.weights(wave);
      const r = Math.random() * (w.rusher + w.swarm + w.gunner);
      spawn(r < w.rusher ? 'rusher' : r < w.rusher + w.swarm ? 'swarm' : 'gunner', false, S.x, S.y);
    }
    if (eliteDue && list.length < 240) { eliteDue = false; spawn('rusher', true, S.x, S.y); }
    else eliteDue = false;

    // 移動＆敵彈（守塔模式：怪瞄核心 0,0，不是瞄玩家）
    for (let i = list.length - 1; i >= 0; i--) {
      const m = list[i];
      m.t += dt;
      const d = MOB_TYPES[m.type];
      const sp = d.speed * (m.elite ? 0.8 : 1);
      const dx = CORE.x - m.x, dy = CORE.y - m.y;
      const dist = Math.hypot(dx, dy) || 1;
      if (d.ranged && dist < d.range * 0.7) {
        // 保持距離橫移（仍瞄核心）
        m.x += (-dy / dist) * sp * 0.6 * dt;
        m.y += (dx / dist) * sp * 0.6 * dt;
        m.fireT += dt;
        if (m.fireT >= d.fireCd) { m.fireT = 0; onShoot(m, dx / dist, dy / dist, d.bulletSpeed); }
      } else {
        m.x += (dx / dist) * sp * dt;
        m.y += (dy / dist) * sp * dt;
      }
    }
  }

  function kill(i) { pool.put(list[i]); list[i] = list[list.length - 1]; list.pop(); }

  return { preload, update, list, kill, get wave() { return wave; }, get dolls() { return MOB_DOLLS; },
    get MOB_DOLLS() { return MOB_DOLLS; }, get ELITE_DOLL() { return ELITE_DOLL; } };
})();
