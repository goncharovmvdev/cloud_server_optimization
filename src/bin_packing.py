from copy import deepcopy
from dataclasses import dataclass, field
from typing import List

from .config import NodeTemplate


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class PodPlacement:
    """Pod request scheduled onto a worker node."""

    _service_id: int = field()
    _cpu_request: float = field()
    _memory_request_gib: float = field()

    def __init__(
        self,
        *,
        service_id: int,
        cpu_request: float,
        memory_request_gib: float,
    ) -> None:
        if service_id < 0:
            raise ValueError("service_id must be non-negative")
        if cpu_request <= 0:
            raise ValueError("cpu_request must be positive")
        if memory_request_gib <= 0:
            raise ValueError("memory_request_gib must be positive")

        object.__setattr__(self, "_service_id", service_id)
        object.__setattr__(self, "_cpu_request", cpu_request)
        object.__setattr__(self, "_memory_request_gib", memory_request_gib)

    def get_service_id(self) -> int:
        return self._service_id

    def get_cpu_request(self) -> float:
        return self._cpu_request

    def get_memory_request_gib(self) -> float:
        return self._memory_request_gib


@dataclass(slots=True, kw_only=True, init=False)
class NodePlacement:
    """Active worker node with the pods currently scheduled onto it."""

    _pool_name: str = field()
    _cpu_capacity: float = field()
    _memory_capacity_gib: float = field()
    _max_pods: int = field()
    _pods: List[PodPlacement] = field(default_factory=list)
    _used_cpu: float = field(default=0.0)
    _used_memory_gib: float = field(default=0.0)

    def __init__(
        self,
        *,
        pool_name: str,
        cpu_capacity: float,
        memory_capacity_gib: float,
        max_pods: int,
        pods: List[PodPlacement] | None = None,
        used_cpu: float = 0.0,
        used_memory_gib: float = 0.0,
    ) -> None:
        if not pool_name:
            raise ValueError("pool_name must be non-empty")
        if cpu_capacity <= 0:
            raise ValueError("cpu_capacity must be positive")
        if memory_capacity_gib <= 0:
            raise ValueError("memory_capacity_gib must be positive")
        if max_pods <= 0:
            raise ValueError("max_pods must be positive")
        if used_cpu < 0 or used_memory_gib < 0:
            raise ValueError("used resources must be non-negative")

        object.__setattr__(self, "_pool_name", pool_name)
        object.__setattr__(self, "_cpu_capacity", cpu_capacity)
        object.__setattr__(self, "_memory_capacity_gib", memory_capacity_gib)
        object.__setattr__(self, "_max_pods", max_pods)
        object.__setattr__(self, "_pods", list(pods) if pods is not None else [])
        object.__setattr__(self, "_used_cpu", used_cpu)
        object.__setattr__(self, "_used_memory_gib", used_memory_gib)

    @classmethod
    def from_template(cls, template: NodeTemplate) -> "NodePlacement":
        return cls(
            pool_name=template.get_pool_name(),
            cpu_capacity=template.get_cpu_capacity(),
            memory_capacity_gib=template.get_memory_capacity_gib(),
            max_pods=template.get_max_pods(),
        )

    def get_pool_name(self) -> str:
        return self._pool_name

    def get_cpu_capacity(self) -> float:
        return self._cpu_capacity

    def get_memory_capacity_gib(self) -> float:
        return self._memory_capacity_gib

    def get_max_pods(self) -> int:
        return self._max_pods

    def get_pods(self) -> List[PodPlacement]:
        return list(self._pods)

    def get_used_cpu(self) -> float:
        return self._used_cpu

    def get_used_memory_gib(self) -> float:
        return self._used_memory_gib

    def get_free_cpu(self) -> float:
        return self._cpu_capacity - self._used_cpu

    def get_free_memory_gib(self) -> float:
        return self._memory_capacity_gib - self._used_memory_gib

    def get_free_pod_slots(self) -> int:
        return self._max_pods - len(self._pods)

    def has_pods(self) -> bool:
        return len(self._pods) > 0

    def can_place_pod(self, pod: PodPlacement) -> bool:
        return (
            self.get_free_pod_slots() > 0
            and self.get_free_cpu() >= pod.get_cpu_request()
            and self.get_free_memory_gib() >= pod.get_memory_request_gib()
        )

    def add_pod(self, pod: PodPlacement) -> None:
        if not self.can_place_pod(pod):
            raise ValueError("node has no free resources for pod placement")

        self._pods.append(pod)
        self._used_cpu += pod.get_cpu_request()
        self._used_memory_gib += pod.get_memory_request_gib()

    def remove_pod(self, pod: PodPlacement) -> None:
        self._pods.remove(pod)
        self._used_cpu -= pod.get_cpu_request()
        self._used_memory_gib -= pod.get_memory_request_gib()

    def reset_usage(self) -> None:
        self._used_cpu = 0.0
        self._used_memory_gib = 0.0


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class SchedulingProfile:
    """Strategy-specific weights for Kubernetes-like node scoring."""

    _name: str = field()
    _sort_largest_pods_first: bool = field()
    _node_resources_fit_weight: float = field()
    _balanced_allocation_weight: float = field()
    _image_locality_weight: float = field()

    def __init__(
        self,
        *,
        name: str,
        sort_largest_pods_first: bool,
        node_resources_fit_weight: float,
        balanced_allocation_weight: float,
        image_locality_weight: float,
    ) -> None:
        if not name:
            raise ValueError("name must be non-empty")
        if node_resources_fit_weight < 0:
            raise ValueError("node_resources_fit_weight must be non-negative")
        if balanced_allocation_weight < 0:
            raise ValueError("balanced_allocation_weight must be non-negative")
        if image_locality_weight < 0:
            raise ValueError("image_locality_weight must be non-negative")
        if (
            node_resources_fit_weight
            + balanced_allocation_weight
            + image_locality_weight
            <= 0
        ):
            raise ValueError("at least one scoring weight must be positive")

        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_sort_largest_pods_first", sort_largest_pods_first)
        object.__setattr__(
            self,
            "_node_resources_fit_weight",
            node_resources_fit_weight,
        )
        object.__setattr__(
            self,
            "_balanced_allocation_weight",
            balanced_allocation_weight,
        )
        object.__setattr__(self, "_image_locality_weight", image_locality_weight)

    def get_name(self) -> str:
        return self._name

    def get_sort_largest_pods_first(self) -> bool:
        return self._sort_largest_pods_first

    def get_node_resources_fit_weight(self) -> float:
        return self._node_resources_fit_weight

    def get_balanced_allocation_weight(self) -> float:
        return self._balanced_allocation_weight

    def get_image_locality_weight(self) -> float:
        return self._image_locality_weight


REACTIVE_SCHEDULING_PROFILE = SchedulingProfile(
    name="reactive",
    sort_largest_pods_first=False,
    node_resources_fit_weight=4.0,
    balanced_allocation_weight=1.0,
    image_locality_weight=1.0,
)
FFD_SCHEDULING_PROFILE = SchedulingProfile(
    name="ffd",
    sort_largest_pods_first=True,
    node_resources_fit_weight=2.0,
    balanced_allocation_weight=3.0,
    image_locality_weight=1.0,
)
HYBRID_SCHEDULING_PROFILE = SchedulingProfile(
    name="hybrid",
    sort_largest_pods_first=True,
    node_resources_fit_weight=3.0,
    balanced_allocation_weight=2.0,
    image_locality_weight=2.0,
)


def get_scheduling_profile(strategy_name: str) -> SchedulingProfile:
    if strategy_name == REACTIVE_SCHEDULING_PROFILE.get_name():
        return REACTIVE_SCHEDULING_PROFILE
    if strategy_name == FFD_SCHEDULING_PROFILE.get_name():
        return FFD_SCHEDULING_PROFILE
    return HYBRID_SCHEDULING_PROFILE


class KubernetesLikeNodeScorer:
    """
    Score feasible placement targets using Kubernetes-like resource plugins.

    The score combines:
    - NodeResourcesFit with LeastAllocated
    - NodeResourcesBalancedAllocation
    - ImageLocality
    """

    _MAX_NODE_SCORE = 100.0

    def __init__(
        self,
        pod: PodPlacement,
        profile: SchedulingProfile,
    ) -> None:
        self._pod = pod
        self._profile = profile

    def score_node(self, node: NodePlacement) -> float:
        if not node.can_place_pod(self._pod):
            raise ValueError("node cannot fit pod")
        return self._score_breakdown(
            cpu_capacity=node.get_cpu_capacity(),
            memory_capacity_gib=node.get_memory_capacity_gib(),
            used_cpu=node.get_used_cpu(),
            used_memory_gib=node.get_used_memory_gib(),
            existing_pods=node.get_pods(),
        )["weighted_total_score"]

    def score_template(self, template: NodeTemplate) -> float:
        if (
            template.get_max_pods() <= 0
            or template.get_cpu_capacity() < self._pod.get_cpu_request()
            or template.get_memory_capacity_gib() < self._pod.get_memory_request_gib()
        ):
            raise ValueError("template cannot fit pod")
        return self._score_breakdown(
            cpu_capacity=template.get_cpu_capacity(),
            memory_capacity_gib=template.get_memory_capacity_gib(),
            used_cpu=0.0,
            used_memory_gib=0.0,
            existing_pods=[],
        )["weighted_total_score"]

    def explain_node(self, node: NodePlacement) -> dict[str, float | bool | dict[str, float]]:
        if not node.can_place_pod(self._pod):
            raise ValueError("node cannot fit pod")
        return self._score_breakdown(
            cpu_capacity=node.get_cpu_capacity(),
            memory_capacity_gib=node.get_memory_capacity_gib(),
            used_cpu=node.get_used_cpu(),
            used_memory_gib=node.get_used_memory_gib(),
            existing_pods=node.get_pods(),
        )

    def explain_template(
        self,
        template: NodeTemplate,
    ) -> dict[str, float | bool | dict[str, float]]:
        if (
            template.get_max_pods() <= 0
            or template.get_cpu_capacity() < self._pod.get_cpu_request()
            or template.get_memory_capacity_gib() < self._pod.get_memory_request_gib()
        ):
            raise ValueError("template cannot fit pod")
        return self._score_breakdown(
            cpu_capacity=template.get_cpu_capacity(),
            memory_capacity_gib=template.get_memory_capacity_gib(),
            used_cpu=0.0,
            used_memory_gib=0.0,
            existing_pods=[],
        )

    def _score_breakdown(
        self,
        *,
        cpu_capacity: float,
        memory_capacity_gib: float,
        used_cpu: float,
        used_memory_gib: float,
        existing_pods: List[PodPlacement],
    ) -> dict[str, float | bool | dict[str, float]]:
        least_allocated_score = self._least_allocated_score(
            cpu_capacity=cpu_capacity,
            memory_capacity_gib=memory_capacity_gib,
            used_cpu=used_cpu,
            used_memory_gib=used_memory_gib,
        )
        balanced_allocation_score = self._balanced_allocation_score(
            cpu_capacity=cpu_capacity,
            memory_capacity_gib=memory_capacity_gib,
            used_cpu=used_cpu,
            used_memory_gib=used_memory_gib,
        )
        image_locality_score = self._image_locality_score(existing_pods)

        total_weight = (
            self._profile.get_node_resources_fit_weight()
            + self._profile.get_balanced_allocation_weight()
            + self._profile.get_image_locality_weight()
        )
        weighted_sum = (
            self._profile.get_node_resources_fit_weight() * least_allocated_score
            + self._profile.get_balanced_allocation_weight()
            * balanced_allocation_score
            + self._profile.get_image_locality_weight() * image_locality_score
        )
        return {
            "least_allocated_score": least_allocated_score,
            "balanced_allocation_score": balanced_allocation_score,
            "image_locality_score": image_locality_score,
            "weighted_total_score": weighted_sum / total_weight,
            "free_cpu_after": max(
                cpu_capacity - used_cpu - self._pod.get_cpu_request(),
                0.0,
            ),
            "free_memory_after_gib": max(
                memory_capacity_gib - used_memory_gib - self._pod.get_memory_request_gib(),
                0.0,
            ),
            "cpu_util_after": (
                used_cpu + self._pod.get_cpu_request()
            ) / max(cpu_capacity, 1e-9),
            "memory_util_after": (
                used_memory_gib + self._pod.get_memory_request_gib()
            ) / max(memory_capacity_gib, 1e-9),
            "has_same_service_on_node": any(
                pod.get_service_id() == self._pod.get_service_id()
                for pod in existing_pods
            ),
            "weights": {
                "node_resources_fit": self._profile.get_node_resources_fit_weight(),
                "balanced_allocation": self._profile.get_balanced_allocation_weight(),
                "image_locality": self._profile.get_image_locality_weight(),
            },
        }

    def _least_allocated_score(
        self,
        *,
        cpu_capacity: float,
        memory_capacity_gib: float,
        used_cpu: float,
        used_memory_gib: float,
    ) -> float:
        free_cpu_after = max(
            cpu_capacity - used_cpu - self._pod.get_cpu_request(),
            0.0,
        )
        free_memory_after = max(
            memory_capacity_gib - used_memory_gib - self._pod.get_memory_request_gib(),
            0.0,
        )
        cpu_score = self._MAX_NODE_SCORE * free_cpu_after / max(cpu_capacity, 1e-9)
        memory_score = (
            self._MAX_NODE_SCORE
            * free_memory_after
            / max(memory_capacity_gib, 1e-9)
        )
        return 0.5 * (cpu_score + memory_score)

    def _balanced_allocation_score(
        self,
        *,
        cpu_capacity: float,
        memory_capacity_gib: float,
        used_cpu: float,
        used_memory_gib: float,
    ) -> float:
        cpu_fraction_after = (
            used_cpu + self._pod.get_cpu_request()
        ) / max(cpu_capacity, 1e-9)
        memory_fraction_after = (
            used_memory_gib + self._pod.get_memory_request_gib()
        ) / max(memory_capacity_gib, 1e-9)
        imbalance = min(abs(cpu_fraction_after - memory_fraction_after), 1.0)
        return self._MAX_NODE_SCORE * (1.0 - imbalance)

    def _image_locality_score(self, existing_pods: List[PodPlacement]) -> float:
        if any(
            pod.get_service_id() == self._pod.get_service_id()
            for pod in existing_pods
        ):
            return self._MAX_NODE_SCORE
        return 0.0


class PodFirstFitDecreasingPacker:
    """
    Kubernetes-like pod packer for heterogeneous worker pools.

    The strategy profile controls pod ordering and weighted node scoring.
    """

    def __init__(
        self,
        pods: List[PodPlacement],
        node_templates: List[NodeTemplate],
        scoring_profile: SchedulingProfile,
    ) -> None:
        self._scoring_profile = scoring_profile
        if scoring_profile.get_sort_largest_pods_first():
            self._ordered_pods = sorted(
                pods,
                key=lambda pod: (pod.get_cpu_request(), pod.get_memory_request_gib()),
                reverse=True,
            )
        else:
            self._ordered_pods = list(pods)
        self._opened_nodes: List[NodePlacement] = []
        self._available_templates = list(node_templates)

    def pack(self) -> tuple[List[NodePlacement], List[NodeTemplate]]:
        for pod in self._ordered_pods:
            if self._place_on_opened_node(pod):
                continue

            template_idx = self._find_template_idx_for_pod(pod)
            if template_idx is None:
                continue

            template = self._available_templates.pop(template_idx)
            node = NodePlacement.from_template(template)
            node.add_pod(pod)
            self._opened_nodes.append(node)

        return list(self._opened_nodes), list(self._available_templates)

    def _place_on_opened_node(self, pod: PodPlacement) -> bool:
        feasible_nodes = [node for node in self._opened_nodes if node.can_place_pod(pod)]
        if not feasible_nodes:
            return False

        scorer = KubernetesLikeNodeScorer(pod, self._scoring_profile)
        target_node = max(
            feasible_nodes,
            key=lambda node: (
                scorer.score_node(node),
                -node.get_free_cpu(),
                -node.get_free_memory_gib(),
                node.get_pool_name(),
            ),
        )
        target_node.add_pod(pod)
        return True

    def _find_template_idx_for_pod(self, pod: PodPlacement) -> int | None:
        feasible_templates = [
            (idx, template)
            for idx, template in enumerate(self._available_templates)
            if (
                template.get_max_pods() > 0
                and template.get_cpu_capacity() >= pod.get_cpu_request()
                and template.get_memory_capacity_gib() >= pod.get_memory_request_gib()
            )
        ]
        if not feasible_templates:
            return None

        scorer = KubernetesLikeNodeScorer(pod, self._scoring_profile)
        return max(
            feasible_templates,
            key=lambda item: (
                scorer.score_template(item[1]),
                -item[1].get_priority(),
                item[1].get_cpu_capacity(),
                item[1].get_memory_capacity_gib(),
            ),
        )[0]


class PodRebalancer:
    """
    Lightweight pod rebalance to relieve critically utilized nodes.

    Pods are migrated only from nodes that are close to their schedulable limits
    on CPU, memory, or pod slots.
    """

    def __init__(
        self,
        plan: List[NodePlacement],
        migration_budget: int,
        scoring_profile: SchedulingProfile,
        rebalance_trigger_utilization: float = 0.95,
    ) -> None:
        if not (0.0 < rebalance_trigger_utilization <= 1.0):
            raise ValueError("rebalance_trigger_utilization must be in (0, 1]")
        self._nodes = [deepcopy(node) for node in plan]
        self._migration_budget = migration_budget
        self._migrations = 0
        self._scoring_profile = scoring_profile
        self._rebalance_trigger_utilization = rebalance_trigger_utilization

    def rebalance(self) -> List[NodePlacement]:
        while self._migrations < self._migration_budget:
            hot_node_indices = self._get_hot_node_indices()
            if not hot_node_indices:
                break

            moved_any = False
            for src_idx in hot_node_indices:
                if self._rebalance_from_node(src_idx):
                    moved_any = True
                if self._migrations >= self._migration_budget:
                    break

            if not moved_any:
                break

        return list(self._nodes)

    def _get_hot_node_indices(self) -> List[int]:
        return sorted(
            [
                idx
                for idx, node in enumerate(self._nodes)
                if node.has_pods() and self._is_critically_utilized(node)
            ],
            key=lambda idx: self._get_max_resource_utilization(self._nodes[idx]),
            reverse=True,
        )

    def _get_max_resource_utilization(self, node: NodePlacement) -> float:
        cpu_utilization = (
            node.get_used_cpu() / node.get_cpu_capacity()
            if node.get_cpu_capacity() > 0
            else 0.0
        )
        memory_utilization = (
            node.get_used_memory_gib() / node.get_memory_capacity_gib()
            if node.get_memory_capacity_gib() > 0
            else 0.0
        )
        pod_slot_utilization = (
            len(node.get_pods()) / node.get_max_pods()
            if node.get_max_pods() > 0
            else 0.0
        )
        return max(cpu_utilization, memory_utilization, pod_slot_utilization)

    def _is_critically_utilized(self, node: NodePlacement) -> bool:
        return (
            self._get_max_resource_utilization(node)
            >= self._rebalance_trigger_utilization
        )

    def _rebalance_from_node(self, src_idx: int) -> bool:
        src_node = self._nodes[src_idx]
        src_pods = sorted(
            src_node.get_pods(),
            key=lambda pod: (
                pod.get_cpu_request() / max(src_node.get_cpu_capacity(), 1e-9),
                pod.get_memory_request_gib()
                / max(src_node.get_memory_capacity_gib(), 1e-9),
            ),
            reverse=True,
        )
        moved_any = False

        for pod in src_pods:
            if not self._is_critically_utilized(self._nodes[src_idx]):
                break
            feasible_dst = [
                idx
                for idx in range(len(self._nodes))
                if idx != src_idx and self._nodes[idx].can_place_pod(pod)
            ]
            scorer = KubernetesLikeNodeScorer(pod, self._scoring_profile)
            dst_candidates = sorted(
                feasible_dst,
                key=lambda idx: (
                    scorer.score_node(self._nodes[idx]),
                    -self._nodes[idx].get_free_cpu(),
                    -self._nodes[idx].get_free_memory_gib(),
                    self._nodes[idx].get_pool_name(),
                ),
                reverse=True,
            )

            moved = False
            for dst_idx in dst_candidates:
                self._nodes[dst_idx].add_pod(pod)
                self._nodes[src_idx].remove_pod(pod)
                self._migrations += 1
                moved_any = True
                moved = True
                break

            if not moved:
                continue
            if self._migrations >= self._migration_budget:
                break

        if not self._nodes[src_idx].has_pods():
            self._nodes[src_idx].reset_usage()

        return moved_any


class ActivePlanBuilder:
    """
    Build the final active-node set.

    Non-empty nodes are always kept. Existing empty nodes are reused as warm
    spares first, then more nodes are opened from the remaining inventory.
    """

    def __init__(
        self,
        used_nodes: List[NodePlacement],
        spare_templates: List[NodeTemplate],
        target_nodes: int,
    ) -> None:
        self._active_nodes = [deepcopy(node) for node in used_nodes if node.has_pods()]
        self._empty_nodes = [deepcopy(node) for node in used_nodes if not node.has_pods()]
        self._remaining_templates = list(spare_templates)
        self._target_nodes = target_nodes

    def build(self) -> List[NodePlacement]:
        while len(self._active_nodes) < self._target_nodes and self._empty_nodes:
            self._active_nodes.append(self._empty_nodes.pop(0))

        while len(self._active_nodes) < self._target_nodes and self._remaining_templates:
            self._active_nodes.append(
                NodePlacement.from_template(self._remaining_templates.pop(0))
            )

        return list(self._active_nodes)
