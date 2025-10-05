"""
Интерфейс для модулей управления шаблонами

Определяет контракт для различных стратегий управления шаблонами виртуальных машин
в кластере Proxmox VE.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any


class TemplateInterface(ABC):
    """Интерфейс для модулей управления шаблонами"""

    @abstractmethod
    def prepare_templates_for_target_node(self, config: Dict[str, Any],
                                        node_selection: str, target_node: str) -> bool:
        """
        Подготовить шаблоны для целевой ноды

        Args:
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды
            target_node: Целевая нода

        Returns:
            True если подготовка успешна
        """
        pass

    @abstractmethod
    def create_local_template(self, template_node: str, template_vmid: int,
                            target_node: str, new_vmid: int) -> bool:
        """Создать локальный шаблон на целевой ноде"""
        pass

    @abstractmethod
    def get_template_mapping(self) -> Dict[str, int]:
        """Получить mapping локальных шаблонов"""
        pass
