import random
from typing import List, Dict
from app.core.proxmox_manager import ProxmoxManager
from app.utils.logger import logger


class DeploymentDistributor:
    """Модуль для распределения пользователей по нодам кластера"""

    def __init__(self, proxmox_manager: ProxmoxManager):
        self.proxmox = proxmox_manager

    def distribute_users_to_nodes(self, users: List[str]) -> Dict[str, str]:
        """
        Распределить пользователей по нодам равномерно

        Args:
            users: Список пользователей

        Returns:
            dict: Словарь распределения пользователь -> нода
        """
        nodes = self.proxmox.get_nodes()
        if not nodes:
            logger.error("❌ Не удалось получить список нод!")
            return {}

        if len(nodes) == 1:
            # Если только одна нода, размещаем всех пользователей на ней
            return {user: nodes[0] for user in users}

        # Распределяем пользователей равномерно по всем нодам
        user_node_mapping = {}
        for i, user in enumerate(users):
            node_index = i % len(nodes)
            user_node_mapping[user] = nodes[node_index]

        return user_node_mapping

    def select_target_node(self, nodes: List[str], selection: str, target_node: str) -> str:
        """Выбрать целевую ноду для развертывания"""
        if len(nodes) == 1:
            return nodes[0]
        if selection == "specific" and target_node:
            return target_node
        else:
            # Используем первую ноду по умолчанию
            return nodes[0]

    def select_node_for_user(self, nodes: List[str], selection: str, target_node: str) -> str:
        """Выбрать ноду для конкретного пользователя"""
        if len(nodes) == 1:
            return nodes[0]
        if selection == "specific" and target_node:
            return target_node
        elif selection == "balanced":
            return random.choice(nodes)
        else:
            return None

    def get_node_distribution_info(self, users: List[str]) -> Dict[str, int]:
        """Получить информацию о распределении пользователей по нодам"""
        distribution = self.distribute_users_to_nodes(users)
        node_counts = {}
        for node in distribution.values():
            node_counts[node] = node_counts.get(node, 0) + 1
        return node_counts

    def validate_node_availability(self, nodes: List[str]) -> List[str]:
        """Проверить доступность нод и вернуть список доступных"""
        available_nodes = []
        for node in nodes:
            try:
                # Попытаемся получить статус ноды
                status = self.proxmox.proxmox.nodes(node).status.get()
                if status.get('status') == 'online':
                    available_nodes.append(node)
                else:
                    logger.warning(f"Нода '{node}' недоступна (статус: {status.get('status', 'unknown')})")
            except Exception as e:
                logger.warning(f"Не удалось получить статус ноды '{node}': {e}")

        if not available_nodes:
            logger.error("❌ Нет доступных нод для развертывания!")
            return []

        return available_nodes
