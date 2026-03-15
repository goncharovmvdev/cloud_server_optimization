from typing import Any

from src.bin_packing import (
    KubernetesLikeNodeScorer,
    NodePlacement,
    PodPlacement,
    get_scheduling_profile,
)
from src.config import WorkerNodeConfig


POLICY_NAMES = ["reactive", "ffd", "hybrid"]
DEFAULT_POLICY_NAME = "hybrid"
SERVICE_SPECS = [
    {
        "id": 0,
        "service_label": "checkout-api",
        "image_label": "checkout:v1",
        "color_class": "service-0",
    },
    {
        "id": 1,
        "service_label": "catalog-api",
        "image_label": "catalog:v2",
        "color_class": "service-1",
    },
    {
        "id": 2,
        "service_label": "payments",
        "image_label": "payments:v3",
        "color_class": "service-2",
    },
    {
        "id": 3,
        "service_label": "search",
        "image_label": "search:v1",
        "color_class": "service-3",
    },
    {
        "id": 4,
        "service_label": "recommender",
        "image_label": "reco:v4",
        "color_class": "service-4",
    },
    {
        "id": 5,
        "service_label": "analytics",
        "image_label": "analytics:v2",
        "color_class": "service-5",
    },
]
POOL_SPECS = {
    "compute-large": {
        "cpu_cores": 32.0,
        "memory_gib": 128.0,
        "system_reserved_cpu": 1.0,
        "kube_reserved_cpu": 1.0,
        "system_reserved_memory_gib": 4.0,
        "kube_reserved_memory_gib": 4.0,
        "max_pods_per_node": 40,
        "safe_cpu_util": 0.85,
        "safe_memory_util": 0.90,
        "priority": 0,
    },
    "compute-medium": {
        "cpu_cores": 16.0,
        "memory_gib": 64.0,
        "system_reserved_cpu": 1.0,
        "kube_reserved_cpu": 1.0,
        "system_reserved_memory_gib": 2.0,
        "kube_reserved_memory_gib": 2.0,
        "max_pods_per_node": 30,
        "safe_cpu_util": 0.85,
        "safe_memory_util": 0.90,
        "priority": 1,
    },
    "memory-heavy": {
        "cpu_cores": 24.0,
        "memory_gib": 192.0,
        "system_reserved_cpu": 1.0,
        "kube_reserved_cpu": 1.0,
        "system_reserved_memory_gib": 4.0,
        "kube_reserved_memory_gib": 4.0,
        "max_pods_per_node": 30,
        "safe_cpu_util": 0.85,
        "safe_memory_util": 0.90,
        "priority": 2,
    },
}


def get_policy_names() -> list[str]:
    return list(POLICY_NAMES)


def build_snapshot(
    policy_name: str = DEFAULT_POLICY_NAME,
    node_counts: dict[str, int] | None = None,
    pod_requests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_policy = (
        policy_name if policy_name in POLICY_NAMES else DEFAULT_POLICY_NAME
    )
    normalized_counts = _normalize_node_counts(node_counts)
    normalized_pods = _normalize_pod_requests(pod_requests)

    node_inventory = _build_node_inventory(normalized_counts)
    deployment_pods = _schedule_pods(normalized_policy, node_inventory, normalized_pods)
    nodes = _serialize_cluster_nodes(node_inventory)
    summary = _build_summary(nodes, deployment_pods)

    return {
        "policy": normalized_policy,
        "policies": get_policy_names(),
        "service_catalog": _build_service_catalog(),
        "pool_catalog": _build_pool_catalog(normalized_counts),
        "deployment_pods": deployment_pods,
        "summary": summary,
        "nodes": nodes,
        "notes": [
            "Кластер стартует пустым: сначала добавьте ноды нужных типов.",
            "Deploy pod создаёт pod request и scheduler пытается положить его на одну из добавленных нод.",
            "Все стратегии выбирают ноду по взвешенному score из NodeResourcesFit(LeastAllocated), NodeResourcesBalancedAllocation и ImageLocality.",
            "У каждого pod в очереди есть раскрывающийся блок с решением шедулера: там видно отсеянные ноды, breakdown score и причину выбора.",
            "Reactive сохраняет порядок прихода pod'ов, а FFD и Hybrid сначала сортируют более тяжёлые pod'ы.",
            "Поле Service / Image позволяет управлять ImageLocality: одинаковые service/image классы получают бонус на уже прогретых нодах.",
            "Стратегии отличаются именно весами score-компонент, а не только порядком обхода нод.",
        ],
    }


def _build_summary(
    nodes: list[dict[str, Any]],
    deployment_pods: list[dict[str, Any]],
) -> dict[str, Any]:
    inventory_nodes = len(nodes)
    running_nodes = sum(1 for node in nodes if node["state"] == "running")
    cold_nodes = sum(1 for node in nodes if node["state"] == "cold")
    scheduled_pods = sum(1 for pod in deployment_pods if pod["status"] == "scheduled")
    pending_pods = sum(1 for pod in deployment_pods if pod["status"] == "pending")
    requested_cpu = sum(pod["cpu_request"] for pod in deployment_pods)
    requested_memory = sum(pod["memory_request_gib"] for pod in deployment_pods)
    cluster_cpu = sum(node["total_cpu"] for node in nodes)
    cluster_memory = sum(node["total_memory_gib"] for node in nodes)
    free_cpu = sum(node["free_cpu"] for node in nodes)
    free_memory = sum(node["free_memory_gib"] for node in nodes)

    return {
        "inventory_nodes": inventory_nodes,
        "active_nodes": running_nodes,
        "running_nodes": running_nodes,
        "warm_nodes": 0,
        "cold_nodes": cold_nodes,
        "deployed_pods": scheduled_pods,
        "pending_pods": pending_pods,
        "requested_cpu": round(float(requested_cpu), 2),
        "requested_memory_gib": round(float(requested_memory), 2),
        "cluster_cpu": round(float(cluster_cpu), 2),
        "cluster_memory_gib": round(float(cluster_memory), 2),
        "free_active_cpu": round(float(free_cpu), 2),
        "free_active_memory_gib": round(float(free_memory), 2),
        "standby_cpu": round(float(sum(node["total_cpu"] for node in nodes if node["state"] == "cold")), 2),
        "standby_memory_gib": round(
            float(sum(node["total_memory_gib"] for node in nodes if node["state"] == "cold")),
            2,
        ),
    }


def _normalize_node_counts(
    node_counts: dict[str, int] | None,
) -> dict[str, int]:
    normalized = {pool_name: 0 for pool_name in POOL_SPECS}
    if node_counts is None:
        return normalized

    for pool_name in POOL_SPECS:
        try:
            raw_value = int(node_counts.get(pool_name, 0))
        except (TypeError, ValueError):
            raw_value = 0
        normalized[pool_name] = max(raw_value, 0)

    return normalized


def _normalize_pod_requests(
    pod_requests: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if pod_requests is None:
        return normalized

    for index, pod in enumerate(pod_requests):
        if not isinstance(pod, dict):
            continue

        cpu_request = _parse_positive_float(pod.get("cpu_request"))
        memory_request = _parse_positive_float(pod.get("memory_request_gib"))
        if cpu_request is None or memory_request is None:
            continue

        pod_id = str(pod.get("id") or f"pod-{index + 1:02d}")
        service_spec = _get_service_spec(
            _parse_non_negative_int(pod.get("service_id"), 0),
        )
        normalized.append(
            {
                "id": pod_id,
                "label": pod_id,
                "color_class": service_spec["color_class"],
                "service_id": service_spec["id"],
                "service_label": service_spec["service_label"],
                "image_label": service_spec["image_label"],
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


def _build_node_inventory(
    node_counts: dict[str, int],
) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []

    for pool_name in sorted(POOL_SPECS, key=lambda name: POOL_SPECS[name]["priority"]):
        config = _build_worker_node_config(pool_name, 1)
        for index in range(node_counts[pool_name]):
            inventory.append(
                {
                    "id": f"{pool_name}-{index + 1:02d}",
                    "pool_name": pool_name,
                    "pool_class": _pool_class_name(pool_name),
                    "priority": POOL_SPECS[pool_name]["priority"],
                    "placement": NodePlacement(
                        pool_name=pool_name,
                        cpu_capacity=config.get_schedulable_cpu_cores(),
                        memory_capacity_gib=config.get_schedulable_memory_gib(),
                        max_pods=config.get_max_pods_per_node(),
                    ),
                    "assigned_pods": [],
                }
            )

    return inventory


def _schedule_pods(
    policy_name: str,
    node_inventory: list[dict[str, Any]],
    pod_requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ordered_pods = _ordered_pods_for_policy(policy_name, pod_requests)

    for schedule_step, pod in enumerate(ordered_pods, start=1):
        pod_placement = PodPlacement(
            service_id=pod["service_id"],
            cpu_request=pod["cpu_request"],
            memory_request_gib=pod["memory_request_gib"],
        )
        scheduler_decision = _build_scheduler_decision(
            policy_name,
            node_inventory,
            pod_placement,
            schedule_step,
            len(ordered_pods),
        )
        target_node = _find_node_by_id(
            node_inventory,
            scheduler_decision["chosen_node_id"],
        )
        pod["scheduler_decision"] = scheduler_decision
        if target_node is None:
            pod["status"] = "pending"
            pod["status_label"] = "Pending: no node fits"
            continue

        target_node["placement"].add_pod(pod_placement)
        target_node["assigned_pods"].append(
            {
                "id": pod["id"],
                "label": pod["label"],
                "service_id": pod["service_id"],
                "service_label": pod["service_label"],
                "image_label": pod["image_label"],
                "cpu_request": round(float(pod["cpu_request"]), 2),
                "memory_request_gib": round(float(pod["memory_request_gib"]), 2),
                "service_class": pod["color_class"],
            }
        )
        pod["status"] = "scheduled"
        pod["node_id"] = target_node["id"]
        pod["node_pool"] = target_node["pool_name"]
        pod["status_label"] = f"Scheduled on {target_node['id']}"

    return sorted(
        pod_requests,
        key=lambda pod: pod["creation_index"],
    )


def _ordered_pods_for_policy(
    policy_name: str,
    pod_requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not get_scheduling_profile(policy_name).get_sort_largest_pods_first():
        return list(pod_requests)

    return sorted(
        pod_requests,
        key=lambda pod: (
            pod["cpu_request"],
            pod["memory_request_gib"],
            -pod["creation_index"],
        ),
        reverse=True,
    )


def _build_scheduler_decision(
    policy_name: str,
    node_inventory: list[dict[str, Any]],
    pod: PodPlacement,
    schedule_step: int,
    total_pods: int,
) -> dict[str, Any]:
    profile = get_scheduling_profile(policy_name)
    scorer = KubernetesLikeNodeScorer(pod, profile)
    node_evaluations: list[dict[str, Any]] = []
    feasible_evaluations: list[dict[str, Any]] = []

    for node in node_inventory:
        placement = node["placement"]
        evaluation = {
            "node_id": node["id"],
            "pool_name": node["pool_name"],
            "state": "running" if placement.has_pods() else "cold",
            "free_cpu_before": round(float(placement.get_free_cpu()), 2),
            "free_memory_before_gib": round(float(placement.get_free_memory_gib()), 2),
            "free_pods_before": placement.get_free_pod_slots(),
        }
        filter_reasons = _build_filter_reasons(placement, pod)
        if filter_reasons:
            evaluation["status"] = "filtered"
            evaluation["filter_reasons"] = filter_reasons
            evaluation["decision_reason"] = "Нода отсеяна жёсткими ресурсными ограничениями."
            node_evaluations.append(evaluation)
            continue

        score_breakdown = scorer.explain_node(placement)
        selection_key = (
            score_breakdown["weighted_total_score"],
            -score_breakdown["free_cpu_after"],
            -score_breakdown["free_memory_after_gib"],
            -(placement.get_free_pod_slots() - 1),
            -node["priority"],
            node["id"],
        )
        evaluation["status"] = "scored"
        evaluation["score_breakdown"] = {
            "node_resources_fit": round(float(score_breakdown["least_allocated_score"]), 2),
            "balanced_allocation": round(
                float(score_breakdown["balanced_allocation_score"]),
                2,
            ),
            "image_locality": round(float(score_breakdown["image_locality_score"]), 2),
            "weighted_total": round(float(score_breakdown["weighted_total_score"]), 2),
            "free_cpu_after": round(float(score_breakdown["free_cpu_after"]), 2),
            "free_memory_after_gib": round(
                float(score_breakdown["free_memory_after_gib"]),
                2,
            ),
            "cpu_util_after_pct": round(
                100.0 * float(score_breakdown["cpu_util_after"]),
                1,
            ),
            "memory_util_after_pct": round(
                100.0 * float(score_breakdown["memory_util_after"]),
                1,
            ),
            "has_same_service_on_node": bool(
                score_breakdown["has_same_service_on_node"],
            ),
        }
        evaluation["weights"] = {
            "node_resources_fit": float(score_breakdown["weights"]["node_resources_fit"]),
            "balanced_allocation": float(score_breakdown["weights"]["balanced_allocation"]),
            "image_locality": float(score_breakdown["weights"]["image_locality"]),
        }
        evaluation["_selection_key"] = selection_key
        node_evaluations.append(evaluation)
        feasible_evaluations.append(evaluation)

    chosen_evaluation = None
    if feasible_evaluations:
        chosen_evaluation = max(
            feasible_evaluations,
            key=lambda evaluation: evaluation["_selection_key"],
        )
        ranked_feasible = sorted(
            feasible_evaluations,
            key=lambda evaluation: evaluation["_selection_key"],
            reverse=True,
        )
        for rank, evaluation in enumerate(ranked_feasible, start=1):
            evaluation["rank"] = rank
            if evaluation["node_id"] == chosen_evaluation["node_id"]:
                evaluation["decision_reason"] = (
                    "Выбрана: максимальный итоговый score среди всех допустимых нод."
                )
                continue
            if (
                evaluation["score_breakdown"]["weighted_total"]
                < chosen_evaluation["score_breakdown"]["weighted_total"]
            ):
                evaluation["decision_reason"] = (
                    "Не выбрана: итоговый score ниже, чем у выбранной ноды."
                )
            else:
                evaluation["decision_reason"] = (
                    "Не выбрана: проиграла дополнительное сравнение по более плотному размещению после деплоя или по приоритету ноды."
                )

    for evaluation in node_evaluations:
        evaluation.pop("_selection_key", None)

    if not node_evaluations:
        summary = "Кластер пуст. Сначала добавьте ноды, а потом деплойте этот pod."
    elif chosen_evaluation is None:
        summary = "Ни одна нода не подошла: все кандидаты были отсеяны ресурсными ограничениями."
    else:
        summary = (
            f"Выбрана нода {chosen_evaluation['node_id']} с итоговым score "
            f"{chosen_evaluation['score_breakdown']['weighted_total']:.2f}."
        )

    return {
        "policy": policy_name,
        "schedule_step": schedule_step,
        "total_pods_in_order": total_pods,
        "sort_largest_pods_first": profile.get_sort_largest_pods_first(),
        "summary": summary,
        "chosen_node_id": None if chosen_evaluation is None else chosen_evaluation["node_id"],
        "chosen_node_pool": None if chosen_evaluation is None else chosen_evaluation["pool_name"],
        "weights": {
            "node_resources_fit": profile.get_node_resources_fit_weight(),
            "balanced_allocation": profile.get_balanced_allocation_weight(),
            "image_locality": profile.get_image_locality_weight(),
        },
        "node_evaluations": node_evaluations,
    }


def _find_node_by_id(
    node_inventory: list[dict[str, Any]],
    node_id: str | None,
) -> dict[str, Any] | None:
    if node_id is None:
        return None
    for node in node_inventory:
        if node["id"] == node_id:
            return node
    return None


def _build_filter_reasons(
    node: NodePlacement,
    pod: PodPlacement,
) -> list[str]:
    reasons: list[str] = []
    if node.get_free_pod_slots() <= 0:
        reasons.append("нет свободных pod slots")
    if node.get_free_cpu() < pod.get_cpu_request():
        reasons.append(
            "недостаточно CPU: "
            f"нужно {pod.get_cpu_request():.2f}, свободно {node.get_free_cpu():.2f}"
        )
    if node.get_free_memory_gib() < pod.get_memory_request_gib():
        reasons.append(
            "недостаточно памяти: "
            f"нужно {pod.get_memory_request_gib():.2f} GiB, "
            f"свободно {node.get_free_memory_gib():.2f} GiB"
        )
    return reasons


def _serialize_cluster_nodes(
    node_inventory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    for node in node_inventory:
        placement = node["placement"]
        total_cpu = float(placement.get_cpu_capacity())
        total_memory = float(placement.get_memory_capacity_gib())
        used_cpu = float(placement.get_used_cpu())
        used_memory = float(placement.get_used_memory_gib())
        total_pods = placement.get_max_pods()
        used_pods = len(node["assigned_pods"])
        state = "running" if placement.has_pods() else "cold"

        nodes.append(
            {
                "id": node["id"],
                "pool_name": node["pool_name"],
                "pool_class": node["pool_class"],
                "state": state,
                "status_label": "Running pods" if state == "running" else "Cold inventory",
                "total_cpu": round(total_cpu, 2),
                "used_cpu": round(used_cpu, 2),
                "free_cpu": round(total_cpu - used_cpu, 2),
                "cpu_util_pct": round(100.0 * used_cpu / max(total_cpu, 1.0), 1),
                "total_memory_gib": round(total_memory, 2),
                "used_memory_gib": round(used_memory, 2),
                "free_memory_gib": round(total_memory - used_memory, 2),
                "memory_util_pct": round(100.0 * used_memory / max(total_memory, 1.0), 1),
                "total_pods": total_pods,
                "used_pods": used_pods,
                "free_pods": total_pods - used_pods,
                "pods": list(node["assigned_pods"]),
            }
        )

    return nodes


def _build_pool_catalog(
    node_counts: dict[str, int],
) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []

    for pool_name in sorted(POOL_SPECS, key=lambda name: POOL_SPECS[name]["priority"]):
        config = _build_worker_node_config(pool_name, 1)
        catalog.append(
            {
                "name": pool_name,
                "display_name": _display_pool_name(pool_name),
                "pool_class": _pool_class_name(pool_name),
                "current_count": node_counts[pool_name],
                "per_node_cpu": round(float(config.get_schedulable_cpu_cores()), 2),
                "per_node_memory_gib": round(float(config.get_schedulable_memory_gib()), 2),
                "per_node_pods": config.get_max_pods_per_node(),
            }
        )

    return catalog


def _build_service_catalog() -> list[dict[str, Any]]:
    return [dict(spec) for spec in SERVICE_SPECS]


def _build_worker_node_config(
    pool_name: str,
    machine_count: int,
) -> WorkerNodeConfig:
    spec = POOL_SPECS[pool_name]
    return WorkerNodeConfig(
        machine_count=machine_count,
        cpu_cores=spec["cpu_cores"],
        memory_gib=spec["memory_gib"],
        system_reserved_cpu=spec["system_reserved_cpu"],
        kube_reserved_cpu=spec["kube_reserved_cpu"],
        system_reserved_memory_gib=spec["system_reserved_memory_gib"],
        kube_reserved_memory_gib=spec["kube_reserved_memory_gib"],
        max_pods_per_node=spec["max_pods_per_node"],
        safe_cpu_util=spec["safe_cpu_util"],
        safe_memory_util=spec["safe_memory_util"],
        priority=spec["priority"],
    )


def _display_pool_name(pool_name: str) -> str:
    return pool_name.replace("-", " ").title()


def _pool_class_name(pool_name: str) -> str:
    return pool_name.replace("_", "-")


def _get_service_spec(service_id: int) -> dict[str, Any]:
    for spec in SERVICE_SPECS:
        if spec["id"] == service_id:
            return spec
    return SERVICE_SPECS[service_id % len(SERVICE_SPECS)]


def _parse_positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None
    return parsed


def _parse_non_negative_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(parsed, 0)
