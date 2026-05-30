"""Сервис снапшотов кластера для дашборда bin-packing."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from src.packing import (
    FFD_SCHEDULING_PROFILE,
    KubernetesLikeNodeScorer,
    NodePlacement,
    NodeScoreBreakdown,
    PodPlacement,
)
from src.config import DEFAULT_WORKER_POOLS, WorkerNodeConfig
from src.planning import (
    CheapestClusterPlan,
    plan_cheapest_cluster,
    plan_optimal_cluster_milp,
)


SCHEDULER_NAME = "bin-packing"
SCHEDULING_PROFILE = FFD_SCHEDULING_PROFILE
# Капасити-планнинг работает на полном дефолтном каталоге, но MILP-перебор
# растёт быстро, поэтому даём пользователю до 5 нод каждого пула.
_CAPACITY_PLANNING_MAX_PER_POOL = 5
_MILP_TIME_LIMIT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class ServiceSpec:
    id: int
    service_label: str
    image_label: str
    color_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "service_label": self.service_label,
            "image_label": self.image_label,
            "color_class": self.color_class,
        }


SERVICE_SPECS: tuple[ServiceSpec, ...] = (
    ServiceSpec(0, "checkout-api", "checkout:v1", "service-0"),
    ServiceSpec(1, "catalog-api", "catalog:v2", "service-1"),
    ServiceSpec(2, "payments", "payments:v3", "service-2"),
    ServiceSpec(3, "search", "search:v1", "service-3"),
    ServiceSpec(4, "recommender", "reco:v4", "service-4"),
    ServiceSpec(5, "analytics", "analytics:v2", "service-5"),
)


# Pool-конфиги визуализации берутся из единого источника правды в src/config.
# machine_count переопределяем на 1 — визуализация оперирует per-node.
POOL_SPECS: dict[str, WorkerNodeConfig] = {
    name: dataclasses.replace(cfg, machine_count=1)
    for name, cfg in DEFAULT_WORKER_POOLS.items()
}


@dataclass(slots=True)
class _InventoryNode:
    id: str
    pool_name: str
    pool_class: str
    priority: int
    placement: NodePlacement
    assigned_pods: list[dict[str, Any]]


_DEFAULT_NOTES: tuple[str, ...] = (
    "Кластер стартует пустым: сначала добавьте ноды нужных типов.",
    "Deploy pod создаёт pod request, и шедулер пытается положить его на одну из добавленных нод.",
    "Bin-packing: pod-ы сортируются по убыванию (cpu, memory) — большие идут первыми.",
    "Выбор ноды среди подходящих — взвешенный score из NodeResourcesFit(LeastAllocated) и ImageLocality.",
    "У каждого pod есть раскрывающийся блок с решением шедулера: отсеянные ноды, breakdown score и причина выбора.",
    "Поле Service / Image управляет ImageLocality: одинаковые service/image классы получают бонус на прогретых нодах.",
)


def build_snapshot(
    node_counts: dict[str, int] | None = None,
    pod_requests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    counts = _normalize_node_counts(node_counts)
    pods = _normalize_pod_requests(pod_requests)

    inventory = _build_node_inventory(counts)
    deployment_pods = _schedule_pods(inventory, pods)
    nodes = [_serialize_node(node) for node in inventory]

    return {
        "scheduler": SCHEDULER_NAME,
        "service_catalog": [spec.to_dict() for spec in SERVICE_SPECS],
        "pool_catalog": _build_pool_catalog(counts),
        "deployment_pods": deployment_pods,
        "summary": _build_summary(nodes, deployment_pods),
        "nodes": nodes,
        "capacity_comparison": _build_capacity_comparison(pods),
        "notes": list(_DEFAULT_NOTES),
    }


def _build_capacity_comparison(
    pod_requests: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Считает обе capacity-planning конфигурации для текущих pod requests:
      • bin-packing (plan_cheapest_cluster)
      • MILP        (plan_optimal_cluster_milp)
    и возвращает сравнение для UI. ``None`` — если pod-ов нет.
    """
    if not pod_requests:
        return None

    pods = [
        PodPlacement(
            service_id=pod["service_id"],
            cpu_request=pod["cpu_request"],
            memory_request_gib=pod["memory_request_gib"],
        )
        for pod in pod_requests
    ]
    candidate_pools = {
        name: dataclasses.replace(
            cfg, machine_count=min(cfg.machine_count, _CAPACITY_PLANNING_MAX_PER_POOL)
        )
        for name, cfg in DEFAULT_WORKER_POOLS.items()
    }

    bp_plan = plan_cheapest_cluster(pods, candidate_pools=candidate_pools)
    try:
        milp_plan = plan_optimal_cluster_milp(
            pods,
            candidate_pools=candidate_pools,
            time_limit_seconds=_MILP_TIME_LIMIT_SECONDS,
        )
        milp_error = None
    except Exception as exc:  # pulp/CBC может бросить — UI это отрисует
        milp_plan = None
        milp_error = str(exc)

    savings = None
    if milp_plan is not None and bp_plan.total_cost_per_hour > 0:
        diff = bp_plan.total_cost_per_hour - milp_plan.total_cost_per_hour
        savings = {
            "per_hour": _round(diff),
            "pct": round(100.0 * diff / bp_plan.total_cost_per_hour, 1),
        }

    return {
        "bin_packing": _serialize_plan(bp_plan),
        "milp": _serialize_plan(milp_plan) if milp_plan is not None else None,
        "milp_error": milp_error,
        "savings": savings,
        "max_per_pool": _CAPACITY_PLANNING_MAX_PER_POOL,
    }


def _serialize_plan(plan: CheapestClusterPlan) -> dict[str, Any]:
    return {
        "total_cost_per_hour": _round(plan.total_cost_per_hour),
        "total_cost_per_day": _round(plan.total_cost_per_day),
        "active_nodes_count": plan.active_nodes_count,
        "pool_counts": dict(plan.pool_counts),
        "unplaced_pods": len(plan.unplaced_pods),
        "nodes": [_serialize_planned_node(node, i) for i, node in enumerate(plan.nodes)],
    }


def _serialize_planned_node(node: NodePlacement, index: int) -> dict[str, Any]:
    cpu_used = node.used_cpu
    mem_used = node.used_memory_gib
    return {
        "id": f"{node.pool_name}-{index + 1:02d}",
        "pool_name": node.pool_name,
        "pool_class": _pool_class_name(node.pool_name),
        "cost_per_hour": _round(node.cost_per_hour),
        "cpu_capacity": _round(node.cpu_capacity),
        "memory_capacity_gib": _round(node.memory_capacity_gib),
        "used_cpu": _round(cpu_used),
        "used_memory_gib": _round(mem_used),
        "cpu_util_pct": round(100.0 * cpu_used / max(node.cpu_capacity, 1.0), 1),
        "memory_util_pct": round(100.0 * mem_used / max(node.memory_capacity_gib, 1.0), 1),
        "pods": [
            {
                "service_id": pod.service_id,
                "service_class": _service_spec(pod.service_id).color_class,
                "service_label": _service_spec(pod.service_id).service_label,
                "cpu_request": _round(pod.cpu_request),
                "memory_request_gib": _round(pod.memory_request_gib),
            }
            for pod in node.pods
        ],
    }


def _build_summary(
    nodes: list[dict[str, Any]],
    deployment_pods: list[dict[str, Any]],
) -> dict[str, Any]:
    running = [node for node in nodes if node["state"] == "running"]
    cold = [node for node in nodes if node["state"] == "cold"]
    scheduled_pods = sum(1 for pod in deployment_pods if pod["status"] == "scheduled")
    pending_pods = sum(1 for pod in deployment_pods if pod["status"] == "pending")

    return {
        "inventory_nodes": len(nodes),
        "active_nodes": len(running),
        "running_nodes": len(running),
        "warm_nodes": 0,
        "cold_nodes": len(cold),
        "deployed_pods": scheduled_pods,
        "pending_pods": pending_pods,
        "requested_cpu": _round(sum(pod["cpu_request"] for pod in deployment_pods)),
        "requested_memory_gib": _round(sum(pod["memory_request_gib"] for pod in deployment_pods)),
        "cluster_cpu": _round(sum(node["total_cpu"] for node in nodes)),
        "cluster_memory_gib": _round(sum(node["total_memory_gib"] for node in nodes)),
        "free_active_cpu": _round(sum(node["free_cpu"] for node in nodes)),
        "free_active_memory_gib": _round(sum(node["free_memory_gib"] for node in nodes)),
        "standby_cpu": _round(sum(node["total_cpu"] for node in cold)),
        "standby_memory_gib": _round(sum(node["total_memory_gib"] for node in cold)),
        "running_cost_per_hour": _round(sum(node["cost_per_hour"] for node in running)),
        "cluster_cost_per_hour": _round(sum(node["cost_per_hour"] for node in nodes)),
        "running_cost_per_day": _round(24 * sum(node["cost_per_hour"] for node in running)),
    }


def _normalize_node_counts(node_counts: dict[str, int] | None) -> dict[str, int]:
    if not node_counts:
        return {name: 0 for name in POOL_SPECS}

    normalized: dict[str, int] = {}
    for name in POOL_SPECS:
        try:
            value = int(node_counts.get(name, 0))
        except (TypeError, ValueError):
            value = 0
        normalized[name] = max(value, 0)
    return normalized


def _normalize_pod_requests(
    pod_requests: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not pod_requests:
        return []

    normalized: list[dict[str, Any]] = []
    for index, pod in enumerate(pod_requests):
        if not isinstance(pod, dict):
            continue

        cpu_request = _parse_positive_float(pod.get("cpu_request"))
        memory_request = _parse_positive_float(pod.get("memory_request_gib"))
        if cpu_request is None or memory_request is None:
            continue

        pod_id = str(pod.get("id") or f"pod-{index + 1:02d}")
        service = _service_spec(_parse_non_negative_int(pod.get("service_id"), 0))
        normalized.append(
            {
                "id": pod_id,
                "label": pod_id,
                "color_class": service.color_class,
                "service_id": service.id,
                "service_label": service.service_label,
                "image_label": service.image_label,
                "cpu_request": cpu_request,
                "memory_request_gib": memory_request,
                "status": "pending",
                "status_label": "Pending",
                "node_id": None,
                "node_pool": None,
                "creation_index": index,
            }
        )

    return normalized


def _build_node_inventory(node_counts: dict[str, int]) -> list[_InventoryNode]:
    inventory: list[_InventoryNode] = []

    for name in sorted(POOL_SPECS, key=lambda n: POOL_SPECS[n].priority):
        config = POOL_SPECS[name]
        for index in range(node_counts[name]):
            inventory.append(
                _InventoryNode(
                    id=f"{name}-{index + 1:02d}",
                    pool_name=name,
                    pool_class=_pool_class_name(name),
                    priority=config.priority,
                    placement=NodePlacement(
                        pool_name=name,
                        cpu_capacity=config.schedulable_cpu_cores,
                        memory_capacity_gib=config.schedulable_memory_gib,
                        max_pods=config.max_pods_per_node,
                        cost_per_hour=config.cost_per_hour,
                    ),
                    assigned_pods=[],
                )
            )

    return inventory


def _schedule_pods(
    inventory: list[_InventoryNode],
    pod_requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ordered_pods = sorted(
        pod_requests,
        key=lambda pod: (
            pod["cpu_request"],
            pod["memory_request_gib"],
            -pod["creation_index"],
        ),
        reverse=True,
    )
    total = len(ordered_pods)
    inventory_by_id = {node.id: node for node in inventory}

    for step, pod in enumerate(ordered_pods, start=1):
        placement = PodPlacement(
            service_id=pod["service_id"],
            cpu_request=pod["cpu_request"],
            memory_request_gib=pod["memory_request_gib"],
        )
        decision = _build_scheduler_decision(inventory, placement, step, total)
        pod["scheduler_decision"] = decision

        target = inventory_by_id.get(decision["chosen_node_id"])
        if target is None:
            pod["status"] = "pending"
            pod["status_label"] = "Pending: no node fits"
            continue

        target.placement.add_pod(placement)
        target.assigned_pods.append(_serialize_assigned_pod(pod))
        pod["status"] = "scheduled"
        pod["node_id"] = target.id
        pod["node_pool"] = target.pool_name
        pod["status_label"] = f"Scheduled on {target.id}"

    return sorted(pod_requests, key=lambda pod: pod["creation_index"])


def _serialize_assigned_pod(pod: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": pod["id"],
        "label": pod["label"],
        "service_id": pod["service_id"],
        "service_label": pod["service_label"],
        "image_label": pod["image_label"],
        "cpu_request": _round(pod["cpu_request"]),
        "memory_request_gib": _round(pod["memory_request_gib"]),
        "service_class": pod["color_class"],
    }


def _build_scheduler_decision(
    inventory: list[_InventoryNode],
    pod: PodPlacement,
    schedule_step: int,
    total_pods: int,
) -> dict[str, Any]:
    scorer = KubernetesLikeNodeScorer(pod, SCHEDULING_PROFILE)
    evaluations: list[dict[str, Any]] = []
    feasible: list[dict[str, Any]] = []

    for node in inventory:
        evaluation = _initial_evaluation(node)
        filter_reasons = _filter_reasons(node.placement, pod)
        if filter_reasons:
            evaluation["status"] = "filtered"
            evaluation["filter_reasons"] = filter_reasons
            evaluation["decision_reason"] = "Нода отсеяна жёсткими ресурсными ограничениями."
            evaluations.append(evaluation)
            continue

        breakdown = scorer.explain_node(node.placement)
        evaluation["status"] = "scored"
        evaluation["score_breakdown"] = _serialize_score_breakdown(breakdown)
        evaluation["weights"] = _serialize_weights(breakdown)
        evaluation["_selection_key"] = (
            breakdown.weighted_total_score,
            -breakdown.free_cpu_after,
            -breakdown.free_memory_after_gib,
            -(node.placement.free_pod_slots - 1),
            -node.priority,
            node.id,
        )
        evaluations.append(evaluation)
        feasible.append(evaluation)

    chosen = _select_and_rank(feasible)
    for evaluation in evaluations:
        evaluation.pop("_selection_key", None)

    return {
        "scheduler": SCHEDULER_NAME,
        "schedule_step": schedule_step,
        "total_pods_in_order": total_pods,
        "summary": _decision_summary(evaluations, chosen),
        "chosen_node_id": chosen["node_id"] if chosen else None,
        "chosen_node_pool": chosen["pool_name"] if chosen else None,
        "weights": {
            "node_resources_fit": SCHEDULING_PROFILE.node_resources_fit_weight,
            "image_locality": SCHEDULING_PROFILE.image_locality_weight,
        },
        "node_evaluations": evaluations,
    }


def _initial_evaluation(node: _InventoryNode) -> dict[str, Any]:
    placement = node.placement
    return {
        "node_id": node.id,
        "pool_name": node.pool_name,
        "state": "running" if placement.has_pods else "cold",
        "free_cpu_before": _round(placement.free_cpu),
        "free_memory_before_gib": _round(placement.free_memory_gib),
        "free_pods_before": placement.free_pod_slots,
    }


def _serialize_score_breakdown(breakdown: NodeScoreBreakdown) -> dict[str, Any]:
    return {
        "node_resources_fit": _round(breakdown.least_allocated_score),
        "image_locality": _round(breakdown.image_locality_score),
        "weighted_total": _round(breakdown.weighted_total_score),
        "free_cpu_after": _round(breakdown.free_cpu_after),
        "free_memory_after_gib": _round(breakdown.free_memory_after_gib),
        "cpu_util_after_pct": round(100.0 * breakdown.cpu_util_after, 1),
        "memory_util_after_pct": round(100.0 * breakdown.memory_util_after, 1),
        "has_same_service_on_node": breakdown.has_same_service_on_node,
    }


def _serialize_weights(breakdown: NodeScoreBreakdown) -> dict[str, float]:
    return {
        "node_resources_fit": float(breakdown.weights["node_resources_fit"]),
        "image_locality": float(breakdown.weights["image_locality"]),
    }


def _select_and_rank(
    feasible: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not feasible:
        return None

    ranked = sorted(feasible, key=lambda e: e["_selection_key"], reverse=True)
    chosen = ranked[0]
    chosen_total = chosen["score_breakdown"]["weighted_total"]

    for rank, evaluation in enumerate(ranked, start=1):
        evaluation["rank"] = rank
        if evaluation["node_id"] == chosen["node_id"]:
            evaluation["decision_reason"] = (
                "Выбрана: максимальный итоговый score среди всех допустимых нод."
            )
        elif evaluation["score_breakdown"]["weighted_total"] < chosen_total:
            evaluation["decision_reason"] = (
                "Не выбрана: итоговый score ниже, чем у выбранной ноды."
            )
        else:
            evaluation["decision_reason"] = (
                "Не выбрана: проиграла tie-break "
                "по более плотному размещению после деплоя или по приоритету ноды."
            )
    return chosen


def _decision_summary(
    evaluations: list[dict[str, Any]],
    chosen: dict[str, Any] | None,
) -> str:
    if not evaluations:
        return "Кластер пуст. Сначала добавьте ноды, а потом деплойте этот pod."
    if chosen is None:
        return "Ни одна нода не подошла: все кандидаты были отсеяны ресурсными ограничениями."
    return (
        f"Выбрана нода {chosen['node_id']} с итоговым score "
        f"{chosen['score_breakdown']['weighted_total']:.2f}."
    )


def _filter_reasons(node: NodePlacement, pod: PodPlacement) -> list[str]:
    reasons: list[str] = []
    if node.free_pod_slots <= 0:
        reasons.append("нет свободных pod slots")
    if node.free_cpu < pod.cpu_request:
        reasons.append(
            f"недостаточно CPU: нужно {pod.cpu_request:.2f}, свободно {node.free_cpu:.2f}"
        )
    if node.free_memory_gib < pod.memory_request_gib:
        reasons.append(
            f"недостаточно памяти: нужно {pod.memory_request_gib:.2f} GiB, "
            f"свободно {node.free_memory_gib:.2f} GiB"
        )
    return reasons


def _serialize_node(node: _InventoryNode) -> dict[str, Any]:
    placement = node.placement
    total_cpu = placement.cpu_capacity
    total_memory = placement.memory_capacity_gib
    used_cpu = placement.used_cpu
    used_memory = placement.used_memory_gib
    used_pods = len(node.assigned_pods)
    state = "running" if placement.has_pods else "cold"

    return {
        "id": node.id,
        "pool_name": node.pool_name,
        "pool_class": node.pool_class,
        "state": state,
        "status_label": "Running pods" if state == "running" else "Cold inventory",
        "total_cpu": _round(total_cpu),
        "used_cpu": _round(used_cpu),
        "free_cpu": _round(total_cpu - used_cpu),
        "cpu_util_pct": round(100.0 * used_cpu / max(total_cpu, 1.0), 1),
        "total_memory_gib": _round(total_memory),
        "used_memory_gib": _round(used_memory),
        "free_memory_gib": _round(total_memory - used_memory),
        "memory_util_pct": round(100.0 * used_memory / max(total_memory, 1.0), 1),
        "total_pods": placement.max_pods,
        "used_pods": used_pods,
        "free_pods": placement.max_pods - used_pods,
        "cost_per_hour": _round(placement.cost_per_hour),
        "pods": list(node.assigned_pods),
    }


def _build_pool_catalog(node_counts: dict[str, int]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for name in sorted(POOL_SPECS, key=lambda n: POOL_SPECS[n].priority):
        config = POOL_SPECS[name]
        catalog.append(
            {
                "name": name,
                "display_name": _display_pool_name(name),
                "pool_class": _pool_class_name(name),
                "current_count": node_counts[name],
                "per_node_cpu": _round(config.schedulable_cpu_cores),
                "per_node_memory_gib": _round(config.schedulable_memory_gib),
                "per_node_pods": config.max_pods_per_node,
                "per_node_cost_per_hour": _round(config.cost_per_hour),
            }
        )
    return catalog


def _display_pool_name(pool_name: str) -> str:
    return pool_name.replace("-", " ").title()


def _pool_class_name(pool_name: str) -> str:
    return pool_name.replace("_", "-")


def _service_spec(service_id: int) -> ServiceSpec:
    for spec in SERVICE_SPECS:
        if spec.id == service_id:
            return spec
    return SERVICE_SPECS[service_id % len(SERVICE_SPECS)]


def _round(value: float) -> float:
    return round(float(value), 2)


def _parse_positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _parse_non_negative_int(value: Any, fallback: int) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return fallback


__all__ = [
    "SCHEDULER_NAME",
    "POOL_SPECS",
    "SERVICE_SPECS",
    "build_snapshot",
]
