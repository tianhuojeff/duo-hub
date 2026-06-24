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
const elBtnRenegotiate = $("#btn-renegotiate");
const elConfirmBar = $("#confirm-bar");
const elPhaseText = $("#phase-text");
const elSessionId = $("#session-id");
const elGwCcmr = $("#gw-ccmr");
const elGwLobster = $("#gw-lobster");
const elGwCodex = $("#gw-codex");

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

async function triggerNegotiate() {
  const res = await fetch("/api/negotiate", { method: "POST" });
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
  if (data.division && (data.phase === "pending_confirmation" || data.phase === "executing" || data.phase === "done")) {
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
    bodyEl.innerHTML = html || '<em>协商中…</em>';
    divEl.style.display = "block";
  } else {
    document.getElementById("division-result").style.display = "none";
  }
}

function handlePhaseChange(newPhase, prevPhase) {
  // 进入确认阶段
  if (newPhase === "pending_confirmation") {
    elConfirmBar.style.display = "flex";
  }
  // 离开确认阶段
  if (prevPhase === "pending_confirmation" && newPhase !== "pending_confirmation") {
    elConfirmBar.style.display = "none";
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
  const working = state.phase === "ai_working" || state.phase === "negotiating";
  const confirming = state.phase === "pending_confirmation";
  elBtnSend.disabled = working;
  elBtnSend.textContent = working ? "⏳ 处理中…" : "🚀 发送";
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

elBtnRenegotiate.addEventListener("click", async () => {
  if (await triggerNegotiate()) {
    lastMsgCount = 0;
    elClaudeOutput.innerHTML = '<div class="placeholder">🤝 重新协商中…</div>';
    elLobsterOutput.innerHTML = '<div class="placeholder">🤝 重新协商中…</div>';
    elCodexOutput.innerHTML = '<div class="placeholder">🤝 重新协商中…</div>';
    taskStartTime = Date.now();
    startElapsedTimer();
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

// === 启动 ===
fetchState();
setInterval(fetchState, POLL_INTERVAL);
console.log("⚡ Duo Hub 三方前端已就绪");
