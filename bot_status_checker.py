#!/usr/bin/env python3
"""
機器人狀態檢查器
功能：檢查機器人服務狀態並發送報告到 Discord
可以手動執行或設定為定期任務
"""

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import subprocess
import psutil
import asyncio
import datetime

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_SYS_CHANNEL_ID = os.getenv("DISCORD_SYS_CHANNEL_ID")

def get_bot_process_status():
    """取得機器人進程狀態"""
    bot_scripts = ["bot.py", "shopbot.py", "uibot.py"]
    process_status = {}
    
    for script in bot_scripts:
        process_status[script] = {
            'running': False,
            'pid': None,
            'cpu_percent': 0,
            'memory_mb': 0,
            'uptime': 'N/A'
        }
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            cmdline = proc.info['cmdline']
            if not cmdline or len(cmdline) < 2:
                continue
                
            if 'python' in cmdline[0].lower():
                script_name = os.path.basename(cmdline[1]) if len(cmdline) > 1 else ""
                if script_name in bot_scripts:
                    process = psutil.Process(proc.info['pid'])
                    uptime_seconds = datetime.datetime.now().timestamp() - proc.info['create_time']
                    uptime_str = str(datetime.timedelta(seconds=int(uptime_seconds)))
                    
                    process_status[script_name] = {
                        'running': True,
                        'pid': proc.info['pid'],
                        'cpu_percent': process.cpu_percent(),
                        'memory_mb': process.memory_info().rss / 1024 / 1024,
                        'uptime': uptime_str
                    }
        except (psutil.NoSuchProcess, psutil.AccessDenied, IndexError):
            continue
    
    return process_status

def get_systemd_service_status():
    """取得 systemd 服務狀態"""
    services = ["discord-bot", "discord-shopbot", "discord-uibot"]
    service_status = {}
    
    for service in services:
        try:
            # 檢查服務是否啟用
            enabled_result = subprocess.run(
                ["systemctl", "is-enabled", service],
                capture_output=True,
                text=True
            )
            
            # 檢查服務是否活躍
            active_result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True
            )
            
            # 取得服務詳細狀態
            status_result = subprocess.run(
                ["systemctl", "status", service, "--no-pager", "-l"],
                capture_output=True,
                text=True
            )
            
            service_status[service] = {
                'enabled': enabled_result.stdout.strip(),
                'active': active_result.stdout.strip(),
                'status_details': status_result.stdout.split('\n')[:5]  # 只取前5行
            }
            
        except Exception as e:
            service_status[service] = {
                'enabled': 'unknown',
                'active': 'unknown',
                'status_details': [f"Error: {e}"]
            }
    
    return service_status

def get_recent_errors():
    """取得最近的錯誤日誌"""
    try:
        error_result = subprocess.run(
            ["journalctl", "-p", "err", "-n", "5", "--no-pager", "--since", "1 hour ago"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if error_result.stdout.strip():
            return error_result.stdout.strip()
        else:
            return "✅ 過去1小時內沒有發現系統錯誤"
            
    except subprocess.TimeoutExpired:
        return "⏰ 查詢錯誤日誌超時"
    except Exception as e:
        return f"❌ 無法查詢錯誤日誌: {e}"

def get_system_resources():
    """取得系統資源使用情況"""
    try:
        # CPU 使用率
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # 記憶體使用率
        memory = psutil.virtual_memory()
        
        # 磁碟使用率
        disk = psutil.disk_usage('/home/e193752468')
        
        # 系統負載
        load_avg = os.getloadavg()
        
        return {
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_used_gb': memory.used / 1024 / 1024 / 1024,
            'memory_total_gb': memory.total / 1024 / 1024 / 1024,
            'disk_percent': (disk.used / disk.total) * 100,
            'disk_used_gb': disk.used / 1024 / 1024 / 1024,
            'disk_total_gb': disk.total / 1024 / 1024 / 1024,
            'load_avg': load_avg
        }
    except Exception as e:
        return {'error': str(e)}

async def send_status_report(detailed=False):
    """發送狀態報告到 Discord"""
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    
    @bot.event
    async def on_ready():
        try:
            channel = bot.get_channel(int(DISCORD_SYS_CHANNEL_ID))
            if not channel:
                print("❌ 找不到指定的Discord頻道")
                return
            
            # 取得各種狀態資訊
            process_status = get_bot_process_status()
            service_status = get_systemd_service_status()
            system_resources = get_system_resources()
            
            # 建立主要狀態 embed
            embed = discord.Embed(
                title="🤖 機器人狀態報告",
                color=0x00ff00,
                timestamp=datetime.datetime.now()
            )
            
            # 進程狀態
            process_info = ""
            all_running = True
            for script, status in process_status.items():
                if status['running']:
                    process_info += f"✅ **{script}**\n"
                    process_info += f"   PID: {status['pid']}, 運行時間: {status['uptime']}\n"
                    process_info += f"   CPU: {status['cpu_percent']:.1f}%, 記憶體: {status['memory_mb']:.1f}MB\n\n"
                else:
                    process_info += f"❌ **{script}** - 未運行\n\n"
                    all_running = False
            
            embed.add_field(name="🔍 進程狀態", value=process_info, inline=False)
            
            # Systemd 服務狀態
            if detailed:
                service_info = ""
                for service, status in service_status.items():
                    icon = "✅" if status['active'] == 'active' else "❌"
                    service_info += f"{icon} **{service}**\n"
                    service_info += f"   啟用: {status['enabled']}, 狀態: {status['active']}\n\n"
                
                if service_info:
                    embed.add_field(name="🔧 Systemd 服務", value=service_info, inline=False)
            
            # 系統資源
            if 'error' not in system_resources:
                resource_info = f"🖥️ **CPU**: {system_resources['cpu_percent']:.1f}%\n"
                resource_info += f"🧠 **記憶體**: {system_resources['memory_percent']:.1f}% "
                resource_info += f"({system_resources['memory_used_gb']:.1f}GB/{system_resources['memory_total_gb']:.1f}GB)\n"
                resource_info += f"💾 **磁碟**: {system_resources['disk_percent']:.1f}% "
                resource_info += f"({system_resources['disk_used_gb']:.1f}GB/{system_resources['disk_total_gb']:.1f}GB)\n"
                resource_info += f"⚖️ **系統負載**: {system_resources['load_avg'][0]:.2f}, {system_resources['load_avg'][1]:.2f}, {system_resources['load_avg'][2]:.2f}"
                
                embed.add_field(name="📊 系統資源", value=resource_info, inline=False)
            
            # 設定整體狀態顏色
            if all_running:
                embed.color = 0x00ff00  # 綠色 - 一切正常
            else:
                embed.color = 0xff0000  # 紅色 - 有問題
            
            await channel.send(embed=embed)
            
            # 如果是詳細模式，額外發送錯誤日誌
            if detailed:
                recent_errors = get_recent_errors()
                if recent_errors and "沒有發現系統錯誤" not in recent_errors:
                    error_embed = discord.Embed(
                        title="⚠️ 最近的系統錯誤",
                        description=f"```\n{recent_errors[:1900]}\n```",  # Discord 限制
                        color=0xff9900,
                        timestamp=datetime.datetime.now()
                    )
                    await channel.send(embed=error_embed)
                
                # 發送服務詳細日誌
                for service, status in service_status.items():
                    if status['active'] != 'active':  # 只顯示有問題的服務
                        service_details = '\n'.join(status['status_details'])
                        if len(service_details) > 1800:
                            service_details = service_details[:1800] + "..."
                        
                        service_embed = discord.Embed(
                            title=f"❌ {service} 服務詳情",
                            description=f"```\n{service_details}\n```",
                            color=0xff0000,
                            timestamp=datetime.datetime.now()
                        )
                        await channel.send(embed=service_embed)
            
            print("📢 狀態報告已發送")
            
        except Exception as e:
            print(f"❌ 發送狀態報告失敗: {e}")
        finally:
            await bot.close()
    
    try:
        await bot.start(TOKEN)
    except Exception as e:
        print(f"❌ Discord狀態報告BOT啟動失敗: {e}")

def main():
    """主程式"""
    import sys
    
    detailed = False
    if len(sys.argv) > 1 and sys.argv[1] in ['--detailed', '-d']:
        detailed = True
        print("🔍 執行詳細狀態檢查...")
    else:
        print("🔍 執行基本狀態檢查...")
    
    try:
        asyncio.run(send_status_report(detailed=detailed))
        print("✅ 狀態檢查完成")
    except Exception as e:
        print(f"❌ 狀態檢查失敗: {e}")

if __name__ == "__main__":
    main()
