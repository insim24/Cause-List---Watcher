// Search the cause lists by case title / party name.
// Fixtures, captured 2026-10-13:
//   fixture_entries_2026-10-14_court11.json  every case row the watcher's
//       extract_entries_from_pdf() read for court 11 from the live
//       causelist_14102026.pdf (tracked or not)
//   fixture_cases_2026-10-13.json            cases_auto.json as of that day
// Run: node --test dbtest/test_title_search.js
// Needs python (+ jsdom for the dashboard test; skipped without it).

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.join(__dirname, '..');
const ENTRIES = path.join(__dirname, 'fixture_entries_2026-10-14_court11.json');
const MATCHES = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixture_cases_2026-10-13.json'), 'utf8'));

function py(code, input) {
  return JSON.parse(execFileSync('python', ['-c', [
    'import json,sys',
    'sys.path.insert(0, ' + JSON.stringify(ROOT) + ')',
    'sys.stdout.reconfigure(encoding="utf-8")',
    code,
  ].join('\n')], { input: input || '', encoding: 'utf8' }));
}

test('watcher: a saved title search finds an untracked case, tagged "search"', () => {
  const r = py([
    'from causelist_core import match_people, build_title_watches',
    'entries = json.load(open(' + JSON.stringify(ENTRIES) + ', encoding="utf-8"))',
    'people = [{"person": "Syed Mohtasim", "terms": ["Syed Mohtasim"]}]',
    'def run(terms): return match_people(entries, people, "causelist_14102026.pdf", build_title_watches(terms))',
    'out = {"n": len(entries), "none": len(run([])),',
    '  "sofi": [m for m in run([{"term": "Abdul Rashid Sofi"}]) if m["titles"]],',
    '  "messy": [m["titles"] for m in run(["  abdul   RASHID sofi. "]) if m["titles"]],',
    '  "partial": len([m for m in run(["Abdul Rash"]) if m["titles"]]),',
    '  "short": build_title_watches(["ab", {"term": "  "}, "Wani", "wani"])}',
    'print(json.dumps(out))',
  ].join('\n'));
  assert.strictEqual(r.n, 128, 'all rows for court 11 that day, tracked or not');
  assert.strictEqual(r.sofi.length, 1);
  const m = r.sofi[0];
  assert.deepStrictEqual(m.matchedBy, ['search']);
  assert.deepStrictEqual(m.people, []);
  assert.deepStrictEqual(m.titles, ['Abdul Rashid Sofi']);
  assert.strictEqual(m.court, '11');
  assert.strictEqual(m.sr, '23');
  assert.strictEqual(m.date, '2026-10-14');
  assert.strictEqual(m.caseNo, 'WP(C) 3319/2025 CM(8935/2025)');
  assert.match(m.caseName, /^ABDUL RASHID SOFI AND ORS/);
  assert.match(m.snippet, /M\. M\. SHAH FOR PET/, 'advocates come along in the snippet');
  assert.deepStrictEqual(r.messy, [['abdul RASHID sofi.']], 'case, spacing and punctuation ignored');
  assert.strictEqual(r.partial, 0, 'whole words only');
  assert.deepStrictEqual(r.short, ['Wani'], 'too-short and duplicate terms dropped');
});

test('watcher: merging tags, pruning removed searches, re-parse on new searches', () => {
  const r = py([
    'from causelist_watcher import merge_matches, prune_titles, watch_key',
    'adv = {"date": "2026-10-14", "court": "11", "caseNo": "WP(C) 1/2025", "people": ["A"], "person": "A", "titles": [], "matchedBy": ["advocate"]}',
    'srch = dict(adv, people=[], person="", titles=["Sofi"], matchedBy=["search"])',
    'only = dict(srch, caseNo="WP(C) 2/2025")',
    'legacy = {"date": "2026-10-01", "court": "3", "caseNo": "OWP 9/2020", "people": ["A"], "person": "A"}',
    'saved, added = merge_matches([legacy, adv], [srch, only])',
    'both = [m for m in saved if m["caseNo"] == "WP(C) 1/2025"][0]',
    'merged = {"n": len(saved), "added": added, "both": [both["people"], both["titles"], both["matchedBy"]]}',
    'removed = prune_titles(saved, [])',
    'people = [{"person": "A", "terms": ["A"]}]',
    'print(json.dumps({"merged": merged, "removed": removed, "left": [[m["caseNo"], m.get("titles"), m["matchedBy"]] for m in saved],',
    '  "keys": [watch_key(people, []) == watch_key(people, []), watch_key(people, []) == watch_key(people, ["Sofi"])]}))',
  ].join('\n'));
  assert.deepStrictEqual(r.merged, { n: 3, added: 1, both: [['A'], ['Sofi'], ['advocate', 'search']] });
  assert.strictEqual(r.removed, 1, 'the case found only by the removed search is dropped');
  assert.deepStrictEqual(r.left, [
    ['OWP 9/2020', null, ['advocate']],   // saved before searches existed: left as is, tagged advocate
    ['WP(C) 1/2025', [], ['advocate']],
  ]);
  assert.deepStrictEqual(r.keys, [true, false], 'adding a search forces already-seen PDFs to be read again');
});

let JSDOM = null;
try { ({ JSDOM } = require('jsdom')); } catch (e) { /* optional */ }

test('dashboard: Search saves the term, runs a fetch, then shows the hits', { skip: !JSDOM && 'jsdom not installed' }, async () => {
  const hit = py([
    'from causelist_core import match_people',
    'entries = json.load(open(' + JSON.stringify(ENTRIES) + ', encoding="utf-8"))',
    'print(json.dumps([m for m in match_people(entries, [], "causelist_14102026.pdf", ["Abdul Rashid Sofi"])][0]))',
  ].join('\n'));
  hit.id = 'search-hit';
  const html = execFileSync('python', ['-c', [
    'import json,sys',
    'sys.path.insert(0, ' + JSON.stringify(ROOT) + ')',
    'from dashboard_template import render_dashboard',
    'sys.stdout.reconfigure(encoding="utf-8")',
    'print(render_dashboard(json.loads(sys.stdin.read()), "Test", board={}))',
  ].join('\n')], { input: JSON.stringify(MATCHES), encoding: 'utf8' });

  // a fake GitHub: the contents API for title_watches.json / cases_auto.json,
  // and an Actions run that succeeds straight away
  const repo = { 'title_watches.json': null, 'cases_auto.json': JSON.stringify(MATCHES) };
  const calls = [];
  const statuses = [];
  const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');
  const json = (body, status) => Promise.resolve({ ok: (status || 200) < 300, status: status || 200, json: () => Promise.resolve(body) });
  function fakeFetch(url, opts) {
    url = String(url);
    const method = (opts && opts.method) || 'GET';
    calls.push(method + ' ' + url.replace(/\?.*/, ''));
    const file = /\/contents\/([^?]+)/.exec(url);
    if (file && method === 'GET') {
      const body = repo[file[1]];
      return body == null ? json({}, 404) : json({ content: b64(body), sha: 'sha-' + file[1] });
    }
    if (file && method === 'PUT') {
      const sent = JSON.parse(opts.body);
      repo[file[1]] = Buffer.from(sent.content, 'base64').toString('utf8');
      calls.push('  message: ' + sent.message);
      return json({}, 201);
    }
    if (/\/dispatches$/.test(url)) {
      // the watcher run: it reads title_watches.json and saves the hit
      assert.match(repo['title_watches.json'] || '', /Abdul Rashid Sofi/, 'search saved before the run starts');
      repo['cases_auto.json'] = JSON.stringify(MATCHES.concat([hit]));
      return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) });
    }
    if (/\/runs\?/.test(url)) return json({ workflow_runs: [{ id: 7, status: 'completed', conclusion: 'success', created_at: new Date().toISOString() }] });
    if (url.includes('raw.githubusercontent.com') && url.includes('title_watches.json')) {
      return repo['title_watches.json'] == null ? json({}, 404) : json(JSON.parse(repo['title_watches.json']));
    }
    return Promise.reject(new Error('offline'));
  }

  const errors = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://insim24.github.io/Cause-List---Watcher/causelist_dashboard.html',
    beforeParse(w) {
      w.fetch = fakeFetch;
      w.Notification = { permission: 'default', requestPermission: () => Promise.resolve('default') };
      w.scrollTo = () => {};
      w.addEventListener('error', (e) => errors.push(e.message));
      w.console.error = (...a) => errors.push(a.join(' '));
    },
  });
  const w = dom.window;
  const doc = w.document;
  await new Promise((r) => setTimeout(r, 100));
  const status = () => doc.getElementById('fetchStatus').textContent;
  new w.MutationObserver(() => statuses.push(status())).observe(doc.getElementById('fetchStatus'), { childList: true, characterData: true, subtree: true });
  const submit = (term) => {
    doc.getElementById('titleSearchInput').value = term;
    doc.getElementById('titleSearchForm').dispatchEvent(new w.Event('submit', { cancelable: true }));
  };

  // too short: nothing is saved or run
  w.localStorage.setItem('gh_pat', 'test-token');
  submit('ab');
  assert.match(status(), /at least 3 letters/);
  assert.strictEqual(calls.filter((c) => !c.startsWith('GET')).length, 0);
  assert.strictEqual(doc.getElementById('titleWatchRow').hidden, true);

  submit('Abdul Rashid Sofi');
  await new Promise((r) => setTimeout(r, 400));
  assert.deepStrictEqual(errors, []);

  // order: save the term, then trigger the run, then re-read the cases
  const put = calls.findIndex((c) => c.startsWith('PUT') && c.endsWith('title_watches.json'));
  const dispatch = calls.findIndex((c) => c.endsWith('/dispatches'));
  const reread = calls.findIndex((c, i) => i > dispatch && c.startsWith('GET') && c.endsWith('cases_auto.json'));
  assert.ok(put >= 0 && dispatch > put && reread > dispatch, calls.join('\n'));
  assert.ok(calls.includes('  message: Search cause lists for "Abdul Rashid Sofi"'));
  const saved = JSON.parse(repo['title_watches.json']);
  assert.deepStrictEqual(saved.map((x) => x.term), ['Abdul Rashid Sofi']);
  assert.match(saved[0].added, /^\d{4}-\d{2}-\d{2}$/);

  // honest progress: never "found" before the run has finished
  assert.ok(statuses.some((s) => /^Search saved, looking for it now/.test(s)), statuses.join('\n'));
  assert.ok(!statuses.some((s) => /Found/.test(s) && /Triggering|waiting|Run is/.test(s)));
  assert.match(status(), /Found 1 case for “Abdul Rashid Sofi”/);

  // shown with the existing UI, filtered to the search's chip
  const chip = doc.querySelector('#personChips .chip-btn.active');
  assert.strictEqual(chip.textContent, 'Search: Abdul Rashid Sofi');
  const rows = [...doc.querySelectorAll('#tableBody tr')];
  assert.strictEqual(rows.length, 1);
  assert.match(rows[0].textContent, /WP\(C\) 3319\/2025/);
  assert.strictEqual(rows[0].cells[6].querySelector('.found-by').textContent, 'Search: Abdul Rashid Sofi');
  assert.match(doc.getElementById('titleWatchList').textContent, /Abdul Rashid Sofi/);
  assert.strictEqual(doc.getElementById('titleWatchRow').hidden, false);
  assert.strictEqual(doc.getElementById('titleSearchInput').value, '');

  // the docket card for that day says how it was found, with full details
  w.selectedDate = '2026-10-14';
  w.renderEverything();
  const docket = [...doc.querySelectorAll('.docket')].find((d) => /3319\/2025/.test(d.textContent));
  assert.ok(docket, 'docket card rendered for the hit');
  assert.match(docket.textContent, /Found bySearch: Abdul Rashid Sofi/);
  assert.match(docket.textContent, /Court No11.*Sr No23/);
  assert.match(docket.textContent, /M\. M\. SHAH FOR PET/);

  // removing it rewrites the file and says when the cases go
  doc.querySelector('[data-unwatch="0"]').click();
  await new Promise((r) => setTimeout(r, 100));
  assert.deepStrictEqual(JSON.parse(repo['title_watches.json']), []);
  assert.match(status(), /Removed .*drop off at the next fetch/);
  assert.strictEqual(doc.getElementById('titleWatchRow').hidden, true);
  assert.deepStrictEqual(errors, []);
  w.close();
});
