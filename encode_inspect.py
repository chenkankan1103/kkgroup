import base64
code="""import asyncio, sys
sys.path.append('/home/e193752468/kkgroup')
from status_dashboard import inspect_dashboard, set_bot_type
set_bot_type('bot')
async def main():
    await inspect_dashboard()
asyncio.run(main())
"""
print(base64.b64encode(code.encode('utf-8')).decode())
