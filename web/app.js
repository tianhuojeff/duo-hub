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
const elGraphCanvas = $("#graph-canvas");

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
initGraphCanvas();
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
