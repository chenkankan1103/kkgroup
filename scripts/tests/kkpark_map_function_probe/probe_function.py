"""kkpark-map 功能驗證探針（A-E 段：數據面、零截圖）

以 headless Edge + CDP 管線跑一輪功能檢查。每條探針＝前置條件 → 動作 → 取樣 → PASS/FAIL 判定。

管線手法沿用已驗證的 RUNBOOK（唯一 profile、自動挑 port、CDP 取代 --headless --screenshot、
Windows cp950 強制 UTF-8、finally 收掉 Edge、favicon 404 用 Network domain 排除）。
本檔相對視覺管線多三件事：
1. 多 preset 輪跑（no_login / login_doll / dummy_id），同一支探針可指定 preset
2. 內建 PASS/FAIL 判定（judge 規格），輸出逐條結果與總表
3. 鍵盤走真實 KeyboardEvent（document 層），走 map.js 的 KEYMAP → Sim.setKey 路徑

用法：
  python probe_function.py --probes probes_function.json --root <web/kkpark-map> --out report.json
"""

import argparse
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

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
TMPDIR = os.path.join(tempfile.gettempdir(), 'kkpark_func_probe')
FAVICON_404 = 'favicon.ico'

# 假的但符合前端 /^\d{5,25}$/ 規則（測試用，不是真人）
DOLL_ID = '123456789012345678'
# 刻意選跟 NPC 造型池不同的 itemId，才能分辨「主角/第一位成員穿玩家造型」與「NPC 穿造型池」
DOLL_LOOK = {
    'face': 20699,
    'hair': 44687,
    'skin': 12000,
    'top': 1042163,
    'bottom': 1062066,
    'shoes': 1073427,
}


def build_preset_inject(preset):
    """在頁面腳本執行前寫入 localStorage（avatar.js 啟動時就會讀快取）"""
    lines = [
        'try {',
        "  localStorage.setItem('kkpark_map_tut_v1', '1');",
        "  localStorage.removeItem('kkpark_map_save_v1');",
        "  localStorage.removeItem('kkpark_map_avatar_cache_v1');",
    ]
    if preset == 'login_doll':
        look = json.dumps(DOLL_LOOK)
        lines += [
            "  localStorage.setItem('kkpark_discord_id', '" + DOLL_ID + "');",
            "  localStorage.setItem('kkpark_map_avatar_cache_v1', JSON.stringify({",
            "    '" + DOLL_ID + "': { t: Date.now(), d: " + look + ' }',
            '  }));',
        ]
    elif preset == 'dummy_id':
        # 有登入態但沒有快取 → fetchPaperdoll 會走正式 API → 未知 ID 回 404 → 無造型
        lines.append("  localStorage.setItem('kkpark_discord_id', '" + DOLL_ID + "');")
    else:  # no_login
        lines.append("  localStorage.removeItem('kkpark_discord_id');")
    lines.append('} catch (e) {}')
    return '\n'.join(lines)


# 注入頁面的輔助函式（在頁面載入後、ROAD_NET 已存在時才呼叫，所以延遲取用）
HELPERS_JS = r"""
(function () {
  window.__kkh = {
    press: function (code) {
      document.dispatchEvent(new KeyboardEvent('keydown', { code: code, bubbles: true }));
    },
    release: function (code) {
      document.dispatchEvent(new KeyboardEvent('keyup', { code: code, bubbles: true }));
    },
    roadDist: function (lat, lng) {
      var best = null, bd = Infinity;
      for (var ci = 0; ci < ROAD_NET.length; ci++) {
        var ch = ROAD_NET[ci];
        for (var i = 0; i < ch.length; i++) {
          var p = ch[i], dx = p[0] - lat, dy = p[1] - lng, d = dx * dx + dy * dy;
          if (d < bd) { bd = d; best = p; }
        }
      }
      return best ? { lat: best[0], lng: best[1], dist: Math.sqrt(bd) } : null;
    },
    // 最近路網點＋當地路段切向（用來挑「垂直於路」的方向＝最容易走離路網的情況）
    roadFrame: function (lat, lng) {
      var best = null, bd = Infinity, bi = 0, ci = 0;
      for (var c = 0; c < ROAD_NET.length; c++) {
        var ch = ROAD_NET[c];
        for (var i = 0; i < ch.length; i++) {
          var p = ch[i], dx = p[0] - lat, dy = p[1] - lng, d = dx * dx + dy * dy;
          if (d < bd) { bd = d; best = p; bi = i; ci = c; }
        }
      }
      var chain = ROAD_NET[ci], n = chain.length;
      var prev = chain[Math.max(0, bi - 1)], next = chain[Math.min(n - 1, bi + 1)];
      var tx = next[0] - prev[0], ty = next[1] - prev[1];
      var len = Math.sqrt(tx * tx + ty * ty) || 1;
      tx /= len; ty /= len;
      var plat = -ty, plng = tx;                      // 垂直向量（lat, lng）
      var perpKey = Math.abs(plat) > Math.abs(plng)
        ? (plat > 0 ? 'ArrowUp' : 'ArrowDown')
        : (plng > 0 ? 'ArrowRight' : 'ArrowLeft');
      return { point: { lat: best[0], lng: best[1] }, dist: Math.sqrt(bd),
               tan: { lat: tx, lng: ty }, perp: { lat: plat, lng: plng }, perpKey: perpKey };
    },
    heroPos: function () {
      var p = Sim.state().hero.pos;
      return { lat: p.lat, lng: p.lng };
    },
    setHero: function (lat, lng) {
      var p = Sim.state().hero.pos;
      p.lat = lat; p.lng = lng;
    },
    // 找離路網最遠的點（用來驗「離路太遠＝自由行走」）
    farFromRoad: function (clat, clng, span, step) {
      var best = null, bestD = -1;
      for (var lat = clat - span; lat <= clat + span; lat += step) {
        for (var lng = clng - span; lng <= clng + span; lng += step) {
          var r = this.roadDist(lat, lng);
          if (r && r.dist > bestD) { bestD = r.dist; best = { lat: lat, lng: lng, dist: r.dist }; }
        }
      }
      return best;
    },
    // 找離主角最近的「畫面上」的巡查車（盤查互動要用）
    nearestCop: function () {
      var h = Sim.state().hero.pos, best = null, bd = Infinity;
      var cps = GameMap.copPositions();
      for (var i = 0; i < cps.length; i++) {
        var c = cps[i], dx = c.lat - h.lat, dy = c.lng - h.lng, d = dx * dx + dy * dy;
        if (d < bd) { bd = d; best = { lat: c.lat, lng: c.lng }; }
      }
      return best ? { lat: best.lat, lng: best.lng, dist: Math.sqrt(bd), count: cps.length } : null;
    }
  };
  return 'helpers-ready';
})()
"""


class Probe:
    """headless Edge + CDP：附加 about:blank、注入前置、導頁、執行探針"""

    def __init__(self, root, port, cdp_port):
        self.root, self.port, self.cdp_port = root, port, cdp_port
        self.profile = os.path.join(TMPDIR, 'profile_' + str(int(time.time() * 1000)))
        self.proc = None
        self.httpd = None
        self.ws = None
        self.mid = 0
        self.console_errors = []
        self.http_404 = []
        self._start()

    def _start(self):
        os.makedirs(TMPDIR, exist_ok=True)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=self.root)
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
                '--user-data-dir=' + self.profile,
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
            except Exception:  # noqa: BLE001, S110 — 重試迴圈，連線失敗靜默再試
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
            m = msg.get('method')
            if m == 'Log.entryAdded':
                e = msg['params']['entry']
                if e.get('level') == 'error':
                    self.console_errors.append((e.get('source'), (e.get('text') or '')[:120]))
            elif m == 'Network.responseReceived':
                r = msg['params']['response']
                if r.get('status') == 404:
                    self.http_404.append(r.get('url', '')[:160])
            if msg.get('id') == i:
                return msg

    def ev(self, expr):
        """評估 JS；回傳物件時前端用 JSON.stringify 包起來，這裡還原成 dict"""
        r = self.cmd('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
        res = r.get('result', {}).get('result', {})
        if res.get('subtype') == 'error':
            return {'__error': res.get('description', '')[:200]}
        v = res.get('value')
        if isinstance(v, str):
            t = v.strip()
            if t.startswith(('{', '[')):
                try:
                    return json.loads(t)
                except Exception:  # noqa: BLE001 — 非 JSON 就回原字串
                    return v
        return v

    def wait_for(self, expr, timeout):
        """輪詢到 expr 為真值為止；回傳是否成立"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.ev(expr):
                return True
            time.sleep(0.4)
        return False

    def drag(self, x1, y1, x2, y2):
        """CDP 真實滑鼠拖曳（觸發 Leaflet dragstart → 主角跟隨暫停）"""
        self.cmd(
            'Input.dispatchMouseEvent',
            {'type': 'mousePressed', 'x': x1, 'y': y1, 'button': 'left', 'clickCount': 1},
        )
        steps = 6
        for i in range(1, steps + 1):
            self.cmd(
                'Input.dispatchMouseEvent',
                {
                    'type': 'mouseMoved',
                    'x': x1 + (x2 - x1) * i / steps,
                    'y': y1 + (y2 - y1) * i / steps,
                    'button': 'left',
                },
            )
        self.cmd(
            'Input.dispatchMouseEvent',
            {'type': 'mouseReleased', 'x': x2, 'y': y2, 'button': 'left', 'clickCount': 1},
        )

    def close(self):
        try:
            if self.ws:
                self.ws.close()
        except Exception:  # noqa: BLE001, S110 — 收尾清理，失敗無礙
            pass
        if self.proc:
            self.proc.kill()
        if self.httpd:
            self.httpd.shutdown()
        shutil.rmtree(self.profile, ignore_errors=True)


def pick(value, path):
    """從取樣值依 path 取欄位（支援 a.b 與 a[0]）"""
    if not path:
        return value
    cur = value
    for part in path.replace(']', '').replace('[', '.').split('.'):
        if part == '':
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except Exception:  # noqa: BLE001 — 非數字索引視為找不到
                return None
        else:
            return None
    return cur


def judge_one(value, spec):
    """單條判定規格 → (passed, human_readable_expectation)"""
    op = spec.get('op', 'truthy')
    v = spec.get('value')
    if op == 'truthy':
        return bool(value), 'truthy'
    if op == 'falsy':
        return not value, 'falsy'
    if op == 'eq':
        return value == v, f'== {v!r}'
    if op == 'ne':
        return value != v, f'!= {v!r}'
    if op == 'gt':
        return value is not None and value > v, f'> {v!r}'
    if op == 'ge':
        return value is not None and value >= v, f'>= {v!r}'
    if op == 'lt':
        return value is not None and value < v, f'< {v!r}'
    if op == 'le':
        return value is not None and value <= v, f'<= {v!r}'
    if op == 'between':
        lo, hi = spec.get('min'), spec.get('max')
        ok = value is not None and lo <= value <= hi
        return ok, f'in [{lo!r}, {hi!r}]'
    if op == 'contains':
        return value is not None and v in value, f'contains {v!r}'
    if op == 'not_contains':
        return value is not None and v not in value, f'not contains {v!r}'
    return False, f'unknown op {op!r}'


def judge(value, spec):
    """判定規格（單一或串列，全部要過）"""
    specs = spec if isinstance(spec, list) else [spec]
    failures = []
    expectations = []
    for one in specs:
        got = pick(value, one.get('path'))
        ok, expect = judge_one(got, one)
        expectations.append('{} {}'.format(one.get('path') or 'value', expect))
        if not ok:
            failures.append(
                '{}：實際 {!r}，預期 {}'.format(one.get('path') or 'value', got, expect)
            )
    return (not failures), expectations, failures


def run_preset(args, preset, checks):
    """跑一輪 preset，回傳該輪的探針結果與基準線"""
    port = args.port or (8610 + (os.getpid() % 120))
    cdp_port = args.cdp_port or (9100 + (os.getpid() % 120))
    probe = Probe(args.root, port, cdp_port)
    results = []
    try:
        probe.cmd('Page.enable')
        probe.cmd('Log.enable')
        probe.cmd('Network.enable')
        probe.cmd(
            'Page.addScriptToEvaluateOnNewDocument',
            {'source': build_preset_inject(preset)},
        )
        probe.cmd('Page.navigate', {'url': f'http://127.0.0.1:{port}/index.html'})
        time.sleep(args.settle)
        probe.ev(HELPERS_JS)
        if args.enter:
            probe.ev(
                f"(function(){{var b=document.getElementById('{args.enter}'); if(!b) return 'no-button';"
                "b.click(); return 'clicked';})()"
            )
            time.sleep(args.settle_after_enter)
        if args.fly:
            lat, lng, z = args.fly.split(',')
            probe.ev(f'GameMap.flyTo({lat}, {lng}, {z});')
            time.sleep(args.settle_after_fly)

        for chk in checks:
            name = chk.get('name', 'check')
            segment = chk.get('segment', '-')
            desc = chk.get('desc', '')
            # 順序：動作(action/cdp) → 等待(until) → 取樣(expr)
            if chk.get('action'):
                probe.ev(chk['action'])
            if chk.get('cdp') == 'drag':
                probe.drag(600, 380, 720, 440)
            if chk.get('until'):
                ok_until = probe.wait_for(chk['until'], float(chk.get('timeout', 30)))
            else:
                ok_until = True
            value = probe.ev(chk['expr'])
            specs = chk.get('judge')
            if specs:
                passed, expectations, failures = judge(value, specs)
                if not ok_until and passed:
                    # until 沒成立但判定有過：標成 FAIL，判定條件沒被觸發
                    passed = False
                    failures.append('until 條件未成立：{}'.format(chk['until']))
            else:
                passed = bool(ok_until) and not (isinstance(value, dict) and '__error' in value)
                expectations = ['no-error']
                failures = [] if passed else [f'until 未成立或取樣錯誤：{value!r}']
            results.append(
                {
                    'segment': segment,
                    'name': name,
                    'desc': desc,
                    'preset': preset,
                    'passed': bool(passed),
                    'value': value,
                    'expect': expectations,
                    'fail': failures,
                }
            )
            tag = 'PASS' if passed else 'FAIL'
            print(f'  [{tag}] {name:<42} {desc}', flush=True)
            if not passed:
                print('        → {}'.format('；'.join(failures)), flush=True)

        broken = probe.ev(
            'Array.from(document.images).filter(function(i){return i.complete && i.naturalWidth===0;})'
            '.map(function(i){return i.src.slice(0,80);})'
        )
        real_errors = [e for e in probe.console_errors if not (e[0] == 'network' and '404' in e[1])]
        real_404 = [u for u in probe.http_404 if FAVICON_404 not in u]
        expected_404 = [u for u in real_404 if '/api/game/user/' in u and '/paperdoll' in u]
        unexpected_404 = [u for u in real_404 if u not in expected_404]
        baseline = {
            'broken_images': broken if isinstance(broken, list) else [],
            'console_errors': real_errors,
            'expected_paperdoll_404': expected_404,
            'unexpected_404': unexpected_404,
        }
        baseline['pass'] = not baseline['broken_images'] and not real_errors and not unexpected_404
        return {'preset': preset, 'checks': results, 'baseline': baseline}
    finally:
        probe.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '--probes', default=os.path.join(os.path.dirname(__file__), 'probes_function.json')
    )
    ap.add_argument('--root', required=True, help='web/kkpark-map 路徑')
    ap.add_argument('--preset', default='', help='只跑指定 preset（空白＝依探針設定分組）')
    ap.add_argument('--port', type=int, default=0)
    ap.add_argument('--cdp-port', type=int, default=0)
    ap.add_argument('--enter', default='btnStartNew', help='進入遊戲的按鈕 id；空字串則不點')
    ap.add_argument('--fly', default='22.62,120.30,16')
    ap.add_argument('--settle', type=float, default=4.0)
    ap.add_argument('--settle-after-enter', type=float, default=2.5)
    ap.add_argument('--settle-after-fly', type=float, default=4.0)
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    with open(args.probes, encoding='utf-8') as fh:
        spec = json.loads(fh.read())
    checks = spec.get('checks', [])
    if args.preset:
        checks = [c for c in checks if c.get('preset') == args.preset]
        presets = [args.preset]
    else:
        presets = []
        for c in checks:
            p = c.get('preset', 'no_login')
            if p not in presets:
                presets.append(p)

    report = {'root': args.root, 'runs': []}
    for preset in presets:
        subset = [c for c in checks if c.get('preset', 'no_login') == preset]
        if not subset:
            continue
        print(f'== preset: {preset} ({len(subset)} 條) ==', flush=True)
        report['runs'].append(run_preset(args, preset, subset))

    all_checks = [c for run in report['runs'] for c in run['checks']]
    passed = sum(1 for c in all_checks if c['passed'])
    report['summary'] = {
        'total': len(all_checks),
        'passed': passed,
        'failed': len(all_checks) - passed,
        'baseline_pass': all(run['baseline']['pass'] for run in report['runs']),
    }
    print('\n=== 總表 ===')
    base = 'PASS' if report['summary']['baseline_pass'] else 'FAIL'
    print(f'PASS {passed} / {len(all_checks)}（FAIL {len(all_checks) - passed}）｜BASELINE {base}')
    for run in report['runs']:
        for c in run['checks']:
            if not c['passed']:
                print('  FAIL [{}] {} — {}'.format(c['segment'], c['name'], '；'.join(c['fail'])))
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print('report →', args.out)
    return 0 if report['summary']['failed'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
