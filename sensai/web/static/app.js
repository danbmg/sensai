"use strict";
// Interface web de Sensai : n'affiche que ce que renvoie l'API (/api/...), sans logique métier.

const state = {
  session: null,          // consultation affichée (réponse de GET /api/sessions/{id})
  status: null,           // GET /api/status
  config: null,           // GET /api/config
  controller: null,       // AbortController du tour en cours (bouton Arrêter)
};

// --- Utilitaires (el, api, $ : common.js) ---

function formatArgs(args) {
  return Object.entries(args || {}).map(([key, value]) =>
    `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`).join(", ");
}

// Message bref en bas de l'écran (au lieu d'alert(), qui bloque la page).
let toastTimer = null;

function notify(message, kind = "error") {
  const toast = $("#toast");
  toast.textContent = message;
  toast.className = `toast ${kind}`;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 7000);
}

function scrollDown() {
  const messages = $("#messages");
  messages.scrollTop = messages.scrollHeight;
}

// Texte de réponse, avec les références [S1], [S2]… mises en évidence.
function renderAnswer(node, text) {
  node.textContent = "";
  for (const part of text.split(/(\[S\d+\])/)) {
    node.append(/^\[S\d+\]$/.test(part) ? el("span", { class: "cite", text: part }) : part);
  }
}

// --- Barre du haut : état, modèles, réglages ---

async function loadStatus() {
  state.status = await api("/api/status");
  const { model, rag, mcp, logs } = state.status;
  const chips = $("#status-chips");
  chips.textContent = "";
  chips.append(
    el("span", { class: `chip ${model.ok ? "on" : "bad"}`, text: model.ok ? `Ollama · ${model.name}` : "Ollama indisponible" }),
    el("span", { class: `chip ${rag.active ? "on" : ""}`, text: rag.active ? `RAG · ${rag.documents} document(s)` : (rag.enabled ? "RAG : index vide" : "RAG désactivé") }),
    el("span", { class: `chip ${mcp ? "on" : ""}`, text: mcp ? "Outils via MCP" : "Outils locaux" }),
    el("span", { class: `chip ${logs.enabled ? "on" : ""} ${logs.error ? "bad" : ""}`, text: logs.enabled ? "Logs actifs" : "Logs désactivés" }),
  );
  const banner = $("#model-banner");
  banner.hidden = model.ok && !model.warning && !logs.error;
  banner.className = `banner ${model.ok ? "warn" : ""}`;
  banner.textContent = model.ok ? (model.warning || logs.error) : model.error;

  const tools = $("#tools");
  tools.textContent = "";
  for (const tool of state.status.tools) {
    tools.append(el("li", { title: tool.description }, el("code", { text: tool.name }),
      tool.dangerous ? el("span", { class: "dangerous", text: " · validation du médecin" }) : null));
  }
}

async function loadModels() {
  const select = $("#model-select");
  try {
    const { current, models } = await api("/api/models");
    select.textContent = "";
    for (const name of models.includes(current) ? models : [current, ...models]) {
      select.append(el("option", { value: name, text: name }));
    }
    select.value = current;
  } catch (error) {
    select.textContent = "";
    select.append(el("option", { text: state.status ? state.status.model.name : "?" }));
  }
}

async function switchModel(event) {
  const select = event.target;
  const previous = state.config.model;
  select.disabled = true;
  try {
    const result = await api("/api/config", { method: "PUT", body: { model: select.value } });
    state.config = result;
    notify(result.warning || `Modèle actif : ${result.model}`, result.warning ? "warn" : "info");
  } catch (error) {
    notify(`Modèle refusé : ${error.message}`);
    select.value = previous;
  } finally {
    select.disabled = false;
    await loadStatus();
  }
}

function openSettings() {
  const form = $("#settings-form");
  for (const name of ["temperature", "num_predict", "num_ctx", "max_history_turns", "max_tool_iterations"]) {
    form.elements[name].value = state.config[name];
  }
  $("#settings-error").hidden = true;
  $("#settings-dialog").showModal();
}

async function saveSettings(event) {
  if (event.submitter && event.submitter.value !== "save") return;
  event.preventDefault();
  const form = $("#settings-form");
  const body = {};
  for (const name of ["temperature", "num_predict", "num_ctx", "max_history_turns", "max_tool_iterations"]) {
    body[name] = Number(form.elements[name].value);
  }
  try {
    state.config = await api("/api/config", { method: "PUT", body });
    $("#settings-dialog").close();
  } catch (error) {
    $("#settings-error").textContent = error.message;
    $("#settings-error").hidden = false;
  }
}

// --- Consultations ---

async function loadChoices() {
  const [patients, profiles] = await Promise.all([api("/api/patients"), api("/api/profiles")]);
  const patientSelect = $("#patient-select");
  for (const patient of patients) {
    patientSelect.append(el("option", { value: patient.patient_id, text: patient.name }));
  }
  const profileSelect = $("#profile-select");
  for (const profile of profiles) {
    profileSelect.append(el("option", { value: profile.profile_id,
      text: profile.specialty ? `${profile.profile_id} — ${profile.specialty}` : profile.profile_id }));
  }
}

async function loadSessions() {
  const sessions = await api("/api/sessions");
  const list = $("#session-list");
  list.textContent = "";
  if (!sessions.length) list.append(el("li", { class: "muted small", text: "Aucune consultation enregistrée." }));
  for (const session of sessions) {
    const date = session.updated_at ? new Date(session.updated_at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "";
    const button = el("button", { type: "button", onclick: () => openSession(session.session_id) },
      el("span", { class: "title", text: session.patient_name || "Sans dossier patient" }),
      el("span", { class: "meta", text: `${session.messages} message(s) · ${session.profile_id}${date ? " · " + date : ""}` }));
    if (state.session && state.session.session_id === session.session_id) button.classList.add("active");
    list.append(el("li", {}, button));
  }
}

async function createSession(event) {
  event.preventDefault();
  try {
    const session = await api("/api/sessions", { method: "POST", body: {
      patient: $("#patient-select").value || null, profile: $("#profile-select").value || null } });
    await openSession(session.session_id);
  } catch (error) {
    notify(error.message);
  }
}

async function openSession(sessionId) {
  state.session = await api(`/api/sessions/${encodeURIComponent(sessionId)}`);
  localStorageSet("sensai.session", sessionId);
  await renderPatientHeader();
  const messages = $("#messages");
  messages.textContent = "";
  renderHistory(state.session.history);
  renderSources(state.session.sources);
  const filters = state.session.filters;
  $("#filter-publisher").value = filters.publisher || "";
  $("#filter-tags").value = (filters.tags || []).join(", ");
  for (const control of [$("#message-input"), $("#send"), $("#filters button"), $("#prompt-open")]) control.disabled = false;
  resetGauge();
  await loadSessions();
  $("#message-input").focus();
  scrollDown();
}

async function renderPatientHeader() {
  const header = $("#patient-header");
  header.textContent = "";
  const { patient, profile, session_id } = state.session;
  const meta = `Profil ${profile ? profile.profile_id : "default"} · session ${session_id.slice(0, 8)}`;
  if (!patient) {
    header.append(el("h1", { text: "Consultation sans dossier patient" }), el("p", { class: "muted small", text: meta }));
    return;
  }
  const record = await api(`/api/patients/${encodeURIComponent(patient.patient_id)}`);
  const facts = el("div", { class: "facts" });
  for (const allergy of record.allergies) facts.append(el("span", { class: "fact allergy", text: `Allergie : ${allergy}` }));
  for (const treatment of record.treatments) facts.append(el("span", { class: "fact", text: treatment }));
  for (const item of record.medical_history) facts.append(el("span", { class: "fact", text: item }));
  const born = record.birth_date ? ` · naissance ${new Date(`${record.birth_date}T12:00:00`).toLocaleDateString("fr-FR")}` : "";
  header.append(el("h1", { text: `${record.name}${born}` }),
    el("p", { class: "muted small", text: meta }), facts);
}

function localStorageSet(key, value) {
  try { localStorage.setItem(key, value); } catch (error) { /* navigation privée : sans importance */ }
}

function localStorageGet(key) {
  try { return localStorage.getItem(key); } catch (error) { return null; }
}

// --- Affichage des messages ---

function addMessage(role, text) {
  const node = el("div", { class: `msg ${role}` });
  if (role === "assistant") renderAnswer(node, text); else node.textContent = text;
  $("#messages").append(node);
  return node;
}

function addEvent(kind, text) {
  const node = el("div", { class: `event ${kind}`, text });
  $("#messages").append(node);
  return node;
}

// Un résultat d'outil long (dossier complet en JSON) se replie : la conversation reste lisible.
function addToolResult(tool, content, failed = false) {
  const kind = `tool-result ${failed ? "failed" : ""}`;
  if (content.length <= 160) return addEvent(kind, `← ${content}`);
  const node = el("div", { class: `event ${kind}` },
    el("details", {}, el("summary", { text: `← résultat de ${tool} (${content.length} caractères)` }), content));
  $("#messages").append(node);
  return node;
}

function renderHistory(history) {
  for (const message of history) {
    if (message.role === "user") addMessage("user", message.content);
    else if (message.role === "assistant") {
      if (message.content) addMessage("assistant", message.content);
      for (const call of message.tool_calls || []) {
        addEvent("tool-call", `→ ${call.function.name}(${formatArgs(call.function.arguments)})`);
      }
    } else if (message.role === "tool") addToolResult(message.tool_name || "l'outil", message.content);
  }
}

function renderSources(sources) {
  const list = $("#sources");
  list.textContent = "";
  if (!sources || !sources.length) {
    list.append(el("li", { class: "muted small", text: "Aucune source." }));
    return;
  }
  for (const source of sources) {
    list.append(el("li", {},
      el("strong", { text: `[${source.citation}] ` }),
      el("a", { href: source.source, target: "_blank", rel: "noopener", text: source.title }),
      el("div", { class: "muted", text: `${source.publisher} · page ${source.page} · pertinence ${source.relevance.toFixed(2).replace(".", ",")}` })));
  }
}

function resetGauge() {
  $("#gauge-fill").style.width = "0";
  $("#gauge-label").textContent = "Aucun tour pour l'instant.";
  $("#usage-label").textContent = "";
}

function renderUsage(usage, seconds) {
  const limit = usage.context_window || 0;
  const ratio = limit ? Math.min(1, usage.context_tokens / limit) : 0;
  const fill = $("#gauge-fill");
  fill.style.width = `${Math.round(ratio * 100)}%`;
  fill.className = `gauge-fill ${ratio >= 0.95 ? "full" : ratio >= 0.75 ? "high" : ""}`;
  $("#gauge").setAttribute("aria-label", `Contexte occupé : ${usage.context_tokens} sur ${limit} tokens`);
  $("#gauge-label").textContent = limit
    ? `${usage.context_tokens} / ${limit} tokens de contexte (${Math.round(ratio * 100)} %)`
    : `${usage.context_tokens} tokens de contexte`;
  $("#usage-label").textContent = `Dernier tour : ${usage.prompt_tokens} tokens lus, ${usage.completion_tokens} générés en ${seconds.toFixed(1).replace(".", ",")} s`;
}

// --- Un tour de conversation (SSE lu avec fetch : EventSource ne fait que du GET) ---

async function readEvents(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let type = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) type = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      onEvent(type, data ? JSON.parse(data) : null);
    }
  }
}

async function send(event) {
  event.preventDefault();
  const input = $("#message-input");
  const text = input.value.trim();
  if (!text || state.controller) return;
  input.value = "";
  addMessage("user", text);
  let answer = null;
  let answerText = "";
  const started = performance.now();
  setBusy(true);
  state.controller = new AbortController();

  const onEvent = (type, data) => {
    if (type === "token") {
      if (!answer) answer = addMessage("assistant", "");
      answer.classList.add("pending");
      answerText += data;
      answer.textContent = answerText;
    } else {
      if (answer) { renderAnswer(answer, answerText); answer.classList.remove("pending"); }
      answer = null;
      answerText = "";
      if (type === "tool_call") addEvent("tool-call", `→ ${data.tool}(${formatArgs(data.args)})`);
      else if (type === "confirm") askConfirmation(data);
      else if (type === "tool_result") addToolResult(data.tool, data.content, data.is_error);
      else if (type === "error") addEvent("error", data);
      else if (type === "usage") {
        const seconds = (performance.now() - started) / 1000;
        renderUsage(data, seconds);
        const limit = data.context_window ? `/${data.context_window}` : "";
        $("#messages").append(el("div", { class: "meta-line",
          text: `${data.prompt_tokens} tokens lus · ${data.completion_tokens} générés · contexte ${data.context_tokens}${limit} · ${seconds.toFixed(1).replace(".", ",")} s` }));
      } else if (type === "sources") {
        renderSources(data);
        $("#messages").append(el("div", { class: "source-chips" }, ...data.map((source) =>
          el("a", { href: source.source, target: "_blank", rel: "noopener", text: `[${source.citation}] ${source.title} — p. ${source.page}` }))));
      }
    }
    scrollDown();
  };

  try {
    const response = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.session.session_id, message: text }),
      signal: state.controller.signal,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || response.statusText);
    }
    await readEvents(response, onEvent);
  } catch (error) {
    addEvent("error", error.name === "AbortError" ? "Génération interrompue : ce tour n'est pas enregistré." : error.message);
  } finally {
    if (answer) { renderAnswer(answer, answerText); answer.classList.remove("pending"); }
    state.controller = null;
    setBusy(false);
    closeConfirmation();
    scrollDown();
    loadSessions().catch(() => {});
  }
}

function setBusy(busy) {
  $("#send").disabled = busy;
  $("#stop").hidden = !busy;
  $("#message-input").disabled = busy;
  if (!busy) $("#message-input").focus();
}

// --- Validation humaine (A3) ---

let countdown = null;

function askConfirmation({ id, tool, args }) {
  const dialog = $("#confirm-dialog");
  dialog.dataset.id = id;
  $("#confirm-tool").textContent = tool;
  const list = $("#confirm-args");
  list.textContent = "";
  for (const [key, value] of Object.entries(args)) {
    list.append(el("dt", { text: key }), el("dd", { text: typeof value === "string" ? value : JSON.stringify(value) }));
  }
  let remaining = Math.round(state.status.confirm_timeout);
  const tick = () => { $("#confirm-countdown").textContent = `Sans réponse dans ${remaining} s, l'action sera refusée.`; };
  tick();
  clearInterval(countdown);
  countdown = setInterval(() => { remaining -= 1; tick(); if (remaining <= 0) closeConfirmation(); }, 1000);
  dialog.showModal();
}

async function answerConfirmation(approved) {
  const dialog = $("#confirm-dialog");
  const id = dialog.dataset.id;
  closeConfirmation();
  if (!id) return;
  try {
    await api(`/api/confirm/${encodeURIComponent(id)}`, { method: "POST", body: { approved } });
  } catch (error) {
    addEvent("error", `Validation non prise en compte : ${error.message}`);
  }
}

function closeConfirmation() {
  clearInterval(countdown);
  const dialog = $("#confirm-dialog");
  delete dialog.dataset.id;
  if (dialog.open) dialog.close();
}

// --- Prompt envoyé, filtres ---

async function showPrompt() {
  try {
    const prompt = await api(`/api/sessions/${encodeURIComponent(state.session.session_id)}/prompt`);
    $("#prompt-meta").textContent = `Reçu par ${prompt.model} · pseudonymisé · outils proposés : ${prompt.tools.join(", ") || "aucun"} · ${prompt.context_tokens} tokens de contexte`;
    $("#prompt-body").textContent = JSON.stringify(prompt.messages, null, 2);
  } catch (error) {
    $("#prompt-meta").textContent = error.message;
    $("#prompt-body").textContent = "";
  }
  $("#prompt-dialog").showModal();
}

async function applyFilters(event) {
  event.preventDefault();
  const tags = $("#filter-tags").value.split(",").map((tag) => tag.trim()).filter(Boolean);
  try {
    await api(`/api/sessions/${encodeURIComponent(state.session.session_id)}/filters`, {
      method: "PUT", body: { publisher: $("#filter-publisher").value || null, tags } });
    renderSources([]);
    notify("Filtres appliqués à la prochaine recherche.", "info");
  } catch (error) {
    notify(error.message);
  }
}

// --- Démarrage ---

function bind() {
  $("#model-select").addEventListener("change", switchModel);
  $("#settings-open").addEventListener("click", openSettings);
  $("#settings-form").addEventListener("submit", saveSettings);
  $("#new-session").addEventListener("submit", createSession);
  $("#composer").addEventListener("submit", send);
  $("#message-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("#composer").requestSubmit(); }
  });
  $("#stop").addEventListener("click", () => state.controller && state.controller.abort());
  $("#confirm-approve").addEventListener("click", (event) => { event.preventDefault(); answerConfirmation(true); });
  $("#confirm-refuse").addEventListener("click", (event) => { event.preventDefault(); answerConfirmation(false); });
  $("#confirm-dialog").addEventListener("cancel", (event) => { event.preventDefault(); answerConfirmation(false); });
  $("#prompt-open").addEventListener("click", showPrompt);
  $("#filters").addEventListener("submit", applyFilters);
}

async function start() {
  bind();
  try {
    await loadStatus();
    state.config = await api("/api/config");
    await Promise.all([loadModels(), loadChoices(), loadSessions()]);
    const last = localStorageGet("sensai.session");
    if (last) await openSession(last).catch(() => {});
  } catch (error) {
    const banner = $("#model-banner");
    banner.hidden = false;
    banner.textContent = `Serveur Sensai injoignable : ${error.message}`;
  }
  setInterval(() => loadStatus().catch(() => {}), 30000);
}

start();
