"""
Интерфейс для модулей балансировки нагрузки

Определяет контракт для различных стратегий распределения виртуальных машин
по нодам кластера Proxmox VE.
"""

from abc import ABC, abstractmethod
from typing import Dict, List


class BalancingInterface(ABC):
    """Интерфейс для модулей балансировки нагрузки"""

    @abstractmethod
    def distribute_deployment(self, users: List[str], nodes: List[str],
                            config: Dict = None) -> Dict[str, List[str]]:
        """
        Распределить пользователей по нодам

        Args:
            users: Список пользователей
            nodes: Доступные ноды
            config: Конфигурация развертывания

        Returns:
            Словарь {нода: [пользователи]}
        """
        pass

    @abstractmethod
    def analyze_node_load(self, nodes: List[str]) -> Dict[str, Dict[str, float]]:
        """
        Проанализировать загруженность нод

        Returns:
            Метрики загруженности для каждой ноды
        """
        pass

    @abstractmethod
    def optimize_distribution(self, current_distribution: Dict[str, List[str]],
                            config: Dict = None) -> Dict[str, List[str]]:
        """Оптимизировать существующее распределение"""
        pass
