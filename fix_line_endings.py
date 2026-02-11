#!/usr/bin/env python3
# 確保文件使用 \n 而不是 \r\n
files = ['status_dashboard.py', 'webhook_logger.py', 'bot.py']
for fname in files:
    with open(fname, 'rb') as f:
        content = f.read()
    content = content.replace(b'\r\n', b'\n')
    with open(fname, 'wb') as f:
        f.write(content)
    print(f'{fname}: OK')
