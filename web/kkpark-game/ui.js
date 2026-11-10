'use strict';
/* ui.js — HUD、面板、傷害飛字、虛擬搖桿（canvas 之外的全部 DOM 視圖） */

const UI = (() => {
  const $ = (id) => document.getElementById(id);
  const els = {
    hud: $('hud'), timer: $('hudTimer'), kills: $('hudKills'), gold: $('hudGold'),
    level: $('hudLevel'), xpFill: $('xpFill'), weapons: $('hudWeapons'),
    bossBar: $('bossBar'), bossName: $('bossName'), bossFill: $('bossFill'),
    menu: $('menu'), menuRecord: $('menuRecord'),
    levelup: $('levelup'), lvupCards: $('lvupCards'),
    chest: $('chest'), chestReward: $('chestReward'), btnChestOk: $('btnChestOk'),
    pausePanel: $('pausePanel'), pauseBuild: $('pauseBuild'),
    gameover: $('gameover'), goTitle: $('goTitle'), goStats: $('goStats'), goRecord: $('goRecord'),
    fxLayer: $('fxLayer'), joystick: $('joystick'), joyKnob: $('joyKnob'),
  };
  const panels = ['menu', 'levelup', 'chest', 'pausePanel', 'gameover', 'bossBar'];

  /* ===== 虛擬搖桿：按下位置即中心，拖動算方向 ===== */
  const joy = { active: false, dx: 0, dy: 0 };
  let joyCX = 0, joyCY = 0;

  document.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button, .card, .overlay')) return;
    if (typeof G === 'undefined' || G.state !== 'playing') return;
    joy.active = true;
    joy.dx = 0; joy.dy = 0;
    joyCX = e.clientX; joyCY = e.clientY;
    els.joystick.style.left = joyCX + 'px';
    els.joystick.style.top = joyCY + 'px';
    els.joyKnob.style.transform = 'translate(-50%, -50%)';
    els.joystick.classList.remove('hidden');
  });
  document.addEventListener('pointermove', (e) => {
    if (!joy.active) return;
    let dx = e.clientX - joyCX, dy = e.clientY - joyCY;
    const len = Math.hypot(dx, dy), max = 40;
    if (len > max) { dx = (dx / len) * max; dy = (dy / len) * max; }
    joy.dx = dx / max; joy.dy = dy / max;
    els.joyKnob.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;
  });
  const joyEnd = () => {
    joy.active = false; joy.dx = 0; joy.dy = 0;
    els.joystick.classList.add('hidden');
  };
  document.addEventListener('pointerup', joyEnd);
  document.addEventListener('pointercancel', joyEnd);

  /* ===== 面板 ===== */
  function hideAll() {
    panels.forEach((k) => els[k].classList.add('hidden'));
  }
  function showGame() {
    hideAll();
    els.hud.classList.remove('hidden');
  }
  function showMenu(record) {
    hideAll();
    els.hud.classList.add('hidden');
    els.menu.classList.remove('hidden');
    els.menuRecord.textContent = record ? `最高紀錄：💥 ${record.kills} 擊殺 · Lv.${record.level}` : '';
    stopFloat();
  }
  function showLevelup(choices, onPick) {
    els.levelup.classList.remove('hidden');
    els.lvupCards.innerHTML = '';
    choices.forEach((c) => {
      const card = document.createElement('div');
      card.className = 'card ' + c.kind;
      card.innerHTML =
        `<div class="icon">${c.icon}</div>` +
        `<div class="body"><div class="name">${c.name}` +
        (c.lvText ? `<span class="lv${c.maxed ? ' max' : ''}">${c.lvText}</span>` : '') +
        `</div><div class="desc">${c.desc}</div></div>`;
      card.onclick = () => { els.levelup.classList.add('hidden'); onPick(c); };
      els.lvupCards.appendChild(card);
    });
  }
  function showChest(html, onOk) {
    els.chest.classList.remove('hidden');
    els.chestReward.innerHTML = html;
    els.btnChestOk.onclick = () => { els.chest.classList.add('hidden'); onOk(); };
  }
  function showPause(html) {
    els.pausePanel.classList.remove('hidden');
    els.pauseBuild.innerHTML = html;
  }
  function hidePause() { els.pausePanel.classList.add('hidden'); }
  function showGameOver(o) {
    hideAll();
    els.hud.classList.add('hidden');
    els.gameover.classList.remove('hidden');
    els.goTitle.textContent = o.win ? '🏆 園區傳說達成！' : '💥 被黑粉淹沒了';
    const m = Math.floor(o.time / 60), s = Math.floor(o.time % 60);
    els.goStats.innerHTML =
      `<div class="stat${o.win ? ' win' : ''}"><b>${o.kills}</b>擊殺</div>` +
      `<div class="stat"><b>${o.gold}</b>金幣</div>` +
      `<div class="stat"><b>Lv.${o.level}</b>等級</div>` +
      `<div class="stat"><b>${m}:${String(s).padStart(2, '0')}</b>存活</div>`;
    els.goRecord.textContent = o.isNew ? '🎉 新紀錄！' : '';
    stopFloat();
  }

  /* ===== HUD 即時更新 ===== */
  function updateHud(g) {
    const t = Math.max(0, Math.ceil(RUN_TIME - g.time));
    els.timer.textContent = `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
    els.kills.textContent = `💥 ${g.kills}`;
    els.gold.textContent = `🪙 ${g.gold}`;
    els.level.textContent = `Lv.${g.level}`;
    els.xpFill.style.width = Math.min(100, (g.xp / g.xpNeed) * 100) + '%';
  }
  let bossShown = false;
  function updateBoss(boss) {
    if (!boss) {
      if (bossShown) { els.bossBar.classList.add('hidden'); bossShown = false; }
      return;
    }
    if (!bossShown) { els.bossBar.classList.remove('hidden'); bossShown = true; }
    els.bossName.textContent = boss.name;
    els.bossFill.style.width = Math.max(0, Math.min(100, (boss.hp / boss.maxHp) * 100)) + '%';
  }
  function updateWeaponChips(list) {
    els.weapons.innerHTML = list
      .map((w) => `<span class="wchip${w.evolved ? ' evo' : ''}">${w.icon} ${w.name} <b>Lv.${w.lv}${w.evolved ? ' ★' : ''}</b></span>`)
      .join('');
  }

  /* ===== 傷害飛字（DOM，上限 60 顆） ===== */
  let floatN = 0;
  function floatText(sx, sy, text, cls = '') {
    if (floatN >= 60) return;
    const el = document.createElement('div');
    el.className = 'dmg-float' + (cls ? ' ' + cls : '');
    el.textContent = text;
    el.style.left = sx + 'px';
    el.style.top = sy + 'px';
    els.fxLayer.appendChild(el);
    floatN++;
    setTimeout(() => { el.remove(); floatN--; }, 700);
  }
  function stopFloat() {
    els.fxLayer.innerHTML = '';
    floatN = 0;
  }

  return {
    els, joy,
    showGame, showMenu, showLevelup, showChest, showPause, hidePause, showGameOver,
    updateHud, updateBoss, updateWeaponChips, floatText, stopFloat,
  };
})();
