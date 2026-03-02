import sys
path = r'C:\Users\88697\Desktop\kkgroup\bot_utf.log'
keywords = ['重新創', '不存在', 'Forbidden', '權限']
with open(path, encoding='utf-8', errors='ignore') as f:
    for i, line in enumerate(f, 1):
        if any(k in line for k in keywords):
            print(i, line.strip())
print('done')
