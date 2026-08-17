const { parseDisplayBoard } = require('./_display-board-parser.js');

const ALLOWED_ORIGIN = 'https://insim24.github.io';
const SOURCE_URL = 'https://jkhc.gov.in/dis/';

function setCorsHeaders(res) {
  res.setHeader('Access-Control-Allow-Origin', ALLOWED_ORIGIN);
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
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

  try {
    const upstream = await fetch(SOURCE_URL, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      },
    });

    if (!upstream.ok) {
      res.status(502).json({ error: 'upstream returned status ' + upstream.status });
      return;
    }

    const html = await upstream.text();
    const board = parseDisplayBoard(html);

    res.setHeader('Cache-Control', 's-maxage=15, stale-while-revalidate=30');
    res.status(200).json(board);
  } catch (err) {
    console.error('display-board fetch failed:', err);
    res.status(502).json({ error: 'fetch failed' });
  }
};
