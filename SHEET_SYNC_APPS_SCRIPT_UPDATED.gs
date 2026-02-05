/**
 * Google Apps Script - SHEET 與資料庫同步工具 (更新)
 * 
 * 使用方式：
 * 1. 在 Google Sheets 中，選擇「擴充功能」→「Apps Script」
 * 2. 複製下面的代碼到編輯器
 * 3. 將 API_ENDPOINT 改為你的 Flask 伺服器位址
 * 4. 執行 onOpen() 初始化功能表
 * 5. 點選「🔄 同步工具」→「同步到資料庫」執行同步
 */

// ============================================================
// 設定區
// ============================================================

// 將此改為你的 Flask API 位址（例如：http://your-server.com:5000）
const API_ENDPOINT = "http://35.209.101.28:5000";

// ============================================================
// 功能列表
// ============================================================

/**
 * 初始化功能表（在打開 SHEET 時自動執行）
 */
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('🔄 同步工具')
    .addItem('📤 同步到資料庫', 'syncToDatabase')
    .addItem('📊 查看同步狀態', 'showSyncStatus')
    .addItem('🧹 清理虛擬帳號', 'cleanVirtualAccounts')
    .addSeparator()
    .addItem('✅ 檢查 API 連接', 'checkAPIHealth')
    .addToUi();
}

/**
 * 同步 SHEET 資料到資料庫
 * 
 * SHEET 結構：
 * 第 1 行 = 表頭 (user_id, level, xp, ...)
 * 第 2 行+ = 數據
 */
function syncToDatabase() {
  try {
    Logger.log("⏳ 開始同步...");
    
    // 1. 取得 SHEET 資料
    // ✅ 明確指定工作頁名稱「玩家資料」而不是使用 getActiveSheet()
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
    
    // 📌 更新的 SHEET 結構
    // Row 1 (allData[0]) = 表頭行（例如：user_id, level, xp, ...）
    // Row 2+ (allData[1:]) = 資料行
    
    const headers = allData[0];  // 第 1 行是表頭
    const rows = allData.slice(1);  // 第 2 行開始是資料
    
    Logger.log(`📋 表頭: ${headers.slice(0, 5).join(', ')}...`);
    Logger.log(`📊 資料行數: ${rows.length}`);
    
    // 過濾空行
    const validRows = rows.filter(row => {
      return row.some(cell => cell && cell.toString().trim() !== '');
    });
    
    Logger.log(`📊 有效資料行數: ${validRows.length}`);
    
    if (validRows.length === 0) {
      SpreadsheetApp.getUi().alert("❌ 沒有有效的資料行");
      return;
    }
    
    // 2. 準備請求體
    const payload = {
      headers: headers,
      rows: validRows
    };
    
    // 3. 呼叫 API
    Logger.log(`🌐 呼叫 API: POST ${API_ENDPOINT}/api/sync`);
    
    const options = {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true  // 不拋出 HTTP 錯誤
    };
    
    const response = UrlFetchApp.fetch(`${API_ENDPOINT}/api/sync`, options);
    const result = JSON.parse(response.getContentText());
    
    Logger.log(`📥 API 回應: ${JSON.stringify(result, null, 2)}`);
    
    // 4. 顯示結果
    if (result.status === 'success') {
      const stats = result.stats;
      const message = `✅ 同步完成！\n\n更新: ${stats.updated} 筆\n新增: ${stats.inserted} 筆\n錯誤: ${stats.errors} 筆\n\n訊息: ${result.message}`;
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
    
    const options = {
      method: 'get',
      muteHttpExceptions: true
    };
    
    const response = UrlFetchApp.fetch(`${API_ENDPOINT}/api/stats`, options);
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
    
    const options = {
      method: 'post',
      muteHttpExceptions: true
    };
    
    const result_response = UrlFetchApp.fetch(`${API_ENDPOINT}/api/clean-virtual`, options);
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
 * 檢查 API 連接
 */
function checkAPIHealth() {
  try {
    Logger.log("⏳ 檢查 API 連接...");
    
    const options = {
      method: 'get',
      muteHttpExceptions: true
    };
    
    const response = UrlFetchApp.fetch(`${API_ENDPOINT}/api/health`, options);
    const statusCode = response.getResponseCode();
    const responseText = response.getContentText();
    
    Logger.log(`📥 HTTP 狀態碼: ${statusCode}`);
    Logger.log(`📥 回應內容: ${responseText.substring(0, 500)}`);
    
    // 嘗試解析 JSON
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
      // JSON 解析失敗，顯示原始回應
      const message = `❌ 伺服器回應異常\n\n狀態碼: ${statusCode}\n回應: ${responseText.substring(0, 200)}`;
      SpreadsheetApp.getUi().alert(message);
      Logger.log(message);
    }
  
  } catch (error) {
    const message = `❌ 無法連接到 API\n\n位址: ${API_ENDPOINT}\n錯誤: ${error.toString()}\n\n請檢查：\n1. API 位址是否正確\n2. Flask 伺服器是否正在運行\n3. 防火牆設定`;
    SpreadsheetApp.getUi().alert(message);
    Logger.log(message);
  }
}
