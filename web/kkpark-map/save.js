'use strict';
/* save.js — localStorage 自動存檔／讀檔 */

const Save = (() => {
  const KEY = 'kkpark_map_save_v1';

  function write(s) {
    try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* 隱私模式等，靜默 */ }
  }
  function read() {
    try {
      const r = localStorage.getItem(KEY);
      return r ? JSON.parse(r) : null;
    } catch (e) { return null; }
  }
  function clear() {
    try { localStorage.removeItem(KEY); } catch (e) { /* noop */ }
  }
  return { write, read, clear };
})();
