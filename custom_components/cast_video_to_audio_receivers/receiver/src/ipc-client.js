/**
 * HTTP client for Home Assistant IPC endpoints.
 */

async function postToHa(haUrl, path, body) {
  const url = `${haUrl.replace(/\/$/, '')}${path}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HA IPC ${response.status}: ${text}`);
  }

  return response.json();
}

module.exports = { postToHa };
