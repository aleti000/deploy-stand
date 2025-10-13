"""
Модуль сбалансированного развертывания виртуальных машин

Реализует развертывание с равномерным распределением стендов пользователей
по всем доступным нодам с полной независимостью от других модулей.

РЕФАКТОРИНГ: Упрощенная версия с использованием базовых модулей
"""

import logging
from typing import Dict, List, Any, Optional
from core.modules.deployment.basic_deployer import BasicDeployer
from core.proxmox.proxmox_client import ProxmoxClient
from core.interfaces.balancing_interface import BalancingInterface
from core.modules.common.config_validator import ConfigValidator
from core.modules.common.deployment_utils import DeploymentUtils
from core.modules.users.user_manager import UserManager
from core.modules.templates.template_manager import TemplateManager
from core.modules.deployment.vm_factory import VMFactory

logger = logging.getLogger(__name__)


class BalancedDeployer(BasicDeployer):
    """Сбалансированный развертыватель виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient, balancing_module: BalancingInterface = None):
        """
        Инициализация сбалансированного развертывателя

        Args:
            proxmox_client: Клиент для работы с Proxmox API
            balancing_module: Модуль балансировки нагрузки (по умолчанию SmartBalancer)
        """
        self.proxmox = proxmox_client
        self.utils = DeploymentUtils()
        self.validator = ConfigValidator()
        self.user_manager = UserManager(proxmox_client)
        self.template_manager = TemplateManager(proxmox_client)
        self.vm_factory = VMFactory(proxmox_client)

        if balancing_module is None:
            # Импорт здесь чтобы избежать циклических зависимостей
            from core.modules.balancing.smart_balancer import SmartBalancer
            self.balancer = SmartBalancer(proxmox_client)
        else:
            self.balancer = balancing_module

    def deploy_configuration(self, users: List[str], config: Dict[str, Any],
                           node_selection: str = "balanced", target_node: str = None) -> Dict[str, str]:
        """
        Развернуть конфигурацию виртуальных машин с балансировкой нагрузки

        Args:
            users: Список пользователей для развертывания
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды (всегда "balanced")
            target_node: Целевая нода (игнорируется в сбалансированном режиме)

        Returns:
            Словарь {пользователь: пароль}
        """
        # Валидация конфигурации
        validation_result = self.validator.validate_deployment_config(config)
        if not validation_result.is_valid:
            error_msg = "Ошибка валидации конфигурации:\n" + str(validation_result)
            logger.error(error_msg)
            raise ValueError(error_msg)

        results = {}

        try:
            logger.info("Начинаем сбалансированное развертывание")

            # Получить список доступных нод
            nodes = self.proxmox.get_nodes()
            if not nodes:
                raise ValueError("Нет доступных нод для развертывания")

            logger.info(f"Доступные ноды: {nodes}")

            # Распределить пользователей по нодам с помощью балансировщика
            distribution = self.balancer.distribute_deployment(users, nodes, config)
            logger.info(f"Распределение пользователей по нодам: {distribution}")

            # Развернуть каждого пользователя на назначенной ноде
            for node, node_users in distribution.items():
                if not node_users:
                    continue

                logger.info(f"Развертывание {len(node_users)} пользователей на ноде {node}")

                for user in node_users:
                    try:
                        # Определяем тип развертывания для пользователя
                        deploy_strategy = self._determine_deployment_strategy(user, config, node)

                        if deploy_strategy == "local":
                            logger.info(f"Использование локального развертывания для пользователя {user} на ноде {node}")
                            user_result = self._deploy_for_user_local(user, config, node)
                        else:  # remote
                            logger.info(f"Использование удаленного развертывания для пользователя {user} на ноде {node}")
                            # Подготовить шаблоны для целевой ноды через TemplateManager
                            template_mapping = self.template_manager.prepare_templates_for_target_node(config, node)
                            user_result = self._deploy_for_user_remote(user, config, node, template_mapping)

                        results.update(user_result)

                    except Exception as e:
                        logger.error(f"Ошибка развертывания пользователя {user} на ноде {node}: {e}")
                        # Продолжаем с другими пользователями
                        continue

            # Перезагрузить сетевые конфигурации на задействованных нодах после развертывания
            self._reload_affected_nodes_network(set(distribution.keys()))

            logger.info(f"Сбалансированное развертывание завершено для {len(results)} пользователей")
            return results

        except Exception as e:
            logger.error(f"Ошибка сбалансированного развертывания: {e}")
            raise

    def _determine_deployment_strategy(self, user: str, config: Dict[str, Any], target_node: str) -> str:
        """
        Определить стратегию развертывания для пользователя

        Args:
            user: Имя пользователя
            config: Конфигурация развертывания
            target_node: Целевая нода для пользователя

        Returns:
            "local" если развертывание на ноде шаблона, "remote" в противном случае
        """
        # Проверить все template_node из конфигурации
        for machine_config in config.get('machines', []):
            template_node = machine_config.get('template_node')
            if template_node == target_node:
                # Хотя бы один шаблон находится на целевой ноде
                return "local"

        # Все шаблоны на других нодах
        return "remote"

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Валидация конфигурации развертывания

        Args:
            config: Конфигурация для валидации

        Returns:
            True если конфигурация валидна
        """
        # Базовая валидация через ConfigValidator
        validation_result = self.validator.validate_deployment_config(config)
        if not validation_result.is_valid:
            return False

        # Дополнительная валидация для сбалансированного режима
        machines = config.get('machines', [])
        template_nodes = set()

        # Собрать все уникальные template_node
        for machine in machines:
            template_node = machine.get('template_node')
            if template_node:
                template_nodes.add(template_node)

        if not template_nodes:
            logger.error("В конфигурации не указаны template_node для машин")
            return False

        # Проверить доступность template_node
        available_nodes = set(self.proxmox.get_nodes())
        for template_node in template_nodes:
            if template_node not in available_nodes:
                logger.error(f"Шаблонная нода {template_node} недоступна")
                return False

        return True

    def _reload_affected_nodes_network(self, nodes: set):
        """
        Перезагрузить сеть на задействованных нодах

        Args:
            nodes: Множество имен нод для перезагрузки
        """
        if not nodes:
            return

        print("🔄 Обновление сетевых конфигураций на задействованных нодах...")
        for node in nodes:
            try:
                if self.proxmox.reload_node_network(node):
                    print(f"  ✅ Сеть ноды {node} обновлена")
                else:
                    print(f"  ⚠️ Не удалось обновить сеть ноды {node}")
            except Exception as e:
                print(f"  ❌ Ошибка обновления сети ноды {node}: {e}")

    def get_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        """
        Получить статус сбалансированного развертывания

        Args:
            deployment_id: ID развертывания

        Returns:
            Словарь со статусом развертывания
        """
        return {
            'deployment_id': deployment_id,
            'status': 'completed',
            'strategy': 'balanced',
            'balancer': self.balancer.__class__.__name__,
            'message': 'Сбалансированное развертывание завершено'
        }
