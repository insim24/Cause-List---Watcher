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

async function load({ index, status, indexAfterRun, runConclusion, token, nextDates, texts }) {
  const repo = { 'orders_index.json': index == null ? null : JSON.stringify(index),
    'orders_status.json': status == null ? null : JSON.stringify(status),
    'cases_auto.json': JSON.stringify(MATCHES) };
  const dispatched = [];
  const json = (body, code) => Promise.resolve({ ok: (code || 200) < 300, status: code || 200, json: () => Promise.resolve(body) });
  function fakeFetch(url, opts) {
    url = String(url);
    if (/^orders\//.test(url)) {   // an order's .txt, fetched relative to the page
      const t = (texts || {})[url];
      return Promise.resolve({ ok: t != null, status: t != null ? 200 : 404, text: () => Promise.resolve(t || '') });
    }
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
      if (nextDates) w.localStorage.setItem('next_hearing_dates', JSON.stringify(nextDates));
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

// CRM(M) 333/2022's latest hearing in the fixture is 2026-10-05, court 14, Sr 47.
const ROW_ID = '2026-10-05|14|CRM(M) 333/2022 CrlM(226/2025) CrlM(988/2022) COURT NO. : 14|47';
const LAST_TEXT = 'ORDER 01.11.2026\nHeard. Reply be filed within two weeks.\nList on 10.12.2026.';
function caseIndex(lastOrder) {
  const index = JSON.parse(JSON.stringify(INDEX));
  index.cases['CRM(M) 333/2022'] = { status: 'linked', parties: 'SABZAR vs GHULAM', orders: [
    order(1, '2026-03-01', { next_date: '2026-04-02', next_date_text: 'List on 02.04.2026' }),
    order(2, '2026-11-01', Object.assign({ next_date: '2026-12-10', next_date_text: 'List on 10.12.2026' }, lastOrder || {})),
  ] };
  return index;
}
const caseRow = (doc) => [...doc.querySelectorAll('#tableBody tr')].find((r) => /CRM\(M\) 333\/2022/.test(r.textContent) && !r.classList.contains('case-detail'));
const settle = () => new Promise((r) => setTimeout(r, 60));

test('All cases: name under the number, and an orders panel with the last order text', opt, async () => {
  const texts = { 'orders/WP_C_1_2024/002_2026-11-01.txt': LAST_TEXT };
  const { doc, errors } = await load({ index: caseIndex(), status: STATUS, texts });
  const tr = caseRow(doc);
  assert.match(tr.querySelector('.cn-name').textContent, /SABZAR AHMAD BADDER/);
  const link = tr.querySelector('[data-orders-case]');
  assert.match(link.textContent, /2 orders · latest 1 Nov 2026/);
  link.click();
  await settle();
  const panel = caseRow(doc).nextElementSibling;
  assert.ok(panel.classList.contains('case-detail'));
  assert.match(panel.querySelector('.cd-title').textContent, /SABZAR AHMAD BADDER/);
  assert.match(panel.querySelector('.cd-meta').textContent, /CRM\(M\) 333\/2022.*Next date of hearing: 10 Dec 2026 \(from the last order\)/);
  const orderRows = panel.querySelectorAll('table.cd-orders tbody tr');
  assert.strictEqual(orderRows.length, 2);
  assert.match(orderRows[0].textContent, /1 Nov 2026/);           // newest first
  assert.ok(orderRows[0].querySelector('a.cd-pdf').getAttribute('href').endsWith('.pdf'));
  assert.match(panel.querySelector('.cd-last-head').textContent, /Last order — 1 Nov 2026/);
  assert.strictEqual(panel.querySelector('.cd-last-text').textContent, LAST_TEXT);
  caseRow(doc).querySelector('[data-orders-case]').click();      // closes again
  assert.ok(!caseRow(doc).nextElementSibling || !caseRow(doc).nextElementSibling.classList.contains('case-detail'));
  assert.deepStrictEqual(errors, []);
});

test('a scanned order with no text is flagged, not left blank', opt, async () => {
  const { doc } = await load({ index: caseIndex({ no_text: true, text: undefined, next_date: null }), status: STATUS });
  assert.match(caseRow(doc).textContent, /1 scanned, no text yet/);
  caseRow(doc).querySelector('[data-orders-case]').click();
  const panel = caseRow(doc).nextElementSibling;
  assert.match(panel.textContent, /1 of these orders is a scanned image with no text extracted yet/);
  assert.match(panel.querySelector('table.cd-orders tbody tr').textContent, /scanned image, no text extracted yet/);
  assert.match(panel.textContent, /This order is a scanned image — no text has been extracted from it yet/);
  assert.strictEqual(panel.querySelector('.cd-last-text'), null);
});

test('next date: an empty field is pre-filled from the last order, and nothing is saved', opt, async () => {
  const { w, doc } = await load({ index: caseIndex(), status: STATUS, nextDates: {} });
  const input = caseRow(doc).querySelector('[data-nextid]');
  assert.strictEqual(input.value, '2026-12-10');
  assert.match(caseRow(doc).textContent, /from order of 1 Nov 2026/);
  assert.strictEqual(caseRow(doc).querySelector('.nd-prompt'), null);
  assert.deepStrictEqual(Object.keys(w.nextDatesPending), []);   // not written anywhere
});

test('next date: a different date you set is never changed without asking', opt, async () => {
  const { w, doc } = await load({ index: caseIndex(), status: STATUS, nextDates: { [ROW_ID]: '2026-12-03' } });
  const input = () => caseRow(doc).querySelector('[data-nextid]');
  assert.strictEqual(input().value, '2026-12-03');
  const prompt = caseRow(doc).querySelector('.nd-prompt');
  assert.match(prompt.textContent, /Order of 1 Nov 2026 says next date is 10 Dec 2026, currently stored as 3 Dec 2026\. Update\?/);
  assert.strictEqual(w.nextDates[ROW_ID], '2026-12-03');
  // Keep: your date stays, the question isn't asked again for this order
  caseRow(doc).querySelector('[data-nd-keep]').click();
  assert.strictEqual(w.nextDates[ROW_ID], '2026-12-03');
  assert.strictEqual(w.nextDatesPending['order-kept:' + ROW_ID], '2026-12-10');
  assert.strictEqual(caseRow(doc).querySelector('.nd-prompt'), null);
  assert.strictEqual(input().value, '2026-12-03');
});

test('next date: Update takes the order date as your entry', opt, async () => {
  const { w, doc } = await load({ index: caseIndex(), status: STATUS, nextDates: { [ROW_ID]: '2026-12-03' } });
  caseRow(doc).querySelector('[data-nd-accept]').click();
  assert.strictEqual(w.nextDates[ROW_ID], '2026-12-10');
  assert.strictEqual(w.nextDatesPending[ROW_ID], '2026-12-10');
  assert.strictEqual(caseRow(doc).querySelector('[data-nextid]').value, '2026-12-10');
  assert.strictEqual(caseRow(doc).querySelector('.nd-prompt'), null);
});

test('next date: no prompt when your date matches, or the order date has passed', opt, async () => {
  let r = await load({ index: caseIndex(), status: STATUS, nextDates: { [ROW_ID]: '2026-12-10' } });
  assert.strictEqual(caseRow(r.doc).querySelector('.nd-prompt'), null);
  // last order's next date is before the latest hearing (2026-10-05): stale, ignored
  r = await load({ index: caseIndex({ next_date: '2026-10-01' }), status: STATUS, nextDates: { [ROW_ID]: '2026-12-03' } });
  assert.strictEqual(caseRow(r.doc).querySelector('.nd-prompt'), null);
  assert.strictEqual(caseRow(r.doc).querySelector('[data-nextid]').value, '2026-12-03');
});

test('a failed order run says so and re-enables the button', opt, async () => {
  const { doc } = await load({ index: INDEX, status: STATUS, runConclusion: 'failure', token: true });
  doc.getElementById('ordersBtn').click();
  await new Promise((r) => setTimeout(r, 300));
  assert.match(doc.getElementById('fetchStatus').textContent, /failure/);
  assert.strictEqual(doc.getElementById('ordersBtn').disabled, false);
});
