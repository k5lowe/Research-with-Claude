// Service worker: fetches Yahoo chart data on behalf of the content script.
// Runs with host_permissions, so it is not blocked by page CORS — and because
// the request comes from the user's real browser, Yahoo serves it normally
// (unlike server-side scrapers, which get blocked).

const CHART_HOSTS = [
  "https://query1.finance.yahoo.com",
  "https://query2.finance.yahoo.com",
];

async function fetchChart(symbol, interval, range) {
  const path =
    `/v8/finance/chart/${encodeURIComponent(symbol)}` +
    `?interval=${encodeURIComponent(interval)}` +
    `&range=${encodeURIComponent(range)}` +
    `&includePrePost=false&events=div%2Csplit`;

  let lastErr = null;
  for (const host of CHART_HOSTS) {
    try {
      const res = await fetch(host + path, { credentials: "omit" });
      if (!res.ok) {
        lastErr = new Error(`HTTP ${res.status} from ${host}`);
        continue;
      }
      const json = await res.json();
      if (json?.chart?.error) {
        lastErr = new Error(json.chart.error.description || "Yahoo chart error");
        continue;
      }
      return json;
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("fetch failed");
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "fetchChart") return;
  fetchChart(msg.symbol, msg.interval, msg.range)
    .then((data) => sendResponse({ ok: true, data }))
    .catch((err) => sendResponse({ ok: false, error: String(err?.message || err) }));
  return true; // keep the message channel open for the async response
});
