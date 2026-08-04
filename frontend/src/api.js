const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });

  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    const message = payload?.detail?.message || payload?.detail || payload?.message || `Request failed (${response.status})`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return payload;
}

export const api = {
  chat: (body) => request('/chat', { method: 'POST', body: JSON.stringify(body) }),
  approve: (sessionId, approved) => request('/approve', {
    method: 'POST', body: JSON.stringify({ session_id: sessionId, approved }),
  }),
  trace: (sessionId) => request(`/trace/${encodeURIComponent(sessionId)}`),
  setSpend: (sessionId, dollars) => request('/debug/set-spend', {
    method: 'POST', body: JSON.stringify({ session_id: sessionId, dollars: Number(dollars) }),
  }),
  endChat: (sessionId) => request('/end-chat', {
    method: 'POST', body: JSON.stringify({ session_id: sessionId }),
  }),
  deleteSession: (sessionId) => request(`/session/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),
};
