"""
Распределитель ресурсов системы Deploy-Stand

Предоставляет функциональность для распределения задач развертывания
по нодам кластера Proxmox VE.
"""

import logging
from typing import Dict, List, Any
from core.proxmox.proxmox_client import ProxmoxClient

logger = logging.getLogger(__name__)


class DeploymentDistributor:
    """Распределитель задач развертывания"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация распределителя ресурсов

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def distribute_deployment(self, users: List[str], nodes: List[str]) -> Dict[str, List[str]]:
        """
        Распределить пользователей по нодам

        Args:
            users: Список пользователей
            nodes: Доступные ноды

        Returns:
            Словарь {нода: [пользователи]}
        """
        if not users or not nodes:
            return {}

        # Простое распределение round-robin
        distribution = {node: [] for node in nodes}

        for i, user in enumerate(users):
            node_index = i % len(nodes)
            selected_node = nodes[node_index]
            distribution[selected_node].append(user)

        logger.info(f"Распределение пользователей: {distribution}")
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
                    'vm_count': 999,  # Высокое значение чтобы избежать выбора этой ноды
                    'cpu_usage': 1.0,
                    'memory_usage': 1.0,
                    'storage_available': 0.0,
                    'network_bandwidth': 0.0,
                    'active_templates': 0
                }

        return node_metrics

    def select_optimal_node(self, nodes: List[str], user_count: int = 1) -> str:
        """
        Выбрать оптимальную ноду для развертывания

        Args:
            nodes: Доступные ноды
            user_count: Количество пользователей для размещения

        Returns:
            Имя оптимальной ноды
        """
        if not nodes:
            raise ValueError("Нет доступных нод")

        if len(nodes) == 1:
            return nodes[0]

        # Анализировать загруженность нод
        node_metrics = self.analyze_node_load(nodes)

        # Найти ноду с минимальной загруженностью
        best_node = None
        best_score = float('inf')

        for node, metrics in node_metrics.items():
            # Рассчитать общий score (меньше = лучше)
            score = (metrics['vm_count'] * 0.3 +
                    metrics['cpu_usage'] * 0.25 +
                    metrics['memory_usage'] * 0.25 +
                    (1.0 - metrics['storage_available'] / 100.0) * 0.2)

            if score < best_score:
                best_score = score
                best_node = node

        if best_node:
            logger.info(f"Выбрана оптимальная нода: {best_node} (score: {best_score:.2f})")
            return best_node

        # Fallback на первую ноду
        logger.warning("Не удалось выбрать оптимальную ноду, используется fallback")
        return nodes[0]

    def get_distribution_summary(self, distribution: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Получить сводку распределения

        Args:
            distribution: Распределение пользователей по нодам

        Returns:
            Сводная информация о распределении
        """
        total_users = sum(len(users) for users in distribution.values())
        node_count = len(distribution)

        if node_count == 0:
            return {'total_users': 0, 'node_count': 0, 'avg_users_per_node': 0}

        avg_users_per_node = total_users / node_count

        return {
            'total_users': total_users,
            'node_count': node_count,
            'avg_users_per_node': avg_users_per_node,
            'distribution': distribution
        }
