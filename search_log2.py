import sys
path = r'C:\Users\88697\Desktop\kkgroup\bot_utf.log'
keywords = ['不存在', '重新創', 'NotFound', 'ERROR', '錯誤']
with open(path, encoding='utf-8', errors='ignore') as f:
    for i,line in enumerate(f,1):
        if any(k in line for k in keywords):
            print(i, line.strip())
            # print more context lines
            for _ in range(3):
                try: print(next(f).strip())
                except StopIteration: break
            print('----')
            # don't stop
print('search complete')
