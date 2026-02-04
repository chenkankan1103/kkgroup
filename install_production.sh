#!/bin/bash
#
# Sheet Sync API 生产环境安装脚本
# 在 GCP 实例上运行此脚本来部署 Flask API
#
# 使用方式：
# chmod +x install_production.sh
# ./install_production.sh
#

set -e  # 如果任何命令失败，停止执行

echo "=========================================="
echo "🚀 Sheet Sync API 生产环境安装"
echo "=========================================="

# 1. 检查 Python 版本
echo ""
echo "✅ 检查 Python 版本..."
python3 --version

# 2. 进入项目目录
PROJECT_DIR="/path/to/kkgroup"
echo ""
echo "✅ 进入项目目录: $PROJECT_DIR"
cd "$PROJECT_DIR" || { echo "❌ 项目目录不存在"; exit 1; }

# 3. 创建虚拟环境
echo ""
echo "✅ 创建 Python 虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "   虚拟环境已创建"
else
    echo "   虚拟环境已存在"
fi

# 4. 激活虚拟环境
echo ""
echo "✅ 激活虚拟环境..."
source venv/bin/activate

# 5. 升级 pip
echo ""
echo "✅ 升级 pip..."
pip install --upgrade pip setuptools wheel

# 6. 安装依赖
echo ""
echo "✅ 安装项目依赖..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "   依赖已安装"
else
    echo "   ⚠️  requirements.txt 不存在，跳过"
fi

# 7. 安装 Gunicorn
echo ""
echo "✅ 安装 Gunicorn..."
pip install gunicorn

# 8. 测试 Flask 应用
echo ""
echo "✅ 测试 Flask 应用导入..."
python3 -c "from sheet_sync_api import app; print('✅ Flask 应用导入成功')"

# 9. 安装 Supervisor（如果未安装）
echo ""
echo "✅ 检查 Supervisor..."
if ! command -v supervisord &> /dev/null; then
    echo "   ⚠️  Supervisor 未安装，请手动安装："
    echo "   sudo apt-get update && sudo apt-get install -y supervisor"
else
    echo "   Supervisor 已安装"
fi

# 10. 复制 Supervisor 配置
echo ""
echo "✅ Supervisor 配置说明..."
echo ""
echo "   1. 编辑配置文件（需要改项目路径）:"
echo "      sudo nano /etc/supervisor/conf.d/sheet-sync-api.conf"
echo ""
echo "   2. 复制下面的内容（改 /path/to/kkgroup 为实际路径，改 ubuntu 为你的用户名）:"
echo ""
cat supervisor_sheet_sync_api.conf | sed 's/^/   /'
echo ""
echo "   3. 保存后执行:"
echo "      sudo supervisorctl reread"
echo "      sudo supervisorctl update"
echo "      sudo supervisorctl start sheet-sync-api"
echo ""

# 11. 快速启动选项
echo "=========================================="
echo "✅ 安装完成！"
echo "=========================================="
echo ""
echo "快速启动选项："
echo ""
echo "A) 测试运行（前台，用于测试）:"
echo "   cd $PROJECT_DIR"
echo "   source venv/bin/activate"
echo "   gunicorn -w 4 -b 0.0.0.0:5000 sheet_sync_api:app"
echo ""
echo "B) 使用 Supervisor（后台，生产推荐）:"
echo "   1. 编辑 /etc/supervisor/conf.d/sheet-sync-api.conf"
echo "   2. sudo supervisorctl reread && sudo supervisorctl update"
echo "   3. sudo supervisorctl start sheet-sync-api"
echo "   4. 查看日志: tail -f /var/log/sheet-sync-api.log"
echo ""
echo "=========================================="
