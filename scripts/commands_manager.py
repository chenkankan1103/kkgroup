#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KKGroup 統一指令管理工具

統一管理所有系統指令，包括：
- GCP VM SSH 指令
- Systemd 服務管理
- 日誌查詢
- 診斷工具
- Git 操作

使用方式：
  python scripts/commands_manager.py --help
  python scripts/commands_manager.py run bot restart
  python scripts/commands_manager.py list
"""

import json
import subprocess
import argparse
import sys
import shutil
from typing import Dict, List, Any
from pathlib import Path


def resolve_gcloud_command() -> List[str]:
    """解析可供 subprocess 使用的 gcloud 執行命令。"""
    candidates = ["gcloud", "gcloud.cmd", "gcloud.exe", "gcloud.ps1", "gcloud.bat"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if not resolved:
            continue
        if resolved.lower().endswith(".ps1"):
            powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
            if powershell:
                return [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    resolved,
                ]
            continue
        return [resolved]
    raise FileNotFoundError(
        "找不到 gcloud CLI，請確認 Google Cloud SDK 已安裝並加入 PATH"
    )


class CommandsManager:
    def __init__(self, registry_path: str = "config/commands_registry.json"):
        """初始化指令管理器"""
        self.registry_path = Path(registry_path)
        self.registry = self._load_registry()
        self.gcloud_command = None

        # GCP 連接參數
        self.gcp_instance = (
            self.registry.get("gcp", {}).get("connection", {}).get("instance", "")
        )
        self.gcp_zone = (
            self.registry.get("gcp", {}).get("connection", {}).get("zone", "")
        )
        self.gcp_tunnel = (
            self.registry.get("gcp", {}).get("connection", {}).get("tunnel", "iap")
        )

    def _load_registry(self) -> Dict[str, Any]:
        """載入指令註冊表"""
        if not self.registry_path.exists():
            print(f"❌ 找不到指令註冊表: {self.registry_path}")
            sys.exit(1)

        with open(self.registry_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_gcp_ssh_command(self, remote_command: str) -> List[str]:
        """構建 GCP SSH 命令"""
        if self.gcloud_command is None:
            self.gcloud_command = resolve_gcloud_command()

        return self.gcloud_command + [
            "-q",
            "compute",
            "ssh",
            self.gcp_instance,
            "--zone",
            self.gcp_zone,
            f"--tunnel-through-{self.gcp_tunnel}",
            "--command",
            remote_command,
        ]

    def run_service_command(self, service: str, action: str) -> bool:
        """執行服務命令"""
        if service not in self.registry.get("services", {}):
            print(f"❌ 未知的服務: {service}")
            return False

        service_config = self.registry["services"][service]

        if action == "restart":
            command = service_config.get("restart", "")
        elif action == "status":
            command = service_config.get("status", "")
        else:
            print(f"❌ 未知的操作: {action}")
            return False

        if not command:
            print(f"❌ 找不到 {service} 的 {action} 命令")
            return False

        return self._execute_ssh_command(command)

    def get_service_logs(self, service: str, log_type: str = "recent_50") -> bool:
        """獲取服務日誌"""
        if service not in self.registry.get("services", {}):
            print(f"❌ 未知的服務: {service}")
            return False

        service_config = self.registry["services"][service]
        logs_config = service_config.get("logs", {})

        if log_type not in logs_config:
            available = ", ".join(logs_config.keys())
            print(f"❌ 未知的日誌類型: {log_type}")
            print(f"   可用: {available}")
            return False

        command = logs_config[log_type]
        return self._execute_ssh_command(command)

    def run_diagnostic(self, diag_name: str) -> bool:
        """執行診斷命令"""
        diagnostics = self.registry.get("diagnostics", {})

        if diag_name not in diagnostics:
            available = ", ".join(diagnostics.keys())
            print(f"❌ 未知的診斷: {diag_name}")
            print(f"   可用: {available}")
            return False

        diag_config = diagnostics[diag_name]
        command = diag_config.get("command", "")

        if not command:
            print(f"❌ 找不到 {diag_name} 的命令")
            return False

        print(f"📋 執行診斷: {diag_config.get('name', diag_name)}")
        print("=" * 60)
        return self._execute_ssh_command(command)

    def run_management_command(self, cmd_name: str) -> bool:
        """執行管理命令"""
        management = self.registry.get("management", {})

        if cmd_name not in management:
            available = ", ".join(management.keys())
            print(f"❌ 未知的管理命令: {cmd_name}")
            print(f"   可用: {available}")
            return False

        cmd_config = management[cmd_name]
        commands = cmd_config.get("commands", [])

        print(f"📋 執行: {cmd_config.get('name', cmd_name)}")
        print("=" * 60)

        success = True
        for i, command in enumerate(commands, 1):
            print(f"\n[{i}/{len(commands)}] 執行: {command}")
            if not self._execute_ssh_command(command):
                success = False
                break

        return success

    def _execute_ssh_command(self, remote_command: str) -> bool:
        """執行 SSH 命令"""
        try:
            ssh_cmd = self._build_gcp_ssh_command(remote_command)

            print(
                f"💻 {remote_command[:80]}{'...' if len(remote_command) > 80 else ''}"
            )
            print()

            result = subprocess.run(ssh_cmd, check=False)
            return result.returncode == 0
        except KeyboardInterrupt:
            print("\n⏹️  已中止")
            return False
        except Exception as e:
            print(f"❌ 執行失敗: {e}")
            return False

    def list_services(self) -> None:
        """列出所有服務"""
        services = self.registry.get("services", {})
        print("\n📦 可用服務:")
        print("=" * 60)
        for service_name, config in services.items():
            print(f"  • {service_name}")
            print(f"    名稱: {config.get('name', 'N/A')}")
            logs = config.get("logs", {})
            print(f"    日誌類型: {', '.join(logs.keys())}")
            print()

    def list_diagnostics(self) -> None:
        """列出所有診斷工具"""
        diagnostics = self.registry.get("diagnostics", {})
        print("\n🔍 可用診斷:")
        print("=" * 60)
        for diag_name, config in diagnostics.items():
            print(f"  • {diag_name}")
            print(f"    {config.get('name', 'N/A')}")
        print()

    def list_management(self) -> None:
        """列出所有管理命令"""
        management = self.registry.get("management", {})
        print("\n⚙️  可用管理命令:")
        print("=" * 60)
        for cmd_name, config in management.items():
            print(f"  • {cmd_name}")
            print(f"    {config.get('name', 'N/A')}")
            commands = config.get("commands", [])
            print(f"    命令數: {len(commands)}")
        print()

    def list_all(self) -> None:
        """列出所有可用命令"""
        print("\n" + "=" * 60)
        print("🎯 KKGroup 統一指令管理系統")
        print("=" * 60)
        self.list_services()
        self.list_diagnostics()
        self.list_management()


def main():
    parser = argparse.ArgumentParser(
        description="KKGroup 統一指令管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 查看所有可用指令
  python scripts/commands_manager.py list

  # 執行服務操作
  python scripts/commands_manager.py run bot restart
  python scripts/commands_manager.py run bot status

  # 查看日誌
  python scripts/commands_manager.py logs bot recent_50
  python scripts/commands_manager.py logs bot errors_100

  # 執行診斷
  python scripts/commands_manager.py diag tunnel_config
  python scripts/commands_manager.py diag all_services

  # 執行管理命令
  python scripts/commands_manager.py manage restart_all
  python scripts/commands_manager.py manage restart_bots
        """,
    )

    subparsers = parser.add_subparsers(dest="action", help="操作")

    # list 命令
    subparsers.add_parser("list", help="列出所有可用指令")

    # run 命令 (服務操作)
    run_parser = subparsers.add_parser("run", help="執行服務操作")
    run_parser.add_argument("service", help="服務名稱")
    run_parser.add_argument("operation", choices=["restart", "status"], help="操作")

    # logs 命令
    logs_parser = subparsers.add_parser("logs", help="查看服務日誌")
    logs_parser.add_argument("service", help="服務名稱")
    logs_parser.add_argument(
        "log_type", nargs="?", default="recent_50", help="日誌類型"
    )

    # diag 命令 (診斷)
    diag_parser = subparsers.add_parser("diag", help="執行診斷")
    diag_parser.add_argument("diagnostic", help="診斷名稱")

    # manage 命令 (管理)
    manage_parser = subparsers.add_parser("manage", help="執行管理命令")
    manage_parser.add_argument("command", help="管理命令")

    args = parser.parse_args()

    manager = CommandsManager()

    if args.action == "list":
        manager.list_all()
    elif args.action == "run":
        success = manager.run_service_command(args.service, args.operation)
        sys.exit(0 if success else 1)
    elif args.action == "logs":
        success = manager.get_service_logs(args.service, args.log_type)
        sys.exit(0 if success else 1)
    elif args.action == "diag":
        success = manager.run_diagnostic(args.diagnostic)
        sys.exit(0 if success else 1)
    elif args.action == "manage":
        success = manager.run_management_command(args.command)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
