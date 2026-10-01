const { findCourtForm, parseTables, parseLegend, pageNotice } = require('./_court-list-parser.js');

const ALLOWED_ORIGIN = 'https://insim24.github.io';
const BOARD_URL = 'https://jkhc.gov.in/dis/';
const ALLOWED_HOST = 'jkhc.gov.in';
const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
};

function setCorsHeaders(res) {
  res.setHeader('Access-Control-Allow-Origin', ALLOWED_ORIGIN);
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
}

// Minimal cookie jar: the board's CSRF token is tied to its session cookie,
// so the cookies from loading the board must go back with the form post.
function collectCookies(resp, jar) {
  const list = typeof resp.headers.getSetCookie === 'function' ? resp.headers.getSetCookie() : [];
  for (const c of list) {
    const pair = c.split(';')[0];
    const eq = pair.indexOf('=');
    if (eq > 0) jar[pair.slice(0, eq).trim()] = pair.slice(eq + 1).trim();
  }
}

function cookieHeader(jar) {
  return Object.keys(jar).map((k) => k + '=' + jar[k]).join('; ');
}

module.exports = async (req, res) => {
  setCorsHeaders(res);

  if (req.method === 'OPTIONS') {
    res.status(204).end();
    return;
  }

  if (req.method !== 'GET') {
    res.status(405).json({ error: 'method not allowed' });
    return;
  }

  const wing = String((req.query && req.query.wing) || '').slice(0, 60);
  const court = String((req.query && req.query.court) || '').trim();
  if (!/^[0-9A-Za-z-]{1,8}$/.test(court)) {
    res.status(400).json({ error: 'invalid court number' });
    return;
  }

  try {
    const jar = {};
    const boardResp = await fetch(BOARD_URL, { headers: HEADERS });
    if (!boardResp.ok) {
      res.status(502).json({ error: 'board returned status ' + boardResp.status });
      return;
    }
    collectCookies(boardResp, jar);
    const boardHtml = await boardResp.text();

    const form = findCourtForm(boardHtml, wing, court);
    if (!form) {
      res.status(404).json({ error: 'Court ' + court + ' is not on the live board right now (it may have risen for the day).' });
      return;
    }

    const target = new URL(form.action || BOARD_URL, BOARD_URL);
    if (target.hostname !== ALLOWED_HOST) {
      res.status(502).json({ error: 'unexpected form target' });
      return;
    }

    const body = new URLSearchParams(form.fields);
    const headers = Object.assign({}, HEADERS, { 'Referer': BOARD_URL, 'Origin': 'https://' + ALLOWED_HOST });
    if (Object.keys(jar).length) headers['Cookie'] = cookieHeader(jar);

    let detailResp;
    if (form.method === 'POST') {
      headers['Content-Type'] = 'application/x-www-form-urlencoded';
      detailResp = await fetch(target, { method: 'POST', headers, body: body.toString() });
    } else {
      body.forEach((v, k) => target.searchParams.append(k, v));
      detailResp = await fetch(target, { headers });
    }

    if (!detailResp.ok) {
      res.status(502).json({ error: 'court page returned status ' + detailResp.status });
      return;
    }

    const detailHtml = await detailResp.text();
    const notice = pageNotice(detailHtml);
    const tables = parseTables(detailHtml);

    if (!tables.length && /csrf|mention all field/i.test(notice)) {
      console.error('court-list rejected by upstream:', notice);
      res.status(502).json({ error: 'The High Court site rejected the request: ' + notice });
      return;
    }

    res.setHeader('Cache-Control', 's-maxage=30, stale-while-revalidate=60');
    res.status(200).json({ wing, court, notice, tables, legend: parseLegend(detailHtml), source: target.toString() });
  } catch (err) {
    console.error('court-list fetch failed:', err);
    res.status(502).json({ error: 'fetch failed' });
  }
};
