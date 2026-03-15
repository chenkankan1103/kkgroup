import asyncio
import requests
from utils.stock_api import fetch_chart

async def check():
    symbols = [('GC=F', '黃金'), ('CL=F', '原油')]
    
    for symbol, name in symbols:
        url = await fetch_chart(symbol)
        if url:
            resp = requests.get(url, timeout=10)
            print(name + ' (' + symbol + '):')
            print('  HTTP: ' + str(resp.status_code))
            ct = resp.headers.get('Content-Type', '?')
            print('  Content-Type: ' + ct)
            print('  Size: ' + str(len(resp.content)) + ' bytes')
            if resp.status_code == 200 and 'image' in ct:
                print('  OK 有效的圖表')
            else:
                print('  WARN 可能的問題')
        print()

asyncio.run(check())
