# 🚀 Godot 卡牌冒險版 - 快速開始指南

## 📦 項目內容概覽

這個 Godot 項目已為你準備了完整的架構和核心系統。以下是已創建的文件和它們的作用：

### 📁 文件結構

```
game/
├── project.godot                          # Godot 項目配置
├── assets/
│   └── data/
│       └── game_data.json                 # 遊戲數據定義（卡牌、敵人、地點）
├── scripts/
│   ├── Constants.gd                       # 遊戲常數 ✅
│   ├── GameManager.gd                     # 主遊戲循環 ✅
│   ├── network/
│   │   └── APIClient.gd                   # Flask API 客戶端 ✅
│   ├── systems/
│   │   ├── BattleManager.gd               # 戰鬥系統 ✅
│   │   ├── Card.gd                        # 卡牌類 ✅
│   │   ├── Character.gd                   # 角色系統 ✅
│   │   ├── Enemy.gd                       # 敵人系統 ✅
│   │   └── MapSystem.gd                   # 地圖系統 ✅
│   └── ui/
│       └── UIManager.gd                   # UI 管理 ✅
├── scenes/                                # 待建立：UI 場景文件
├── web/                                   # Web 版本（現有）
└── system/                                # 系統模組
```

### 📄 文檔

已創建的設計和實現文檔：

1. **GODOT_GAME_DESIGN.md** (50kb)
   - 完整的遊戲設計文檔
   - 卡牌系統、戰鬥系統、地圖系統設計
   - 技術架構概覽
   - 美術指南

2. **GODOT_IMPLEMENTATION_GUIDE.md** (20kb)
   - 逐步實現清單
   - 場景結構建議
   - UI 組件開發指南
   - 性能優化建議

3. **GODOT_BACKEND_API_GUIDE.md** (15kb)
   - Flask 後端 API 擴展
   - 新增端點定義
   - 數據庫更新 SQL
   - 測試用例

---

## 🎮 快速開始步驟

### 步驟 1: 開啟 Godot 項目

```bash
cd game/
# 使用 Godot 4.x 開啟項目
godot .
```

### 步驟 2: 運行測試場景

在 Godot 編輯器中：

1. 選擇 `GameManager.gd`
2. 按 `F6` 或 Run → Run Project

你應該看到：
```
[GameManager] 初始化系統...
[BattleManager] 已初始化
[MapSystem] 地圖系統已初始化，共 4 個位置
[GameManager] 所有系統已初始化
[GameManager] 載入遊戲...
[GameManager] 進入主遊戲
```

### 步驟 3: 測試命令（控制台）

在運行中按下快捷鍵測試功能：

| 快捷鍵 | 功能 |
|--------|------|
| `M` | 進入地圖 |
| `B` | 開始戰鬥 |
| `C` | 查看角色 |
| `D` | 查看卡組 |

或在 Output 控制台中輸入命令：

```gdscript
# GameManager 內的 process_command() 方法已實現
# 例如：
print(_ready())  # 開始遊戲
```

---

## 🛠️ 後續開發優先順序

### 優先級 1: UI 場景 (最關鍵)

需要建立以下場景文件（.tscn）：

1. **BattleUI.tscn** - 戰鬥介面
   ```
   ├── PlayerPanel
   │   ├── 角色圖像 (紙娃娃)
   │   └── 血量條
   ├── EnemyPanel
   │   ├── 敵人圖像
   │   └── 敵人血量條
   ├── CardHandPanel
   │   └── 卡牌容器 (動態)
   ├── EnergyDisplay
   ├── LogPanel
   └── ActionButtons
   ```

2. **MapUI.tscn** - 地圖介面
   ```
   ├── 地圖背景
   ├── 位置節點 (4 個按鈕)
   └── 信息面板
   ```

**建議實現步驟:**
```
1. 建立 BattleUI.tscn
   ↓
2. 實現卡牌拖放
   ↓
3. 連接 BattleManager 信號
   ↓
4. 完成戰鬥動畫
```

### 優先級 2: 整合紙娃娃

```gdscript
# Character.gd 中已準備好
# 取得 URL:
var url = character.get_paperdoll_url()

# 在 UI 中加載:
var http_request = HTTPRequest.new()
add_child(http_request)
http_request.request(url)
var image = await Image.load_from_file(url)
```

### 優先級 3: 後端集成

```bash
# 1. 在 Flask 中添加新端點
# 位置: blueprints/game_api.py (參考指南已提供)

# 2. 更新數據庫
# 執行提供的 SQL 語句

# 3. 測試 API
curl http://localhost:5000/api/game/cards
```

---

## 💾 數據流示例

### 場景 1: 開始戰鬥

```
玩家選擇位置
    ↓
GameManager._encounter_enemy()
    ↓
APIClient.start_battle(location_id)
    ↓
Flask: create battle session
    ↓
BattleManager.setup_battle(player, enemies)
    ↓
UIManager.show_battle_ui()
    ↓
BattleManager.start_player_turn()
    ↓
顯示手牌 → 玩家選卡 → 執行效果 → 敵人回合
```

### 場景 2: 保存進度

```
戰鬥結束或玩家移動
    ↓
GameManager → Character.level_up() OR
    ↓
MapSystem.move_to_location()
    ↓
APIClient.update_character_data()
    ↓
Flask: update user in database
    ↓
進度已保存
```

---

## 🎨 美術資源清單

需要準備的美術資源：

### 卡牌圖片
- 8 張卡牌藝術（1080 x 1500 px）
- 路徑: `assets/images/cards/`
- 檔案: `attack_01.png`, `attack_02.png` 等

### 角色圖像
- 使用 MapleStory.io API 動態生成
- 無需手動準備

### UI 元素
- 按鈕、面板、邊框
- 血條、能量指示器
- 路徑: `assets/images/ui/`

### 音效
- 背景音樂: 1 首 (loop)
- 卡牌音效: 3-5 個
- 路徑: `assets/audio/`

---

## 🧪 測試清單

### 單元測試

```gdscript
# test_card.gd
func test_card_creation():
    var card = Card.new("test_001", "Test Card", Constants.CardType.ATTACK, 1, 5)
    assert(card.name == "Test Card")
    assert(card.cost == 1)
    print("✓ Card creation test passed")

# test_battle.gd
func test_battle_logic():
    var player = Character.new("123", "TestPlayer")
    var enemy = Enemy.new("enemy_001", "Test Enemy")
    
    var battle_mgr = BattleManager.new()
    battle_mgr.setup_battle(player, [enemy])
    
    assert(battle_mgr.player_hp > 0)
    print("✓ Battle setup test passed")
```

### 集成測試

```bash
# 測試完整流程
1. 開始遊戲
2. 進入地圖
3. 選擇位置
4. 開始戰鬥
5. 使用卡牌
6. 敵人回合
7. 勝利並獲得獎勵
8. 返回地圖
```

---

## 🔧 常見配置

### 遊戲平衡參數

在 `Constants.gd` 中調整：

```gdscript
# 難度參數
const STARTING_ENERGY = 3              # 初始能量
const MAX_ENERGY = 10                  # 最大能量
const DRAW_CARD_COUNT = 5              # 每回合抽牌數
const MAX_HAND_SIZE = 10               # 最大手牌數

# 敵人難度倍數
# 在 MapSystem 中：difficulty * 10 = 敵人 HP
# difficulty * 2 = 敵人傷害

# 倍數平衡
const REWARD_MULTIPLIER = 1.5          # 獲得獎勵倍數
```

### API 配置

在 `Constants.gd` 中設置：

```gdscript
const API_BASE_URL = "http://localhost:5000"  # 開發
# const API_BASE_URL = "https://your-domain.com"  # 生產
```

---

## 📊 開發進度追蹤

### 已完成 (30%)
- [x] 核心系統架構
- [x] 遊戲邏輯框架
- [x] API 客戶端
- [x] 數據定義

### 進行中 (0%)
- [ ] UI 場景文件
- [ ] 卡牌 UI

### 待開始 (70%)
- [ ] 戰鬥 UI
- [ ] 地圖 UI
- [ ] 動畫效果
- [ ] 音效 SFX
- [ ] 後端 API
- [ ] 性能優化

---

## 🆘 常見問題

### Q: 如何添加新卡牌？
A: 編輯 `game/assets/data/game_data.json` 的 `cards` 陣列，然後遊戲會自動加載。

### Q: 如何自定義敵人？
A: 編輯 `game_data.json` 的 `enemies` 陣列。

### Q: 紙娃娃圖片不顯示？
A: 檢查 `Character.get_paperdoll_url()` 生成的 URL 是否有效。

### Q: 如何連接到後端？
A: 設置 `Constants.API_BASE_URL` 並確保 Flask 服務器運行。

---

## 📚 相關文檔

- [遊戲設計文檔](GODOT_GAME_DESIGN.md) - 完整的系統設計
- [實現指南](GODOT_IMPLEMENTATION_GUIDE.md) - UI 和功能實現
- [後端 API 指南](GODOT_BACKEND_API_GUIDE.md) - Flask 端點定義

---

## 🎯 下一步建議

### 今天
1. 在 Godot 中打開項目
2. 運行 `GameManager` 場景
3. 測試控制台命令

### 本周
1. 創建 `BattleUI.tscn`
2. 実現卡牌 UI 組件
3. 連接信號

### 本月
1. 完整戰鬥 UI
2. 地圖導航
3. 後端集成
4. Alpha 測試

---

## 📞 技術支持

如遇到問題：

1. 檢查 Godot 版本 (需要 4.0+)
2. 查看 Output 控制台的錯誤訊息
3. 參考實現文檔對應章節
4. 檢查 GDScript 語法

---

**祝開發愉快！** 🎮

這個架構已經為你做好了重擔。你只需要：
1. 建立漂亮的 UI 場景
2. 集成紙娃娃系統
3. 擴展後端 API
4. 測試並優化

整個框架已準備好，剩下的就是把它變成視覺上美麗且令人興奮的遊戲！

**版本**: 1.0  
**最後更新**: 2026-04-07
