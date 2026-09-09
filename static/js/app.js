// DOM Element References
const runNowBtn = document.getElementById("run-now-btn");
const emptyRunBtn = document.getElementById("empty-run-btn");
const runBanner = document.getElementById("run-banner");
const runBannerText = document.getElementById("run-banner-text");
const runSpinner = document.getElementById("run-spinner");
const lastRunStatus = document.getElementById("last-run-status");
const lastRunTime = document.getElementById("last-run-time");
const emptyState = document.getElementById("empty-state");
const fleetTable = document.getElementById("fleet-table");
const fleetTbody = document.getElementById("fleet-tbody");
const searchInput = document.getElementById("search-input");
const searchClear = document.getElementById("search-clear");
const searchWrapper = document.querySelector(".search-wrapper");
const institutionFilter = document.getElementById("institution-filter");
const riskFilter = document.getElementById("risk-filter");
const pageSizeSelect = document.getElementById("page-size");
const prevPageBtn = document.getElementById("prev-page");
const nextPageBtn = document.getElementById("next-page");
const pageInfo = document.getElementById("page-info");
const activeFilters = document.getElementById("active-filters");
const clearAllBtn = document.getElementById("clear-all-filters");

// Constants
const RISK_ORDER = { critical: 3, warning: 2, healthy: 1, unknown: 0 };
const RISK_LABEL = { critical: "Critical", warning: "Warning", healthy: "Healthy", unknown: "Unknown" };
const GAUGE_MAX_DAYS = 30;

// State management
const state = {
  predictions: [],
  filters: {
    institution_code: null,
    risk_level: null,
    search: '',
    page: 1,
    page_size: 20
  },
  institutions: [],
  total: 0,
  totalPages: 0
};

// Formatting & Utility Helpers
function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtRul(days, overdue = false) {
  if (days == null) return "—";
  
  if (overdue) {
    const totalMinutes = Math.max(0, Math.round(-days * 24 * 60));
    const wholeDays = Math.floor(totalMinutes / (24 * 60));
    const hours = Math.floor((totalMinutes % (24 * 60)) / 60);
    const minutes = totalMinutes % 60;
    return `<div style="color: #dc3545;">${wholeDays} days ${hours} hours ${minutes} minutes</div><span class="badge overdue">OVERDUE</span>`;
  }

  const totalMinutes = Math.max(0, Math.round(days * 24 * 60));
  const wholeDays = Math.floor(totalMinutes / (24 * 60));
  const hours = Math.floor((totalMinutes % (24 * 60)) / 60);
  const minutes = totalMinutes % 60;

  return `${wholeDays} days ${hours} hours ${minutes} minutes`;
}

function riskLabel(level) {
  return RISK_LABEL[level] || "Unknown";
}

function confidenceLabel(conf) {
  if (conf == null) return "—";
  const pct = Math.round(conf * 100);
  if (conf > 0.7) return `<span class="confidence-high">${pct}%</span>`;
  if (conf > 0.4) return `<span class="confidence-medium">${pct}%</span>`;
  return `<span class="confidence-low">${pct}%</span>`;
}

function gaugeFillPct(days) {
  if (days == null) return 8;
  const pct = 100 - (days / GAUGE_MAX_DAYS) * 100;
  return Math.min(100, Math.max(4, pct));
}

function setButtonsDisabled(disabled) {
  if (runNowBtn) runNowBtn.disabled = disabled;
  if (emptyRunBtn) emptyRunBtn.disabled = disabled;
}

function showBanner(text, isError = false) {
  if (!runBanner || !runBannerText) return;
  runBannerText.textContent = text;
  runBanner.classList.add("visible");
  runBanner.classList.toggle("error", isError);
  if (runSpinner) runSpinner.style.display = isError ? "none" : "block";
}

function hideBanner() {
  if (runBanner) runBanner.classList.remove("visible");
}

const closeBannerBtn = document.getElementById("close-banner-btn");
if (closeBannerBtn) {
  closeBannerBtn.addEventListener("click", hideBanner);
}

function debounce(fn, delay) {
  let timeoutId;
  return (...args) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

// Rendering Functions
function renderStats(data) {
  const fleetElems = document.querySelectorAll("#stat-fleet");
  const critElems = document.querySelectorAll("#stat-critical");
  const warnElems = document.querySelectorAll("#stat-warning");
  const hlthElems = document.querySelectorAll("#stat-healthy");

  // Use overall statistics from API response (all ATMs, not just paginated)
  fleetElems.forEach(el => el.textContent = data.fleet_size || 0);
  critElems.forEach(el => el.textContent = data.critical_count || 0);
  warnElems.forEach(el => el.textContent = data.warning_count || 0);
  hlthElems.forEach(el => el.textContent = data.healthy_count || 0);
}

function buildDetailPanel(components) {
  const head = `
    <div class="detail-head">
      <div>Component</div><div>RUL</div><div>Risk</div><div>Confidence</div><div>Gauge</div>
    </div>
  `;
  const items = components
    .map(
      (c) => `
        <div class="detail-item">
          <div class="component-name">${c.component_id}</div>
          <div>${fmtRul(c.predicted_rul_days, c.overdue)}</div>
          <div><span class="badge ${c.risk_level}">${riskLabel(c.risk_level)}</span></div>
          <div class="confidence-cell">
            <div class="confidence-row"><span class="confidence-label">Survival:</span> ${confidenceLabel(c.confidence)}</div>
            <div class="confidence-row"><span class="confidence-label">Entropy:</span> ${confidenceLabel(c.confidence_entropy)}</div>
          </div>
          <div class="gauge">
            <div class="gauge-fill" style="width:${gaugeFillPct(c.predicted_rul_days)}%"></div>
            ${c.overdue ? '<span class="overdue-badge">OVERDUE</span>' : ''}
          </div>
        </div>
      `
    )
    .join("");
  return `<div class="detail-panel">${head}${items}</div>`;
}

function renderTable(predictions) {
  if (!predictions || predictions.length === 0) {
    if (emptyState) emptyState.style.display = "block";
    if (fleetTable) fleetTable.style.display = "none";
    return;
  }

  if (emptyState) emptyState.style.display = "none";
  if (fleetTable) fleetTable.style.display = "table";

  const sorted = [...predictions].sort((a, b) => {
    const riskDiff = (RISK_ORDER[b.overall_risk] ?? 0) - (RISK_ORDER[a.overall_risk] ?? 0);
    if (riskDiff !== 0) return riskDiff;
    const ra = a.weakest_component_rul_days ?? Infinity;
    const rb = b.weakest_component_rul_days ?? Infinity;
    return ra - rb;
  });

  if (!fleetTbody) return;
  fleetTbody.innerHTML = "";
  sorted.forEach((atm, idx) => {
    const rowId = `atm-detail-${idx}`;

    const summaryRow = document.createElement("tr");
    summaryRow.className = "atm-row";
    summaryRow.innerHTML = `
      <td class="chevron-cell"><span class="chevron">&#9662;</span></td>
      <td class="pid-cell">${atm.pid}</td>
      <td>${atm.institution_name ? `${atm.institution_name} (${atm.institution_code})` : (atm.institution_code || "—")}</td>
      <td>${atm.address || "—"}</td>
      <td><span class="badge ${atm.overall_risk}">${riskLabel(atm.overall_risk)}</span></td>
      <td>${atm.weakest_component_id || "—"}</td>
      <td class="rul-cell">${fmtRul(atm.weakest_component_rul_days, atm.overdue)}</td>
    `;

    const detailRow = document.createElement("tr");
    detailRow.className = "detail-row";
    detailRow.id = rowId;
    const detailCell = document.createElement("td");
    detailCell.colSpan = 7;
    detailCell.innerHTML = buildDetailPanel(atm.components || []);
    detailRow.appendChild(detailCell);

    summaryRow.addEventListener("click", () => {
      const willOpen = !detailRow.classList.contains("visible");
      detailRow.classList.toggle("visible", willOpen);
      summaryRow.classList.toggle("expanded", willOpen);
    });

    fleetTbody.appendChild(summaryRow);
    fleetTbody.appendChild(detailRow);
  });
}

function updateFilterUI() {
  if (!activeFilters) return;

  const instTag = document.querySelector('[data-filter="institution"]');
  const riskTag = document.querySelector('[data-filter="risk"]');
  const searchTag = document.querySelector('[data-filter="search"]');

  if (instTag) instTag.hidden = !state.filters.institution_code;
  if (riskTag) riskTag.hidden = !state.filters.risk_level;
  if (searchTag) searchTag.hidden = !state.filters.search;
  
  const hasAnyFilter = state.filters.institution_code || state.filters.risk_level || state.filters.search;
  activeFilters.hidden = !hasAnyFilter;
  if (clearAllBtn) clearAllBtn.hidden = !hasAnyFilter;

  if (state.filters.institution_code && instTag) {
    const inst = state.institutions.find(i => i.code === state.filters.institution_code);
    const span = instTag.querySelector('span');
    if (span) span.textContent = inst?.name || state.filters.institution_code;
  }
  if (state.filters.risk_level && riskTag) {
    const span = riskTag.querySelector('span');
    if (span) span.textContent = riskLabel(state.filters.risk_level);
  }
  if (state.filters.search && searchTag) {
    const span = searchTag.querySelector('span');
    if (span) span.textContent = state.filters.search;
  }

  if (searchClear) searchClear.hidden = !searchInput.value;
  
  document.querySelectorAll('.stat-card').forEach(card => {
    const risk = card.dataset.risk;
    if (risk && state.filters.risk_level && state.filters.risk_level !== risk) {
      card.style.opacity = '0.4';
    } else {
      card.style.opacity = '1';
    }
  });
}

function updatePagination() {
  if (pageInfo) pageInfo.textContent = `Page ${state.filters.page} of ${state.totalPages || 1}`;
  if (prevPageBtn) prevPageBtn.disabled = state.filters.page <= 1;
  if (nextPageBtn) nextPageBtn.disabled = state.filters.page >= state.totalPages || state.totalPages === 0;
  const paginationElem = document.getElementById("pagination");
  if (paginationElem) paginationElem.hidden = state.totalPages <= 1 && state.predictions.length === 0;
}

function populateInstitutionFilter() {
  if (!institutionFilter || !state.institutions) return;
  const currentVal = institutionFilter.value;
  institutionFilter.innerHTML = '<option value="">All Institutions</option>' +
    state.institutions.map(i => `<option value="${i.code}">${i.name} (${i.code})</option>`).join('');
  institutionFilter.value = currentVal || (state.filters.institution_code || "");
}

// API Functions
async function fetchPredictions() {
  const params = new URLSearchParams({
    page: state.filters.page,
    page_size: state.filters.page_size
  });
  
  if (state.filters.institution_code) params.set('institution_code', state.filters.institution_code);
  if (state.filters.risk_level) params.set('risk_level', state.filters.risk_level);
  if (state.filters.search) params.set('search', state.filters.search);

  try {
    const res = await fetch(`/api/predictions/latest?${params.toString()}`);
    if (res.status === 401) {
      showBanner('Authentication expired or missing. Please log in again.', true);
      return;
    }
    if (!res.ok) throw new Error('Failed to fetch predictions');
    const data = await res.json();
    
    state.predictions = data.predictions || [];
    state.total = data.total || 0;
    state.totalPages = data.total_pages || 0;
    state.institutions = data.institutions || [];
    state.filters.page = data.page || 1;
    state.filters.page_size = data.page_size || 20;
    
    populateInstitutionFilter();
    updateFilterUI();
    renderTable(state.predictions);
    renderStats(data);
    updatePagination();
  } catch (err) {
    console.error('Failed to fetch predictions:', err);
    showBanner('Failed to load predictions', true);
  }
}

async function triggerRun() {
  setButtonsDisabled(true);
  showBanner("Running prediction pipeline…");
  try {
    const res = await fetch("/api/predictions/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ triggered_by: "manual" }),
    });
    if (res.status === 401) {
      showBanner('Authentication expired or missing. Please log in again.', true);
      setButtonsDisabled(false);
      return;
    }
    if (!res.ok) throw new Error(`Pipeline failed with HTTP ${res.status}`);
    const run = await res.json();
    
    if (run.status === "failed") {
      showBanner(`Prediction run failed: ${run.error_message || "unknown error"}`, true);
    } else {
      hideBanner();
      if (lastRunStatus) lastRunStatus.textContent = "Last run successful";
      if (lastRunTime) lastRunTime.textContent = `${fmtDate(run.completed_at || run.started_at)} · ${run.triggered_by}`;
      await fetchPredictions();
    }
  } catch (err) {
    showBanner("Could not reach the prediction pipeline. Check the API and try again.", true);
    console.error(err);
  } finally {
    setButtonsDisabled(false);
  }
}

// Event Listeners Registration
if (runNowBtn) runNowBtn.addEventListener("click", triggerRun);
if (emptyRunBtn) emptyRunBtn.addEventListener("click", triggerRun);

// Search Expand/Collapse
function initSearchExpand() {
  if (!searchInput || !searchWrapper) return;
  
  searchInput.addEventListener('focus', () => {
    searchInput.classList.remove('collapsed');
    searchInput.classList.add('expanded');
    const expandedPlaceholder = searchInput.dataset.expandedPlaceholder || 'Search ATM by PID, name, address, institution...';
    searchInput.placeholder = expandedPlaceholder;
  });
  
  searchInput.addEventListener('blur', () => {
    if (!searchInput.value.trim()) {
      searchInput.classList.remove('expanded');
      searchInput.classList.add('collapsed');
      const collapsedPlaceholder = searchInput.dataset.collapsedPlaceholder || 'Search by ATM name...';
      searchInput.placeholder = collapsedPlaceholder;
    }
  });
  
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      searchInput.blur();
      if (!searchInput.value.trim()) {
        searchInput.classList.remove('expanded');
        searchInput.classList.add('collapsed');
        const collapsedPlaceholder = searchInput.dataset.collapsedPlaceholder || 'Search by ATM name...';
        searchInput.placeholder = collapsedPlaceholder;
      }
    }
  });
}

// Update active filter tags UI
function updateActiveFilters() {
  if (!activeFilters) return;

  const instTag = document.querySelector('[data-filter="institution"]');
  const riskTag = document.querySelector('[data-filter="risk"]');
  const searchTag = document.querySelector('[data-filter="search"]');

  let hasAnyFilter = false;

  if (state.filters.institution_code && instTag) {
    const inst = state.institutions.find(i => i.code === state.filters.institution_code);
    const span = instTag.querySelector('span:last-of-type');
    if (span) span.textContent = inst?.name || state.filters.institution_code;
    instTag.hidden = false;
    hasAnyFilter = true;
  } else if (instTag) {
    instTag.hidden = true;
  }

  if (state.filters.risk_level && riskTag) {
    const span = riskTag.querySelector('span:last-of-type');
    if (span) span.textContent = riskLabel(state.filters.risk_level);
    riskTag.hidden = false;
    hasAnyFilter = true;
  } else if (riskTag) {
    riskTag.hidden = true;
  }

  if (state.filters.search && searchTag) {
    const span = searchTag.querySelector('span:last-of-type');
    if (span) span.textContent = state.filters.search;
    searchTag.hidden = false;
    hasAnyFilter = true;
  } else if (searchTag) {
    searchTag.hidden = true;
  }

  if (searchClear) searchClear.hidden = !searchInput.value;

  activeFilters.hidden = !hasAnyFilter;
  if (clearAllBtn) clearAllBtn.hidden = !hasAnyFilter;

  document.querySelectorAll('.stat-card').forEach(card => {
    const risk = card.dataset.risk;
    if (risk && state.filters.risk_level && state.filters.risk_level !== risk) {
      card.style.opacity = '0.4';
    } else {
      card.style.opacity = '1';
    }
  });
}

// Filter tag remove buttons
function initFilterTagRemoval() {
  document.querySelectorAll('.filter-remove').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const tag = e.target.closest('.filter-tag');
      if (!tag) return;
      const filter = tag.dataset.filter;
      if (filter === 'institution' && institutionFilter) institutionFilter.value = '';
      if (filter === 'risk' && riskFilter) riskFilter.value = '';
      if (filter === 'search' && searchInput) searchInput.value = '';
      
      const key = filter === 'institution' ? 'institution_code' : 
                  filter === 'risk' ? 'risk_level' : 'search';
      state.filters[key] = null;
      state.filters.page = 1;
      fetchPredictions();
    });
  });

  if (clearAllBtn) {
    clearAllBtn.addEventListener('click', () => {
      state.filters.institution_code = null;
      state.filters.risk_level = null;
      state.filters.search = '';
      state.filters.page = 1;
      if (institutionFilter) institutionFilter.value = '';
      if (riskFilter) riskFilter.value = '';
      if (searchInput) searchInput.value = '';
      updateActiveFilters();
      fetchPredictions();
    });
  }
}

// Other filter event listeners
if (institutionFilter) {
  institutionFilter.addEventListener('change', () => {
    state.filters.institution_code = institutionFilter.value || null;
    state.filters.page = 1;
    fetchPredictions();
  });
}

if (riskFilter) {
  riskFilter.addEventListener('change', () => {
    state.filters.risk_level = riskFilter.value || null;
    state.filters.page = 1;
    fetchPredictions();
  });
}

if (pageSizeSelect) {
  pageSizeSelect.addEventListener('change', () => {
    state.filters.page_size = parseInt(pageSizeSelect.value, 10);
    state.filters.page = 1;
    fetchPredictions();
  });
}

if (prevPageBtn) {
  prevPageBtn.addEventListener('click', () => {
    if (state.filters.page > 1) {
      state.filters.page--;
      fetchPredictions();
    }
  });
}

if (nextPageBtn) {
  nextPageBtn.addEventListener('click', () => {
    if (state.filters.page < state.totalPages) {
      state.filters.page++;
      fetchPredictions();
    }
  });
}

// Debounced search
const debouncedSearch = debounce(() => {
  if (searchInput) {
    state.filters.search = searchInput.value.trim();
    state.filters.page = 1;
    fetchPredictions();
    updateActiveFilters();
  }
}, 300);

if (searchInput) {
  searchInput.addEventListener('input', debouncedSearch);
}

if (searchClear) {
  searchClear.addEventListener('click', () => {
    if (searchInput) {
      searchInput.value = '';
      searchInput.dispatchEvent(new Event('input'));
      searchInput.focus();
    }
  });
}

// Stat card click handlers
document.querySelectorAll('.stat-card').forEach(card => {
  card.style.cursor = 'pointer';
  card.addEventListener('click', () => {
    const risk = card.dataset.risk;
    if (!risk) return;
    
    if (state.filters.risk_level === risk) {
      if (riskFilter) riskFilter.value = '';
      state.filters.risk_level = null;
    } else {
      if (riskFilter) riskFilter.value = risk;
      state.filters.risk_level = risk;
    }
    state.filters.page = 1;
    fetchPredictions();
  });
});

// Initialize new features
initSearchExpand();
initFilterTagRemoval();
updateActiveFilters();

// Initial load
fetchPredictions();