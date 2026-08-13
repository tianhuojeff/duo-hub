(function () {
  const agentMeta = {
    claude: { name: "Claude", icon: "Cl", gateway: "ccmr" },
    lobster: { name: "龙虾", icon: "Lo", gateway: "openclaw" },
    codex: { name: "Codex CLI", icon: "Cx", gateway: "codex" },
  };

  let mounted = false;
  let rootEl = null;
  let nodeEls = {};
  let feedEl = null;
  let phaseEl = null;
  let taskEl = null;

  function statusOf(state, id) {
    const agent = (state.agents || []).find((item) => item.id === id) || {};
    return agent.status || state[`${id}_status`] || "idle";
  }

  function modelOf(state, id) {
    const agent = (state.agents || []).find((item) => item.id === id) || {};
    return agent.model || state[`${id}_model`] || "";
  }

  function recentActivity(messages, id) {
    for (let i = (messages || []).length - 1; i >= 0; i -= 1) {
      const msg = messages[i];
      if (msg.role === id) return msg.content || "";
    }
    return "";
  }

  function shortText(text, max = 96) {
    const compact = String(text || "").replace(/\s+/g, " ").trim();
    return compact.length > max ? compact.slice(0, max) + "..." : compact;
  }

  function buildNode(id) {
    const meta = agentMeta[id];
    return `
      <div class="supervisor-status__agent" data-agent="${id}" data-status="idle">
        <span class="supervisor-status__agent-ring"></span>
        <span class="supervisor-status__agent-icon">${meta.icon}</span>
        <div class="supervisor-status__agent-copy">
          <strong>${meta.name}</strong>
          <span class="supervisor-status__agent-status">idle</span>
          <small class="supervisor-status__agent-model"></small>
        </div>
      </div>
    `;
  }

  function init(container) {
    if (!container || mounted) return;
    rootEl = container;
    rootEl.innerHTML = `
      <div class="supervisor-status" data-phase="idle">
        <div class="supervisor-status__map">
          <div class="supervisor-status__core">
            <span class="supervisor-status__core-pulse"></span>
            <strong>Codex 主管</strong>
            <small>主对话 / 分工 / 派发</small>
          </div>
          <span class="supervisor-status__link supervisor-status__link--claude"></span>
          <span class="supervisor-status__link supervisor-status__link--lobster"></span>
          <span class="supervisor-status__link supervisor-status__link--codex"></span>
          <div class="supervisor-status__nodes">
            ${buildNode("claude")}
            ${buildNode("lobster")}
            ${buildNode("codex")}
          </div>
        </div>
        <div class="supervisor-status__side">
          <div class="supervisor-status__phase">
            <span>PHASE</span>
            <strong data-role="phase">idle</strong>
          </div>
          <div class="supervisor-status__task" data-role="task">等待 Codex 派发三方分工</div>
          <div class="supervisor-status__feed" data-role="feed"></div>
        </div>
      </div>
    `;
    nodeEls = Object.fromEntries(
      Object.keys(agentMeta).map((id) => [id, rootEl.querySelector(`[data-agent="${id}"]`)]),
    );
    feedEl = rootEl.querySelector('[data-role="feed"]');
    phaseEl = rootEl.querySelector('[data-role="phase"]');
    taskEl = rootEl.querySelector('[data-role="task"]');
    mounted = true;
  }

  function update(state) {
    if (!mounted || !state) return;
    const shell = rootEl.querySelector(".supervisor-status");
    shell.dataset.phase = state.phase || "idle";
    phaseEl.textContent = state.phase || "idle";
    taskEl.textContent = state.active_task_id
      ? `当前任务：${state.active_task_id}`
      : "等待 Codex 派发三方分工";

    for (const id of Object.keys(agentMeta)) {
      const el = nodeEls[id];
      const status = statusOf(state, id);
      const model = modelOf(state, id);
      const gatewayName = agentMeta[id].gateway;
      const gatewayOnline = state.gateways && state.gateways[gatewayName];
      el.dataset.status = status;
      el.dataset.gateway = gatewayOnline ? "online" : "offline";
      el.querySelector(".supervisor-status__agent-status").textContent =
        `${status}${gatewayOnline ? " / online" : " / offline"}`;
      el.querySelector(".supervisor-status__agent-model").textContent =
        model || shortText(recentActivity(state.messages, id), 42) || "standby";
    }

    const feed = (state.messages || [])
      .filter((msg) => ["codex", "claude", "lobster", "system"].includes(msg.role))
      .slice(-4)
      .reverse()
      .map((msg) => {
        const label = msg.role === "system" ? "系统" : (agentMeta[msg.role]?.name || msg.role);
        const time = msg.timestamp ? msg.timestamp.slice(11, 16) : "";
        return `
          <div class="supervisor-status__feed-item" data-role="${msg.role}">
            <span>${label}</span>
            <p>${shortText(msg.content, 110)}</p>
            <time>${time}</time>
          </div>
        `;
      })
      .join("");
    feedEl.innerHTML = feed || '<div class="supervisor-status__empty">暂无分工记录</div>';
  }

  window.DuoSupervisorStatus = { init, update };
})();
