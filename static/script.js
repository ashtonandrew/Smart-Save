console.log("SmartSave frontend loaded");

const form = document.getElementById("searchForm");
const resultsEl = document.getElementById("results");

async function runSearch(q, province) {
  resultsEl.textContent = "Searching…";
  const url = `/api/search?q=${encodeURIComponent(q)}&province=${encodeURIComponent(province)}&refresh=true`;
  const res = await fetch(url);
  const data = await res.json();
  if (!Array.isArray(data) || data.length === 0) {
    resultsEl.textContent = "No results.";
    return;
  }
  resultsEl.innerHTML = data.map(r => `
    <div class="card">
      <div><strong>${r.store}</strong></div>
      <div>${r.title}</div>
      <div>${r.price != null ? "$" + Number(r.price).toFixed(2) : "—"}</div>
      <a href="${r.url}" target="_blank" rel="noopener">View</a>
    </div>
  `).join("");
}

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
