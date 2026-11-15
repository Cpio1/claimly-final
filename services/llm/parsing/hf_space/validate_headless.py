"""Validate the deployed static release in a separate, temporary Chrome profile."""
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

from websockets.sync.client import connect

HERE = Path(__file__).resolve().parent
REPORTS = HERE / 'reports'
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


class Browser:
    def __init__(self, socket):
        self.socket = socket
        self.counter = 0
        self.errors = []

    def command(self, method, params=None):
        self.counter += 1
        identifier = self.counter
        self.socket.send(json.dumps({'id': identifier, 'method': method, 'params': params or {}}))
        while True:
            message = json.loads(self.socket.recv(timeout=30))
            if message.get('method') == 'Runtime.exceptionThrown':
                details = message['params']['exceptionDetails']
                detail = details.get('exception', {}).get('description', details.get('text', 'JavaScript exception'))
                self.errors.append(detail)
                print(json.dumps({'javascript_error': detail[:1000]}), flush=True)
            if message.get('method') == 'Runtime.consoleAPICalled' and message['params']['type'] in ('error', 'warning'):
                print(json.dumps({'browser_console': [a.get('value', a.get('description', '')) for a in message['params'].get('args', [])][:3]}), flush=True)
            if message.get('id') == identifier:
                if 'error' in message:
                    raise RuntimeError(message['error']['message'])
                return message.get('result', {})

    def evaluate(self, expression):
        value = self.command('Runtime.evaluate', {'expression': expression, 'awaitPromise': True, 'returnByValue': True})
        if 'exceptionDetails' in value:
            raise RuntimeError(value['exceptionDetails'].get('text', 'Evaluation failed'))
        return value.get('result', {}).get('value')

    def until(self, expression, seconds=60):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            result = self.evaluate(expression)
            if result:
                return result
            time.sleep(.3)
        raise RuntimeError('Browser did not reach the expected state.')

    def screenshot(self, name):
        data = self.command('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})['data']
        (REPORTS / name).write_bytes(base64.b64decode(data))


def main():
    REPORTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='claimly-chrome-qa-') as profile:
        process = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
            '--no-default-browser-check', '--remote-debugging-port=0', '--user-data-dir=' + profile,
            '--window-size=1440,1100', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            active = Path(profile) / 'DevToolsActivePort'
            for _ in range(100):
                if active.exists():
                    break
                time.sleep(.1)
            port = active.read_text().splitlines()[0]
            tabs = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json'))
            target = next(tab for tab in tabs if tab['type'] == 'page')
            with connect(target['webSocketDebuggerUrl'], max_size=20 * 1024 * 1024) as socket:
                browser = Browser(socket)
                browser.command('Page.enable')
                browser.command('Runtime.enable')
                browser.command('Page.navigate', {'url': 'http://127.0.0.1:8873/__qa/validation.html'})
                browser.until("document.querySelector('#run') && !document.querySelector('#run').disabled")
                browser.evaluate("document.querySelector('#run').click(); true")
                last = None
                deadline = time.monotonic() + 480
                while time.monotonic() < deadline:
                    state = browser.evaluate("(document.querySelector('#status')?.textContent || '') + ' | ' + (document.querySelector('#demo')?.contentDocument?.querySelector('#status-text')?.textContent || '')")
                    if state != last:
                        print(state, flush=True)
                        last = state
                    if state.startswith('Validation complete:'):
                        break
                    time.sleep(1)
                else:
                    browser.screenshot('validation-timeout.png')
                    print(json.dumps({'browser_errors': browser.errors, 'body_excerpt': browser.evaluate("document.body.innerText.slice(0,5000)")}), flush=True)
                    raise RuntimeError('Live browser validation timed out.')
                browser.screenshot('validation-results.png')
                # Inspect the app itself at desktop and mobile widths.
                browser.command('Page.navigate', {'url': 'http://127.0.0.1:8873/'})
                browser.until("document.documentElement.dataset.parserReady === 'true'")
                browser.screenshot('desktop-empty.png')
                browser.evaluate("document.querySelector('[data-example=\"warranty.pdf\"]').click(); true")
                browser.until("document.querySelector('#status')?.dataset.state === 'complete'", seconds=90)
                browser.screenshot('desktop-parsed.png')
                desktop = browser.evaluate("({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,text:document.querySelector('#canonical-text').textContent})")
                browser.command('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True})
                time.sleep(.5)
                browser.screenshot('mobile.png')
                mobile = browser.evaluate("({width:innerWidth,scrollWidth:document.documentElement.scrollWidth})")
                evidence = {'desktop': desktop, 'mobile': mobile, 'browser_errors': browser.errors,
                            'screenshot_files': ['desktop-empty.png', 'desktop-parsed.png', 'mobile.png', 'validation-results.png']}
                (REPORTS / 'browser-ui.json').write_text(json.dumps(evidence, indent=2) + '\n')
                print(json.dumps({'desktop_overflow': desktop['scrollWidth'] > desktop['width'],
                                  'mobile_overflow': mobile['scrollWidth'] > mobile['width'],
                                  'uncaught_browser_errors': len(browser.errors)}, indent=2), flush=True)
        finally:
            process.terminate()
            process.wait(timeout=15)


if __name__ == '__main__':
    main()
