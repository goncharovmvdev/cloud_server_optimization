const policySelect = document.getElementById("policy-select");
const policyPill = document.getElementById("policy-pill");
const summaryGrid = document.getElementById("summary-grid");
const notesList = document.getElementById("notes-list");
const poolCatalog = document.getElementById("pool-catalog");
const resetClusterButton = document.getElementById("reset-cluster-btn");
const deployForm = document.getElementById("deploy-form");
const podServiceSelect = document.getElementById("pod-service-select");
const podCpuInput = document.getElementById("pod-cpu-input");
const podMemoryInput = document.getElementById("pod-memory-input");
const clearPodsButton = document.getElementById("clear-pods-btn");
const deploymentList = document.getElementById("deployment-list");
const nodesGrid = document.getElementById("nodes-grid");

const state = {
  policy: "hybrid",
  loadedPolicies: false,
  nodeCounts: {},
  pods: [],
  serviceCatalog: [],
  selectedServiceId: 0,
  nextPodNumber: 1,
};

function formatNumber(value) {
  return Number.parseFloat(value).toFixed(1);
}

function policyTitle(policy) {
  return policy.toUpperCase();
}

function nextPodId() {
  const id = `pod-${String(state.nextPodNumber).padStart(2, "0")}`;
  state.nextPodNumber += 1;
  return id;
}

function recomputeNextPodNumber() {
  const maxNumber = state.pods.reduce((currentMax, pod) => {
    const match = /^pod-(\d+)$/.exec(pod.id);
    if (!match) {
      return currentMax;
    }
    return Math.max(currentMax, Number.parseInt(match[1], 10));
  }, 0);
  state.nextPodNumber = maxNumber + 1;
}

async function loadSnapshot() {
  const params = new URLSearchParams({
    policy: state.policy,
    pods: JSON.stringify(state.pods),
  });

  for (const [poolName, count] of Object.entries(state.nodeCounts)) {
    params.set(`count_${poolName}`, String(count));
  }

  const response = await fetch(`/api/snapshot?${params.toString()}`);
  if (!response.ok) {
    throw new Error("Failed to load cluster snapshot");
  }

  const payload = await response.json();
  renderPayload(payload);
}

function renderPayload(payload) {
  if (!state.loadedPolicies) {
    policySelect.innerHTML = payload.policies
      .map((policy) => `<option value="${policy}">${policyTitle(policy)}</option>`)
      .join("");
    state.loadedPolicies = true;
  }

  state.policy = payload.policy;
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
  if (!state.serviceCatalog.some((service) => service.id === state.selectedServiceId)) {
    state.selectedServiceId = state.serviceCatalog.length > 0 ? state.serviceCatalog[0].id : 0;
  }
  recomputeNextPodNumber();

  policySelect.value = payload.policy;
  policyPill.textContent = policyTitle(payload.policy);

  renderServiceSelect(payload.service_catalog);
  renderPoolCatalog(payload.pool_catalog);
  renderSummary(payload.summary);
  renderDeploymentList(payload.deployment_pods);
  renderNotes(payload.notes);
  renderNodes(payload.nodes);
}

function renderServiceSelect(serviceCatalog) {
  podServiceSelect.innerHTML = serviceCatalog
    .map(
      (service) => `
        <option value="${service.id}">
          ${service.service_label} (${service.image_label})
        </option>
      `,
    )
    .join("");
  podServiceSelect.value = String(state.selectedServiceId);
}

function renderSummary(summary) {
  const cards = [
    {
      label: "Inventory Nodes",
      value: summary.inventory_nodes,
      subtitle: `${summary.cold_nodes} idle nodes in cluster`,
    },
    {
      label: "Running Nodes",
      value: summary.running_nodes,
      subtitle: "nodes with at least one scheduled pod",
    },
    {
      label: "Scheduled Pods",
      value: summary.deployed_pods,
      subtitle: `${summary.pending_pods} pending`,
    },
    {
      label: "Requested CPU",
      value: formatNumber(summary.requested_cpu),
      subtitle: `${formatNumber(summary.cluster_cpu)} cluster CPU total`,
    },
    {
      label: "Requested Memory",
      value: `${formatNumber(summary.requested_memory_gib)}`,
      subtitle: `${formatNumber(summary.cluster_memory_gib)} GiB cluster total`,
    },
    {
      label: "Free CPU",
      value: formatNumber(summary.free_active_cpu),
      subtitle: `${formatNumber(summary.free_active_memory_gib)} GiB memory free`,
    },
  ];

  summaryGrid.innerHTML = cards
    .map(
      (card) => `
        <article class="summary-card">
          <div class="summary-label">${card.label}</div>
          <div class="summary-value">${card.value}</div>
          <div class="summary-subtitle">${card.subtitle}</div>
        </article>
      `,
    )
    .join("");
}

function renderPoolCatalog(catalog) {
  poolCatalog.innerHTML = catalog
    .map(
      (pool) => `
        <article class="pool-card pool-${pool.pool_class}">
          <div class="pool-card-header">
            <div>
              <h3 class="pool-name">${pool.display_name}</h3>
              <div class="pool-count">${pool.current_count} nodes in cluster</div>
            </div>
            <div class="pool-badge">${pool.name}</div>
          </div>

          <div class="pool-stats">
            <div class="pool-stat">
              <span class="pool-stat-label">Schedulable CPU</span>
              <span class="pool-stat-value">${formatNumber(pool.per_node_cpu)}</span>
            </div>
            <div class="pool-stat">
              <span class="pool-stat-label">Schedulable Memory</span>
              <span class="pool-stat-value">${formatNumber(pool.per_node_memory_gib)} GiB</span>
            </div>
            <div class="pool-stat">
              <span class="pool-stat-label">Max Pods</span>
              <span class="pool-stat-value">${pool.per_node_pods}</span>
            </div>
          </div>

          <div class="pool-actions">
            <button
              class="counter-button"
              type="button"
              data-action="decrement"
              data-pool-name="${pool.name}"
              ${pool.current_count === 0 ? "disabled" : ""}
            >
              Remove
            </button>
            <button
              class="counter-button add"
              type="button"
              data-action="increment"
              data-pool-name="${pool.name}"
            >
              Add node
            </button>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderDeploymentList(pods) {
  if (pods.length === 0) {
    deploymentList.innerHTML = `
      <article class="deployment-empty">
        <h3>Пока нет pod requests</h3>
        <p>Введите CPU и Memory, затем нажмите Deploy pod.</p>
      </article>
    `;
    return;
  }

  deploymentList.innerHTML = pods
    .map(
      (pod) => `
        <article class="deployment-row ${pod.status}">
          <div class="deployment-main">
            <div class="deployment-name">${pod.id}</div>
            <div class="deployment-service">${pod.service_label} / ${pod.image_label}</div>
            <div class="deployment-reqs">${formatNumber(pod.cpu_request)} CPU / ${formatNumber(pod.memory_request_gib)} GiB</div>
          </div>
          <div class="deployment-status">
            <div class="deployment-status-chip ${pod.status}">${pod.status}</div>
            <div class="deployment-status-text">${pod.status_label}</div>
          </div>
          <button
            class="deployment-remove"
            type="button"
            data-action="remove-pod"
            data-pod-id="${pod.id}"
          >
            Remove
          </button>
          ${renderSchedulerDecision(pod.scheduler_decision)}
        </article>
      `,
    )
    .join("");
}

function renderSchedulerDecision(decision) {
  if (!decision) {
    return "";
  }

  const orderMode = decision.sort_largest_pods_first
    ? "pod'ы отсортированы по размеру перед планированием"
    : "pod'ы планируются в порядке поступления";

  const nodeEvaluations = decision.node_evaluations
    .map((evaluation) => renderNodeEvaluation(evaluation))
    .join("");

  return `
    <details class="decision-details">
      <summary class="decision-summary">
        <span class="decision-summary-title">Решение шедулера</span>
        <span class="decision-summary-text">${decision.summary}</span>
      </summary>
      <div class="decision-meta">
        <div class="decision-meta-item">
          <span class="decision-meta-label">Политика</span>
          <span class="decision-meta-value">${policyTitle(decision.policy)}</span>
        </div>
        <div class="decision-meta-item">
          <span class="decision-meta-label">Порядок</span>
          <span class="decision-meta-value">шаг ${decision.schedule_step}/${decision.total_pods_in_order}, ${orderMode}</span>
        </div>
        <div class="decision-meta-item">
          <span class="decision-meta-label">Веса</span>
          <span class="decision-meta-value">fit ${formatNumber(decision.weights.node_resources_fit)} / balance ${formatNumber(decision.weights.balanced_allocation)} / image ${formatNumber(decision.weights.image_locality)}</span>
        </div>
      </div>
      <div class="decision-grid">
        ${nodeEvaluations}
      </div>
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
        <header class="decision-card-header">
          <div>
            <div class="decision-node-id">${evaluation.node_id}</div>
            <div class="decision-node-pool">${evaluation.pool_name}</div>
          </div>
          <div class="decision-chip filtered">Отсеяна</div>
        </header>
        <div class="decision-card-text">${evaluation.decision_reason}</div>
        <div class="decision-prestate">
          до размещения: ${formatNumber(evaluation.free_cpu_before)} CPU свободно / ${formatNumber(evaluation.free_memory_before_gib)} GiB свободно / ${evaluation.free_pods_before} pod-слотов
        </div>
        <ul class="decision-reasons">
          ${reasons}
        </ul>
      </article>
    `;
  }

  const breakdown = evaluation.score_breakdown;
  const chosenClass = evaluation.rank === 1 ? " chosen" : "";
  const chosenLabel = evaluation.rank === 1 ? "Выбрана" : `Ранг ${evaluation.rank}`;
  const imageLocality = breakdown.has_same_service_on_node ? "на ноде уже есть такой service/image" : "для service/image нода холодная";

  return `
    <article class="decision-card scored${chosenClass}">
      <header class="decision-card-header">
        <div>
          <div class="decision-node-id">${evaluation.node_id}</div>
          <div class="decision-node-pool">${evaluation.pool_name}</div>
        </div>
        <div class="decision-chip scored">${chosenLabel}</div>
      </header>
      <div class="decision-card-text">${evaluation.decision_reason}</div>
      <div class="decision-score-grid">
        <div class="decision-score-item">
          <span class="decision-score-label">Итог</span>
          <span class="decision-score-value">${formatNumber(breakdown.weighted_total)}</span>
        </div>
        <div class="decision-score-item">
          <span class="decision-score-label">LeastAllocated</span>
          <span class="decision-score-value">${formatNumber(breakdown.node_resources_fit)}</span>
        </div>
        <div class="decision-score-item">
          <span class="decision-score-label">Баланс</span>
          <span class="decision-score-value">${formatNumber(breakdown.balanced_allocation)}</span>
        </div>
        <div class="decision-score-item">
          <span class="decision-score-label">ImageLocality</span>
          <span class="decision-score-value">${formatNumber(breakdown.image_locality)}</span>
        </div>
      </div>
      <div class="decision-prestate">
        до размещения: ${formatNumber(evaluation.free_cpu_before)} CPU свободно / ${formatNumber(evaluation.free_memory_before_gib)} GiB свободно / ${evaluation.free_pods_before} pod-слотов
      </div>
      <div class="decision-poststate">
        после размещения: ${formatNumber(breakdown.free_cpu_after)} CPU свободно / ${formatNumber(breakdown.free_memory_after_gib)} GiB свободно
      </div>
      <div class="decision-poststate">
        загрузка после: ${formatNumber(breakdown.cpu_util_after_pct)}% CPU / ${formatNumber(breakdown.memory_util_after_pct)}% памяти
      </div>
      <div class="decision-poststate">${imageLocality}</div>
    </article>
  `;
}

function renderNotes(notes) {
  notesList.innerHTML = notes.map((note) => `<li>${note}</li>`).join("");
}

function renderNodes(nodes) {
  if (nodes.length === 0) {
    nodesGrid.innerHTML = `
      <article class="cluster-empty">
        <h3>Кластер пока пуст</h3>
        <p>Добавьте хотя бы одну ноду в секции выше, и после этого pod deployment начнёт отображать placement.</p>
      </article>
    `;
    return;
  }

  nodesGrid.innerHTML = nodes
    .map((node, index) => {
      const cpuWidth = Math.min(node.cpu_util_pct, 100);
      const memoryWidth = Math.min(node.memory_util_pct, 100);
      const podWidth = node.total_pods === 0 ? 0 : (node.used_pods / node.total_pods) * 100;
      const podsMarkup = node.pods.length
        ? node.pods
            .map(
              (pod) => `
                <article class="pod-chip ${pod.service_class}">
                  <div class="pod-chip-header">
                    <span class="pod-service">${pod.service_label}</span>
                    <span class="pod-id">${pod.id}</span>
                  </div>
                  <div class="pod-chip-image">${pod.image_label}</div>
                  <div class="pod-chip-meta">
                    <span>${formatNumber(pod.cpu_request)} CPU</span>
                    <span>${formatNumber(pod.memory_request_gib)} GiB</span>
                  </div>
                </article>
              `,
            )
            .join("")
        : `
            <div class="pods-empty">
              На этой ноде пока нет задеплоенных pod'ов.
            </div>
          `;

      return `
        <article
          class="node-card pool-${node.pool_class} state-${node.state}"
          style="animation-delay: ${index * 40}ms"
        >
          <header class="node-card-header">
            <div>
              <h3 class="node-id">${node.id}</h3>
              <div class="node-pool">${node.pool_name}</div>
            </div>
            <div class="status-chip ${node.state}">${node.status_label}</div>
          </header>

          <div class="resource-stack">
            <div class="resource-row">
              <div class="resource-meta">
                <span class="resource-name">CPU</span>
                <span class="resource-value">${formatNumber(node.free_cpu)} free / ${formatNumber(node.total_cpu)} max</span>
              </div>
              <div class="resource-bar">
                <div class="resource-fill" style="width:${cpuWidth}%"></div>
              </div>
            </div>

            <div class="resource-row">
              <div class="resource-meta">
                <span class="resource-name">Memory</span>
                <span class="resource-value">${formatNumber(node.free_memory_gib)} GiB free / ${formatNumber(node.total_memory_gib)} GiB max</span>
              </div>
              <div class="resource-bar">
                <div class="resource-fill memory" style="width:${memoryWidth}%"></div>
              </div>
            </div>

            <div class="resource-row">
              <div class="resource-meta">
                <span class="resource-name">Pod Slots</span>
                <span class="resource-value">${node.free_pods} free / ${node.total_pods} max</span>
              </div>
              <div class="resource-bar">
                <div class="resource-fill pods" style="width:${podWidth}%"></div>
              </div>
            </div>
          </div>

          <section class="pods-section">
            <div class="pods-section-header">
              <span class="pods-title">Pods on node</span>
              <span class="pods-count">${node.used_pods}/${node.total_pods}</span>
            </div>
            <div class="pods-grid">
              ${podsMarkup}
            </div>
          </section>

          <footer class="node-footer">
            <span>used CPU ${formatNumber(node.used_cpu)}</span>
            <span>used pods ${node.used_pods}</span>
          </footer>
        </article>
      `;
    })
    .join("");
}

function installListeners() {
  policySelect.addEventListener("change", () => {
    state.policy = policySelect.value;
    loadSnapshot().catch(renderError);
  });

  podServiceSelect.addEventListener("change", () => {
    const serviceId = Number.parseInt(podServiceSelect.value, 10);
    if (Number.isInteger(serviceId) && serviceId >= 0) {
      state.selectedServiceId = serviceId;
    }
  });

  poolCatalog.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const poolName = target.dataset.poolName;
    const action = target.dataset.action;
    if (!poolName || !action) {
      return;
    }

    const current = state.nodeCounts[poolName] ?? 0;
    if (action === "increment") {
      state.nodeCounts[poolName] = current + 1;
    } else if (action === "decrement") {
      state.nodeCounts[poolName] = Math.max(current - 1, 0);
    }

    loadSnapshot().catch(renderError);
  });

  resetClusterButton.addEventListener("click", () => {
    for (const poolName of Object.keys(state.nodeCounts)) {
      state.nodeCounts[poolName] = 0;
    }
    loadSnapshot().catch(renderError);
  });

  deployForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const serviceId = Number.parseInt(podServiceSelect.value, 10);
    const cpuRequest = Number.parseFloat(podCpuInput.value);
    const memoryRequest = Number.parseFloat(podMemoryInput.value);
    if (!Number.isInteger(serviceId) || serviceId < 0) {
      renderError(new Error("Select a valid service/image"));
      return;
    }
    if (!(cpuRequest > 0) || !(memoryRequest > 0)) {
      renderError(new Error("Service, CPU and Memory requests must be valid"));
      return;
    }

    state.selectedServiceId = serviceId;
    state.pods.push({
      id: nextPodId(),
      service_id: serviceId,
      cpu_request: cpuRequest,
      memory_request_gib: memoryRequest,
    });
    loadSnapshot().catch(renderError);
  });

  clearPodsButton.addEventListener("click", () => {
    state.pods = [];
    recomputeNextPodNumber();
    loadSnapshot().catch(renderError);
  });

  deploymentList.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    if (target.dataset.action !== "remove-pod") {
      return;
    }

    const podId = target.dataset.podId;
    if (!podId) {
      return;
    }

    state.pods = state.pods.filter((pod) => pod.id !== podId);
    recomputeNextPodNumber();
    loadSnapshot().catch(renderError);
  });
}

function renderError(error) {
  summaryGrid.innerHTML = `
    <article class="summary-card">
      <div class="summary-label">Error</div>
      <div class="summary-value">Unavailable</div>
      <div class="summary-subtitle">${error.message}</div>
    </article>
  `;
}

installListeners();
loadSnapshot().catch(renderError);
