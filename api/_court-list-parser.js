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

// Turns every <table> on the court's page into rows of cell text.
// Each row is {header: bool, cells: [...]}; empty rows are dropped.
function parseTables(html) {
  const tables = [];
  const tableRe = /<table\b[\s\S]*?<\/table>/gi;
  let tm;
  while ((tm = tableRe.exec(html)) !== null) {
    const rows = [];
    const rowRe = /<tr\b[\s\S]*?<\/tr>/gi;
    let rm;
    while ((rm = rowRe.exec(tm[0])) !== null) {
      const cellTags = rm[0].match(/<t[hd]\b[\s\S]*?<\/t[hd]>/gi) || [];
      const cells = cellTags.map(cellText);
      if (!cells.some(Boolean)) continue;
      rows.push({ header: cellTags.every((c) => /^<th/i.test(c)), cells });
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

module.exports = { findCourtForm, parseTables, pageNotice, splitWings };
