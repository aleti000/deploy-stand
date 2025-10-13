"""
Локальный модуль развертывания виртуальных машин

Развертывает виртуальные машины непосредственно на ноде,
где хранятся оригинальные шаблоны.

РЕФАКТОРИНГ: Упрощенная версия с использованием базовых модулей
"""

import logging
from typing import Dict, List, Any
from core.modules.deployment.basic_deployer import BasicDeployer
from core.proxmox.proxmox_client import ProxmoxClient
from core.modules.common.config_validator import ConfigValidator
from core.modules.common.deployment_utils import DeploymentUtils
from core.modules.users.user_manager import UserManager
from core.modules.deployment.vm_factory import VMFactory

logger = logging.getLogger(__name__)


class LocalDeployer(BasicDeployer):
    """Локальный развертыватель виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация локального развертывателя

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client
        self.utils = DeploymentUtils()
        self.validator = ConfigValidator()
        self.user_manager = UserManager(proxmox_client)
        self.vm_factory = VMFactory(proxmox_client)

    def deploy_configuration(self, users: List[str], config: Dict[str, Any],
                           node_selection: str = "auto", target_node: str = None) -> Dict[str, str]:
        """
        Развернуть конфигурацию виртуальных машин на локальной ноде

        Args:
            users: Список пользователей для развертывания
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды (игнорируется, всегда использует ноду с шаблонами)
            target_node: Целевая нода (игнорируется, используется нода шаблона)

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
        nodes_with_users = set()

        try:
            # Развернуть для каждого пользователя
            for user in users:
                user_result = self._deploy_for_user(user, config)
                results.update(user_result)
                # Отслеживаем задействованные ноды
                nodes_with_users.update(self._get_user_nodes(user, config))

            # Перезагрузить сетевые конфигурации на задействованных нодах
            self._reload_affected_nodes_network(nodes_with_users)

            logger.info(f"Локальное развертывание завершено для {len(results)} пользователей")
            return results

        except Exception as e:
            logger.error(f"Ошибка локального развертывания: {e}")
            raise

    def _deploy_for_user(self, user: str, config: Dict[str, Any]) -> Dict[str, str]:
        """
        Развертывание для одного пользователя на локальной ноде

        Args:
            user: Имя пользователя
            config: Конфигурация развертывания

        Returns:
            Словарь {пользователь: пароль}
        """
        try:
            # Проверить, существует ли уже пользователь
            if self.user_manager.check_user_exists(user):
                logger.info(f"Пользователь {user} уже существует, пропускаем создание")
                # Получить существующий пароль или сгенерировать новый
                password = self.utils.generate_password()
            else:
                # Создать пользователя и пул через UserManager
                success, password = self.user_manager.create_user_and_pool(user)
                if not success:
                    raise Exception(f"Ошибка создания пользователя {user}")

            # Создать виртуальные машины через VMFactory
            pool_name = self.utils.extract_pool_name(user)
            for machine_config in config.get('machines', []):
                self.vm_factory.create_machine_local(machine_config, pool_name)

            logger.info(f"Локальное развертывание для пользователя {user} завершено")
            return {user: password}

        except Exception as e:
            logger.error(f"Ошибка локального развертывания для пользователя {user}: {e}")
            raise

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Валидация конфигурации развертывания

        Args:
            config: Конфигурация для валидации

        Returns:
            True если конфигурация валидна
        """
        validation_result = self.validator.validate_deployment_config(config)
        return validation_result.is_valid

    def _get_user_nodes(self, user: str, config: Dict[str, Any]) -> set:
        """
        Получить список нод, используемых пользователем

        Args:
            user: Имя пользователя
            config: Конфигурация развертывания

        Returns:
            Множество имен нод
        """
        nodes = set()
        for machine_config in config.get('machines', []):
            nodes.add(machine_config.get('template_node'))
        return nodes

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
        Получить статус локального развертывания

        Args:
            deployment_id: ID развертывания

        Returns:
            Словарь со статусом развертывания
        """
        return {
            'deployment_id': deployment_id,
            'status': 'completed',
            'strategy': 'local',
            'message': 'Локальное развертывание на ноде с шаблонами завершено'
        }
