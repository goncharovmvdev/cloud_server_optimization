# Список литературы для аннотации проекта

Подборка ориентирована на тему проекта: оптимизация размещения подов и управления ресурсами в Kubernetes-подобном облачном кластере. Оставлены только 7 наиболее важных источников с упором на методы оптимизации и официальную документацию Kubernetes по распределению ресурсов.

## Ключевые источники

1. Burns B., Grant B., Oppenheimer D., Brewer E., Wilkes J. Borg, Omega, and Kubernetes // Queue. 2016. Vol. 14, no. 1. P. 70-93. DOI: 10.1145/2898442.2898444.

2. Christensen H. I., Khan A., Pokutta S., Tetali P. Approximation and online algorithms for multidimensional bin packing: A survey // Computer Science Review. 2017. Vol. 24. P. 63-79. DOI: 10.1016/j.cosrev.2016.12.001.

3. Baker B. S. A new proof for the first-fit decreasing bin-packing algorithm // Journal of Algorithms. 1985. Vol. 6, no. 1. P. 49-70. DOI: 10.1016/0196-6774(85)90018-5.

4. Karmarkar N., Karp R. M. An efficient approximation scheme for the one-dimensional bin-packing problem // Proceedings of the 23rd Annual Symposium on Foundations of Computer Science (SFCS 1982). IEEE, 1982. P. 312-320. DOI: 10.1109/SFCS.1982.61.

5. Rzadca K., Findeisen P., Swiderski J., Zych P., Broniek P., Kusmierek J., Nowak P. K., Strack B., Witusowski P., Hand S., Wilkes J. Autopilot: workload autoscaling at Google Scale // Proceedings of the Fifteenth European Conference on Computer Systems (EuroSys '20). ACM, 2020. DOI: 10.1145/3342195.3387524.

6. Kubernetes Authors. Scheduler Configuration [Электронный ресурс]. URL: https://kubernetes.io/docs/reference/scheduling/config/ (дата обращения: 15.03.2026).

7. Kubernetes Authors. Horizontal Pod Autoscaling [Электронный ресурс]. URL: https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/ (дата обращения: 15.03.2026).

## Эти источники:

- Источники 2-4 дают алгоритмическую базу для раздела про оптимизацию размещения и bin packing.
- Источник 5 полезен для обоснования автоматического масштабирования нагрузки как части оптимизации ресурсов.
- Источник 1 связывает выбранные методы с архитектурой реальных кластерных планировщиков и Kubernetes.
- Источники 6-7 нужны как официальная практическая опора для описания логики `kube-scheduler` и `HorizontalPodAutoscaler`.
