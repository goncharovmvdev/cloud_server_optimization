from abc import ABC, abstractmethod
from copy import deepcopy
import math
from typing import List, Tuple

import numpy as np

from .bin_packing import (
    ActivePlanBuilder,
    KubernetesLikeNodeScorer,
    NodePlacement,
    PodPlacement,
    PodFirstFitDecreasingPacker,
    PodRebalancer,
    SchedulingProfile,
    get_scheduling_profile,
)
from .config import ClusterConfig
from .forecasting import EwmaForecaster, Forecaster


NodePlan = List[NodePlacement]
NodeInventoryKey = Tuple[str, float, float, int]


class ServiceDemandPlanner:
    """
    Build per-service demand shares and convert aggregate demand into pod requests.
    """

    def __init__(self, n_services: int, rng: np.random.Generator) -> None:
        if n_services <= 0:
            raise ValueError("n_services must be positive")
        self._rng = rng
        self._service_weights = rng.dirichlet(np.ones(n_services))

    def build_pods(self, total_demand: float) -> List[PodPlacement]:
        pods: List[PodPlacement] = []
        for service_id, service_demand in enumerate(self._service_demands(total_demand)):
            replicas = self._replicas_for_service(float(service_demand))
            for _ in range(replicas):
                cpu_request = self._rng.uniform(2.0, 8.0)
                memory_request_gib = self._rng.uniform(4.0, 16.0)
                pods.append(
                    PodPlacement(
                        service_id=service_id,
                        cpu_request=cpu_request,
                        memory_request_gib=memory_request_gib,
                    )
                )
        return pods

    def estimate_replicas(self, total_demand: float) -> int:
        return sum(
            self._replicas_for_service(float(service_demand))
            for service_demand in self._service_demands(total_demand)
        )

    def _service_demands(self, total_demand: float) -> np.ndarray:
        return self._service_weights * max(total_demand, 0.0)

    def _replicas_for_service(self, service_demand: float) -> int:
        target_cpu_load = 0.75
        desired = math.ceil(max(service_demand, 0.0) / target_cpu_load)
        min_replicas = 1
        max_replicas = 64
        desired = max(desired, min_replicas)
        return min(desired, max_replicas)


class ExistingPlanPacker:
    """
    Pack pod requests into cluster inventory while optionally reusing an existing plan.
    """

    def __init__(
        self,
        cfg: ClusterConfig,
        scoring_profile: SchedulingProfile,
        existing_active_plan: List[NodePlacement] | None = None,
    ) -> None:
        self._cfg = cfg
        self._scoring_profile = scoring_profile
        self._existing_active_plan = (
            [deepcopy(node) for node in existing_active_plan]
            if existing_active_plan is not None
            else None
        )

    def pack(self, pods: List[PodPlacement]) -> tuple[NodePlan, list]:
        if self._existing_active_plan is None:
            return self._pack_fresh(pods)

        existing_nodes = list(self._existing_active_plan)
        available_templates = self._subtract_active_nodes_from_inventory(
            self._cfg.get_node_templates(),
            existing_nodes,
        )
        remaining_pods = list(pods)

        for pod in remaining_pods[:]:
            feasible_nodes = [node for node in existing_nodes if node.can_place_pod(pod)]
            if not feasible_nodes:
                continue

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
            remaining_pods.remove(pod)

        if remaining_pods:
            new_used, spare_templates = PodFirstFitDecreasingPacker(
                remaining_pods,
                available_templates,
                self._scoring_profile,
            ).pack()
            existing_nodes.extend(new_used)
            return existing_nodes, spare_templates

        return existing_nodes, available_templates

    def _pack_fresh(self, pods: List[PodPlacement]) -> tuple[NodePlan, list]:
        return PodFirstFitDecreasingPacker(
            pods,
            self._cfg.get_node_templates(),
            self._scoring_profile,
        ).pack()

    def _node_inventory_key_from_node(self, node: NodePlacement) -> NodeInventoryKey:
        return (
            node.get_pool_name(),
            node.get_cpu_capacity(),
            node.get_memory_capacity_gib(),
            node.get_max_pods(),
        )

    def _node_inventory_key_from_template(self, template) -> NodeInventoryKey:
        return (
            template.get_pool_name(),
            template.get_cpu_capacity(),
            template.get_memory_capacity_gib(),
            template.get_max_pods(),
        )

    def _subtract_active_nodes_from_inventory(
        self,
        node_templates,
        active_nodes: List[NodePlacement],
    ):
        remaining_templates = list(node_templates)

        for active_node in active_nodes:
            active_key = self._node_inventory_key_from_node(active_node)
            matched_template_idx = None
            for idx, template in enumerate(remaining_templates):
                if self._node_inventory_key_from_template(template) == active_key:
                    matched_template_idx = idx
                    break

            if matched_template_idx is None:
                raise ValueError(
                    "active node inventory exceeds configured cluster capacity"
                )

            remaining_templates.pop(matched_template_idx)

        return remaining_templates


class Policy(ABC):
    """
    Abstract base class for cluster management policies.
    Each policy computes demand prediction and active worker nodes.
    """

    @abstractmethod
    def __call__(
        self,
        demand: float,
        hist: np.ndarray,
        n_services: int,
        cfg: ClusterConfig,
        existing_active_plan: List[NodePlacement] | None = None,
    ) -> Tuple[float, NodePlan, int]:
        """
        Compute predicted demand, active node plan, and number of active nodes.
        existing_active_plan: already occupied nodes to account for existing load.
        """
        raise NotImplementedError


class ScoreBasedPolicy(Policy):
    """
    Base class for policies driven by a fixed scheduling profile and RNG seed.
    """

    def __init__(self, policy_name: str, rng_seed: int = 42) -> None:
        self._rng_seed = rng_seed
        self._scoring_profile = get_scheduling_profile(policy_name)

    def _build_demand_planner(self, n_services: int) -> ServiceDemandPlanner:
        return ServiceDemandPlanner(
            n_services,
            np.random.default_rng(self._rng_seed),
        )

    def _pack_pods(
        self,
        pods: List[PodPlacement],
        cfg: ClusterConfig,
        existing_active_plan: List[NodePlacement] | None = None,
    ) -> tuple[NodePlan, list]:
        return ExistingPlanPacker(
            cfg,
            self._scoring_profile,
            existing_active_plan,
        ).pack(pods)

    def _get_scoring_profile(self) -> SchedulingProfile:
        return self._scoring_profile


class ReactivePolicy(ScoreBasedPolicy):
    """
    Reactive policy: sizes the cluster from current demand without forecasting.
    """

    def __init__(self, rng_seed: int = 42) -> None:
        super().__init__("reactive", rng_seed)

    def __call__(
        self,
        demand: float,
        hist: np.ndarray,
        n_services: int,
        cfg: ClusterConfig,
        existing_active_plan: List[NodePlacement] | None = None,
    ) -> Tuple[float, NodePlan, int]:
        demand_planner = self._build_demand_planner(n_services)

        predicted = demand
        pods = demand_planner.build_pods(demand)
        used_nodes, spare_templates = self._pack_pods(
            pods,
            cfg,
            existing_active_plan,
        )
        target_nodes = min(
            cfg.get_max_active_nodes(),
            max(len([node for node in used_nodes if node.has_pods()]) + 2, 1),
        )
        active_plan = ActivePlanBuilder(
            used_nodes,
            spare_templates,
            target_nodes,
        ).build()
        active_nodes = len(active_plan)

        return predicted, active_plan, active_nodes


class FfdPolicy(ScoreBasedPolicy):
    """
    FFD policy: packs pod replicas tightly onto heterogeneous worker pools.
    """

    def __init__(self, rng_seed: int = 42) -> None:
        super().__init__("ffd", rng_seed)

    def __call__(
        self,
        demand: float,
        hist: np.ndarray,
        n_services: int,
        cfg: ClusterConfig,
        existing_active_plan: List[NodePlacement] | None = None,
    ) -> Tuple[float, NodePlan, int]:
        demand_planner = self._build_demand_planner(n_services)

        predicted = demand
        pods = demand_planner.build_pods(demand)
        used_nodes, spare_templates = self._pack_pods(
            pods,
            cfg,
            existing_active_plan,
        )
        target_nodes = min(
            cfg.get_max_active_nodes(),
            max(len([node for node in used_nodes if node.has_pods()]), 1),
        )
        active_plan = ActivePlanBuilder(
            used_nodes,
            spare_templates,
            target_nodes,
        ).build()
        active_nodes = len(active_plan)

        return predicted, active_plan, active_nodes


class HybridPolicy(ScoreBasedPolicy):
    """
    Hybrid policy: uses demand forecasting plus pod-aware packing across node pools.
    """

    def __init__(
        self,
        forecaster: Forecaster | None = None,
        rng_seed: int = 42,
    ):
        super().__init__("hybrid", rng_seed)
        self._forecaster = forecaster or EwmaForecaster()

    def __call__(
        self,
        demand: float,
        hist: np.ndarray,
        n_services: int,
        cfg: ClusterConfig,
        existing_active_plan: List[NodePlacement] | None = None,
    ) -> Tuple[float, NodePlan, int]:
        demand_planner = self._build_demand_planner(n_services)

        used_nodes, spare_templates = self._pack_pods(
            demand_planner.build_pods(demand),
            cfg,
            existing_active_plan,
        )
        rebalanced_nodes = PodRebalancer(
            used_nodes,
            cfg.get_migration_budget(),
            self._get_scoring_profile(),
            cfg.get_rebalance_trigger_utilization(),
        ).rebalance()

        predicted = self._forecaster.forecast(hist)
        boosted = max(predicted, demand) * (1.0 + cfg.get_headroom())
        predicted_replicas = demand_planner.estimate_replicas(boosted)
        target_nodes = cfg.required_nodes_for_replicas(predicted_replicas)

        active_plan = ActivePlanBuilder(
            rebalanced_nodes,
            spare_templates,
            target_nodes,
        ).build()
        active_nodes = len(active_plan)

        return predicted, active_plan, active_nodes
