const ALLOWED_ORIGIN = 'https://insim24.github.io';
const REDIRECT_URI = 'https://insim24.github.io/Cause-List---Watcher/causelist_dashboard.html';

function setCorsHeaders(res) {
  res.setHeader('Access-Control-Allow-Origin', ALLOWED_ORIGIN);
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

module.exports = async (req, res) => {
  setCorsHeaders(res);

  if (req.method === 'OPTIONS') {
    res.status(204).end();
    return;
  }

  if (req.method !== 'POST') {
    res.status(405).json({ error: 'method not allowed' });
    return;
  }

  try {
    const body = req.body && typeof req.body === 'object' ? req.body : JSON.parse(req.body || '{}');
    const code = body.code;
    if (!code) {
      res.status(400).json({ error: 'missing code' });
      return;
    }

    const ghResp = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({
        client_id: process.env.GITHUB_OAUTH_CLIENT_ID,
        client_secret: process.env.GITHUB_OAUTH_CLIENT_SECRET,
        code: code,
        redirect_uri: REDIRECT_URI,
      }),
    });

    const data = await ghResp.json();

    if (data.error) {
      res.status(400).json({ error: data.error_description || data.error });
      return;
    }

    res.status(200).json({ access_token: data.access_token });
  } catch (err) {
    console.error('github-oauth-exchange failed:', err);
    res.status(500).json({ error: 'exchange failed' });
  }
};
