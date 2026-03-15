from dataclasses import dataclass, field
import math


@dataclass(frozen=True, kw_only=True, init=False)
class PodConfig:
    _cpu_request: float = field()
    _cpu_limit: float = field()
    _memory_request_gib: float = field()
    _memory_limit_gib: float = field()
    _target_cpu_utilization: float = field()
    _min_replicas_per_service: int = field()
    _max_replicas_per_service: int = field()

    def __init__(
        self,
        *,
        cpu_request: float,
        cpu_limit: float,
        memory_request_gib: float,
        memory_limit_gib: float,
        target_cpu_utilization: float,
        min_replicas_per_service: int,
        max_replicas_per_service: int,
    ) -> None:
        if cpu_request <= 0:
            raise ValueError("cpu_request must be positive")
        if cpu_limit < cpu_request:
            raise ValueError("cpu_limit must be greater than or equal to cpu_request")
        if memory_request_gib <= 0:
            raise ValueError("memory_request_gib must be positive")
        if memory_limit_gib < memory_request_gib:
            raise ValueError(
                "memory_limit_gib must be greater than or equal to memory_request_gib"
            )
        if not (0 < target_cpu_utilization <= 1):
            raise ValueError("target_cpu_utilization must be between 0 and 1")
        if min_replicas_per_service < 0:
            raise ValueError("min_replicas_per_service must be non-negative")
        if max_replicas_per_service < min_replicas_per_service:
            raise ValueError(
                "max_replicas_per_service must be >= min_replicas_per_service"
            )

        object.__setattr__(self, "_cpu_request", cpu_request)
        object.__setattr__(self, "_cpu_limit", cpu_limit)
        object.__setattr__(self, "_memory_request_gib", memory_request_gib)
        object.__setattr__(self, "_memory_limit_gib", memory_limit_gib)
        object.__setattr__(self, "_target_cpu_utilization", target_cpu_utilization)
        object.__setattr__(self, "_min_replicas_per_service", min_replicas_per_service)
        object.__setattr__(self, "_max_replicas_per_service", max_replicas_per_service)

    def get_cpu_request(self) -> float:
        return self._cpu_request

    def get_cpu_limit(self) -> float:
        return self._cpu_limit

    def get_memory_request_gib(self) -> float:
        return self._memory_request_gib

    def get_memory_limit_gib(self) -> float:
        return self._memory_limit_gib

    def get_target_cpu_utilization(self) -> float:
        return self._target_cpu_utilization

    def get_min_replicas_per_service(self) -> int:
        return self._min_replicas_per_service

    def get_max_replicas_per_service(self) -> int:
        return self._max_replicas_per_service

    def get_target_cpu_load(self) -> float:
        return self._cpu_request * self._target_cpu_utilization


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class NodeTemplate:
    _pool_name: str = field()
    _cpu_capacity: float = field()
    _memory_capacity_gib: float = field()
    _max_pods: int = field()
    _priority: int = field()

    def __init__(
        self,
        *,
        pool_name: str,
        cpu_capacity: float,
        memory_capacity_gib: float,
        max_pods: int,
        priority: int,
    ) -> None:
        if not pool_name:
            raise ValueError("pool_name must be non-empty")
        if cpu_capacity <= 0:
            raise ValueError("cpu_capacity must be positive")
        if memory_capacity_gib <= 0:
            raise ValueError("memory_capacity_gib must be positive")
        if max_pods <= 0:
            raise ValueError("max_pods must be positive")

        object.__setattr__(self, "_pool_name", pool_name)
        object.__setattr__(self, "_cpu_capacity", cpu_capacity)
        object.__setattr__(self, "_memory_capacity_gib", memory_capacity_gib)
        object.__setattr__(self, "_max_pods", max_pods)
        object.__setattr__(self, "_priority", priority)

    def get_pool_name(self) -> str:
        return self._pool_name

    def get_cpu_capacity(self) -> float:
        return self._cpu_capacity

    def get_memory_capacity_gib(self) -> float:
        return self._memory_capacity_gib

    def get_max_pods(self) -> int:
        return self._max_pods

    def get_priority(self) -> int:
        return self._priority


@dataclass(frozen=True, kw_only=True, init=False)
class WorkerNodeConfig:
    _machine_count: int = field()
    _cpu_cores: float = field()
    _memory_gib: float = field()
    _system_reserved_cpu: float = field()
    _kube_reserved_cpu: float = field()
    _system_reserved_memory_gib: float = field()
    _kube_reserved_memory_gib: float = field()
    _max_pods_per_node: int = field()
    _safe_cpu_util: float = field()
    _safe_memory_util: float = field()
    _priority: int = field()

    def __init__(
        self,
        *,
        machine_count: int,
        cpu_cores: float,
        memory_gib: float,
        system_reserved_cpu: float,
        kube_reserved_cpu: float,
        system_reserved_memory_gib: float,
        kube_reserved_memory_gib: float,
        max_pods_per_node: int,
        safe_cpu_util: float,
        safe_memory_util: float,
        priority: int,
    ) -> None:
        if machine_count <= 0:
            raise ValueError("machine_count must be positive")
        if cpu_cores <= 0:
            raise ValueError("cpu_cores must be positive")
        if memory_gib <= 0:
            raise ValueError("memory_gib must be positive")
        if system_reserved_cpu < 0 or kube_reserved_cpu < 0:
            raise ValueError("reserved CPU values must be non-negative")
        if system_reserved_memory_gib < 0 or kube_reserved_memory_gib < 0:
            raise ValueError("reserved memory values must be non-negative")
        if max_pods_per_node <= 0:
            raise ValueError("max_pods_per_node must be positive")
        if not (0 < safe_cpu_util <= 1):
            raise ValueError("safe_cpu_util must be between 0 and 1")
        if not (0 < safe_memory_util <= 1):
            raise ValueError("safe_memory_util must be between 0 and 1")

        object.__setattr__(self, "_machine_count", machine_count)
        object.__setattr__(self, "_cpu_cores", cpu_cores)
        object.__setattr__(self, "_memory_gib", memory_gib)
        object.__setattr__(self, "_system_reserved_cpu", system_reserved_cpu)
        object.__setattr__(self, "_kube_reserved_cpu", kube_reserved_cpu)
        object.__setattr__(self, "_system_reserved_memory_gib", system_reserved_memory_gib)
        object.__setattr__(self, "_kube_reserved_memory_gib", kube_reserved_memory_gib)
        object.__setattr__(self, "_max_pods_per_node", max_pods_per_node)
        object.__setattr__(self, "_safe_cpu_util", safe_cpu_util)
        object.__setattr__(self, "_safe_memory_util", safe_memory_util)
        object.__setattr__(self, "_priority", priority)

        if self.get_allocatable_cpu_cores() <= 0:
            raise ValueError("reserved CPU leaves no allocatable CPU on the node")
        if self.get_allocatable_memory_gib() <= 0:
            raise ValueError("reserved memory leaves no allocatable memory on the node")

    def get_machine_count(self) -> int:
        return self._machine_count

    def get_cpu_cores(self) -> float:
        return self._cpu_cores

    def get_memory_gib(self) -> float:
        return self._memory_gib

    def get_system_reserved_cpu(self) -> float:
        return self._system_reserved_cpu

    def get_kube_reserved_cpu(self) -> float:
        return self._kube_reserved_cpu

    def get_system_reserved_memory_gib(self) -> float:
        return self._system_reserved_memory_gib

    def get_kube_reserved_memory_gib(self) -> float:
        return self._kube_reserved_memory_gib

    def get_max_pods_per_node(self) -> int:
        return self._max_pods_per_node

    def get_safe_cpu_util(self) -> float:
        return self._safe_cpu_util

    def get_safe_memory_util(self) -> float:
        return self._safe_memory_util

    def get_priority(self) -> int:
        return self._priority

    def get_allocatable_cpu_cores(self) -> float:
        return self._cpu_cores - self._system_reserved_cpu - self._kube_reserved_cpu

    def get_allocatable_memory_gib(self) -> float:
        return self._memory_gib - self._system_reserved_memory_gib - self._kube_reserved_memory_gib

    def get_schedulable_cpu_cores(self) -> float:
        return self.get_allocatable_cpu_cores() * self._safe_cpu_util

    def get_schedulable_memory_gib(self) -> float:
        return self.get_allocatable_memory_gib() * self._safe_memory_util

    def get_max_schedulable_pods(self, pod: PodConfig) -> int:
        cpu_bound = math.floor(self.get_schedulable_cpu_cores() / pod.get_cpu_request())
        memory_bound = math.floor(
            self.get_schedulable_memory_gib() / pod.get_memory_request_gib()
        )
        return min(self._max_pods_per_node, cpu_bound, memory_bound)

    def to_node_template(self, pool_name: str, pod: PodConfig) -> NodeTemplate:
        return NodeTemplate(
            pool_name=pool_name,
            cpu_capacity=self.get_schedulable_cpu_cores(),
            memory_capacity_gib=self.get_schedulable_memory_gib(),
            max_pods=self.get_max_schedulable_pods(pod),
            priority=self._priority,
        )


DEFAULT_POD_CONFIG = PodConfig(
    cpu_request=4.0,
    cpu_limit=6.0,
    memory_request_gib=8.0,
    memory_limit_gib=12.0,
    target_cpu_utilization=0.75,
    min_replicas_per_service=1,
    max_replicas_per_service=64,
)


@dataclass(frozen=True, kw_only=True, init=False)
class ClusterConfig:
    """
    Конфигурация Kubernetes-like кластера на физических worker-машинах.

    Параметры:
        headroom: Запас на burst поверх прогноза.
        migration_budget: Лимит перемещений pod'ов за шаг.
        rebalance_trigger_utilization: Порог критической утилизации, после
            которого разрешён перенос pod'ов между нодами.
        worker_pools: Несколько пулов worker nodes с разными лимитами.
    """

    _headroom: float = field()
    _migration_budget: int = field()
    _rebalance_trigger_utilization: float = field()
    _worker_pools: dict[str, WorkerNodeConfig] = field()

    def __init__(
        self,
        *,
        headroom: float,
        migration_budget: int,
        rebalance_trigger_utilization: float,
        worker_pools: dict[str, WorkerNodeConfig],
    ) -> None:
        if headroom < 0:
            raise ValueError("headroom must be non-negative")
        if migration_budget < 0:
            raise ValueError("migration_budget must be non-negative")
        if not (0.0 < rebalance_trigger_utilization <= 1.0):
            raise ValueError("rebalance_trigger_utilization must be in (0, 1]")

        if not isinstance(worker_pools, dict):
            raise TypeError("worker_pools must be a dict[str, WorkerNodeConfig]")
        if len(worker_pools) == 0:
            raise ValueError("worker_pools must contain at least one pool")
        for pool_name, pool in worker_pools.items():
            if not isinstance(pool_name, str):
                raise TypeError("worker_pools keys must be strings")
            if not isinstance(pool, WorkerNodeConfig):
                raise TypeError("worker_pools values must be WorkerNodeConfig")

        object.__setattr__(self, "_headroom", headroom)
        object.__setattr__(self, "_migration_budget", migration_budget)
        object.__setattr__(
            self,
            "_rebalance_trigger_utilization",
            rebalance_trigger_utilization,
        )
        object.__setattr__(self, "_worker_pools", dict(worker_pools))

    def get_headroom(self) -> float:
        return self._headroom

    def get_migration_budget(self) -> int:
        return self._migration_budget

    def get_rebalance_trigger_utilization(self) -> float:
        return self._rebalance_trigger_utilization

    def get_worker_pools(self) -> dict[str, WorkerNodeConfig]:
        return dict(self._worker_pools)

    def get_max_active_nodes(self) -> int:
        return sum(pool.get_machine_count() for pool in self._worker_pools.values())

    def get_ordered_pool_items(self) -> list[tuple[str, WorkerNodeConfig]]:
        return sorted(
            self._worker_pools.items(),
            key=lambda item: (
                item[1].get_priority(),
                -item[1].get_schedulable_cpu_cores(),
                -item[1].get_schedulable_memory_gib(),
                item[0],
            ),
        )

    def get_node_templates(self, pod: PodConfig = DEFAULT_POD_CONFIG) -> list[NodeTemplate]:
        templates: list[NodeTemplate] = []
        for pool_name, pool in self.get_ordered_pool_items():
            template = pool.to_node_template(pool_name, pod)
            templates.extend([template] * pool.get_machine_count())
        return templates

    def required_nodes_for_replicas(self, replicas: int) -> int:
        if replicas <= 0:
            return 0

        remaining = replicas
        required_nodes = 0
        for template in self.get_node_templates():
            if remaining <= 0:
                break
            remaining -= template.get_max_pods()
            required_nodes += 1

        required_nodes = max(required_nodes, 1)
        return min(required_nodes, self.get_max_active_nodes())


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
    ),
}

DEFAULT_CLUSTER_CONFIG = ClusterConfig(
    headroom=0.15,
    migration_budget=12,
    rebalance_trigger_utilization=0.95,
    worker_pools=DEFAULT_WORKER_POOLS,
)


__all__ = [
    "PodConfig",
    "NodeTemplate",
    "WorkerNodeConfig",
    "ClusterConfig",
    "DEFAULT_CLUSTER_CONFIG",
]
