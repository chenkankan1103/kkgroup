import asyncio
from status_dashboard import update_dashboard_metrics

class DummyBot:
    def get_channel(self, id):
        print(f"dummy get_channel {id}")
        return None

async def main():
    await update_dashboard_metrics(DummyBot())

if __name__ == '__main__':
    asyncio.run(main())
