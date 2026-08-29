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

const RISK_ORDER = { critical: 3, warning: 2, healthy: 1, unknown: 0 };
const RISK_LABEL = { critical: "Critical", warning: "Warning", healthy: "Healthy", unknown: "Unknown" };
// Reference ceiling (days) used only to scale gauge fill width - not a
// business threshold, just a visual range so the bar has room to breathe.
const GAUGE_MAX_DAYS = 30;

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

function fmtRul(days) {
  return days == null ? "—" : `${days.toFixed(1)} d`;
}

function riskLabel(level) {
  return RISK_LABEL[level] || "Unknown";
}

function gaugeFillPct(days) {
  if (days == null) return 8;
  const pct = 100 - (days / GAUGE_MAX_DAYS) * 100;
  return Math.min(100, Math.max(4, pct));
}

function setButtonsDisabled(disabled) {
  runNowBtn.disabled = disabled;
  if (emptyRunBtn) emptyRunBtn.disabled = disabled;
}

function showBanner(text, isError = false) {
  runBannerText.textContent = text;
  runBanner.classList.add("visible");
  runBanner.classList.toggle("error", isError);
  runSpinner.style.display = isError ? "none" : "block";
}

function hideBanner() {
  runBanner.classList.remove("visible");
}

function renderStats(predictions) {
  const counts = { critical: 0, warning: 0, healthy: 0 };
  predictions.forEach((p) => {
    if (counts[p.overall_risk] !== undefined) counts[p.overall_risk] += 1;
  });
  document.getElementById("stat-fleet").textContent = predictions.length;
  document.getElementById("stat-critical").textContent = counts.critical;
  document.getElementById("stat-warning").textContent = counts.warning;
  document.getElementById("stat-healthy").textContent = counts.healthy;
}

function buildDetailPanel(components) {
  const head = `
    <div class="detail-head">
      <div>Component</div><div>RUL</div><div>Risk</div><div>Gauge</div>
    </div>
  `;
  const items = components
    .map(
      (c) => `
        <div class="detail-item">
          <div class="component-name">${c.component_id}</div>
          <div>${fmtRul(c.predicted_rul_days)}</div>
          <div><span class="badge ${c.risk_level}">${riskLabel(c.risk_level)}</span></div>
          <div class="gauge"><div class="gauge-fill" style="width:${gaugeFillPct(c.predicted_rul_days)}%"></div></div>
        </div>
      `
    )
    .join("");
  return `<div class="detail-panel">${head}${items}</div>`;
}

function renderTable(predictions) {
  if (!predictions || predictions.length === 0) {
    emptyState.style.display = "block";
    fleetTable.style.display = "none";
    return;
  }

  emptyState.style.display = "none";
  fleetTable.style.display = "table";

  const sorted = [...predictions].sort((a, b) => {
    const riskDiff = (RISK_ORDER[b.overall_risk] ?? 0) - (RISK_ORDER[a.overall_risk] ?? 0);
    if (riskDiff !== 0) return riskDiff;
    const ra = a.weakest_component_rul_days ?? Infinity;
    const rb = b.weakest_component_rul_days ?? Infinity;
    return ra - rb;
  });

  fleetTbody.innerHTML = "";
  sorted.forEach((atm, idx) => {
    const rowId = `atm-detail-${idx}`;

    const summaryRow = document.createElement("tr");
    summaryRow.className = "atm-row";
    summaryRow.innerHTML = `
      <td class="chevron-cell"><span class="chevron">&#9662;</span></td>
      <td class="pid-cell">${atm.pid}</td>
      <td><span class="badge ${atm.overall_risk}">${riskLabel(atm.overall_risk)}</span></td>
      <td>${atm.weakest_component_id || "—"}</td>
      <td class="rul-cell">${fmtRul(atm.weakest_component_rul_days)}</td>
    `;

    const detailRow = document.createElement("tr");
    detailRow.className = "detail-row";
    detailRow.id = rowId;
    const detailCell = document.createElement("td");
    detailCell.colSpan = 5;
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

function renderRun(run) {
  if (!run) {
    lastRunStatus.textContent = "No run yet";
    lastRunTime.textContent = "—";
    renderTable([]);
    renderStats([]);
    return;
  }

  const statusLabel = { success: "Last run succeeded", failed: "Last run failed", pending: "Run in progress" };
  lastRunStatus.textContent = statusLabel[run.status] || run.status;
  lastRunTime.textContent = `${fmtDate(run.completed_at || run.started_at)} · ${run.triggered_by}`;

  if (run.status === "failed") {
    showBanner(`Prediction run failed: ${run.error_message || "unknown error"}`, true);
  } else if (run.status === "pending") {
    showBanner("Running prediction pipeline…");
  } else {
    hideBanner();
  }

  renderTable(run.predictions || []);
  renderStats(run.predictions || []);
}

async function fetchLatest() {
  try {
    const res = await fetch("/api/predictions/latest");
    if (!res.ok) return;
    const run = await res.json();
    renderRun(run);
  } catch (err) {
    console.error("Failed to fetch latest prediction", err);
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
    const run = await res.json();
    renderRun(run);
  } catch (err) {
    showBanner("Could not reach the prediction pipeline. Check the API and try again.", true);
    console.error(err);
  } finally {
    setButtonsDisabled(false);
  }
}

runNowBtn.addEventListener("click", triggerRun);
if (emptyRunBtn) emptyRunBtn.addEventListener("click", triggerRun);

fetchLatest();
