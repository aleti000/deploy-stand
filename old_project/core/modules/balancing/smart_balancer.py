"""
Интеллектуальный модуль балансировки нагрузки

Реализует продвинутую стратегию распределения виртуальных машин по нодам
с предиктивным анализом и многофакторной оптимизацией.
"""

import logging
from typing import Dict, List
from core.interfaces.balancing_interface import BalancingInterface
from core.proxmox.proxmox_client import ProxmoxClient
from utils.monitoring.metrics import PerformanceMetrics
from utils.caching.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class SmartBalancer(BalancingInterface):
    """Интеллектуальная балансировка с предиктивным анализом"""

    def __init__(self, proxmox_client: ProxmoxClient,
                 metrics: PerformanceMetrics, cache: CacheManager):
        """
        Инициализация интеллектуального балансировщика

        Args:
            proxmox_client: Клиент для работы с Proxmox API
            metrics: Метрики производительности
            cache: Кеш менеджер
        """
        self.proxmox = proxmox_client
        self.metrics = metrics
        self.cache = cache
        self.cache_ttl = 300  # 5 минут

    def distribute_deployment(self, users: List[str], nodes: List[str],
                            config: Dict = None) -> Dict[str, List[str]]:
        """
        Интеллектуальное распределение пользователей

        Args:
            users: Список пользователей
            nodes: Доступные ноды
            config: Конфигурация развертывания

        Returns:
            Словарь {нода: [пользователи]}
        """
        cache_key = f"distribution:{hash(str(users))}:{hash(str(nodes))}"

        # Проверить кеш
        cached_result = self.cache.get(cache_key)
        if cached_result:
            logger.info("Использовано кешированное распределение")
            return cached_result

        # Собрать метрики нод
        node_metrics = self.analyze_node_load(nodes)

        # Рассчитать веса нод
        node_weights = self._calculate_node_weights(node_metrics, config)

        # Предиктивный анализ требований пользователей
        user_demand = self._estimate_user_resource_demand(users, config)

        # Распределить пользователей
        distribution = self._intelligent_distribution(users, nodes, node_weights, user_demand)

        # Оптимизировать распределение
        optimized_distribution = self._optimize_for_template_migration(distribution, config)

        # Сохранить в кеш
        self.cache.set(cache_key, optimized_distribution, self.cache_ttl)

        logger.info(f"Интеллектуальное распределение: {optimized_distribution}")
        return optimized_distribution

    def analyze_node_load(self, nodes: List[str]) -> Dict[str, Dict[str, float]]:
        """
        Комплексный анализ загруженности нод

        Args:
            nodes: Список нод для анализа

        Returns:
            Метрики загруженности для каждой ноды
        """
        node_metrics = {}

        for node in nodes:
            try:
                # Получить базовые метрики
                vms = self.proxmox.get_vms_on_node(node)
                vm_count = len(vms)

                # Расширенные метрики (заглушки для демонстрации)
                metrics = {
                    'vm_count': vm_count,
                    'cpu_usage': min(vm_count * 0.1, 1.0),  # Оценка на основе количества VM
                    'memory_usage': min(vm_count * 0.15, 1.0),  # Оценка на основе количества VM
                    'storage_available': max(100.0 - vm_count * 5.0, 0.0),  # Оценка доступного места
                    'network_bandwidth': max(100.0 - vm_count * 2.0, 10.0),  # Оценка пропускной способности
                    'active_templates': min(vm_count, 10)  # Оценка количества активных шаблонов
                }

                node_metrics[node] = metrics

            except Exception as e:
                logger.error(f"Ошибка анализа ноды {node}: {e}")
                # Fallback метрики при ошибке
                node_metrics[node] = {
                    'vm_count': 999,
                    'cpu_usage': 1.0,
                    'memory_usage': 1.0,
                    'storage_available': 0.0,
                    'network_bandwidth': 0.0,
                    'active_templates': 0
                }

        return node_metrics

    def optimize_distribution(self, current_distribution: Dict[str, List[str]],
                            config: Dict = None) -> Dict[str, List[str]]:
        """
        Оптимизировать существующее распределение

        Args:
            current_distribution: Текущее распределение пользователей
            config: Конфигурация развертывания

        Returns:
            Оптимизированное распределение
        """
        # Получить актуальные метрики нод
        nodes = list(current_distribution.keys())
        node_metrics = self.analyze_node_load(nodes)

        # Рассчитать веса нод
        node_weights = self._calculate_node_weights(node_metrics, config)

        # Получить всех пользователей
        all_users = []
        for users in current_distribution.values():
            all_users.extend(users)

        # Предиктивный анализ требований пользователей
        user_demand = self._estimate_user_resource_demand(all_users, config)

        # Перераспределить пользователей
        optimized_distribution = self._intelligent_distribution(all_users, nodes, node_weights, user_demand)

        logger.info(f"Распределение оптимизировано: {optimized_distribution}")
        return optimized_distribution

    def _calculate_node_weights(self, node_metrics: Dict[str, Dict[str, float]],
                              config: Dict = None) -> Dict[str, float]:
        """
        Рассчитать весовые коэффициенты для нод

        Args:
            node_metrics: Метрики нод
            config: Конфигурация развертывания

        Returns:
            Словарь весов нод
        """
        weights = {}

        for node, metrics in node_metrics.items():
            # Базовый вес на основе количества VM (меньше = лучше)
            vm_weight = 1.0 / (1.0 + metrics['vm_count'])

            # CPU weight (ниже использование = выше вес)
            cpu_weight = 1.0 / (1.0 + metrics['cpu_usage'])

            # Memory weight (больше доступной памяти = выше вес)
            memory_weight = 1.0 / (1.0 + (1.0 - metrics['memory_usage']))

            # Storage weight (больше места = выше вес)
            storage_weight = metrics['storage_available'] / 100.0

            # Комбинированный вес с настраиваемыми коэффициентами
            total_weight = (vm_weight * 0.3 + cpu_weight * 0.25 +
                           memory_weight * 0.25 + storage_weight * 0.2)

            weights[node] = total_weight

        return weights

    def _estimate_user_resource_demand(self, users: List[str], config: Dict = None) -> Dict[str, Dict[str, float]]:
        """
        Предиктивная оценка потребления ресурсов пользователями

        Args:
            users: Список пользователей
            config: Конфигурация развертывания

        Returns:
            Словарь требований ресурсов для каждого пользователя
        """
        user_demand = {}

        # Базовые требования ресурсов на пользователя
        base_cpu = 0.1
        base_memory = 0.2
        base_storage = 10.0  # GB

        # Коэффициенты в зависимости от конфигурации
        if config:
            machines = config.get('machines', [])
            if machines:
                # Увеличить требования в зависимости от количества машин
                machine_multiplier = len(machines)
                base_cpu *= machine_multiplier
                base_memory *= machine_multiplier
                base_storage *= machine_multiplier

        for user in users:
            user_demand[user] = {
                'cpu': base_cpu,
                'memory': base_memory,
                'storage': base_storage
            }

        return user_demand

    def _intelligent_distribution(self, users: List[str], nodes: List[str],
                                node_weights: Dict[str, float],
                                user_demand: Dict[str, Dict[str, float]]) -> Dict[str, List[str]]:
        """
        Интеллектуальное распределение пользователей по нодам

        Args:
            users: Список пользователей
            nodes: Доступные ноды
            node_weights: Весовые коэффициенты нод
            user_demand: Требования ресурсов пользователей

        Returns:
            Распределение пользователей по нодам
        """
        distribution = {node: [] for node in nodes}

        # Нормализация весов
        total_weight = sum(node_weights.values())
        if total_weight == 0:
            # Fallback: равномерное распределение
            return self._fallback_distribution(users, nodes)

        normalized_weights = {node: weight/total_weight for node, weight in node_weights.items()}

        # Распределение пользователей с учетом их потребностей
        for user in users:
            # Выбор лучшей ноды для пользователя
            best_node = self._select_best_node_for_user(user, nodes, normalized_weights, user_demand)

            if best_node:
                distribution[best_node].append(user)
            else:
                # Fallback на ноду с минимальной загруженностью
                least_loaded_node = min(nodes, key=lambda x: node_weights[x])
                distribution[least_loaded_node].append(user)

        return distribution

    def _select_best_node_for_user(self, user: str, nodes: List[str],
                                 node_weights: Dict[str, float],
                                 user_demand: Dict[str, Dict[str, float]]) -> str:
        """
        Выбор оптимальной ноды для конкретного пользователя

        Args:
            user: Пользователь
            nodes: Доступные ноды
            node_weights: Весовые коэффициенты нод
            user_demand: Требования ресурсов пользователя

        Returns:
            Лучшая нода для пользователя
        """
        best_node = None
        best_score = -1

        for node in nodes:
            # Расчет совместимости пользователя с нодой
            compatibility_score = self._calculate_user_node_compatibility(user, node, user_demand)

            # Комбинированный score
            total_score = node_weights[node] * 0.7 + compatibility_score * 0.3

            if total_score > best_score:
                best_score = total_score
                best_node = node

        return best_node

    def _calculate_user_node_compatibility(self, user: str, node: str,
                                         user_demand: Dict[str, Dict[str, float]]) -> float:
        """
        Рассчитать совместимость пользователя с нодой

        Args:
            user: Пользователь
            node: Нода
            user_demand: Требования ресурсов пользователя

        Returns:
            Коэффициент совместимости 0.0-1.0
        """
        # Заглушка - в реальности здесь должна быть более сложная логика
        # учитывающая исторические данные, предпочтения и т.д.

        if user not in user_demand:
            return 0.5  # Средняя совместимость по умолчанию

        # Простая логика: предпочтение нодам с достаточными ресурсами
        user_needs = user_demand[user]

        # Здесь можно добавить более сложную логику оценки совместимости
        # Например, учитывать историю размещения пользователя, сетевые требования и т.д.

        return 0.8  # Заглушка - высокая совместимость

    def _optimize_for_template_migration(self, distribution: Dict[str, List[str]],
                                       config: Dict = None) -> Dict[str, List[str]]:
        """
        Оптимизация распределения для минимизации миграций шаблонов

        Args:
            distribution: Текущее распределение
            config: Конфигурация развертывания

        Returns:
            Оптимизированное распределение
        """
        if not config:
            return distribution

        optimized = {node: [] for node in distribution.keys()}

        # Анализ требований к шаблонам для каждой группы пользователей
        template_requirements = self._analyze_template_requirements(distribution, config)

        # Перераспределение для оптимизации использования шаблонов
        for node, users in distribution.items():
            if users:
                # Проверить эффективность использования шаблонов на этой ноде
                template_efficiency = self._calculate_template_efficiency(node, users, config)

                if template_efficiency < 0.7:  # Если эффективность ниже 70%
                    # Попытаться переместить пользователей на более эффективные ноды
                    moved_users = self._optimize_user_placement(users, node, distribution, config)
                    optimized[node] = moved_users
                else:
                    optimized[node] = users

        return optimized

    def _analyze_template_requirements(self, distribution: Dict[str, List[str]],
                                     config: Dict = None) -> Dict[str, List]:
        """
        Анализ требований к шаблонам для распределения

        Args:
            distribution: Распределение пользователей
            config: Конфигурация развертывания

        Returns:
            Требования к шаблонам для каждой ноды
        """
        template_requirements = {}

        if not config:
            return template_requirements

        machines = config.get('machines', [])

        for node, users in distribution.items():
            node_templates = set()

            for user in users:
                for machine in machines:
                    template_vmid = machine.get('template_vmid')
                    if template_vmid:
                        node_templates.add(template_vmid)

            template_requirements[node] = list(node_templates)

        return template_requirements

    def _calculate_template_efficiency(self, node: str, users: List[str],
                                     config: Dict = None) -> float:
        """
        Рассчитать эффективность использования шаблонов на ноде

        Args:
            node: Нода для анализа
            users: Пользователи на ноде
            config: Конфигурация развертывания

        Returns:
            Коэффициент эффективности 0.0-1.0
        """
        if not config or not users:
            return 0.0

        # Заглушка - в реальности здесь должна быть логика расчета эффективности
        # учитывающая использование шаблонов, миграции и производительность

        # Простая логика: больше пользователей = выше эффективность
        efficiency = min(len(users) * 0.1, 1.0)

        return efficiency

    def _optimize_user_placement(self, users: List[str], current_node: str,
                               distribution: Dict[str, List[str]],
                               config: Dict = None) -> List[str]:
        """
        Оптимизировать размещение пользователей

        Args:
            users: Пользователи для размещения
            current_node: Текущая нода
            distribution: Текущее распределение
            config: Конфигурация развертывания

        Returns:
            Оптимизированный список пользователей для текущей ноды
        """
        # Заглушка - в реальности здесь должна быть сложная логика оптимизации
        # учитывающая множество факторов

        # Пока просто возвращаем пользователей как есть
        return users

    def _fallback_distribution(self, users: List[str], nodes: List[str]) -> Dict[str, List[str]]:
        """
        Fallback распределение при ошибках

        Args:
            users: Список пользователей
            nodes: Доступные ноды

        Returns:
            Простое распределение
        """
        if not users or not nodes:
            return {}

        distribution = {node: [] for node in nodes}

        for i, user in enumerate(users):
            node_index = i % len(nodes)
            selected_node = nodes[node_index]
            distribution[selected_node].append(user)

        logger.warning(f"Использовано fallback распределение: {distribution}")
        return distribution
