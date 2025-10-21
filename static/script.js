console.log("SmartSave frontend loaded");

const form = document.getElementById("searchForm");
const resultsEl = document.getElementById("results");

// --- CSV fallback helpers ---
let _csvCache = null;

// NOTE: put your cleaned CSV at: static/data/walmart_milk_clean.csv
async function loadWalmartCsv() {
  if (_csvCache) return _csvCache;
  const url = "/static/data/walmart_milk_clean.csv";
  const res = await fetch(url);
  if (!res.ok) throw new Error(`CSV HTTP ${res.status}`);
  const text = await res.text();
  const parsed = Papa.parse(text, { header: true, skipEmptyLines: true });
  _csvCache = Array.isArray(parsed.data) ? parsed.data : [];
  return _csvCache;
}

function toNumberOrNull(v) {
  if (v == null) return null;
  const n = Number(String(v).replace(/[^\d.]/g, ""));
  return Number.isFinite(n) ? n : null;
}

async function searchCsvFallback(q) {
  const query = (q || "").trim().toLowerCase();
  const rows = await loadWalmartCsv();

  const filtered = rows
    .filter(r => r && (r.title || "").toLowerCase().includes(query))
    .map(r => ({
      store: "Walmart",
      title: r.title || "",
      price: toNumberOrNull(r.price),
      url: r.url || "",
      image: r.image || null
    }));

  return filtered;
}

// --- UI rendering (kept simple like your current version) ---
function renderCards(list) {
  resultsEl.innerHTML = list.map(r => `
    <div class="card">
      <div><strong>${r.store || "—"}</strong></div>
      <div>${r.title || "Untitled"}</div>
      <div>${r.price != null ? "$" + Number(r.price).toFixed(2) : "—"}</div>
      <a href="${r.url || "#"}" target="_blank" rel="noopener">View</a>
    </div>
  `).join("");
}

// --- Search flow: API first, then CSV fallback ---
async function runSearch(q, province) {
  resultsEl.textContent = "Searching…";

  // 1) Try API
  try {
    const url = `/api/search?q=${encodeURIComponent(q)}&province=${encodeURIComponent(province)}&refresh=true`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (Array.isArray(data) && data.length > 0) {
      renderCards(data);
      return;
    }
  } catch (err) {
    console.warn("API search failed, will try CSV fallback:", err);
  }

  // 2) Fallback to CSV
  try {
    const csvData = await searchCsvFallback(q);
    if (csvData.length > 0) {
      renderCards(csvData);
    } else {
      resultsEl.textContent = "No results.";
    }
  } catch (csvErr) {
    console.error("CSV fallback failed:", csvErr);
    resultsEl.textContent = "No results.";
  }
}

// --- Events ---
form?.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = document.getElementById("q").value.trim();
  const prov = document.getElementById("prov").value.trim().toUpperCase() || "AB";
  if (!q) return;
  runSearch(q, prov);
});

window.addEventListener("DOMContentLoaded", () => {
  const qInput = document.getElementById("q");
  if (qInput && !qInput.value) qInput.value = "milk";
  runSearch("milk", "AB");
});
