'use strict';
/* looks.js — 角色外型表（楓之谷紙娃娃部件 ID 組合）
   ID 來源：twms_fashion_db.json（VM 的紙娃娃 DB），繁中名稱篩選：
   俐落鐵鎚制服 1050478 / 鐵鎚制服帽 1004964 / 黑西裝 1040001 / 黑西褲 1060001
   黑色領帶襯衫 1042129 / 帥氣黑帽 1006138 / 英式軍裝上衣 1042181 / 軍用毛帽 1002488
   白藍領西裝 1042046 / 褐色西裝帽 1002804 / 午夜墨鏡 1006094 / 藍色合身褲 1060113
   每個 look 都是 {face, hair, top, bottom, shoes, hat?} → 直接餵 maplestory.io URL。

   為什麼用 ID 不用 AI 生圖：官方設計、風格 100% 一致、零生成成本、體積只有幾 KB。
*/

// 臉/髮候選（避開可愛系，選成熟/普通型）
const LOOK_FACES = [20005, 20006, 20007, 20008, 20101, 20201, 20301, 20401];
const LOOK_HAIRS = [30120, 30121, 30122, 30130, 30200, 30220, 31000, 32000];
const LOOK_SHOES = [1072005, 1073002, 1071003, 1072663, 1073181, 1073681];

// ===== 角色外型 =====
// ID 來自繁中篩選 + 視覺判定（外型板 board-police.png 判讀結果）：
//   俐落鐵鎚制服 1050478 深藍制服＋金扣 → 44px 剪影最清楚（主選巡查員）
//   鐵鎚制服帽 1004964 金星大盤帽（有帽徽）
//   軍帽 1004763 深色制服版（隊長）
//   墨鏡白襯衫 1042140 ＋ 午夜墨鏡 1006094 → 偵探感（副選便衣）
//   海藍襯衫 1042329 ＋ 藍色徽章帽 1002346 → 亮色制服（第三選擇）
const LOOKS = {
  // 保全巡查員：俐落鐵鎚制服＋鐵鎚制服帽
  patrol: {
    label: '保全巡查員',
    top: 1050478, bottom: 1060001, shoes: 1073002,
    hat: 1004964,
    faces: [20005, 20007, 20008], hairs: [30120, 30121, 30200],
  },
  // 便衣巡查：黑西裝＋帥氣黑帽（不用 accessory 墨鏡——那會疊在頭上像護目鏡）
  plainclothes: {
    label: '便衣巡查',
    top: 1040001, bottom: 1060001, shoes: 1072005,
    hat: 1006138, accessory: 0,
    faces: [20006, 20007, 20201], hairs: [30122, 30130, 30220],
  },
  // 幹部/隊長：同一套俐落鐵鎚制服＋深色軍帽（深色系寫實路線）
  commander: {
    label: '巡邏隊長',
    top: 1050478, bottom: 1060116, shoes: 1072663,
    hat: 1004763,
    faces: [20005, 20008, 20401], hairs: [30120, 30200, 31000],
  },
  // 亮色制服巡查：海藍襯衫＋藍色徽章帽（44px 亮度最高、徽章最明顯）
  officer: {
    label: '制服巡查',
    top: 1042329, bottom: 1060113, shoes: 1073002,
    hat: 1002346,
    faces: [20006, 20101, 20301], hairs: [30121, 30220, 32000],
  },
  // 打手（基層）：黑領帶襯衫，無帽
  thug: {
    label: '打手',
    top: 1042129, bottom: 1060001, shoes: 1073181,
    hat: 0,
    faces: [20007, 20008, 20301], hairs: [30122, 30130, 31000],
  },
};

// ===== 依 look 與 seed 決定出一套具體 ID（穩定：同 seed 永遠同一套）=====
function lookHash(seed, salt) {
  let h = salt | 0;
  const s = String(seed);
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 2654435761) | 0;
  return Math.abs(h);
}
function resolveLook(key, seed) {
  const L = LOOKS[key];
  if (!L) return null;
  const pick = (arr, salt) => arr[lookHash(seed + key, salt) % arr.length];
  const out = {
    face: pick(L.faces || LOOK_FACES, 11),
    hair: pick(L.hairs || LOOK_HAIRS, 13),
    top: L.top, bottom: L.bottom, shoes: pick(LOOK_SHOES, 17),
    hat: L.hat || 0,
    accessory: L.accessory || 0,
  };
  return out;
}

// URL 公式的唯一來源在 player.js 的 dollUrl()（避免兩份公式漂移）
// 這裡只負責「外型定義」與「依 seed 抽出具體 ID」，不碰 URL。
