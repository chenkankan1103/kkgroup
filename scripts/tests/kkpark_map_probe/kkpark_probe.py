"""kkpark-map 視覺驗證探針（可重用管線）

用途：以 headless Edge + CDP 跑一輪 DOM 數據面檢查，零截圖優先，輸出可解析的 JSON。

用法：
  python scripts/tests/kkpark_map_probe/kkpark_probe.py --preset no_login
  python scripts/tests/kkpark_map_probe/kkpark_probe.py --preset login_doll --fly 22.62,120.30,16
  python scripts/tests/kkpark_map_probe/kkpark_probe.py --shot out.png --clip-selector '.mk-poi'

前置預置（--preset）：
  no_login  : 教學已看 + 無存檔 + 移除登入態（預設）
  login_doll: no_login 再加 kkpark_discord_id 與 kkpark_map_avatar_cache_v1 快取（免打正式 API 即可渲染主角造型）
  login_api : 只寫 kkpark_discord_id 並清掉快取 → 強制走正式 API（端到端驗證）
  tut_only  : 只標記教學已看 + 無存檔

Discord ID 一律由 --uid 或環境變數 KKPARK_DISCORD_ID 注入，腳本內不得寫死真實 ID
（kkgroup 是公開 repo，commit 進去的真實 Discord ID 等於公開發布）。

探針檔格式（JSON，見同目錄 probes.json）：
  {"checks": [
     {"name": "poi_count", "expr": "document.querySelectorAll('.mk-poi').length",
      "until": "document.querySelectorAll('.mk-poi').length > 0", "timeout": 20}
  ]}

基準線：破圖 0、console 錯誤 0（favicon.ico 404 不算）。
路徑全部由 __file__ 推導，執行期產物（瀏覽器 profile、截圖）落在系統 temp，不污染 repo。
"""

import argparse
import base64
import contextlib
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]  # scripts/tests/kkpark_map_probe -> repo root
GAME_DIR = REPO_ROOT / 'web' / 'kkpark-map'
DEFAULT_PROBES = HERE / 'probes.json'
TMPDIR = Path(tempfile.gettempdir()) / 'kkpark_shot'
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
FAVICON_404 = 'favicon.ico'


def build_preset_inject(preset, uid):
    """在頁面腳本執行前寫入 localStorage（avatar.js 啟動時就會讀快取）"""
    lines = [
        'try {',
        "  localStorage.setItem('kkpark_map_tut_v1', '1');",
        "  localStorage.removeItem('kkpark_map_save_v1');",
    ]
    if preset == 'login_doll':
        lines += [
            f"  localStorage.setItem('kkpark_discord_id', '{uid}');",
            "  localStorage.setItem('kkpark_map_avatar_cache_v1', JSON.stringify({",
            f"    '{uid}': {{ t: Date.now(), d: {{ face: 20005, hair: 30120, skin: 12000,",
            '                                 top: 1040014, bottom: 1060096, shoes: 1072005 } }',
            '  }));',
        ]
    elif preset == 'login_api':
        # 只寫 ID 並清掉快取 → fetchPaperdoll 必須打正式 API（端到端驗證用）
        lines += [
            f"  localStorage.setItem('kkpark_discord_id', '{uid}');",
            "  localStorage.removeItem('kkpark_map_avatar_cache_v1');",
        ]
    elif preset == 'no_login':
        lines.append("  localStorage.removeItem('kkpark_discord_id');")
    lines += ['} catch (e) {}']
    return '\n'.join(lines)


class Probe:
    """headless Edge + CDP 的薄封裝：頁面準備、DOM 取值、收尾"""

    def __init__(self, root, port, cdp_port):
        self.root = Path(root)
        self.port = port
        self.cdp_port = cdp_port
        self.profile = TMPDIR / f'probe_profile_{int(time.time() * 1000)}'
        self.proc = None
        self.httpd = None
        self.ws = None
        self.mid = 0
        self.console_errors = []
        self.http_404 = []
        self._start()

    def _start(self):
        TMPDIR.mkdir(parents=True, exist_ok=True)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(self.root))
        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', self.port), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.proc = subprocess.Popen(
            [
                EDGE,
                '--headless=new',
                '--disable-gpu',
                '--no-first-run',
                '--no-default-browser-check',
                f'--remote-debugging-port={self.cdp_port}',
                f'--user-data-dir={self.profile}',
                'about:blank',
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ws_url = None
        for _ in range(60):
            try:
                tabs = json.load(
                    urllib.request.urlopen(f'http://127.0.0.1:{self.cdp_port}/json/list', timeout=2)
                )
                pages = [t for t in tabs if t.get('type') == 'page']
                if pages:
                    ws_url = pages[0]['webSocketDebuggerUrl']
                    break
            except (OSError, ValueError):
                # DevTools 端點還沒起來，或回應不是 JSON——繼續輪詢
                pass
            time.sleep(0.3)
        if not ws_url:
            raise RuntimeError('devtools target not found')
        from websockets.sync.client import connect

        self.ws = connect(ws_url, max_size=64 * 1024 * 1024)

    def cmd(self, method, params=None):
        self.mid += 1
        i = self.mid
        self.ws.send(json.dumps({'id': i, 'method': method, 'params': params or {}}))
        while True:
            msg = json.loads(self.ws.recv(timeout=30))
            method = msg.get('method')
            if method == 'Log.entryAdded':
                entry = msg['params']['entry']
                if entry.get('level') == 'error':
                    self.console_errors.append(
                        (entry.get('source'), (entry.get('text') or '')[:120])
                    )
            elif method == 'Network.responseReceived':
                resp = msg['params']['response']
                if resp.get('status') == 404:
                    self.http_404.append(resp.get('url', '')[:120])
            if msg.get('id') == i:
                return msg

    def ev(self, expr):
        """在頁面內求值；回傳 JSON 字串時自動解析成物件"""
        res = self.cmd('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
        result = res.get('result', {}).get('result', {})
        if result.get('subtype') == 'error':
            return {'__error': result.get('description', '')[:200]}
        value = result.get('value')
        if isinstance(value, str):
            text = value.strip()
            if text.startswith(('{', '[')):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return value
        return value

    def close(self):
        with contextlib.suppress(Exception):
            if self.ws:
                self.ws.close()
        if self.proc:
            self.proc.kill()
        if self.httpd:
            self.httpd.shutdown()
        shutil.rmtree(self.profile, ignore_errors=True)


def run(args):
    spec = json.loads(Path(args.probes).read_text(encoding='utf-8'))
    checks = spec.get('checks', [])
    port = args.port or (8810 + (os.getpid() % 200))
    probe = Probe(args.root, port, args.cdp_port or (9300 + (os.getpid() % 200)))
    out = {
        'preset': args.preset,
        'checks': {},
        'baseline': {},
        'console_errors': [],
        'http_404': [],
    }
    try:
        probe.cmd('Page.enable')
        probe.cmd('Log.enable')
        probe.cmd('Network.enable')
        probe.cmd(
            'Page.addScriptToEvaluateOnNewDocument',
            {'source': build_preset_inject(args.preset, args.uid)},
        )
        probe.cmd('Page.navigate', {'url': f'http://127.0.0.1:{port}/index.html'})
        time.sleep(args.settle)
        out['checks']['page_ready'] = probe.ev('document.readyState')
        if args.enter:
            out['checks']['enter'] = probe.ev(
                f"(function(){{var b=document.getElementById('{args.enter}');"
                " if(!b) return 'no-button'; b.click(); return 'clicked';})()"
            )
            time.sleep(args.settle_after_enter)
        if args.fly:
            lat, lng, zoom = args.fly.split(',')
            out['checks']['fly'] = probe.ev(f"GameMap.flyTo({lat}, {lng}, {zoom}); 'flew'")
            time.sleep(args.settle_after_fly)

        for chk in checks:
            name = chk.get('name', 'check')
            until = chk.get('until')
            timeout = float(chk.get('timeout', 20))
            if until:
                deadline = time.time() + timeout
                while time.time() < deadline:
                    if probe.ev(until):
                        break
                    time.sleep(0.6)
            out['checks'][name] = probe.ev(chk['expr'])

        broken = probe.ev(
            'Array.from(document.images).filter(function(i){return i.complete && '
            'i.naturalWidth===0;}).map(function(i){return i.src.slice(0,80);})'
        )
        out['baseline']['broken_images'] = broken if isinstance(broken, list) else []
        real_errors = [e for e in probe.console_errors if not (e[0] == 'network' and '404' in e[1])]
        real_404 = [u for u in probe.http_404 if FAVICON_404 not in u]
        out['console_errors'] = probe.console_errors
        out['http_404'] = probe.http_404
        out['baseline']['console_errors'] = real_errors
        out['baseline']['non_favicon_404'] = real_404
        out['baseline']['pass'] = (
            len(out['baseline']['broken_images']) == 0
            and len(real_errors) == 0
            and len(real_404) == 0
        )

        if args.shot:
            shot_args = {'format': 'png'}
            if args.clip_selector:
                rect = probe.ev(
                    f"(function(){{var el=document.querySelector('{args.clip_selector}');"
                    ' if(!el) return null; var r=el.getBoundingClientRect(); var p=12;'
                    ' return JSON.stringify({x:Math.max(0,r.left-p),y:Math.max(0,r.top-p),'
                    ' width:r.width+p*2,height:r.height+p*2});})()'
                )
                if rect:
                    shot_args['clip'] = dict(json.loads(rect), scale=args.scale)
            res = probe.cmd('Page.captureScreenshot', shot_args)
            with open(args.shot, 'wb') as fh:
                fh.write(base64.b64decode(res['result']['data']))
            out['screenshot'] = args.shot
    finally:
        probe.close()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print('BASELINE:', 'PASS' if out['baseline'].get('pass') else 'FAIL')
    return 0 if out['baseline'].get('pass') else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--probes', default=str(DEFAULT_PROBES))
    ap.add_argument('--root', default=str(GAME_DIR))
    ap.add_argument(
        '--preset',
        default='no_login',
        choices=['no_login', 'login_doll', 'login_api', 'tut_only'],
    )
    ap.add_argument(
        '--uid',
        default=os.environ.get('KKPARK_DISCORD_ID', '123456789012345678'),
        help='Discord 使用者 ID；預設取環境變數 KKPARK_DISCORD_ID。'
        '真實 ID 請用執行時參數／環境變數注入，不要寫進任何要 commit 的檔案',
    )
    ap.add_argument('--port', type=int, default=0)
    ap.add_argument('--cdp-port', type=int, default=0)
    ap.add_argument('--enter', default='btnStartNew', help='進入遊戲的按鈕 id；空字串則不點')
    ap.add_argument('--fly', default='', help='lat,lng,zoom')
    ap.add_argument('--settle', type=float, default=4.0)
    ap.add_argument('--settle-after-enter', type=float, default=2.5)
    ap.add_argument('--settle-after-fly', type=float, default=5.0)
    ap.add_argument('--shot', default='')
    ap.add_argument('--clip-selector', default='')
    ap.add_argument('--scale', type=float, default=1.0)
    sys.exit(run(ap.parse_args()))
