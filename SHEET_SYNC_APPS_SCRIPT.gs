/**
 * ⚠️ 此檔案已棄用 - DEPRECATED ⚠️
 * 
 * 此版本使用舊的 Sheet 結構：
 * - Row 1 = 分組標題行
 * - Row 2 = 表頭行
 * - Row 3+ = 資料行
 * 
 * 請使用新版本：SHEET_SYNC_APPS_SCRIPT_UPDATED.gs
 * 新版結構：
 * - Row 1 = 表頭行
 * - Row 2+ = 資料行
 * 
 * 此檔案保留僅供參考，請勿使用！
 */

/**
 * Google Apps Script - SHEET 與資料庫同步工具 (舊版 - 已棄用)
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
const API_ENDPOINT = "http://YOUR_SERVER_IP:5000";

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
 */
function syncToDatabase() {
  try {
    Logger.log("⏳ 開始同步...");
    
    // 1. 取得 SHEET 資料
    const sheet = SpreadsheetApp.getActiveSheet();
    const allData = sheet.getDataRange().getValues();
    
    if (allData.length < 3) {
      SpreadsheetApp.getUi().alert("❌ 資料不足（至少需要 3 行：分組標題、表頭、資料）");
      return;
    }
    
    // 📌 SHEET 結構
    // Row 1 (allData[0]) = 分組標題行（例如：分組、分組、空、空、...）
    // Row 2 (allData[1]) = 實際表頭行（例如：user_id, nickname, level, xp, ...）
    // Row 3+ (allData[2:]) = 資料行
    
    // ✅ 步驟 1：提取表頭，使用 Row 2 (allData[1])
    const headerRowRaw = allData[1];
    
    // ⚠️ 重要：表頭行的第一個非空值對應的位置就是數據的起始列
    // 例如如果 allData[1] = ['user_id', 'nickname', 'level', ...]
    // 那麼 headers 應該是完整的數組，保持原始位置
    const headers = headerRowRaw.filter(h => h && h.toString().trim() !== '');
    
    if (headers.length === 0) {
      SpreadsheetApp.getUi().alert("❌ 表頭行為空，無法同步");
      return;
    }
    
    Logger.log(`✅ 表頭已識別 (${headers.length} 列): ${headers.slice(0, 5).join(', ')}...`);
    Logger.log(`🔍 完整表頭: ${JSON.stringify(headers)}`);
    
    // ✅ 步驟 2：提取資料行（第 3 行開始，即 allData[2:]）
    // 每一行都需要與表頭數量對應
    const dataRowsRaw = allData.slice(2);
    
    // 過濾：只保留有非空值的行
    const rows = dataRowsRaw
      .filter(row => {
        // 該行是否有任何非空值？
        return row.some(cell => cell && cell.toString().trim() !== '');
      })
      .map(row => {
        // 每行只取前 N 列（與表頭數量對應）
        // 這確保了列對齊
        return row.slice(0, headers.length);
      });
    
    if (rows.length === 0) {
      SpreadsheetApp.getUi().alert("❌ 沒有有效的資料行（第 3 行以下都是空的）");
      return;
    }
    
    Logger.log(`📊 資料行過濾完成: ${rows.length} 筆有效記錄`);
    Logger.log(`📝 第 1 筆資料: ${JSON.stringify(rows[0])}`);
    
    // ✅ 步驟 3：驗證資料完整性
    // 檢查第一筆記錄的第一列是否是有效的 user_id（應該是數字，不是字符串 "user_id"）
    const firstRecordFirstCol = rows[0][0];
    const isFirstColNumeric = !isNaN(firstRecordFirstCol) && firstRecordFirstCol !== '';
    
    Logger.log(`🔍 第 1 筆資料的第 1 列值: "${firstRecordFirstCol}" (是否數字: ${isFirstColNumeric})`);
    
    if (!isFirstColNumeric) {
      Logger.log(`⚠️ 警告：第 1 列不是數字，可能是表頭或無效資料`);
    }
    
    // ✅ 步驟 4：準備請求體
    const payload = {
      headers: headers,
      rows: rows
    };
    
    Logger.log(`🌐 準備呼叫 API: POST ${API_ENDPOINT}/api/sync`);
    Logger.log(`📦 請求內容: headers=${headers.length} 列, rows=${rows.length} 筆`);
    
    // ✅ 步驟 5：呼叫 API
    const options = {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };
    
    const response = UrlFetchApp.fetch(`${API_ENDPOINT}/api/sync`, options);
    const statusCode = response.getResponseCode();
    const responseText = response.getContentText();
    
    Logger.log(`📥 API 回應狀態碼: ${statusCode}`);
    Logger.log(`📥 API 回應內容: ${responseText.substring(0, 500)}`);
    
    const result = JSON.parse(responseText);
    
    // ✅ 步驟 6：顯示結果
    if (result.status === 'success') {
      const stats = result.stats;
      const message = `✅ 同步完成！\n\n更新: ${stats.updated} 筆\n新增: ${stats.inserted} 筆\n錯誤: ${stats.errors} 筆\n\n訊息: ${result.message}`;
      SpreadsheetApp.getUi().alert(message);
      Logger.log(`✅ 同步成功！${message}`);
    } else {
      const message = `❌ 同步失敗\n\n狀態: ${result.status}\n錯誤: ${result.message}\n\n請檢查伺服器日誌了解詳情`;
      SpreadsheetApp.getUi().alert(message);
      Logger.log(`❌ 同步失敗: ${message}`);
    }
  
  } catch (error) {
    const message = `❌ 執行錯誤: ${error.toString()}`;
    SpreadsheetApp.getUi().alert(message);
    Logger.log(`❌ 執行錯誤: ${error}`);
    Logger.log(`堆疊追蹤: ${error.stack}`);
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
    const result = JSON.parse(response.getContentText());
    
    if (result.status === 'ok') {
      const message = `✅ API 連接正常\n\n${result.message}\n時間: ${result.timestamp}`;
      SpreadsheetApp.getUi().alert(message);
      Logger.log(message);
    } else {
      SpreadsheetApp.getUi().alert("❌ API 連接失敗");
    }
  
  } catch (error) {
    const message = `❌ 無法連接到 API\n\n位址: ${API_ENDPOINT}\n錯誤: ${error.toString()}\n\n請檢查：\n1. API 位址是否正確\n2. Flask 伺服器是否正在運行\n3. 防火牆設定`;
    SpreadsheetApp.getUi().alert(message);
    Logger.log(message);
  }
}
