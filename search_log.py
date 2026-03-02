import sys, re
path = r'C:\Users\88697\Desktop\kkgroup\bot_utf.log'
with open(path, encoding='utf-8', errors='ignore') as f:
    for i, line in enumerate(f, 1):
        if 'ERROR' in line or 'Traceback' in line or 'Exception' in line:
            print(i, line.strip())
            sys.exit(0)
print('no error found')
