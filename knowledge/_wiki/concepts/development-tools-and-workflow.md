# 開發工具和流程指南

## 開發環境設定

### 1. 本機開發環境
**Python 環境**:
```bash
# 建立虛擬環境
python -m venv .venv

# 啟動虛擬環境
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 安裝依賴
pip install -r requirements.txt
```

**環境變數設定** (`.env`):
```env
# Discord Bot Tokens
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_SHOPBOT_TOKEN=your_shopbot_token_here
DISCORD_UIBOT_TOKEN=your_uibot_token_here

# Database
DATABASE_URL=sqlite:///data/database.db

# API Keys
GOOGLE_AI_API_KEY=your_google_ai_key
STOCK_API_KEY=your_stock_api_key

# Webhooks
DISCORD_WEBHOOK_URL=your_webhook_url
ERROR_WEBHOOK_URL=your_error_webhook_url

# Cloudflare
CLOUDFLARE_TUNNEL_URL=your_tunnel_url
```

### 2. 開發工具配置
**VS Code 推薦擴充套件**:
```json
{
    "recommendations": [
        "ms-python.python",
        "ms-python.flake8",
        "ms-python.black-formatter",
        "bradlc.vscode-tailwindcss",
        "ms-vscode.powershell",
        "gitlab.gitlab-workflow"
    ]
}
```

**Git 配置**:
```bash
# 設定使用者資訊
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# 設定預設編輯器
git config --global core.editor "code --wait"

# 設定分行符號
git config --global core.autocrlf true  # Windows
git config --global core.autocrlf input  # Linux/Mac
```

## 開發流程

### 1. 分支策略
**主要分支**:
- `main`: 生產環境分支
- `develop`: 開發分支
- `feature/*`: 功能分支
- `hotfix/*`: 緊急修復分支

**工作流程**:
```bash
# 1. 從 main 建立功能分支
git checkout main
git pull origin main
git checkout -b feature/new-feature

# 2. 開發和提交
git add .
git commit -m "feat: add new feature"

# 3. 推送並建立 Pull Request
git push origin feature/new-feature

# 4. 合併到 main
git checkout main
git merge feature/new-feature
git push origin main
```

### 2. 提交訊息規範
**Conventional Commits**:
```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

**類型說明**:
- `feat`: 新功能
- `fix`: 錯誤修復
- `docs`: 文檔更新
- `style`: 程式碼格式調整
- `refactor`: 重構
- `test`: 測試相關
- `chore`: 建置過程或輔助工具的變動

**範例**:
```bash
git commit -m "feat(bot): add new slash command for user management"
git commit -m "fix(api): resolve database connection timeout issue"
git commit -m "docs: update API documentation with new endpoints"
```

## 測試策略

### 1. 單元測試
**測試結構**:
```
tests/
├── unit/
│   ├── test_bot.py
│   ├── test_api.py
│   └── test_utils.py
├── integration/
│   ├── test_discord_integration.py
│   └── test_database_integration.py
└── e2e/
    └── test_full_workflow.py
```

**測試範例** (`tests/unit/test_bot.py`):
```python
import pytest
import asyncio
from unittest.mock import Mock, patch
from bots.bot import KKGroupBot

@pytest.fixture
def bot():
    return KKGroupBot()

@pytest.mark.asyncio
async def test_bot_ready_event(bot):
    """測試 Bot 準備就緒事件"""
    with patch('discord.Client') as mock_client:
        await bot.on_ready()
        mock_client.assert_called_once()

def test_command_registration(bot):
    """測試指令註冊"""
    assert len(bot.tree.get_commands()) > 0
```

### 2. 整合測試
**Discord 整合測試**:
```python
import pytest
from discord.ext.test import bot, message

@pytest.mark.asyncio
async def test_slash_command():
    """測試 Slash 指令"""
    with bot() as b:
        await message("!test")
        assert b.sent_messages[0].content == "Test response"
```

### 3. 測試執行
**執行測試**:
```bash
# 執行所有測試
pytest

# 執行特定測試檔案
pytest tests/unit/test_bot.py

# 執行並生成覆蓋率報告
pytest --cov=. --cov-report=html

# 執行特定測試類別
pytest tests/unit/test_bot.py::TestBotCommands
```

## 程式碼品質

### 1. 程式碼格式化
**Black 配置** (`pyproject.toml`):
```toml
[tool.black]
line-length = 88
target-version = ['py38']
include = '\.pyi?$'
extend-exclude = '''
/(
  # directories
  \.eggs
  | \.git
  | \.venv
  | build
  | dist
)/
'''
```

**執行格式化**:
```bash
# 格式化所有 Python 檔案
black .

# 檢查格式但不修改
black --check .

# 格式化特定檔案
black bots/bot.py
```

### 2. 程式碼檢查
**Flake8 配置** (`.flake8`):
```ini
[flake8]
max-line-length = 88
extend-ignore = E203, W503
exclude = .git,__pycache__,docs/source/conf.py,old,build,dist
```

**執行檢查**:
```bash
# 檢查所有檔案
flake8 .

# 檢查特定目錄
flake8 bots/

# 產生詳細報告
flake8 --format=html --output-file=flake8-report.html .
```

### 3. 型別檢查
**MyPy 配置** (`mypy.ini`):
```ini
[mypy]
python_version = 3.8
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True

[mypy-discord.*]
ignore_missing_imports = True

[mypy-flask.*]
ignore_missing_imports = True
```

## 自動化工具

### 1. 指令管理器
**指令管理腳本** (`scripts/commands_manager.py`):
```python
#!/usr/bin/env python3
import json
import os
from pathlib import Path

class CommandsManager:
    def __init__(self):
        self.registry_path = Path("config/commands_registry.json")
        self.load_registry()
    
    def load_registry(self):
        if self.registry_path.exists():
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                self.registry = json.load(f)
        else:
            self.registry = {"commands": []}
    
    def save_registry(self):
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)
    
    def add_command(self, name: str, description: str, category: str = "general"):
        command = {
            "name": name,
            "description": description,
            "category": category
        }
        self.registry["commands"].append(command)
        self.save_registry()
        print(f"指令 '{name}' 已新增到註冊表")
    
    def list_commands(self, category: str = None):
        commands = self.registry["commands"]
        if category:
            commands = [cmd for cmd in commands if cmd["category"] == category]
        
        for cmd in commands:
            print(f"- {cmd['name']}: {cmd['description']}")

# 使用範例
if __name__ == "__main__":
    manager = CommandsManager()
    manager.add_command("test", "測試指令", "general")
    manager.list_commands()
```

### 2. 自動化腳本
**依賴更新腳本** (`scripts/update_dependencies.py`):
```python
#!/usr/bin/env python3
import subprocess
import json
from pathlib import Path

def update_requirements():
    """更新 requirements.txt"""
    print("正在更新依賴套件...")
    
    # 檢查過期套件
    result = subprocess.run(['pip', 'list', '--outdated'], 
                          capture_output=True, text=True)
    
    if result.stdout:
        print("發現過期套件:")
        print(result.stdout)
        
        # 更新套件
        subprocess.run(['pip', 'install', '--upgrade', 'pip'])
        subprocess.run(['pip', 'install', '--upgrade', '-r', 'requirements.txt'])
        
        # 重新生成 requirements.txt
        subprocess.run(['pip', 'freeze', '>', 'requirements.txt'], shell=True)
        print("依賴套件更新完成")
    else:
        print("所有套件都是最新版本")

if __name__ == "__main__":
    update_requirements()
```

## 除錯工具

### 1. 日誌系統
**日誌配置** (`utils/logger.py`):
```python
import logging
import sys
from pathlib import Path

def setup_logger(name: str, level: str = "INFO"):
    """設定日誌記錄器"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # 建立日誌目錄
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 檔案處理器
    file_handler = logging.FileHandler(log_dir / f"{name}.log")
    file_handler.setLevel(logging.DEBUG)
    
    # 控制台處理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # 格式設定
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger
```

### 2. 效能分析
**效能分析工具** (`utils/profiler.py`):
```python
import time
import functools
from typing import Callable

def profile_time(func: Callable) -> Callable:
    """裝飾器：測量函數執行時間"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        print(f"{func.__name__} 執行時間: {end_time - start_time:.4f} 秒")
        return result
    return wrapper

def profile_memory(func: Callable) -> Callable:
    """裝"""裝飾器：測量記憶體使用"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / 1024 / 1024  # MB
        
        result = func(*args, **kwargs)
        
        mem_after = process.memory_info().rss / 1024 / 1024  # MB
        print(f"{func.__name__} 記憶體使用: {mem_after - mem_before:.2f} MB")
        
        return result
    return wrapper
```

## 文檔生成

### 1. API 文檔
**OpenAPI 規範** (`docs/api.yaml`):
```yaml
openapi: 3.0.0
info:
  title: KKGroup API
  version: 1.0.0
  description: KKGroup Discord Bot API 文檔

paths:
  /api/user/{user_id}:
    get:
      summary: 獲取用戶資訊
      parameters:
        - name: user_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: 成功回應
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  username:
                    type: string
```

### 2. 程式碼文檔
**Docstring 範例**:
```python
def process_user_data(user_id: str, data: dict) -> dict:
    """處理用戶資料
    
    Args:
        user_id: 用戶 ID
        data: 用戶資料字典
        
    Returns:
        處理後的用戶資料
        
    Raises:
        ValueError: 當用戶 ID 無效時
        KeyError: 當必要資料缺失時
        
    Example:
        >>> result = process_user_data("123", {"name": "John"})
        >>> print(result["name"])
        John
    """
    if not user_id:
        raise ValueError("用戶 ID 不能為空")
    
    # 處理邏輯
    processed_data = data.copy()
    processed_data["user_id"] = user_id
    processed_data["processed_at"] = datetime.now().isoformat()
    
    return processed_data
```

## 版本控制

### 1. 版本標記
**版本管理** (`version.py`):
```python
__version__ = "1.0.0"
__build__ = "20240511"

def get_version():
    """獲取當前版本資訊"""
    return f"{__version__}.{__build__}"

def increment_version(part: str = "patch"):
    """遞增版本號"""
    major, minor, patch = map(int, __version__.split('.'))
    
    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    else:  # patch
        patch += 1
    
    global __version__
    __version__ = f"{major}.{minor}.{patch}"
    return __version__
```

### 2. 發布流程
**發布腳本** (`scripts/release.py`):
```python
#!/usr/bin/env python3
import subprocess
from version import increment_version, get_version

def create_release():
    """建立新版本發布"""
    print("開始建立發布...")
    
    # 1. 更新版本號
    new_version = increment_version()
    print(f"版本號更新為: {new_version}")
    
    # 2. 提交版本變更
    subprocess.run(['git', 'add', 'version.py'], check=True)
    subprocess.run(['git', 'commit', '-m', f'chore: bump version to {new_version}'], check=True)
    
    # 3. 建立標籤
    subprocess.run(['git', 'tag', '-a', f'v{new_version}', '-m', f'Release version {new_version}'], check=True)
    
    # 4. 推送到遠端
    subprocess.run(['git', 'push', 'origin', 'main'], check=True)
    subprocess.run(['git', 'push', 'origin', f'v{new_version}'], check=True)
    
    print(f"發布 {new_version} 完成！")

if __name__ == "__main__":
    create_release()
```

## 相關文檔

- [專案架構總覽](project-architecture.md)
- [Discord Bot 系統詳解](discord-bot-system.md)
- [Web API 和遊戲系統](web-api-and-game-system.md)
- [部署和維運指南](deployment-and-operations.md)
- [開發工作流程](development-workflow.md)
- [LogMonitor 與 Auto AI Fix 流程總覽](log_monitor_pipeline.md)
- [GitHub Actions AI 除錯系統](../github-actions-ai-debugging.md)
- [編碼規則和路徑](coding-rules-and-paths.md)
