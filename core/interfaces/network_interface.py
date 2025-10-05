"""
Интерфейс для модулей управления сетью

Определяет контракт для различных стратегий настройки сети виртуальных машин
в кластере Proxmox VE.
"""

from abc import ABC, abstractmethod
from typing import Dict, List


class NetworkInterface(ABC):
    """Интерфейс для модулей управления сетью"""

    @abstractmethod
    def configure_network(self, vmid: int, node: str, networks: List[Dict],
                         pool: str, device_type: str = 'linux') -> bool:
        """
        Настроить сетевые интерфейсы виртуальной машины

        Args:
            vmid: ID виртуальной машины
            node: Нода размещения
            networks: Конфигурация сетей
            pool: Пул пользователя
            device_type: Тип устройства

        Returns:
            True если настройка успешна
        """
        pass

    @abstractmethod
    def allocate_bridge(self, node: str, bridge_name: str, pool: str,
                       reserved: bool = False) -> str:
        """Выделить bridge для сети"""
        pass

    @abstractmethod
    def cleanup_unused_bridges(self, nodes: List[str]) -> int:
        """Очистить неиспользуемые bridge'ы"""
        pass
