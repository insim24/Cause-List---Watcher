// "All cases" shows each case once, on its latest hearing date.
// Runs the real dashboard against a snapshot of cases_auto.json taken on
// 2026-10-02 (99 hearings of 69 cases). Needs jsdom + python; skipped without jsdom.
// Run: node --test dbtest/test_all_cases.js

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.join(__dirname, '..');
const MATCHES = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixture_cases_2026-10-02.json'), 'utf8'));

let JSDOM = null;
try { ({ JSDOM } = require('jsdom')); } catch (e) { /* optional */ }

// the dashboard starts polling timers; close every window so node can exit
const windows = [];
test.after(() => windows.forEach((w) => w.close()));

async function loadDashboard(matches, nextDates) {
  const html = execFileSync('python', ['-c', [
    'import json,sys',
    'sys.path.insert(0, ' + JSON.stringify(ROOT) + ')',
    'from dashboard_template import render_dashboard',
    'sys.stdout.reconfigure(encoding="utf-8")',
    'print(render_dashboard(json.loads(sys.stdin.read()), "Test", board={}))',
  ].join('\n')], { input: JSON.stringify(matches), encoding: 'utf8' });
  const errors = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://insim24.github.io/Cause-List---Watcher/causelist_dashboard.html',
    beforeParse(w) {
      w.localStorage.setItem('next_hearing_dates', JSON.stringify(nextDates || {}));
      w.fetch = () => Promise.reject(new Error('offline'));
      w.Notification = { permission: 'default', requestPermission: () => Promise.resolve('default') };
      w.addEventListener('error', (e) => errors.push(e.message));
      w.console.error = (...a) => errors.push(a.join(' '));
    },
  });
  windows.push(dom.window);
  await new Promise((r) => setTimeout(r, 100));
  const doc = dom.window.document;
  const rows = [...doc.querySelectorAll('#tableBody tr')].map((tr) => ({
    date: tr.cells[0].textContent,
    caseNo: tr.cells[4].textContent,
    caseName: tr.cells[5].textContent,
    people: tr.cells[6].textContent,
    nextDate: tr.querySelector('input.next-date') && tr.querySelector('input.next-date').value,
  }));
  return { w: dom.window, doc, rows, errors };
}

test('each case appears once, on its latest date', { skip: !JSDOM && 'jsdom not installed' }, async () => {
  const { w, doc, rows, errors } = await loadDashboard(MATCHES);
  assert.deepStrictEqual(errors, []);
  assert.strictEqual(MATCHES.length, 99);
  assert.strictEqual(rows.length, 69);
  assert.strictEqual(doc.getElementById('allCount').textContent, '69');

  // no case key shown twice
  const keys = rows.map((r) => w.caseKey(r.caseNo));
  assert.strictEqual(new Set(keys).size, rows.length);

  // Khalida: three hearings -> one row on 1 Oct, earlier dates listed
  const khalida = rows.filter((r) => r.caseName.startsWith('KHALIDA'));
  assert.strictEqual(khalida.length, 1);
  assert.match(khalida[0].date, /^2026-10-01earlier: 14 Sept?, 19 Aug$/);

  // every row shown is the latest hearing of its case
  rows.forEach((r) => {
    const hearings = MATCHES.filter((m) => w.caseKey(m.caseNo) === w.caseKey(r.caseNo));
    const latest = hearings.map((m) => m.date).sort().pop();
    assert.ok(r.date.startsWith(latest), r.caseNo + ' shows ' + r.date + ', latest is ' + latest);
  });
});

test('different cases are never merged', { skip: !JSDOM && 'jsdom not installed' }, async () => {
  const { w, rows } = await loadDashboard(MATCHES);
  // the application number isn't the case's identity
  assert.strictEqual(w.caseKey('CM(5339/2026) IN WP(C) 1319/2025 CM(304/2026)'), 'WPC1319/2025');
  assert.strictEqual(w.caseKey('CM(M) 161/2026 CM(2889/2026) Caveat 312/2026'), 'CMM161/2026');
  // a lower-court case in [..] isn't either
  assert.strictEqual(w.caseKey('LPA 74/2020 in[SWP 381/2011] CM(4775/2025)'), 'LPA74/2020');
  // every merged group is one case number, or numbers tied by a shared caveat
  // (FAO 26/2026 converted to RFA 92/2026, both under Caveat 1131/2026)
  const groups = {};
  MATCHES.forEach((m) => {
    const shown = w.groupByCase([m].concat(MATCHES.filter((x) => x !== m)))[0];
    const k = shown.caseNo + '@' + shown.date;
    (groups[k] = groups[k] || new Set()).add(m);
  });
  Object.values(groups).forEach((g) => {
    const hearings = [...g];
    const nums = new Set(hearings.map((m) => w.caseKey(m.caseNo)));
    if (nums.size === 1) return;
    const caveatSets = hearings.map((m) => new Set(w.caveatKeys(m.caseNo)));
    const shared = [...caveatSets[0]].filter((c) => caveatSets.every((s) => s.has(c)));
    assert.ok(shared.length, 'group without a shared caveat: ' + [...nums].join(', '));
  });
  const multiNumber = Object.values(groups).filter((g) => new Set([...g].map((m) => w.caseKey(m.caseNo))).size > 1);
  assert.strictEqual(multiNumber.length, 1, 'only the FAO -> RFA conversion spans two case numbers');
});

test('converted case (FAO -> RFA) shows once under its new number', { skip: !JSDOM && 'jsdom not installed' }, async () => {
  const { w, rows } = await loadDashboard(MATCHES);
  assert.strictEqual(w.caseKey('FAO 26/2026 CM(5096/2026) Caveat 1131/2026'), 'FAO26/2026');
  assert.deepStrictEqual([...w.caveatKeys('RFA 92/2026 CM(5096/2026) Caveat 1131/2026')], ['CAVEAT1131/2026']);
  const zam = rows.filter((r) => r.caseName.startsWith('ZAMROODA'));
  assert.strictEqual(zam.length, 1);
  assert.match(zam[0].caseNo, /^RFA 92\/2026/);
  assert.match(zam[0].date, /^2026-10-01earlier: 18 Sept?, 11 Aug$/);
});

test('merged row: people unioned, clean name, next date carried forward', { skip: !JSDOM && 'jsdom not installed' }, async () => {
  const ganie = MATCHES.filter((m) => m.caseNo.startsWith('CM(M) 161/2026'));
  assert.strictEqual(ganie.length, 4);
  const sept1 = ganie.find((m) => m.date === '2026-09-01');
  const id = (m) => [m.date, m.court, m.caseNo, m.sr].join('|');
  const { rows } = await loadDashboard(MATCHES, {
    [id(sept1)]: '2026-10-20',   // set on an earlier hearing, still after the latest (29 Sep)
  });
  const row = rows.find((r) => r.caseNo.startsWith('CM(M) 161/2026'));
  assert.match(row.people, /Syed Mohtasim/);
  assert.match(row.people, /Owais Ashraf/);
  assert.strictEqual(row.nextDate, '2026-10-20');

  // page-header text that leaked into one hearing's name isn't shown
  const afshin = rows.find((r) => r.caseName.startsWith('AFSHIN KHAN'));
  assert.doesNotMatch(afshin.caseName, /CAUSELIST/);
});
