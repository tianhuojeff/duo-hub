(function () {
  let mounted = false;
  let rootEl = null;
  let shellEl = null;
  let nodesEl = null;
  let feedEl = null;
  let phaseEl = null;
  let taskEl = null;
  const nodeEls = new Map();

  function shortText(text, max = 96) {
    const compact = String(text || "").replace(/\s+/g, " ").trim();
    return compact.length > max ? compact.slice(0, max) + "..." : compact;
  }

  function recentActivity(messages, id) {
    for (let i = (messages || []).length - 1; i >= 0; i -= 1) {
      const msg = messages[i];
      if (msg.role === id) return msg.content || "";
    }
    return "";
  }

  function make(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function init(container) {
    if (!container || mounted) return;
    rootEl = container;
    shellEl = make("div", "supervisor-status");
    shellEl.dataset.phase = "idle";

    const mapEl = make("div", "supervisor-status__map");
    const coreEl = make("div", "supervisor-status__core");
    coreEl.append(make("span", "supervisor-status__core-pulse"));
    coreEl.append(make("strong", "", "Codex 主管"));
    coreEl.append(make("small", "", "主对话 / 分工 / 派发"));
    mapEl.append(coreEl);
    nodesEl = make("div", "supervisor-status__nodes");
    mapEl.append(nodesEl);

    const sideEl = make("div", "supervisor-status__side");
    const phaseBox = make("div", "supervisor-status__phase");
    phaseBox.append(make("span", "", "PHASE"));
    phaseEl = make("strong", "", "idle");
    phaseBox.append(phaseEl);
    sideEl.append(phaseBox);
    taskEl = make("div", "supervisor-status__task", "等待 Codex 派发 Agent 任务");
    sideEl.append(taskEl);
    feedEl = make("div", "supervisor-status__feed");
    sideEl.append(feedEl);

    shellEl.append(mapEl, sideEl);
    rootEl.replaceChildren(shellEl);
    mounted = true;
  }

  function buildNode(agent) {
    const el = make("div", "supervisor-status__agent");
    el.dataset.agent = agent.id;
    el.dataset.status = "idle";
    el.style.setProperty("--agent-color", agent.color || "#38bdf8");
    el.append(make("span", "supervisor-status__agent-ring"));
    el.append(make("span", "supervisor-status__agent-icon", agent.icon || "AI"));
    const copy = make("div", "supervisor-status__agent-copy");
    copy.append(make("strong", "", agent.label || agent.id));
    copy.append(make("span", "supervisor-status__agent-status", "idle"));
    copy.append(make("small", "supervisor-status__agent-model", "standby"));
    el.append(copy);
    return el;
  }

  function reconcileAgents(agents) {
    const activeIds = new Set((agents || []).map((agent) => agent.id));
    for (const [id, el] of nodeEls.entries()) {
      if (!activeIds.has(id)) {
        el.remove();
        nodeEls.delete(id);
      }
    }
    for (const agent of agents || []) {
      if (nodeEls.has(agent.id)) continue;
      const el = buildNode(agent);
      nodeEls.set(agent.id, el);
      nodesEl.append(el);
    }
  }

  function renderFeed(state, agentMap) {
    const allowedRoles = new Set(["codex", "system", ...agentMap.keys()]);
    const messages = (state.messages || [])
      .filter((msg) => allowedRoles.has(msg.role))
      .slice(-4)
      .reverse();
    feedEl.replaceChildren();
    if (!messages.length) {
      feedEl.append(make("div", "supervisor-status__empty", "暂无分工记录"));
      return;
    }
    for (const msg of messages) {
      const item = make("div", "supervisor-status__feed-item");
      item.dataset.role = msg.role;
      const agent = agentMap.get(msg.role);
      item.append(make("span", "", msg.role === "system" ? "系统" : (agent?.label || msg.role)));
      item.append(make("p", "", shortText(msg.content, 110)));
      item.append(make("time", "", msg.timestamp ? msg.timestamp.slice(11, 16) : ""));
      feedEl.append(item);
    }
  }

  function update(state) {
    if (!mounted || !state) return;
    const agents = state.agents || [];
    const agentMap = new Map(agents.map((agent) => [agent.id, agent]));
    reconcileAgents(agents);
    shellEl.dataset.phase = state.phase || "idle";
    phaseEl.textContent = state.phase || "idle";
    taskEl.textContent = state.active_task_id
      ? `当前任务：${state.active_task_id}`
      : "等待 Codex 派发 Agent 任务";

    for (const agent of agents) {
      const el = nodeEls.get(agent.id);
      if (!el) continue;
      const status = agent.status || "idle";
      const gatewayOnline = Boolean(state.gateways && state.gateways[agent.gateway || agent.id]);
      el.dataset.status = status;
      el.dataset.gateway = gatewayOnline ? "online" : "offline";
      el.querySelector(".supervisor-status__agent-status").textContent =
        `${status}${gatewayOnline ? " / online" : " / offline"}`;
      el.querySelector(".supervisor-status__agent-model").textContent =
        agent.model || shortText(recentActivity(state.messages, agent.id), 42) || "standby";
    }
    renderFeed(state, agentMap);
  }

  window.DuoSupervisorStatus = { init, update };
})();
