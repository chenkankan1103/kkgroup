/**
 * Google Apps Script - SHEET 與資料庫同步工具 (修復浮點精度)
 * 
 * 🔧 修復：確保 Discord ID 以字符串形式發送，避免浮點精度損失
 */

// ============================================================
// 設定區
// ============================================================

const CONFIG_SHEET_NAME = '系統配置';
const CONFIG_KEY_API_ENDPOINT = 'API_ENDPOINT';
const DEFAULT_API_ENDPOINT = "http://35.206.126.157:5000";

/**
 * 動態獲取 API 端點（從 Google Sheet 讀取）
 */
function getAPIEndpoint() {
  try {
    const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    const configSheet = spreadsheet.getSheetByName(CONFIG_SHEET_NAME);
    
    if (!configSheet) {
      Logger.log(`⚠️ 找不到「${CONFIG_SHEET_NAME}」工作頁，使用預設值`);
      return DEFAULT_API_ENDPOINT;
    }
    
    const configData = configSheet.getDataRange().getValues();
    for (let row = 1; row < configData.length; row++) {
      const keyCell = configData[row][0];
      const valueCell = configData[row][1];
      
      if (keyCell && keyCell.toString().trim() === CONFIG_KEY_API_ENDPOINT) {
        const endpoint = valueCell.toString().trim();
        if (endpoint && endpoint.length > 0) {
          Logger.log(`✅ 從「${CONFIG_SHEET_NAME}」讀取 API_ENDPOINT: ${endpoint}`);
          return endpoint;
        }
      }
    }
    
    Logger.log(`⚠️ 未找到配置，使用預設值`);
    return DEFAULT_API_ENDPOINT;
  } catch (error) {
    Logger.log(`❌ 讀取配置出錯: ${error.toString()}`);
    return DEFAULT_API_ENDPOINT;
  }
}

/**
 * 🔧 修復：转换值为适当的类型，确保 ID 为字符串
 * 
 * 目的：防止 JSON.stringify 将大整数转换为浮点数
 */
function convertValueForAPI(value, columnName) {
  if (value === null || value === undefined || value === '') {
    return '';
  }
  
  const colNameLower = columnName.toString().toLowerCase();
  
  // 🔑 关键修复：ID 列必须转换为字符串（保留精度）
  if (colNameLower.includes('id') || colNameLower.includes('user_id')) {
    // 将 ID 转换为字符串，避免浮点数精度损失
    const idStr = value.toString().trim();
    
    // 如果是科学计数法，先转为数字，再转为字符串
    if (idStr.toLowerCase().includes('e')) {
      try {
        const numValue = Number(idStr);
        if (!isNaN(numValue) && numValue > 0) {
          return Math.floor(numValue).toString();
        }
      } catch (e) {
        Logger.log(`⚠️ 无法转换科学计数法 ID: ${idStr}`);
      }
    }
    
    return idStr;
  }
  
  // 其他数值列保持为数字
  if (colNameLower.includes('level') || colNameLower.includes('xp') || 
      colNameLower.includes('coin') || colNameLower.includes('kkcoin') ||
      colNameLower.includes('hp') || colNameLower.includes('stamina')) {
    const num = Number(value);
    return isNaN(num) ? '' : num;
  }
  
  // 其他列保持为字符串
  return value.toString();
}

/**
 * 初始化功能表（在打開 SHEET 時自動執行）
 */
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('🔄 同步工具')
    .addItem('📤 同步到資料庫', 'syncToDatabase')
    .addItem('📥 從資料庫同步', 'syncFromDatabase')
    .addItem('📊 查看同步狀態', 'showSyncStatus')
    .addItem('🧹 清理虛擬帳號', 'cleanVirtualAccounts')
    .addSeparator()
    .addItem('✅ 檢查 API 連接', 'checkAPIHealth')
    .addItem('⚙️ 系統配置說明', 'showConfigGuide')
    .addToUi();
}

/**
 * 顯示系統配置說明
 */
function showConfigGuide() {
  const message = `⚙️ 系統配置說明\n\n` +
    `1️⃣ 建立「系統配置」工作頁\n` +
    `   在 Google Sheet 中新增工作頁，命名為「系統配置」\n\n` +
    `2️⃣ 設置表頭（第 1 行）\n` +
    `   A1: 設定名稱\n` +
    `   B1: 設定值\n\n` +
    `3️⃣ 添加配置（第 2 行）\n` +
    `   A2: API_ENDPOINT\n` +
    `   B2: http://你的IP:5000\n\n` +
    `📌 當 GCP IP 變更時，直接更新 B2 的值！\n` +
    `不需要修改代碼`;
  
  SpreadsheetApp.getUi().alert(message);
}

/**
 * 同步 SHEET 資料到資料庫（修復浮點精度）
 */
function syncToDatabase() {
  try {
    Logger.log("⏳ 開始同步...");
    
    const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = spreadsheet.getSheetByName('玩家資料');
    
    if (!sheet) {
      SpreadsheetApp.getUi().alert("❌ 找不到「玩家資料」工作頁，請確認工作頁名稱是否正確");
      return;
    }
    
    const allData = sheet.getDataRange().getValues();
    
    if (allData.length < 2) {
      SpreadsheetApp.getUi().alert("❌ 資料不足（至少需要 2 行：表頭、資料）");
      return;
    }
    
    const headers = allData[0];
    const rows = allData.slice(1);
    
    Logger.log(`📋 表頭: ${headers.slice(0, 5).join(', ')}...`);
    Logger.log(`📊 資料行數: ${rows.length}`);
    
    const userIdIndex = headers.findIndex(h => h && h.toString().toLowerCase() === 'user_id');
    
    if (userIdIndex === -1) {
      SpreadsheetApp.getUi().alert("❌ 找不到 'user_id' 欄位，請確認表頭設置正確");
      return;
    }
    
    Logger.log(`📍 user_id 列索引: ${userIdIndex}`);
    
    // 🔧 修復：轉換資料行，確保 ID 為字符串
    const convertedRows = rows.filter((row, rowIndex) => {
      const userIdValue = row[userIdIndex];
      
      if (!userIdValue || userIdValue.toString().trim() === '') {
        Logger.log(`⚠️ 跳過第 ${rowIndex + 2} 行：user_id 為空`);
        return false;
      }
      
      const userIdNum = Number(userIdValue);
      if (isNaN(userIdNum) || userIdNum <= 0) {
        Logger.log(`⚠️ 跳過第 ${rowIndex + 2} 行：user_id '${userIdValue}' 無效`);
        return false;
      }
      
      // 🔑 關鍵修復：轉換每個值，確保 ID 為字符串
      const convertedRow = row.map((value, colIndex) => {
        const columnName = headers[colIndex];
        return convertValueForAPI(value, columnName);
      });
      
      Logger.log(`   ✓ 行 ${rowIndex + 2}: user_id=${convertedRow[userIdIndex]} (類型: ${typeof convertedRow[userIdIndex]})`);
      
      return true;
    }).map((row, rowIndex) => {
      return row.map((value, colIndex) => {
        const columnName = headers[colIndex];
        return convertValueForAPI(value, columnName);
      });
    });
    
    Logger.log(`📊 有效資料行數: ${convertedRows.length}`);
    
    if (convertedRows.length === 0) {
      SpreadsheetApp.getUi().alert("❌ 沒有有效的資料行（需要有非空且有效的 user_id）");
      return;
    }
    
    // 2. 準備請求體（含轉換後的資料）
    const payload = {
      headers: headers,
      rows: convertedRows
    };
    
    // 3. 呼叫 API
    const apiEndpoint = getAPIEndpoint();
    Logger.log(`🌐 呼叫 API: POST ${apiEndpoint}/api/sync`);
    Logger.log(`📤 傳送 ${convertedRows.length} 筆記錄（ID 已轉換為字符串）`);
    
    const options = {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };
    
    const response = UrlFetchApp.fetch(`${apiEndpoint}/api/sync`, options);
    const result = JSON.parse(response.getContentText());
    
    Logger.log(`📥 API 回應: ${JSON.stringify(result, null, 2)}`);
    
    // 4. 顯示結果
    if (result.status === 'success') {
      const stats = result.stats;
      
      let message = `✅ 同步完成！\n\n`;
      message += `新增: ${stats.inserted} 筆\n`;
      message += `更新: ${stats.updated} 筆\n`;
      message += `重複: ${stats.duplicates || 0} 筆\n`;
      message += `錯誤: ${stats.errors} 筆\n`;
      
      if (stats.errors > 0 && result.error_details && result.error_details.length > 0) {
        message += `\n🔍 錯誤詳情（前 5 筆）:\n`;
        for (let i = 0; i < Math.min(5, result.error_details.length); i++) {
          const err = result.error_details[i];
          message += `  ❌ 記錄 ${err.record}: ${err.reason}\n`;
        }
        if (result.error_details.length > 5) {
          message += `  ... 還有 ${result.error_details.length - 5} 個錯誤\n`;
        }
        message += `\n檢查 Google Sheet 中的資料格式\n`;
      }
      
      SpreadsheetApp.getUi().alert(message);
      Logger.log(`✅ ${message}`);
    } else {
      const message = `❌ 同步失敗\n\n錯誤: ${result.message}`;
      SpreadsheetApp.getUi().alert(message);
      Logger.log(`❌ ${message}`);
    }
  
  } catch (error) {
    const message = `❌ 執行錯誤: ${error.toString()}\n\n請檢查：\n1. API 伺服器是否正常運行\n2. API 位址是否正確\n3. 檢查上面的「✅ 檢查 API 連接」測試`;
    SpreadsheetApp.getUi().alert(message);
    Logger.log(`❌ ${message}`);
  }
}

/**
 * 查看同步狀態（API 統計資訊）
 */
function showSyncStatus() {
  try {
    Logger.log("⏳ 取得資料庫狀態...");
    
    const apiEndpoint = getAPIEndpoint();
    const options = {
      method: 'get',
      muteHttpExceptions: true
    };
    
    const response = UrlFetchApp.fetch(`${apiEndpoint}/api/stats`, options);
    const result = JSON.parse(response.getContentText());
    
    if (result.status === 'ok') {
      const stats = result.stats;
      const message = `📊 資料庫統計\n\n` +
        `真實玩家: ${stats.real_users} 人\n` +
        `虛擬帳號: ${stats.virtual_accounts} 個\n` +
        `總玩家: ${stats.total_users} 人\n\n` +
        `KKCoin 總計: ${stats.total_kkcoin}\n\n` +
        `欄位數: ${stats.total_columns}`;
      SpreadsheetApp.getUi().alert(message);
      Logger.log(message);
    } else {
      SpreadsheetApp.getUi().alert("❌ 無法取得統計資訊");
    }
  
  } catch (error) {
    SpreadsheetApp.getUi().alert(`❌ 錯誤: ${error.toString()}`);
  }
}

/**
 * 清理虛擬帳號
 */
function cleanVirtualAccounts() {
  try {
    const ui = SpreadsheetApp.getUi();
    const response = ui.alert('⚠️ 確認清理虛擬帳號？', ui.ButtonSet.YES_NO);
    
    if (response !== ui.Button.YES) {
      Logger.log("❌ 取消清理");
      return;
    }
    
    Logger.log("⏳ 清理虛擬帳號...");
    
    const apiEndpoint = getAPIEndpoint();
    const options = {
      method: 'post',
      muteHttpExceptions: true
    };
    
    const result_response = UrlFetchApp.fetch(`${apiEndpoint}/api/clean-virtual`, options);
    const result = JSON.parse(result_response.getContentText());
    
    if (result.status === 'success' || result.status === 'warning') {
      const message = `✅ ${result.message}\n\n刪除數: ${result.stats.deleted}`;
      SpreadsheetApp.getUi().alert(message);
      Logger.log(message);
    } else {
      SpreadsheetApp.getUi().alert(`❌ 清理失敗: ${result.message}`);
    }
  
  } catch (error) {
    SpreadsheetApp.getUi().alert(`❌ 錯誤: ${error.toString()}`);
  }
}

/**
 * 從資料庫同步數據到 SHEET（反向同步）
 */
function syncFromDatabase() {
  try {
    Logger.log("⏳ 從資料庫同步數據...");
    
    const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    let sheet = spreadsheet.getSheetByName('玩家資料');
    let sheetHeaders = null;
    
    if (sheet && sheet.getLastRow() > 0) {
      const headerRow = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      sheetHeaders = headerRow.filter(h => h && h.toString().trim() !== '');
      Logger.log(`📋 當前 SHEET 表頭: ${sheetHeaders.join(', ')}`);
    }
    
    const apiEndpoint = getAPIEndpoint();
    Logger.log(`🌐 呼叫 API: POST ${apiEndpoint}/api/export`);
    
    const exportPayload = {};
    if (sheetHeaders && sheetHeaders.length > 0) {
      exportPayload.headers = sheetHeaders;
      Logger.log(`📤 傳送 SHEET 表頭順序到 API（${sheetHeaders.length} 欄位）`);
    }
    
    const options = {
      method: sheetHeaders && sheetHeaders.length > 0 ? 'post' : 'get',
      contentType: 'application/json',
      muteHttpExceptions: true
    };
    
    if (sheetHeaders && sheetHeaders.length > 0) {
      options.payload = JSON.stringify(exportPayload);
    }
    
    const response = UrlFetchApp.fetch(`${apiEndpoint}/api/export`, options);
    const statusCode = response.getResponseCode();
    const result = JSON.parse(response.getContentText());
    
    if (statusCode !== 200 || result.status !== 'success') {
      Logger.log(`❌ API 錯誤: ${result.message}`);
      SpreadsheetApp.getUi().alert(`❌ 同步失敗\n\n錯誤: ${result.message}`);
      return;
    }
    
    const headers = result.headers;
    const rows = result.rows;
    
    Logger.log(`📥 取得資料: ${headers.length} 欄位, ${rows.length} 行`);
    Logger.log(`📋 返回表頭: ${headers.slice(0, 10).join(', ')}${headers.length > 10 ? '...' : ''}`);
    
    if (!sheet) {
      Logger.log("⚠️ 找不到「玩家資料」工作頁，創建新工作頁...");
      sheet = spreadsheet.insertSheet('玩家資料');
    }
    
    try {
      if (sheet.getMaxRows() > 1) {
        const lastRow = sheet.getLastRow();
        if (lastRow > 1) {
          const rowsToDelete = lastRow - 1;
          if (rowsToDelete > 0) {
            sheet.deleteRows(2, Math.min(rowsToDelete, 1000));
            Logger.log(`✓ 已清空 ${Math.min(rowsToDelete, 1000)} 行舊數據`);
          }
        }
      }
    } catch (e) {
      Logger.log(`⚠️ 刪除行失敗：${e}，改用覆蓋策略`);
      try {
        const currentData = sheet.getDataRange().getValues();
        if (currentData.length > 1) {
          sheet.getRange(1, 1, currentData.length, currentData[0].length).clearContent();
        }
      } catch (e2) {
        Logger.log(`警告：無法清空現有數據: ${e2}`);
      }
    }
    
    if (rows.length > 0) {
      const allData = [headers, ...rows];
      sheet.getRange(1, 1, allData.length, headers.length).setValues(allData);
      Logger.log(`✅ 已寫入 ${rows.length} 行數據`);
    } else {
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
      Logger.log("⚠️ 資料庫中沒有用戶數據");
    }
    
    const message = `✅ 同步完成！\n\n` +
      `欄位: ${headers.length} 個\n` +
      `玩家: ${rows.length} 個\n\n` +
      `訊息: ${result.message}`;
    
    SpreadsheetApp.getUi().alert(message);
    Logger.log(`✅ ${message}`);
  
  } catch (error) {
    const message = `❌ 執行錯誤: ${error.toString()}\n\n請檢查 API 伺服器是否正常運行`;
    SpreadsheetApp.getUi().alert(message);
    Logger.log(`❌ ${message}`);
  }
}

/**
 * 檢查 API 連接
 */
function checkAPIHealth() {
  try {
    Logger.log("⏳ 檢查 API 連接...");
    
    const apiEndpoint = getAPIEndpoint();
    const options = {
      method: 'get',
      muteHttpExceptions: true
    };
    
    const response = UrlFetchApp.fetch(`${apiEndpoint}/api/health`, options);
    const statusCode = response.getResponseCode();
    const responseText = response.getContentText();
    
    Logger.log(`📥 HTTP 狀態碼: ${statusCode}`);
    Logger.log(`📥 回應內容: ${responseText.substring(0, 500)}`);
    
    try {
      const result = JSON.parse(responseText);
      
      if (result.status === 'ok') {
        const message = `✅ API 連接正常\n\n${result.message}\n時間: ${result.timestamp}`;
        SpreadsheetApp.getUi().alert(message);
        Logger.log(message);
      } else {
        SpreadsheetApp.getUi().alert("❌ API 連接失敗");
      }
    } catch (parseError) {
      const message = `❌ 伺服器回應異常\n\n狀態碼: ${statusCode}\n回應: ${responseText.substring(0, 200)}`;
      SpreadsheetApp.getUi().alert(message);
      Logger.log(message);
    }
  
  } catch (error) {
    const apiEndpoint = getAPIEndpoint();
    const message = `❌ 無法連接到 API\n\n位址: ${apiEndpoint}\n錯誤: ${error.toString()}\n\n請檢查：\n1. 「系統配置」表中的 API_ENDPOINT 是否正確\n2. Flask 伺服器是否正在運行\n3. 防火牆設定`;
    SpreadsheetApp.getUi().alert(message);
    Logger.log(message);
  }
}
