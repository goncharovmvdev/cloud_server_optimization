"""Конфигурация Kubernetes-like кластера."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True, kw_only=True)
class PodConfig:
    """Параметры pod-а, по которым считается ёмкость ноды."""

    cpu_request: float
    memory_request_gib: float

    def __post_init__(self) -> None:
        if self.cpu_request <= 0:
            raise ValueError("cpu_request must be positive")
        if self.memory_request_gib <= 0:
            raise ValueError("memory_request_gib must be positive")


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeTemplate:
    """Готовый шаблон ноды для bin-packing / MILP-планировщика."""

    pool_name: str
    cpu_capacity: float
    memory_capacity_gib: float
    max_pods: int
    priority: int
    cost_per_hour: float

    def __post_init__(self) -> None:
        if not self.pool_name:
            raise ValueError("pool_name must be non-empty")
        if self.cpu_capacity <= 0:
            raise ValueError("cpu_capacity must be positive")
        if self.memory_capacity_gib <= 0:
            raise ValueError("memory_capacity_gib must be positive")
        if self.max_pods <= 0:
            raise ValueError("max_pods must be positive")
        if self.cost_per_hour < 0:
            raise ValueError("cost_per_hour must be non-negative")


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerNodeConfig:
    """Параметры физической worker-машины пула."""

    machine_count: int
    cpu_cores: float
    memory_gib: float
    system_reserved_cpu: float
    kube_reserved_cpu: float
    system_reserved_memory_gib: float
    kube_reserved_memory_gib: float
    max_pods_per_node: int
    safe_cpu_util: float
    safe_memory_util: float
    priority: int
    cost_per_hour: float

    def __post_init__(self) -> None:
        if self.machine_count <= 0:
            raise ValueError("machine_count must be positive")
        if self.cpu_cores <= 0:
            raise ValueError("cpu_cores must be positive")
        if self.memory_gib <= 0:
            raise ValueError("memory_gib must be positive")
        if self.system_reserved_cpu < 0 or self.kube_reserved_cpu < 0:
            raise ValueError("reserved CPU values must be non-negative")
        if self.system_reserved_memory_gib < 0 or self.kube_reserved_memory_gib < 0:
            raise ValueError("reserved memory values must be non-negative")
        if self.max_pods_per_node <= 0:
            raise ValueError("max_pods_per_node must be positive")
        if not 0 < self.safe_cpu_util <= 1:
            raise ValueError("safe_cpu_util must be in (0, 1]")
        if not 0 < self.safe_memory_util <= 1:
            raise ValueError("safe_memory_util must be in (0, 1]")
        if self.cost_per_hour < 0:
            raise ValueError("cost_per_hour must be non-negative")
        if self.allocatable_cpu_cores <= 0:
            raise ValueError("reserved CPU leaves no allocatable CPU on the node")
        if self.allocatable_memory_gib <= 0:
            raise ValueError("reserved memory leaves no allocatable memory on the node")

    @property
    def allocatable_cpu_cores(self) -> float:
        return self.cpu_cores - self.system_reserved_cpu - self.kube_reserved_cpu

    @property
    def allocatable_memory_gib(self) -> float:
        return self.memory_gib - self.system_reserved_memory_gib - self.kube_reserved_memory_gib

    @property
    def schedulable_cpu_cores(self) -> float:
        return self.allocatable_cpu_cores * self.safe_cpu_util

    @property
    def schedulable_memory_gib(self) -> float:
        return self.allocatable_memory_gib * self.safe_memory_util

    def max_schedulable_pods(self, pod: PodConfig) -> int:
        cpu_bound = math.floor(self.schedulable_cpu_cores / pod.cpu_request)
        memory_bound = math.floor(self.schedulable_memory_gib / pod.memory_request_gib)
        return min(self.max_pods_per_node, cpu_bound, memory_bound)

    def to_node_template(self, pool_name: str, pod: PodConfig) -> NodeTemplate:
        return NodeTemplate(
            pool_name=pool_name,
            cpu_capacity=self.schedulable_cpu_cores,
            memory_capacity_gib=self.schedulable_memory_gib,
            max_pods=self.max_schedulable_pods(pod),
            priority=self.priority,
            cost_per_hour=self.cost_per_hour,
        )


DEFAULT_POD_CONFIG = PodConfig(
    cpu_request=4.0,
    memory_request_gib=8.0,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ClusterConfig:
    """Конфигурация Kubernetes-like кластера на физических worker-машинах."""

    worker_pools: dict[str, WorkerNodeConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.worker_pools:
            raise ValueError("worker_pools must contain at least one pool")
        # Защитная копия, чтобы внешние мутации не пробивали frozen-инвариант.
        object.__setattr__(self, "worker_pools", dict(self.worker_pools))

    @property
    def max_active_nodes(self) -> int:
        return sum(pool.machine_count for pool in self.worker_pools.values())

    def ordered_pool_items(self) -> list[tuple[str, WorkerNodeConfig]]:
        return sorted(
            self.worker_pools.items(),
            key=lambda item: (
                item[1].priority,
                -item[1].schedulable_cpu_cores,
                -item[1].schedulable_memory_gib,
                item[0],
            ),
        )

    def node_templates(self, pod: PodConfig = DEFAULT_POD_CONFIG) -> list[NodeTemplate]:
        templates: list[NodeTemplate] = []
        for pool_name, pool in self.ordered_pool_items():
            templates.extend([pool.to_node_template(pool_name, pod)] * pool.machine_count)
        return templates


DEFAULT_WORKER_POOLS: dict[str, WorkerNodeConfig] = {
    "compute-large": WorkerNodeConfig(
        machine_count=24,
        cpu_cores=64.0,
        memory_gib=256.0,
        system_reserved_cpu=1.0,
        kube_reserved_cpu=1.0,
        system_reserved_memory_gib=4.0,
        kube_reserved_memory_gib=4.0,
        max_pods_per_node=110,
        safe_cpu_util=0.85,
        safe_memory_util=0.90,
        priority=0,
        cost_per_hour=2.10,
    ),
    "compute-medium": WorkerNodeConfig(
        machine_count=40,
        cpu_cores=32.0,
        memory_gib=128.0,
        system_reserved_cpu=1.0,
        kube_reserved_cpu=1.0,
        system_reserved_memory_gib=4.0,
        kube_reserved_memory_gib=4.0,
        max_pods_per_node=110,
        safe_cpu_util=0.85,
        safe_memory_util=0.90,
        priority=1,
        cost_per_hour=1.00,
    ),
    "memory-heavy": WorkerNodeConfig(
        machine_count=16,
        cpu_cores=48.0,
        memory_gib=384.0,
        system_reserved_cpu=1.0,
        kube_reserved_cpu=1.0,
        system_reserved_memory_gib=4.0,
        kube_reserved_memory_gib=4.0,
        max_pods_per_node=110,
        safe_cpu_util=0.85,
        safe_memory_util=0.90,
        priority=2,
        cost_per_hour=2.60,
    ),
}


__all__ = [
    "PodConfig",
    "NodeTemplate",
    "WorkerNodeConfig",
    "ClusterConfig",
    "DEFAULT_POD_CONFIG",
    "DEFAULT_WORKER_POOLS",
]
