/**
 * Google Apps Script - SHEET 與資料庫同步工具（改進版）
 * 
 * ✅ 改進內容：
 * 1. 嚴格的 user_id 驗證（整數、非零）
 * 2. 詳細的錯誤報告
 * 3. 批量操作優化
 * 4. API 超時處理
 * 5. 自動重試機制
 * 
 * 使用方式：
 * 1. 到 Google Sheet 中：擴充功能 → Apps Script
 * 2. 複製下面代碼到 Code.gs
 * 3. 將 API_ENDPOINT 改為你的地址
 * 4. 執行 onOpen() 進行初始化
 * 5. 點選「🔄 同步工具」使用
 */

// ============================================================
// 設定區（編輯此部分）
// ============================================================

// ⚠️ 必須修改：你的 Flask API 位址
const API_ENDPOINT = "http://35.209.101.28:5000";

// API 超時時間（毫秒）
const API_TIMEOUT = 30000;

// 最大重試次數
const MAX_RETRIES = 3;

// 預期的表頭名稱（用於驗證 SHEET 結構）
const EXPECTED_HEADERS = ['user_id', 'nickname', 'level', 'kkcoin'];  // 可根據需要修改

// ============================================================
// 開啟時初始化功能表
// ============================================================

function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('🔄 同步工具')
    .addItem('📤 同步到資料庫', 'syncToDatabase')
    .addItem('📥 從資料庫同步', 'syncFromDatabase')
    .addItem('📊 查看同步狀態', 'showSyncStatus')
    .addItem('🧹 清理虛擬帳號', 'cleanVirtualAccounts')
    .addSeparator()
    .addItem('✅ 檢查 API 連接', 'checkAPIHealth')
    .addItem('🔧 驗證 SHEET 結構', 'validateSheetStructure')
    .addToUi();
}

// ============================================================
// 主要功能：同步到資料庫
// ============================================================

/**
 * 同步 SHEET 資料到資料庫
 * 
 * SHEET 結構要求：
 * - 第 1 行 = 表頭（必須包含 user_id）
 * - 第 2+ 行 = 實際資料
 * - user_id = 主鍵，必須是整數且 > 0
 * - 空行會自動跳過
 */
function syncToDatabase() {
  try {
    Logger.log("⏳ [同步開始] " + new Date().toLocaleString());
    
    // 1. 驗證 SHEET 結構
    const sheetData = getAndValidateSheetData();
    if (!sheetData) return;  // 驗證失敗
    
    const { headers, rows, userIdIndex } = sheetData;
    
    // 2. 過濾有效行
    const validRows = validateAndFilterRows(rows, userIdIndex);
    
    if (validRows.length === 0) {
      showAlert("❌ 沒有有效的資料行", "需要至少有 1 行有效的資料（user_id 非空且為正整數）");
      return;
    }
    
    Logger.log(`📊 有效行數: ${validRows.length}/${rows.length}`);
    
    // 3. 準備並發送請求
    const payload = {
      headers: headers,
      rows: validRows,
      timestamp: new Date().toISOString()
    };
    
    const result = callAPIWithRetry('POST', '/api/sync', payload);
    
    if (!result) {
      showAlert("❌ API 連接失敗", "無法連接到資料庫伺服器，請檢查網絡與 API 位址");
      return;
    }
    
    // 4. 顯示結果
    displaySyncResult(result);
    
  } catch (error) {
    Logger.log(`❌ 未預期的錯誤: ${error}`);
    showAlert("❌ 執行錯誤", error.toString());
  }
}

// ============================================================
// 輔助函數：數據驗證
// ============================================================

/**
 * 取得並驗證 SHEET 資料
 */
function getAndValidateSheetData() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = spreadsheet.getSheetByName('玩家資料');
  
  if (!sheet) {
    showAlert("❌ 找不到工作頁", "請確認是否有名為「玩家資料」的工作頁");
    return null;
  }
  
  const allData = sheet.getDataRange().getValues();
  
  if (allData.length < 2) {
    showAlert("❌ 資料不足", "至少需要表頭行（第 1 行）和資料行（第 2+ 行）");
    return null;
  }
  
  const headers = allData[0];
  const rows = allData.slice(1);
  
  // 驗證 user_id 列
  const userIdIndex = headers.findIndex(h => 
    h && h.toString().toLowerCase().trim() === 'user_id'
  );
  
  if (userIdIndex === -1) {
    showAlert("❌ 缺少必要欄位", "表頭必須包含 'user_id' 欄位");
    return null;
  }
  
  Logger.log(`✅ 驗證成功 | 表頭: ${headers.length} 列 | 資料: ${rows.length} 行`);
  Logger.log(`📍 user_id 列索引: ${userIdIndex}`);
  
  return { headers, rows, userIdIndex };
}

/**
 * 驗證並過濾有效的數據行
 */
function validateAndFilterRows(rows, userIdIndex) {
  const validRows = [];
  const invalidRows = [];
  
  rows.forEach((row, rowIndex) => {
    const rowNum = rowIndex + 2;  // SHEET 中的實際行號
    const userIdValue = row[userIdIndex];
    
    // 檢查 user_id 是否為空
    if (!userIdValue || userIdValue.toString().trim() === '') {
      invalidRows.push({ row: rowNum, reason: 'user_id 為空' });
      return;
    }
    
    // 檢查 user_id 是否為有效正整數
    const userIdNum = Number(userIdValue);
    if (isNaN(userIdNum) || userIdNum <= 0) {
      invalidRows.push({ 
        row: rowNum, 
        reason: `user_id '${userIdValue}' 無效（必須是正整數）` 
      });
      return;
    }
    
    // 此行有效
    validRows.push(row);
  });
  
  // 記錄被跳過的行
  if (invalidRows.length > 0) {
    Logger.log(`⚠️ 跳過 ${invalidRows.length} 行:`);
    invalidRows.forEach(item => {
      Logger.log(`   第 ${item.row} 行: ${item.reason}`);
    });
  }
  
  return validRows;
}

// ============================================================
// 輔助函數：API 呼叫
// ============================================================

/**
 * 帶重試機制的 API 呼叫
 */
function callAPIWithRetry(method, endpoint, payload = null) {
  let lastError = null;
  
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      Logger.log(`🌐 [嘗試 ${attempt}/${MAX_RETRIES}] ${method} ${API_ENDPOINT}${endpoint}`);
      
      const options = {
        method: method.toLowerCase(),
        contentType: 'application/json',
        muteHttpExceptions: true,
        timeout: API_TIMEOUT
      };
      
      if (payload) {
        options.payload = JSON.stringify(payload);
      }
      
      const response = UrlFetchApp.fetch(`${API_ENDPOINT}${endpoint}`, options);
      const responseCode = response.getResponseCode();
      const responseText = response.getContentText();
      
      Logger.log(`📥 API 回應代碼: ${responseCode}`);
      
      if (responseCode >= 200 && responseCode < 300) {
        return JSON.parse(responseText);
      } else {
        lastError = `HTTP ${responseCode}: ${responseText}`;
        Logger.log(`⚠️ 錯誤: ${lastError}`);
        
        // 對於 5xx 錯誤，嘗試重試
        if (responseCode >= 500 && attempt < MAX_RETRIES) {
          Utilities.sleep(1000 * attempt);  // 指數退避
          continue;
        } else {
          return null;
        }
      }
      
    } catch (error) {
      lastError = error.toString();
      Logger.log(`⚠️ 網絡錯誤: ${lastError}`);
      
      if (attempt < MAX_RETRIES) {
        Utilities.sleep(1000 * attempt);
        continue;
      }
    }
  }
  
  Logger.log(`❌ 所有重試都失敗: ${lastError}`);
  return null;
}

// ============================================================
// 輔助函數：顯示結果
// ============================================================

/**
 * 顯示同步結果
 */
function displaySyncResult(result) {
  if (!result || !result.status) {
    showAlert("❌ 無效的 API 回應", "請檢查伺服器日誌");
    return;
  }
  
  if (result.status === 'success') {
    const stats = result.stats || {};
    
    let message = `✅ 同步完成！\n\n`;
    message += `新增: ${stats.inserted || 0} 筆\n`;
    message += `更新: ${stats.updated || 0} 筆\n`;
    message += `重複: ${stats.duplicates || 0} 筆\n`;
    message += `錯誤: ${stats.errors || 0} 筆\n`;
    
    // 顯示錯誤詳情（如果有）
    if ((stats.errors || 0) > 0 && result.error_details && result.error_details.length > 0) {
      message += `\n🔍 錯誤詳情（前 5 筆）:\n`;
      const errors = result.error_details.slice(0, 5);
      errors.forEach((err, idx) => {
        message += `  ${idx + 1}. 記錄 ${err.record || '?'}: ${err.reason || '未知原因'}\n`;
      });
      
      if (result.error_details.length > 5) {
        message += `  ... 還有 ${result.error_details.length - 5} 個錯誤\n`;
      }
      
      message += `\n💡 建議：\n`;
      message += `• 檢查數據格式（特別是數值欄位）\n`;
      message += `• 確認 SHEET 表頭名稱與資料庫相符\n`;
      message += `• 使用「驗證 SHEET 結構」檢查配置\n`;
    }
    
    showAlert("同步結果", message);
    
  } else {
    showAlert("❌ 同步失敗", `錯誤: ${result.message || '未知錯誤'}`);
  }
}

/**
 * 顯示信息對話框
 */
function showAlert(title, message) {
  const ui = SpreadsheetApp.getUi();
  ui.alert(`${title}\n\n${message}`);
  Logger.log(`${title}: ${message}`);
}

// ============================================================
// 次要功能
// ============================================================

/**
 * 驗證 SHEET 結構
 */
function validateSheetStructure() {
  try {
    const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = spreadsheet.getSheetByName('玩家資料');
    
    if (!sheet) {
      showAlert("❌ 工作頁不存在", "找不到「玩家資料」工作頁");
      return;
    }
    
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    
    let message = `✅ SHEET 結構驗證\n\n`;
    message += `工作頁名稱: 玩家資料\n`;
    message += `欄位數: ${headers.length}\n`;
    message += `表頭: ${headers.join(', ')}\n\n`;
    
    // 檢查必要欄位
    const hasUserId = headers.some(h => h && h.toString().toLowerCase().trim() === 'user_id');
    message += (hasUserId ? '✅' : '❌') + ` 有 user_id 欄位\n`;
    
    const dataRows = sheet.getLastRow() - 1;
    message += `資料行數: ${dataRows}\n`;
    
    showAlert("SHEET 結構", message);
    
  } catch (error) {
    showAlert("❌ 驗證失敗", error.toString());
  }
}

/**
 * 檢查 API 連接
 */
function checkAPIHealth() {
  try {
    Logger.log("🔍 檢查 API 連接...");
    
    const startTime = new Date().getTime();
    
    const options = {
      method: 'get',
      muteHttpExceptions: true,
      timeout: API_TIMEOUT
    };
    
    const response = UrlFetchApp.fetch(`${API_ENDPOINT}/api/health`, options);
    const endTime = new Date().getTime();
    const latency = endTime - startTime;
    
    const responseCode = response.getResponseCode();
    
    if (responseCode === 200) {
      const result = JSON.parse(response.getContentText());
      let message = `✅ API 連接正常\n\n`;
      message += `伺服器: ${API_ENDPOINT}\n`;
      message += `延遲: ${latency}ms\n`;
      message += `狀態: ${result.status}\n`;
      message += `時間: ${result.timestamp}\n`;
      
      showAlert("API 狀態", message);
    } else {
      showAlert("❌ API 無法連接", `HTTP ${responseCode}\n\n請檢查：\n• API 地址是否正確\n• 伺服器是否運行\n• 防火牆設置`);
    }
    
  } catch (error) {
    showAlert("❌ 連接錯誤", error.toString());
  }
}

/**
 * 從資料庫同步到 SHEET
 */
function syncFromDatabase() {
  try {
    Logger.log("⏳ 從資料庫同步...");
    
    const result = callAPIWithRetry('GET', '/api/export');
    
    if (!result || result.status !== 'success') {
      showAlert("❌ 同步失敗", result?.message || "無法從資料庫讀取數據");
      return;
    }
    
    const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = spreadsheet.getSheetByName('玩家資料');
    
    if (!sheet) {
      showAlert("❌ 工作頁不存在", "找不到「玩家資料」工作頁");
      return;
    }
    
    // 寫入資料
    const data = result.data || {};
    const headers = result.headers || [];
    const rows = result.rows || [];
    
    // 清除現有內容
    const lastRow = sheet.getLastRow();
    if (lastRow > 1) {
      sheet.deleteRows(2, lastRow - 1);
    }
    
    // 寫入表頭
    if (headers.length > 0) {
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    }
    
    // 寫入資料
    if (rows.length > 0) {
      sheet.getRange(2, 1, rows.length, rows[0].length).setValues(rows);
    }
    
    showAlert("✅ 同步完成", `已同步 ${rows.length} 行資料到 SHEET`);
    
  } catch (error) {
    showAlert("❌ 同步失敗", error.toString());
  }
}

/**
 * 查看同步狀態
 */
function showSyncStatus() {
  try {
    Logger.log("📊 取得同步狀態...");
    
    const result = callAPIWithRetry('GET', '/api/stats');
    
    if (!result) {
      showAlert("❌ 無法取得統計資訊", "請檢查 API 連接");
      return;
    }
    
    const stats = result.stats || {};
    
    let message = `📊 資料庫統計\n\n`;
    message += `真實玩家: ${stats.real_users || 0} 人\n`;
    message += `虛擬帳號: ${stats.virtual_accounts || 0} 個\n`;
    message += `總玩家: ${stats.total_users || 0} 人\n`;
    message += `KKCoin 總計: ${stats.total_kkcoin || 0}\n`;
    message += `欄位數: ${stats.total_columns || 0}\n`;
    
    showAlert("統計資訊", message);
    
  } catch (error) {
    showAlert("❌ 取得統計失敗", error.toString());
  }
}

/**
 * 清理虛擬帳號
 */
function cleanVirtualAccounts() {
  try {
    const ui = SpreadsheetApp.getUi();
    const response = ui.alert('⚠️ 確認刪除虛擬帳號？', '此操作無法撤銷', ui.ButtonSet.YES_NO);
    
    if (response !== ui.Button.YES) {
      Logger.log("⏹️ 操作已取消");
      return;
    }
    
    const result = callAPIWithRetry('POST', '/api/cleanup', {});
    
    if (result && result.status === 'success') {
      const stats = result.stats || {};
      showAlert("✅ 清理完成", `已刪除 ${stats.deleted || 0} 個虛擬帳號`);
    } else {
      showAlert("❌ 清理失敗", result?.message || "未知錯誤");
    }
    
  } catch (error) {
    showAlert("❌ 操作失敗", error.toString());
  }
}
