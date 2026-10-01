/*
 * Helpers for drilling into one court from the live Digital Display Board.
 *
 * On the board, each court number is a submit button inside its own
 * <form method="post" action="...">, alongside hidden inputs (branch/wing and
 * a CSRF token tied to the board's session cookie). Posting that form returns
 * a page listing the court's cases for the day. The token and field names are
 * whatever the board renders at the time, so rather than hard-coding them this
 * copies every input of the matching form verbatim.
 */

const { decodeEntities, cellText } = require('./_display-board-parser.js');

function attr(tagHtml, name) {
  const re = new RegExp('\\b' + name + '\\s*=\\s*(?:"([^"]*)"|\'([^\']*)\'|([^\\s>]+))', 'i');
  const m = re.exec(tagHtml);
  if (!m) return null;
  return decodeEntities(m[1] != null ? m[1] : m[2] != null ? m[2] : m[3]);
}

// Returns [{wing, html}] for each <div class="wing"> block on the board.
function splitWings(html) {
  const wings = [];
  const wingRe = /<div class="wing">([\s\S]*?)<\/table>\s*<\/div>/g;
  let m;
  while ((m = wingRe.exec(html)) !== null) {
    const firstRow = /<tr>([\s\S]*?)<\/tr>/.exec(m[1]);
    wings.push({ wing: firstRow ? cellText(firstRow[1]) : '', html: m[1] });
  }
  return wings;
}

// Finds the form whose roomno button matches `court` inside `wingName`
// (case-insensitive; falls back to any wing when the name doesn't match).
// Returns {action, method, fields: [[name, value], ...]} or null.
function findCourtForm(html, wingName, court) {
  const wings = splitWings(html);
  const wanted = String(wingName || '').trim().toLowerCase();
  const ordered = wings.filter((w) => w.wing.toLowerCase() === wanted)
    .concat(wings.filter((w) => w.wing.toLowerCase() !== wanted));

  for (const w of ordered) {
    const formRe = /<form\b[^>]*>[\s\S]*?<\/form>/gi;
    let fm;
    while ((fm = formRe.exec(w.html)) !== null) {
      const formHtml = fm[0];
      const inputs = formHtml.match(/<input\b[^>]*>/gi) || [];
      const fields = [];
      let matches = false;
      for (const tag of inputs) {
        const name = attr(tag, 'name');
        if (!name) continue;
        const value = (attr(tag, 'value') || '').trim();
        if (name.toLowerCase() === 'roomno' && value === String(court).trim()) matches = true;
        fields.push([name, value]);
      }
      if (!matches) continue;
      const openTag = /<form\b[^>]*>/i.exec(formHtml)[0];
      return {
        action: attr(openTag, 'action') || '',
        method: (attr(openTag, 'method') || 'get').toUpperCase(),
        fields,
      };
    }
  }
  return null;
}

// Case-status colours, as set by the court page's own legend
// (<div id="rectangle" style="background:#xxx">Label.</div>). Each case row
// carries one of these as an inline style="background:#xxx" on its <tr>;
// there is no status text or class. These are the fallback when the legend
// can't be read; whatever the legend says wins.
const KNOWN_STATUS_COLORS = {
  '#ebacac': 'disposed',
  '#dfefff': 'to_be_heard',
  '#e8e8e8': 'hearing_complete',
};

function statusFromLabel(label) {
  const l = String(label || '').toLowerCase();
  if (/dispos/.test(l)) return 'disposed';
  if (/to be heard/.test(l)) return 'to_be_heard';
  if (/hearing complete/.test(l)) return 'hearing_complete';
  return '';
}

function normColor(c) {
  const m = /#([0-9a-f]{6}|[0-9a-f]{3})(?![0-9a-f])/i.exec(String(c || ''));
  if (!m) return '';
  let h = m[1].toLowerCase();
  if (h.length === 3) h = h.split('').map((x) => x + x).join('');
  return '#' + h;
}

function backgroundOf(tagHtml) {
  const style = attr(tagHtml, 'style') || '';
  const m = /background(?:-color)?\s*:\s*([^;]+)/i.exec(style);
  return m ? normColor(m[1]) : '';
}

// Returns [{status, label, color}] from the legend boxes at the top of the page.
function parseLegend(html) {
  const legend = [];
  const re = /<div\b[^>]*id\s*=\s*"rectangle"[^>]*>([\s\S]*?)<\/div>/gi;
  let m;
  while ((m = re.exec(html)) !== null) {
    const label = cellText(m[1]).replace(/\.$/, '');
    const color = backgroundOf(/<div\b[^>]*>/i.exec(m[0])[0]);
    if (label && color) legend.push({ status: statusFromLabel(label), label, color });
  }
  return legend;
}

// Court page dates are DD/MM/YYYY; 01/01/5000 is the site's "no date set".
function isoFromCourtDate(s) {
  const m = /(\d{1,2})\/(\d{1,2})\/(\d{4})/.exec(String(s || ''));
  if (!m || Number(m[3]) >= 3000) return '';
  return m[3] + '-' + m[2].padStart(2, '0') + '-' + m[1].padStart(2, '0');
}

// A cell's text, or for the case-number cell (a submit button inside a form)
// the button's label.
function cellValue(cellHtml) {
  const text = cellText(cellHtml);
  if (text) return text;
  const btn = /<input\b[^>]*type\s*=\s*"?submit"?[^>]*>/i.exec(cellHtml);
  return btn ? (attr(btn[0], 'value') || '').trim() : '';
}

// Turns every <table> on the court's page into rows of cell text.
// Each row is {header: bool, cells: [...]}; empty rows are dropped. Case rows
// (Sr No first) also get {sr, caseNo, title, nextDate, nextDateRaw, section,
// status, color}. The legend table itself is left out (see parseLegend).
function parseTables(html) {
  const legend = parseLegend(html);
  const colorStatus = Object.assign({}, KNOWN_STATUS_COLORS);
  legend.forEach((l) => { if (l.status) colorStatus[l.color] = l.status; });

  const tables = [];
  const tableRe = /<table\b[\s\S]*?<\/table>/gi;
  let tm;
  while ((tm = tableRe.exec(html)) !== null) {
    if (/id\s*=\s*"rectangle"/i.test(tm[0])) continue;
    const rows = [];
    let section = '';
    const rowRe = /<tr\b[\s\S]*?<\/tr>/gi;
    let rm;
    while ((rm = rowRe.exec(tm[0])) !== null) {
      const cellTags = rm[0].match(/<t[hd]\b[\s\S]*?<\/t[hd]>/gi) || [];
      const cells = cellTags.map(cellValue);
      if (!cells.some(Boolean)) continue;
      const header = cellTags.every((c) => /^<th/i.test(c) || /class\s*=\s*"td_head"/i.test(c));
      const row = { header, cells };
      if (header) {
        const list = /CAUSELIST\s*:\s*(.+?)\s*CAUSELIST/i.exec(cells.join(' '));
        if (list) section = list[1].trim().toLowerCase().replace(/(^|-)\w/g, (c) => c.toUpperCase());
      } else if (/^\d+$/.test(cells[0] || '') && cells.length >= 4) {
        const color = backgroundOf(/<tr\b[^>]*>/i.exec(rm[0])[0]);
        row.sr = cells[0];
        row.caseNo = cells[1];
        row.title = cells[2];
        row.nextDateRaw = cells[cells.length - 1];
        row.nextDate = isoFromCourtDate(row.nextDateRaw);
        row.section = section;
        row.color = color;
        row.status = colorStatus[color] || '';
      }
      rows.push(row);
    }
    if (rows.length) tables.push({ rows });
  }
  return tables;
}

// Visible text outside tables, e.g. headings or "Invalid CSRF token" notices.
function pageNotice(html) {
  const body = /<body\b[^>]*>([\s\S]*)<\/body>/i.exec(html);
  let text = (body ? body[1] : html)
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<table\b[\s\S]*?<\/table>/gi, ' ')
    .replace(/<footer[\s\S]*?<\/footer>/gi, ' ');
  return cellText(text);
}

module.exports = { findCourtForm, parseTables, parseLegend, pageNotice, splitWings, isoFromCourtDate };
