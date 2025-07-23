import threading
import subprocess
import time
import socket

# 等待網路可用：試著解析 discord.com DNS
def wait_for_network(host="discord.com", port=443, retries=5, delay=5):
    for i in range(retries):
        try:
            socket.create_connection((host, port), timeout=3)
            print(f"✅ 網路已連通：{host}:{port}")
            return True
        except OSError:
            print(f"⏳ DNS 尚未就緒，等待 {delay} 秒...（第 {i+1}/{retries} 次）")
            time.sleep(delay)
    print(f"❌ 無法連線到 {host}:{port}，可能會造成 Discord bot 啟動失敗")
    return False

# 執行子程式，並可延遲執行
def run_process(command, delay=0):
    if delay > 0:
        print(f"⏳ 等待 {delay} 秒再啟動: {command}")
        time.sleep(delay)
    print(f"🚀 啟動進程: {command}")
    try:
        process = subprocess.Popen(command, shell=True)
        process.wait()
        print(f"✅ 進程結束: {command}")
    except Exception as e:
        print(f"❌ 執行失敗: {command} - {e}")

if __name__ == "__main__":
    print("🚀 啟動所有服務...")

    # 等待網路（避免 Discord DNS 問題）
    wait_for_network()

    # 定義所有要啟動的服務（命令, 延遲秒數）
    services = [
        ("python bot.py", 5),        # 主 bot 延遲 5 秒
        ("python uibot.py", 10),     # UI bot 延遲 10 秒
        ("python web.py", 0),        # Flask 後台不用延遲
        ("python shopbot.py", 7),    # 黑市 bot 延遲 7 秒
    ]

    threads = []
    for command, delay in services:
        t = threading.Thread(target=run_process, args=(command, delay))
        t.start()
        threads.append(t)

    # 等待全部完成
    for t in threads:
        t.join()

    print("🔚 所有服務已結束")


# ===================================

# 方案二：最簡版 - 同時啟動所有程式
"""
import subprocess
import os

if __name__ == "__main__":
    print("🚀 啟動所有服務...")
    
    # 同時啟動所有程式
    processes = []
    commands = ["python bot.py", "python uibot.py", "python web.py"]
    
    for cmd in commands:
        print(f"🚀 啟動: {cmd}")
        process = subprocess.Popen(cmd, shell=True)
        processes.append(process)
    
    # 等待所有程式結束
    for process in processes:
        process.wait()
    
    print("🔚 所有服務已結束")
"""