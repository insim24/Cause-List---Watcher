// The Court orders card (orders_index.json / orders_status.json from
// orders_watcher.py) and the "Fetch new orders" button.
// Run: node --test dbtest/test_orders.js   (needs jsdom + python)

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.join(__dirname, '..');
const MATCHES = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixture_cases_2026-10-13.json'), 'utf8'));
let JSDOM = null;
try { ({ JSDOM } = require('jsdom')); } catch (e) { /* optional */ }

const HTML = JSDOM && execFileSync('python', ['-c', [
  'import json,sys', 'sys.path.insert(0, ' + JSON.stringify(ROOT) + ')',
  'from dashboard_template import render_dashboard', 'sys.stdout.reconfigure(encoding="utf-8")',
  'print(render_dashboard(json.loads(sys.stdin.read()), "Test", board={}))',
].join('\n')], { input: JSON.stringify(MATCHES), encoding: 'utf8' });

const windows = [];
test.after(() => windows.forEach((w) => w.close()));

const order = (no, date, extra) => Object.assign({
  no, date, judge: "HON'BLE MR. JUSTICE A", token: 't' + no, sha256: 'h' + no,
  pdf: 'orders/WP_C_1_2024/00' + no + '_' + date + '.pdf', text: 'orders/WP_C_1_2024/00' + no + '_' + date + '.txt',
  excerpt: 'order number ' + no,
}, extra || {});

const INDEX = { cases: {
  'WP(C) 1/2024': { status: 'linked', parties: 'ALPHA vs STATE', orders: [
    order(1, '2024-07-03', { excerpt: 'Issue notice to the respondents' }),
    order(2, '2024-10-23'),
    order(3, '2024-11-06', { duplicate_of: 2 }),
  ] },
  'CRM(M) 9/2025': { status: 'linked', parties: 'BETA vs UT', orders: [order(1, '2025-02-12')] },
} };
const STATUS = { last_run: '2026-11-24T05:00:00+00:00', ok: true, cases_total: 3, cases_linked: 2,
  new_orders: [{ case: 'WP(C) 1/2024', no: 2, date: '2024-10-23' }],
  unlinked: [{ case: 'FAO 26/2026', status: 'not_found', why: 'no matching record on the portal' }] };

async function load({ index, status, indexAfterRun, runConclusion, token }) {
  const repo = { 'orders_index.json': index == null ? null : JSON.stringify(index),
    'orders_status.json': status == null ? null : JSON.stringify(status),
    'cases_auto.json': JSON.stringify(MATCHES) };
  const dispatched = [];
  const json = (body, code) => Promise.resolve({ ok: (code || 200) < 300, status: code || 200, json: () => Promise.resolve(body) });
  function fakeFetch(url, opts) {
    url = String(url);
    const wf = /\/workflows\/([^/]+)\/dispatches$/.exec(url);
    if (wf) {
      dispatched.push(wf[1]);
      if (indexAfterRun) repo['orders_index.json'] = JSON.stringify(indexAfterRun);
      return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) });
    }
    if (/\/runs\?/.test(url)) return json({ workflow_runs: [{ id: 9, status: 'completed', conclusion: runConclusion || 'success', html_url: 'https://github.com/run/9', created_at: new Date().toISOString() }] });
    const file = /\/main\/([^?]+)/.exec(url);
    if (file && file[1] in repo) {
      const body = repo[file[1]];
      return body == null ? json({}, 404) : json(JSON.parse(body));
    }
    return Promise.reject(new Error('offline'));
  }
  const errors = [];
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously',
    url: 'https://insim24.github.io/Cause-List---Watcher/causelist_dashboard.html',
    beforeParse(w) {
      Object.defineProperty(w.document, 'hidden', { value: false });
      if (token) w.localStorage.setItem('gh_pat', 't');
      w.fetch = fakeFetch;
      w.Notification = { permission: 'default', requestPermission: () => Promise.resolve('default') };
      w.Element.prototype.scrollIntoView = function () {};
      w.addEventListener('error', (e) => errors.push(e.message));
      w.console.error = (...a) => errors.push(a.join(' '));
    },
  });
  windows.push(dom.window);
  await new Promise((r) => setTimeout(r, 150));
  const doc = dom.window.document;
  const rows = () => [...doc.querySelectorAll('#ordersBody tr')].map((tr) => tr.textContent);
  return { w: dom.window, doc, errors, dispatched, rows };
}

const opt = { skip: !JSDOM && 'jsdom not installed' };

test('lists orders newest first, skips duplicates, marks new ones', opt, async () => {
  const { doc, rows, errors } = await load({ index: INDEX, status: STATUS });
  assert.deepStrictEqual(errors, []);
  assert.strictEqual(doc.getElementById('ordersCount').textContent, '3');
  const r = rows();
  assert.strictEqual(r.length, 3);
  assert.match(r[0], /CRM\(M\) 9\/2025/);              // 2025-02-12
  assert.match(r[1], /WP\(C\) 1\/2024.*NEW|NEW.*WP\(C\) 1\/2024/);  // order 2, in the last check
  assert.doesNotMatch(r[2], /NEW/);
  const link = doc.querySelector('#ordersBody a[href$=".pdf"]');
  assert.ok(link.getAttribute('href').startsWith('orders/'));
  const note = doc.getElementById('ordersNote').textContent;
  assert.match(note, /2 of 3 cases/);
  assert.match(note, /1 new order/);
  assert.match(note, /FAO 26\/2026/);
});

test('search matches order text and highlights it', opt, async () => {
  const { w, doc, rows } = await load({ index: INDEX, status: STATUS });
  const box = doc.getElementById('ordersSearch');
  box.value = 'notice respondents';
  box.dispatchEvent(new w.Event('input'));
  assert.strictEqual(rows().length, 1);
  assert.strictEqual(doc.querySelectorAll('#ordersBody mark').length, 2);
});

test('no files yet: explains what to do, no errors', opt, async () => {
  const { doc, rows, errors } = await load({});
  assert.deepStrictEqual(errors, []);
  assert.match(rows()[0], /No orders downloaded yet/);
  assert.match(doc.getElementById('ordersNote').textContent, /Fetch new orders/);
});

test('Fetch new orders dispatches orders.yml and shows the new orders', opt, async () => {
  const after = JSON.parse(JSON.stringify(INDEX));
  after.cases['CRM(M) 9/2025'].orders.push(order(2, '2026-11-20'));
  const { doc, dispatched, rows } = await load({ index: INDEX, status: STATUS, indexAfterRun: after, token: true });
  doc.getElementById('ordersBtn').click();
  await new Promise((r) => setTimeout(r, 300));
  assert.deepStrictEqual(dispatched, ['orders.yml']);
  assert.match(rows()[0], /20 Nov 2026/);
  assert.match(doc.getElementById('fetchStatus').textContent, /new order/);
  assert.strictEqual(doc.getElementById('ordersBtn').disabled, false);
});

test('a failed order run says so and re-enables the button', opt, async () => {
  const { doc } = await load({ index: INDEX, status: STATUS, runConclusion: 'failure', token: true });
  doc.getElementById('ordersBtn').click();
  await new Promise((r) => setTimeout(r, 300));
  assert.match(doc.getElementById('fetchStatus').textContent, /failure/);
  assert.strictEqual(doc.getElementById('ordersBtn').disabled, false);
});
