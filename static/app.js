// app.js
// Jarvis browser UI — handles sending messages, receiving SSE streams,
// rendering cards, heartbeat, and shutdown on tab close.

const API = "http://localhost:7777";

// ── State ─────────────────────────────────────────────────────────────────
let activeStreams = 0;      // count of in-progress requests (allows parallel)
let threadEl     = null;   // the .thread div inside .chat-container
let welcomeShown = true;

// Actions that take a long time — show progress bar instead of blocking input
const LONG_ACTIONS = new Set([
  "generate_blender_mcp", "generate_blender_cc",
  "refine_blender_mcp",   "refine_blender_cc",
  "generate_image", "generate_shape_e", "generate_cad",
]);

// ── Init ──────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  startHeartbeat();
  setupInput();
});

// ── Health check ──────────────────────────────────────────────────────────
async function checkHealth() {
  const dot  = document.getElementById("statusDot");
  const text = document.getElementById("statusText");
  try {
    const res  = await fetch(`${API}/health`);
    const data = await res.json();
    if (data.ollama === "running") {
      dot.className  = "status-dot online";
      text.textContent = "Online";
    } else {
      dot.className  = "status-dot offline";
      text.textContent = "Ollama offline";
    }
  } catch {
    dot.className  = "status-dot offline";
    text.textContent = "Offline";
    setTimeout(checkHealth, 3000);
  }
}

// ── Heartbeat — keeps server alive while tab is open ─────────────────────
function startHeartbeat() {
  setInterval(async () => {
    try { await fetch(`${API}/heartbeat`, { method: "POST" }); }
    catch {}
  }, 15000);
}

// ── Shutdown on tab close ─────────────────────────────────────────────────
window.addEventListener("beforeunload", () => {
  navigator.sendBeacon(`${API}/shutdown`, "");
});

// ── Input setup ───────────────────────────────────────────────────────────
function setupInput() {
  const input = document.getElementById("messageInput");
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    if (e.key === "Escape") { input.value = ""; }
  });
  input.focus();
}

// ── Send suggestion chip ──────────────────────────────────────────────────
function sendSuggestion(text) {
  document.getElementById("messageInput").value = text;
  sendMessage();
}

// ── Send message ──────────────────────────────────────────────────────────
async function sendMessage() {
  const input = document.getElementById("messageInput");
  const text  = input.value.trim();
  if (!text) return;

  input.value = "";
  ensureThread();

  // Append user message
  appendMessage("user", text);

  // Show typing indicator while brain routes the command (~1s)
  const typingId = appendTyping();
  activeStreams++;
  updateSendBtn();

  try {
    const res = await fetch(`${API}/chat`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ message: text }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const action = data.action;

    removeTyping(typingId);

    // Long-running actions: show progress bar and unblock input immediately
    if (LONG_ACTIONS.has(action)) {
      streamReplyAsync(data.stream_id, action);   // fire and forget
    } else {
      await streamReply(data.stream_id, action);  // wait for fast actions
    }

  } catch (err) {
    removeTyping(typingId);
    appendMessage("jarvis", `Error: ${err.message}`);
    console.error(err);
  } finally {
    activeStreams--;
    updateSendBtn();
    document.getElementById("messageInput").focus();
    checkHealth();
  }
}

function updateSendBtn() {
  // Only block send if we have active SHORT streams (long ones run in background)
  document.getElementById("sendBtn").disabled = false;
  document.getElementById("messageInput").disabled = false;
}

// ── SSE stream reader (blocking — waits for completion) ───────────────────
async function streamReply(streamId, action) {
  return new Promise((resolve, reject) => {
    const { row, textEl } = appendJarvisRow();
    const es = new EventSource(`${API}/stream/${streamId}`);
    let cardRendered = false;

    es.addEventListener("token", (e) => {
      const { text } = JSON.parse(e.data);
      textEl.textContent += text;
      scrollToBottom();
    });
    es.addEventListener("card", (e) => {
      const card = JSON.parse(e.data);
      if (!cardRendered) { renderCard(row, card, action); cardRendered = true; }
      scrollToBottom();
    });
    es.addEventListener("done", () => { es.close(); resolve(); });
    es.onerror = () => { es.close(); reject(new Error("Stream error")); };
  });
}

// ── SSE stream reader (non-blocking — shows progress bar, input stays free) ─
function streamReplyAsync(streamId, action) {
  const { row, textEl } = appendJarvisRow();

  // Show progress bar immediately
  const progressEl = appendProgressBar(row, action);

  const es = new EventSource(`${API}/stream/${streamId}`);
  let cardRendered = false;

  es.addEventListener("token", (e) => {
    const { text } = JSON.parse(e.data);
    textEl.textContent += text;
    scrollToBottom();
  });
  es.addEventListener("card", (e) => {
    const card = JSON.parse(e.data);
    if (progressEl) progressEl.remove();   // remove progress bar when done
    if (!cardRendered) { renderCard(row, card, action); cardRendered = true; }
    scrollToBottom();
  });
  es.addEventListener("done", () => { es.close(); });
  es.onerror = () => { es.close(); };
}

// ── DOM helpers ───────────────────────────────────────────────────────────

function ensureThread() {
  const container = document.getElementById("chatContainer");

  // Remove welcome screen on first message
  if (welcomeShown) {
    container.innerHTML = "";
    welcomeShown = false;
    threadEl = document.createElement("div");
    threadEl.className = "thread";
    container.appendChild(threadEl);
  }
}

function appendMessage(role, text) {
  const row    = document.createElement("div");
  row.className = `msg-row ${role === "user" ? "user-row" : ""}`;

  const avatar  = document.createElement("div");
  avatar.className = `avatar ${role === "user" ? "user-av" : "jarvis-av"}`;
  avatar.textContent = role === "user" ? "A" : "⬡";

  const bubble  = document.createElement("div");
  bubble.className = "bubble";

  const sender  = document.createElement("div");
  sender.className = "sender";
  sender.textContent = role === "user" ? "You" : "Jarvis";

  const msgText = document.createElement("div");
  msgText.className = "msg-text";
  msgText.textContent = text;

  bubble.appendChild(sender);
  bubble.appendChild(msgText);
  row.appendChild(avatar);
  row.appendChild(bubble);
  threadEl.appendChild(row);
  scrollToBottom();
  return row;
}

function appendJarvisRow() {
  const row    = document.createElement("div");
  row.className = "msg-row";

  const avatar = document.createElement("div");
  avatar.className = "avatar jarvis-av";
  avatar.textContent = "⬡";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const sender = document.createElement("div");
  sender.className = "sender";
  sender.textContent = "Jarvis";

  const textEl = document.createElement("div");
  textEl.className = "msg-text";

  bubble.appendChild(sender);
  bubble.appendChild(textEl);
  row.appendChild(avatar);
  row.appendChild(bubble);
  threadEl.appendChild(row);
  scrollToBottom();

  return { row, textEl, bubble };
}

function appendTyping() {
  const id  = "typing-" + Date.now();
  const row = document.createElement("div");
  row.id    = id;
  row.className = "msg-row";

  const avatar = document.createElement("div");
  avatar.className = "avatar jarvis-av";
  avatar.textContent = "⬡";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const sender = document.createElement("div");
  sender.className = "sender";
  sender.textContent = "Jarvis";

  const dots = document.createElement("div");
  dots.className = "typing";
  dots.innerHTML = "<span></span><span></span><span></span>";

  bubble.appendChild(sender);
  bubble.appendChild(dots);
  row.appendChild(avatar);
  row.appendChild(bubble);
  threadEl.appendChild(row);
  scrollToBottom();
  return id;
}

function removeTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function scrollToBottom() {
  const c = document.getElementById("chatContainer");
  c.scrollTop = c.scrollHeight;
}

function appendProgressBar(row, action) {
  const bubble = row.querySelector(".bubble");
  if (!bubble) return null;

  const labels = {
    "generate_blender_cc":  "Claude is writing Blender code…",
    "generate_blender_mcp": "Generating in Blender…",
    "refine_blender_cc":    "Claude is refining the model…",
    "refine_blender_mcp":   "Refining in Blender…",
    "generate_image":       "Generating image…",
    "generate_shape_e":     "Generating 3D mesh…",
    "generate_cad":         "Building 3D preview…",
  };
  const label = labels[action] || "Working…";

  const wrap = document.createElement("div");
  wrap.className = "progress-wrap";
  wrap.innerHTML = `
    <div class="progress-label">${label}</div>
    <div class="progress-track"><div class="progress-bar"></div></div>
  `;
  bubble.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

// ── Card renderer ─────────────────────────────────────────────────────────
function renderCard(row, card, action) {
  const bubble = row.querySelector(".bubble");
  if (!bubble) return;

  let cardEl   = null;
  let postRender = null;   // callback fired after cardEl is in the DOM

  switch (card.type) {

    case "time":
      cardEl = makeCard("⏱ Current Time", `
        <div class="time-display">${card.value || ""}</div>
      `);
      break;

    case "files": {
      const lines = (card.lines || []).map(l => {
        const isFolder = l.includes("📁");
        const isFile   = l.includes("📄");
        const cls = isFolder ? "folder" : isFile ? "file" : "";
        return `<div class="file-line ${cls}">${escHtml(l)}</div>`;
      }).join("");
      cardEl = makeCard(`📁 ${escHtml(card.query || "Files")}`, `
        <div class="file-list">${lines}</div>
      `);
      break;
    }

    case "search": {
      // card.result now contains only the sources block
      const sourcesRaw = (card.result || "").replace(/^Sources:\n?/, "").trim();
      const sourceLines = sourcesRaw.split("\n").filter(l => l.trim());
      const sourcesHtml = sourceLines.map(line => {
        const m = line.match(/•\s*(.*?):\s*(https?:\/\/\S+)/);
        if (m) {
          return `<a class="search-source-link" href="${m[2]}" target="_blank">↗ ${escHtml(m[1].trim())}</a>`;
        }
        return `<div class="search-source-line">${escHtml(line)}</div>`;
      }).join("");
      cardEl = makeCard(`🔍 ${escHtml(card.query || "Search")}`, `
        ${sourcesHtml ? `<div class="search-sources">${sourcesHtml}</div>` : ""}
      `);
      break;
    }

    case "browser":
      cardEl = makeCard("🌐 Opened in Chrome", `
        <div class="search-result">${escHtml(card.result || "")}</div>
      `);
      break;

    case "image":
      cardEl = makeCard(`🎨 ${escHtml(card.description || "Generated Image")}`, `
        <div class="image-result">
          <img src="${card.url}" alt="${escHtml(card.description || "")}"
               style="cursor:zoom-in"
               onclick="openLightbox('${card.url}')"
               onload="scrollToBottom()"
               onerror="this.parentElement.innerHTML='<span class=\\'img-error\\'>Could not load image.</span>'" />
        </div>
      `);
      break;

    case "3d_preview":
      cardEl = makeCard("⬡ 3D Preview", `
        <div class="td-status">
          <span class="td-icon">⬡</span>
          Preview opened in browser for: <strong>${escHtml(card.description || "")}</strong>
        </div>
      `);
      break;

    case "3d_blender":
      cardEl = makeCard("⬡ Blender", `
        <div class="td-status">
          <span>Blender opened with: <strong>${escHtml(card.description || "")}</strong></span>
        </div>
      `);
      break;

    case "code_file": {
      const lang = (card.filename || "").split(".").pop() || "text";
      const codeBody = card.code
        ? `<div class="code-inline">
             <div class="code-inline-header">
               <span class="code-inline-filename">${escHtml(card.filename || "")}</span>
               <button class="code-copy-btn" onclick="copyCode(this)">Copy</button>
             </div>
             <pre class="code-pre"><code>${escHtml(card.code)}</code></pre>
           </div>`
        : `<div class="code-file-path">${escHtml(card.filepath || "")}</div>`;
      cardEl = makeCard(`💻 ${escHtml(card.filename || "Code")}`, codeBody);
      break;
    }

    case "clarify": {
      const hasGuess = !!card.best_guess;
      cardEl = makeCard("❓ Clarification Needed", `
        <div class="clarify-question">${escHtml(card.question || "")}</div>
        <div class="clarify-actions">
          ${hasGuess ? `
            <button class="clarify-btn confirm"
              onclick="sendSuggestion('yes')">
              Yes, ${escHtml(card.best_guess)}
            </button>
          ` : ""}
          <button class="clarify-btn dismiss"
            onclick="document.getElementById('messageInput').focus()">
            Let me rephrase
          </button>
        </div>
      `);
      break;
    }

    case "diagram": {
      const diagId = "diag-" + Date.now();
      cardEl = makeCard(`📊 ${escHtml(card.description || "Diagram")}`, `
        <div class="diagram-wrap">
          <div class="diagram-container" id="${diagId}">
            <span class="diagram-loading">Rendering diagram…</span>
          </div>
        </div>
      `);
      postRender = () => {
        const el = document.getElementById(diagId);
        if (!el || !card.code) return;
        mermaid.render("svg-" + diagId, card.code)
          .then(({ svg }) => {
            el.innerHTML = svg;
            scrollToBottom();
          })
          .catch(err => {
            el.innerHTML = `<pre class="diagram-error">${escHtml(String(err))}</pre>`;
          });
      };
      break;
    }

    case "unknown":
      // No special card for unknown — text is enough
      break;

    default:
      // No card for plain text responses
      break;
  }

  if (cardEl) {
    bubble.appendChild(cardEl);
    if (postRender) setTimeout(postRender, 60);
  }
}

function makeCard(title, bodyHtml) {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <div class="card-header">${title}</div>
    <div class="card-body">${bodyHtml}</div>
  `;
  return card;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Lightbox ──────────────────────────────────────────────────────────────
function openLightbox(src) {
  const lb  = document.getElementById("lightbox");
  const img = document.getElementById("lightboxImg");
  img.src = src;
  lb.classList.add("active");
}

function closeLightbox() {
  document.getElementById("lightbox").classList.remove("active");
}

// Close lightbox with Escape key
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeLightbox();
});

// ── Code copy ─────────────────────────────────────────────────────────────
function copyCode(btn) {
  const code = btn.closest(".code-inline").querySelector("code");
  if (code) {
    navigator.clipboard.writeText(code.textContent)
      .then(() => {
        btn.textContent = "✓ Copied!";
        setTimeout(() => btn.textContent = "Copy", 2000);
      });
  }
}
