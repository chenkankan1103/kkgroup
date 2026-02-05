/**
 * Google Sheet 清理腳本
 * 用於移除污染的欄位和恢復正確的表頭結構
 */

/**
 * 清理 SHEET 結構
 * 移除：
 * 1. 中文預設欄位（第 1 欄, 第 2 欄, 第 3 欄）
 * 2. 不必要的舊欄位
 * 3. 保留核心欄位
 */
function cleanupSheetStructure() {
  try {
    Logger.log("🧹 開始清理 SHEET 結構...");
    
    const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = spreadsheet.getSheetByName('玩家資料');
    
    if (!sheet) {
      alert("❌ 找不到「玩家資料」工作頁");
      return;
    }
    
    // 1. 取得現有表頭
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    Logger.log("📋 現有表頭：" + headers.join(", "));
    
    // 2. 定義需保留的欄位（按優先順序）
    const coreColumns = [
      'user_id',        // 必須：主鍵
      'nickname',       // 必須：玩家名稱
      'level',          // 常用：等級
      'xp',             // 常用：經驗
      'kkcoin',         // 常用：貨幣
      'hp',             // 常用：生命值
      'stamina',        // 常用：體力
      'gender',         // 常用：性別
      'title',          // 常用：標題
      'streak',         // 常用：連勝
      'vip_level'       // 常用：VIP等級
    ];
    
    // 3. 找出要刪除的欄位
    const columnsToDelete = [];
    
    headers.forEach((header, index) => {
      const headerLower = (header || '').toString().toLowerCase().trim();
      
      // 刪除中文預設欄位
      if (headerLower.includes('第') && headerLower.includes('欄')) {
        columnsToDelete.push({ index: index + 1, reason: '中文預設欄位' });
        return;
      }
      
      // 刪除舊的狀態字段
      if (['is_stunned', 'is_locked', 'thread_id', 'actions_used', 
           'last_recovery', 'injury_recovery_time', 'last_work_date',
           'last_action_date', 'last_check_in', 'last_heal'].includes(headerLower)) {
        columnsToDelete.push({ index: index + 1, reason: '舊狀態字段' });
        return;
      }
      
      // 刪除角色外觀字段（通常不需要同步）
      if (['face', 'hair', 'skin', 'top', 'bottom', 'shoes', 'accessories',
           'avatar', 'appearance'].includes(headerLower)) {
        columnsToDelete.push({ index: index + 1, reason: '外觀字段' });
        return;
      }
    });
    
    // 4. 執行刪除（從後往前，避免索引混亂）
    if (columnsToDelete.length > 0) {
      Logger.log(`⚠️ 要刪除 ${columnsToDelete.length} 個欄位：`);
      
      columnsToDelete.sort((a, b) => b.index - a.index);  // 從後往前排序
      
      columnsToDelete.forEach(col => {
        Logger.log(`  • 欄位 ${col.index}: ${col.reason}`);
        sheet.deleteColumn(col.index);
      });
      
      Logger.log(`✅ 已刪除 ${columnsToDelete.length} 個欄位`);
    } else {
      Logger.log("✅ 沒有需要刪除的欄位");
    }
    
    // 5. 取得預期的新表頭
    const newHeaders = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    Logger.log("📋 清理後表頭：" + newHeaders.join(", "));
    
    // 6. 驗證核心欄位
    const missingCores = coreColumns.filter(col => 
      !newHeaders.some(h => h && h.toString().toLowerCase().trim() === col.toLowerCase())
    );
    
    if (missingCores.length > 0) {
      Logger.log("⚠️ 警告：缺少核心欄位：" + missingCores.join(", "));
    }
    
    alert("✅ 清理完成！\n\n清理後表頭：\n" + newHeaders.join(", "));
    
  } catch (error) {
    Logger.log("❌ 錯誤：" + error);
    alert("❌ 清理失敗：" + error);
  }
}

/**
 * 一鍵修復 SHEET
 * 刪除所有污染欄位
 */
function fixSheetCompletely() {
  try {
    Logger.log("🔧 開始完整修復 SHEET...");
    
    const ui = SpreadsheetApp.getUi();
    const response = ui.alert(
      '⚠️ 此操作將刪除污染的欄位\n\n' +
      '刪除欄位：\n' +
      '• 中文預設欄位（第 1 欄, 第 2 欄, 第 3 欄）\n' +
      '• 舊狀態字段（is_stunned, is_locked, actions_used 等）\n' +
      '• 外觀字段（face, hair, skin 等）\n\n' +
      '是否繼續？',
      ui.ButtonSet.YES_NO
    );
    
    if (response !== ui.Button.YES) {
      Logger.log("⏹️ 用戶取消了操作");
      return;
    }
    
    cleanupSheetStructure();
    
  } catch (error) {
    Logger.log("❌ 修復失敗：" + error);
    alert("❌ 修復失敗：" + error);
  }
}

/**
 * 在菜單中添加清理選項
 */
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('🔧 SHEET 修復工具')
    .addItem('🔧 一鍵清理污染欄位', 'fixSheetCompletely')
    .addToUi();
}
