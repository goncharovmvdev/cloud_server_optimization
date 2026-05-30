const dom = {
  kpiStrip: document.getElementById("kpi-strip"),
  canvasHint: document.getElementById("canvas-hint"),
  queueHint: document.getElementById("queue-hint"),
  poolCatalog: document.getElementById("pool-catalog"),
  resetClusterButton: document.getElementById("reset-cluster-btn"),
  deployForm: document.getElementById("deploy-form"),
  podServiceSelect: document.getElementById("pod-service-select"),
  podCpuInput: document.getElementById("pod-cpu-input"),
  podMemoryInput: document.getElementById("pod-memory-input"),
  clearPodsButton: document.getElementById("clear-pods-btn"),
  deploymentList: document.getElementById("deployment-list"),
  nodesGrid: document.getElementById("nodes-grid"),
  capacityCard: document.getElementById("capacity-card"),
  capacityGrid: document.getElementById("capacity-grid"),
  capacityHint: document.getElementById("capacity-hint"),
};

const state = {
  scheduler: "bin-packing",
  nodeCounts: {},
  pods: [],
  serviceCatalog: [],
  selectedServiceId: 0,
  nextPodNumber: 1,
};

const fmt = (value) => Number.parseFloat(value).toFixed(1);
const title = (value) => value.toUpperCase();

function nextPodId() {
  const id = `pod-${String(state.nextPodNumber).padStart(2, "0")}`;
  state.nextPodNumber += 1;
  return id;
}

function recomputeNextPodNumber() {
  const max = state.pods.reduce((acc, pod) => {
    const match = /^pod-(\d+)$/.exec(pod.id);
    return match ? Math.max(acc, Number.parseInt(match[1], 10)) : acc;
  }, 0);
  state.nextPodNumber = max + 1;
}

async function loadSnapshot() {
  const params = new URLSearchParams({
    pods: JSON.stringify(state.pods),
  });
  for (const [pool, count] of Object.entries(state.nodeCounts)) {
    params.set(`count_${pool}`, String(count));
  }

  const response = await fetch(`/api/snapshot?${params.toString()}`);
  if (!response.ok) {
    throw new Error("Failed to load cluster snapshot");
  }
  renderPayload(await response.json());
}

function renderPayload(payload) {
  state.scheduler = payload.scheduler;
  state.serviceCatalog = payload.service_catalog;
  state.nodeCounts = Object.fromEntries(
    payload.pool_catalog.map((pool) => [pool.name, pool.current_count]),
  );
  state.pods = payload.deployment_pods.map((pod) => ({
    id: pod.id,
    service_id: pod.service_id,
    cpu_request: pod.cpu_request,
    memory_request_gib: pod.memory_request_gib,
  }));
  if (!state.serviceCatalog.some((s) => s.id === state.selectedServiceId)) {
    state.selectedServiceId = state.serviceCatalog[0]?.id ?? 0;
  }
  recomputeNextPodNumber();

  renderServiceSelect(payload.service_catalog);
  renderPoolCatalog(payload.pool_catalog);
  renderKpi(payload.summary);
  renderNodes(payload.nodes);
  renderQueue(payload.deployment_pods);
  renderCapacityComparison(payload.capacity_comparison);
}

function renderCapacityComparison(comparison) {
  if (!comparison) {
    dom.capacityCard.hidden = true;
    return;
  }
  dom.capacityCard.hidden = false;

  const { bin_packing: bp, milp, savings, milp_error, max_per_pool } = comparison;

  const savingsBadge = savings && savings.per_hour > 0
    ? `<span class="chip lime">−$${fmt(savings.per_hour)}/h · ${fmt(savings.pct)} %</span>`
    : savings && savings.per_hour <= 0
      ? `<span class="chip muted">эвристика совпала с оптимумом</span>`
      : "";
  dom.capacityHint.innerHTML = `до ${max_per_pool} нод каждого пула · ${savingsBadge}`;

  const cards = [
    renderPlanCard("bin-packing", "FFD + cost-aware", "cyan", bp),
    milp
      ? renderPlanCard("MILP", "PuLP + CBC, оптимум", "lime", milp)
      : renderMilpError(milp_error),
  ];
  dom.capacityGrid.innerHTML = cards.join("");
}

function renderPlanCard(title, sub, tone, plan) {
  if (!plan) return "";
  const poolBreakdown = Object.entries(plan.pool_counts)
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([name, count]) => `<li><span>${name}</span><strong>×${count}</strong></li>`)
    .join("") || `<li class="muted">пусто</li>`;
  const unplaced = plan.unplaced_pods > 0
    ? `<div class="plan-warn">не размещено: ${plan.unplaced_pods} pod</div>`
    : "";
  const nodes = (plan.nodes || []).map(renderPlannedNode).join("");
  return `
    <article class="plan-card ${tone}">
      <header class="plan-head">
        <div>
          <div class="plan-title">${title}</div>
          <div class="plan-sub">${sub}</div>
        </div>
        <div class="plan-cost">
          <div class="plan-cost-value">$${fmt(plan.total_cost_per_hour)}<span class="plan-cost-unit">/h</span></div>
          <div class="plan-cost-day">$${fmt(plan.total_cost_per_day)} / day</div>
        </div>
      </header>
      <div class="plan-meta">
        <span><strong>${plan.active_nodes_count}</strong> нод</span>
      </div>
      <ul class="plan-pools">${poolBreakdown}</ul>
      ${nodes ? `<div class="plan-nodes">${nodes}</div>` : ""}
      ${unplaced}
    </article>
  `;
}

function renderPlannedNode(node) {
  const cpuWidth = Math.min(node.cpu_util_pct, 100);
  const memWidth = Math.min(node.memory_util_pct, 100);
  const pods = node.pods.length
    ? node.pods
        .map(
          (pod, i) => `
            <span class="pod-tag ${pod.service_class}" title="${pod.service_label} · ${fmt(pod.cpu_request)} cpu · ${fmt(pod.memory_request_gib)} GiB">
              ${pod.service_label.replace(/-.*/, "")}-${i + 1}
            </span>
          `,
        )
        .join("")
    : `<span class="no-pods">empty</span>`;
  return `
    <article class="plan-node pool-${node.pool_class}">
      <header class="plan-node-head">
        <div>
          <div class="plan-node-id">${node.id}</div>
          <div class="plan-node-sub">${node.pool_name} · $${fmt(node.cost_per_hour)}/h</div>
        </div>
        <div class="plan-node-counts">
          <span><strong>${node.pods.length}</strong> pod${node.pods.length === 1 ? "" : "s"}</span>
        </div>
      </header>
      <div class="plan-node-bars">
        ${renderMiniBar("cpu", "CPU", node.used_cpu, node.cpu_capacity, cpuWidth)}
        ${renderMiniBar("memory", "MEM", node.used_memory_gib, node.memory_capacity_gib, memWidth, "GiB")}
      </div>
      <div class="plan-node-pods">${pods}</div>
    </article>
  `;
}

function renderMiniBar(kind, label, used, total, width, unit = "") {
  const u = unit ? ` ${unit}` : "";
  return `
    <div class="bar">
      <div class="bar-meta">
        <span>${label}</span>
        <span><strong>${fmt(used)}</strong>${u} / ${fmt(total)}${u}</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill ${kind}" style="width:${width}%"></div>
      </div>
    </div>
  `;
}

function renderMilpError(message) {
  return `
    <article class="plan-card coral">
      <header class="plan-head">
        <div>
          <div class="plan-title">MILP</div>
          <div class="plan-sub">PuLP + CBC, оптимум</div>
        </div>
      </header>
      <div class="plan-warn">solver error: ${message || "unknown"}</div>
    </article>
  `;
}

function renderServiceSelect(serviceCatalog) {
  dom.podServiceSelect.innerHTML = serviceCatalog
    .map(
      (service) => `
        <option value="${service.id}">${service.service_label} · ${service.image_label}</option>
      `,
    )
    .join("");
  dom.podServiceSelect.value = String(state.selectedServiceId);
}

function renderKpi(summary) {
  const cards = [
    {
      tone: "cyan",
      label: "Nodes",
      value: summary.running_nodes,
      unit: `/ ${summary.inventory_nodes}`,
      sub: `${summary.cold_nodes} idle in inventory`,
    },
    {
      tone: "lime",
      label: "Pods",
      value: summary.deployed_pods,
      unit: summary.pending_pods ? `· ${summary.pending_pods} pending` : "",
      sub: summary.pending_pods ? "scheduling pressure detected" : "all requests placed",
    },
    {
      tone: "violet",
      label: "CPU",
      value: fmt(summary.cluster_cpu - summary.free_active_cpu),
      unit: `/ ${fmt(summary.cluster_cpu)}`,
      sub: `${fmt(summary.free_active_cpu)} free`,
    },
    {
      tone: "coral",
      label: "Cost · $/h",
      value: `$${fmt(summary.running_cost_per_hour)}`,
      unit: `· $${fmt(summary.running_cost_per_day)}/day`,
      sub: summary.cluster_cost_per_hour > summary.running_cost_per_hour
        ? `$${fmt(summary.cluster_cost_per_hour - summary.running_cost_per_hour)}/h idle in pool`
        : "all inventory in use",
    },
  ];

  dom.kpiStrip.innerHTML = cards
    .map(
      (card) => `
        <article class="kpi ${card.tone}">
          <div class="kpi-label">${card.label}</div>
          <div class="kpi-value">${card.value}${
            card.unit ? `<span class="kpi-unit">${card.unit}</span>` : ""
          }</div>
          <div class="kpi-sub">${card.sub}</div>
        </article>
      `,
    )
    .join("");
}

function renderPoolCatalog(catalog) {
  dom.poolCatalog.innerHTML = catalog
    .map(
      (pool) => `
        <article class="pool-item pool-${pool.pool_class}">
          <div class="pool-row">
            <div class="pool-name">${pool.display_name}</div>
            <div class="pool-count">×${pool.current_count} · $${fmt(pool.per_node_cost_per_hour)}/h</div>
          </div>
          <div class="pool-spec">
            ${fmt(pool.per_node_cpu)} cpu · ${fmt(pool.per_node_memory_gib)} GiB · ${pool.per_node_pods} pods
          </div>
          <div class="pool-controls">
            <button
              class="ghost"
              type="button"
              data-action="decrement"
              data-pool-name="${pool.name}"
              ${pool.current_count === 0 ? "disabled" : ""}
            >−</button>
            <button
              class="btn subtle"
              type="button"
              data-action="increment"
              data-pool-name="${pool.name}"
            >+ add</button>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderNodes(nodes) {
  dom.canvasHint.textContent = nodes.length
    ? `${nodes.length} node${nodes.length === 1 ? "" : "s"} in cluster`
    : "add nodes to start";

  if (!nodes.length) {
    dom.nodesGrid.innerHTML = `
      <div class="empty">
        <h3>Cluster is empty</h3>
        <p>Pick a pool from the rail to spin up a worker node.</p>
      </div>
    `;
    return;
  }

  dom.nodesGrid.innerHTML = nodes
    .map((node, index) => {
      const cpuWidth = Math.min(node.cpu_util_pct, 100);
      const memoryWidth = Math.min(node.memory_util_pct, 100);
      const podWidth = node.total_pods === 0
        ? 0
        : (node.used_pods / node.total_pods) * 100;
      const podsMarkup = node.pods.length
        ? node.pods
            .map(
              (pod) => `
                <span class="pod-tag ${pod.service_class}" title="${pod.service_label} · ${pod.image_label}">${pod.id}</span>
              `,
            )
            .join("")
        : `<span class="no-pods">no pods scheduled</span>`;

      return `
        <article class="node ${node.state} pool-${node.pool_class}" style="animation-delay:${index * 35}ms">
          <header class="node-head">
            <div>
              <h3 class="node-id">${node.id}</h3>
              <div class="node-pool">${node.pool_name} · $${fmt(node.cost_per_hour)}/h</div>
            </div>
            <span class="state ${node.state}">${node.state}</span>
          </header>

          <div class="bars">
            ${renderBar("cpu", "CPU", node.used_cpu, node.total_cpu, cpuWidth)}
            ${renderBar("memory", "MEM", node.used_memory_gib, node.total_memory_gib, memoryWidth, "GiB")}
            ${renderBar("pods", "PODS", node.used_pods, node.total_pods, podWidth)}
          </div>

          <div class="node-pods">${podsMarkup}</div>
        </article>
      `;
    })
    .join("");
}

function renderBar(kind, label, used, total, width, unit = "") {
  const u = unit ? ` ${unit}` : "";
  return `
    <div class="bar">
      <div class="bar-meta">
        <span>${label}</span>
        <span><strong>${fmt(used)}</strong>${u} / ${fmt(total)}${u}</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill ${kind}" style="width:${width}%"></div>
      </div>
    </div>
  `;
}

function renderQueue(pods) {
  const scheduled = pods.filter((pod) => pod.status === "scheduled").length;
  const pending = pods.filter((pod) => pod.status === "pending").length;
  dom.queueHint.textContent = pods.length
    ? `${scheduled} scheduled · ${pending} pending`
    : "empty";

  if (!pods.length) {
    dom.deploymentList.innerHTML = `
      <div class="empty">
        <h3>Queue is empty</h3>
        <p>Fill the deploy form on the left and hit <strong>Deploy</strong> to enqueue a pod.</p>
      </div>
    `;
    return;
  }

  dom.deploymentList.innerHTML = pods
    .map(
      (pod) => `
        <article class="deployment-row service-${pod.service_id} ${pod.status}">
          <div class="deployment-main">
            <div class="deployment-id">${pod.id}</div>
            <div class="deployment-service">${pod.service_label} · ${pod.image_label}</div>
            <div class="deployment-reqs">${fmt(pod.cpu_request)} cpu · ${fmt(pod.memory_request_gib)} GiB</div>
          </div>
          <div class="deployment-status">
            <span class="chip ${pod.status}">${pod.status}</span>
            <span class="deployment-status-text">${pod.status_label}</span>
          </div>
          <button class="deployment-remove" type="button" data-action="remove-pod" data-pod-id="${pod.id}">
            remove
          </button>
          ${renderSchedulerDecision(pod.scheduler_decision)}
        </article>
      `,
    )
    .join("");
}

function renderSchedulerDecision(decision) {
  if (!decision) return "";

  const cards = decision.node_evaluations
    .map((evaluation) => renderNodeEvaluation(evaluation))
    .join("");

  return `
    <details class="decision">
      <summary>
        <span>scheduler decision</span>
        <span class="decision-text">${decision.summary}</span>
      </summary>
      <div class="decision-meta">
        <div class="decision-meta-cell">
          <div class="decision-meta-label">scheduler</div>
          <div class="decision-meta-value">${title(decision.scheduler)}</div>
        </div>
        <div class="decision-meta-cell">
          <div class="decision-meta-label">step</div>
          <div class="decision-meta-value">${decision.schedule_step} of ${decision.total_pods_in_order} · sorted by size</div>
        </div>
        <div class="decision-meta-cell">
          <div class="decision-meta-label">weights</div>
          <div class="decision-meta-value">fit ${fmt(decision.weights.node_resources_fit)} · image ${fmt(decision.weights.image_locality)}</div>
        </div>
      </div>
      <div class="decision-grid">${cards}</div>
    </details>
  `;
}

function renderNodeEvaluation(evaluation) {
  if (evaluation.status === "filtered") {
    const reasons = evaluation.filter_reasons
      .map((reason) => `<li>${reason}</li>`)
      .join("");
    return `
      <article class="decision-card filtered">
        <div class="decision-card-head">
          <div>
            <div class="decision-node">${evaluation.node_id}</div>
            <div class="decision-node-sub">${evaluation.pool_name}</div>
          </div>
          <span class="chip filtered">filtered</span>
        </div>
        <div class="decision-reason">${evaluation.decision_reason}</div>
        <ul class="decision-reasons">${reasons}</ul>
      </article>
    `;
  }

  const breakdown = evaluation.score_breakdown;
  const chosen = evaluation.rank === 1;
  return `
    <article class="decision-card scored ${chosen ? "chosen" : ""}">
      <div class="decision-card-head">
        <div>
          <div class="decision-node">${evaluation.node_id}</div>
          <div class="decision-node-sub">${evaluation.pool_name}</div>
        </div>
        <span class="chip scored">${chosen ? "chosen" : `#${evaluation.rank}`}</span>
      </div>
      <div class="decision-reason">${evaluation.decision_reason}</div>
      <div class="decision-scores">
        ${renderScoreCell("total", breakdown.weighted_total)}
        ${renderScoreCell("least-alloc", breakdown.node_resources_fit)}
        ${renderScoreCell("locality", breakdown.image_locality)}
      </div>
      <div class="decision-after">
        <span>${fmt(breakdown.cpu_util_after_pct)}% cpu after</span>
        <span>${fmt(breakdown.memory_util_after_pct)}% mem after</span>
      </div>
    </article>
  `;
}

function renderScoreCell(label, value) {
  const width = Math.max(0, Math.min(100, Number(value)));
  return `
    <div class="decision-score">
      <div class="decision-score-label">${label}</div>
      <div class="decision-score-value">${fmt(value)}</div>
      <div class="decision-fill"><span style="width:${width}%"></span></div>
    </div>
  `;
}

function installListeners() {
  dom.podServiceSelect.addEventListener("change", () => {
    const serviceId = Number.parseInt(dom.podServiceSelect.value, 10);
    if (Number.isInteger(serviceId) && serviceId >= 0) {
      state.selectedServiceId = serviceId;
    }
  });

  dom.poolCatalog.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const poolName = target.dataset.poolName;
    const action = target.dataset.action;
    if (!poolName || !action) return;

    const current = state.nodeCounts[poolName] ?? 0;
    if (action === "increment") {
      state.nodeCounts[poolName] = current + 1;
    } else if (action === "decrement") {
      state.nodeCounts[poolName] = Math.max(current - 1, 0);
    }
    loadSnapshot().catch(renderError);
  });

  dom.resetClusterButton.addEventListener("click", () => {
    for (const name of Object.keys(state.nodeCounts)) {
      state.nodeCounts[name] = 0;
    }
    loadSnapshot().catch(renderError);
  });

  dom.deployForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const serviceId = Number.parseInt(dom.podServiceSelect.value, 10);
    const cpu = Number.parseFloat(dom.podCpuInput.value);
    const memory = Number.parseFloat(dom.podMemoryInput.value);
    if (!Number.isInteger(serviceId) || serviceId < 0) {
      renderError(new Error("Select a valid service / image"));
      return;
    }
    if (!(cpu > 0) || !(memory > 0)) {
      renderError(new Error("CPU and memory must be positive"));
      return;
    }
    state.selectedServiceId = serviceId;
    state.pods.push({
      id: nextPodId(),
      service_id: serviceId,
      cpu_request: cpu,
      memory_request_gib: memory,
    });
    loadSnapshot().catch(renderError);
  });

  dom.clearPodsButton.addEventListener("click", () => {
    state.pods = [];
    recomputeNextPodNumber();
    loadSnapshot().catch(renderError);
  });

  dom.deploymentList.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.dataset.action !== "remove-pod") return;
    const podId = target.dataset.podId;
    if (!podId) return;
    state.pods = state.pods.filter((pod) => pod.id !== podId);
    recomputeNextPodNumber();
    loadSnapshot().catch(renderError);
  });
}

function renderError(error) {
  dom.kpiStrip.innerHTML = `
    <article class="kpi coral">
      <div class="kpi-label">Error</div>
      <div class="kpi-value">offline</div>
      <div class="kpi-sub">${error.message}</div>
    </article>
  `;
}

installListeners();
loadSnapshot().catch(renderError);
