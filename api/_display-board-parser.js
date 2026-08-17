/*
 * Parses the J&K High Court's live Digital Display Board
 * (https://jkhc.gov.in/dis/) into { wingName: {idle, courts, raw_status_rows,
 * messages} }.
 *
 * The board renders each wing as a <div class="wing"><table class="my_table">
 * with rows: a title row (<th colspan="3">Wing Name</th>), a column-header
 * row (COURT NO / CORAM / SR NO), then either data rows (court number is
 * inside a hidden <input name="roomno" value="..."> submit button, not plain
 * text) or a single "No Cases To Display" row, then a "Messages" title row
 * followed by id/text rows. This mirrors that structure directly rather than
 * flattening to text first, since the court number isn't reachable that way.
 */

function decodeEntities(s) {
  return s
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#0*39;/g, "'")
    .replace(/&#x27;/gi, "'");
}

function cellText(html) {
  return decodeEntities(html.replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim();
}

function extractTdCells(rowHtml) {
  return rowHtml.match(/<td[\s\S]*?<\/td>/g) || [];
}

function courtNumberFromCell(cellHtml) {
  const inputTag = /<input\b[^>]*name="roomno"[^>]*>/.exec(cellHtml);
  if (inputTag) {
    const val = /value="([^"]*)"/.exec(inputTag[0]);
    if (val && val[1].trim()) return val[1].trim();
  }
  return cellText(cellHtml);
}

function parseDisplayBoard(html) {
  const result = {};
  const wingRe = /<div class="wing">([\s\S]*?)<\/table>\s*<\/div>/g;
  let wingMatch;

  while ((wingMatch = wingRe.exec(html)) !== null) {
    const chunk = wingMatch[1];
    const rows = chunk.match(/<tr>([\s\S]*?)<\/tr>/g) || [];
    if (!rows.length) continue;

    const wingName = cellText(rows[0]);
    let section = 'courts';
    const courts = [];
    const messages = [];
    const rawStatusRows = [];
    let idle = false;

    for (let i = 1; i < rows.length; i++) {
      const rowHtml = rows[i];
      if (/<th/.test(rowHtml)) {
        if (cellText(rowHtml).toLowerCase() === 'messages') section = 'messages';
        continue;
      }
      const cells = extractTdCells(rowHtml);
      if (!cells.length) continue;

      if (section === 'courts') {
        if (cells.length === 1) {
          if (cellText(cells[0]).toLowerCase() === 'no cases to display') idle = true;
          continue;
        }
        if (cells.length === 3) {
          const court = courtNumberFromCell(cells[0]);
          const coram = cellText(cells[1]);
          const item = cellText(cells[2]);
          if (court) courts.push({ court, item, coram });
          continue;
        }
        rawStatusRows.push(cellText(rowHtml));
      } else if (cells.length >= 2) {
        const id = cellText(cells[0]);
        const text = cellText(cells[1]);
        if (text) messages.push({ id, text });
      }
    }

    result[wingName] = { idle, courts, raw_status_rows: rawStatusRows, messages };
  }

  return result;
}

module.exports = { parseDisplayBoard };
