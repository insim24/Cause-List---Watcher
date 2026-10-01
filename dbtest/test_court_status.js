// Regression tests for the live court status feature, against pages captured
// from https://jkhc.gov.in/dis/ on 2026-10-01 while court 11 was sitting:
//   fixture_active.html        main display board (court 11 at Sr 73; Jammu idle)
//   fixture_court_active.html  court 11's own list, rows coloured by status
// Run: node --test dbtest/test_court_status.js
// The dashboard test needs jsdom and python; it is skipped if jsdom is missing.

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.join(__dirname, '..');
const { parseDisplayBoard } = require(path.join(ROOT, 'api/_display-board-parser.js'));
const { parseTables, parseLegend, findCourtForm, isoFromCourtDate } = require(path.join(ROOT, 'api/_court-list-parser.js'));

const BOARD_HTML = fs.readFileSync(path.join(__dirname, 'fixture_active.html'), 'utf8');
const COURT_HTML = fs.readFileSync(path.join(__dirname, 'fixture_court_active.html'), 'utf8');

function caseRows(tables) {
  return tables.flatMap((t) => t.rows).filter((r) => r.sr);
}

test('main board: court 11 sitting at Sr 73, Jammu idle', () => {
  const board = parseDisplayBoard(BOARD_HTML);
  assert.deepStrictEqual(board['Srinagar Wing'].courts, [
    { court: '11', item: '73', coram: "HON'BLE MR. JUSTICE MOHD YOUSUF WANI" },
  ]);
  assert.strictEqual(board['Srinagar Wing'].idle, false);
  assert.strictEqual(board['Jammu Wing'].idle, true);
  const form = findCourtForm(BOARD_HTML, 'Srinagar Wing', '11');
  assert.ok(form, 'court 11 form found');
  assert.strictEqual(form.method, 'POST');
});

test('court page legend: the three statuses and their colours', () => {
  assert.deepStrictEqual(parseLegend(COURT_HTML), [
    { status: 'disposed', label: 'Disposed', color: '#ebacac' },
    { status: 'to_be_heard', label: 'To Be Heard', color: '#dfefff' },
    { status: 'hearing_complete', label: 'Hearing Complete', color: '#e8e8e8' },
  ]);
});

test('court page rows: every case tagged with its status', () => {
  const tables = parseTables(COURT_HTML);
  assert.strictEqual(tables.length, 1, 'legend table is not returned as a case table');
  const rows = caseRows(tables);
  assert.strictEqual(rows.length, 74);
  const bySr = (sr) => rows.find((r) => r.sr === String(sr));

  const complete = rows.filter((r) => r.status === 'hearing_complete').map((r) => Number(r.sr));
  assert.deepStrictEqual(complete, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 24, 30, 60, 73, 74]);
  assert.strictEqual(rows.filter((r) => r.status === 'to_be_heard').length, 58);
  assert.ok(rows.every((r) => r.status), 'no row left without a status');

  assert.ok(rows.every((r) => r.caseNo), 'case number read from the submit button');
  assert.strictEqual(bySr(1).caseNo, 'OWP-1552/2018');
  assert.strictEqual(bySr(1).section, 'Regular');
  assert.strictEqual(bySr(1).nextDate, '2026-11-02');
  assert.strictEqual(bySr(74).section, 'Supplementary-1');
  assert.strictEqual(bySr(74).caseNo, 'WP(C)-752/2026');
});

test('01/01/5000 is "no date set"', () => {
  assert.strictEqual(isoFromCourtDate('01/01/5000'), '');
  assert.strictEqual(isoFromCourtDate(' 08/10/2026'), '2026-10-08');
  const sr5 = caseRows(parseTables(COURT_HTML)).find((r) => r.sr === '5');
  assert.strictEqual(sr5.nextDateRaw, '01/01/5000');
  assert.strictEqual(sr5.nextDate, '');
});

test('a Disposed (pink) row is recognised', () => {
  // No case was disposed in the capture, so recolour a real row with the
  // legend's Disposed colour (as the site would) and check it's picked up.
  const html = COURT_HTML.replace('<tr style="background:#DFEFFF;;;"><td>11</td>', '<tr style="background:#ebacac;;;"><td>11</td>');
  const sr11 = caseRows(parseTables(html)).find((r) => r.sr === '11');
  assert.strictEqual(sr11.status, 'disposed');
});

test('legend wins over the built-in colours if the site changes them', () => {
  const html = COURT_HTML
    .replace('background:#ebacac;color: white">Disposed.', 'background:#ffc0cb;color: white">Disposed.')
    .replace('<tr style="background:#DFEFFF;;;"><td>11</td>', '<tr style="background:#FFC0CB;;;"><td>11</td>');
  const sr11 = caseRows(parseTables(html)).find((r) => r.sr === '11');
  assert.strictEqual(sr11.status, 'disposed');
});

let JSDOM = null;
try { ({ JSDOM } = require('jsdom')); } catch (e) { /* optional */ }

test('dashboard: statuses, "now at", scoped fetches, next-date pre-fill', { skip: !JSDOM && 'jsdom not installed' }, async () => {
  const courtRows = caseRows(parseTables(COURT_HTML));
  const row = (sr) => courtRows.find((r) => r.sr === String(sr));
  const today = '2026-10-01';
  const match = (sr, extra) => Object.assign({
    id: 't' + sr, person: 'Test', people: ['Test'], court: '11', sr: String(sr),
    caseNo: row(sr).caseNo.replace('-', ' ') + ' CrlM(1/2026)', caseName: row(sr).title,
    date: today, listType: row(sr).section, bench: '', benchType: '', snippet: '',
  }, extra || {});
  const matches = [
    match(1),            // hearing complete, next date 02/11/2026, I entered a different one
    match(3),            // hearing complete, next date 29/10/2026, nothing entered
    match(5),            // hearing complete, next date 01/01/5000 (none)
    match(73),           // the item being heard now
    match(74),           // supplementary list
    match(20),           // to be heard
    { id: 'other', person: 'Test', people: ['Test'], court: '99', sr: '4', caseNo: 'WP(C) 1/2020', caseName: 'X Vs Y', date: today, listType: 'Regular' },
  ];
  const manualId = [today, '11', matches[0].caseNo, '1'].join('|');

  const html = execFileSync('python', ['-c', [
    'import json,sys',
    'sys.path.insert(0, ' + JSON.stringify(ROOT) + ')',
    'from dashboard_template import render_dashboard',
    'sys.stdout.reconfigure(encoding="utf-8")',
    'print(render_dashboard(json.loads(sys.stdin.read()), "Test", board={}))',
  ].join('\n')], { input: JSON.stringify(matches), encoding: 'utf8' });

  const courtListCalls = [];
  const repoFile = { body: JSON.stringify({ [manualId]: '2026-10-20' }) };
  const json = (body, status) => Promise.resolve({ ok: (status || 200) < 300, status: status || 200, json: () => Promise.resolve(body) });
  function fakeFetch(url, opts) {
    url = String(url);
    if (url.includes('/api/display-board')) return json(parseDisplayBoard(BOARD_HTML));
    if (url.includes('/api/court-list')) {
      courtListCalls.push(url);
      return json({ tables: parseTables(COURT_HTML), legend: parseLegend(COURT_HTML), notice: '' });
    }
    if (url.includes('next_dates.json')) return json(JSON.parse(repoFile.body));
    return Promise.reject(new Error('offline: ' + url));
  }

  const errors = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://insim24.github.io/Cause-List---Watcher/causelist_dashboard.html',
    beforeParse(w) {
      const RealDate = w.Date;
      const fixed = new RealDate('2026-10-01T16:30:00').getTime();
      w.Date = class extends RealDate {
        constructor(...a) { if (a.length) super(...a); else super(fixed); }
        static now() { return fixed; }
      };
      w.fetch = fakeFetch;
      w.Notification = { permission: 'default', requestPermission: () => Promise.resolve('default') };
      w.scrollTo = () => {};
      w.HTMLElement.prototype.scrollIntoView = () => {};
      w.addEventListener('error', (e) => errors.push(e.message));
      w.console.error = (...a) => errors.push(a.join(' '));
    },
  });
  const w = dom.window;
  Object.defineProperty(w.document, 'hidden', { value: false });
  w.pollBoard();
  await new Promise((r) => setTimeout(r, 300));
  const doc = w.document;

  assert.deepStrictEqual(errors, []);
  assert.strictEqual(courtListCalls.length, 1, 'only courts with my cases today AND on the board are fetched');
  assert.match(courtListCalls[0], /court=11\b/);

  const board = doc.getElementById('boardRow').textContent;
  assert.match(board, /Now at Sr 73/);
  assert.match(board, /Your Sr 1\s*Hearing Complete/);
  assert.match(board, /Your Sr 20\s*To Be Heard/);

  const widget = [...doc.querySelectorAll('#todayWidgetBody .tw-row')].map((r) => r.textContent);
  const wRow = (sr) => widget.find((t) => t.startsWith(String(sr) + 'Crt'));
  assert.match(wRow(1), /Hearing Complete/);
  assert.match(wRow(73), /Hearing Complete.*court at Sr 73/);
  assert.match(wRow(20), /To Be Heard/);
  assert.doesNotMatch(wRow(4), /Hearing|To Be Heard/, 'court 99 has no status (not sitting)');

  const input = (sr) => [...doc.querySelectorAll('[data-nextid]')].find((i) => i.getAttribute('data-nextid').startsWith(today + '|11|') && i.getAttribute('data-nextid').endsWith('|' + sr));
  // my entry is kept; the site's differing date is shown alongside
  assert.strictEqual(input(1).value, '2026-10-20');
  assert.match(input(1).parentNode.textContent, /Court site: 2 Nov 2026/);
  // nothing entered: pre-filled from the court site
  assert.strictEqual(input(3).value, '2026-10-29');
  assert.match(input(3).parentNode.textContent, /from court site/);
  // 01/01/5000 and "next date = today" stay blank
  assert.strictEqual(input(5).value, '');
  assert.strictEqual(input(73).value, '');
  // site dates are queued for syncing; the manual entry is untouched
  assert.strictEqual(w.nextDatesPending['site:' + manualId], '2026-11-02');
  assert.strictEqual(w.nextDates[manualId], '2026-10-20');

  // court panel: status column, Now marker on Sr 73, 5000 shown blank
  w.openCourtList('Srinagar Wing', '11');
  await new Promise((r) => setTimeout(r, 200));
  const panelRows = [...doc.querySelectorAll('#courtModalBody tr')];
  const pRow = (sr) => panelRows.find((tr) => tr.cells[0] && tr.cells[0].textContent === String(sr));
  assert.match(pRow(73).textContent, /Hearing Complete\s*Now/);
  assert.ok(pRow(73).classList.contains('is-current'));
  assert.ok(pRow(20).classList.contains('st-to_be_heard'));
  assert.strictEqual(pRow(5).cells[3].textContent, '');
  assert.deepStrictEqual(errors, []);
  w.close();
});
