import os
import subprocess

from discord.ext import commands

ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))
GIT_DIR = "/home/e193752468/kkgroup"

# 定義重啟順序：先關閉的放前面，主 Bot 放最後
SERVICES = [
    ("shopbot", "shopbot.service"),
    ("uibot", "uibot.service"),
    ("bot", "bot.service"),  # 主 Bot 最後重啟
]


class AdminBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def restart_service(self, service_name: str):
        """使用 systemctl 重啟服務"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", service_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return True, f"✅ {service_name} 重啟成功"
            else:
                return False, f"❌ {service_name} 重啟失敗: {result.stderr}"
        except subprocess.TimeoutExpired:
            return False, f"⏱️ {service_name} 重啟超時"
        except Exception as e:
            return False, f"❌ {service_name} 重啟錯誤: {str(e)}"

    def stop_service(self, service_name: str):
        """停止服務"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "stop", service_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return True, f"⏸️ {service_name} 已停止"
            else:
                return False, f"❌ {service_name} 停止失敗: {result.stderr}"
        except Exception as e:
            return False, f"❌ {service_name} 停止錯誤: {str(e)}"

    def start_service(self, service_name: str):
        """啟動服務"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "start", service_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return True, f"▶️ {service_name} 已啟動"
            else:
                return False, f"❌ {service_name} 啟動失敗: {result.stderr}"
        except Exception as e:
            return False, f"❌ {service_name} 啟動錯誤: {str(e)}"

    def get_service_status(self, service_name: str):
        """獲取服務狀態"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip()
        except:
            return "unknown"

    def check_git_updates(self):
        """檢查 Git 更新"""
        try:
            subprocess.run(["git", "fetch"], cwd=GIT_DIR, check=True, timeout=10)
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD..origin/main"],
                cwd=GIT_DIR,
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            commits_behind = int(result.stdout.strip())
            return commits_behind > 0, commits_behind
        except Exception as e:
            return False, str(e)

    def get_git_update_details(self):
        """獲取更新詳情"""
        try:
            commits = (
                subprocess.check_output(
                    [
                        "git",
                        "log",
                        "HEAD..origin/main",
                        "--pretty=format:• %s (%h)",
                        "--max-count=5",
                    ],
                    cwd=GIT_DIR,
                    timeout=5,
                )
                .decode("utf-8")
                .strip()
            )

            changed_files = (
                subprocess.check_output(
                    ["git", "diff", "--name-only", "HEAD", "origin/main"],
                    cwd=GIT_DIR,
                    timeout=5,
                )
                .decode("utf-8")
                .strip()
            )

            return {
                "commits": commits if commits else "沒有 commit 資訊",
                "files": changed_files.split("\n") if changed_files else [],
            }
        except Exception as e:
            return {"commits": f"獲取失敗: {e}", "files": []}

    def pull_git_updates(self):
        """拉取 Git 更新"""
        try:
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=GIT_DIR,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            return True, result.stdout
        except Exception as e:
            return False, str(e)


async def setup(bot):
    await bot.add_cog(AdminBot(bot))
