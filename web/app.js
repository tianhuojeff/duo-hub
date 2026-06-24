/**
 * Duo Hub — 三AI协作中心 前端逻辑
 */

const POLL_INTERVAL = 500;

const $ = (sel) => document.querySelector(sel);

const elClaudeOutput = $("#claude-output");
const elLobsterOutput = $("#lobster-output");
const elCodexOutput = $("#codex-output");
const elClaudeStatus = $("#claude-status-badge");
const elLobsterStatus = $("#lobster-status-badge");
const elCodexStatus = $("#codex-status-badge");
const elClaudeModel = $("#claude-model");
const elLobsterModel = $("#lobster-model");
const elCodexModel = $("#codex-model");
const elClaudeElapsed = $("#claude-elapsed");
const elLobsterElapsed = $("#lobster-elapsed");
const elCodexElapsed = $("#codex-elapsed");
const elChatMessages = $("#chat-messages");
const elTaskInput = $("#task-input");
const elBtnSend = $("#btn-send");
const elBtnStop = $("#btn-stop");
const elBtnConfirm = $("#btn-confirm");
const elBtnFeedback = $("#btn-feedback");
const elBtnRenegotiate = $("#btn-renegotiate");
const elBtnCancelDivision = $("#btn-cancel-division");
const elConfirmBar = $("#confirm-bar");
const elConfirmText = $("#confirm-text");
const elPhaseText = $("#phase-text");
const elSessionId = $("#session-id");
const elAppVersion = $("#app-version");
const elGwCcmr = $("#gw-ccmr");
const elGwLobster = $("#gw-lobster");
const elGwCodex = $("#gw-codex");
const elGraphCanvas = $("#graph-canvas");
const elStarMapWindow = $(".star-map-window");
const elMapViewport = $("#star-map-viewport");
const elBtnMapExpand = $("#btn-map-expand");

let state = {
  phase: "idle",
  claude_status: "idle",
  lobster_status: "idle",
  codex_status: "idle",
  messages: [],
  gateways: { ccmr: false, openclaw: false, codex: false },
};
let lastClaudeMsgIdx = -1;
let lastLobsterMsgIdx = -1;
let lastCodexMsgIdx = -1;
let lastMsgCount = 0;
let taskStartTime = null;
let elapsedTimer = null;
let lastPhase = "idle";

const STATUS_LABELS = {
  idle: "空闲", working: "工作中…", done: "✅ 完成",
  timeout: "⏰ 超时", error: "❌ 错误",
};
const PHASE_LABELS = {
  idle: "就绪 — 输入需求开始",
  ai_working: "⚡ AI 分析中…",
  negotiating: "🤝 自动协商中…",
  pending_confirmation: "📋 等待确认分工",
  awaiting_feedback: "⚠️ 等待你裁决分工",
  executing: "🔨 三方执行中…",
  done: "🎉 全部完成！",
  awaiting_user: "就绪 — 可继续输入需求",
};

// === API ===
async function fetchState() {
  try {
    const res = await fetch("/api/state");
    if (!res.ok) return;
    updateUI(await res.json());
  } catch (e) {}
}

async function submitTask(text, needsDivision) {
  const res = await fetch("/api/task", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, needs_division: needsDivision }),
  });
  const data = await res.json();
  if (!res.ok) { alert("错误: " + (data.error || "未知错误")); return false; }
  return true;
}

async function confirmPlan() {
  const res = await fetch("/api/confirm", { method: "POST" });
  const data = await res.json();
  if (!res.ok) { alert("错误: " + (data.error || "未知错误")); return false; }
  return true;
}

async function triggerNegotiate(feedback = "") {
  const res = await fetch("/api/negotiate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feedback }),
  });
  const data = await res.json();
  if (!res.ok) { alert("错误: " + (data.error || "未知错误")); return false; }
  return true;
}

async function cancelDivision(note = "") {
  const res = await fetch("/api/cancel-division", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  const data = await res.json();
  if (!res.ok) { alert("错误: " + (data.error || "未知错误")); return false; }
  return true;
}

async function setModel(ai, model) {
  await fetch("/api/set-model", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ai, model }),
  });
}

async function stopSession() {
  if (!confirm("确定要重置会话？所有对话记录将被清空。")) return;
  await fetch("/api/stop", { method: "POST" });
  location.reload();
}

// === UI 更新 ===
function updateUI(data) {
  const prevPhase = state.phase;
  state = data;

  updateGatewayIndicators(data.gateways);
  if (data.session_id) elSessionId.textContent = "会话 " + data.session_id.slice(-8);
  if (data.version && elAppVersion) elAppVersion.textContent = "v" + data.version;

  // 阶段变化
  if (data.phase !== prevPhase) {
    handlePhaseChange(data.phase, prevPhase);
    lastPhase = prevPhase;
  }

  elPhaseText.textContent = PHASE_LABELS[data.phase] || data.phase;
  updateButtonStates();
  updateStatusBadges(data);
  updateElapsed(data.phase);

  // 模型选择框状态同步
  if (data.claude_model && elClaudeModel.value !== data.claude_model) {
    elClaudeModel.value = data.claude_model;
  }
  if (data.lobster_model !== undefined && elLobsterModel.value !== data.lobster_model) {
    elLobsterModel.value = data.lobster_model;
  }
  if (data.codex_model !== undefined && elCodexModel.value !== data.codex_model) {
    elCodexModel.value = data.codex_model;
  }

  // 消息渲染
  if (data.messages && data.messages.length > lastMsgCount) {
    renderMessages(data.messages);
    lastMsgCount = data.messages.length;
  }
  if (data.messages) renderAIPanels(data.messages);

  // 分工结果统一展示
  if (data.division && (data.phase === "pending_confirmation" || data.phase === "awaiting_feedback" || data.phase === "executing" || data.phase === "done")) {
    const divEl = document.getElementById("division-result");
    const bodyEl = document.getElementById("division-body");
    let html = "";
    if (data.division.claude) {
      html += '<div class="division-item"><strong>🔵 Claude 负责:</strong><br>' + renderMarkdown(data.division.claude) + '</div>';
    }
    if (data.division.lobster) {
      html += '<div class="division-item" style="margin-top:8px"><strong>🦞 龙虾 负责:</strong><br>' + renderMarkdown(data.division.lobster) + '</div>';
    }
    if (data.division.codex) {
      html += '<div class="division-item" style="margin-top:8px"><strong>🟢 Codex 负责:</strong><br>' + renderMarkdown(data.division.codex) + '</div>';
    }
    const peerFeedback = data.peer_feedback || {};
    const peerStates = peerFeedback.states || {};
    const needsReview = data.phase === "awaiting_feedback" || data.division_status === "needs_user";
    if (needsReview && (peerFeedback.claude || peerFeedback.lobster)) {
      html += '<div class="division-review"><strong>⚠️ 分歧/待裁决:</strong>';
      if (peerFeedback.claude) {
        html += '<div style="margin-top:6px"><span>🔵 Claude: ' + escapeHtml(peerStates.claude || "unknown") + '</span><br>' + renderMarkdown(peerFeedback.claude) + '</div>';
      }
      if (peerFeedback.lobster) {
        html += '<div style="margin-top:6px"><span>🦞 龙虾: ' + escapeHtml(peerStates.lobster || "unknown") + '</span><br>' + renderMarkdown(peerFeedback.lobster) + '</div>';
      }
      html += '</div>';
    }
    bodyEl.innerHTML = html || '<em>协商中…</em>';
    divEl.style.display = "block";
  } else {
    document.getElementById("division-result").style.display = "none";
  }
}

function handlePhaseChange(newPhase, prevPhase) {
  // 进入确认阶段
  if (newPhase === "pending_confirmation" || newPhase === "awaiting_feedback") {
    elConfirmBar.style.display = "flex";
    if (newPhase === "awaiting_feedback") {
      elConfirmText.textContent = "三方未达成一致：输入你的裁决/修改意见，或选择下一步。";
      elBtnConfirm.textContent = "✅ 仍确认执行";
      elTaskInput.placeholder = "写给三方的补充意见，例如：按龙虾意见改，Claude 只负责合成，Codex 负责检查…";
    } else {
      elConfirmText.textContent = "三方已同意分工：可确认执行，也可输入修改意见。";
      elBtnConfirm.textContent = "✅ 确认执行";
      elTaskInput.placeholder = "可选：输入修改意见后点“按输入修改”…";
    }
  }
  // 离开确认阶段
  if ((prevPhase === "pending_confirmation" || prevPhase === "awaiting_feedback") && newPhase !== "pending_confirmation" && newPhase !== "awaiting_feedback") {
    elConfirmBar.style.display = "none";
    elTaskInput.placeholder = "📝 输入你的需求… (Ctrl+Enter 发送)";
  }
  // 进入工作阶段 → 清空面板
  if (newPhase === "ai_working" && prevPhase !== "negotiating") {
    elClaudeOutput.innerHTML = '<div class="placeholder">⏳ 正在分析任务…</div>';
    elLobsterOutput.innerHTML = '<div class="placeholder">⏳ 正在分析任务…</div>';
    elCodexOutput.innerHTML = '<div class="placeholder">⏳ 正在分析任务…</div>';
  }
  if (newPhase === "negotiating") {
    elClaudeOutput.innerHTML = '<div class="placeholder">🤝 正在协商分工…</div>';
    elLobsterOutput.innerHTML = '<div class="placeholder">🤝 正在协商分工…</div>';
    elCodexOutput.innerHTML = '<div class="placeholder">🤝 正在协商分工…</div>';
  }
  // 进入执行阶段 → 清空确认栏，显示执行中
  if (newPhase === "executing") {
    elConfirmBar.style.display = "none";
    elClaudeOutput.innerHTML = '<div class="placeholder">🔨 正在执行任务…</div>';
    elLobsterOutput.innerHTML = '<div class="placeholder">🔨 正在执行任务…</div>';
    elCodexOutput.innerHTML = '<div class="placeholder">🔨 正在执行任务…</div>';
    taskStartTime = Date.now();
    startElapsedTimer();
  }
  // 确认后清空确认栏
  if (newPhase === "confirmed") {
    elConfirmBar.style.display = "none";
  }
  // 重置
  if (newPhase === "idle") {
    elConfirmBar.style.display = "none";
  }
}

function updateGatewayIndicators(gws) {
  elGwCcmr.textContent = gws.ccmr ? "🔵 ccmr ●" : "🔵 ccmr ○";
  elGwCcmr.className = "gw-indicator " + (gws.ccmr ? "online" : "offline");
  elGwLobster.textContent = gws.openclaw ? "🦞 龙虾 ●" : "🦞 龙虾 ○";
  elGwLobster.className = "gw-indicator " + (gws.openclaw ? "online" : "offline");
  elGwCodex.textContent = gws.codex ? "🟢 Codex ●" : "🟢 Codex ○";
  elGwCodex.className = "gw-indicator " + (gws.codex ? "online" : "offline");
}

function updateStatusBadges(data) {
  elClaudeStatus.textContent = STATUS_LABELS[data.claude_status] || data.claude_status;
  elClaudeStatus.dataset.status = data.claude_status;
  elLobsterStatus.textContent = STATUS_LABELS[data.lobster_status] || data.lobster_status;
  elLobsterStatus.dataset.status = data.lobster_status;
  elCodexStatus.textContent = STATUS_LABELS[data.codex_status] || data.codex_status;
  elCodexStatus.dataset.status = data.codex_status;
}

function updateButtonStates() {
  const working = state.phase === "ai_working" || state.phase === "negotiating" || state.phase === "executing";
  const deciding = state.phase === "pending_confirmation" || state.phase === "awaiting_feedback";
  elBtnSend.disabled = working;
  elBtnSend.textContent = working ? "⏳ 处理中…" : deciding ? "✏️ 提交意见" : "🚀 发送";
  elTaskInput.disabled = working;
  // 模型选择框在 AI 工作中也可切换（下次生效）
}

function updateElapsed(phase) {
  if (phase === "ai_working" || phase === "negotiating") {
    if (!taskStartTime) { taskStartTime = Date.now(); startElapsedTimer(); }
  } else {
    stopElapsedTimer();
  }
}

function startElapsedTimer() {
  stopElapsedTimer();
  elapsedTimer = setInterval(() => {
    if (!taskStartTime) return;
    const sec = Math.floor((Date.now() - taskStartTime) / 1000);
    const m = Math.floor(sec / 60), s = sec % 60;
    const t = `⏱ ${m}:${String(s).padStart(2, "0")}`;
    elClaudeElapsed.textContent = t;
    elLobsterElapsed.textContent = t;
    elCodexElapsed.textContent = t;
  }, 1000);
}

function stopElapsedTimer() {
  if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
  taskStartTime = null;
  elClaudeElapsed.textContent = "";
  elLobsterElapsed.textContent = "";
  elCodexElapsed.textContent = "";
}

function renderAIPanels(messages) {
  let latestClaude = null, latestLobster = null, latestCodex = null;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === "claude" && !latestClaude) latestClaude = m;
    if (m.role === "lobster" && !latestLobster) latestLobster = m;
    if (m.role === "codex" && !latestCodex) latestCodex = m;
    if (latestClaude && latestLobster && latestCodex) break;
  }
  if (latestClaude && latestClaude.id !== lastClaudeMsgIdx) {
    elClaudeOutput.innerHTML = renderMarkdown(latestClaude.content);
    elClaudeOutput.scrollTop = 0;
    lastClaudeMsgIdx = latestClaude.id;
  }
  if (latestLobster && latestLobster.id !== lastLobsterMsgIdx) {
    elLobsterOutput.innerHTML = renderMarkdown(latestLobster.content);
    elLobsterOutput.scrollTop = 0;
    lastLobsterMsgIdx = latestLobster.id;
  }
  if (latestCodex && latestCodex.id !== lastCodexMsgIdx) {
    elCodexOutput.innerHTML = renderMarkdown(latestCodex.content);
    elCodexOutput.scrollTop = 0;
    lastCodexMsgIdx = latestCodex.id;
  }
}

function renderMessages(messages) {
  const newMsgs = messages.slice(lastMsgCount);
  if (!newMsgs.length) return;
  const empty = elChatMessages.querySelector(".chat-empty");
  if (empty) empty.remove();

  newMsgs.forEach((m) => {
    const div = document.createElement("div");
    div.className = `chat-msg role-${m.role}`;

    const roleLabel = {
      user: "👤 天火大人", claude: "🔵 Claude", lobster: "🦞 龙虾", codex: "🟢 Codex", system: "⚙ 系统",
    }[m.role] || m.role;

    const time = m.timestamp ? m.timestamp.slice(11, 16) : "";
    div.innerHTML = `
      <span class="msg-role">${roleLabel}</span>
      <span class="msg-time">${time}</span>
      <span class="msg-content">${escapeHtml(truncate(m.content, 150))}</span>
    `;
    elChatMessages.appendChild(div);
  });
  elChatMessages.scrollTop = elChatMessages.scrollHeight;
}

// === Markdown 简单渲染 ===
function renderMarkdown(text) {
  if (!text) return "";
  let html = escapeHtml(text);
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => `<pre><code>${code.trim()}</code></pre>`);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/^- (.+)$/gm, "• $1");
  html = html.replace(/\n\n/g, "<br><br>");
  html = html.replace(/\n/g, "<br>");
  return html;
}

function escapeHtml(text) {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return text.replace(/[&<>"']/g, (c) => map[c]);
}

function truncate(text, maxLen) {
  return text.length <= maxLen ? text : text.slice(0, maxLen) + "…";
}

// === 事件 ===
elBtnSend.addEventListener("click", async () => {
  const text = elTaskInput.value.trim();
  const decisionPhase = state.phase === "pending_confirmation" || state.phase === "awaiting_feedback";
  if (decisionPhase) {
    if (!text) {
      alert("先在输入框写你的修改意见，再提交。");
      return;
    }
    if (await triggerNegotiate(text)) {
      elTaskInput.value = "";
      lastMsgCount = 0;
      taskStartTime = Date.now();
      startElapsedTimer();
      fetchState();
    }
    return;
  }
  if (!text) return;
  const needsDivision = document.getElementById("chk-division").checked;
  if (await submitTask(text, needsDivision)) {
    elTaskInput.value = "";
    lastMsgCount = 0;
    taskStartTime = Date.now();
    startElapsedTimer();
    elClaudeOutput.innerHTML = '<div class="placeholder">⏳ 正在分析任务…</div>';
    elLobsterOutput.innerHTML = '<div class="placeholder">⏳ 正在分析任务…</div>';
    elCodexOutput.innerHTML = '<div class="placeholder">⏳ 正在分析任务…</div>';
    fetchState();
  }
});

elBtnConfirm.addEventListener("click", async () => {
  if (await confirmPlan()) {
    elConfirmBar.style.display = "none";
    fetchState();
  }
});

elBtnFeedback.addEventListener("click", async () => {
  const feedback = elTaskInput.value.trim();
  if (!feedback) {
    alert("先在输入框写清楚你要怎么改分工。");
    elTaskInput.focus();
    return;
  }
  if (await triggerNegotiate(feedback)) {
    elTaskInput.value = "";
    lastMsgCount = 0;
    taskStartTime = Date.now();
    startElapsedTimer();
    fetchState();
  }
});

elBtnRenegotiate.addEventListener("click", async () => {
  const feedback = elTaskInput.value.trim();
  if (await triggerNegotiate(feedback)) {
    lastMsgCount = 0;
    elTaskInput.value = "";
    elClaudeOutput.innerHTML = '<div class="placeholder">🤝 重新协商中…</div>';
    elLobsterOutput.innerHTML = '<div class="placeholder">🤝 重新协商中…</div>';
    elCodexOutput.innerHTML = '<div class="placeholder">🤝 重新协商中…</div>';
    taskStartTime = Date.now();
    startElapsedTimer();
    fetchState();
  }
});

elBtnCancelDivision.addEventListener("click", async () => {
  const note = elTaskInput.value.trim();
  if (await cancelDivision(note)) {
    elTaskInput.value = "";
    elConfirmBar.style.display = "none";
    fetchState();
  }
});

elBtnStop.addEventListener("click", stopSession);

elTaskInput.addEventListener("keydown", (e) => {
  if (e.ctrlKey && e.key === "Enter") { e.preventDefault(); elBtnSend.click(); }
});

// 模型切换
elClaudeModel.addEventListener("change", () => setModel("claude", elClaudeModel.value));
elLobsterModel.addEventListener("change", () => setModel("lobster", elLobsterModel.value));
elCodexModel.addEventListener("change", () => setModel("codex", elCodexModel.value));

function setMapExpanded(expanded) {
  if (!elStarMapWindow || !elBtnMapExpand) return;
  elStarMapWindow.classList.toggle("is-expanded", expanded);
  document.body.classList.toggle("map-immersive", expanded);
  elBtnMapExpand.textContent = expanded ? "×" : "⛶";
  elBtnMapExpand.title = expanded ? "收起星图" : "放大星图";
  elBtnMapExpand.setAttribute("aria-label", expanded ? "收起星图" : "放大星图");
  window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
}

if (elBtnMapExpand) {
  elBtnMapExpand.addEventListener("click", (e) => {
    e.stopPropagation();
    setMapExpanded(!elStarMapWindow.classList.contains("is-expanded"));
  });
}

if (elMapViewport) {
  elMapViewport.addEventListener("click", () => {
    if (!elStarMapWindow.classList.contains("is-expanded")) {
      setMapExpanded(true);
    }
  });
}

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && elStarMapWindow && elStarMapWindow.classList.contains("is-expanded")) {
    setMapExpanded(false);
  }
});

if (location.hash === "#star-map") {
  window.requestAnimationFrame(() => setMapExpanded(true));
}

// === 启动 ===
initEnergyFieldCanvas();
fetchState();
setInterval(fetchState, POLL_INTERVAL);
console.log("⚡ Duo Hub 三方前端已就绪");

function initGraphCanvas() {
  if (!elGraphCanvas) return;
  const ctx = elGraphCanvas.getContext("2d");
  if (!ctx) return;

  const host = elGraphCanvas.parentElement || elGraphCanvas;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const palette = ["#38bdf8", "#3b82f6", "#22c55e", "#f59e0b", "#a78bfa", "#e1e4ed"];
  const particles = [];
  const pulses = [];
  const pointers = new Map();
  let width = 0;
  let height = 0;
  let dpr = 1;
  let lastTime = performance.now();
  let fieldEnergy = 0.68;
  let targetEnergy = 0.68;
  let lastPinchDistance = null;
  let pointer = {
    x: 0,
    y: 0,
    active: false,
    down: false,
    strength: 0,
    lastMove: 0,
  };

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = host.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 20) {
      window.requestAnimationFrame(resize);
      return false;
    }
    width = Math.floor(rect.width);
    height = Math.floor(rect.height);
    if (!pointer.x && !pointer.y) {
      pointer.x = width * 0.5;
      pointer.y = height * 0.5;
    }
    elGraphCanvas.width = Math.floor(width * dpr);
    elGraphCanvas.height = Math.floor(height * dpr);
    elGraphCanvas.style.width = "100%";
    elGraphCanvas.style.height = "100%";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    particles.length = 0;
    const count = Math.max(90, Math.min(280, Math.floor((width * height) / 1150)));
    for (let i = 0; i < count; i++) {
      particles.push(makeParticle(Math.random() * width, Math.random() * height));
    }
    draw(performance.now());
    return true;
  }

  function makeParticle(x, y) {
    const depth = 0.18 + Math.random() * 0.82;
    const color = palette[Math.floor(Math.random() * palette.length)];
    const angle = Math.random() * Math.PI * 2;
    const speed = 0.12 + Math.random() * 0.28;
    return {
      x,
      y,
      px: x,
      py: y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      depth,
      size: 0.95 + depth * 3.05 + Math.random() * 1.15,
      color,
      phase: Math.random() * Math.PI * 2,
      twinkle: 0.62 + Math.random() * 0.52,
    };
  }

  function activePointer() {
    if (pointers.size === 0) return null;
    const pts = Array.from(pointers.values());
    const sum = pts.reduce((acc, pt) => ({ x: acc.x + pt.x, y: acc.y + pt.y }), { x: 0, y: 0 });
    return { x: sum.x / pts.length, y: sum.y / pts.length };
  }

  function updatePointer(now) {
    const pt = activePointer();
    if (pt) {
      pointer.x += (pt.x - pointer.x) * 0.35;
      pointer.y += (pt.y - pointer.y) * 0.35;
      pointer.active = true;
      pointer.lastMove = now;
      targetEnergy = pointer.down ? 1.35 : 1.08;
    } else if (now - pointer.lastMove > 900) {
      pointer.active = false;
      pointer.down = false;
      targetEnergy = 0.68;
    }
    pointer.strength += ((pointer.active ? 1 : 0) - pointer.strength) * 0.06;
    fieldEnergy += (targetEnergy - fieldEnergy) * 0.035;
  }

  function updateParticles(dt) {
    const centerX = width * 0.5 + (pointer.x - width * 0.5) * 0.08 * pointer.strength;
    const centerY = height * 0.5 + (pointer.y - height * 0.5) * 0.08 * pointer.strength;
    const maxRadius = Math.max(width, height) * 0.72;

    particles.forEach((pt) => {
      pt.px = pt.x;
      pt.py = pt.y;
      pt.phase += (0.004 + pt.depth * 0.008) * dt * fieldEnergy;

      const cx = pt.x - centerX;
      const cy = pt.y - centerY;
      const cd = Math.max(90, Math.hypot(cx, cy));
      const curl = (1 - Math.min(cd / maxRadius, 1)) * (0.025 + pt.depth * 0.035) * fieldEnergy;
      pt.vx += (-cy / cd) * curl * dt;
      pt.vy += (cx / cd) * curl * dt;

      pt.vx += Math.cos(pt.phase) * 0.008 * dt;
      pt.vy += Math.sin(pt.phase * 0.9) * 0.008 * dt;

      if (pointer.strength > 0.01) {
        const dx = pointer.x - pt.x;
        const dy = pointer.y - pt.y;
        const dist = Math.max(22, Math.hypot(dx, dy));
        const radius = pointer.down ? 360 : 260;
        if (dist < radius) {
          const force = Math.pow(1 - dist / radius, 2) * pointer.strength * (0.65 + pt.depth);
          const tangent = pointer.down ? 0.17 : 0.105;
          const pull = pointer.down ? 0.07 : 0.035;
          pt.vx += ((dx / dist) * pull + (-dy / dist) * tangent) * force * dt;
          pt.vy += ((dy / dist) * pull + (dx / dist) * tangent) * force * dt;
        }
      }

      pt.x += pt.vx * dt * (0.55 + pt.depth) * fieldEnergy;
      pt.y += pt.vy * dt * (0.55 + pt.depth) * fieldEnergy;
      pt.vx *= 0.985;
      pt.vy *= 0.985;

      const pad = 36;
      if (pt.x < -pad) { pt.x = width + pad; pt.px = pt.x; }
      if (pt.x > width + pad) { pt.x = -pad; pt.px = pt.x; }
      if (pt.y < -pad) { pt.y = height + pad; pt.py = pt.y; }
      if (pt.y > height + pad) { pt.y = -pad; pt.py = pt.y; }
    });

    for (let i = pulses.length - 1; i >= 0; i--) {
      const pulse = pulses[i];
      pulse.life -= 0.018 * dt;
      pulse.radius += (5.5 + pulse.force * 2.5) * dt;
      if (pulse.life <= 0) pulses.splice(i, 1);
    }
  }

  function drawParticle(pt, now) {
    const alpha = Math.min(1, (0.46 + pt.depth * 0.7) * (0.78 + Math.sin(now * 0.0015 + pt.phase) * 0.22) * pt.twinkle);
    const radius = pt.size * (0.86 + pointer.strength * 0.34);
    const gradient = ctx.createRadialGradient(pt.x, pt.y, 0, pt.x, pt.y, radius * 5.8);
    gradient.addColorStop(0, `${pt.color}ff`);
    gradient.addColorStop(0.22, `${pt.color}cc`);
    gradient.addColorStop(0.58, `${pt.color}44`);
    gradient.addColorStop(1, `${pt.color}00`);
    ctx.globalAlpha = alpha;
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, radius * 5.8, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = Math.min(1, alpha + 0.38);
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, Math.max(0.8, radius * 0.58), 0, Math.PI * 2);
    ctx.fill();
  }

  function drawLinks() {
    const maxDist = width < 700 ? 92 : 126;
    ctx.lineWidth = 1.1;
    for (let i = 0; i < particles.length; i++) {
      const a = particles[i];
      for (let j = i + 1; j < particles.length; j++) {
        const b = particles[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const d = Math.hypot(dx, dy);
        if (d < maxDist) {
          const alpha = (1 - d / maxDist) * 0.25 * Math.min(1, a.depth + b.depth);
          ctx.strokeStyle = `rgba(129, 212, 250, ${alpha})`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }
  }

  function drawPointerHud(now) {
    if (pointer.strength < 0.02) return;
    const pulse = Math.sin(now * 0.006) * 5;
    const base = pointer.down ? 62 : 48;
    ctx.save();
    ctx.translate(pointer.x, pointer.y);
    ctx.rotate(now * 0.0008);
    ctx.globalAlpha = 0.58 * pointer.strength;
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 1.45;
    for (let i = 0; i < 3; i++) {
      const r = base + i * 18 + pulse * (i + 0.4);
      ctx.beginPath();
      ctx.arc(0, 0, r, i * 0.72, Math.PI * 1.4 + i * 0.72);
      ctx.stroke();
    }
    ctx.strokeStyle = "#22c55e";
    ctx.globalAlpha = 0.38 * pointer.strength;
    ctx.beginPath();
    ctx.arc(0, 0, base + 72 + pulse, -Math.PI * 0.2, Math.PI * 0.84);
    ctx.stroke();
    ctx.restore();
  }

  function drawPulses() {
    pulses.forEach((pulse) => {
      const alpha = Math.max(0, pulse.life);
      ctx.globalAlpha = alpha * 0.68;
      ctx.strokeStyle = pulse.color;
      ctx.lineWidth = 1.8 + pulse.force * 1.1;
      ctx.beginPath();
      ctx.arc(pulse.x, pulse.y, pulse.radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = alpha * 0.32;
      ctx.beginPath();
      ctx.arc(pulse.x, pulse.y, pulse.radius * 0.62, 0, Math.PI * 2);
      ctx.stroke();
    });
  }

  function draw(now) {
    ctx.clearRect(0, 0, width, height);
    ctx.globalCompositeOperation = "lighter";

    drawLinks();
    particles.forEach((pt) => drawParticle(pt, now));
    drawPointerHud(now);
    drawPulses();

    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }

  function animate(now) {
    const dt = Math.min(2.2, Math.max(0.55, (now - lastTime) / 16.67));
    lastTime = now;
    updatePointer(now);
    updateParticles(dt);
    draw(now);
    if (reduceMotion) {
      window.setTimeout(() => window.requestAnimationFrame(animate), 120);
    } else {
      window.requestAnimationFrame(animate);
    }
  }

  function addPulse(x, y, force = 1) {
    pulses.push({
      x,
      y,
      force,
      radius: 18,
      life: 1,
      color: force > 1.2 ? "#f59e0b" : "#38bdf8",
    });
    if (pulses.length > 8) pulses.shift();
  }

  function localPoint(e) {
    const rect = host.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(width, e.clientX - rect.left)),
      y: Math.max(0, Math.min(height, e.clientY - rect.top)),
    };
  }

  function syncPointerFromEvent(e) {
    pointers.set(e.pointerId, localPoint(e));
  }

  function updatePinchEnergy() {
    if (pointers.size === 2) {
      const pts = Array.from(pointers.values());
      const d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      if (lastPinchDistance !== null) {
        targetEnergy = Math.max(0.55, Math.min(1.7, targetEnergy + (d - lastPinchDistance) * 0.004));
      }
      lastPinchDistance = d;
    } else {
      lastPinchDistance = null;
    }
  }

  window.addEventListener("resize", resize);
  if (window.ResizeObserver) {
    new ResizeObserver(resize).observe(host);
  }
  host.addEventListener("pointermove", (e) => {
    syncPointerFromEvent(e);
    updatePinchEnergy();
  }, { passive: true });
  host.addEventListener("pointerdown", (e) => {
    pointer.down = true;
    syncPointerFromEvent(e);
    updatePinchEnergy();
    const pt = localPoint(e);
    addPulse(pt.x, pt.y, 1.4);
    try { host.setPointerCapture(e.pointerId); } catch (err) {}
  }, { passive: true });
  window.addEventListener("pointerup", (e) => {
    pointers.delete(e.pointerId);
    pointer.down = pointers.size > 0;
    lastPinchDistance = null;
    const pt = localPoint(e);
    addPulse(pt.x, pt.y, 0.8);
  }, { passive: true });
  window.addEventListener("pointercancel", (e) => {
    pointers.delete(e.pointerId);
    pointer.down = pointers.size > 0;
    lastPinchDistance = null;
  }, { passive: true });
  host.addEventListener("pointerleave", (e) => {
    if (!pointer.down) {
      pointers.delete(e.pointerId);
      lastPinchDistance = null;
    }
  }, { passive: true });
  host.addEventListener("wheel", (e) => {
    e.preventDefault();
    targetEnergy = Math.max(0.5, Math.min(1.65, targetEnergy + (e.deltaY < 0 ? 0.08 : -0.08)));
  }, { passive: false });

  if (resize()) {
    updateParticles(1);
    draw(performance.now());
  }
  window.requestAnimationFrame((now) => {
    resize();
    lastTime = now;
    animate(now);
  });
}

function initEnergyFieldCanvas() {
  if (!elGraphCanvas) return;
  const ctx = elGraphCanvas.getContext("2d");
  const host = elGraphCanvas.parentElement || elGraphCanvas;
  if (!ctx || !host) return;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const particles = [];
  const pulses = [];
  const dragTrail = [];
  const pointers = new Map();
  const semanticNodes = [
    { key: "user", label: "天火需求", type: "需求", color: "#f8fafc", glow: "#a5f3fc", lane: 0, phase: 0.12, weight: 1.12 },
    { key: "claude", label: "Claude", type: "代码执行", color: "#dbeafe", glow: "#3b82f6", lane: 1, phase: 0.92, weight: 1.05 },
    { key: "lobster", label: "龙虾", type: "外部执行", color: "#ffedd5", glow: "#f59e0b", lane: 1, phase: 2.18, weight: 1.05 },
    { key: "codex", label: "Codex", type: "协调验证", color: "#dcfce7", glow: "#22c55e", lane: 1, phase: 3.46, weight: 1.05 },
    { key: "memory", label: "共享记忆", type: "Memory", color: "#f5f3ff", glow: "#a78bfa", lane: 2, phase: 4.12, weight: 0.94 },
    { key: "tasks", label: "任务队列", type: "Tasks", color: "#e0f2fe", glow: "#38bdf8", lane: 2, phase: 5.12, weight: 0.9 },
    { key: "division", label: "协商分工", type: "Protocol", color: "#fef9c3", glow: "#eab308", lane: 2, phase: 0.72, weight: 0.92 },
    { key: "investment", label: "投资学习", type: "Learning", color: "#ccfbf1", glow: "#14b8a6", lane: 3, phase: 1.56, weight: 0.86 },
    { key: "strategy", label: "策略版本", type: "Backtest", color: "#e0e7ff", glow: "#6366f1", lane: 3, phase: 2.74, weight: 0.86 },
    { key: "github", label: "GitHub v0.4.2", type: "Version", color: "#f8fafc", glow: "#64748b", lane: 3, phase: 3.82, weight: 0.78 },
    { key: "log", label: "工作日志", type: "Log", color: "#fae8ff", glow: "#d946ef", lane: 3, phase: 4.82, weight: 0.8 },
    { key: "telegram", label: "TG 桥", type: "Bridge", color: "#dbeafe", glow: "#0ea5e9", lane: 3, phase: 5.76, weight: 0.76 },
  ];
  const semanticLinks = [
    ["user", "claude"], ["user", "lobster"], ["user", "codex"],
    ["codex", "division"], ["division", "claude"], ["division", "lobster"],
    ["memory", "tasks"], ["memory", "log"], ["investment", "strategy"],
    ["codex", "github"], ["tasks", "telegram"], ["codex", "memory"],
  ];
  const palette = [
    { core: "#ffffff", glow: "#7dd3fc" },
    { core: "#e0f2fe", glow: "#38bdf8" },
    { core: "#dbeafe", glow: "#0ea5e9" },
    { core: "#cffafe", glow: "#22d3ee" },
    { core: "#f0fbff", glow: "#60a5fa" },
  ];
  const core = {
    x: 0,
    y: 0,
    tx: 0,
    ty: 0,
    vx: 0,
    vy: 0,
    radius: 60,
    spin: 0,
    energy: 0.86,
    compression: 1,
  };
  const pointer = {
    x: 0,
    y: 0,
    lastX: 0,
    lastY: 0,
    vx: 0,
    vy: 0,
    active: false,
    down: false,
    strength: 0,
    lastMove: 0,
  };
  let width = 0;
  let height = 0;
  let dpr = 1;
  let lastTime = performance.now();
  let targetEnergy = 0.86;
  let densityScale = 0.78;
  let lastPinchDistance = null;
  let hoveredSemantic = null;

  function isExpandedMap() {
    return !!(elStarMapWindow && elStarMapWindow.classList.contains("is-expanded"));
  }

  function desiredParticleCount() {
    const expanded = isExpandedMap();
    const baseCount = Math.max(96, Math.min(expanded ? 560 : 320, Math.floor((width * height) / 780)));
    return Math.max(56, Math.round(baseCount * densityScale));
  }

  function syncParticleCount(force = false) {
    const targetCount = desiredParticleCount();
    if (force) {
      particles.length = 0;
      for (let i = 0; i < targetCount; i++) particles.push(makeParticle());
      return;
    }
    if (particles.length < targetCount) {
      const addCount = Math.min(48, targetCount - particles.length);
      for (let i = 0; i < addCount; i++) particles.push(makeParticle());
    } else if (particles.length > targetCount) {
      const removeCount = Math.min(48, particles.length - targetCount);
      particles.splice(Math.max(0, particles.length - removeCount), removeCount);
    }
  }

  function resize() {
    const rect = host.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 20) {
      window.requestAnimationFrame(resize);
      return false;
    }

    dpr = Math.min(window.devicePixelRatio || 1, 2);
    const nextWidth = Math.floor(rect.width);
    const nextHeight = Math.floor(rect.height);
    const changed = Math.abs(nextWidth - width) > 1 || Math.abs(nextHeight - height) > 1;
    width = nextWidth;
    height = nextHeight;
    core.radius = Math.max(44, Math.min(isExpandedMap() ? 180 : 96, Math.min(width, height) * 0.45));

    if (changed) {
      core.x = width * 0.5;
      core.y = height * 0.5;
      core.tx = core.x;
      core.ty = core.y;
      if (!pointer.active) {
        pointer.x = core.x;
        pointer.y = core.y;
        pointer.lastX = pointer.x;
        pointer.lastY = pointer.y;
      }
    } else if (!core.x && !core.y) {
      core.x = width * 0.5;
      core.y = height * 0.5;
      core.tx = core.x;
      core.ty = core.y;
      pointer.x = core.x;
      pointer.y = core.y;
      pointer.lastX = pointer.x;
      pointer.lastY = pointer.y;
    }

    elGraphCanvas.width = Math.floor(width * dpr);
    elGraphCanvas.height = Math.floor(height * dpr);
    elGraphCanvas.style.width = "100%";
    elGraphCanvas.style.height = "100%";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const targetCount = desiredParticleCount();
    if (changed) {
      syncParticleCount(true);
    } else if (Math.abs(particles.length - targetCount) > 10) {
      syncParticleCount(false);
    }
    updateParticles(1, performance.now());
    draw(performance.now());
    return true;
  }

  function randomAnchor() {
    const theta = Math.random() * Math.PI * 2;
    const banded = Math.random() < 0.62;
    const phi = banded ? Math.PI * 0.5 + (Math.random() - 0.5) * 0.92 : Math.acos(Math.random() * 2 - 1);
    const shell = Math.random() < 0.74 ? 0.66 + Math.random() * 0.44 : 0.22 + Math.random() * 0.38;
    const radius = core.radius * shell;
    return {
      x: Math.sin(phi) * Math.cos(theta) * radius,
      y: Math.cos(phi) * radius * (banded ? 0.52 : 0.78),
      z: Math.sin(phi) * Math.sin(theta) * radius,
    };
  }

  function makeParticle() {
    const anchor = randomAnchor();
    const color = palette[Math.floor(Math.random() * palette.length)];
    const lane = Math.floor(Math.random() * 6);
    const orbitRadius = core.radius * (0.42 + lane * 0.105 + Math.random() * 0.08);
    const orbitTilt = -0.62 + lane * 0.22 + (Math.random() - 0.5) * 0.16;
    return {
      ax: anchor.x,
      ay: anchor.y,
      az: anchor.z,
      x: anchor.x,
      y: anchor.y,
      z: anchor.z,
      vx: 0,
      vy: 0,
      vz: 0,
      sx: core.x + anchor.x,
      sy: core.y + anchor.y,
      psx: core.x + anchor.x,
      psy: core.y + anchor.y,
      seed: Math.random() * 1000,
      spin: 0.62 + lane * 0.045 + Math.random() * 0.1,
      orbitPhase: Math.random() * Math.PI * 2,
      orbitRadius,
      orbitTilt,
      orbitY: core.radius * (0.08 + Math.random() * 0.24),
      orbitDepth: 0.68 + Math.random() * 0.42,
      size: 0.48 + Math.random() * 1.32,
      alpha: 0.34 + Math.random() * 0.34,
      color,
    };
  }

  function activePointer() {
    if (!pointers.size) return null;
    const points = Array.from(pointers.values());
    const sum = points.reduce((acc, point) => ({ x: acc.x + point.x, y: acc.y + point.y }), { x: 0, y: 0 });
    return { x: sum.x / points.length, y: sum.y / points.length };
  }

  function updatePointer(now) {
    const point = activePointer();
    if (point) {
      pointer.lastX = pointer.x;
      pointer.lastY = pointer.y;
      if (!pointer.active || now - pointer.lastMove > 120) {
        pointer.x = point.x;
        pointer.y = point.y;
      } else {
        pointer.x += (point.x - pointer.x) * 0.82;
        pointer.y += (point.y - pointer.y) * 0.82;
      }
      pointer.vx = pointer.x - pointer.lastX;
      pointer.vy = pointer.y - pointer.lastY;
      pointer.active = true;
      pointer.lastMove = now;
      targetEnergy = pointer.down ? 1.74 : 1.24;

      if (Math.hypot(pointer.vx, pointer.vy) > 0.7) {
        dragTrail.push({ x: pointer.x, y: pointer.y, life: 1 });
        if (dragTrail.length > 26) dragTrail.shift();
      }
    } else if (now - pointer.lastMove > 850) {
      pointer.active = false;
      pointer.down = false;
      pointer.vx *= 0.85;
      pointer.vy *= 0.85;
      targetEnergy = 0.86;
    }
    pointer.strength += ((pointer.active ? 1 : 0) - pointer.strength) * 0.18;
    core.energy += (targetEnergy - core.energy) * 0.08;
  }

  function updateCore(dt) {
    const idleX = width * 0.5;
    const idleY = height * 0.5;
    core.tx = idleX + (pointer.x - idleX) * pointer.strength * 0.96;
    core.ty = idleY + (pointer.y - idleY) * pointer.strength * 0.96;
    core.vx += (core.tx - core.x) * 0.16 * dt;
    core.vy += (core.ty - core.y) * 0.16 * dt;
    core.vx *= 0.66;
    core.vy *= 0.66;
    core.x += core.vx * dt;
    core.y += core.vy * dt;

    const targetCompression = pointer.down ? 0.56 : pointer.active ? 0.73 : 1;
    core.compression += (targetCompression - core.compression) * 0.055 * dt;
    core.spin += (0.008 + core.energy * 0.012) * dt;
  }

  function rotatedAnchor(point, now) {
    const orbitAngle = point.orbitPhase + core.spin * point.spin;
    const wobble = Math.sin(now * 0.0016 + point.seed) * core.radius * 0.016 * core.energy;
    let x = (Math.cos(orbitAngle) * point.orbitRadius + wobble) * core.compression;
    let y = (Math.sin(orbitAngle * 1.7 + point.seed) * point.orbitY + Math.cos(orbitAngle + point.seed) * wobble * 0.6) * core.compression;
    let z = (Math.sin(orbitAngle) * point.orbitRadius * point.orbitDepth) * core.compression;

    const tilt = point.orbitTilt;
    const cosT = Math.cos(tilt);
    const sinT = Math.sin(tilt);
    const y0 = y * cosT - z * sinT;
    const z0 = y * sinT + z * cosT;
    y = y0;
    z = z0;

    const rotY = core.spin * 0.36;
    const cosY = Math.cos(rotY);
    const sinY = Math.sin(rotY);
    const x1 = x * cosY + z * sinY;
    const z1 = -x * sinY + z * cosY;

    const rotX = Math.sin(core.spin * 0.42) * 0.2;
    const cosX = Math.cos(rotX);
    const sinX = Math.sin(rotX);
    return {
      x: x1,
      y: y * cosX - z1 * sinX,
      z: y * sinX + z1 * cosX,
    };
  }

  function project(point) {
    const fov = core.radius * 4.7;
    const scale = fov / (fov + point.z);
    return {
      x: core.x + point.x * scale,
      y: core.y + point.y * scale,
      scale,
    };
  }

  function updateParticles(dt, now) {
    updateCore(dt);
    particles.forEach((point) => {
      const target = rotatedAnchor(point, now);
      const spring = 0.026 + core.energy * 0.006;
      point.vx += (target.x - point.x) * spring * dt;
      point.vy += (target.y - point.y) * spring * dt;
      point.vz += (target.z - point.z) * spring * dt;

      const projected = project(point);
      if (pointer.strength > 0.01) {
        const dx = pointer.x - projected.x;
        const dy = pointer.y - projected.y;
        const dist = Math.max(18, Math.hypot(dx, dy));
        const radius = core.radius * (pointer.down ? 4.3 : 3.25);
        if (dist < radius) {
          const falloff = Math.pow(1 - dist / radius, 2);
          const fromCoreX = projected.x - core.x;
          const fromCoreY = projected.y - core.y;
          const fromCoreDist = Math.max(24, Math.hypot(fromCoreX, fromCoreY));
          const burst = (pointer.down ? 0.095 : 0.042) * falloff * pointer.strength;
          const pull = (pointer.down ? 0.14 : 0.066) * falloff * pointer.strength;
          const tangent = (pointer.down ? 0.2 : 0.12) * falloff * pointer.strength;
          const drag = Math.min(1.9, Math.hypot(pointer.vx, pointer.vy) / 8) * falloff;
          point.vx += ((dx / dist) * pull - (dy / dist) * tangent + pointer.vx * 0.018 * drag + (fromCoreX / fromCoreDist) * burst) * dt;
          point.vy += ((dy / dist) * pull + (dx / dist) * tangent + pointer.vy * 0.018 * drag + (fromCoreY / fromCoreDist) * burst) * dt;
          point.vz += (pointer.down ? -0.34 : 0.14) * falloff * dt;
        }
      }

      point.x += point.vx * dt;
      point.y += point.vy * dt;
      point.z += point.vz * dt;
      point.vx *= 0.88;
      point.vy *= 0.88;
      point.vz *= 0.88;

      const next = project(point);
      point.psx = Number.isFinite(point.sx) ? point.sx : next.x;
      point.psy = Number.isFinite(point.sy) ? point.sy : next.y;
      point.sx = next.x;
      point.sy = next.y;
      point.scale = next.scale;
    });

    for (let i = pulses.length - 1; i >= 0; i--) {
      const pulse = pulses[i];
      pulse.life -= 0.022 * dt;
      pulse.radius += (6.5 + pulse.force * 4.5) * dt;
      if (pulse.life <= 0) pulses.splice(i, 1);
    }
    for (let i = dragTrail.length - 1; i >= 0; i--) {
      dragTrail[i].life -= 0.035 * dt;
      if (dragTrail[i].life <= 0) dragTrail.splice(i, 1);
    }
  }

  function drawCoreAura(now) {
    const pulse = 1 + Math.sin(now * 0.004) * 0.05 + pointer.strength * 0.18;
    const auraRadius = core.radius * (1.72 + pointer.strength * 0.42);
    const aura = ctx.createRadialGradient(core.x, core.y, 0, core.x, core.y, auraRadius);
    aura.addColorStop(0, "rgba(240, 251, 255, 0.42)");
    aura.addColorStop(0.1, "rgba(125, 211, 252, 0.34)");
    aura.addColorStop(0.36, "rgba(14, 165, 233, 0.16)");
    aura.addColorStop(1, "rgba(14, 165, 233, 0)");
    ctx.globalAlpha = 0.72;
    ctx.fillStyle = aura;
    ctx.beginPath();
    ctx.arc(core.x, core.y, auraRadius, 0, Math.PI * 2);
    ctx.fill();

    ctx.lineWidth = 1.2;
    for (let i = 0; i < 3; i++) {
      const radius = core.radius * (0.86 + i * 0.28) * pulse;
      ctx.strokeStyle = `rgba(125, 211, 252, ${0.34 - i * 0.06})`;
      ctx.beginPath();
      ctx.ellipse(core.x, core.y, radius, radius * (0.45 + i * 0.08), core.spin * (0.45 + i * 0.16), 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  function drawDragTrail() {
    if (dragTrail.length < 2) return;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (let i = 1; i < dragTrail.length; i++) {
      const a = dragTrail[i - 1];
      const b = dragTrail[i];
      const alpha = Math.min(a.life, b.life) * 0.46;
      if (alpha <= 0) continue;
      const gradient = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
      gradient.addColorStop(0, `rgba(59, 130, 246, ${alpha * 0.15})`);
      gradient.addColorStop(1, `rgba(125, 211, 252, ${alpha})`);
      ctx.strokeStyle = gradient;
      ctx.lineWidth = 8 * alpha + 1;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
  }

  function semanticPosition(node, now) {
    const expanded = isExpandedMap();
    const laneRadius = core.radius * (expanded ? 1.18 + node.lane * 0.24 : 1.05 + node.lane * 0.16);
    const angle = node.phase + core.spin * (0.3 + node.lane * 0.035);
    const tilt = -0.54 + node.lane * 0.24;
    let x = Math.cos(angle) * laneRadius;
    let y = Math.sin(angle * 1.32 + node.lane) * core.radius * (expanded ? 0.2 : 0.13);
    let z = Math.sin(angle) * laneRadius * 0.82;
    const cosT = Math.cos(tilt);
    const sinT = Math.sin(tilt);
    const y1 = y * cosT - z * sinT;
    const z1 = y * sinT + z * cosT;
    const fov = core.radius * 5.1;
    const scale = fov / (fov + z1);
    return {
      node,
      x: core.x + x * scale,
      y: core.y + y1 * scale,
      z: z1,
      scale,
      radius: (expanded ? 5.8 : 4.2) * node.weight * Math.max(0.78, scale),
    };
  }

  function currentNodeLabel(node) {
    if (node.key === "github") return `GitHub v${state.version || "0.4.2"}`;
    if (node.key === "tasks") return state.phase === "awaiting_feedback" ? "待裁决任务" : "任务队列";
    if (node.key === "division" && state.division_status === "needs_user") return "分工待裁决";
    return node.label;
  }

  function drawSemanticLinks(positions) {
    const byKey = new Map(positions.map((item) => [item.node.key, item]));
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    semanticLinks.forEach(([aKey, bKey]) => {
      const a = byKey.get(aKey);
      const b = byKey.get(bKey);
      if (!a || !b) return;
      const alpha = isExpandedMap() ? 0.18 : 0.08;
      const gradient = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
      gradient.addColorStop(0, `${a.node.glow}11`);
      gradient.addColorStop(0.5, `rgba(125, 211, 252, ${alpha})`);
      gradient.addColorStop(1, `${b.node.glow}11`);
      ctx.strokeStyle = gradient;
      ctx.lineWidth = Math.max(0.7, (a.scale + b.scale) * 0.38);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    });
    ctx.restore();
  }

  function rectsOverlap(a, b) {
    return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  }

  function drawSemanticLabel(item, placedLabels = []) {
    const label = currentNodeLabel(item.node);
    const type = item.node.type;
    const padX = 8;
    const narrow = width < 560;
    const labelFont = isExpandedMap() ? (narrow ? "11px" : "12px") : "10px";
    ctx.save();
    ctx.font = `600 ${labelFont} ${getComputedStyle(document.documentElement).getPropertyValue("--font-sans") || "sans-serif"}`;
    const labelWidth = ctx.measureText(label).width;
    ctx.font = `500 10px ${getComputedStyle(document.documentElement).getPropertyValue("--font-mono") || "monospace"}`;
    const typeWidth = ctx.measureText(type).width;
    const boxWidth = Math.max(labelWidth, typeWidth) + padX * 2;
    const boxHeight = isExpandedMap() ? (narrow ? 34 : 38) : 28;
    let x = item.x + item.radius + 8;
    let y = item.y - boxHeight * 0.5;
    if (x + boxWidth > width - 8) x = item.x - item.radius - boxWidth - 8;
    x = Math.max(8, Math.min(width - boxWidth - 8, x));
    y = Math.max(8, Math.min(height - boxHeight - 8, y));
    const baseY = y;
    for (let attempt = 0; attempt < 12; attempt++) {
      const rect = { x, y, w: boxWidth, h: boxHeight };
      if (!placedLabels.some((placed) => rectsOverlap(rect, placed))) break;
      const step = boxHeight + 5;
      const direction = attempt % 2 === 0 ? 1 : -1;
      const distance = Math.ceil((attempt + 1) / 2) * step;
      y = Math.max(8, Math.min(height - boxHeight - 8, baseY + direction * distance));
    }
    placedLabels.push({ x, y, w: boxWidth, h: boxHeight });
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "rgba(5, 8, 16, 0.78)";
    ctx.strokeStyle = "rgba(125, 211, 252, 0.28)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(x, y, boxWidth, boxHeight, 6);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = item.node.color;
    ctx.font = `600 ${labelFont} ${getComputedStyle(document.documentElement).getPropertyValue("--font-sans") || "sans-serif"}`;
    ctx.fillText(label, x + padX, y + 16);
    if (isExpandedMap()) {
      ctx.fillStyle = "rgba(139, 143, 168, 0.92)";
      ctx.font = `500 ${narrow ? "9px" : "10px"} ${getComputedStyle(document.documentElement).getPropertyValue("--font-mono") || "monospace"}`;
      ctx.fillText(type, x + padX, y + (narrow ? 28 : 30));
    }
    ctx.restore();
  }

  function drawSemanticNodes(now) {
    const positions = semanticNodes.map((node) => semanticPosition(node, now)).sort((a, b) => b.z - a.z);
    const placedLabels = [];
    drawSemanticLinks(positions);
    hoveredSemantic = null;
    if (pointer.active) {
      let nearest = null;
      let nearestDistance = Infinity;
      positions.forEach((item) => {
        const d = Math.hypot(pointer.x - item.x, pointer.y - item.y);
        if (d < item.radius + 18 && d < nearestDistance) {
          nearest = item;
          nearestDistance = d;
        }
      });
      hoveredSemantic = nearest;
    }

    positions.forEach((item) => {
      const hover = hoveredSemantic && hoveredSemantic.node.key === item.node.key;
      const glowRadius = item.radius * (hover ? 6.8 : 4.8);
      const gradient = ctx.createRadialGradient(item.x, item.y, 0, item.x, item.y, glowRadius);
      gradient.addColorStop(0, `${item.node.color}ff`);
      gradient.addColorStop(0.22, `${item.node.glow}cc`);
      gradient.addColorStop(1, `${item.node.glow}00`);
      ctx.globalCompositeOperation = "lighter";
      ctx.globalAlpha = hover ? 0.96 : 0.7;
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(item.x, item.y, glowRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalCompositeOperation = "source-over";
      ctx.globalAlpha = 1;
      ctx.fillStyle = item.node.color;
      ctx.strokeStyle = item.node.glow;
      ctx.lineWidth = hover ? 2 : 1.2;
      ctx.beginPath();
      ctx.arc(item.x, item.y, item.radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      if (isExpandedMap() || hover) drawSemanticLabel(item, placedLabels);
    });
  }

  function drawParticle(point, now) {
    const speed = Math.hypot(point.sx - point.psx, point.sy - point.psy);
    const depth = Math.max(0.45, Math.min(1.55, point.scale || 1));
    const flicker = 0.78 + Math.sin(now * 0.003 + point.seed) * 0.22;
    const alpha = Math.min(0.78, point.alpha * flicker * (0.48 + depth * 0.22) * (0.84 + pointer.strength * 0.18));
    const radius = point.size * depth * (1.05 + pointer.strength * 0.18);

    if (speed > 0.35) {
      ctx.globalAlpha = Math.min(0.38, speed * 0.038) * alpha;
      ctx.strokeStyle = point.color.glow;
      ctx.lineWidth = Math.max(0.75, radius * 0.52);
      ctx.beginPath();
      ctx.moveTo(point.psx, point.psy);
      ctx.lineTo(point.sx, point.sy);
      ctx.stroke();
    }

    const glowRadius = radius * (3.15 + core.energy * 0.95);
    const gradient = ctx.createRadialGradient(point.sx, point.sy, 0, point.sx, point.sy, glowRadius);
    gradient.addColorStop(0, `${point.color.core}ff`);
    gradient.addColorStop(0.18, `${point.color.glow}b8`);
    gradient.addColorStop(0.54, `${point.color.glow}24`);
    gradient.addColorStop(1, `${point.color.glow}00`);
    ctx.globalAlpha = alpha;
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(point.sx, point.sy, glowRadius, 0, Math.PI * 2);
    ctx.fill();

    ctx.globalAlpha = Math.min(0.92, alpha + 0.22);
    ctx.fillStyle = point.color.core;
    ctx.beginPath();
    ctx.arc(point.sx, point.sy, Math.max(0.75, radius * 0.56), 0, Math.PI * 2);
    ctx.fill();
  }

  function drawForceField(now) {
    if (pointer.strength < 0.02) return;
    const pulse = Math.sin(now * 0.008) * 7;
    const base = core.radius * (pointer.down ? 0.86 : 0.68);
    ctx.save();
    ctx.translate(pointer.x, pointer.y);
    ctx.rotate(now * 0.0011);
    for (let i = 0; i < 4; i++) {
      ctx.globalAlpha = (0.48 - i * 0.075) * pointer.strength;
      ctx.strokeStyle = i % 2 ? "#38bdf8" : "#a5f3fc";
      ctx.lineWidth = 1.35;
      ctx.beginPath();
      ctx.arc(0, 0, base + i * 14 + pulse, i * 0.62, Math.PI * 1.35 + i * 0.62);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawPulses() {
    pulses.forEach((pulse) => {
      const alpha = Math.max(0, pulse.life);
      ctx.globalAlpha = alpha * 0.74;
      ctx.strokeStyle = pulse.color;
      ctx.lineWidth = 1.9 + pulse.force * 1.2;
      ctx.beginPath();
      ctx.arc(pulse.x, pulse.y, pulse.radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = alpha * 0.24;
      ctx.beginPath();
      ctx.arc(pulse.x, pulse.y, pulse.radius * 0.55, 0, Math.PI * 2);
      ctx.stroke();
    });
  }

  function draw(now) {
    ctx.clearRect(0, 0, width, height);
    ctx.globalCompositeOperation = "lighter";
    ctx.lineCap = "round";
    drawCoreAura(now);
    drawDragTrail();
    particles.slice().sort((a, b) => b.z - a.z).forEach((point) => drawParticle(point, now));
    drawSemanticNodes(now);
    drawForceField(now);
    drawPulses();
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }

  function animate(now) {
    const dt = Math.min(2.2, Math.max(0.55, (now - lastTime) / 16.67));
    lastTime = now;
    updatePointer(now);
    updateParticles(dt, now);
    draw(now);
    if (reduceMotion) {
      window.setTimeout(() => window.requestAnimationFrame(animate), 120);
    } else {
      window.requestAnimationFrame(animate);
    }
  }

  function addPulse(x, y, force = 1) {
    pulses.push({
      x,
      y,
      force,
      radius: core.radius * 0.28,
      life: 1,
      color: force > 1.2 ? "#7dd3fc" : "#38bdf8",
    });
    if (pulses.length > 8) pulses.shift();
  }

  function localPoint(event) {
    const rect = host.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(width, event.clientX - rect.left)),
      y: Math.max(0, Math.min(height, event.clientY - rect.top)),
    };
  }

  function syncPointerFromEvent(event) {
    pointers.set(event.pointerId, localPoint(event));
  }

  function updatePinchEnergy() {
    if (pointers.size === 2) {
      const points = Array.from(pointers.values());
      const distance = Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
      if (lastPinchDistance !== null) {
        targetEnergy = Math.max(0.72, Math.min(1.95, targetEnergy + (distance - lastPinchDistance) * 0.004));
      }
      lastPinchDistance = distance;
    } else {
      lastPinchDistance = null;
    }
  }

  window.addEventListener("resize", resize);
  if (window.ResizeObserver) {
    new ResizeObserver(resize).observe(host);
  }
  host.addEventListener("pointermove", (event) => {
    syncPointerFromEvent(event);
    updatePinchEnergy();
  }, { passive: true });
  host.addEventListener("pointerdown", (event) => {
    pointer.down = true;
    syncPointerFromEvent(event);
    updatePinchEnergy();
    const point = localPoint(event);
    addPulse(point.x, point.y, 1.4);
    try { host.setPointerCapture(event.pointerId); } catch (err) {}
  }, { passive: true });
  window.addEventListener("pointerup", (event) => {
    pointers.delete(event.pointerId);
    pointer.down = pointers.size > 0;
    lastPinchDistance = null;
    const point = localPoint(event);
    addPulse(point.x, point.y, 0.8);
  }, { passive: true });
  window.addEventListener("pointercancel", (event) => {
    pointers.delete(event.pointerId);
    pointer.down = pointers.size > 0;
    lastPinchDistance = null;
  }, { passive: true });
  host.addEventListener("pointerleave", (event) => {
    if (!pointer.down) {
      pointers.delete(event.pointerId);
      lastPinchDistance = null;
    }
  }, { passive: true });
  host.addEventListener("wheel", (event) => {
    event.preventDefault();
    const direction = event.deltaY < 0 ? 1 : -1;
    densityScale = Math.max(0.36, Math.min(1.38, densityScale + direction * 0.12));
    syncParticleCount(false);
    targetEnergy = Math.max(0.72, Math.min(1.95, targetEnergy + direction * 0.035));
    addPulse(pointer.active ? pointer.x : core.x, pointer.active ? pointer.y : core.y, 0.75 + densityScale * 0.3);
  }, { passive: false });

  if (resize()) {
    updateParticles(1, performance.now());
    draw(performance.now());
  }
  window.requestAnimationFrame((now) => {
    resize();
    lastTime = now;
    animate(now);
  });
}
