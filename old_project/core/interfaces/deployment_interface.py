"""
Интерфейс для модулей развертывания виртуальных машин

Определяет контракт для различных стратегий развертывания виртуальных машин
в кластере Proxmox VE.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any


class DeploymentInterface(ABC):
    """Интерфейс для модулей развертывания виртуальных машин"""

    @abstractmethod
    def deploy_configuration(self, users: List[str], config: Dict[str, Any],
                           node_selection: str = "auto", target_node: str = None) -> Dict[str, str]:
        """
        Развернуть конфигурацию виртуальных машин

        Args:
            users: Список пользователей для развертывания
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды ("auto", "specific", "balanced")
            target_node: Целевая нода (если node_selection="specific")

        Returns:
            Словарь {пользователь: пароль}
        """
        pass

    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Валидация конфигурации развертывания"""
        pass

    @abstractmethod
    def get_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        """Получить статус развертывания"""
        pass
