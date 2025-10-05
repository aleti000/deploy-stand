"""
Простой модуль балансировки нагрузки

Реализует базовую стратегию распределения виртуальных машин по нодам
на основе простого алгоритма round-robin.
"""

import logging
from typing import Dict, List
from core.interfaces.balancing_interface import BalancingInterface
from core.proxmox.proxmox_client import ProxmoxClient

logger = logging.getLogger(__name__)


class SimpleBalancer(BalancingInterface):
    """Простая балансировка нагрузки"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация простого балансировщика

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def distribute_deployment(self, users: List[str], nodes: List[str],
                            config: Dict = None) -> Dict[str, List[str]]:
        """
        Распределить пользователей по нодам простым алгоритмом

        Args:
            users: Список пользователей
            nodes: Доступные ноды
            config: Конфигурация развертывания

        Returns:
            Словарь {нода: [пользователи]}
        """
        if not users or not nodes:
            return {}

        distribution = {node: [] for node in nodes}

        # Простое распределение round-robin
        for i, user in enumerate(users):
            node_index = i % len(nodes)
            selected_node = nodes[node_index]
            distribution[selected_node].append(user)

        logger.info(f"Простое распределение: {distribution}")
        return distribution

    def analyze_node_load(self, nodes: List[str]) -> Dict[str, Dict[str, float]]:
        """
        Проанализировать загруженность нод

        Args:
            nodes: Список нод для анализа

        Returns:
            Метрики загруженности для каждой ноды
        """
        node_metrics = {}

        for node in nodes:
            try:
                # Получить количество виртуальных машин на ноде
                vms = self.proxmox.get_vms_on_node(node)
                vm_count = len(vms)

                # Рассчитать базовые метрики
                metrics = {
                    'vm_count': vm_count,
                    'cpu_usage': 0.0,  # Заглушка - в реальности нужно получать реальные метрики
                    'memory_usage': 0.0,
                    'storage_available': 100.0,  # Заглушка
                    'network_bandwidth': 100.0,  # Заглушка
                    'active_templates': 0  # Заглушка
                }

                node_metrics[node] = metrics

            except Exception as e:
                logger.error(f"Ошибка анализа ноды {node}: {e}")
                # Fallback метрики при ошибке
                node_metrics[node] = {
                    'vm_count': 999,  # Высокое значение чтобы избежать выбора этой ноды
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
        # Простая оптимизация - перераспределить пользователей равномерно
        all_users = []
        for users in current_distribution.values():
            all_users.extend(users)

        nodes = list(current_distribution.keys())

        if not all_users or not nodes:
            return current_distribution

        # Перераспределить пользователей равномерно
        optimized_distribution = {node: [] for node in nodes}

        for i, user in enumerate(all_users):
            node_index = i % len(nodes)
            selected_node = nodes[node_index]
            optimized_distribution[selected_node].append(user)

        logger.info(f"Оптимизированное распределение: {optimized_distribution}")
        return optimized_distribution
