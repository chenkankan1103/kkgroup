'use strict';
/* main.js — 遊戲迴圈＋狀態機（menu/playing/levelup/gameover）＋渲染＋HUD */

(() => {
  const $ = id => document.getElementById(id);
  const cv = $('game');
  Engine.init(cv);

  // ===== 世界狀態 =====
  const S = {
    phase: 'menu',          // menu / playing / levelup / gameover
    x: 0, y: 0, vx: 0, vy: 0,
    stats: null,            // 基礎+詞綴後的數值（每幀由 recompute 重算快取）
    skills: {},             // { bullet: {lvl}, ring: {lvl}, lance: {lvl} }
    fireT: 0, ringAng: 0, lanceT: 0,
    invT: 0,                // 受擊無敵
    xp: 0, level: 1, kills: 0, time: 0,
    look: null, doll: null, // 紙娃娃
  };

  // 裝備與統計
  const gear = [];         // 已撿裝備（詞綴已即時生效；面板顯示最近 6 件）
  function baseStats() {
    return { hp: BAL.baseHp, maxHp: BAL.baseHp, dmgPct: 0, aspdPct: 0, mspdPct: 0,
             magnetPct: 0, xpPct: 0, bullets: 2, pierce: 0 };
  }
  function recompute() {
    const st = baseStats();
    for (const it of gear) Loot.applyToStats(st, it);
    for (const k in S.skills) { /* 技能等級不在詞綴內，另計 */ }
    st.magnet = BAL.magnetR * (1 + st.magnetPct / 100);
    S.stats = st;
  }

  // ===== 池 =====
  const bulletPool = Engine.makePool(() => ({ x: 0, y: 0, vx: 0, vy: 0, life: 0, dmg: 0, pierce: 0 }), () => {});
  const bullets = [];
  const eBulletPool = Engine.makePool(() => ({ x: 0, y: 0, vx: 0, vy: 0, life: 0 }), () => {});
  const eBullets = [];
  const orbPool = Engine.makePool(() => ({ x: 0, y: 0, kind: 'xp', v: 0, t: 0, item: null }), () => { });
  const orbs = [];
  const txtPool = Engine.makePool(() => ({ x: 0, y: 0, vy: 0, life: 0, text: '', color: '' }), () => {});
  const floats = [];       // 傷害飄字
  const ringDmgT = new Map();

  function pushFloat(x, y, text, color) {
    if (floats.length > 80) return;           // 上限防爆
    const f = txtPool.get();
    f.x = x; f.y = y; f.vy = -46; f.life = 0.7; f.text = text; f.color = color || '#ffd35c';
    floats.push(f);
  }

  // ===== 輸入 =====
  const keys = {};
  window.addEventListener('keydown', e => { keys[e.key.toLowerCase()] = true; if (e.key === ' ') e.preventDefault(); });
  window.addEventListener('keyup', e => { keys[e.key.toLowerCase()] = false; });

  // ===== 開場流程 =====
  async function bootDoll() {
    let look = await Player.fetchMyLook();
    if (!look) look = npcFallback();
    S.look = look;
    S.doll = await Player.preloadDoll(look);
  }
  function npcFallback() {
    const db = NPC_LOOKS_DB;
    const g = { face: db.male, hair: db.male, top: db.top.male, bottom: db.bottom.male, shoes: db.shoes };
    const p = (a, d) => (a && a.length ? a[(Math.random() * a.length) | 0] : d);
    return { face: p(g.face, 20005), hair: p(g.hair, 30120), top: p(g.top, 1040014), bottom: p(g.bottom, 1060096), shoes: p(g.shoes, 1072005) };
  }

  $('btnStart').onclick = startGame;
  function startGame() {
    // 重置
    S.phase = 'playing';
    S.x = 0; S.y = 0; S.invT = 0; S.xp = 0; S.level = 1; S.kills = 0; S.time = 0;
    S.skills = { bullet: { lvl: 1 } };
    gear.length = 0;
    bullets.length = 0; eBullets.length = 0; orbs.length = 0; floats.length = 0;
    Mobs.list.length = 0;
    recompute();
    $('menu').classList.add('hidden');
    $('gameover').classList.add('hidden');
    $('hud').classList.remove('hidden');
  }

  // ===== 升級 =====
  function gainXp(v) {
    S.xp += Math.round(v * (1 + (S.stats.xpPct || 0) / 100));
    if (S.xp >= BAL.xpToLevel(S.level)) {
      S.xp -= BAL.xpToLevel(S.level);
      S.level++;
      openLevelUp();
    }
  }
  let levelChoices = null;
  function openLevelUp() {
    S.phase = 'levelup';
    const pool2 = LEVEL_UPS.filter(u => !u.can || u.can(S));
    const picks = [];
    const bag = pool2.slice();
    while (picks.length < 3 && bag.length) {
      const total = bag.reduce((s, u) => s + u.w, 0);
      let x = Math.random() * total;
      let idx = 0;
      for (let i = 0; i < bag.length; i++) { x -= bag[i].w; if (x <= 0) { idx = i; break; } }
      picks.push(bag.splice(idx, 1)[0]);
    }
    levelChoices = picks;
    $('lvChoices').innerHTML = picks.map((u, i) =>
      `<button class="lv-btn" data-i="${i}"><b>${u.name}</b><span>${u.desc}</span></button>`).join('');
    $('levelup').classList.remove('hidden');
  }
  $('lvChoices').addEventListener('click', e => {
    const b = e.target.closest('.lv-btn');
    if (!b) return;
    const u = levelChoices[+b.dataset.i];
    if (u) u.apply(S);
    recompute();
    $('levelup').classList.add('hidden');
    S.phase = 'playing';
  });

  // ===== 掉落 =====
  function dropLoot(x, y, elite) {
    const o = orbPool.get();
    o.x = x; o.y = y; o.t = 0; o.kind = 'xp'; o.v = elite ? 12 : 1;
    if (elite || Math.random() < 0.045) {       // 精英必掉、雜兵 4.5%
      o.item = Loot.makeItem(elite);
      o.kind = 'item';
    }
    orbs.push(o);
  }

  // ===== 戰鬥 =====
  function fireBullet() {
    const st = S.stats;
    const n = st.bullets;
    const nearest = nearestMob(S.x, S.y, 560);
    const baseAng = nearest ? Math.atan2(nearest.y - S.y, nearest.x - S.x) : (S.facing || 0);
    for (let i = 0; i < n; i++) {
      const spread = (i - (n - 1) / 2) * 0.14;
      const b = bulletPool.get();
      const ang = baseAng + spread;
      b.x = S.x; b.y = S.y;
      b.vx = Math.cos(ang) * BAL.bulletSpeed;
      b.vy = Math.sin(ang) * BAL.bulletSpeed;
      b.life = 1.5;
      b.dmg = BAL.baseBulletDmg * (1 + st.dmgPct / 100);
      b.pierce = st.pierce;
      bullets.push(b);
    }
  }
  function nearestMob(x, y, maxR) {
    let best = null, bd = maxR * maxR;
    for (const m of Mobs.list) {
      const dx = m.x - x, dy = m.y - y, d2 = dx * dx + dy * dy;
      if (d2 < bd) { bd = d2; best = m; }
    }
    return best;
  }
  function hitMob(m, dmg, i) {
    m.hp -= dmg;
    pushFloat(m.x + (Math.random() - 0.5) * 14, m.y - 24, Math.round(dmg), '#fff');
    if (m.hp <= 0) {
      S.kills++;
      dropLoot(m.x, m.y, m.elite);
      const xp = MOB_TYPES[m.type].xp * (m.elite ? 12 : 1);
      Mobs.kill(i);
      ringDmgT.delete(m);   // 池會重用物件，清掉殘留計時
      gainXp(xp);
      return true;
    }
    return false;
  }

  // ===== 主迴圈 =====
  let last = performance.now();
  function loop(now) {
    requestAnimationFrame(loop);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    Engine.fpsTick(dt);
    if (S.phase === 'playing') step(dt);
    render(dt);
  }

  function step(dt) {
    S.time += dt;
    const st = S.stats;
    // 移動
    let mx = (keys['d'] || keys['arrowright'] ? 1 : 0) - (keys['a'] || keys['arrowleft'] ? 1 : 0);
    let my = (keys['s'] || keys['arrowdown'] ? 1 : 0) - (keys['w'] || keys['arrowup'] ? 1 : 0);
    if (mx || my) {
      const inv = 1 / Math.hypot(mx, my);
      mx *= inv; my *= inv;
      S.facing = Math.atan2(my, mx);
    }
    S.moving = !!(mx || my);
    const spd = BAL.playerSpeed * (1 + (st.mspdPct || 0) / 100);
    S.x += mx * spd * dt; S.y += my * spd * dt;

    // 基礎彈幕
    S.fireT += dt;
    const fireCd = BAL.baseFireCd / (1 + (st.aspdPct || 0) / 100);
    if (S.skills.bullet && S.fireT >= fireCd) { S.fireT = 0; fireBullet(); }
    // 環身鎖鏈
    if (S.skills.ring) {
      const r = S.skills.ring.lvl;
      S.ringAng += BAL.ring.speed * dt;
      const R = BAL.ring.r + r * BAL.ring.perLvlR;
      const rx = S.x + Math.cos(S.ringAng) * R, ry = S.y + Math.sin(S.ringAng) * R;
      for (let i = Mobs.list.length - 1; i >= 0; i--) {
        const m = Mobs.list[i];
        if ((m.x - rx) ** 2 + (m.y - ry) ** 2 < (m.scale * 16 + 12) ** 2) {
          const lastT = ringDmgT.get(m) || 0;
          if (S.time - lastT > 0.35) {
            ringDmgT.set(m, S.time);
            if (hitMob(m, (BAL.ring.dps + r * BAL.ring.perLvlDps) * 0.35 * (1 + st.dmgPct / 100), i)) continue;
          }
        }
      }
    }
    // 貫穿鏢
    if (S.skills.lance) {
      S.lanceT += dt;
      if (S.lanceT >= BAL.lance.cd) {
        S.lanceT = 0;
        const b = bulletPool.get();
        const ang = S.facing || 0;
        b.x = S.x; b.y = S.y;
        b.vx = Math.cos(ang) * BAL.lance.speed; b.vy = Math.sin(ang) * BAL.lance.speed;
        b.life = 1.4;
        b.dmg = (BAL.lance.dmg + S.skills.lance.lvl * BAL.lance.perLvlDmg) * (1 + st.dmgPct / 100);
        b.pierce = 99;
        bullets.push(b);
      }
    }

    // 我方彈
    for (let i = bullets.length - 1; i >= 0; i--) {
      const b = bullets[i];
      b.life -= dt;
      b.x += b.vx * dt; b.y += b.vy * dt;
      let dead = b.life <= 0;
      if (!dead) {
        for (let j = Mobs.list.length - 1; j >= 0; j--) {
          const m = Mobs.list[j];
          if ((m.x - b.x) ** 2 + (m.y - b.y) ** 2 < (m.scale * 16 + 5) ** 2) {
            if (hitMob(m, b.dmg, j)) continue;
            if (b.pierce > 0) b.pierce--;
            else { dead = true; break; }
          }
        }
      }
      if (dead) { bulletPool.put(b); bullets[i] = bullets[bullets.length - 1]; bullets.pop(); }
    }

    Mobs.update(dt, S, null,
      (m, nx, ny, sp) => {
        const eb = eBulletPool.get();
        eb.x = m.x; eb.y = m.y; eb.vx = nx * sp; eb.vy = ny * sp; eb.life = 2.4;
        eBullets.push(eb);
      });

    // 敵彈
    for (let i = eBullets.length - 1; i >= 0; i--) {
      const b = eBullets[i];
      b.life -= dt;
      b.x += b.vx * dt; b.y += b.vy * dt;
      const dead = b.life <= 0 || ((b.x - S.x) ** 2 + (b.y - S.y) ** 2 < 14 ** 2);
      if (dead && b.life > 0) damagePlayer(MOB_TYPES.gunner.dmg * 0.6);
      if (dead) { eBulletPool.put(b); eBullets[i] = eBullets[eBullets.length - 1]; eBullets.pop(); }
    }

    // 碰撞傷害＋被撞無敵
    if (S.invT > 0) S.invT -= dt;
    else {
      for (const m of Mobs.list) {
        if ((m.x - S.x) ** 2 + (m.y - S.y) ** 2 < (m.scale * 14 + 12) ** 2) {
          damagePlayer(MOB_TYPES[m.type].dmg * (m.elite ? 1.6 : 1));
          break;
        }
      }
    }

    // 撿物
    const mag = st.magnet;
    for (let i = orbs.length - 1; i >= 0; i--) {
      const o = orbs[i];
      o.t += dt;
      const d2 = (o.x - S.x) ** 2 + (o.y - S.y) ** 2;
      if (d2 < mag * mag) { const d = Math.sqrt(d2) || 1; o.x += (S.x - o.x) / d * 300 * dt; o.y += (S.y - o.y) / d * 300 * dt; }
      if (d2 < 20 * 20) {
        if (o.kind === 'xp') gainXp(o.v);
        else {
          Loot.applyToStats(st, o.item);
          gear.push(o.item);
          if (gear.length > 12) gear.shift();
          pushFloat(S.x, S.y - 40, o.item.name, o.item.rarity.color);
          renderGearPanel();
        }
        orbPool.put(o); orbs[i] = orbs[orbs.length - 1]; orbs.pop();
      }
    }

    // 飄字
    for (let i = floats.length - 1; i >= 0; i--) {
      const f = floats[i];
      f.life -= dt; f.y += f.vy * dt;
      if (f.life <= 0) { txtPool.put(f); floats[i] = floats[floats.length - 1]; floats.pop(); }
    }

    // HUD
    $('hudHp').textContent = Math.max(0, Math.round(st.hp)) + '/' + st.maxHp;
    $('hudTime').textContent = fmtTime(S.time);
    $('hudLevel').textContent = 'Lv.' + S.level;
    $('hudKills').textContent = S.kills;
    $('hudWave').textContent = '第 ' + (Mobs.wave + 1) + ' 波';
  }

  function damagePlayer(dmg) {
    if (S.invT > 0) return;
    S.stats.hp -= dmg;
    S.invT = BAL.invulnHit;
    pushFloat(S.x, S.y - 30, '-' + Math.round(dmg), '#ff6b6b');
    $('game').classList.add('hitflash');
    setTimeout(() => $('game').classList.remove('hitflash'), 120);
    if (S.stats.hp <= 0) gameOver();
  }

  function fmtTime(t) {
    const m = (t / 60) | 0, s = (t % 60) | 0;
    return m + ':' + String(s).padStart(2, '0');
  }

  function renderGearPanel() {
    const el = $('gearList');
    el.innerHTML = gear.slice(-6).reverse().map(it =>
      `<div class="gear-item" style="border-color:${it.rarity.color}"><b style="color:${it.rarity.color}">${it.name}</b>` +
      `<span>${it.affixes.map(a => Loot.affixLine(a)).join('・')}</span></div>`).join('');
  }

  // ===== 結局 =====
  function gameOver() {
    S.phase = 'gameover';
    const mins = fmtTime(S.time);
    $('goStats').innerHTML =
      `<span>存活 <b>${mins}</b></span><span>等級 <b>Lv.${S.level}</b></span><span>擊殺 <b>${S.kills}</b></span><span>波次 <b>${Mobs.wave + 1}</b></span>`;
    const topGear = gear.slice(-3).reverse();
    $('goGear').innerHTML = topGear.length
      ? '戰利品：' + topGear.map(it => `<b style="color:${it.rarity.color}">${it.name}</b>`).join('、')
      : '（沒撿到裝備）';
    const shareTxt = `🏴 KK 園區倖存者｜存活 ${mins}・Lv.${S.level}・擊殺 ${S.kills}\n來臥底兼割草：${DC_INVITE}`;
    $('btnShare').onclick = () => {
      const done = () => { $('btnShare').textContent = '✓ 已複製'; setTimeout(() => { $('btnShare').textContent = '📋 複製戰績'; }, 2200); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(shareTxt).then(done).catch(() => {});
      else {
        const ta = document.createElement('textarea');
        ta.value = shareTxt; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); done(); } catch (e) {}
        ta.remove();
      }
    };
    $('gameover').classList.remove('hidden');
    $('hud').classList.add('hidden');
  }
  $('btnRetry').onclick = startGame;

  // ===== 渲染 =====
  function render(dt) {
    const cam = { x: S.x, y: S.y };
    Engine.begin(cam);
    Engine.drawGrid(cam);
    const ctx = Engine.ctx;
    // 掉落物＋光柱
    for (const o of orbs) {
      if (o.kind === 'xp') {
        ctx.fillStyle = '#5ee0a0';
        ctx.fillRect(o.x - 4, o.y - 4, 8, 8);
      } else {
        const c = o.item.rarity.color;
        const beamH = o.item.rarity.affixes >= 4 ? 90 : o.item.rarity.affixes === 2 ? 60 : 34;
        const grad = ctx.createLinearGradient(o.x, o.y, o.x, o.y - beamH);
        grad.addColorStop(0, c + 'cc'); grad.addColorStop(1, c + '00');
        ctx.fillStyle = grad;
        ctx.fillRect(o.x - 3, o.y - beamH, 6, beamH);
        ctx.fillStyle = c;
        ctx.fillRect(o.x - 6, o.y - 6, 12, 12);
      }
    }
    // 怪
    const wob = t => Math.sin(t * 10) * 2;
    for (const m of Mobs.list) {
      const di = Object.keys(MOB_TYPES).indexOf(m.type);
      const doll = m.elite ? Mobs.ELITE_DOLL : Mobs.MOB_DOLLS[di];
      const img = doll && (doll.walk && (Math.sin(m.t * 8) > 0 ? doll.walk : doll.stand) || doll.stand);
      if (!img) continue;
      ctx.save();
      if (doll.hue) ctx.filter = `hue-rotate(${doll.hue}deg) brightness(${m.elite ? 1.15 : 1})`;
      const sz = 44 * m.scale;
      const wobY = m.elite ? 0 : wob(m.t);
      if (ctx.filter !== 'none') {
        ctx.shadowColor = m.elite ? 'rgba(255,80,80,0.9)' : 'rgba(0,0,0,0.45)';
        ctx.shadowBlur = m.elite ? 16 : 6;
      }
      ctx.drawImage(img, m.x - sz / 2, m.y - sz + wobY, sz, sz);
      ctx.restore();
      if (m.hp < m.maxHp) {
        ctx.fillStyle = '#0008';
        ctx.fillRect(m.x - 16, m.y - sz - 8 - wobY, 32, 4);
        ctx.fillStyle = '#ff5a5a';
        ctx.fillRect(m.x - 16, m.y - sz - 8 - wobY, 32 * Math.max(0, m.hp / m.maxHp), 4);
      }
    }
    // 我方彈
    ctx.fillStyle = '#ffd35c';
    for (const b of bullets) { ctx.beginPath(); ctx.arc(b.x, b.y, 4, 0, 7); ctx.fill(); }
    ctx.fillStyle = '#7fb3ff';
    for (const b of eBullets) { ctx.beginPath(); ctx.arc(b.x, b.y, 5, 0, 7); ctx.fill(); }
    // 環
    if (S.phase === 'playing' && S.skills.ring) {
      const r = S.skills.ring.lvl;
      const R = BAL.ring.r + r * BAL.ring.perLvlR;
      ctx.strokeStyle = 'rgba(255,211,92,0.8)';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(S.x + Math.cos(S.ringAng) * R, S.y + Math.sin(S.ringAng) * R, 10, 0, 7);
      ctx.stroke();
    }
    // 主角
    if (S.doll) {
      const img = S.moving ? (S.doll.walk || S.doll.stand) : S.doll.stand;
      if (img) {
        if (S.invT > 0 && (S.time * 20 | 0) % 2 === 0) ctx.globalAlpha = 0.4;
        ctx.drawImage(img, S.x - 26, S.y - 62, 52, 62);
        ctx.globalAlpha = 1;
      }
    }
    // 飄字
    ctx.font = '700 13px monospace';
    ctx.textAlign = 'center';
    for (const f of floats) {
      ctx.globalAlpha = Math.min(1, f.life * 2);
      ctx.fillStyle = f.color;
      ctx.fillText(f.text, f.x, f.y);
    }
    ctx.globalAlpha = 1;
    Engine.end();
  }

  // ===== 驗證鉤：探針/測試讀狀態用（唯讀慣例，別在遊戲邏輯外改） =====
  window.__KS = {
    get S() { return S; },
    get gear() { return gear; },
    get mobCount() { return Mobs.list.length; },
    get dollFallback() { return !!(S.doll && S.doll.fallback); },
    get mobDolls() { return Mobs.dolls; },
  };

  // ===== 啟動 =====
  // 造型＋怪造型都預載完才開始（怪造型沒載完就開打會看不到怪）
  bootDoll()
    .then(() => Mobs.preload())
    .then(() => { $('btnStart').disabled = false; $('menuHint').textContent = '造型已就緒'; })
    .catch(() => { $('btnStart').disabled = false; $('menuHint').textContent = '造型載入失敗，用替代圖上陣'; });
  requestAnimationFrame(loop);
})();
