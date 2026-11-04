/* The browser keeps only an anonymous visitor ID. No API keys live here. */
const sessionKey = "nightfind-session";
let sessionId;
try {
  sessionId = localStorage.getItem(sessionKey);
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem(sessionKey, sessionId);
  }
} catch {
  sessionId = `nf-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export async function request(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "X-Session": sessionId, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败，请稍后重试。");
  return data;
}
