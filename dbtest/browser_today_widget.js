// Real-Chrome tests for the draggable Today's Board widget: drives headless
// Chrome over the DevTools protocol with real mouse and (emulated) touch input,
// on a dashboard rendered from this repo's cases_auto.json with network calls
// stubbed. Writes the page, a Chrome profile and per-theme screenshots to a
// temp folder (printed at the end).
// Run: node dbtest/browser_today_widget.js   (needs Chrome + python; Node 22+)
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execFileSync } = require('child_process');
const { launch, sleep, CHROME } = require('./cdp_driver');

if (!fs.existsSync(CHROME)) { console.log('SKIP: Chrome not found at ' + CHROME); process.exit(0); }

const ROOT = path.join(__dirname, '..');
const DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'today-widget-'));
const URL = 'file:///' + path.join(DIR, 'page.html').replace(/\\/g, '/');

// the page: real data, fetch stubbed so nothing hits the network
(function buildPage() {
  const read = (f) => JSON.parse(fs.readFileSync(path.join(ROOT, f), 'utf8'));
  const M = read('cases_auto.json');
  const W = fs.existsSync(path.join(ROOT, 'title_watches.json')) ? read('title_watches.json') : [];
  const B = read('display_board.json');
  const html = execFileSync('python', ['-c', [
    'import json,sys', 'sys.path.insert(0, ' + JSON.stringify(ROOT) + ')',
    'from dashboard_template import render_dashboard', 'sys.stdout.reconfigure(encoding="utf-8")',
    'd = json.loads(sys.stdin.read())', 'print(render_dashboard(d["m"], "Test", board=d["b"]))',
  ].join('\n')], { input: JSON.stringify({ m: M, b: B }), encoding: 'utf8' });
  const stub = '<script>(function(){var DATA=' + JSON.stringify({ 'title_watches.json': W, 'cases_auto.json': M, 'display-board': B, 'next_dates.json': {} }) +
    ';window.fetch=function(u){u=String(u);for(var k in DATA)if(u.includes(k))return Promise.resolve({ok:true,status:200,json:function(){return Promise.resolve(JSON.parse(JSON.stringify(DATA[k])));}});' +
    'return Promise.reject(new Error("offline: "+u));};})();</script>';
  fs.writeFileSync(path.join(DIR, 'page.html'), html.replace(/<head[^>]*>/i, (m) => m + stub));
  ['icon-192.png', 'icon-512.png', 'icon-512-maskable.png', 'apple-touch-icon.png', 'site.webmanifest', 'manifest.json']
    .forEach((f) => { if (fs.existsSync(path.join(ROOT, f))) fs.copyFileSync(path.join(ROOT, f), path.join(DIR, f)); });
})();
const THEMES = ['Midnight Ink', 'Chambers Green', 'Parchment Light', 'Frost Silver', 'Willow Light', 'Slate & Silver', 'Deep Burgundy'];
const results = [];
const problems = [];   // console errors / exceptions

function check(name, fn) { results.push([name, fn]); }

(async () => {
  const b = await launch(DIR, 9333);
  const { send, on, evaluate } = b;
  on((m) => {
    if (m.method === 'Runtime.exceptionThrown') problems.push('exception: ' + JSON.stringify(m.params.exceptionDetails).slice(0, 300));
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') problems.push('console.error: ' + m.params.args.map((a) => a.value || a.description).join(' '));
    if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error' && !/manifest/i.test(m.params.entry.text)) problems.push('log: ' + m.params.entry.text + ' ' + (m.params.entry.url || ''));
  });
  await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');

  async function viewport(w, h, touch) {
    await send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: !!touch });
    await send('Emulation.setTouchEmulationEnabled', touch ? { enabled: true, maxTouchPoints: 5 } : { enabled: false });
    await sleep(150);
  }
  async function load() {
    await send('Page.navigate', { url: URL });
    await sleep(900);
  }
  const rect = () => evaluate(`(function(){var r=document.getElementById('todayWidget').getBoundingClientRect(),h=document.getElementById('twHead').getBoundingClientRect();
    return {left:Math.round(r.left),top:Math.round(r.top),right:Math.round(r.right),width:Math.round(r.width),headH:Math.round(h.height),
      vw:document.documentElement.clientWidth,vh:innerHeight,collapsed:document.getElementById('todayWidget').classList.contains('collapsed'),
      pos:getComputedStyle(document.getElementById('todayWidget')).position,inline:document.getElementById('todayWidget').getAttribute('style')||'',
      cls:document.getElementById('todayWidget').className,saved:(function(){try{return localStorage.getItem('today_widget_pos')}catch(e){return 'ERR'}})(),
      z:getComputedStyle(document.getElementById('todayWidget')).zIndex,scrollY:Math.round(scrollY)};})()`);
  // a point on the header's title (the drag handle, not its buttons)
  const handle = async () => evaluate(`(function(){var r=document.querySelector('#twHead .tw-title').getBoundingClientRect();return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};})()`);
  const mouse = (type, x, y, extra) => send('Input.dispatchMouseEvent', Object.assign({ type, x, y, button: 'left', buttons: type === 'mouseReleased' ? 0 : 1, clickCount: 1, pointerType: 'mouse' }, extra || {}));
  async function mouseDrag(dx, dy, steps, midCheck) {
    const p = await handle();
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: p.x, y: p.y, pointerType: 'mouse' });
    await mouse('mousePressed', p.x, p.y);
    let mid = null;
    for (let i = 1; i <= steps; i++) {
      await mouse('mouseMoved', Math.round(p.x + dx * i / steps), Math.round(p.y + dy * i / steps));
      if (i === Math.ceil(steps / 2) && midCheck) mid = await rect();
    }
    await mouse('mouseReleased', p.x + dx, p.y + dy);
    await sleep(80);
    return mid;
  }
  async function mouseTap() {
    const p = await handle();
    await mouse('mousePressed', p.x, p.y); await mouse('mouseReleased', p.x, p.y); await sleep(80);
  }
  const touch = (type, pts) => send('Input.dispatchTouchEvent', { type, touchPoints: pts });
  async function touchDrag(x, y, dx, dy, steps) {
    await touch('touchStart', [{ x, y }]);
    for (let i = 1; i <= steps; i++) { await touch('touchMove', [{ x: Math.round(x + dx * i / steps), y: Math.round(y + dy * i / steps) }]); await sleep(16); }
    // a real finger slows before lifting; a flick at full speed is a fling, and Chrome
    // swallows the click of a tap that stops a fling (any page, not this widget)
    for (let k = 0; k < 6; k++) { await touch('touchMove', [{ x: Math.round(x + dx), y: Math.round(y + dy) }]); await sleep(30); }
    await touch('touchEnd', [{ x: Math.round(x + dx), y: Math.round(y + dy) }]);
    await sleep(400);
  }

  // ---------- desktop, mouse ----------
  await viewport(1280, 900, false);
  await load();
  await evaluate(`localStorage.clear()`); await load();
  const r0 = await rect();
  check('default spot: fixed top-right, 18px in', () => {
    assert.strictEqual(r0.pos, 'fixed'); assert.strictEqual(r0.top, 18); assert.strictEqual(r0.vw - r0.right, 18);
    assert.strictEqual(r0.inline, ''); assert.match(r0.cls, /tw-draggable/); assert.doesNotMatch(r0.cls, /tw-moved/);
  });
  const gripShown = await evaluate(`getComputedStyle(document.querySelector('.tw-grip')).display + '|' + getComputedStyle(document.getElementById('twHead')).touchAction + '|' + getComputedStyle(document.getElementById('twHead')).cursor + '|' + getComputedStyle(document.body).touchAction + '|' + getComputedStyle(document.getElementById('twReset')).display`);
  check('grip shown; touch-action:none + grab on the handle only; reset hidden by default', () => assert.match(gripShown, /^(inline|block)\|none\|grab\|auto\|none$/));

  await mouseTap(); const afterTap = await rect(); await mouseTap(); const afterTap2 = await rect();
  check('mouse click on header still collapses / expands', () => { assert.strictEqual(afterTap.collapsed, true); assert.strictEqual(afterTap2.collapsed, false); });

  const before = await rect();
  // move 4px and back: below the 6px threshold, so it's a click
  { const p = await handle(); await mouse('mousePressed', p.x, p.y); await mouse('mouseMoved', p.x + 4, p.y + 3); await mouse('mouseReleased', p.x + 4, p.y + 3); await sleep(80); }
  const jitter = await rect();
  check('a 4px wobble is still a click (toggles, does not move)', () => { assert.strictEqual(jitter.collapsed, true); assert.strictEqual(jitter.left, before.left); assert.strictEqual(jitter.top, before.top); });
  await mouseTap();   // expand again

  const mid = await mouseDrag(-400, 220, 12, true);
  const r = await rect();
  check('mouse drag moves it by the pointer delta and does not toggle', () => {
    assert.strictEqual(r.left, before.left - 400); assert.strictEqual(r.top, before.top + 220);
    assert.strictEqual(r.collapsed, false, 'drag release must not toggle collapse');
  });
  check('while dragging: tw-dragging class (raised z-index 60, stronger shadow), back to 40 after', () => {
    assert.match(mid.cls, /tw-dragging/); assert.strictEqual(mid.z, '60'); assert.doesNotMatch(r.cls, /tw-dragging/); assert.strictEqual(r.z, '40');
  });
  check('position saved as nearest-corner offsets', () => {
    const s = JSON.parse(r.saved);
    assert.deepStrictEqual(s, { h: 'right', x: r.vw - r.right, v: 'top', y: r.top });
  });
    const resetShown = await evaluate(`getComputedStyle(document.getElementById('twReset')).display`);

  // clamp: drag far past each edge
  await mouseDrag(-3000, -3000, 10); const tl = await rect();
  await mouseDrag(5000, 5000, 10); const br = await rect();
  check('clamped at the top-left and bottom-right edges (header stays visible)', () => {
    assert.strictEqual(tl.left, 0); assert.strictEqual(tl.top, 0);
    assert.strictEqual(br.left, br.vw - br.width); assert.strictEqual(br.top, br.vh - br.headH);
  });
  check('bottom-right drop saved against the bottom-right corner', () => assert.deepStrictEqual(JSON.parse(br.saved), { h: 'right', x: 0, v: 'bottom', y: br.headH }));

  // put it somewhere ordinary, then reload
  await mouseDrag(-500, -br.vh + 300, 10); const placed = await rect();
  await load(); const reloaded = await rect();
  check('position survives a reload', () => { assert.strictEqual(reloaded.left, placed.left); assert.strictEqual(reloaded.top, placed.top); assert.match(reloaded.cls, /tw-moved/); });

  // resize narrower while floating, then into banner mode and back
  await viewport(1200, 640, false); const narrowerFloat = await rect();
  await viewport(1000, 800, false); const banner = await rect();
  await viewport(1280, 900, false); const backWide = await rect();
  check('narrower floating viewport: same corner offsets, still on screen', () => {
    const s = JSON.parse(placed.saved);
    const off = s.h === 'left' ? narrowerFloat.left : narrowerFloat.vw - narrowerFloat.right;
    assert.strictEqual(off, s.x, 'kept its offset from the ' + s.h + ' edge');
    assert.ok(narrowerFloat.left >= 0 && narrowerFloat.right <= narrowerFloat.vw);
    assert.ok(narrowerFloat.top >= 0 && narrowerFloat.top <= narrowerFloat.vh - narrowerFloat.headH);
  });
  check('banner mode (<=1180px): static, no inline left/top, not draggable', () => {
    assert.strictEqual(banner.pos, 'static'); assert.strictEqual(banner.inline, ''); assert.doesNotMatch(banner.cls, /tw-draggable/);
  });
  check('back to wide: saved spot re-applied', () => { assert.strictEqual(backWide.left, placed.left); assert.strictEqual(backWide.top, placed.top); });

  // reset
  const resetBtn = await evaluate(`(function(){var r=document.getElementById('twReset').getBoundingClientRect();return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};})()`);
  await mouse('mousePressed', resetBtn.x, resetBtn.y); await mouse('mouseReleased', resetBtn.x, resetBtn.y); await sleep(80);
  const afterReset = await rect();
  check('reset button: back to the default spot, saved position cleared, no toggle', () => {
    assert.notStrictEqual(resetShown, 'none');
    assert.strictEqual(afterReset.top, 18); assert.strictEqual(afterReset.vw - afterReset.right, 18);
    assert.strictEqual(afterReset.inline, ''); assert.strictEqual(afterReset.saved, null); assert.strictEqual(afterReset.collapsed, false);
    assert.doesNotMatch(afterReset.cls, /tw-moved/);
  });

  // ---------- laptop-saved position restored on smaller screens ----------
  await evaluate(`localStorage.setItem('today_widget_pos', JSON.stringify({h:'left',x:900,v:'bottom',y:150}))`);
  await viewport(1920, 1080, false); await load(); const big = await rect();
  await viewport(1190, 600, false); const small = await rect();
  await viewport(390, 844, true); await load(); const phone = await rect();
  check('position saved at 1920 wide restores on screen at 1190x600; phone shows the banner', () => {
    assert.deepStrictEqual([big.left, big.top], [900, 1080 - 150]);
    assert.ok(small.left >= 0 && small.left + small.width <= small.vw, JSON.stringify(small));
    assert.strictEqual(small.top, 600 - 150);
    assert.strictEqual(phone.pos, 'static'); assert.strictEqual(phone.inline, '');
  });

  // ---------- touch (emulated touchscreen) ----------
  // phone: dragging the banner header scrolls the page (dragging is off there)
  await evaluate(`scrollTo(0,0)`);
  { const p = await handle(); await touchDrag(p.x, p.y + 0, 0, -300, 12); }
  const phoneAfter = await rect();
  check('phone banner: swiping its header scrolls the page, widget not moved', () => {
    assert.ok(phoneAfter.scrollY > 100, 'scrollY ' + phoneAfter.scrollY); assert.strictEqual(phoneAfter.inline, '');
  });

  // touch on a wide (tablet-landscape) screen where it floats
  await evaluate(`localStorage.removeItem('today_widget_pos')`);
  await viewport(1366, 900, true); await load();
  const t0 = await rect();
  { const p = await handle(); await touchDrag(p.x, p.y, -350, 260, 14); }
  const t1 = await rect();
  check('touch drag moves it, page does not scroll, no toggle', () => {
    assert.strictEqual(t1.left, t0.left - 350); assert.strictEqual(t1.top, t0.top + 260);
    assert.strictEqual(t1.scrollY, 0); assert.strictEqual(t1.collapsed, false);
  });
  { const p = await handle(); await touch('touchStart', [{ x: p.x, y: p.y }]); await touch('touchEnd', [{ x: p.x, y: p.y }]); await sleep(400); }
  const t2 = await rect();
  { const p = await handle(); await touch('touchStart', [{ x: p.x, y: p.y }]); await touch('touchEnd', [{ x: p.x, y: p.y }]); await sleep(400); }
  const t3 = await rect();
  check('touch tap on the header toggles collapse (and again)', () => { assert.strictEqual(t2.collapsed, true); assert.strictEqual(t3.collapsed, false); });
  // swipe on the page itself (stats area, away from the widget) scrolls normally
  const stats = await evaluate(`(function(){var r=document.getElementById('statsRow').getBoundingClientRect();return {x:Math.round(r.left+60),y:Math.round(r.top+40)};})()`);
  await touchDrag(stats.x, stats.y + 300, 0, -350, 12);
  const t4 = await rect();
  check('touch swipe outside the handle scrolls the page normally', () => { assert.ok(t4.scrollY > 100, 'scrollY ' + t4.scrollY); assert.strictEqual(t4.left, t1.left); });
  // touching the widget body (its list) scrolls too, rather than dragging
  const body = await evaluate(`(function(){var r=document.getElementById('todayWidgetBody').getBoundingClientRect();return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+20)};})()`);
  await touchDrag(body.x, body.y, 0, -30, 6);
  const t5 = await rect();
  check('touching the widget body does not drag it', () => { assert.strictEqual(t5.left, t1.left); assert.strictEqual(t5.top, t1.top); });

  // ---------- stacking: widget vs theme gear / theme menu / court panel ----------
  await viewport(1280, 900, false);
  await evaluate(`localStorage.clear()`); await load();
  const gear = await evaluate(`(function(){var r=document.getElementById('themeGearBtn').getBoundingClientRect();return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};})()`);
  const w0 = await rect();
  // drop the header's title onto the gear
  { const p = await handle(); await mouseDrag(gear.x - p.x, gear.y - p.y, 12); }
  const stack = await evaluate(`(function(){
    var tw=document.getElementById('todayWidget'), g=document.getElementById('themeGearBtn').getBoundingClientRect();
    var overGear = tw.contains(document.elementFromPoint(g.left+g.width/2, g.top+g.height/2));
    document.getElementById('themePanel').style.display='flex';   // menu open (as the gear click does)
    var p=document.getElementById('themePanel').getBoundingClientRect();
    var menuOnTop = document.getElementById('themePanel').contains(document.elementFromPoint(p.left+20, p.top+15));
    document.getElementById('themePanel').style.display='none';
    document.getElementById('courtModal').hidden=false;
    var r=tw.getBoundingClientRect();
    var modalOnTop = !tw.contains(document.elementFromPoint(r.left+r.width/2, r.top+10));
    document.getElementById('courtModal').hidden=true;
    return {overGear:overGear, menuOnTop:menuOnTop, modalOnTop:modalOnTop};})()`);
  check('widget dragged over the gear covers it; the open theme menu and the court panel still sit above the widget', () => {
    assert.ok(w0.left > gear.x, 'default spot is clear of the gear');
    assert.deepStrictEqual(stack, { overGear: true, menuOnTop: true, modalOnTop: true });
  });

  // ---------- default spot vs controls at common widths ----------
  await viewport(1280, 900, false);
  await evaluate(`localStorage.clear()`); await load();
  const overlaps = {};
  for (const [w, h] of [[1181, 800], [1280, 720], [1366, 768], [1440, 900], [1536, 864], [1920, 1080]]) {
    await viewport(w, h, false); await sleep(150);
    overlaps[w + 'x' + h] = await evaluate(`(function(){var tw=document.getElementById('todayWidget'),r=tw.getBoundingClientRect(),hit=[];
      document.querySelectorAll('button,a,input,select,[role=button]').forEach(function(el){if(tw.contains(el))return;var b=el.getBoundingClientRect();if(!b.width||!b.height)return;
        if(b.left<r.right&&b.right>r.left&&b.top<r.bottom&&b.bottom>r.top){hit.push((el.id||el.textContent.trim().slice(0,30)||el.className)+'@'+Math.round(b.left)+','+Math.round(b.top))}});return hit;})()`);
  }

  // ---------- themes ----------
  await viewport(1280, 900, false);
  const themeShots = {};
  for (let i = 0; i < THEMES.length; i++) {
    const before = problems.length;
    await evaluate(`localStorage.setItem('dashboard_theme', ${JSON.stringify(THEMES[i])}); localStorage.setItem('today_widget_pos', JSON.stringify({h:'right',x:260,v:'top',y:150}))`);
    await load();
    // grab mid-drag for the screenshot
    const p = await handle();
    await mouse('mousePressed', p.x, p.y); await mouse('mouseMoved', p.x - 20, p.y + 20); await mouse('mouseMoved', p.x - 40, p.y + 40);
    const shot = await send('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: 1280, height: 520, scale: 1 } });
    fs.writeFileSync(path.join(DIR, 'theme_' + i + '.png'), Buffer.from(shot.data, 'base64'));
    await mouse('mouseReleased', p.x - 40, p.y + 40); await sleep(60);
    const still = await send('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: 1280, height: 520, scale: 1 } });
    fs.writeFileSync(path.join(DIR, 'theme_' + i + '_rest.png'), Buffer.from(still.data, 'base64'));
    themeShots[THEMES[i]] = problems.length - before;
  }

  // ---------- report ----------
  let failed = 0;
  for (const [name, fn] of results) {
    try { await fn(); console.log('PASS', name); } catch (e) { failed++; console.log('FAIL', name, '\n   ', e.message.split('\n').slice(0, 6).join('\n    ')); }
  }
  const covered = Object.keys(overlaps).filter((k) => overlaps[k].length);
  if (covered.length) { failed++; console.log('FAIL default spot covers controls:', JSON.stringify(overlaps)); }
  else console.log('PASS default spot covers no buttons/links/inputs at', Object.keys(overlaps).join(', '));
  if (problems.length) { failed++; console.log('FAIL console errors:', problems); }
  else console.log('PASS no console errors in', THEMES.length, 'themes:', JSON.stringify(themeShots));
  console.log('\nscreenshots and page:', DIR);
  b.close();
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error('HARNESS', e); process.exit(2); });
