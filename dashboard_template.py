"""Generates a static, self-contained HTML dashboard from the accumulated
matches JSON: stat cards, a month calendar, a day-by-day agenda panel that
updates on click, and a full searchable/filterable case list below.
Visually consistent with the manual-upload 'My Causelist Docket' artifact,
but read-only and pre-populated by the watcher script instead of by hand."""

import json
import html as _html
from datetime import datetime

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<link rel="manifest" href="site.webmanifest" />
<link rel="icon" href="icon-192.png" type="image/png" />
<link rel="apple-touch-icon" href="apple-touch-icon.png" />
<meta name="theme-color" content="#0B1319" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
<meta name="apple-mobile-web-app-title" content="Causelist" />
<title>My Causelist Docket</title>
<style>
  :root{{
    --ink-900:#0B1319;--ink-850:#0F1A22;--ink-800:#15222C;--ink-700:#1D2E3A;--ink-650:#243848;
    --line:#2E4353;--line-soft:#243848;
    --parchment:#EFE7D6;--parchment-dim:#93A0A6;--parchment-faint:#5C6B72;
    --seal:#C2503A;--seal-soft:rgba(194,80,58,0.14);--seal-line:rgba(194,80,58,0.45);
    --brass:#CBA135;--brass-soft:rgba(203,161,53,0.14);--brass-line:rgba(203,161,53,0.5);
    --shadow:0 10px 28px rgba(0,0,0,0.35);
    --font-serif:Georgia,'Iowan Old Style','Palatino Linotype','Book Antiqua',serif;
    --font-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace;
    --font-sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  }}
  *{{box-sizing:border-box;}}
  html,body{{margin:0;padding:0;}}
  body{{
    background:
      radial-gradient(1100px 500px at 8% -8%, rgba(203,161,53,0.07), transparent 55%),
      radial-gradient(900px 500px at 100% 0%, rgba(194,80,58,0.05), transparent 50%),
      var(--ink-900);
    color:var(--parchment);font-family:var(--font-sans);-webkit-font-smoothing:antialiased;
    min-height:100vh;
  }}
  button{{font-family:inherit;}}
  .page{{max-width:1120px;margin:0 auto;padding:32px 24px 70px;}}

  /* ---- hero ---- */
  .hero{{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:16px;
    padding-bottom:22px;border-bottom:1px solid var(--line);margin-bottom:26px;}}
  .hero-left{{display:flex;gap:16px;align-items:center;}}
  .theme-picker{{position:relative;flex:none;z-index:65;}}
  .theme-gear-btn{{background:transparent;border:1px solid var(--line);
    color:var(--parchment-dim);width:32px;height:32px;border-radius:50%;cursor:pointer;
    font-size:15px;transition:.15s;}}
  .theme-gear-btn:hover{{border-color:var(--brass);color:var(--brass);}}
  .theme-panel{{position:absolute;top:40px;left:0;z-index:65;background:var(--ink-850);
    border:1px solid var(--line);border-radius:9px;box-shadow:var(--shadow);padding:8px;
    display:flex;flex-direction:column;gap:4px;min-width:190px;}}
  .theme-swatch-btn{{display:flex;align-items:center;gap:10px;background:transparent;
    border:1px solid transparent;border-radius:6px;padding:7px 9px;cursor:pointer;
    color:var(--parchment);font-size:12.5px;font-family:inherit;text-align:left;width:100%;transition:.12s;}}
  .theme-swatch-btn:hover{{background:var(--ink-700);}}
  .theme-swatch-btn.active{{border-color:var(--brass);background:var(--brass-soft);}}
  .theme-swatch-dot{{width:16px;height:16px;border-radius:50%;flex:none;border:1px solid rgba(255,255,255,0.15);}}
  .seal{{width:54px;height:54px;border-radius:50%;border:1.5px solid var(--brass);
    display:flex;align-items:center;justify-content:center;font-family:var(--font-serif);
    font-size:32px;color:var(--brass);flex:none;box-shadow:0 0 0 4px var(--ink-900), 0 0 0 5px var(--brass-line);}}
  h1{{font-family:var(--font-serif);font-size:27px;margin:0 0 5px;letter-spacing:.2px;font-weight:700;}}
  .hero-sub{{margin:0;color:var(--parchment-dim);font-size:13px;}}
  .chip-row{{display:flex;gap:8px;flex-wrap:wrap;}}
  .chip-btn{{background:var(--ink-800);border:1px solid var(--line);color:var(--parchment-dim);
    padding:8px 15px;border-radius:999px;font-size:12.5px;cursor:pointer;transition:.15s;}}
  .chip-btn:hover{{color:var(--parchment);}}
  .chip-btn.active{{background:var(--brass-soft);border-color:var(--brass);color:var(--brass);font-weight:600;}}

  /* ---- fetch now ---- */
  .fetch-row{{display:flex;align-items:center;gap:12px;margin-bottom:22px;flex-wrap:wrap;}}
  .fetch-btn{{background:var(--brass);color:var(--ink-900);border:none;font-weight:700;
    padding:8px 16px;border-radius:6px;cursor:pointer;font-size:12.5px;
    display:flex;align-items:center;gap:7px;transition:.15s;}}
  .fetch-btn:hover{{opacity:.85;}}
  .fetch-btn:disabled{{opacity:.55;cursor:default;}}
  .fetch-status{{font-size:12px;color:var(--parchment-dim);}}
  .fetch-status.ok{{color:#7FBF7F;}}
  .fetch-status.err{{color:var(--seal);}}
  .fetch-status a{{color:inherit;text-decoration:underline;}}
  .fetch-manual-link{{font-size:11px;color:var(--parchment-faint);text-decoration:underline;cursor:pointer;}}

  /* ---- stat cards ---- */
  .stats-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px;}}
  .stat-card{{background:var(--ink-800);border:1px solid var(--line);border-radius:9px;
    padding:16px 18px;box-shadow:var(--shadow);position:relative;overflow:hidden;}}
  .stat-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--brass);}}
  .stat-card.hot::before{{background:var(--seal);}}
  .stat-num{{font-family:var(--font-serif);font-size:28px;color:var(--parchment);line-height:1;margin-bottom:7px;font-weight:700;}}
  .stat-num.hot{{color:var(--seal);}}
  .stat-label{{font-family:var(--font-mono);font-size:10px;letter-spacing:1.2px;text-transform:uppercase;color:var(--parchment-faint);}}
  .stat-sub{{font-size:11.5px;color:var(--brass);margin-top:5px;}}

  /* ---- main grid: calendar + agenda ---- */
  .main-grid{{display:grid;grid-template-columns:1fr 1.2fr;gap:16px;margin-bottom:20px;align-items:start;}}
  .card{{background:var(--ink-800);border:1px solid var(--line);border-radius:9px;padding:19px;box-shadow:var(--shadow);}}
  .card h2{{font-family:var(--font-serif);font-size:17px;margin:0;}}

  .cal-nav{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;}}
  .cal-nav button{{background:transparent;border:1px solid var(--line);color:var(--parchment);
    width:30px;height:30px;border-radius:50%;cursor:pointer;font-size:15px;transition:.15s;}}
  .cal-nav button:hover{{border-color:var(--brass);color:var(--brass);}}
  .cal-nav h3{{font-family:var(--font-serif);font-size:16.5px;margin:0;}}
  .cal-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;}}
  .cal-dow{{text-align:center;font-size:10px;color:var(--parchment-faint);font-family:var(--font-mono);padding-bottom:5px;letter-spacing:.5px;}}
  .cal-cell{{aspect-ratio:1;border:1px solid var(--line);border-radius:6px;display:flex;
    align-items:center;justify-content:center;font-size:13px;background:var(--ink-700);
    position:relative;transition:.13s;}}
  .cal-cell.empty{{border:none;background:transparent;}}
  .cal-cell.has-case{{cursor:pointer;border-color:var(--seal-line);}}
  .cal-cell.has-case:hover{{background:var(--seal-soft);transform:translateY(-1px);}}
  .cal-cell.today{{outline:1.5px solid var(--brass);outline-offset:-1px;}}
  .cal-cell.selected{{background:var(--brass-soft);border-color:var(--brass);}}
  .stamp{{position:absolute;top:2px;right:2px;background:var(--seal);color:#F5F0E6;
    font-family:var(--font-mono);font-size:9px;border-radius:50%;width:15px;height:15px;
    display:flex;align-items:center;justify-content:center;box-shadow:0 1px 3px rgba(0,0,0,.4);}}
  .link-btn{{background:transparent;border:none;color:var(--brass);font-size:12.5px;cursor:pointer;
    margin-top:14px;padding:0;font-family:inherit;}}
  .link-btn:hover{{text-decoration:underline;}}

  .agenda-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:6px;}}
  .agenda-day-group{{margin-bottom:18px;}}
  .agenda-day-group:last-child{{margin-bottom:0;}}
  .agenda-day-label{{font-family:var(--font-mono);font-size:11px;letter-spacing:1px;text-transform:uppercase;
    color:var(--brass);margin-bottom:9px;padding-bottom:5px;border-bottom:1px dashed var(--line);
    display:flex;justify-content:space-between;}}
  .agenda-day-label .away{{color:var(--parchment-faint);text-transform:none;letter-spacing:0;font-size:11px;}}

  /* ---- docket cards (a single case entry) ---- */
  .docket{{background:var(--ink-700);border:1px solid var(--line);border-radius:6px;padding:13px 15px;
    margin-bottom:10px;border-top:3px double var(--brass);transition:.15s;}}
  .docket:last-child{{margin-bottom:0;}}
  .docket:hover{{transform:translateY(-1px);box-shadow:0 6px 16px rgba(0,0,0,.32);}}
  .docket-meta{{display:flex;flex-wrap:wrap;gap:16px 20px;margin-bottom:9px;font-family:var(--font-mono);font-size:12.5px;}}
  .docket-meta div span{{display:block;font-size:9.5px;color:var(--brass);text-transform:uppercase;letter-spacing:1px;margin-bottom:2px;}}
  .snippet{{background:var(--ink-850);border:1px solid var(--line);border-radius:4px;padding:9px 11px;
    font-family:var(--font-mono);font-size:11.5px;color:var(--parchment-dim);white-space:pre-wrap;
    max-height:110px;overflow:auto;}}

  /* ---- all cases ---- */
  .all-head{{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:16px;flex-wrap:wrap;}}
  #searchBox{{flex:1;min-width:240px;background:var(--ink-700);border:1px solid var(--line);
    color:var(--parchment);padding:10px 13px;border-radius:6px;font-size:14px;}}
  #searchBox:focus{{outline:2px solid var(--brass);outline-offset:1px;}}

  .empty-state{{text-align:center;padding:34px 10px;color:var(--parchment-dim);}}
  .footer-note{{font-size:11px;color:var(--parchment-faint);text-align:center;margin-top:22px;}}

  /* ---- sticky Today's Hearings widget ---- */
  #todayWidget{{
    position:fixed;top:18px;right:18px;width:300px;max-height:70vh;z-index:40;
    background:var(--ink-850);border:1px solid var(--brass-line);border-radius:9px;
    box-shadow:0 14px 34px rgba(0,0,0,0.5);display:flex;flex-direction:column;overflow:hidden;
  }}
  #todayWidget.collapsed #todayWidgetBody{{display:none;}}
  #todayWidget.collapsed{{max-height:none;}}
  .tw-head{{display:flex;align-items:center;justify-content:space-between;gap:8px;
    padding:11px 13px;border-bottom:1px solid var(--line);background:var(--ink-800);cursor:pointer;}}
  .tw-head-left{{display:flex;align-items:center;gap:8px;}}
  .tw-dot{{width:8px;height:8px;border-radius:50%;background:var(--seal);flex:none;}}
  .tw-dot.idle{{background:var(--parchment-faint);}}
  .tw-title{{font-family:var(--font-serif);font-size:14.5px;}}
  .tw-count{{font-family:var(--font-mono);font-size:10.5px;color:var(--brass);background:var(--brass-soft);
    padding:2px 7px;border-radius:999px;}}
  .tw-toggle{{background:none;border:none;color:var(--parchment-dim);font-size:13px;cursor:pointer;padding:2px 4px;}}
  #todayWidgetBody{{overflow-y:auto;padding:11px 13px;}}
  .tw-row{{display:grid;grid-template-columns:34px 44px 1fr;gap:9px;align-items:start;
    padding:8px 0;border-bottom:1px solid var(--line-soft);}}
  .tw-row:last-child{{border-bottom:none;}}
  .tw-sr{{font-family:var(--font-mono);font-size:12px;color:var(--brass);background:var(--brass-soft);
    border-radius:4px;text-align:center;padding:3px 0;height:fit-content;}}
  .tw-court{{font-family:var(--font-mono);font-size:11px;color:var(--parchment-dim);}}
  .tw-court b{{display:block;color:var(--parchment);font-size:13px;}}
  .tw-case{{font-size:12.5px;line-height:1.35;}}
  .tw-adv{{font-size:10.5px;color:var(--parchment-faint);margin-top:2px;}}
  .tw-note{{font-size:10.5px;color:var(--parchment-faint);padding:9px 13px;border-top:1px dashed var(--line);
    line-height:1.5;}}
  .tw-empty{{padding:16px 13px;color:var(--parchment-dim);font-size:12.5px;text-align:center;}}

  /* ---- live display board ---- */
  .board-row{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px;}}
  .wing-card h3{{font-family:var(--font-serif);font-size:15px;margin:0 0 10px;display:flex;align-items:center;gap:8px;}}
  .wing-badge{{font-family:var(--font-mono);font-size:9.5px;letter-spacing:.6px;text-transform:uppercase;
    padding:2px 8px;border-radius:999px;}}
  .wing-badge.idle{{background:var(--ink-700);color:var(--parchment-faint);}}
  .wing-badge.active{{background:var(--seal-soft);color:var(--seal);}}
  .board-court-row{{display:flex;justify-content:space-between;align-items:center;
    background:var(--ink-700);border:1px solid var(--line);border-radius:5px;
    padding:8px 11px;margin-bottom:7px;font-family:var(--font-mono);font-size:12.5px;}}
  .board-court-row b{{color:var(--brass);}}
  .board-msg{{font-size:11.5px;color:var(--parchment-dim);line-height:1.5;padding:7px 0;
    border-top:1px dashed var(--line);}}
  .board-msg:first-of-type{{border-top:none;}}
  .board-empty{{font-size:12px;color:var(--parchment-faint);}}
  .board-stale-note{{font-size:10.5px;color:var(--parchment-faint);margin-top:6px;}}

  /* ---- sortable table (All cases) ---- */
  .table-scroll{{overflow-x:auto;}}
  table.case-table{{width:100%;border-collapse:collapse;font-size:13px;min-width:720px;}}
  table.case-table th{{text-align:left;font-family:var(--font-mono);font-size:10px;letter-spacing:.8px;
    text-transform:uppercase;color:var(--brass);padding:9px 10px;border-bottom:1px solid var(--line);
    cursor:pointer;white-space:nowrap;user-select:none;}}
  table.case-table th:hover{{color:var(--parchment);}}
  table.case-table th .arrow{{opacity:.6;font-size:9px;margin-left:3px;}}
  table.case-table td{{padding:10px;border-bottom:1px solid var(--line-soft);vertical-align:top;}}
  table.case-table tr:hover td{{background:var(--ink-700);}}
  td.mono{{font-family:var(--font-mono);font-size:12.5px;white-space:nowrap;}}
  td.wrap-cell{{max-width:260px;white-space:normal;overflow-wrap:break-word;}}

  @media (max-width:1180px){{
    #todayWidget{{position:static;width:auto;max-height:none;margin-bottom:20px;box-shadow:var(--shadow);}}
    #todayWidgetBody{{max-height:280px;}}
  }}
  @media (max-width:900px){{
    .main-grid{{grid-template-columns:1fr;}}
    .stats-row{{grid-template-columns:repeat(2,1fr);}}
    .board-row{{grid-template-columns:1fr;}}
  }}
  @media (max-width:520px){{
    .hero{{align-items:flex-start;}}
    h1{{font-size:22px;}}
    .stat-num{{font-size:23px;}}
    .docket-meta{{gap:10px 16px;}}
  }}
</style>
</head>
<body>
<div class="page">

  <div id="todayWidget">
    <div class="tw-head" id="twHead">
      <div class="tw-head-left">
        <span class="tw-dot idle" id="twDot"></span>
        <span class="tw-title">Today's Board</span>
        <span class="tw-count" id="twCount">0</span>
      </div>
      <button class="tw-toggle" id="twToggle">&#8722;</button>
    </div>
    <div id="todayWidgetBody"></div>
    <div class="tw-note">Ordered by serial number within each court \u2014 usually also hearing order, but there's no live "now calling" feed available for this court, so treat this as a schedule, not a real-time queue.</div>
  </div>

  <div class="hero">
    <div class="hero-left">
      <div class="seal">§</div>
      <div>
        <h1>My Causelist Docket</h1>
        <p class="hero-sub">{name} &middot; <span id="lastChecked">last checked {generated_at}</span></p>
      </div>
      <div class="theme-picker">
        <button class="theme-gear-btn" id="themeGearBtn" title="Choose theme" aria-label="Choose theme">&#9881;</button>
        <div class="theme-panel" id="themePanel" style="display:none"></div>
      </div>
    </div>
    <div class="chip-row" id="personChips"></div>
  </div>

  <div class="fetch-row">
    <button class="fetch-btn" id="fetchBtn"><span>&#8635;</span><span>Fetch Now</span></button>
    <span class="fetch-status" id="fetchStatus"></span>
    <a href="#" class="fetch-manual-link" id="manualTokenLink">or paste a token manually</a>
  </div>

  <div class="stats-row" id="statsRow"></div>

  <div class="board-row" id="boardRow" style="display:none"></div>

  <div class="main-grid">
    <div class="card">
      <div class="cal-nav">
        <button data-calnav="prev">&#8249;</button>
        <h3 id="calTitle"></h3>
        <button data-calnav="next">&#8250;</button>
      </div>
      <div class="cal-grid" id="calGrid"></div>
      <button class="link-btn" id="todayBtn">Jump to today</button>
    </div>

    <div class="card">
      <div class="agenda-head">
        <h2 id="agendaTitle">Upcoming</h2>
        <button class="link-btn" id="backToUpcoming" style="display:none">&larr; back to upcoming</button>
      </div>
      <div id="agendaBody"></div>
    </div>
  </div>

  <div class="card">
    <div class="all-head">
      <h2>All cases ({count})</h2>
      <input type="text" id="searchBox" placeholder="Search by court no., case no., date&hellip;" />
    </div>
    <div class="table-scroll">
      <table class="case-table">
        <thead><tr id="tableHead"></tr></thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
  </div>

  <p class="footer-note">Generated by your local causelist_watcher.py script &middot; {source_note}</p>
</div>

<script>
var THEMES = {{
  'Midnight Ink': {{ink900:'#0B1319',ink850:'#0F1A22',ink800:'#15222C',ink700:'#1D2E3A',ink650:'#243848',line:'#2E4353',linesoft:'#243848',parchment:'#EFE7D6',parchdim:'#93A0A6',parchfaint:'#7E8D94',seal:'#C2503A',sealAlpha:0.14,brass:'#CBA135',brassAlpha:0.14}},
  'Chambers Green': {{ink900:'#0A1410',ink850:'#0E1D17',ink800:'#14281F',ink700:'#1C3A2B',ink650:'#254A37',line:'#2E5340',linesoft:'#254A37',parchment:'#E9EDE2',parchdim:'#94A896',parchfaint:'#7E9080',seal:'#C2503A',sealAlpha:0.14,brass:'#C9A227',brassAlpha:0.14}},
  'Parchment Light': {{ink900:'#F6F1E4',ink850:'#EFE8D5',ink800:'#EAE2CC',ink700:'#E2D8BD',ink650:'#D8CBA9',line:'#C9B98D',linesoft:'#D8CBA9',parchment:'#2A2116',parchdim:'#6B5D45',parchfaint:'#5E5340',seal:'#A8402E',sealAlpha:0.14,brass:'#6B4E0D',brassAlpha:0.18}},
  'Frost Silver': {{ink900:'#F1F3F5',ink850:'#EAEDF0',ink800:'#E3E7EB',ink700:'#D9DEE4',ink650:'#CCD3DB',line:'#B8C2CC',linesoft:'#CCD3DB',parchment:'#1B222A',parchdim:'#4F5A64',parchfaint:'#485560',seal:'#A8402E',sealAlpha:0.14,brass:'#3D5A73',brassAlpha:0.16}},
  'Willow Light': {{ink900:'#F3F6EF',ink850:'#ECF0E5',ink800:'#E4EADB',ink700:'#D8E0CB',ink650:'#C9D4B8',line:'#B8C7A0',linesoft:'#C9D4B8',parchment:'#1F2A18',parchdim:'#4E6140',parchfaint:'#485C3B',seal:'#A8402E',sealAlpha:0.14,brass:'#3F5824',brassAlpha:0.19}},
  'Slate & Silver': {{ink900:'#12161C',ink850:'#171C24',ink800:'#1E252F',ink700:'#28323F',ink650:'#333F4E',line:'#3B4756',linesoft:'#333F4E',parchment:'#E7EAEE',parchdim:'#98A2AF',parchfaint:'#80899A',seal:'#C2503A',sealAlpha:0.14,brass:'#B9C4CE',brassAlpha:0.14}},
  'Deep Burgundy': {{ink900:'#1A0E12',ink850:'#241319',ink800:'#301A22',ink700:'#40232E',ink650:'#502D3A',line:'#5C3040',linesoft:'#502D3A',parchment:'#F0E6E4',parchdim:'#A38E92',parchfaint:'#8F7A7D',seal:'#E2664A',sealAlpha:0.16,brass:'#D4A94A',brassAlpha:0.14}}
}};
var THEME_ORDER = ['Midnight Ink', 'Chambers Green', 'Parchment Light', 'Frost Silver', 'Willow Light', 'Slate & Silver', 'Deep Burgundy'];
var THEME_STORAGE_KEY = 'dashboard_theme';

function hexToRgbTriplet(hex){{
  var h = hex.replace('#', '');
  var r = parseInt(h.substring(0, 2), 16);
  var g = parseInt(h.substring(2, 4), 16);
  var b = parseInt(h.substring(4, 6), 16);
  return r + ',' + g + ',' + b;
}}
function applyTheme(name){{
  var t = THEMES[name] || THEMES['Midnight Ink'];
  var root = document.documentElement.style;
  root.setProperty('--ink-900', t.ink900);
  root.setProperty('--ink-850', t.ink850);
  root.setProperty('--ink-800', t.ink800);
  root.setProperty('--ink-700', t.ink700);
  root.setProperty('--ink-650', t.ink650);
  root.setProperty('--line', t.line);
  root.setProperty('--line-soft', t.linesoft);
  root.setProperty('--parchment', t.parchment);
  root.setProperty('--parchment-dim', t.parchdim);
  root.setProperty('--parchment-faint', t.parchfaint);
  root.setProperty('--seal', t.seal);
  root.setProperty('--seal-soft', 'rgba(' + hexToRgbTriplet(t.seal) + ',' + t.sealAlpha + ')');
  root.setProperty('--seal-line', 'rgba(' + hexToRgbTriplet(t.seal) + ',0.45)');
  root.setProperty('--brass', t.brass);
  root.setProperty('--brass-soft', 'rgba(' + hexToRgbTriplet(t.brass) + ',' + t.brassAlpha + ')');
  root.setProperty('--brass-line', 'rgba(' + hexToRgbTriplet(t.brass) + ',0.5)');
}}
function saveTheme(name){{
  localStorage.setItem(THEME_STORAGE_KEY, name);
}}
function loadSavedTheme(){{
  var saved = localStorage.getItem(THEME_STORAGE_KEY);
  return (saved && THEMES[saved]) ? saved : 'Midnight Ink';
}}
function renderThemePanel(activeName){{
  var panel = document.getElementById('themePanel');
  panel.innerHTML = THEME_ORDER.map(function(name){{
    var t = THEMES[name];
    var activeCls = name === activeName ? ' active' : '';
    var dotStyle = 'background:linear-gradient(135deg,' + t.ink900 + ' 50%,' + t.brass + ' 50%);';
    return '<button class="theme-swatch-btn' + activeCls + '" data-theme-name="' + name + '">' +
      '<span class="theme-swatch-dot" style="' + dotStyle + '"></span><span>' + name + '</span></button>';
  }}).join('');
  panel.querySelectorAll('[data-theme-name]').forEach(function(btn){{
    btn.addEventListener('click', function(){{
      var name = btn.getAttribute('data-theme-name');
      applyTheme(name);
      saveTheme(name);
      renderThemePanel(name);
      document.getElementById('themePanel').style.display = 'none';
    }});
  }});
}}

applyTheme(loadSavedTheme());

var MATCHES = {matches_json};
var BOARD = {board_json};
var selectedPerson = null;
var selectedDate = null;

function esc(s){{ return String(s==null?'':s).replace(/[&<>"']/g,function(c){{return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];}}); }}
function todayIso(){{ var d=new Date(); return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'); }}
function daysInMonth(y,m){{ return new Date(y,m+1,0).getDate(); }}
function fmtDate(iso){{ return new Date(iso+'T00:00:00').toLocaleDateString('en-IN',{{day:'numeric',month:'short',year:'numeric'}}); }}
function fmtDateShort(iso){{ return new Date(iso+'T00:00:00').toLocaleDateString('en-IN',{{day:'numeric',month:'short'}}); }}
function daysAway(iso){{
  var d1=new Date(todayIso()+'T00:00:00'), d2=new Date(iso+'T00:00:00');
  return Math.round((d2-d1)/86400000);
}}
function daysAwayLabel(n){{
  if(n===0) return 'today';
  if(n===1) return 'tomorrow';
  if(n===-1) return 'yesterday';
  if(n>1) return 'in '+n+' days';
  return Math.abs(n)+' days ago';
}}

var calCursor = (function(){{
  var future = MATCHES.map(function(m){{return m.date;}}).filter(function(d){{return d && d>=todayIso();}}).sort();
  if (future.length) return new Date(future[0]+'T00:00:00');
  var any = MATCHES.map(function(m){{return m.date;}}).filter(Boolean).sort();
  if (any.length) return new Date(any[any.length-1]+'T00:00:00');
  return new Date();
}})();

function filtered(){{
  return selectedPerson ? MATCHES.filter(function(m){{return m.people && m.people.indexOf(selectedPerson)!==-1;}}) : MATCHES;
}}

function renderChips(){{
  var people = Array.from(new Set(MATCHES.reduce(function(acc,m){{return acc.concat(m.people||[]);}},[])));
  var box = document.getElementById('personChips');
  if (people.length < 2){{ box.style.display='none'; return; }}
  box.style.display='flex';
  var html = '<button class="chip-btn'+(!selectedPerson?' active':'')+'" data-p="">All advocates</button>';
  people.forEach(function(p){{
    html += '<button class="chip-btn'+(selectedPerson===p?' active':'')+'" data-p="'+esc(p)+'">'+esc(p)+'</button>';
  }});
  box.innerHTML = html;
  box.querySelectorAll('[data-p]').forEach(function(btn){{
    btn.addEventListener('click', function(){{
      selectedPerson = btn.getAttribute('data-p') || null;
      renderEverything();
    }});
  }});
}}

function statCardHtml(num, label, sub, hot){{
  return '<div class="stat-card'+(hot?' hot':'')+'"><div class="stat-num'+(hot?' hot':'')+'">'+esc(num)+'</div>'+
    '<div class="stat-label">'+esc(label)+'</div>'+(sub?'<div class="stat-sub">'+esc(sub)+'</div>':'')+'</div>';
}}

function renderStats(){{
  var list = filtered();
  var today = todayIso();
  var todayCount = list.filter(function(m){{return m.date===today;}}).length;
  var weekEnd = new Date(); weekEnd.setDate(weekEnd.getDate()+6);
  var weekEndIso = weekEnd.getFullYear()+'-'+String(weekEnd.getMonth()+1).padStart(2,'0')+'-'+String(weekEnd.getDate()).padStart(2,'0');
  var weekCount = list.filter(function(m){{return m.date && m.date>=today && m.date<=weekEndIso;}}).length;
  var future = list.map(function(m){{return m.date;}}).filter(function(d){{return d && d>=today;}}).sort();
  var next = future.length ? future[0] : null;

  var html = '';
  html += statCardHtml(todayCount, "Today", todayCount>0?'has a hearing':'', todayCount>0);
  html += statCardHtml(weekCount, 'Next 7 Days', '', false);
  html += statCardHtml(next?fmtDateShort(next):'\\u2014', 'Next Hearing', next?daysAwayLabel(daysAway(next)):'none scheduled', false);
  html += statCardHtml(list.length, 'Total Tracked', '', false);
  document.getElementById('statsRow').innerHTML = html;
}}

function docketHtml(e){{
  var personRow = e.person ? '<div><span>Advocate</span>'+esc(e.person)+'</div>' : '';
  var benchText = e.bench || '';
  if (e.benchType) benchText = (benchText ? benchText+' ' : '') + '('+e.benchType+')';
  var benchRow = benchText ? '<div><span>Bench</span>'+esc(benchText)+'</div>' : '';
  var listRow = e.listType ? '<div><span>List</span>'+esc(e.listType)+'</div>' : '';
  var caseNameLine = e.caseName ? '<div style="margin-bottom:8px;font-size:13px">'+esc(e.caseName)+'</div>' : '';
  return '<div class="docket"><div class="docket-meta">'+
    personRow+
    '<div><span>Court No</span>'+esc(e.court||'\\u2014')+'</div>'+
    '<div><span>Sr No</span>'+esc(e.sr||'\\u2014')+'</div>'+
    '<div><span>Case No</span>'+esc(e.caseNo||'\\u2014')+'</div>'+
    '<div><span>Date</span>'+esc(e.date||'\\u2014')+'</div>'+
    benchRow+listRow+
    '</div>'+caseNameLine+'<div class="snippet">'+esc(e.snippet||'')+'</div></div>';
}}

function renderCalendar(){{
  var y=calCursor.getFullYear(), m=calCursor.getMonth();
  document.getElementById('calTitle').textContent = calCursor.toLocaleDateString('en-IN',{{month:'long',year:'numeric'}});
  var counts = {{}};
  filtered().forEach(function(mt){{ if(mt.date) counts[mt.date]=(counts[mt.date]||0)+1; }});
  var first=new Date(y,m,1), startDow=first.getDay(), total=daysInMonth(y,m);
  var html='';
  ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].forEach(function(d){{ html+='<div class="cal-dow">'+d+'</div>'; }});
  for (var i=0;i<startDow;i++) html += '<div class="cal-cell empty"></div>';
  for (var d=1; d<=total; d++){{
    var iso=y+'-'+String(m+1).padStart(2,'0')+'-'+String(d).padStart(2,'0');
    var cnt=counts[iso]||0;
    var cls='cal-cell'+(cnt>0?' has-case':'')+(iso===todayIso()?' today':'')+(iso===selectedDate?' selected':'');
    html += '<div class="'+cls+'" data-day="'+iso+'">'+d+(cnt>0?'<span class="stamp">'+cnt+'</span>':'')+'</div>';
  }}
  document.getElementById('calGrid').innerHTML = html;
  document.querySelectorAll('[data-day]').forEach(function(cell){{
    cell.addEventListener('click', function(){{
      var iso = cell.getAttribute('data-day');
      var entries = filtered().filter(function(mt){{return mt.date===iso;}});
      if (!entries.length) return;
      selectedDate = iso;
      renderCalendar();
      renderAgenda();
    }});
  }});
}}

function groupByDate(list){{
  var map = {{}};
  list.forEach(function(m){{ if(!m.date) return; (map[m.date]=map[m.date]||[]).push(m); }});
  return map;
}}

function agendaGroupHtml(d, entries){{
  return '<div class="agenda-day-group"><div class="agenda-day-label"><span>'+esc(fmtDate(d))+'</span>'+
    '<span class="away">'+esc(daysAwayLabel(daysAway(d)))+'</span></div>'+
    entries.map(docketHtml).join('')+'</div>';
}}

function renderAgenda(){{
  var list = filtered();
  var body = document.getElementById('agendaBody');
  var title = document.getElementById('agendaTitle');
  var backBtn = document.getElementById('backToUpcoming');

  if (selectedDate){{
    title.textContent = fmtDate(selectedDate);
    backBtn.style.display = 'inline-block';
    var entries = list.filter(function(m){{return m.date===selectedDate;}});
    body.innerHTML = entries.length ? entries.map(docketHtml).join('') : '<div class="empty-state">No saved cases on this date.</div>';
    return;
  }}
  backBtn.style.display = 'none';
  var today = todayIso();
  var upcoming = list.filter(function(m){{return m.date && m.date>=today;}});
  var groups = groupByDate(upcoming);
  var dates = Object.keys(groups).sort();

  if (!dates.length){{
    var past = list.filter(function(m){{return m.date && m.date<today;}});
    var pgroups = groupByDate(past);
    var pdates = Object.keys(pgroups).sort().reverse().slice(0,5);
    if (!pdates.length){{
      title.textContent = 'Upcoming';
      body.innerHTML = '<div class="empty-state">No cases saved yet.</div>';
      return;
    }}
    title.textContent = 'No upcoming hearings \\u2014 recent';
    body.innerHTML = pdates.map(function(d){{return agendaGroupHtml(d, pgroups[d]);}}).join('');
    return;
  }}
  title.textContent = 'Upcoming';
  body.innerHTML = dates.slice(0,7).map(function(d){{return agendaGroupHtml(d, groups[d]);}}).join('');
}}

var TABLE_COLS = [
  {{key:'date', label:'Date'}},
  {{key:'court', label:'Court No'}},
  {{key:'sr', label:'Sr No'}},
  {{key:'caseNo', label:'Case No'}},
  {{key:'caseName', label:'Case Name'}},
  {{key:'person', label:'Advocate'}},
  {{key:'bench', label:'Bench'}}
];
var sortState = {{key:'date', dir:'desc'}};

function numOrText(v){{
  var n = parseFloat(v);
  return isNaN(n) ? null : n;
}}
function cmpBy(key, dir){{
  var mul = dir==='asc' ? 1 : -1;
  return function(a,b){{
    var av = a[key]||'', bv = b[key]||'';
    var an = numOrText(av), bn = numOrText(bv);
    if (an!==null && bn!==null) return (an-bn)*mul;
    return String(av).localeCompare(String(bv)) * mul;
  }};
}}

function renderTableHead(){{
  var html = TABLE_COLS.map(function(c){{
    var arrow = sortState.key===c.key ? (sortState.dir==='asc'?'&#9650;':'&#9660;') : '';
    return '<th data-sortkey="'+c.key+'">'+c.label+' <span class="arrow">'+arrow+'</span></th>';
  }}).join('');
  document.getElementById('tableHead').innerHTML = html;
  document.querySelectorAll('[data-sortkey]').forEach(function(th){{
    th.addEventListener('click', function(){{
      var k = th.getAttribute('data-sortkey');
      if (sortState.key===k) sortState.dir = sortState.dir==='asc' ? 'desc' : 'asc';
      else sortState = {{key:k, dir:'asc'}};
      renderTableHead();
      renderAllTable(document.getElementById('searchBox').value);
    }});
  }});
}}

function tableRowHtml(e){{
  return '<tr>'+
    '<td class="mono">'+esc(e.date||'\\u2014')+'</td>'+
    '<td class="mono">'+esc(e.court||'\\u2014')+'</td>'+
    '<td class="mono">'+esc(e.sr||'\\u2014')+'</td>'+
    '<td class="mono wrap-cell">'+esc(e.caseNo||'\\u2014')+'</td>'+
    '<td class="wrap-cell">'+esc(e.caseName||'\\u2014')+'</td>'+
    '<td>'+esc(e.person||'\\u2014')+'</td>'+
    '<td>'+esc(e.bench||'\\u2014')+'</td>'+
    '</tr>';
}}

function renderAllTable(q){{
  var list = filtered().slice();
  if (q){{
    q = q.toLowerCase();
    list = list.filter(function(e){{
      return ((e.court||'')+(e.sr||'')+(e.caseNo||'')+(e.caseName||'')+(e.date||'')+(e.snippet||'')+(e.person||'')+(e.bench||'')).toLowerCase().indexOf(q)!==-1;
    }});
  }}
  list.sort(cmpBy(sortState.key, sortState.dir));
  var body = document.getElementById('tableBody');
  body.innerHTML = list.length ? list.map(tableRowHtml).join('') :
    '<tr><td colspan="7"><div class="empty-state">No cases found.</div></td></tr>';
}}

function courtSortKey(e){{
  var n = parseFloat(e.court);
  return isNaN(n) ? 9999 : n;
}}
function srSortKey(e){{
  var n = parseFloat(e.sr);
  return isNaN(n) ? 9999 : n;
}}

function renderTodayWidget(){{
  var today = todayIso();
  var list = filtered().filter(function(m){{return m.date===today;}});
  list = list.slice().sort(function(a,b){{
    var c = courtSortKey(a)-courtSortKey(b);
    return c!==0 ? c : srSortKey(a)-srSortKey(b);
  }});
  document.getElementById('twCount').textContent = list.length;
  document.getElementById('twDot').className = 'tw-dot' + (list.length ? '' : ' idle');
  var body = document.getElementById('todayWidgetBody');
  if (!list.length){{
    body.innerHTML = '<div class="tw-empty">No hearings found for today.</div>';
    return;
  }}
  body.innerHTML = list.map(function(e){{
    var advLine = e.person ? '<div class="tw-adv">'+esc(e.person)+'</div>' : '';
    return '<div class="tw-row">'+
      '<div class="tw-sr">'+esc(e.sr||'\\u2014')+'</div>'+
      '<div class="tw-court">Crt<b>'+esc(e.court||'\\u2014')+'</b></div>'+
      '<div class="tw-case">'+esc(e.caseName||e.caseNo||'\\u2014')+advLine+'</div>'+
      '</div>';
  }}).join('');
}}

function renderBoard(){{
  var row = document.getElementById('boardRow');
  if (!BOARD || typeof BOARD !== 'object'){{ row.style.display = 'none'; return; }}
  var wings = Object.keys(BOARD);
  if (!wings.length){{ row.style.display = 'none'; return; }}
  row.style.display = 'grid';
  row.innerHTML = wings.map(function(name){{
    var w = BOARD[name];
    var badge = w.idle
      ? '<span class="wing-badge idle">No cases now</span>'
      : '<span class="wing-badge active">Live</span>';
    var body = '';
    if (!w.idle && w.courts && w.courts.length){{
      body += w.courts.map(function(c){{
        return '<div class="board-court-row"><span>Court <b>'+esc(c.court)+'</b></span><span>Now on item <b>'+esc(c.item)+'</b></span></div>';
      }}).join('');
    }} else if (!w.idle && w.raw_status_rows && w.raw_status_rows.length){{
      body += w.raw_status_rows.map(function(l){{ return '<div class="board-court-row">'+esc(l)+'</div>'; }}).join('');
    }} else if (w.idle) {{
      body += '<div class="board-empty">No courts currently in session on this board.</div>';
    }}
    if (w.messages && w.messages.length){{
      body += w.messages.map(function(m){{
        return '<div class="board-msg">'+esc(m.text)+'</div>';
      }}).join('');
    }}
    return '<div class="card wing-card"><h3>'+esc(name)+' '+badge+'</h3>'+body+
      '<div class="board-stale-note">From the High Court\\'s live display board \\u2014 updates whenever this dashboard is regenerated.</div></div>';
  }}).join('');
}}

var GH_OWNER = 'insim24';
var GH_REPO = 'Cause-List---Watcher';
var GH_WORKFLOW = 'watch.yml';
var GH_BRANCH = 'main';
var GH_API = 'https://api.github.com';
var GH_OAUTH_CLIENT_ID = 'Ov23li1if38IxNLXEcFz';
var OAUTH_REDIRECT_URI = 'https://insim24.github.io/Cause-List---Watcher/causelist_dashboard.html';
var OAUTH_EXCHANGE_URL = 'https://causelist-watcher-oauth.vercel.app/api/github-oauth-exchange';

function ghToken(){{ return localStorage.getItem('gh_pat') || ''; }}
function setGhToken(t){{ if (t) localStorage.setItem('gh_pat', t); }}
function clearGhToken(){{ localStorage.removeItem('gh_pat'); }}
function ensureGhToken(){{
  return ghToken() || null;
}}
function randomOauthState(){{
  var arr = new Uint8Array(16);
  crypto.getRandomValues(arr);
  return Array.prototype.map.call(arr, function(b){{ return b.toString(16).padStart(2, '0'); }}).join('');
}}
function startGithubSignIn(pendingFetch){{
  var state = randomOauthState();
  sessionStorage.setItem('gh_oauth_state', state);
  sessionStorage.setItem('gh_oauth_pending_fetch', pendingFetch ? '1' : '');
  ghStatus('Redirecting to GitHub to sign in\\u2026', '');
  var qs = 'client_id=' + encodeURIComponent(GH_OAUTH_CLIENT_ID) +
    '&scope=' + encodeURIComponent('public_repo,workflow') +
    '&redirect_uri=' + encodeURIComponent(OAUTH_REDIRECT_URI) +
    '&state=' + encodeURIComponent(state);
  window.location.href = 'https://github.com/login/oauth/authorize?' + qs;
}}
function promptForManualToken(){{
  var t = window.prompt('Paste a GitHub personal access token to trigger a fetch.\\n\\nNeeds "repo" + "workflow" scope (classic token), or Actions:write + Contents:read (fine-grained, scoped to this repo).\\n\\nStored ONLY in this browser\\'s local storage \\u2014 never written into this file or committed anywhere.');
  if (t){{
    setGhToken(t.trim());
    triggerFetch();
  }}
}}
function completeGithubOauthIfNeeded(){{
  var params = new URLSearchParams(window.location.search);
  var code = params.get('code');
  var state = params.get('state');
  if (!code || !state) return;

  var expectedState = sessionStorage.getItem('gh_oauth_state') || '';
  sessionStorage.removeItem('gh_oauth_state');
  var pendingFetch = sessionStorage.getItem('gh_oauth_pending_fetch') === '1';
  sessionStorage.removeItem('gh_oauth_pending_fetch');

  var cleanUrl = window.location.origin + window.location.pathname;
  window.history.replaceState({{}}, document.title, cleanUrl);

  if (state !== expectedState){{
    ghStatus('Sign-in failed: state mismatch (possible CSRF). Please try again.', 'err');
    return;
  }}

  ghStatus('Finishing sign-in\\u2026', '');
  fetch(OAUTH_EXCHANGE_URL, {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{code: code}})
  }}).then(function(resp){{
    return resp.json().then(function(data){{
      if (!resp.ok || data.error){{
        throw new Error(data.error || ('exchange failed with status ' + resp.status));
      }}
      return data;
    }});
  }}).then(function(data){{
    setGhToken(data.access_token);
    ghStatus('Signed in.', 'ok');
    if (pendingFetch){{
      triggerFetch();
    }}
  }}).catch(function(err){{
    ghStatus('Sign-in error: ' + err.message, 'err');
  }});
}}
function ghStatus(msg, kind, link){{
  var el = document.getElementById('fetchStatus');
  el.textContent = msg;
  el.className = 'fetch-status' + (kind ? ' ' + kind : '');
  if (link){{
    var a = document.createElement('a');
    a.href = link; a.target = '_blank'; a.rel = 'noopener'; a.textContent = 'View run on GitHub';
    el.appendChild(document.createTextNode(' '));
    el.appendChild(a);
  }}
}}
function ghApi(path, opts){{
  opts = opts || {{}};
  var headers = opts.headers || {{}};
  headers['Authorization'] = 'Bearer ' + ghToken();
  headers['Accept'] = 'application/vnd.github+json';
  opts.headers = headers;
  return fetch(GH_API + path, opts);
}}
function b64ToUtf8(b64){{
  var binary = atob(b64.replace(/\\n/g, ''));
  var bytes = new Uint8Array(binary.length);
  for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new TextDecoder('utf-8').decode(bytes);
}}
function fetchRepoJson(path){{
  return ghApi('/repos/' + GH_OWNER + '/' + GH_REPO + '/contents/' + path + '?ref=' + GH_BRANCH)
    .then(function(resp){{
      if (!resp.ok) throw new Error('Could not read ' + path + ' (status ' + resp.status + ')');
      return resp.json();
    }})
    .then(function(data){{ return JSON.parse(b64ToUtf8(data.content)); }});
}}
function pollForRun(afterMs, attempt){{
  attempt = attempt || 0;
  if (attempt > 30) return Promise.reject(new Error('Timed out waiting for the run to appear in the Actions list.'));
  return ghApi('/repos/' + GH_OWNER + '/' + GH_REPO + '/actions/workflows/' + GH_WORKFLOW + '/runs?event=workflow_dispatch&per_page=5')
    .then(function(resp){{ return resp.json(); }})
    .then(function(data){{
      var runs = (data.workflow_runs || []).filter(function(r){{ return new Date(r.created_at).getTime() >= afterMs - 5000; }});
      if (runs.length) return runs[runs.length - 1];
      return new Promise(function(resolve){{ setTimeout(resolve, 4000); }}).then(function(){{ return pollForRun(afterMs, attempt + 1); }});
    }});
}}
function pollRunUntilDone(run, attempt){{
  attempt = attempt || 0;
  if (run.status === 'completed') return run;
  if (attempt > 60) return Promise.reject(new Error('Timed out waiting for the run to finish.'));
  ghStatus('Run is ' + run.status + '\\u2026', '');
  return new Promise(function(resolve){{ setTimeout(resolve, 5000); }})
    .then(function(){{ return ghApi('/repos/' + GH_OWNER + '/' + GH_REPO + '/actions/runs/' + run.id); }})
    .then(function(resp){{ return resp.json(); }})
    .then(function(fresh){{ return pollRunUntilDone(fresh, attempt + 1); }});
}}
function refreshDataFromRepo(){{
  return fetchRepoJson('cases_auto.json').then(function(matches){{
    MATCHES = matches;
    return fetchRepoJson('display_board.json').catch(function(){{ return null; }});
  }}).then(function(board){{
    BOARD = board || {{}};
    renderEverything();
    var lc = document.getElementById('lastChecked');
    if (lc) lc.textContent = 'fetched just now via GitHub Actions';
    ghStatus('Done \\u2014 dashboard updated with the latest data.', 'ok');
  }});
}}
function triggerFetch(){{
  var token = ensureGhToken();
  if (!token){{ startGithubSignIn(true); return; }}
  var btn = document.getElementById('fetchBtn');
  btn.disabled = true;
  var startedAt = Date.now();
  ghStatus('Triggering a fresh fetch\\u2026', '');
  ghApi('/repos/' + GH_OWNER + '/' + GH_REPO + '/actions/workflows/' + GH_WORKFLOW + '/dispatches', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ref: GH_BRANCH}})
  }}).then(function(resp){{
    if (resp.status === 401 || resp.status === 403){{
      clearGhToken();
      throw new Error('That token was rejected (status ' + resp.status + '). Click Fetch Now again to re-enter it.');
    }}
    if (resp.status !== 204){{
      throw new Error('GitHub returned status ' + resp.status + ' when triggering the workflow.');
    }}
    ghStatus('Triggered \\u2014 waiting for the run to start\\u2026', '');
    return pollForRun(startedAt);
  }}).then(function(run){{
    return pollRunUntilDone(run);
  }}).then(function(run){{
    if (!run) return;
    if (run.conclusion !== 'success'){{
      ghStatus('Run finished with status: ' + run.conclusion + '.', 'err', run.html_url);
      return;
    }}
    ghStatus('Run succeeded \\u2014 pulling fresh data\\u2026', '');
    return refreshDataFromRepo();
  }}).catch(function(err){{
    ghStatus('Error: ' + err.message, 'err');
  }}).then(function(){{
    btn.disabled = false;
  }});
}}

function renderEverything(){{
  renderChips();
  renderStats();
  renderBoard();
  renderCalendar();
  renderAgenda();
  renderTodayWidget();
  renderTableHead();
  renderAllTable(document.getElementById('searchBox').value);
}}

document.getElementById('twToggle').addEventListener('click', function(e){{
  e.stopPropagation();
  document.getElementById('todayWidget').classList.toggle('collapsed');
  this.innerHTML = document.getElementById('todayWidget').classList.contains('collapsed') ? '&#9633;' : '&#8722;';
}});
document.getElementById('twHead').addEventListener('click', function(){{
  document.getElementById('todayWidget').classList.toggle('collapsed');
  document.getElementById('twToggle').innerHTML =
    document.getElementById('todayWidget').classList.contains('collapsed') ? '&#9633;' : '&#8722;';
}});
document.querySelectorAll('[data-calnav]').forEach(function(btn){{
  btn.addEventListener('click', function(){{
    var dir = btn.getAttribute('data-calnav')==='prev' ? -1 : 1;
    calCursor = new Date(calCursor.getFullYear(), calCursor.getMonth()+dir, 1);
    renderCalendar();
  }});
}});
document.getElementById('todayBtn').addEventListener('click', function(){{
  calCursor = new Date();
  selectedDate = todayIso();
  renderCalendar();
  renderAgenda();
}});
document.getElementById('backToUpcoming').addEventListener('click', function(){{
  selectedDate = null;
  renderCalendar();
  renderAgenda();
}});
document.getElementById('searchBox').addEventListener('input', function(e){{ renderAllTable(e.target.value); }});
document.getElementById('fetchBtn').addEventListener('click', triggerFetch);
document.getElementById('manualTokenLink').addEventListener('click', function(e){{
  e.preventDefault();
  promptForManualToken();
}});
document.getElementById('themeGearBtn').addEventListener('click', function(e){{
  e.stopPropagation();
  var panel = document.getElementById('themePanel');
  panel.style.display = panel.style.display === 'none' ? 'flex' : 'none';
}});
document.addEventListener('click', function(e){{
  var panel = document.getElementById('themePanel');
  var gear = document.getElementById('themeGearBtn');
  if (panel.style.display !== 'none' && !panel.contains(e.target) && e.target !== gear){{
    panel.style.display = 'none';
  }}
}});
renderThemePanel(loadSavedTheme());

completeGithubOauthIfNeeded();
renderEverything();
</script>
</body>
</html>
"""


def render_dashboard(matches, name, source_note="run manually or on a schedule", board=None):
    return TEMPLATE.format(
        name=_html.escape(name or "Your cases"),
        generated_at=datetime.now().strftime("%d %b %Y, %I:%M %p"),
        count=len(matches),
        matches_json=json.dumps(matches),
        board_json=json.dumps(board or {}),
        source_note=_html.escape(source_note),
    )
