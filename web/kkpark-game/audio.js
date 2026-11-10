'use strict';
/* audio.js — WebAudio 合成音效（零音檔依賴），第一次使用者互動才建 AudioContext */

const Sfx = (() => {
  let ctx = null;
  let master = null;
  let muted = false;

  function ensure() {
    if (!ctx) {
      try {
        ctx = new (window.AudioContext || window.webkitAudioContext)();
        master = ctx.createGain();
        master.gain.value = 0.28;
        master.connect(ctx.destination);
      } catch (e) {
        return null; // 無音訊環境，靜默降級
      }
    }
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  // 單音：freq 起始頻率 → end 結尾頻率（exponential 滑音）
  function tone({ freq = 440, end = 0, dur = 0.1, type = 'square', vol = 1, delay = 0 }) {
    if (muted || !ensure()) return;
    const t0 = ctx.currentTime + delay;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = type;
    o.frequency.setValueAtTime(freq, t0);
    if (end) o.frequency.exponentialRampToValueAtTime(Math.max(1, end), t0 + dur);
    g.gain.setValueAtTime(vol, t0);
    g.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
    o.connect(g);
    g.connect(master);
    o.start(t0);
    o.stop(t0 + dur + 0.02);
  }

  // 白噪爆音（打擊／爆炸感）
  function noise({ dur = 0.12, vol = 0.6, freq = 900 }) {
    if (muted || !ensure()) return;
    const n = Math.floor(ctx.sampleRate * dur);
    const buf = ctx.createBuffer(1, n, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const f = ctx.createBiquadFilter();
    f.type = 'lowpass';
    f.frequency.value = freq;
    const g = ctx.createGain();
    g.gain.value = vol;
    src.connect(f);
    f.connect(g);
    g.connect(master);
    src.start();
  }

  return {
    unlock: ensure,
    toggleMute() {
      muted = !muted;
      return muted;
    },
    get muted() {
      return muted;
    },
    shoot() {
      tone({ freq: 720, end: 380, dur: 0.06, type: 'square', vol: 0.22 });
    },
    hit() {
      noise({ dur: 0.05, vol: 0.35, freq: 1100 });
    },
    kill() {
      noise({ dur: 0.11, vol: 0.45, freq: 600 });
      tone({ freq: 200, end: 60, dur: 0.11, type: 'sawtooth', vol: 0.3 });
    },
    pickup() {
      tone({ freq: 880, end: 1320, dur: 0.07, type: 'sine', vol: 0.3 });
    },
    gold() {
      tone({ freq: 1200, dur: 0.05, type: 'sine', vol: 0.28 });
      tone({ freq: 1600, dur: 0.07, type: 'sine', vol: 0.24, delay: 0.05 });
    },
    levelup() {
      [523, 659, 784, 1047].forEach((f, i) =>
        tone({ freq: f, dur: 0.13, type: 'square', vol: 0.3, delay: i * 0.07 })
      );
    },
    hurt() {
      tone({ freq: 220, end: 90, dur: 0.17, type: 'sawtooth', vol: 0.45 });
    },
    chest() {
      [784, 988, 1175, 1568].forEach((f, i) =>
        tone({ freq: f, dur: 0.15, type: 'triangle', vol: 0.35, delay: i * 0.08 })
      );
    },
    boss() {
      tone({ freq: 110, end: 55, dur: 0.55, type: 'sawtooth', vol: 0.5 });
      tone({ freq: 165, end: 82, dur: 0.55, type: 'square', vol: 0.25, delay: 0.1 });
    },
    evolve() {
      [659, 784, 1047, 1319, 1568].forEach((f, i) =>
        tone({ freq: f, dur: 0.17, type: 'triangle', vol: 0.35, delay: i * 0.09 })
      );
    },
    gameover() {
      [392, 330, 262, 196].forEach((f, i) =>
        tone({ freq: f, dur: 0.3, type: 'sawtooth', vol: 0.35, delay: i * 0.22 })
      );
    },
    win() {
      [523, 659, 784, 1047, 784, 1047, 1319].forEach((f, i) =>
        tone({ freq: f, dur: 0.2, type: 'square', vol: 0.35, delay: i * 0.16 })
      );
    },
  };
})();
