// Minimal Chrome DevTools Protocol driver for dbtest/browser_*.js (Node 22+: global WebSocket/fetch).
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function launch(dir, port) {
  const prof = path.join(dir, 'prof-cdp');
  fs.rmSync(prof, { recursive: true, force: true });
  const proc = spawn(CHROME, ['--headless=new', '--remote-debugging-port=' + port, '--user-data-dir=' + prof,
    '--no-first-run', '--disable-gpu', '--allow-file-access-from-files', 'about:blank'], { stdio: 'ignore' });
  let targets;
  for (let i = 0; i < 50; i++) {
    try { targets = await (await fetch('http://127.0.0.1:' + port + '/json')).json(); break; } catch (e) { await sleep(200); }
  }
  const page = targets.find((t) => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r));
  let id = 0;
  const pending = new Map();
  const listeners = [];
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { res, rej } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? rej(new Error(msg.error.message)) : res(msg.result);
    } else if (msg.method) listeners.forEach((l) => l(msg));
  });
  const send = (method, params) => new Promise((res, rej) => {
    const i = ++id;
    pending.set(i, { res, rej });
    ws.send(JSON.stringify({ id: i, method, params: params || {} }));
  });
  const on = (fn) => listeners.push(fn);
  const evaluate = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error('eval failed: ' + JSON.stringify(r.exceptionDetails).slice(0, 400));
    return r.result.value;
  };
  return { send, on, evaluate, close: () => { try { ws.close(); } catch (e) {} proc.kill(); } };
}

module.exports = { launch, sleep, CHROME };
