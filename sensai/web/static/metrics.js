"use strict";
// Tableau de bord EV3 : lit GET /api/metrics (calculé sur les logs JSONL) et dessine en SVG.
// Une seule série par graphique : pas de légende, le titre dit ce qui est tracé.

let current = null;     // dernière réponse de /api/metrics
let days = "";          // période choisie ("" : tout)

const number = (value, digits = 1) => value.toLocaleString("fr-FR", { maximumFractionDigits: digits });
const seconds = (value) => `${number(value)} s`;
const percent = (value) => `${number(value * 100)} %`;
const shortDay = (day) => new Date(`${day}T12:00:00`).toLocaleDateString("fr-FR", { day: "numeric", month: "short" });

// --- Tooltip (survol et focus clavier) ---

function showTooltip(event, rows) {
  const tooltip = $("#tooltip");
  tooltip.textContent = "";
  for (const [value, label] of rows) {
    tooltip.append(el("div", {}, el("strong", { text: value }), el("span", { class: "muted", text: ` ${label}` })));
  }
  tooltip.hidden = false;
  const box = event.target.getBoundingClientRect ? event.target.getBoundingClientRect() : null;
  const x = event.clientX ?? (box ? box.right : 0);
  const y = event.clientY ?? (box ? box.top : 0);
  const width = tooltip.offsetWidth;
  tooltip.style.left = `${Math.min(window.innerWidth - width - 8, x + 14)}px`;
  tooltip.style.top = `${y + 14 + window.scrollY}px`;
}

function hideTooltip() {
  $("#tooltip").hidden = true;
}

function hoverable(node, rows) {
  node.setAttribute("tabindex", "0");
  node.addEventListener("pointermove", (event) => showTooltip(event, rows));
  node.addEventListener("focus", (event) => showTooltip(event, rows));
  node.addEventListener("pointerleave", hideTooltip);
  node.addEventListener("blur", hideTooltip);
  return node;
}

// --- Axes ---

// Pas de graduation « rond » (1, 2, 2,5 ou 5 × 10^n) : 4 intervalles égaux couvrent la valeur max.
function niceStep(max, integer = false) {
  const raw = Math.max(max, integer ? 4 : 1e-9) / 4;
  const power = 10 ** Math.floor(Math.log10(raw));
  const steps = integer ? [1, 2, 5, 10] : [1, 2, 2.5, 5, 10];
  const step = steps.map((m) => m * power).find((candidate) => candidate >= raw);
  return integer ? Math.max(1, Math.ceil(step)) : step;
}

function frame(container, height) {
  const width = Math.max(280, container.clientWidth);
  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, width, height, role: "img" });
  container.textContent = "";
  container.append(root);
  return { root, width, height };
}

function yAxis(root, { left, right, top, bottom, max, format }) {
  for (let i = 0; i <= 4; i += 1) {
    const value = (max / 4) * i;      // max = 4 pas ronds : chaque graduation tombe juste
    const y = bottom - ((bottom - top) * i) / 4;
    root.append(svg("line", { x1: left, x2: right, y1: y, y2: y, class: i ? "grid" : "baseline" }),
      svg("text", { x: left - 6, y: y + 4, "text-anchor": "end", class: "tick" }, format(value)));
  }
}

// Colonne arrondie côté valeur, carrée sur la ligne de base.
function columnPath(x, y, width, base) {
  const r = Math.min(4, width / 2, (base - y) / 2);
  return `M${x},${base} V${y + r} Q${x},${y} ${x + r},${y} H${x + width - r} Q${x + width},${y} ${x + width},${y + r} V${base} Z`;
}

function barPath(x, y, length, thickness) {
  const r = Math.min(4, thickness / 2, length / 2);
  return `M${x},${y} H${x + length - r} Q${x + length},${y} ${x + length},${y + r} V${y + thickness - r} Q${x + length},${y + thickness} ${x + length - r},${y + thickness} H${x} Z`;
}

// --- Graphiques ---

function lineChart(container, points, format, label, tickFormat = format) {
  const { root, width, height } = frame(container, 220);
  const area = { left: 52, right: width - 24, top: 14, bottom: height - 28 };
  const max = 4 * niceStep(Math.max(...points.map((p) => p.value)) * 1.1);
  root.setAttribute("aria-label", `${label} : ${points.map((p) => `${p.label} ${format(p.value)}`).join(", ")}`);
  yAxis(root, { ...area, max, format: tickFormat });
  const step = points.length > 1 ? (area.right - area.left) / (points.length - 1) : 0;
  const xy = points.map((p, i) => [points.length > 1 ? area.left + i * step : (area.left + area.right) / 2,
    area.bottom - (p.value / max) * (area.bottom - area.top)]);
  if (points.length > 1) {
    root.append(svg("path", { d: xy.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join(" "), class: "series-line" }));
  }
  const labelEvery = Math.ceil(points.length / 8);
  points.forEach((point, i) => {
    if (i % labelEvery === 0 || i === points.length - 1) {
      root.append(svg("text", { x: xy[i][0], y: height - 8, "text-anchor": "middle", class: "tick" }, shortDay(point.label)));
    }
  });
  // Valeur directe sur le dernier point seulement ; le reste passe par l'axe et le survol.
  const [lastX, lastY] = xy[xy.length - 1];
  root.append(svg("text", { x: Math.min(lastX, area.right - 4), y: lastY - 10, "text-anchor": "end", class: "value-label" },
    format(points[points.length - 1].value)));
  const crosshair = svg("line", { y1: area.top, y2: area.bottom, class: "crosshair", visibility: "hidden" });
  root.append(crosshair);
  points.forEach((point, i) => {
    const dot = hoverable(svg("circle", { cx: xy[i][0], cy: xy[i][1], r: 4, class: "series-dot" }),
      [[format(point.value), shortDay(point.label)], ...point.extra]);
    root.append(dot);
  });
  // Le réticule trouve le jour le plus proche : on vise une date, pas un point de 8 px.
  const overlay = svg("rect", { x: area.left - 12, y: area.top, width: area.right - area.left + 24,
    height: area.bottom - area.top, class: "overlay" });
  overlay.addEventListener("pointermove", (event) => {
    const bounds = root.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width) * width;
    const i = step ? Math.max(0, Math.min(points.length - 1, Math.round((x - area.left) / step))) : 0;
    crosshair.setAttribute("x1", xy[i][0]);
    crosshair.setAttribute("x2", xy[i][0]);
    crosshair.setAttribute("visibility", "visible");
    showTooltip(event, [[format(points[i].value), shortDay(points[i].label)], ...points[i].extra]);
  });
  overlay.addEventListener("pointerleave", () => { crosshair.setAttribute("visibility", "hidden"); hideTooltip(); });
  root.insertBefore(overlay, crosshair);
}

function columnChart(container, points, format, label) {
  const { root, width, height } = frame(container, 220);
  const area = { left: 52, right: width - 16, top: 14, bottom: height - 28 };
  const max = 4 * niceStep(Math.max(...points.map((p) => p.value)), true);
  root.setAttribute("aria-label", `${label} : ${points.map((p) => `${p.label} ${format(p.value)}`).join(", ")}`);
  yAxis(root, { ...area, max, format: (v) => number(v, 0) });
  const slot = (area.right - area.left) / points.length;
  const thickness = Math.min(24, slot - 2);
  const labelEvery = Math.ceil(points.length / 8);
  points.forEach((point, i) => {
    const x = area.left + i * slot + (slot - thickness) / 2;
    const y = area.bottom - (point.value / max) * (area.bottom - area.top);
    root.append(hoverable(svg("path", { d: columnPath(x, y, thickness, area.bottom), class: "series-fill" }),
      [[format(point.value), shortDay(point.label)], ...point.extra]));
    if (i % labelEvery === 0 || i === points.length - 1) {
      root.append(svg("text", { x: x + thickness / 2, y: height - 8, "text-anchor": "middle", class: "tick" }, shortDay(point.label)));
    }
    if (i === points.length - 1) {
      root.append(svg("text", { x: x + thickness / 2, y: y - 6, "text-anchor": "middle", class: "value-label" }, format(point.value)));
    }
  });
}

function barChart(container, rows, format, label) {
  const thickness = 20;
  const gap = 14;
  const { root, width } = frame(container, rows.length * (thickness + gap) + 8);
  const left = 190;
  const right = width - 70;
  const max = Math.max(...rows.map((row) => row.value)) || 1;
  root.setAttribute("aria-label", `${label} : ${rows.map((r) => `${r.label} ${format(r.value)}`).join(", ")}`);
  rows.forEach((row, i) => {
    const y = 4 + i * (thickness + gap);
    const length = Math.max(2, ((right - left) * row.value) / max);
    root.append(
      svg("text", { x: left - 8, y: y + thickness / 2 + 4, "text-anchor": "end", class: "category" }, row.label),
      hoverable(svg("path", { d: barPath(left, y, length, thickness), class: row.emphasis ? "series-fill" : "deemph-fill" }), row.extra),
      svg("text", { x: left + length + 6, y: y + thickness / 2 + 4, class: "value-label" }, format(row.value)),
    );
  });
}

// --- Tables (la vue tableau de chaque graphique) ---

function table(node, headers, rows) {
  node.textContent = "";
  node.append(el("thead", {}, el("tr", {}, ...headers.map((h) => el("th", { text: h })))));
  node.append(el("tbody", {}, ...rows.map((cells) => el("tr", {}, ...cells.map((c) => el("td", { text: String(c) }))))));
}

function configText(config) {
  return Object.entries(config).map(([key, value]) => `${key}=${value}`).join(" · ");
}

// --- Rendu ---

function kpi(labelText, value, detail) {
  return el("div", { class: "panel kpi" }, el("span", { class: "kpi-label", text: labelText }),
    el("span", { class: "kpi-value", text: value }), el("span", { class: "muted small", text: detail }));
}

function render(data) {
  current = data;
  const empty = $("#empty");
  const content = $("#content");
  if (!data.enabled || !data.turns) {
    empty.hidden = false;
    content.hidden = true;
    empty.textContent = data.enabled
      ? "Aucun tour enregistré sur cette période."
      : "Logs désactivés : mettez enabled = true dans la section [logging] de config.toml.";
    return;
  }
  empty.hidden = true;
  content.hidden = false;
  $("#source-note").textContent = data.skipped ? `${data.skipped} ligne(s) de log illisible(s) ignorée(s)` : "";

  const tools = Object.entries(data.tool_calls);
  const kpis = $("#kpis");
  kpis.textContent = "";
  kpis.append(
    kpi("Tours", number(data.turns, 0), `${data.errors} erreur(s) · ${data.blocked} refus du filtre`),
    kpi("Latence moyenne", seconds(data.latency_mean), `p50 ${seconds(data.latency_p50)} · p95 ${seconds(data.latency_p95)}`),
    kpi("Taux d'erreur", percent(data.error_rate), "hors refus du filtre d'entrée"),
    kpi("Tokens générés", number(data.completion_tokens_mean), `par tour · ${number(data.prompt_tokens_mean, 0)} lus · contexte max ${data.context_tokens_max}`),
    kpi("Appels d'outils", number(tools.reduce((sum, [, count]) => sum + count, 0), 0),
      tools.slice(0, 3).map(([name, count]) => `${name} ×${count}`).join(" · ") || "aucun"),
  );

  const daily = (key) => data.by_day.map((day) => ({ label: day.day, value: day[key],
    extra: [[`${day.turns} tour(s)`, ""], [percent(day.error_rate), "d'erreurs"]] }));
  lineChart($("#latency-chart"), daily("latency_mean"), seconds, "Latence moyenne par jour",
    (value) => `${number(value, 2)} s`);
  columnChart($("#volume-chart"), daily("turns"), (v) => number(v, 0), "Tours par jour");

  const configs = data.by_config;
  barChart($("#config-chart"), configs.map((group, i) => ({
    label: `${group.config.model || "?"} · depuis le ${shortDay(group.since.slice(0, 10))}`,
    value: group.latency_mean,
    emphasis: i === configs.length - 1,
    extra: [[seconds(group.latency_mean), `latence moyenne · ${group.turns} tour(s) · configuration ${group.config_id.slice(0, 6)}`],
      [`depuis ${new Date(group.since).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}`, ""],
      [configText(group.config), ""]],
  })), seconds, "Latence moyenne par configuration");

  table($("#model-table"), ["Modèle", "Tours", "Latence moy.", "p95", "Erreurs", "Tokens générés"],
    data.by_model.map((g) => [g.model, g.turns, seconds(g.latency_mean), seconds(g.latency_p95), percent(g.error_rate), number(g.completion_tokens_mean)]));
  table($("#config-table"), ["Configuration", "Depuis", "Tours", "Latence moy.", "Réglages"],
    configs.map((g) => [g.config_id.slice(0, 6), g.since.replace("T", " "), g.turns, seconds(g.latency_mean), configText(g.config)]));
  table($("#recent-table"), ["Heure", "Modèle", "État", "Latence", "Tokens lus", "Tokens générés", "Outils"],
    data.recent.map((r) => [r.timestamp.replace("T", " "), r.model,
      r.status === "ok" ? "abouti" : r.status === "blocked" ? "refusé (filtre)" : `erreur : ${r.error}`,
      seconds(r.latency_s), r.prompt_tokens, r.completion_tokens, r.tools.join(", ") || "—"]));
}

async function load() {
  const content = $("#content");
  content.classList.add("loading");     // le cadre reste en place pendant le rechargement
  try {
    render(await api(`/api/metrics${days ? `?days=${days}` : ""}`));
  } catch (error) {
    $("#empty").hidden = false;
    $("#empty").textContent = `Métriques indisponibles : ${error.message}`;
  } finally {
    content.classList.remove("loading");
  }
}

for (const button of document.querySelectorAll(".filter-row button")) {
  button.addEventListener("click", () => {
    days = button.dataset.days;
    for (const other of document.querySelectorAll(".filter-row button")) other.classList.toggle("selected", other === button);
    load();
  });
}

let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => current && render(current), 150);
});

load();
