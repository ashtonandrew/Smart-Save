console.log("SmartSave frontend loaded");

const form = document.getElementById("searchForm");
const resultsEl = document.getElementById("results");
const sortEl = document.getElementById("sort");
const countEl = document.getElementById("count");

function fmtMoney(v) {
  if (v == null || isNaN(v)) return "—";
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(Number(v));
}

function render(items) {
  if (!Array.isArray(items) || items.length === 0) {
    resultsEl.classList.add("empty");
    resultsEl.innerHTML = `<div class="empty-state">No results.</div>`;
    countEl.textContent = "";
    return;
  }
  resultsEl.classList.remove("empty");
  countEl.textContent = `${items.length} result${items.length === 1 ? "" : "s"}`;

  const html = items.map(r => {
    const title = r.title || "";
    const price = r.price != null ? Number(r.price) : null;
    const ppu = r.price_per_unit ? String(r.price_per_unit) : "";
    const img = r.image || "";
    const store = r.store || "Walmart";
    const url = r.url || "#";

    return `
      <article class="card">
        <a class="thumb" href="${url}" target="_blank" rel="noopener">
          <img loading="lazy" src="${img}" alt="${title.replace(/"/g, "&quot;")}" onerror="this.style.display='none'">
        </a>
        <div class="info">
          <div class="store">${store}</div>
          <div class="title" title="${title.replace(/"/g, "&quot;")}">${title}</div>
          <div class="price-row">
            <div class="price">${fmtMoney(price)}</div>
            ${ppu ? `<div class="ppu">${ppu}</div>` : ""}
          </div>
          <div class="actions">
            <a class="view" href="${url}" target="_blank" rel="noopener">View</a>
          </div>
        </div>
      </article>
    `;
  }).join("");

  resultsEl.innerHTML = html;
}

function applySort(items, how) {
  const sorted = [...items];
  if (how === "price-asc") {
    sorted.sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));
  } else if (how === "price-desc") {
    sorted.sort((a, b) => (b.price ?? -Infinity) - (a.price ?? -Infinity));
  } else if (how === "store-asc") {
    sorted.sort((a, b) => (a.store || "").localeCompare(b.store || ""));
  }
  return sorted;
}

let lastData = [];

async function runSearch(q, province) {
  resultsEl.innerHTML = `<div class="loading">Searching…</div>`;
  try {
    const url = `/api/search?q=${encodeURIComponent(q)}&province=${encodeURIComponent(province)}&refresh=true`;
    const res = await fetch(url);
    const data = await res.json();
    if (!Array.isArray(data)) throw new Error("Bad API response");
    lastData = data;
    render(applySort(lastData, sortEl.value));
  } catch (err) {
    console.error(err);
    resultsEl.innerHTML = `<div class="error">Error loading results.</div>`;
    countEl.textContent = "";
  }
}

form?.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = document.getElementById("q").value.trim();
  const prov = (document.getElementById("prov").value || "").trim().toUpperCase() || "AB";
  if (!q) return;
  runSearch(q, prov);
});

sortEl?.addEventListener("change", () => {
  render(applySort(lastData, sortEl.value));
});

window.addEventListener("DOMContentLoaded", () => {
  const qInput = document.getElementById("q");
  if (qInput && !qInput.value) qInput.value = "milk";
  runSearch("milk", "AB");
});
