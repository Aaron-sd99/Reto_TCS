const API_BASE = "http://localhost:8080";

const elements = {
  totalTransfers: document.querySelector("#totalTransfers"),
  transferBreakdown: document.querySelector("#transferBreakdown"),
  outboxPublished: document.querySelector("#outboxPublished"),
  outboxBreakdown: document.querySelector("#outboxBreakdown"),
  aiRecommendations: document.querySelector("#aiRecommendations"),
  ledgerEntries: document.querySelector("#ledgerEntries"),
  accountsTable: document.querySelector("#accountsTable"),
  transfersList: document.querySelector("#transfersList"),
  transferForm: document.querySelector("#transferForm"),
  transferResult: document.querySelector("#transferResult"),
  sourceAccount: document.querySelector("#sourceAccount"),
  destinationAccount: document.querySelector("#destinationAccount"),
  amount: document.querySelector("#amount"),
  currency: document.querySelector("#currency"),
  customerId: document.querySelector("#customerId"),
  apiStatus: document.querySelector("#apiStatus"),
  refreshButton: document.querySelector("#refreshButton"),
  observabilityStatus: document.querySelector("#observabilityStatus"),
  metricFilters: document.querySelector("#metricFilters"),
  metricChart: document.querySelector("#metricChart"),
  metricDetail: document.querySelector("#metricDetail"),
};

const METRIC_VIEWS = {
  services: {
    title: "Estado de servicios",
    query: "up",
    rangeQuery: "up",
    chart: "line",
    description: "Targets scrapeados por Prometheus.",
    label: (metric) => metric.job || metric.instance || "servicio",
    formatValue: (value) => (value === 1 ? "UP" : "DOWN"),
    summarize: (series) => `${series.filter((row) => row.value === 1).length}/${series.length}`,
    latestLabel: "estado actual",
  },
  transfers: {
    title: "Transferencias por estado",
    query: "sum by (status) (smartbancs_transfer_outcomes_total)",
    rangeQuery: "round(sum by (status) (increase(smartbancs_transfer_outcomes_total[1m])))",
    chart: "bars",
    description: "Resultados finales acumulados y actividad reciente por minuto.",
    label: (metric) => metric.status || "sin estado",
    latestLabel: "último minuto",
  },
  latency: {
    title: "Latencia p95",
    query: "histogram_quantile(0.95, sum by (le, route) (rate(smartbancs_request_latency_seconds_bucket[5m])))",
    rangeQuery: "histogram_quantile(0.95, sum by (le, route) (rate(smartbancs_request_latency_seconds_bucket[5m])))",
    chart: "line",
    description: "Percentil 95 de tiempo de respuesta por ruta HTTP.",
    label: (metric) => metric.route || "ruta",
    formatValue: (value) => `${(value * 1000).toFixed(1)} ms`,
    summarize: (series) => {
      const max = Math.max(...series.map((row) => row.value), 0);
      return `${(max * 1000).toFixed(1)} ms`;
    },
    latestLabel: "p95 actual",
  },
  errors: {
    title: "Errores HTTP",
    query: "sum by (route, status) (smartbancs_request_latency_seconds_count{status=~\"4..|5..\"})",
    rangeQuery: "round(sum by (route, status) (increase(smartbancs_request_latency_seconds_count{status=~\"4..|5..\"}[1m])))",
    chart: "bars",
    description: "Errores HTTP 4xx/5xx acumulados y actividad reciente.",
    label: (metric) => `${metric.route || "ruta"} · ${metric.status || "status"}`,
    latestLabel: "último minuto",
  },
  outbox: {
    title: "Eventos outbox",
    query: "sum by (event_type, result) (smartbancs_outbox_events_total)",
    rangeQuery: "round(sum by (event_type, result) (increase(smartbancs_outbox_events_total[1m])))",
    chart: "bars",
    description: "Eventos acumulados y actividad reciente procesada por outbox.",
    label: (metric) => `${metric.event_type || "evento"} · ${metric.result || "resultado"}`,
    latestLabel: "último minuto",
  },
  core: {
    title: "Liquidación Bancs",
    query: "sum by (status) (bancs_postings_total)",
    rangeQuery: "round(sum by (status) (increase(bancs_postings_total[1m])))",
    chart: "bars",
    description: "Postings acumulados y actividad reciente del adapter.",
    label: (metric) => metric.status || "estado",
    latestLabel: "último minuto",
  },
  ai: {
    title: "Recomendaciones IA",
    query: "sum by (type) (ai_recommendations_total)",
    rangeQuery: "round(sum by (type) (increase(ai_recommendations_total[1m])))",
    chart: "bars",
    description: "Recomendaciones acumuladas y actividad reciente de IA.",
    label: (metric) => metric.type || "recomendación",
    latestLabel: "último minuto",
  },
};

let activeMetricView = "services";
let refreshing = false;

function formatMoney(value, currency = "USD") {
  return new Intl.NumberFormat("es-EC", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(Number(value || 0));
}

function generateKey() {
  return `ui-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function statusClass(status) {
  if (status === "SETTLED") return "settled";
  if (status === "REJECTED") return "rejected";
  return "pending";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#039;");
}

function renderTransferResult(transfer) {
  elements.transferResult.innerHTML = `
    <strong>${transfer.status}</strong><br />
    Transferencia ${transfer.id}<br />
    ${transfer.source_account} → ${transfer.destination_account} · ${formatMoney(transfer.amount, transfer.currency)}
  `;
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(body?.detail || `HTTP ${response.status}`);
  }
  return body;
}

async function loadSummary() {
  const summary = await request("/v1/operations/summary");
  const transferValues = Object.values(summary.transfers || {});
  const outbox = summary.outbox || {};
  const totalTransfers = transferValues.reduce((sum, value) => sum + value, 0);
  const published = outbox.PUBLISHED || 0;

  elements.totalTransfers.textContent = totalTransfers;
  elements.transferBreakdown.textContent = Object.entries(summary.transfers || {})
    .map(([key, value]) => `${key}: ${value}`)
    .join(" · ") || "Sin transferencias";
  elements.outboxPublished.textContent = published;
  elements.outboxBreakdown.textContent = Object.entries(outbox)
    .map(([key, value]) => `${key}: ${value}`)
    .join(" · ") || "Sin eventos";
  elements.aiRecommendations.textContent = summary.ai_recommendations || 0;
  elements.ledgerEntries.textContent = summary.ledger_entries || 0;
}

async function loadAccounts() {
  const accounts = await request("/v1/accounts");
  elements.accountsTable.innerHTML = accounts
    .map((account) => `
      <tr>
        <td><strong>${account.account_id}</strong></td>
        <td>${account.customer_id}</td>
        <td>${formatMoney(account.available_balance, account.currency)}</td>
        <td>${account.status}</td>
      </tr>
    `)
    .join("");

  const options = accounts
    .map((account) => `<option value="${account.account_id}">${account.account_id} · ${formatMoney(account.available_balance, account.currency)}</option>`)
    .join("");
  elements.sourceAccount.innerHTML = options;
  elements.destinationAccount.innerHTML = options;
  if (accounts.length > 1) {
    elements.destinationAccount.selectedIndex = 1;
  }
}

async function loadTransfers() {
  const transfers = await request("/v1/transfers?limit=12");
  elements.transfersList.innerHTML = transfers.length
    ? transfers.map((transfer) => `
      <article class="activity-item">
        <div>
          <strong>${transfer.source_account} → ${transfer.destination_account}</strong>
          <span>${formatMoney(transfer.amount, transfer.currency)} · ${transfer.correlation_id}</span>
        </div>
        <span class="badge ${statusClass(transfer.status)}">${transfer.status}</span>
      </article>
    `).join("")
    : "<p class=\"panel-copy\">Todavía no hay transferencias registradas.</p>";
}

async function queryPrometheus(query) {
  const response = await fetch(`/prometheus/api/v1/query?query=${encodeURIComponent(query)}`);
  const payload = await response.json();
  if (!response.ok || payload.status !== "success") {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload.data.result.map((item) => ({
    metric: item.metric,
    value: Number(item.value?.[1] || 0),
  }));
}

async function queryPrometheusRange(query) {
  const end = Math.floor(Date.now() / 1000);
  const start = end - 30 * 60;
  const params = new URLSearchParams({
    query,
    start: String(start),
    end: String(end),
    step: "30",
  });
  const response = await fetch(`/prometheus/api/v1/query_range?${params.toString()}`);
  const payload = await response.json();
  if (!response.ok || payload.status !== "success") {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload.data.result.map((item) => ({
    metric: item.metric,
    values: item.values.map(([timestamp, value]) => ({
      timestamp: Number(timestamp),
      value: Number(value || 0),
    })),
  }));
}

function buildSeriesPath(points, maxValue, dimensions) {
  const { width, height, padding } = dimensions;
  if (!points.length) return "";
  const minTime = points[0].timestamp;
  const maxTime = points[points.length - 1].timestamp || minTime + 1;
  return points
    .map((point, index) => {
      const x = padding.left + ((point.timestamp - minTime) / Math.max(maxTime - minTime, 1)) * (width - padding.left - padding.right);
      const y = padding.top + (1 - point.value / Math.max(maxValue, 1)) * (height - padding.top - padding.bottom);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

function buildActivityBars(rangeSeries, maxValue, dimensions, palette) {
  const { width, height, padding } = dimensions;
  const points = rangeSeries[0]?.values || [];
  if (!points.length) return "";
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const groupWidth = plotWidth / points.length;
  const barWidth = Math.max(3, Math.min(14, (groupWidth - 3) / Math.max(rangeSeries.length, 1)));

  return rangeSeries
    .map((serie, serieIndex) => serie.values
      .map((point, pointIndex) => {
        const value = Math.max(point.value, 0);
        const barHeight = value === 0 ? 0 : Math.max(2, (value / Math.max(maxValue, 1)) * plotHeight);
        const x = padding.left + pointIndex * groupWidth + serieIndex * barWidth + 2;
        const y = padding.top + plotHeight - barHeight;
        return `
          <rect
            x="${x.toFixed(1)}"
            y="${y.toFixed(1)}"
            width="${barWidth.toFixed(1)}"
            height="${barHeight.toFixed(1)}"
            rx="2"
            fill="${palette[serieIndex % palette.length]}"
          />`;
      })
      .join(""))
    .join("");
}

function formatMetricValue(value) {
  return new Intl.NumberFormat("es-EC", { maximumFractionDigits: 2 }).format(value);
}

function renderMetricChart(viewKey, instantSeries, rangeSeries) {
  const view = METRIC_VIEWS[viewKey];
  const rows = [...instantSeries].sort((left, right) => right.value - left.value);
  const allPoints = rangeSeries.flatMap((serie) => serie.values);
  const maxValue = view.chart === "bars"
    ? Math.max(...allPoints.map((point) => point.value), 1)
    : Math.max(...allPoints.map((point) => point.value), ...rows.map((row) => row.value), 1);
  const totalValue = rows.reduce((sum, row) => sum + row.value, 0);
  const dimensions = {
    width: 920,
    height: 260,
    padding: { top: 20, right: 28, bottom: 34, left: 56 },
  };
  const palette = ["#0f766e", "#1d4ed8", "#b45309", "#7c3aed", "#b91c1c", "#334155"];

  if (!rows.length) {
    elements.metricChart.innerHTML = `
      <div class="observability-stats">
        <article>
          <span>${escapeHtml(view.title)}</span>
          <strong>0</strong>
          <small>sin actividad registrada</small>
        </article>
        <article>
          <span>Series</span>
          <strong>0</strong>
          <small>dimensiones visibles</small>
        </article>
        <article>
          <span>Última muestra</span>
          <strong>0</strong>
          <small>ventana de 30 minutos</small>
        </article>
      </div>
      <div class="timeseries-card">
        <div class="chart-title">
          <strong>${escapeHtml(view.title)}</strong>
          <span>Últimos 30 minutos</span>
        </div>
        <svg class="timeseries-chart" viewBox="0 0 ${dimensions.width} ${dimensions.height}" role="img" aria-label="${escapeHtml(view.title)}">
          <line x1="${dimensions.padding.left}" y1="20" x2="${dimensions.padding.left}" y2="226" />
          <line x1="${dimensions.padding.left}" y1="226" x2="892" y2="226" />
          <line class="grid-line" x1="${dimensions.padding.left}" y1="72" x2="892" y2="72" />
          <line class="grid-line" x1="${dimensions.padding.left}" y1="124" x2="892" y2="124" />
          <line class="grid-line" x1="${dimensions.padding.left}" y1="176" x2="892" y2="176" />
          <text x="12" y="27">1</text>
          <text x="12" y="231">0</text>
        </svg>
      </div>
      <div class="metric-legend">
        <span><i style="background:#94a3b8"></i>Sin actividad <strong>0</strong></span>
      </div>
    `;
    elements.metricDetail.textContent = `${view.description} Consulta: ${view.query}`;
    return;
  }

  const paths = rangeSeries
    .map((serie, index) => {
      const path = buildSeriesPath(serie.values, maxValue, dimensions);
      if (!path) return "";
      return `<path d="${path}" fill="none" stroke="${palette[index % palette.length]}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" />`;
    })
    .join("");
  const bars = buildActivityBars(rangeSeries, maxValue, dimensions, palette);
  const latestPoint = rangeSeries.reduce((sum, serie) => sum + (serie.values.at(-1)?.value || 0), 0);
  const primaryStat = view.summarize ? view.summarize(rows) : formatMetricValue(totalValue);
  const secondaryStat = viewKey === "services" ? "servicios activos" : "total acumulado";
  const chartMarkup = view.chart === "bars" ? bars : paths;

  elements.metricChart.innerHTML = `
    <div class="observability-stats">
      <article>
        <span>${escapeHtml(view.title)}</span>
        <strong>${escapeHtml(primaryStat)}</strong>
        <small>${escapeHtml(secondaryStat)}</small>
      </article>
      <article>
        <span>Series</span>
        <strong>${rows.length}</strong>
        <small>dimensiones visibles</small>
      </article>
      <article>
        <span>Última muestra</span>
        <strong>${formatMetricValue(latestPoint)}</strong>
        <small>${escapeHtml(view.latestLabel || "ventana de 30 minutos")}</small>
      </article>
    </div>

    <div class="timeseries-card">
      <div class="chart-title">
        <strong>${escapeHtml(view.title)}</strong>
        <span>Últimos 30 minutos</span>
      </div>
      <svg class="timeseries-chart" viewBox="0 0 ${dimensions.width} ${dimensions.height}" role="img" aria-label="${escapeHtml(view.title)}">
        <line x1="${dimensions.padding.left}" y1="20" x2="${dimensions.padding.left}" y2="226" />
        <line x1="${dimensions.padding.left}" y1="226" x2="892" y2="226" />
        <line class="grid-line" x1="${dimensions.padding.left}" y1="72" x2="892" y2="72" />
        <line class="grid-line" x1="${dimensions.padding.left}" y1="124" x2="892" y2="124" />
        <line class="grid-line" x1="${dimensions.padding.left}" y1="176" x2="892" y2="176" />
        <text x="12" y="27">${formatMetricValue(maxValue)}</text>
        <text x="12" y="231">0</text>
        ${chartMarkup}
      </svg>
    </div>

    <div class="metric-legend">
      ${rows.map((row, index) => `
        <span>
          <i style="background:${palette[index % palette.length]}"></i>
          ${escapeHtml(view.label(row.metric))}
          <strong>${escapeHtml(view.formatValue ? view.formatValue(row.value) : formatMetricValue(row.value))}</strong>
        </span>
      `).join("")}
    </div>
  `;
  elements.metricDetail.textContent = `${view.description} Consulta: ${view.query}`;
}

async function loadObservability(viewKey = activeMetricView) {
  const view = METRIC_VIEWS[viewKey];
  try {
    elements.observabilityStatus.textContent = "Consultando";
    elements.observabilityStatus.className = "status-pill pending";
    const [instantSeries, rangeSeries] = await Promise.all([
      queryPrometheus(view.query),
      queryPrometheusRange(view.rangeQuery),
    ]);
    renderMetricChart(viewKey, instantSeries, rangeSeries);
    elements.observabilityStatus.textContent = "Prometheus OK · auto 5s";
    elements.observabilityStatus.className = "status-pill ok";
  } catch (error) {
    elements.metricChart.innerHTML = `<p class="panel-copy">No se pudo leer Prometheus: ${error.message}</p>`;
    elements.metricDetail.textContent = "Verifica que el contenedor prometheus esté arriba en Docker Compose.";
    elements.observabilityStatus.textContent = "Sin métricas";
    elements.observabilityStatus.className = "status-pill pending";
  }
}

async function refreshDashboard() {
  if (refreshing) return;
  refreshing = true;
  try {
    await request("/health");
    elements.apiStatus.textContent = "API disponible";
    elements.apiStatus.className = "status-pill ok";
    await Promise.all([loadSummary(), loadAccounts(), loadTransfers(), loadObservability()]);
  } catch (error) {
    elements.apiStatus.textContent = "API no disponible";
    elements.apiStatus.className = "status-pill pending";
    elements.transferResult.textContent = `No se pudo actualizar la consola: ${error.message}`;
  } finally {
    refreshing = false;
  }
}

async function submitTransfer(event) {
  event.preventDefault();
  if (elements.sourceAccount.value === elements.destinationAccount.value) {
    elements.transferResult.textContent = "La cuenta origen y destino deben ser diferentes.";
    return;
  }
  if (Number(elements.amount.value) <= 0) {
    elements.transferResult.textContent = "El monto debe ser mayor a cero.";
    return;
  }
  const idempotencyKey = generateKey();
  const payload = {
    source_account: elements.sourceAccount.value,
    destination_account: elements.destinationAccount.value,
    amount: elements.amount.value,
    currency: elements.currency.value.toUpperCase(),
    customer_id: elements.customerId.value,
  };

  try {
    elements.transferResult.textContent = "Procesando transferencia...";
    const transfer = await request("/v1/transfers", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
        "X-Correlation-Id": `ui-${idempotencyKey}`,
      },
      body: JSON.stringify(payload),
    });
    renderTransferResult(transfer);
    setTimeout(async () => {
      try {
        const currentTransfer = await request(`/v1/transfers/${transfer.id}`);
        renderTransferResult(currentTransfer);
      } finally {
        await refreshDashboard();
      }
    }, 900);
  } catch (error) {
    elements.transferResult.textContent = `No se pudo crear la transferencia: ${error.message}`;
  }
}

elements.transferForm.addEventListener("submit", submitTransfer);
elements.refreshButton.addEventListener("click", refreshDashboard);
elements.metricFilters.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-view]");
  if (!button) return;
  activeMetricView = button.dataset.view;
  [...elements.metricFilters.querySelectorAll("button[data-view]")].forEach((filterButton) => {
    filterButton.classList.toggle("active", filterButton.dataset.view === activeMetricView);
  });
  loadObservability(activeMetricView);
});

refreshDashboard();
setInterval(refreshDashboard, 5000);
