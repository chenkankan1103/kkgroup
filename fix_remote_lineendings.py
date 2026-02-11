#!/usr/bin/env python3
import sys

files_to_fix = [
    '/home/e193752468/kkgroup/status_dashboard.py',
    '/home/e193752468/kkgroup/webhook_logger.py',
    '/home/e193752468/kkgroup/bot.py'
]

for fpath in files_to_fix:
    try:
        with open(fpath, 'rb') as f:
            content = f.read()
        
        # 轉換 CRLF 為 LF
        content = content.replace(b'\r\n', b'\n')
        
        with open(fpath, 'wb') as f:
            f.write(content)
        
        print(f'✅ Fixed {fpath}')
    except Exception as e:
        print(f'❌ Error fixing {fpath}: {e}')

print('Done')
