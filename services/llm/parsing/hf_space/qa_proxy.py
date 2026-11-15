"""Loopback-only QA bridge to the authenticated LIVE private Static Space.

The browser receives deployed app bytes, never Hub/session credentials. The test
harness and fictional negative fixtures are local-only and are never deployed.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

import httpx2
from huggingface_hub import get_token, HfApi

HERE = Path(__file__).resolve().parent
SPACE = 'junglemvn/claimly-parsing-demo'
ORIGIN = 'https://huggingface.co'
ALLOW_FIXTURES = {'warranty.pdf', 'scan_pdf.pdf', 'table_bill.pdf', 'multipage_contract.pdf', 'png_scan.png',
                 'exif_rotated.jpg', 'bill.pdf', 'blank_page.pdf', 'corrupt_pdf.pdf', 'encrypted.pdf', 'empty.pdf',
                 'unsupported.txt', 'over_25pages.pdf', 'warranty_misleading_name.pdf', 'injection_recipe.pdf', 'receipt.pdf'}
client = httpx2.Client(timeout=60, follow_redirects=True)
requests_seen = []
revision = ''


def authenticate() -> None:
    """Fetch exact deployed repository bytes; credentials stay on loopback server."""
    global revision
    info = HfApi().space_info(SPACE)
    revision = info.sha
    probe = live_file('/index.html')
    if probe.status_code != 200 or 'made readable' not in probe.text:
        raise RuntimeError('Authenticated live app did not load.')
    print(json.dumps({'verified_repository_revision': revision, 'sdk': info.sdk,
                      'private': info.private, 'stage': info.runtime.stage}), flush=True)


def live_file(path: str):
    if path == '/':
        path = '/index.html'
    # httpx drops Authorization on cross-origin CDN redirects.
    return client.get(f'{ORIGIN}/spaces/{SPACE}/resolve/{revision}{path}',
                      headers={'Authorization': 'Bearer ' + get_token()})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_bytes(self, data: bytes, mime: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        requests_seen.append({'method': 'GET', 'path': path})
        if path == '/__qa/validation.html':
            self.send_bytes((HERE / 'validate_browser.html').read_bytes(), 'text/html; charset=utf-8')
            return
        if path == '/__qa/network':
            self.send_bytes(json.dumps(requests_seen).encode(), 'application/json')
            return
        if path.startswith('/__qa/fixtures/'):
            name = path.rsplit('/', 1)[-1]
            if name in ALLOW_FIXTURES:
                self.send_bytes((HERE.parent / 'fixtures' / name).read_bytes(), 'application/octet-stream')
                return
            self.send_bytes(b'Not found', 'text/plain', 404)
            return
        # Proxy only the deployed static asset allowlist, never arbitrary URLs.
        if path not in ('/', '/favicon.ico', '/README.md', '/THIRD_PARTY.md', '/AGENTS.md', '/index.html', '/style.css', '/app.js', '/release-manifest.json') \
                and not path.startswith(('/vendor/', '/examples/')):
            self.send_bytes(b'Not found', 'text/plain', 404)
            return
        try:
            upstream = live_file(path)
            served_path = '/index.html' if path == '/' else path
            mime = mimetypes.guess_type(served_path)[0] or 'application/octet-stream'
            self.send_bytes(upstream.content, mime, upstream.status_code)
        except Exception as exc:
            # Exception strings may include signed URLs. Emit the type only.
            print(json.dumps({'proxy_error_type': type(exc).__name__}), flush=True)
            self.send_bytes(b'Live Space request failed.', 'text/plain', 502)

    def do_POST(self) -> None:
        if self.path == '/__qa/report' and self.headers.get('Origin') == 'http://127.0.0.1:8873':
            length = int(self.headers.get('Content-Length', '0'))
            if 0 < length < 500000:
                report = json.loads(self.rfile.read(length))
                if isinstance(report.get('cases'), list):
                    target = HERE / 'reports/browser-verification.json'
                    target.parent.mkdir(exist_ok=True)
                    report['deployed_revision'] = revision
                    target.write_text(json.dumps(report, indent=2) + '\n')
                    print(json.dumps({'browser_validation_passed': report.get('passed'), 'failed': report.get('failed')}), flush=True)
                    self.send_bytes(b'{}', 'application/json')
                    return
        requests_seen.append({'method': 'POST', 'path': urlsplit(self.path).path})
        self.send_bytes(b'QA bridge permits no uploads or writes.', 'text/plain', 405)


if __name__ == '__main__':
    authenticate()
    print('Authenticated live Static Space; QA bridge http://127.0.0.1:8873 (credentials remain server-side).', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8873), Handler).serve_forever()
