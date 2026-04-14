import asyncio
from status_dashboard import initialize_dashboard

class DummyBot:
    def get_channel(self, id):
        print(f"dummy get_channel {id}")
        return None

async def main():
    # 此脚本已弃用 - metrics 现在通过 status_dashboard 的独立更新任务自动处理
    print("This script is deprecated. Metrics are now handled by the automatic update task in status_dashboard.")

if __name__ == '__main__':
    asyncio.run(main())
