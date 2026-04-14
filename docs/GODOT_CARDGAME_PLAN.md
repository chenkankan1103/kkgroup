# 🎮 KK 群 Godot 卡牌作戰遊戲 - 完整實施計畫

**目標**: 將 Web 版紙娃娃 RPG 升級為 Godot 卡牌作戰遊戲（類似殺戮尖塔）

---

## 📋 1. 遊戲架構概覽

```
遊戲流程：
用戶登入 
  ↓
選擇/創建卡牌組
  ↓
進入園區地圖
  ↓
選擇站點節點
  ↓ (每個節點對應一場戰鬥或事件)
卡牌作戰系統
  ↓
勝利/失敗 → 獲得獎勵 → 返回地圖
```

### 核心系統
- **UI 層**：Godot 4.6 GDScript + CanvasLayer
- **邏輯層**：卡牌系統、戰鬥系統、節點系統
- **資料層**：REST API + Python 後端（現有）
- **美術層**：紙娃娃渲染、卡牌動畫、園區地圖

---

## 🎯 2. Godot 項目結構

```
game/
├── project.godot                    # Godot 配置（已存在）
├── scenes/
│   ├── ui/
│   │   ├── MainMenu.tscn           # 登入/菜單
│   │   ├── CardGameUI.tscn         # 卡牌作戰 UI
│   │   └── CharacterDisplay.tscn   # 紙娃娃展示
│   ├── game/
│   │   ├── GameMap.tscn            # 園區地圖
│   │   ├── MoneyNode.tscn          # 地圖節點（可重用）
│   │   └── CardBattle.tscn         # 卡牌戰鬥場景
│   └── world/
│       ├── MapZones/               # 園區各區域
│       └── NPCs/                   # NPC 定義
│
├── scripts/
│   ├── ui/
│   │   ├── UIManager.gd            # UI 全局管理器
│   │   ├── CardRenderer.gd         # 卡牌渲染
│   │   └── CharacterRenderer.gd    # 紙娃娃渲染
│   │
│   ├── game/
│   │   ├── CardSystem.gd           # 卡牌系統核心
│   │   ├── BattleSystem.gd         # 戰鬥邏輯
│   │   ├── MapManager.gd           # 地圖/節點管理
│   │   └── Node.gd                 # 節點類型（基類）
│   │
│   ├── network/
│   │   ├── APIClient.gd            # REST API 客戶端
│   │   └── SyncManager.gd          # 數據同步
│   │
│   ├── systems/
│   │   ├── PlayerManager.gd        # 玩家管理
│   │   ├── GameState.gd            # 遊戲狀態管理
│   │   └── AudioManager.gd         # 音效管理
│   │
│   └── utils/
│       ├── Constants.gd            # 常數定義
│       ├── Helper.gd               # 幫助函數
│       └── Animator.gd             # 通用動畫工具
│
├── assets/
│   ├── images/
│   │   ├── cards/                  # 卡牌圖像
│   │   ├── characters/             # 紙娃娃資源
│   │   └── ui/                     # UI 資源
│   ├── sounds/
│   │   ├── cards/
│   │   └── battle/
│   │
├── data/
│   ├── cards.json                  # 卡牌庫定義
│   ├── enemies.json                # 敵人配置
│   ├── nodes.json                  # 地圖節點定義
│   └── zones.json                  # 園區區域定義
│
└── export_presets.cfg              # 導出配置
```

---

## 🎴 3. 卡牌系統設計

### 3.1 卡牌類型

```gd
# CardType 枚舉
enum CardType {
    ATTACK,      # 攻擊卡 (紅色)
    DEFENSE,     # 防守卡 (藍色)
    SKILL,       # 技能卡 (綠色)
    SPECIAL,     # 特殊卡 (紫色)
}

# 卡牌數據結構
class Card:
    var id: String                  # 卡牌唯一 ID
    var name: String                # 卡牌名稱
    var type: CardType              # 卡牌類型
    var cost: int                   # 能量消耗
    var damage: int                 # 傷害值
    var armor: int                  # 護甲值
    var description: String         # 卡牌描述
    var rarity: String              # 稀有度 (common/rare/epic)
    var effects: Array              # 特殊效果
```

### 3.2 卡牌組管理

```gd
# 玩家卡牌組
var deck: Array[Card] = []         # 當前卡牌組
var hand: Array[Card] = []         # 當前手牌
var discard_pile: Array[Card] = [] # 棄牌堆
var exhaust_pile: Array[Card] = [] # 消耗堆

func add_card_to_deck(card: Card):
    deck.append(card)

func draw_card() -> Card:
    if deck.is_empty():
        reshuffle_from_discard()
    if deck.is_empty():
        return null
    return deck.pop_front()

func play_card(card: Card):
    if can_play_card(card):
        hand.erase(card)
        apply_card_effect(card)
        discard_pile.append(card)

func can_play_card(card: Card) -> bool:
    return current_energy >= card.cost
```

### 3.3 戰鬥卡牌流程

```
回合流程：
1. 開始階段 → 補充能量 (每回合 3 點)
2. 抽牌 (5 張)
3. 玩家行動階段
   - 選擇卡牌 → 查看預覽
   - 點擊卡牌 → 確認效果
   - 能量消耗
   - 效果應用到敵人/自己
4. 結束階段 → 棄牌 / 進入敵人回合
5. 敵人回合
6. 勝利判定 (敵人 HP ≤ 0?)
```

---

## 🗺️ 4. 園區地圖與節點系統

### 4.1 地圖結構

```
園區地圖 (roguelike 風格):
  
  [商店節點]
      ↓
  [戰鬥節點] ← [事件節點]
      ↓          ↓
  [寶箱節點] ← [商人節點]
      ↓
  [首領戰鬥]  ← [休息點]
```

### 4.2 節點類型

```gd
enum NodeType {
    BATTLE,      # 戰鬥
    ELITE_BATTLE,# 精英戰鬥 (更強)
    BOSS_BATTLE, # 首領戰鬥
    SHOP,        # 商店
    TREASURE,    # 寶箱
    EVENT,       # 隨機事件
    REST,        # 休息點 (恢復 30% 血)
    CAMPFIRE,    # 篝火 (升級卡牌)
}

class MapNode:
    var id: String
    var type: NodeType
    var x: int
    var y: int
    var reward: Dictionary        # 獎勵
    var enemy: Enemy              # 敵人定義
    var visited: bool = false
```

### 4.3 節點生成 (Procedural)

```gd
func generate_map_nodes(num_nodes: int = 20) -> Array:
    var nodes = []
    var current_y = 0
    
    while current_y < 5:  # 5 層
        var layer_nodes = []
        var num_this_layer = randi_range(2, 4)  # 每層 2-4 個節點
        
        for i in range(num_this_layer):
            var node_type = choose_random_node_type()
            var node = MapNode.new()
            node.type = node_type
            node.x = i
            node.y = current_y
            layer_nodes.append(node)
        
        nodes.append_array(layer_nodes)
        current_y += 1
    
    return nodes
```

---

## 👤 5. 紙娃娃角色系統

### 5.1 角色渲染

```gd
# CharacterRenderer.gd
extends Node2D

class_name CharacterRenderer

var character_data: Dictionary  # { face, hair, top, bottom, shoes, ... }
var paperdoll_image: Image

func _ready():
    # 從 API 獲取紙娃娃圖像
    load_character_from_api(player_id)

func load_character_from_api(user_id: String):
    # 調用 /api/game/user/{user_id}/paperdoll/image
    # 顯示在戰鬥場景中
    var url = "http://localhost:5000/api/game/user/%s/paperdoll/image" % user_id
    # 使用 HTTPRequest 加載
```

### 5.2 角色顯示位置

- **己方**: 左側（佔屏幕 30%）
- **敵方**: 右側（佔屏幕 30%）
- **卡牌與能量條**: 中下方

---

## 💾 6. 數據層 - REST API 集成

### 6.1 所需 API 端點 (現有或新增)

```
已實現:
GET  /api/game/user/{user_id}/paperdoll
GET  /api/game/user/{user_id}/paperdoll/image
GET  /api/game/user/{user_id}/inventory
POST /api/game/user/{user_id}/inventory/equip

需新增:
GET  /api/game/user/{user_id}/cards         # 獲取卡牌組
POST /api/game/user/{user_id}/cards/update  # 更新卡牌組
POST /api/game/battle/save                  # 保存戰鬥結果
GET  /api/game/user/{user_id}/stats         # 遊戲統計
```

### 6.2 Godot API 客戶端

```gd
# scripts/network/APIClient.gd
extends Node

class_name APIClient

const BASE_URL = "http://localhost:5000"
var http_request: HTTPRequest

func _ready():
    http_request = HTTPRequest.new()
    add_child(http_request)

func get_user_cards(user_id: String) -> Array:
    var url = BASE_URL + "/api/game/user/%s/cards" % user_id
    var response = await http_request.request(url)
    return parse_response(response)

func save_battle_result(user_id: String, battle_data: Dictionary):
    var url = BASE_URL + "/api/game/battle/save"
    var body = JSON.stringify(battle_data)
    await http_request.request(url, [], HTTPClient.METHOD_POST, body)

# 更多方法...
```

---

## 🎨 7. UI 設計

### 7.1 卡牌作戰主 UI

```
┌─────────────────────────────────────────────────────┐
│ [資訊] 敵人 HP: ████████  |  玩家 HP: ████████████  │
├─────────────────────────────────────────────────────┤
│                                                       │
│           [敵人紙娃娃圖像]      [我方紙娃娃圖像]      │
│                                                       │
├─────────────────────────────────────────────────────┤
│ 能量: 3/3  棄牌堆: 12  抽牌堆: 8                      │
├─────────────────────────────────────────────────────┤
│  手牌 (5 張)                                         │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐       │
│ │ 攻擊 │ │ 防守 │ │ 技能 │ │ 特殊 │ │ 抽牌 │       │
│ │ 15  │ │ 10  │ │ 8   │ │ 20  │ │     │       │
│ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘       │
├─────────────────────────────────────────────────────┤
│ [結束回合]                          [投降]           │
└─────────────────────────────────────────────────────┘
```

### 7.2 地圖 UI

```
┌─────────────────────────────────────┐
│ [返回] 園區地圖 - 第 1 層            │
├─────────────────────────────────────┤
│                                     │
│ [商店]     
│  ↓ ← 可選路徑
│ [戰鬥] → [精英戰鬥]
│  ↓       ↓
│ [寶箱] ← [事件]
│  ↓
│ [首領戰鬥]
│
├─────────────────────────────────────┤
│ 玩家: Lv.5 | 金幣: 150 | 血量: 45/60│
└─────────────────────────────────────┘
```

---

## 🛠️ 8. 開發路線圖

### Phase 1: 核心系統 (2 週)
- [ ] Godot 項目基礎設置
- [ ] API 客戶端實現
- [ ] 玩家管理與登入
- [ ] 紙娃娃渲染集成

### Phase 2: 卡牌與戰鬥 (3 週)
- [ ] 卡牌系統實現
- [ ] 戰鬥系統邏輯
- [ ] 敵人 AI
- [ ] 卡牌 UI 與動畫

### Phase 3: 地圖與節點 (2 週)
- [ ] 地圖生成算法
- [ ] 節點系統
- [ ] 地圖 UI
- [ ] 節點事件

### Phase 4: 波蘭與發佈 (1 週)
- [ ] 美術資源優化
- [ ] 音效集成
- [ ] 測試與 Bug 修復
- [ ] Godot 導出 (EXE / HTML5)

---

## 💡 9. 技術要點

### 9.1 性能優化
- **卡牌預加載**: 啟動時加載所有卡牌定義到內存
- **紙娃娃緩存**: 已渲染的紙娃娃圖像緩存 30 分鐘
- **異步 API**: 所有 HTTP 請求使用 `await`，不阻塞 UI

### 9.2 存檔與進度
```gd
# 自動存檔到 user://
var save_file = "user://game_save_%s.json" % user_id
var data = {
    "user_id": user_id,
    "current_floor": 2,
    "deck": [],
    "inventory": {},
    "timestamp": Time.get_ticks_msec()
}
```

### 9.3 跨平台支持
- Windows EXE
- HTML5 (網頁投放)
- 未來：移動端 (iOS/Android)

---

## 📚 10. 資源需求

### 美術資源
- [ ] 卡牌背景圖 (40+ 設計)
- [ ] 卡牌圖標 (攻擊、防守、技能等)
- [ ] 園區地圖背景
- [ ] UI 按鈕與圖標
- [ ] 敵人頭像 (~15 種)

### 音效資源
- [ ] 卡牌使用音效
- [ ] 戰鬥背景音樂
- [ ] 勝利/失敗音效
- [ ] UI 點擊音效

### 配置數據
- [ ] card_definitions.json (卡牌庫)
- [ ] enemies.json (敵人配置)
- [ ] encounters.json (遭遇戰定義)
- [ ] rewards.json (獎勵配置)

---

## 📝 11. 偽代碼示例

### 戰鬥主循環

```gd
# BattleSystem.gd
extends Node

class_name BattleSystem

var player_hp: int = 100
var player_deck: Array[Card]
var player_hand: Array[Card]
var player_energy: int = 3
var player_armor: int = 0

var enemy_hp: int = 80
var enemy_deck: Array[Card]

func _ready():
    start_battle()

func start_battle():
    player_hand.clear()
    draw_cards(5)
    display_ui_state()

func _process(delta):
    if Input.is_action_pressed("play_card"):
        handle_card_play()
    if Input.is_action_pressed("end_turn"):
        end_player_turn()

func draw_cards(count: int):
    for i in range(count):
        var card = player_deck[randi() % player_deck.size()]
        player_hand.append(card)

func handle_card_play():
    var selected_card = get_selected_card()
    if can_play_card(selected_card):
        apply_card_effect(selected_card)
        player_energy -= selected_card.cost
        player_hand.erase(selected_card)

func can_play_card(card: Card) -> bool:
    return player_energy >= card.cost and player_hand.has(card)

func apply_card_effect(card: Card):
    match card.type:
        CardType.ATTACK:
            enemy_hp -= card.damage
        CardType.DEFENSE:
            player_armor += card.armor
        CardType.SKILL:
            execute_skill(card.effects)

func end_player_turn():
    enemy_turn()
    start_new_turn()

func enemy_turn():
    # 簡單 AI：隨機選擇攻擊或防守
    if randf() > 0.5:
        player_hp -= randi_range(10, 20)
    else:
        # enemy_armor += 5

func check_battle_end() -> String:  # "win", "lose", or ""
    if enemy_hp <= 0:
        return "win"
    if player_hp <= 0:
        return "lose"
    return ""
```

---

## 🔗 12. 與現有系統的集成

### Python 後端改進

```python
# 新增 endpoints 到 game_api.py

@game_bp.route('/user/<user_id>/cards', methods=['GET'])
def get_user_cards(user_id):
    user = get_user(user_id)
    return jsonify({
        "cards": user.get('cards', []),
        "deck": user.get('deck', [])
    })

@game_bp.route('/battle/save', methods=['POST'])
def save_battle_result():
    data = request.json
    user_id = data['user_id']
    battle_data = data['battle_result']
    
    # 保存戰鬥結果
    user = get_user(user_id)
    user['battles_fought'] = user.get('battles_fought', 0) + 1
    user['kkcoin'] += battle_data['reward_gold']
    set_user_field(user_id, 'kkcoin', user['kkcoin'])
    
    return jsonify({"success": True})
```

---

## 🚀 13. 快速開始

### 設置開發環境
```bash
# 1. 安裝 Godot 4.6
# 下載自：https://godotengine.org/download/

# 2. 打開項目
cd game/
# 在 Godot 中打開 project.godot

# 3. 測試連接
godot --path . --run

# 4. 構建 EXE
godot --export-release "Windows Desktop" ../builds/game.exe
```

---

## ✅ 完成檢認清單

- [ ] Godot 項目配置完成
- [ ] 主菜單場景完成
- [ ] 卡牌系統實現
- [ ] 戰鬥邏輯完成
- [ ] 地圖生成完成
- [ ] 紙娃娃渲染集成
- [ ] API 客戶端完成
- [ ] UI 完全實現
- [ ] 音效與美術集成
- [ ] 完整測試與 Bug 修復
- [ ] Godot 導出 EXE
- [ ] 文檔與教程完成

---

**下一步**: 開始 Phase 1 核心系統開發，建立基礎架構和 API 連接。

