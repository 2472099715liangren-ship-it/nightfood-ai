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
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      signal: controller.signal,
      headers: { "X-Session": sessionId, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("服务响应暂时无法读取，请重试。");
    }
    if (!response.ok) throw new Error(data.error || "请求失败，请稍后重试。");
    return data;
  } catch (error) {
    if (error.name === "AbortError")
      throw new Error("查询超时，已保留用餐需求，可以重试。");
    if (error instanceof TypeError)
      throw new Error("连接失败，请确认夜寻仍在运行后重试。");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
