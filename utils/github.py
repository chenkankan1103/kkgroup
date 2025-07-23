import os
import requests

def test_github_access(token: str = None) -> tuple:
    """
    測試 GitHub Token 是否有效，並回傳結果
    :param token: Personal Access Token，若未指定則自動讀取環境變數 GITHUB_TOKEN 或 GITHUB_TOKEN
    :return: (ok: bool, msg: str)
    """
    # 支援自動讀取 DISCORD_GITHUB_TOKEN 或 GITHUB_TOKEN
    if token is None:
        token = os.environ.get("DISCORD_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return False, "未提供 GitHub Token，請設定 GITHUB_TOKEN 或 DISCORD_GITHUB_TOKEN 環境變數"

    url = "https://api.github.com/user"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            user = resp.json().get("login", "unknown")
            return True, f"GitHub 連線成功，用戶: {user}"
        else:
            return False, f"GitHub 連線失敗，狀態碼: {resp.status_code}，訊息: {resp.text}"
    except Exception as e:
        return False, f"GitHub 連線失敗，錯誤: {e}"