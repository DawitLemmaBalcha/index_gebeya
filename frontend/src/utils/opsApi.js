// NB-49: the single fetch wrapper for the ops console.
// Same-origin (Caddy routes /ops/* to the API, D13), cookies flow
// automatically. Non-2xx -> thrown Error with the backend detail;
// 401 -> dispatches 'ops:unauthorized' so useOpsAuth flips to the
// login state (every section reacts without bespoke handling).

export async function opsFetch(path, { method = 'GET', body, headers = {} } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error('Network error — is the API reachable?');
  }

  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent('ops:unauthorized'));
    const detail = await res.json().then((d) => d?.detail).catch(() => null);
    throw new Error(detail || 'Not authenticated');
  }

  if (!res.ok) {
    const detail = await res.json().then((d) => d?.detail).catch(() => null);
    throw new Error(detail || `Request failed (${res.status})`);
  }

  return res.json();
}
