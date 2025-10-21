console.log("SmartSave frontend loaded");

const form = document.getElementById("searchForm");
const resultsEl = document.getElementById("results");
const sortSel = document.getElementById("sort");

function showError(msg) {
  resultsEl.innerHTML = `<div class="error">Error loading results.<br><small>${msg}</small></div>`;
}

function render(items) {
  if (!items.length) {
    resultsEl.innerHTML = `<div class="empty">No results.</div>`;
    return;
  }
  resultsEl.innerHTML = items.map(r => {
    // use image proxy to bypass hotlink blocking
    const imgSrc = r.image ? `/img?u=${encodeURIComponent(r.image)}` : null;
    return `
      <div class="card">
        <div class="thumb">
          ${imgSrc
            ? `<img src="${imgSrc}" alt="${r.title}" loading="lazy" />`
            : `<div class="noimg">No image</div>`}
        </div>
        <div class="info">
          <div class="store">${r.store || "Walmart"}</div>
          <div class="title">${r.title || ""}</div>
          <div class="meta">
            <span class="price">${r.price != null && r.price !== "" ? "$" + Number(r.price).toFixed(2) : "—"}</span>
            ${r.size_text ? `<span class="size">${r.size_text}</span>` : ""}
          </div>
          ${r.url ? `<a href="${r.url}" target="_blank" rel="noopener">View</a>` : ""}
        </div>
      </div>
    `;
  }).join("");
}

function sortItems(items, sortKey) {
  const arr = [...items];
  const val = (x) => (typeof x.price === "number" ? x.price : (sortKey === "price-asc" ? Infinity : -Infinity));
  if (sortKey === "price-desc") {
    arr.sort((a, b) => val(b) - val(a));
  } else {
    arr.sort((a, b) => val(a) - val(b));
  }
  return arr;
}

async function runSearch(q, province) {
  resultsEl.textContent = "Searching…";
  const url = `/api/search?q=${encodeURIComponent(q)}&province=${encodeURIComponent(province)}&sort=${encodeURIComponent(sortSel.value)}`;
  try {
    const res = await fetch(url, { headers: { "Accept": "application/json" } });
    const text = await res.text();

    if (!res.ok) {
      showError(`HTTP ${res.status} – ${text.slice(0, 200)}`);
      return;
    }

    let data;
    try { data = JSON.parse(text); }
    catch {
      console.error("Bad JSON from API:", text);
      showError("Server returned non-JSON.");
      return;
    }

    const items = Array.isArray(data) ? data : (data.items || []);
    const sorted = sortItems(items, sortSel.value);
    render(sorted);
  } catch (err) {
    console.error(err);
    showError(err.message || "Network error");
  }
}

form?.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = document.getElementById("q").value.trim() || "milk";
  const prov = document.getElementById("prov").value.trim().toUpperCase() || "AB";
  runSearch(q, prov);
});

sortSel?.addEventListener("change", () => {
  const q = document.getElementById("q").value.trim() || "milk";
  const prov = document.getElementById("prov").value.trim().toUpperCase() || "AB";
  runSearch(q, prov);
});

window.addEventListener("DOMContentLoaded", () => {
  const qInput = document.getElementById("q");
  if (qInput && !qInput.value) qInput.value = "milk";
  runSearch("milk", "AB");
});
