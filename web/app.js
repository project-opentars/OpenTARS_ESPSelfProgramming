"use strict";
// openTARS Self-Programming: a página servida pela placa. Sem framework e sem build: o tools/build_web.py só comprime.

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------- textos (en / pt) ----------------
const I18N = {
  en: {
    skip: "Skip to content", tab_chat: "Chat", tab_programs: "Programs", tab_code: "Code", tab_network: "Boards", tab_settings: "Settings",
    offline: "Board not answering. Retrying…", empty_title: "Ask the board to program itself.",
    s1: "Make the LED breathe blue", s2: "Show a spinning 3D cube on the screen", s3: "What is connected to you?", s4: "Which other boards can you see?",
    prompt_label: "Message", prompt_ph: "Tell the board what to do…", send: "Send", stop: "Stop",
    programs: "Programs", stop_all: "Stop all", programs_hint: "Programs run in the background. Hold BOOT while powering on to skip the ones that start automatically.",
    new_file: "New file", run: "Run", save: "Save", delete: "Delete", close: "Close",
    system_file: "System file: a mistake here can stop the board from starting (fix it over USB).", quick_run: "Quick run",
    this_board: "This board", other_boards: "Other boards (ESP-NOW)",
    espnow_hint: "Boards find each other by themselves when they are on the same Wi-Fi channel. Boards on your Wi-Fi use the router's channel; boards without Wi-Fi use the channel set in Settings.",
    to: "To", message: "Message or code", send_text: "Send as text", run_there: "Run there", received: "Received",
    model: "Model", provider: "Provider", custom: "Other (OpenAI-compatible)",
    ollama_hint: "The model runs on your computer. Type your computer's IP on this Wi-Fi in the address below (not localhost), and make Ollama listen on the network: OLLAMA_HOST=0.0.0.0, then restart Ollama.",
    base_url: "Address", api_key: "API key", model_name: "Model name", load_models: "List models", scan: "Scan", password: "Password",
    board: "Board", board_name: "Name on the network", channel: "ESP-NOW channel when there is no Wi-Fi", oled_pins: "OLED screen (I2C)",
    tpm: "Provider limit, tokens per minute (0 = unknown; it learns it from a 429)", max_tokens: "Max reply tokens (lower is kinder to free plans)",
    rgb_pin: "Onboard RGB LED pin", tz: "Time zone (hours from UTC, e.g. -3 for São Paulo)", model_busy: "model busy, trying again", maintenance: "Maintenance", reboot: "Restart board", clear_chat: "Clear conversation",
    security: "No password: anyone on this Wi-Fi can open this page and run code on the board.",
    thinking: "thinking…", working: "running tools…", busy: "The board is still working on the last request.",
    no_programs: "No programs yet. Ask the board to make one.", log: "Log", run_again: "Run again", autostart: "Start on power-on",
    no_peers: "No other boards seen yet.", open_page: "Open its page", seen: "seen %s s ago", empty_folder: "Empty folder",
    saved: "Saved.", saved_reboot: "Saved. Restart the board: it will leave this network and join %s. Then put your phone back on %s and open http://%s.local (or the IP shown on the board's screen).", confirm_delete: "Delete %s?",
    confirm_reboot: "Restart the board now?", confirm_clear: "Erase the conversation history on the board?", restarting: "Restarting…",
    new_file_name: "File name (in %s):", key_kept: "leave empty to keep the saved key", models_found: "%s models", own_network: "own Wi-Fi",
    wifi: "Wi-Fi", free: "free", keep_ssid: "(keep current)", stopped_msg: "Stopped.", result: "Result", mode: "Mode", ip: "IP",
    name: "Name", mac: "MAC", chan: "Channel", version: "Version", running: "running", done: "done", error: "error", stopped: "stopped", starting: "starting",
  },
  pt: {
    skip: "Pular para o conteúdo", tab_chat: "Conversa", tab_programs: "Programas", tab_code: "Código", tab_network: "Placas", tab_settings: "Ajustes",
    offline: "A placa não está respondendo. Tentando de novo…", empty_title: "Peça para a placa se programar.",
    s1: "Faça o LED respirar em azul", s2: "Mostre um cubo 3D girando na tela", s3: "O que está ligado em você?", s4: "Quais outras placas você vê?",
    prompt_label: "Mensagem", prompt_ph: "Diga o que a placa deve fazer…", send: "Enviar", stop: "Parar",
    programs: "Programas", stop_all: "Parar todos", programs_hint: "Os programas rodam em segundo plano. Segure o BOOT ao ligar para pular os que iniciam sozinhos.",
    new_file: "Novo arquivo", run: "Rodar", save: "Salvar", delete: "Apagar", close: "Fechar",
    system_file: "Arquivo do sistema: um erro aqui pode impedir a placa de ligar (conserta pelo USB).", quick_run: "Rodar rápido",
    this_board: "Esta placa", other_boards: "Outras placas (ESP-NOW)",
    espnow_hint: "As placas se encontram sozinhas quando estão no mesmo canal de Wi-Fi. As que estão no seu Wi-Fi usam o canal do roteador; as sem Wi-Fi usam o canal definido em Ajustes.",
    to: "Para", message: "Mensagem ou código", send_text: "Enviar como texto", run_there: "Rodar lá", received: "Recebidas",
    model: "Modelo", provider: "Provedor", custom: "Outro (compatível com OpenAI)",
    ollama_hint: "O modelo roda no seu computador. Digite abaixo o IP do computador neste Wi-Fi (não localhost) e faça o Ollama escutar na rede: OLLAMA_HOST=0.0.0.0 e reinicie o Ollama.",
    base_url: "Endereço", api_key: "Chave da API", model_name: "Nome do modelo", load_models: "Listar modelos", scan: "Procurar", password: "Senha",
    board: "Placa", board_name: "Nome na rede", channel: "Canal do ESP-NOW quando não há Wi-Fi", oled_pins: "Tela OLED (I2C)",
    tpm: "Limite do provedor, tokens por minuto (0 = desconhecido; ele aprende com um erro 429)", max_tokens: "Máximo de tokens da resposta (menor é melhor em planos grátis)",
    rgb_pin: "Pino do LED RGB da placa", tz: "Fuso horário (horas em relação ao UTC, ex.: -3 em São Paulo)", model_busy: "modelo ocupado, tentando de novo", maintenance: "Manutenção", reboot: "Reiniciar a placa", clear_chat: "Apagar a conversa",
    security: "Sem senha: qualquer pessoa neste Wi-Fi pode abrir esta página e rodar código na placa.",
    thinking: "pensando…", working: "usando ferramentas…", busy: "A placa ainda está trabalhando no pedido anterior.",
    no_programs: "Nenhum programa ainda. Peça para a placa criar um.", log: "Saída", run_again: "Rodar de novo", autostart: "Iniciar ao ligar",
    no_peers: "Nenhuma outra placa encontrada ainda.", open_page: "Abrir a página dela", seen: "vista há %s s", empty_folder: "Pasta vazia",
    saved: "Salvo.", saved_reboot: "Salvo. Reinicie a placa: ela sai desta rede e entra na %s. Depois volte o celular para a %s e abra http://%s.local (ou o IP que aparece na tela da placa).", confirm_delete: "Apagar %s?",
    confirm_reboot: "Reiniciar a placa agora?", confirm_clear: "Apagar o histórico da conversa na placa?", restarting: "Reiniciando…",
    new_file_name: "Nome do arquivo (em %s):", key_kept: "deixe vazio para manter a chave salva", models_found: "%s modelos", own_network: "Wi-Fi próprio",
    wifi: "Wi-Fi", free: "livre", keep_ssid: "(manter o atual)", stopped_msg: "Parado.", result: "Resultado", mode: "Modo", ip: "IP",
    name: "Nome", mac: "MAC", chan: "Canal", version: "Versão", running: "rodando", done: "terminou", error: "erro", stopped: "parado", starting: "iniciando",
  },
};
Object.assign(I18N.en, {
  advanced: "Board and hardware (advanced)", devmode: "Developer mode: allow editing system files", copy: "Copy", copied: "Copied", copy_manual: "Selected: copy it",
  readonly_sys: "System file (read-only). Turn on developer mode in Settings to edit it.", tech_details: "Technical details",
  computer: "Computer", harness: "AI program", harness_model: "Model (optional)", auto_pick: "Automatic",
  bridge_off: "No computer connected", bridge_on: "Connected", bridge_hint: "On the computer that has an AI program installed (claude, codex, opencode, pi or grok), open a terminal and paste:",
  wifi_first: "First put the board on your Wi-Fi: Settings, Wi-Fi. Then come back here.", wifi_network: "Network", wifi_connect: "Connect",
  wifi_own: "The board's own network (no internet)", wifi_lost: "Wi-Fi not connected", wifi_trying: "Connecting…",
  wifi_ok: "Connected. New address: %s. Put your phone back on that Wi-Fi and open it.",
});
Object.assign(I18N.pt, {
  advanced: "Placa e hardware (avançado)", devmode: "Modo desenvolvedor: permitir editar arquivos do sistema", copy: "Copiar", copied: "Copiado", copy_manual: "Selecionado: copie",
  readonly_sys: "Arquivo do sistema (só leitura). Ligue o modo desenvolvedor em Ajustes para editar.", tech_details: "Detalhes técnicos",
  computer: "Computador", harness: "Programa de IA", harness_model: "Modelo (opcional)", auto_pick: "Automático",
  bridge_off: "Nenhum computador conectado", bridge_on: "Conectado", bridge_hint: "No computador que tem um programa de IA instalado (claude, codex, opencode, pi ou grok), abra um terminal e cole:",
  wifi_first: "Primeiro ponha a placa no seu Wi-Fi: Ajustes, Wi-Fi. Depois volte aqui.", wifi_network: "Rede", wifi_connect: "Conectar",
  wifi_own: "Rede própria da placa (sem internet)", wifi_lost: "Wi-Fi desconectado", wifi_trying: "Conectando…",
  wifi_ok: "Conectado. Novo endereço: %s. Volte o celular para esse Wi-Fi e abra-o.",
});
let lang = (() => {
  try { const s = localStorage.getItem("lang"); if (s) return s; } catch (e) { /* armazenamento bloqueado */ }
  return (navigator.language || "en").toLowerCase().startsWith("pt") ? "pt" : "en";
})();
const t = (k, ...a) => { let s = (I18N[lang] && I18N[lang][k]) || I18N.en[k] || k; a.forEach((v) => { s = s.replace("%s", v); }); return s; };

function applyI18n() {
  document.documentElement.lang = lang === "pt" ? "pt-BR" : "en";
  $$("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $$("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  $("#lang").textContent = lang === "pt" ? "EN" : "PT";
}

// ---------------- API ----------------
async function api(path, { method = "GET", body, timeout = 15000, raw = false } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  try {
    const opts = { method, signal: ctl.signal };
    if (body !== undefined) {
      opts.body = typeof body === "string" ? body : JSON.stringify(body);
      opts.headers = { "Content-Type": typeof body === "string" ? "text/plain" : "application/json" };
    }
    const r = await fetch(path, opts);
    if (raw) { if (!r.ok) throw new Error("HTTP " + r.status); return await r.text(); }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(data.error || "HTTP " + r.status); e.status = r.status; throw e; }
    return data;
  } finally { clearTimeout(timer); }
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Markdown pequeno: blocos ```, `código`, **negrito**, parágrafos. Tudo escapado antes.
function md(text) {
  const parts = String(text ?? "").split(/```/);
  return parts.map((chunk, i) => {
    if (i % 2 === 1) return "<pre>" + esc(chunk.replace(/^[a-zA-Z0-9_+-]*\n/, "")) + "</pre>";
    return esc(chunk).split(/\n{2,}/).filter((p) => p.trim()).map((p) =>
      "<p>" + p.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>") + "</p>").join("");
  }).join("");
}

// ---------------- KIPP (o mascote do openTARS, em pixel art) ----------------
const KIPP = (() => {
  const cv = $("#kipp"), ctx = cv.getContext("2d"), P = 3, COLS = [0, 6, 12, 18];
  const C = { claro: "#F4F6FB", meio: "#D3DAEC", escuro: "#8E9ABF", contorno: "#0B1020", neon: "#39FF88", brilho: "#B6FFD2", sombra: "#1FC968" };
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let state = "idle", until = 0;
  const px = (x, y, c) => { if (x >= 0 && x < 23 && y >= 0 && y < 25) { ctx.fillStyle = c; ctx.fillRect(x * P, y * P, P, P); } };
  function lifts(now) {
    if (state === "working") return [0, 1, 2, 3].map((i) => (Math.sin(now * 14 - i * 1.4) > 0.2 ? 1 : 0));
    if (state === "error") return [-1, -2, -2, -1];
    if (state === "happy") return [2, 0, 0, 2];
    if (state === "thinking") return Array(4).fill(Math.sin(now * 2.2) > 0.5 ? 1 : 0);
    return [0, 0, 0, 0];
  }
  function draw(now) {
    if (until && now > until) { state = "idle"; until = 0; }
    ctx.clearRect(0, 0, cv.width, cv.height);
    const up = reduce ? [0, 0, 0, 0] : lifts(now);
    COLS.forEach((x0, i) => {
      const top = 4 - up[i], bot = 23 - Math.max(0, up[i]);
      for (let y = top; y <= bot; y++) for (let dx = 0; dx < 5; dx++) {
        if ((y === top || y === bot) && (dx === 0 || dx === 4)) continue;
        px(x0 + dx, y, dx === 0 ? C.claro : dx === 4 ? C.escuro : C.meio);
      }
      for (let dx = 1; dx < 4; dx++) { px(x0 + dx, top - 1, C.contorno); px(x0 + dx, bot + 1, C.contorno); }
      px(x0 + 2, bot - 5, C.escuro); px(x0 + 2, bot - 2, C.escuro);
    });
    const t0 = 8 - Math.min(up[1], up[2]);
    for (let y = t0; y < t0 + 6; y++) for (let x = 2; x < 21; x++) {
      if ((y === t0 || y === t0 + 5) && (x === 2 || x === 20)) continue;
      px(x, y, y === t0 ? C.brilho : y === t0 + 5 ? C.sombra : C.neon);
    }
    const c = C.contorno, blink = !reduce && (now % 4.2) < 0.12;
    for (const ex of [7, 14]) {
      if (state === "happy") { px(ex, t0 + 2, c); px(ex + 1, t0 + 2, c); px(ex - 1, t0 + 3, c); px(ex + 2, t0 + 3, c); }
      else if (state === "working") { px(ex, t0 + 3, c); px(ex + 1, t0 + 3, c); px(ex, t0 + (ex === 7 ? 0 : 1), c); px(ex + 1, t0 + (ex === 7 ? 1 : 0), c); }
      else if (state === "error") { px(ex, t0 + 3, c); px(ex + 1, t0 + 3, c); px(ex, t0 + (ex === 7 ? 1 : 0), c); px(ex + 1, t0 + (ex === 7 ? 0 : 1), c); }
      else if (state === "thinking") { px(ex + 1, t0 + 1, c); px(ex + 2, t0 + 1, c); }
      else if (blink) { px(ex, t0 + 3, c); px(ex + 1, t0 + 3, c); }
      else { for (const dy of [2, 3]) { px(ex, t0 + dy, c); px(ex + 1, t0 + dy, c); } }
    }
    if (state === "happy") { px(9, t0 + 4, c); px(13, t0 + 4, c); for (const x of [10, 11, 12]) px(x, t0 + 5, c); }
    if (state === "error") { for (const x of [10, 11, 12]) px(x, t0 + 4, c); px(9, t0 + 5, c); px(13, t0 + 5, c); }
    if (state === "thinking" && !reduce) for (const x of [8, 11, 14].slice(0, Math.floor(now * 3) % 4)) px(x, 0, C.claro);
  }
  let last = 0;
  function loop(ms) { if (ms - last > 90) { draw(ms / 1000); last = ms; } requestAnimationFrame(loop); }
  requestAnimationFrame(loop);
  return { set(s, forMs) { state = s; until = forMs ? performance.now() / 1000 + forMs / 1000 : 0; } };
})();

// ---------------- navegação ----------------
let view = "chat";
function show(v) {
  view = v;
  $$(".tabs button").forEach((b) => { if (b.dataset.view === v) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  $$(".view").forEach((s) => { s.hidden = s.id !== "view-" + v; });
  if (v === "programs") loadPrograms();
  if (v === "code") loadFiles(cwd);
  if (v === "network") loadNetwork();
  if (v === "settings") loadSettings();
  if (v === "chat") scrollChat(true);
}
$$(".tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));

// ---------------- conversa ----------------
const msgs = $("#messages");
let lastEvent = 0, busy = false, lastTool = null, stateLine = null, echoUser = null;

function scrollChat(force) {
  const near = msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight < 140;
  if (force || near) msgs.scrollTop = msgs.scrollHeight;
}
function addMsg(cls, html) {
  $("#empty").hidden = true;
  const d = document.createElement("div");
  d.className = "msg " + cls;
  d.innerHTML = html;
  msgs.insertBefore(d, stateLine && stateLine.isConnected ? stateLine : null);
  scrollChat();
  return d;
}
function toolSummary(name, args) {
  const a = args || {};
  const key = a.path || a.name || a.to || a.note || "";
  return esc(name) + (key ? " · " + esc(String(key).slice(0, 60)) : "");
}
function addToolCall(name, args) {
  const d = document.createElement("details");
  d.className = "tool msg";
  const code = args && (args.code || args.content);
  const rest = Object.assign({}, args || {});
  delete rest.code; delete rest.content;
  const restTxt = Object.keys(rest).length ? "<pre>" + esc(JSON.stringify(rest, null, 1)) + "</pre>" : "";
  d.innerHTML = "<summary>" + toolSummary(name, args) + " <span class='res'></span></summary><div class='body'>" + restTxt +
    (code ? "<pre>" + esc(code) + "</pre>" : "") + "</div>";
  $("#empty").hidden = true;
  msgs.insertBefore(d, stateLine && stateLine.isConnected ? stateLine : null);
  lastTool = d;
  scrollChat();
}
function addToolResult(text) {
  const failed = /error|Traceback|status=error/i.test(text);
  if (lastTool) {
    $(".res", lastTool).innerHTML = failed ? "<span class='bad'>✗</span>" : "<span class='ok'>✓</span>";
    $(".body", lastTool).insertAdjacentHTML("beforeend", "<pre>" + esc(text) + "</pre>");
    lastTool = null;
  } else addMsg("assistant", "<pre>" + esc(text) + "</pre>");
}
function setBusy(b, st) {
  busy = b;
  $("#send").hidden = b;
  $("#stop").hidden = !b;
  if (b) {
    if (!stateLine || !stateLine.isConnected) { stateLine = document.createElement("div"); stateLine.className = "msg state"; msgs.appendChild(stateLine); }
    stateLine.textContent = t(st === "working" ? "working" : "thinking");
    scrollChat();
  } else if (stateLine) { stateLine.remove(); stateLine = null; }
}

function handleEvent(e) {
  switch (e.kind) {
    case "user":
      if (echoUser !== null && e.text === echoUser) { echoUser = null; break; }
      addMsg("user", esc(e.text)); break;
    case "assistant": addMsg("assistant", md(e.text)); break;
    case "tool_call": addToolCall(e.name, e.args); break;
    case "tool_result": addToolResult(e.text); break;
    case "error":
      addMsg("error", esc(e.text) + (e.detail ? "<details><summary>" + esc(t("tech_details")) + "</summary>" + esc(e.detail) + "</details>" : ""));
      KIPP.set("error", 4000); setBusy(false);
      if (e.reason === "no_bridge") refreshStatus();
      break;
    case "state":
      if (e.state === "thinking" || e.state === "working") { setBusy(true, e.state); KIPP.set(e.state); }
      else if (e.state === "done") { setBusy(false); KIPP.set("happy", 2500); }
      else if (e.state === "error") { setBusy(false); KIPP.set("error", 4000); }
      break;
    case "program": case "program_output": if (view === "programs") schedulePrograms(); break;
    case "espnow_msg": addInbox(e.sender + ": " + e.text); break;
    case "peer": if (view === "network") loadNetwork(); break;
  }
}

async function loadHistory() {
  try {
    const r = await api("/api/chat/history");
    msgs.innerHTML = ""; lastTool = null; stateLine = null;
    r.items.forEach((it) => {
      if (it.kind === "user") addMsg("user", esc(it.text));
      else if (it.kind === "assistant") addMsg("assistant", md(it.text));
      else if (it.kind === "tool_call") addToolCall(it.name, it.args);
      else if (it.kind === "tool_result") addToolResult(it.text);
    });
    $("#empty").hidden = r.items.length > 0;
    lastEvent = r.last;
    setBusy(r.busy, "thinking");
    if (r.busy) KIPP.set("thinking");
    scrollChat(true);
  } catch (e) { /* o laço de eventos mostra a faixa de "sem conexão" */ }
}

async function eventLoop() {
  for (;;) {
    try {
      const r = await api("/api/events?since=" + lastEvent + "&wait=1", { timeout: 20000 });
      $("#offline").hidden = true;
      r.events.forEach((e) => { lastEvent = Math.max(lastEvent, e.id); handleEvent(e); });
      if (r.last < lastEvent) lastEvent = r.last;  // a placa reiniciou: os números de evento recomeçaram
      if (!r.busy && busy) setBusy(false);
    } catch (e) {
      $("#offline").hidden = false;
      await sleep(2500);
    }
  }
}

async function sendPrompt(text) {
  text = text.trim();
  if (!text) return;
  if (busy) { addMsg("error", esc(t("busy"))); return; }
  addMsg("user", esc(text));
  echoUser = text;
  $("#prompt").value = "";
  setBusy(true, "thinking"); KIPP.set("thinking");
  try { await api("/api/chat", { method: "POST", body: { text } }); }
  catch (e) { setBusy(false); addMsg("error", esc(e.status === 409 ? t("busy") : e.message)); }
}
$("#composer").addEventListener("submit", (ev) => { ev.preventDefault(); sendPrompt($("#prompt").value); });
$("#prompt").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey && !matchMedia("(pointer: coarse)").matches) { ev.preventDefault(); sendPrompt(ev.target.value); }
});
$("#stop").addEventListener("click", () => api("/api/chat/stop", { method: "POST" }).catch(() => {}));
$$(".suggest .chip").forEach((b) => b.addEventListener("click", () => sendPrompt(b.textContent)));

// ---------------- programas ----------------
let progTimer = null, openLogs = new Set();
function schedulePrograms() { clearTimeout(progTimer); progTimer = setTimeout(loadPrograms, 400); }
async function loadPrograms() {
  try {
    const r = await api("/api/programs");
    const auto = new Set((r.autostart || []).map((a) => a.path));
    const ul = $("#program-list");
    if (!r.programs.length && !auto.size) { ul.innerHTML = "<li class='muted'>" + esc(t("no_programs")) + "</li>"; return; }
    const known = new Set(r.programs.map((p) => p.path));
    const rows = r.programs.slice().reverse();
    [...auto].filter((p) => !known.has(p)).forEach((p) => rows.push({ name: p.split("/").pop().replace(".py", ""), path: p, status: "", runtime_ms: 0, error: "" }));
    ul.innerHTML = rows.map((p) => {
      const st = p.status ? "<span class='badge " + esc(p.status) + "'>" + esc(t(p.status)) + "</span>" : "";
      const secs = p.runtime_ms ? " · " + Math.round(p.runtime_ms / 1000) + " s" : "";
      const btns = [
        "<button type='button' class='ghost' data-act='log' data-name='" + esc(p.name) + "'>" + esc(t("log")) + "</button>",
        p.status === "running" || p.status === "starting" ? "<button type='button' class='danger' data-act='stop' data-name='" + esc(p.name) + "'>" + esc(t("stop")) + "</button>" : "",
        p.path && p.status !== "running" ? "<button type='button' data-act='run' data-name='" + esc(p.name) + "' data-path='" + esc(p.path) + "'>" + esc(t("run_again")) + "</button>" : "",
        p.path ? "<label class='small'><input type='checkbox' data-act='auto' data-path='" + esc(p.path) + "'" + (auto.has(p.path) ? " checked" : "") + " style='width:auto'> " + esc(t("autostart")) + "</label>" : "",
      ].join(" ");
      return "<li class='card'><div class='head'><strong class='mono'>" + esc(p.name) + "</strong>" + st + "</div>" +
        "<div class='muted small mono'>" + esc(p.path || "") + secs + "</div>" +
        (p.error ? "<pre class='out bad'>" + esc(p.error) + "</pre>" : "") +
        "<div class='row wrap'>" + btns + "</div><pre class='out' data-log='" + esc(p.name) + "' hidden></pre></li>";
    }).join("");
    for (const name of openLogs) showLog(name);
  } catch (e) { /* tenta de novo na próxima atualização */ }
}
async function showLog(name) {
  const pre = $$("pre[data-log]").find((x) => x.dataset.log === name);
  if (!pre) return;
  try { const r = await api("/api/program/log?name=" + encodeURIComponent(name)); pre.textContent = r.log.join("\n") || "…"; pre.hidden = false; pre.scrollTop = pre.scrollHeight; }
  catch (e) { pre.hidden = true; }
}
$("#program-list").addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-act]");
  if (!b || b.type === "checkbox") return;
  const name = b.dataset.name;
  if (b.dataset.act === "log") {
    if (openLogs.has(name)) { openLogs.delete(name); const pre = $$("pre[data-log]").find((x) => x.dataset.log === name); if (pre) pre.hidden = true; }
    else { openLogs.add(name); showLog(name); }
  } else if (b.dataset.act === "stop") { await api("/api/stop", { method: "POST", body: { name } }).catch(() => {}); loadPrograms(); }
  else if (b.dataset.act === "run") { await api("/api/run", { method: "POST", body: { name, path: b.dataset.path } }).catch((e) => alert(e.message)); loadPrograms(); }
});
$("#program-list").addEventListener("change", async (ev) => {
  const c = ev.target;
  if (c.dataset.act === "auto") await api("/api/autostart", { method: "POST", body: { path: c.dataset.path, enabled: c.checked } }).catch(() => {});
});
$("#stop-all").addEventListener("click", async () => { await api("/api/stop", { method: "POST", body: { name: "all" } }).catch(() => {}); loadPrograms(); });
setInterval(() => { if (view === "programs" && !document.hidden) loadPrograms(); }, 4000);

// ---------------- código: arquivos e editor ----------------
let cwd = "/", editing = null;
const SYSTEM = ["/core", "/main.py", "/boot.py", "/lib", "/www"];
async function loadFiles(path) {
  cwd = path;
  const parts = path.split("/").filter(Boolean);
  $("#crumbs").innerHTML = "<button type='button' data-path='/'>/</button>" +
    parts.map((p, i) => "<button type='button' data-path='/" + esc(parts.slice(0, i + 1).join("/")) + "'>" + esc(p) + "/</button>").join("");
  try {
    const r = await api("/api/files?path=" + encodeURIComponent(path));
    const items = r.items.sort((a, b) => (b.dir - a.dir) || a.name.localeCompare(b.name));
    $("#file-list").innerHTML = items.length ? items.map((it) =>
      "<li><button type='button' class='ghost' data-path='" + esc(it.path) + "' data-dir='" + (it.dir ? 1 : 0) + "'><span class='mono'>" +
      esc(it.name) + (it.dir ? "/" : "") + "</span><span class='size'>" + (it.dir ? "" : it.size + " B") + "</span></button></li>").join("")
      : "<li class='muted'>" + esc(t("empty_folder")) + "</li>";
  } catch (e) { $("#file-list").innerHTML = "<li class='bad'>" + esc(e.message) + "</li>"; }
}
$("#crumbs").addEventListener("click", (ev) => { const b = ev.target.closest("button"); if (b) loadFiles(b.dataset.path); });
$("#file-list").addEventListener("click", (ev) => {
  const b = ev.target.closest("button");
  if (!b) return;
  if (b.dataset.dir === "1") loadFiles(b.dataset.path); else openFile(b.dataset.path);
});
async function openFile(path, text) {
  editing = path;
  $("#editor").hidden = false;
  $("#editor-path").textContent = path;
  const sys = isSystem(path), locked = sys && !devMode();
  $("#ed-warn").hidden = !sys;
  $("#ed-warn").textContent = t(locked ? "readonly_sys" : "system_file");
  $("#ed-text").readOnly = locked;
  $("#ed-save").hidden = locked;
  $("#ed-delete").hidden = locked;
  $("#ed-text").value = text !== undefined ? text : await api("/api/file?path=" + encodeURIComponent(path), { raw: true }).catch((e) => "# " + e.message);
  $("#ed-run").hidden = !path.endsWith(".py") || sys;
  $("#editor").scrollIntoView({ block: "start" });
}
function isSystem(path) { return SYSTEM.some((x) => path === x || path.startsWith(x + "/")); }
function devMode() { try { return localStorage.getItem("devmode") === "1"; } catch (e) { return false; } }
async function saveFile() {
  const force = isSystem(editing) && devMode() ? "&force=1" : "";
  await api("/api/file?path=" + encodeURIComponent(editing) + force, { method: "POST", body: $("#ed-text").value });
}
$("#ed-save").addEventListener("click", async () => { try { await saveFile(); loadFiles(cwd); flash($("#ed-save"), t("saved")); } catch (e) { alert(e.message); } });
$("#ed-run").addEventListener("click", async () => {
  try {
    await saveFile();
    const name = editing.split("/").pop().replace(".py", "");
    await api("/api/stop", { method: "POST", body: { name } }).catch(() => {});
    await api("/api/run", { method: "POST", body: { name, path: editing } });
    openLogs.add(name);
    show("programs");
  } catch (e) { alert(e.message); }
});
$("#ed-delete").addEventListener("click", async () => {
  if (!confirm(t("confirm_delete", editing))) return;
  await api("/api/file/delete", { method: "POST", body: { path: editing, force: isSystem(editing) && devMode() } }).catch((e) => alert(e.message));
  $("#editor").hidden = true; editing = null; loadFiles(cwd);
});
$("#ed-close").addEventListener("click", () => { $("#editor").hidden = true; editing = null; });
$("#new-file").addEventListener("click", () => {
  const n = prompt(t("new_file_name", cwd), "my_program.py");
  if (n) openFile((cwd.endsWith("/") ? cwd : cwd + "/") + n.replace(/^\/+/, ""), "");
});
function flash(btn, text) { const old = btn.textContent; btn.textContent = text; setTimeout(() => { btn.textContent = old; }, 1400); }
// Tab dentro dos editores insere 4 espaços (Esc e depois Tab sai do campo, pelo teclado)
let escaped = false;
$$("textarea.code").forEach((ta) => ta.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") { escaped = true; return; }
  if (ev.key === "Tab" && !ev.shiftKey && !escaped) {
    ev.preventDefault();
    const s = ta.selectionStart;
    ta.setRangeText("    ", s, ta.selectionEnd, "end");
  }
  escaped = false;
}));
$("#quick-go").addEventListener("click", async () => {
  const out = $("#quick-out");
  out.hidden = false; out.textContent = "…";
  try {
    const r = await api("/api/run", { method: "POST", body: { code: $("#quick-code").value } });
    const name = r.program.name;
    for (let i = 0; i < 60; i++) {
      await sleep(500);
      const l = await api("/api/program/log?name=" + encodeURIComponent(name));
      out.textContent = (l.log.join("\n") || "…") + (l.program.status === "running" ? "" : "\n[" + t(l.program.status) + "]");
      if (l.program.status !== "running" && l.program.status !== "starting") break;
    }
  } catch (e) { out.textContent = e.message; }
});

// ---------------- placas (ESP-NOW) ----------------
async function loadNetwork() {
  try {
    const r = await api("/api/peers");
    const me = r.me;
    const facts = [[t("name"), me.name], [t("mode"), me.mode === "sta" ? t("wifi") + " · " + me.ssid : me.mode === "ap" ? t("own_network") : me.mode],
      [t("ip"), me.ip], [t("chan"), me.channel ?? "?"], [t("mac"), me.mac]];
    $("#me").innerHTML = facts.map(([k, v]) => "<dt>" + esc(k) + "</dt><dd>" + esc(v) + "</dd>").join("");
    $("#peer-list").innerHTML = r.peers.length ? r.peers.map((p) =>
      "<li class='card'><div class='head'><strong><span class='dot" + (p.online ? " on" : "") + "'></span>" + esc(p.name) + "</strong>" +
      "<span class='muted small mono'>" + esc(p.mac) + (p.rssi != null ? " · " + esc(p.rssi) + " dBm" : "") + "</span></div>" +
      "<div class='muted small'>" + esc(t("seen", p.seen_s_ago)) + (p.ip ? " · <a href='http://" + esc(p.ip) + "/'>" + esc(t("open_page")) + "</a>" : "") + "</div></li>").join("")
      : "<li class='muted'>" + esc(t("no_peers")) + "</li>";
    const sel = $("#en-to"), cur = sel.value;
    sel.innerHTML = r.peers.map((p) => "<option>" + esc(p.name) + "</option>").join("") + "<option value='all'>all</option>";
    if (cur) sel.value = cur;
  } catch (e) { /* sem conexão */ }
}
function addInbox(line) {
  const li = document.createElement("li");
  li.textContent = line;
  const ul = $("#inbox");
  ul.prepend(li);
  while (ul.children.length > 30) ul.lastChild.remove();
}
async function espnowAction(kind) {
  const out = $("#en-out");
  out.hidden = false; out.textContent = "…";
  const to = $("#en-to").value, text = $("#en-text").value;
  try {
    const r = kind === "run" ? await api("/api/espnow/run", { method: "POST", body: { to, code: text, timeout_s: 15 }, timeout: 40000 })
      : await api("/api/espnow/send", { method: "POST", body: { to, text } });
    out.textContent = r.result;
  } catch (e) { out.textContent = e.message; }
}
$("#en-send").addEventListener("click", () => espnowAction("send"));
$("#en-run").addEventListener("click", () => espnowAction("run"));
setInterval(() => { if (view === "network" && !document.hidden) loadNetwork(); }, 6000);

// ---------------- ajustes ----------------
let cfg = {};
const connectCmd = () => "curl -fsS http://" + location.host + "/bridge.py -o bridge.py && python3 bridge.py http://" + location.host;
async function loadSettings() {
  try {
    cfg = (await api("/api/config")).config;
    $("#board-name").value = cfg.name || "";
    $("#channel").value = cfg.espnow_channel || 1;
    $("#oled-sda").value = cfg.oled.sda; $("#oled-scl").value = cfg.oled.scl; $("#oled-addr").value = cfg.oled.addr;
    $("#rgb-pin").value = cfg.rgb_led_pin;
    $("#tz").value = (cfg.tz_offset_min || 0) / 60;
    $("#harness-model").value = cfg.harness_model || "";
    $("#devmode").checked = devMode();
    const st = await api("/api/status");
    const n = st.network, b = st.bridge;
    $("#bridge-now").textContent = b.connected ? t("bridge_on") : t("bridge_off");
    $("#bridge-hint").textContent = "";
    $("#harness").innerHTML = "<option value=''>" + esc(t("auto_pick")) + "</option>" + b.available.map((h) => "<option>" + esc(h) + "</option>").join("");
    $("#harness").value = cfg.harness || "";
    $("#wifi-now").textContent = n.mode === "sta" ? n.ssid : n.mode === "ap" ? t("wifi_own") : t("wifi_lost");
    $("#wifi-now-ip").textContent = n.ip ? "http://" + n.ip + (n.name ? " · http://" + n.name + ".local" : "") : "";
    $("#about").textContent = "openTARS Self-Programming " + st.version + " · " + Math.round(st.memory.free / 1024) + " KB " + t("free");
  } catch (e) { $("#save-msg").textContent = e.message; }
}
async function scanWifi() {
  $("#wifi-msg").textContent = "…";
  try {
    const r = await api("/api/wifi/scan", { timeout: 20000 });
    $("#wifi-ssid").innerHTML = r.networks.map((w) => "<option>" + esc(w.ssid) + "</option>").join("");
    $("#wifi-msg").textContent = "";
  } catch (e) { $("#wifi-msg").textContent = e.message; }
}
$("#wifi-scan").addEventListener("click", scanWifi);
$("#wifi-go").addEventListener("click", async () => {
  $("#wifi-msg").textContent = t("wifi_trying");
  try {
    const r = await api("/api/wifi/connect", { method: "POST", body: { ssid: $("#wifi-ssid").value, password: $("#wifi-pass").value }, timeout: 40000 });
    $("#wifi-msg").textContent = r.ok ? t("wifi_ok", r.ip || "") : (r.error || r.reason || "failed");
  } catch (e) { $("#wifi-msg").textContent = e.message; }
});
$("#devmode").addEventListener("change", (ev) => {
  try { localStorage.setItem("devmode", ev.target.checked ? "1" : "0"); } catch (e) { /* sem armazenamento */ }
});
async function saveSettings() {
  const body = {
    harness: $("#harness").value, harness_model: $("#harness-model").value.trim(),
    name: $("#board-name").value.trim(), espnow_channel: parseInt($("#channel").value, 10) || 1, lang,
    oled: { sda: +$("#oled-sda").value, scl: +$("#oled-scl").value, addr: +$("#oled-addr").value },
    rgb_led_pin: +$("#rgb-pin").value,
    tz_offset_min: Math.round((parseFloat($("#tz").value) || 0) * 60),
  };
  const r = await api("/api/config", { method: "POST", body });
  cfg = r.config;
  $("#save-msg").textContent = r.rejected && r.rejected.length ? t("saved") + " (" + r.rejected.join(", ") + " ✗)" : t("saved");
  loadSettings();
  refreshStatus();
}
$("#settings").addEventListener("submit", async (ev) => { ev.preventDefault(); try { await saveSettings(); } catch (e) { $("#save-msg").textContent = e.message; } });
$("#reboot").addEventListener("click", async () => {
  if (!confirm(t("confirm_reboot"))) return;
  await api("/api/reboot", { method: "POST" }).catch(() => {});
  $("#save-msg").textContent = t("restarting");
});
$("#clear-chat").addEventListener("click", async () => {
  if (!confirm(t("confirm_clear"))) return;
  try { await api("/api/chat/clear", { method: "POST" }); msgs.innerHTML = ""; $("#empty").hidden = false; } catch (e) { alert(e.message); }
});

// ---------------- cabeçalho e início ----------------
let boardName = "opentars", lastStatus = null;
async function refreshStatus() {
  try {
    const s = await api("/api/status");
    lastStatus = s;
    const n = s.network;
    boardName = n.name || boardName;
    $("#board-line").textContent = [n.name, n.ip, n.mode === "ap" ? t("own_network") : n.ssid, s.memory.free ? Math.round(s.memory.free / 1024) + " KB " + t("free") : ""]
      .filter(Boolean).join(" · ");
    const off = !s.bridge.connected;
    $("#need-ai").hidden = !off;
    if (off) {
      $("#need-text").textContent = s.network.mode === "ap" ? t("wifi_first") : t("bridge_hint");
      $("#cmd").textContent = connectCmd();
      $("#cmd").hidden = $("#copy-cmd").hidden = s.network.mode === "ap";
    }
  } catch (e) { /* o laço de eventos cuida da faixa */ }
}
$("#copy-cmd").addEventListener("click", async () => {
  const cmd = $("#cmd");
  let ok = false;
  try { await navigator.clipboard.writeText(connectCmd()); ok = true; } catch (e) { /* página http: o navegador só libera a área de transferência em https */ }
  if (!ok) {   // plano B: seleciona o comando e usa o copiar antigo
    const r = document.createRange(); r.selectNodeContents(cmd);
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
  }
  $("#copy-cmd").textContent = ok ? t("copied") : t("copy_manual");   // sem copiar, o texto fica selecionado: é só tocar em Copiar do menu
});
$("#lang").addEventListener("click", () => {
  lang = lang === "pt" ? "en" : "pt";
  try { localStorage.setItem("lang", lang); } catch (e) { /* sem armazenamento: vale só nesta visita */ }
  api("/api/config", { method: "POST", body: { lang } }).catch(() => {});   // a placa também responde no idioma escolhido
  applyI18n(); refreshStatus();
  if (view !== "chat") show(view);
});

applyI18n();
setInterval(() => { if (!document.hidden) refreshStatus(); }, 15000);
loadHistory().then(eventLoop);
window.addEventListener("load", refreshStatus);
