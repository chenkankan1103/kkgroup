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
    kk: 0,                  // 本局工作室收益（通關才入帳）
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

  // ===== 園區建築群（v0.3.1：程序化 b3 變體，環帶外地標）=====
  // 樓房=地標；哨塔=自動開火；工作室=站光圈掛機賺 KK 幣（通關才入帳，淪陷蒸發）
  const SPR = {};          // 圖檔非同步載入
  function loadSpr(key, url) {
    const im = new Image();
    im.onload = () => { SPR[key] = im; };
    im.src = url;
  }
  ['bld_a', 'bld_b', 'bld_c', 'bld_d', 'office_a'].forEach(k => loadSpr(k, 'assets/' + k + '.png'));
  const D2R = Math.PI / 180;
  const BUILDINGS = [
    { spr: 'bld_b', ang: 0,   r: 440, w: 190 }, { spr: 'bld_a', ang: 47,  r: 540, w: 170 },
    { spr: 'bld_c', ang: 96,  r: 480, w: 175 }, { spr: 'bld_d', ang: 150, r: 570, w: 180 },
    { spr: 'bld_a', ang: 200, r: 430, w: 175 }, { spr: 'bld_b', ang: 247, r: 520, w: 185 },
    { spr: 'bld_c', ang: 295, r: 550, w: 170 }, { spr: 'bld_d', ang: 341, r: 460, w: 180 },
  ].map(b => { const a = b.ang * D2R; return { ...b, x: Math.cos(a) * b.r, y: Math.sin(a) * b.r }; });
  const TOWERS = [
    { ang: 70,  r: 320 }, { ang: 250, r: 285 },
  ].map(t => { const a = t.ang * D2R; return { ...t, x: Math.cos(a) * t.r, y: Math.sin(a) * t.r + (t.ang > 180 ? 20 : 0), cd: 0 }; });
  const OFFICES = [
    { spr: 'office_a', ang: 160, r: 390, w: 175 }, { spr: 'office_a', ang: 310, r: 400, w: 175 },
  ].map(o => { const a = o.ang * D2R; return { ...o, x: Math.cos(a) * o.r, y: Math.sin(a) * o.r, zone: 90 }; });

  function pushFloat(x, y, text, color) {
    if (floats.length > 80) return;           // 上限防爆
    const f = txtPool.get();
    f.x = x; f.y = y; f.vy = -46; f.life = 0.7; f.text = text; f.color = color || '#ffd35c';
    floats.push(f);
  }

  // ===== 輸入 =====
  const keys = {};
  function toggleGearPanel() {
    const el = $('gearList');
    el.classList.toggle('hidden');
    $('hudBag').classList.toggle('on', !el.classList.contains('hidden'));
  }
  window.addEventListener('keydown', e => {
    keys[e.key.toLowerCase()] = true;
    if (e.key === ' ') e.preventDefault();
    if (e.key === 'Tab') { e.preventDefault(); toggleGearPanel(); }
  });
  window.addEventListener('keyup', e => { keys[e.key.toLowerCase()] = false; });

  // ===== 開場流程 =====
  async function bootDoll() {
    let look = await Player.fetchMyLook();
    if (!look) look = npcFallback();
    S.look = look;
    S.doll = await Player.preloadHero(look);
  }
  function npcFallback() {
    const db = NPC_LOOKS_DB;
    const p = (a, d) => (a && a.length ? a[(Math.random() * a.length) | 0] : d);
    return {
      face: p(db.male.face, 20005), hair: p(db.male.hair, 30120),
      top: p(db.top.male, 1040014), bottom: p(db.bottom.male, 1060096), shoes: p(db.shoes, 1072005),
      hat: 0, accessory: 0,
    };
  }

  $('btnStart').onclick = startGame;
  function startGame() {
    // 重置
    S.phase = 'playing';
    S.x = 0; S.y = 180; S.invT = 0; S.xp = 0; S.level = 1; S.kills = 0; S.time = 0;
    S.kk = 0;
    S.skills = { bullet: { lvl: 1 } };
    S.win = false;
    CORE.hp = CORE.maxHp = BAL.core.hp;
    CORE.hitCd = 0;
    gear.length = 0;
    bullets.length = 0; eBullets.length = 0; orbs.length = 0; floats.length = 0;
    Mobs.reset();
    Mobs.list.length = 0;
    renderGearPanel();
    $('hudBag').textContent = '🎒 0';
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
  let levelChoices = null, lvTimer = 0;
  const AUTO_PICK_SEC = 9;      // 倒數完自動隨機選，遊戲不再無限凍結等點選
  function openLevelUp() {
    S.phase = 'levelup';
    lvTimer = AUTO_PICK_SEC;
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
    $('lvTimer').textContent = '⏱ ' + AUTO_PICK_SEC + ' 秒後自動選擇';
    $('levelup').classList.remove('hidden');
  }
  function applyLevelChoice(i) {
    const u = levelChoices && levelChoices[i];
    if (!u) return;
    u.apply(S);
    recompute();
    $('levelup').classList.add('hidden');
    S.phase = 'playing';
  }
  $('lvChoices').addEventListener('click', e => {
    const b = e.target.closest('.lv-btn');
    if (!b) return;
    applyLevelChoice(+b.dataset.i);
  });
  // 升級倒數（真實時間 tick，不佔 step）
  function tickLevelup(dt) {
    lvTimer -= dt;
    if (lvTimer <= 0) { applyLevelChoice((Math.random() * levelChoices.length) | 0); return; }
    $('lvTimer').textContent = '⏱ ' + Math.ceil(lvTimer) + ' 秒後自動選擇';
  }

  // ===== 掉落 =====
  // v0.2.1：怪常死在玩家環帶外（外圈生成往核心走），掉落直接投影進環帶，
  // 不然磁性 46px 根本橋不到 → gearN 永遠 0
  function dropLoot(x, y, elite) {
    const o = orbPool.get();
    const dx = x - CORE.x, dy = y - CORE.y;
    const d = Math.hypot(dx, dy) || 1;
    const lo = BAL.core.playerRingMin + 18, hi = BAL.core.playerRingMax - 24;
    const cd = Math.max(lo, Math.min(hi, d));
    o.x = CORE.x + dx / d * cd + (Math.random() - 0.5) * 26;
    o.y = CORE.y + dy / d * cd + (Math.random() - 0.5) * 26;
    o.t = 0; o.kind = 'xp'; o.v = elite ? 12 : 1;
    if (elite || Math.random() < 0.045) {       // 精英必掉、雜兵 4.5%
      o.item = Loot.makeItem(elite);
      o.kind = 'item';
    }
    orbs.push(o);
    if (orbs.length > 300) {                    // 防爆：最舊的經驗珠直接入袋（裝備不吞）
      const old = orbs[0];
      if (old.kind === 'xp') { gainXp(old.v); orbPool.put(old); }
      orbs[0] = orbs[orbs.length - 1]; orbs.pop();
    }
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
    else if (S.phase === 'levelup') tickLevelup(dt);
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
    // 守塔：玩家只能在核心周圍的環帶活動（進不了核心、跑不出範圍）
    {
      const dx = S.x - CORE.x, dy = S.y - CORE.y;
      const d = Math.hypot(dx, dy);
      const minR = BAL.core.playerRingMin, maxR = BAL.core.playerRingMax;
      if (d < minR) {
        const k = d < 0.001 ? 0 : minR / d;
        S.x = CORE.x + dx * k; S.y = CORE.y + dy * k;
      } else if (d > maxR) {
        const k = maxR / d;
        S.x = CORE.x + dx * k; S.y = CORE.y + dy * k;
      }
    }

    // 基礎彈幕
    S.fireT += dt;
    const fireCd = BAL.baseFireCd / (1 + (st.aspdPct || 0) / 100);
    if (S.skills.bullet && S.fireT >= fireCd) { S.fireT = 0; fireBullet(); S.swingT = 0.18; }
    // 揮手動作計時（攻擊/施放時短暫換 pose）
    if (S.swingT > 0) S.swingT -= dt;
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

    // 敵彈（守塔：瞄核心，命中核心扣核心血；碰到玩家也扣一點）
    for (let i = eBullets.length - 1; i >= 0; i--) {
      const b = eBullets[i];
      b.life -= dt;
      b.x += b.vx * dt; b.y += b.vy * dt;
      const hitCore = (b.x - CORE.x) ** 2 + (b.y - CORE.y) ** 2 < BAL.core.radius ** 2;
      const hitPlayer = (b.x - S.x) ** 2 + (b.y - S.y) ** 2 < 14 ** 2;
      const dead = b.life <= 0 || hitCore || hitPlayer;
      if (hitCore && b.life > 0) damageCore(MOB_TYPES.gunner.dmg * 0.6);
      if (hitPlayer && b.life > 0) damagePlayer(MOB_TYPES.gunner.dmg * 0.6);
      if (dead) { eBulletPool.put(b); eBullets[i] = eBullets[eBullets.length - 1]; eBullets.pop(); }
    }

    // 怪撞核心扣血（守塔主機制）＋撞玩家扣玩家血
    if (CORE.hitCd > 0) CORE.hitCd -= dt;
    // 核心回血：沒怪靠近時慢慢回（避免一波打死就沒得玩）
    if (BAL.core.regen > 0 && CORE.hp < CORE.maxHp) {
      const near = Mobs.list.some(m => (m.x - CORE.x) ** 2 + (m.y - CORE.y) ** 2 < 260 * 260);
      if (!near) CORE.hp = Math.min(CORE.maxHp, CORE.hp + BAL.core.regen * dt);
    }
    for (const m of Mobs.list) {
      const dCore = (m.x - CORE.x) ** 2 + (m.y - CORE.y) ** 2;
      if (dCore < (BAL.core.radius + m.scale * 14) ** 2) {
        if (CORE.hitCd <= 0) {
          CORE.hitCd = BAL.core.hitCd;
          damageCore(BAL.core.hitDmg * (m.elite ? 1.8 : 1));
        }
      }
      if (S.invT <= 0) {
        if ((m.x - S.x) ** 2 + (m.y - S.y) ** 2 < (m.scale * 14 + 12) ** 2) {
          damagePlayer(MOB_TYPES[m.type].dmg * (m.elite ? 1.6 : 1));
          break;
        }
      }
    }
    if (S.invT > 0) S.invT -= dt;

    // 哨塔自動開火（園區防衛，傷害固定不隨詞綴）
    for (const t of TOWERS) {
      t.cd -= dt;
      if (t.cd > 0) continue;
      const m = nearestMob(t.x, t.y, BAL.towerRange);
      if (!m) continue;
      t.cd = BAL.towerCd;
      const ang = Math.atan2(m.y - t.y, m.x - t.x);
      const b = bulletPool.get();
      b.x = t.x; b.y = t.y - 40;
      b.vx = Math.cos(ang) * BAL.bulletSpeed; b.vy = Math.sin(ang) * BAL.bulletSpeed;
      b.life = BAL.towerRange / BAL.bulletSpeed + 0.1;
      b.dmg = BAL.towerDmg; b.pierce = 0;
      bullets.push(b);
    }

    // 工作室：站進光圈掛機賺 KK 幣（單局上限；通關入帳、淪陷蒸發）
    for (const o of OFFICES) {
      if ((S.x - o.x) ** 2 + (S.y - o.y) ** 2 < o.zone * o.zone) {
        const gain = Math.min(BAL.buildingKkCap - S.kk, BAL.buildingKkRate * dt);
        if (gain > 0) {
          S.kk += gain;
          if ((S.kk | 0) > (o.lastPop | 0)) {
            o.lastPop = S.kk | 0;
            pushFloat(o.x, o.y - 90, '+' + (o.lastPop % 10 === 0 ? o.lastPop : '') || '', '#ffd35c');
          }
        }
      }
    }

    // 撿物
    const mag = st.magnet;
    for (let i = orbs.length - 1; i >= 0; i--) {
      const o = orbs[i];
      o.t += dt;
      const d2 = (o.x - S.x) ** 2 + (o.y - S.y) ** 2;
      if (d2 < mag * mag) { const d = Math.sqrt(d2) || 1; o.x += (S.x - o.x) / d * 420 * dt; o.y += (S.y - o.y) / d * 420 * dt; }
      if (d2 < 20 * 20) {
        if (o.kind === 'xp') gainXp(o.v);
        else {
          Loot.applyToStats(st, o.item);
          gear.push(o.item);
          if (gear.length > 12) gear.shift();
          pushFloat(S.x, S.y - 40, o.item.name, o.item.rarity.color);
          renderGearPanel();
          $('hudBag').textContent = '🎒 ' + gear.length;   // 面板收起時至少看得到件數
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
    $('hudKk').textContent = '💰 ' + (S.kk | 0);
    $('hudWave').textContent = '第 ' + Math.min(Mobs.wave + 1, BAL.waveToWin) + '/' + BAL.waveToWin + ' 波';
    // 核心血條
    const corePct = Math.max(0, Math.min(100, CORE.hp / CORE.maxHp * 100));
    $('hudCoreFill').style.width = corePct.toFixed(1) + '%';
    $('hudCoreFill').className = 'fill' + (corePct <= 30 ? ' hot' : corePct <= 60 ? ' warn' : '');
    $('hudCoreT').textContent = Math.round(CORE.hp);
    checkWin();
  }

  function damagePlayer(dmg) {
    if (S.invT > 0) return;
    S.stats.hp -= dmg;
    S.invT = BAL.invulnHit;
    pushFloat(S.x, S.y - 30, '-' + Math.round(dmg), '#ff6b6b');
    $('game').classList.add('hitflash');
    setTimeout(() => $('game').classList.remove('hitflash'), 120);
    if (S.stats.hp <= 0) gameOver(false);
  }

  // 核心（園區）受損：血量歸零＝園區淪陷
  function damageCore(dmg) {
    CORE.hp = Math.max(0, CORE.hp - dmg);
    pushFloat(CORE.x, CORE.y - 70, '-' + Math.round(dmg), '#ff9b6b');
    if (CORE.hp <= 0) gameOver(false);
  }

  // 勝利：撐過指定波數（v0.2.1：打完整第 12 波才贏，原本第 12 波開打瞬間就結算＝只打 11 波）
  function checkWin() {
    if (S.win || S.phase !== 'playing') return;
    if (Mobs.wave >= BAL.waveToWin) {
      S.win = true;
      gameOver(true);
    }
  }

  function fmtTime(t) {
    const m = (t / 60) | 0, s = (t % 60) | 0;
    return m + ':' + String(s).padStart(2, '0');
  }

  function renderGearPanel() {
    const el = $('gearList');
    el.innerHTML = gear.slice(-6).reverse().map(it =>
      `<div class="gear-item" style="border-color:${it.rarity.color}"><b style="color:${it.rarity.color}">${it.name}</b>` +
      `<span>［${it.slotLabel || '？'}］${it.affixes.map(a => Loot.affixLine(a)).join('・')}</span></div>`).join('');
  }

  // 通關才入庫（v0.3.0：淪陷＝這局的戰利品蒸發）。局外裝備庫 UI 等等接，先埋 localStorage 底
  function bankStash(win) {
    if (!win || !gear.length) return;
    try {
      const id = localStorage.getItem('kkpark_discord_id') || 'guest';
      const key = 'kkpark_survivor_stash_' + id;
      const stash = JSON.parse(localStorage.getItem(key) || '[]');
      for (const it of gear) {
        stash.push({ name: it.name, slot: it.slot, slotLabel: it.slotLabel,
                     rarity: it.rarity.id, affixes: it.affixes });
      }
      while (stash.length > 60) stash.shift();   // 上限防爆
      localStorage.setItem(key, JSON.stringify(stash));
    } catch (e) {}
  }

  // ===== 結局 =====
  function gameOver(win) {
    S.phase = 'gameover';
    const mins = fmtTime(S.time);
    $('goTitle').textContent = win ? '園區守住了！' : '園區淪陷';
    $('goStats').innerHTML =
      `<span>存活 <b>${mins}</b></span><span>等級 <b>Lv.${S.level}</b></span><span>擊殺 <b>${S.kills}</b></span>` +
      `<span>波次 <b>${Math.min(Mobs.wave + 1, BAL.waveToWin)}</b>/${BAL.waveToWin}</span><span>核心 <b>${Math.round(CORE.hp)}</b></span>` +
      `<span>工作室 <b>${win ? '+' + (S.kk | 0) + ' 已記入' : (S.kk | 0) + ' 蒸發'}</b></span>`;
    const topGear = gear.slice(-3).reverse();
    bankStash(win);
    $('goGear').innerHTML = topGear.length
      ? (win
        ? `戰利品 ${gear.length} 件已入庫：`
        : '戰利品蒸發了——守住園區才能帶回：')
        + topGear.map(it => `<b style="color:${it.rarity.color}">${it.name}</b>`).join('、')
      : '（沒撿到裝備）';
    const shareTxt = `🏴 KK 園區守塔｜${win ? '守住園區' : '園區淪陷'}・存活 ${mins}・Lv.${S.level}・擊殺 ${S.kills}\n來守一波：${DC_INVITE}`;
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
  $('hudBag').onclick = toggleGearPanel;

  // ===== 渲染 =====
  function render(dt) {
    const cam = { x: CORE.x, y: CORE.y };   // 鏡頭跟核心（玩家在核心周圍）
    Engine.begin(cam);
    Engine.drawGround(cam, BAL.core.radius);
    const ctx = Engine.ctx;
    drawCore(ctx);
    // 工作室光圈（地面標記，站進去賺幣）
    for (const o of OFFICES) {
      ctx.save();
      ctx.strokeStyle = 'rgba(255,211,92,0.5)';
      ctx.lineWidth = 2;
      ctx.setLineDash([8, 8]);
      ctx.lineDashOffset = -(performance.now() / 90) % 16;
      ctx.beginPath();
      ctx.arc(o.x, o.y, o.zone, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = 'rgba(255,211,92,0.06)';
      ctx.fill();
      ctx.restore();
    }
    // 建築群＋工作室（依 y 排序畫，近的蓋遠的）
    const draws = [...BUILDINGS, ...OFFICES].sort((a, b) => a.y - b.y);
    for (const b of draws) {
      const img = SPR[b.spr];
      if (!img) continue;
      const w = b.w, h = w;
      ctx.drawImage(img, b.x - w / 2, b.y - h * 0.62, w, h);
    }
    // 哨塔：純 Canvas 畫（素材去背救不動，程序化畫最乾淨）
    for (const t of TOWERS) drawTower(ctx, t);
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
    const mobKeys = Object.keys(MOB_TYPES);
    for (const m of Mobs.list) {
      const di = mobKeys.indexOf(m.type);
      const doll = m.elite ? Mobs.ELITE_DOLL : Mobs.MOB_DOLLS[di] || Mobs.MOB_DOLLS[0];
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
      if ((m.fx || 1) < 0) {           // 面左：鏡射（紙娃娃素材預設面向右）
        ctx.translate(m.x, m.y - sz / 2 + wobY);
        ctx.scale(-1, 1);
        ctx.drawImage(img, -sz / 2, -sz / 2, sz, sz);
      } else {
        ctx.drawImage(img, m.x - sz / 2, m.y - sz + wobY, sz, sz);
      }
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
    // 主角（走動用 walk、攻擊用 swing、其餘 stand）
    if (S.doll) {
      let img = S.doll.stand;
      if (S.swingT > 0 && S.doll.swing) img = S.doll.swing;
      else if (S.moving) img = S.doll.walk || S.doll.stand;
      if (img) {
        ctx.save();
        if (S.invT > 0 && (S.time * 20 | 0) % 2 === 0) ctx.globalAlpha = 0.4;
        if (Math.cos(S.facing || 0) < -0.05) {   // 面左：鏡射
          ctx.translate(S.x, S.y - 31);
          ctx.scale(-1, 1);
          ctx.drawImage(img, -26, -31, 52, 62);
        } else {
          ctx.drawImage(img, S.x - 26, S.y - 62, 52, 62);
        }
        ctx.restore();
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
  // v0.2.1：加 debug 鉤供 headless 探針實測 12 波平衡（keys 僅探針模擬走位用）
  window.__KS = {
    get S() { return S; },
    get gear() { return gear; },
    get mobCount() { return Mobs.list.length; },
    get dollFallback() { return !!(S.doll && S.doll.fallback); },
    get mobDolls() { return Mobs.dolls; },
    get keys() { return keys; },
    get orbCount() { return orbs.length; },
    get kk() { return S.kk | 0; },
    debugStart: startGame,
    debugTick(dt, n) { for (let i = 0; i < n && S.phase === 'playing'; i++) step(dt); },
    pickLevel(i) { applyLevelChoice(i); },
  };

  // 哨塔：程序化繪製——混凝土塔身＋頂部哨亭＋橙色頂蓋（開火時砲口亮一下）
  function drawTower(ctx, t) {
    const R = 46;                       // 塔身半寬
    // 塔身（梯形，上窄下寬）
    ctx.save();
    ctx.fillStyle = '#3a4048';
    ctx.strokeStyle = 'rgba(150,170,190,0.55)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(t.x - R * 0.62, t.y - 86);
    ctx.lineTo(t.x + R * 0.62, t.y - 86);
    ctx.lineTo(t.x + R, t.y + 6);
    ctx.lineTo(t.x - R, t.y + 6);
    ctx.closePath();
    ctx.fill(); ctx.stroke();
    // 窗格
    ctx.fillStyle = 'rgba(255,211,92,0.5)';
    for (let i = 0; i < 3; i++) ctx.fillRect(t.x - 5, t.y - 74 + i * 24, 10, 8);
    // 哨亭
    const hot = t.cd > BAL.towerCd - 0.25;   // 剛開火＝亮
    ctx.fillStyle = '#2c323a';
    ctx.strokeStyle = 'rgba(150,170,190,0.7)';
    ctx.beginPath();
    ctx.rect(t.x - R * 0.75, t.y - 116, R * 1.5, 30);
    ctx.fill(); ctx.stroke();
    // 頂蓋（橙紅，跟樓房屋頂同色系）
    ctx.fillStyle = hot ? '#ffd35c' : '#d06a3c';
    ctx.beginPath();
    ctx.moveTo(t.x - R * 0.9, t.y - 116);
    ctx.lineTo(t.x, t.y - 138);
    ctx.lineTo(t.x + R * 0.9, t.y - 116);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  // 園區核心：外圈防護光環＋中央建築（純 Canvas 畫，無外部資產）
  function drawCore(ctx) {
    const R = BAL.core.radius;
    const hpPct = Math.max(0, Math.min(1, CORE.hp / CORE.maxHp));
    // 防護圈
    ctx.save();
    ctx.strokeStyle = hpPct > 0.6 ? 'rgba(90,220,170,0.35)' : hpPct > 0.3 ? 'rgba(240,190,80,0.45)' : 'rgba(240,90,80,0.55)';
    ctx.lineWidth = 3;
    ctx.setLineDash([12, 10]);
    ctx.lineDashOffset = -(performance.now() / 60) % 22;   // 緩慢旋轉＝運作中
    ctx.beginPath();
    ctx.arc(CORE.x, CORE.y, R, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
    // 內圈地板（v0.2.2：疊層調透，讓核心磚紋理透出來）
    const g = ctx.createRadialGradient(CORE.x, CORE.y, 8, CORE.x, CORE.y, R);
    g.addColorStop(0, 'rgba(70,90,80,0.30)');
    g.addColorStop(1, 'rgba(40,52,46,0.12)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(CORE.x, CORE.y, R, 0, Math.PI * 2);
    ctx.fill();
    // 中央建築（主樓）：矩形塔＋窗格
    ctx.fillStyle = 'rgba(30,36,44,0.95)';
    ctx.strokeStyle = 'rgba(150,170,190,0.75)';
    ctx.lineWidth = 2;
    ctx.fillRect(CORE.x - 34, CORE.y - 52, 68, 60);
    ctx.strokeRect(CORE.x - 34, CORE.y - 52, 68, 60);
    ctx.fillStyle = 'rgba(255,211,92,0.85)';
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 3; c++) {
        if ((r + c) % 2 === 0) continue;
        ctx.fillRect(CORE.x - 26 + c * 18, CORE.y - 44 + r * 15, 10, 8);
      }
    }
    ctx.fillStyle = 'rgba(240,166,60,0.9)';
    ctx.fillRect(CORE.x - 34, CORE.y - 56, 68, 6);   // 頂部招牌
    // 血條
    const bw = 120, bh = 8;
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    ctx.fillRect(CORE.x - bw / 2, CORE.y - 76, bw, bh);
    ctx.fillStyle = hpPct > 0.6 ? '#5ee0a0' : hpPct > 0.3 ? '#e0b14c' : '#e05a47';
    ctx.fillRect(CORE.x - bw / 2 + 1, CORE.y - 76 + 1, (bw - 2) * hpPct, bh - 2);
    ctx.restore();
  }

  // ===== 啟動 =====
  // 造型＋怪造型都預載完才開始（怪造型沒載完就開打會看不到怪）
  bootDoll()
    .then(() => Mobs.preload())
    .then(() => { $('btnStart').disabled = false; $('menuHint').textContent = '造型已就緒'; })
    .catch(() => { $('btnStart').disabled = false; $('menuHint').textContent = '造型載入失敗，用替代圖上陣'; });
  Engine.loadTextures(() => { /* 紋理載入完就緒（失敗自動退回網格）*/ });
  requestAnimationFrame(loop);
})();
