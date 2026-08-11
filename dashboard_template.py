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
<meta name="viewport" content="width=device-width, initial-scale=1" />
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
  .stamp{{position:absolute;top:2px;right:2px;background:var(--seal);color:var(--parchment);
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
  td.wrap-cell{{max-width:260px;}}

  @media (max-width:1180px){{
    #todayWidget{{position:static;width:auto;max-height:none;margin-bottom:20px;box-shadow:var(--shadow);}}
    #todayWidgetBody{{max-height:280px;}}
  }}
  @media (max-width:900px){{
    .main-grid{{grid-template-columns:1fr;}}
    .stats-row{{grid-template-columns:repeat(2,1fr);}}
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
        <p class="hero-sub">{name} &middot; last checked {generated_at}</p>
      </div>
    </div>
    <div class="chip-row" id="personChips"></div>
  </div>

  <div class="stats-row" id="statsRow"></div>

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
var MATCHES = {matches_json};
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
  return selectedPerson ? MATCHES.filter(function(m){{return m.person===selectedPerson;}}) : MATCHES;
}}

function renderChips(){{
  var people = Array.from(new Set(MATCHES.map(function(m){{return m.person;}}).filter(Boolean)));
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

function renderEverything(){{
  renderChips();
  renderStats();
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

renderEverything();
</script>
</body>
</html>
"""


def render_dashboard(matches, name, source_note="run manually or on a schedule"):
    return TEMPLATE.format(
        name=_html.escape(name or "Your cases"),
        generated_at=datetime.now().strftime("%d %b %Y, %I:%M %p"),
        count=len(matches),
        matches_json=json.dumps(matches),
        source_note=_html.escape(source_note),
    )
