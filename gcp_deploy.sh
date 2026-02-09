#!/bin/bash
# GCP kkgroup 自動部署腳本
# 此腳本將在 GCP VM 上執行，自動配置和啟動 kkgroup bot

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ===================== 函數定義 =====================
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# ===================== 初始檢查 =====================
echo ""
echo -e "${BLUE}🚀 GCP kkgroup 部署工具${NC}"
echo "════════════════════════════════════════"
echo ""

# 檢查 Python 版本
print_info "檢查 Python 環境..."
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 未安裝"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
print_success "發現 $PYTHON_VERSION"

# ===================== 克隆/更新倉庫 =====================
echo ""
print_info "檢查 kkgroup 倉庫..."

if [ -d "/home/kankan/kkgroup" ]; then
    print_success "倉庫已存在，正在更新..."
    cd /home/kankan/kkgroup
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || print_warning "無法自動拉取更新"
else
    print_warning "未找到 kkgroup 倉庫"
    print_info "請手動克隆或使用 SCP 傳輸"
    echo ""
    echo "方法 1: 使用 git clone (需要 SSH 訪問權限)"
    echo "  git clone git@github.com:你的用戶名/kkgroup.git /home/kankan/kkgroup"
    echo ""
    echo "方法 2: 從本地機器傳輸"
    echo "  scp -r C:\\Users\\88697\\Desktop\\kkgroup/* gcp-kkgroup:/home/kankan/kkgroup/"
    echo ""
    exit 1
fi

print_success "倉庫路徑: /home/kankan/kkgroup"

# ===================== 虛擬環境配置 =====================
echo ""
print_info "配置虛擬環境..."

if [ ! -d ".venv" ]; then
    print_warning "虛擬環境不存在，正在創建..."
    python3 -m venv .venv
    print_success "虛擬環境已創建"
else
    print_success "虛擬環境已存在"
fi

# 激活虛擬環境
source .venv/bin/activate
print_success "虛擬環境已激活"

# ===================== 安裝依賴 =====================
echo ""
print_info "安裝 Python 依賴..."

if [ -f "requirements.txt" ]; then
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    print_success "依賴安裝完成"
else
    print_error "找不到 requirements.txt"
    exit 1
fi

# ===================== 環境變數配置 =====================
echo ""
print_info "檢查 .env 文件..."

if [ ! -f ".env" ]; then
    print_warning ".env 文件不存在，正在創建模板..."
    cat > .env << 'EOF'
# Discord Bot Token
DISCORD_TOKEN=YOUR_TOKEN_HERE

# Google AI API
AI_API_KEY=YOUR_GOOGLE_API_KEY
AI_API_URL=https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent
AI_API_MODEL=gemini-pro

# Groq API (備用)
GROQ_API_KEY=YOUR_GROQ_API_KEY

# 數據庫配置
DB_HOST=localhost
DB_USER=kkgroup_user
DB_PASSWORD=secure_password_here
DB_NAME=kkgroup_db
EOF
    print_success ".env 模板已創建"
    print_warning "請編輯 .env 文件，添加必要的 API 密鑰"
    echo ""
    echo "編輯 .env:"
    echo "  nano /home/kankan/kkgroup/.env"
    echo ""
else
    print_success ".env 文件已存在"
fi

# ===================== 依賴驗證 =====================
echo ""
print_info "驗證依賴..."

if [ -f "verify_dependencies.py" ]; then
    python verify_dependencies.py
else
    print_warning "verify_dependencies.py 不存在，跳過驗證"
fi

# ===================== 啟動 Bot =====================
echo ""
echo -e "${BLUE}════════════════════════════════════════${NC}"
print_info "部署完成！"
echo ""

read -p "是否立即啟動 Bot？ (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "正在啟動 Bot..."
    echo ""
    python bot.py
else
    print_info "保存配置完成，可以稍後手動啟動 Bot：" 
    echo ""
    echo "  cd /home/kankan/kkgroup"
    echo "  source .venv/bin/activate"
    echo "  python bot.py"
    echo ""
fi
