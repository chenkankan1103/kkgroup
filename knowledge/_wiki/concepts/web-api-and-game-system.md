# Web API 和遊戲系統詳解

## 系統概述

KKGroup Web 系統包含 Flask API 服務和 HTML5 遊戲，提供完整的 Web 功能和遊戲體驗，透過 Cloudflare Tunnel 對外服務。

## Web API 架構

### 1. API 伺服器 (`web/api/api_server.py`)
**核心功能**:
- RESTful API 服務
- Discord 認證整合
- 資料庫操作介面
- 跨域資源共享 (CORS)

**主要端點**:
```python
# 基礎配置
app = Flask(__name__)
CORS(app)  # 啟用跨域支援

# Discord 認證端點
@app.route('/auth/discord', methods=['POST'])
async def discord_auth():
    # Discord OAuth 處理
    pass

# 用戶資料端點
@app.route('/api/user/<user_id>', methods=['GET'])
def get_user_data(user_id):
    # 獲取用戶資料
    pass
```

### 2. 遊戲 API (`web/api/game_api.py`)
**專用功能**:
- 遊戲狀態管理
- 玩家資料同步
- 遊戲邏輯處理
- 實時資料更新

**遊戲端點**:
```python
# 遊戲狀態
@app.route('/api/game/status', methods=['GET'])
def game_status():
    return jsonify({"status": "active", "players": online_count})

# 玩家操作
@app.route('/api/game/action', methods=['POST'])
def game_action():
    # 處理玩家操作
    pass

# 資源更新
@app.route('/api/game/resources', methods=['GET'])
def get_resources():
    # 獲取遊戲資源
    pass
```

### 3. 藍圖系統 (`web/blueprints/`)
採用模組化設計，每個藍圖負責特定功能：

#### Discord 認證藍圖 (`discord_auth.py`)
```python
from flask import Blueprint

discord_auth_bp = Blueprint('discord_auth', __name__)

@discord_auth_bp.route('/login')
def login():
    # Discord OAuth 登入流程
    pass

@discord_auth_bp.route('/callback')
def callback():
    # OAuth 回調處理
    pass
```

#### 表格驅動資料庫藍圖 (`sheet_driven_db.py`)
```python
sheet_db_bp = Blueprint('sheet_db', __name__)

@sheet_db_bp.route('/sync', methods=['POST'])
def sync_sheet():
    # Google Sheets 同步
    pass

@sheet_db_bp.route('/data/<sheet_name>')
def get_sheet_data(sheet_name):
    # 獲取表格資料
    pass
```

## 前端系統

### 1. 主入口 (`web/portal/index.html`)
**功能特性**:
- 響應式設計
- TailwindCSS 樣式
- JavaScript 互動
- Discord 整合

**核心結構**:
```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KKGroup Portal</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body>
    <div id="app">
        <!-- 主要內容區域 -->
        <header class="bg-blue-600 text-white">
            <!-- 導航列 -->
        </header>
        <main class="container mx-auto">
            <!-- 主要內容 -->
        </main>
    </div>
    <script src="static/js/main.js"></script>
</body>
</html>
```

### 2. RPG 遊戲 (`web/portal/rpg-game-tailwind.html`)
**遊戲特色**:
- HTML5 Canvas 遊戲
- 角色系統
- 戰鬥機制
- 裝備系統
- 任務系統

**遊戲架構**:
```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <title>KKGroup RPG</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white">
    <div class="game-container">
        <!-- 遊戲畫布 -->
        <canvas id="gameCanvas" width="800" height="600"></canvas>

        <!-- UI 面板 -->
        <div class="ui-panel">
            <div id="character-stats">
                <!-- 角色狀態 -->
            </div>
            <div id="inventory">
                <!-- 背包系統 -->
            </div>
            <div id="quest-log">
                <!-- 任務日誌 -->
            </div>
        </div>
    </div>

    <script>
        // 遊戲引擎
        class RPGGame {
            constructor() {
                this.canvas = document.getElementById('gameCanvas');
                this.ctx = this.canvas.getContext('2d');
                this.player = new Player();
                this.enemies = [];
                this.items = [];
            }

            // 遊戲循環
            gameLoop() {
                this.update();
                this.render();
                requestAnimationFrame(() => this.gameLoop());
            }

            // 更新遊戲狀態
            update() {
                this.player.update();
                this.enemies.forEach(enemy => enemy.update());
            }

            // 渲染畫面
            render() {
                this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
                this.player.render(this.ctx);
                this.enemies.forEach(enemy => enemy.render(this.ctx));
            }
        }

        // 啟動遊戲
        const game = new RPGGame();
        game.gameLoop();
    </script>
</body>
</html>
```

## 活動系統 (`web/activities/`)

### 商家活動 (`merchant/`)
**功能範圍**:
- 限時活動管理
- 特殊商品銷售
- 活動獎勵發放
- 參與記錄追蹤

## 資料庫整合

### 1. 共享資料庫 (`shared/db/`)
#### AI 記憶體 (`ai_memory.py`)
```python
class AIMemory:
    def __init__(self):
        self.memory_store = {}

    def store_memory(self, key: str, value: any):
        self.memory_store[key] = value

    def retrieve_memory(self, key: str) -> any:
        return self.memory_store.get(key)
```

#### 資料庫架構 (`database_schema.py`)
```python
# 資料表定義
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String, unique=True)
    username = db.Column(db.String)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GameData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    player_data = db.Column(db.JSON)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
```

## API 設計原則

### 1. RESTful 設計
- 使用標準 HTTP 方法 (GET, POST, PUT, DELETE)
- 清晰的資源路徑
- 一致的回應格式
- 適當的 HTTP 狀態碼

### 2. 錯誤處理
```python
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

# 自定義錯誤處理
def api_error(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code
```

### 3. 認證與授權
```python
# JWT Token 驗證
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or not verify_token(token):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated
```

## 前端開發規範

### 1. TailwindCSS 使用
```html
<!-- 響應式設計 -->
<div class="container mx-auto px-4">
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <!-- 卡片組件 -->
        <div class="bg-white rounded-lg shadow-md p-6">
            <h3 class="text-lg font-semibold mb-2">標題</h3>
            <p class="text-gray-600">內容</p>
        </div>
    </div>
</div>
```

### 2. JavaScript 最佳實踐
```javascript
// 模組化設計
class GameUI {
    constructor() {
        this.elements = {
            gameCanvas: document.getElementById('gameCanvas'),
            statsPanel: document.getElementById('character-stats'),
            inventory: document.getElementById('inventory')
        };
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadGameData();
    }

    bindEvents() {
        this.elements.gameCanvas.addEventListener('click', this.handleCanvasClick.bind(this));
    }

    async loadGameData() {
        try {
            const response = await fetch('/api/game/data');
            const data = await response.json();
            this.updateUI(data);
        } catch (error) {
            console.error('載入遊戲資料失敗:', error);
        }
    }
}
```

## 部署和配置

### 1. 服務配置
**systemd 服務檔案** (`config/services/kkgroup-api.service`):
```ini
[Unit]
Description=KKGroup API Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/kkgroup
Environment=FLASK_ENV=production
ExecStart=/home/ubuntu/.venv/bin/python -m flask run --host=0.0.0.0 --port=5000
Restart=always

[Install]
WantedBy=multi-user.target
```

### 2. Nginx 配置
**反向代理設定** (`config/nginx/nginx_default.conf`):
```nginx
server {
    listen 80;
    server_name localhost;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/ubuntu/kkgroup/web/portal/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 3. Cloudflare Tunnel 整合
```python
# 隧道 URL 更新
import requests

def update_tunnel_url():
    tunnel_url = "https://your-tunnel-url.trycloudflare.com"

    # 更新配置檔案
    with open('config/tunnel_url.json', 'w') as f:
        json.dump({"url": tunnel_url}, f)

    # 通知 Discord Bot
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    requests.post(webhook_url, json={"content": f"隧道 URL 已更新: {tunnel_url}"})
```

## 效能優化

### 1. 快取策略
```python
# Redis 快取
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)

@cache.memoize(timeout=300)  # 5分鐘快取
def get_user_data(user_id: str):
    return User.query.filter_by(discord_id=user_id).first()
```

### 2. 資料庫優化
```python
# 連接池配置
SQLALCHEMY_DATABASE_URI = 'postgresql://user:pass@localhost/kkgroup'
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 10,
    'pool_recycle': 120,
    'pool_pre_ping': True
}
```

## 安全考量

### 1. CORS 配置
```python
CORS(app,
     origins=['https://your-domain.com', 'https://your-tunnel-url.trycloudflare.com'],
     methods=['GET', 'POST', 'PUT', 'DELETE'],
     allow_headers=['Content-Type', 'Authorization'])
```

### 2. 資料驗證
```python
from marshmallow import Schema, fields, validate

class UserSchema(Schema):
    username = fields.Str(required=True, validate=validate.Length(min=3, max=50))
    email = fields.Email(required=True)
    age = fields.Int(validate=validate.Range(min=13, max=120))
```

## 監控和日誌

### 1. API 監控
```python
import logging

# 請求日誌
@app.before_request
def log_request_info():
    app.logger.info(f"Request: {request.method} {request.url}")

@app.after_request
def log_response_info(response):
    app.logger.info(f"Response: {response.status_code}")
    return response
```

### 2. 錯誤追蹤
```python
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[FlaskIntegration()]
)
```

## 相關文檔

- [專案架構總覽](project-architecture.md)
- [Discord Bot 系統詳解](discord-bot-system.md)
- [Webhook 和隧道設定](webhook-and-tunnel.md)
- [編碼規則和路徑](coding-rules-and-paths.md)
