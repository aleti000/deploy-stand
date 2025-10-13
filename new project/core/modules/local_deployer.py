#!/usr/bin/env python3
"""
Локальный модуль развертывания виртуальных машин для нового проекта

Развертывает виртуальные машины непосредственно на ноде,
где хранятся оригинальные шаблоны. Использует новую архитектуру менеджеров.
"""

import logging
from typing import Dict, List, Any

# Импорт менеджеров и утилит
from ..utils import Logger, ConfigValidator, VMManager, UserManager, PoolManager, NetworkManager, OtherUtils, ProxmoxClient

logger = logging.getLogger(__name__)


class LocalDeployer:
    """
    Локальный развертыватель виртуальных машин

    Использует специализированные менеджеры для каждой области ответственности
    """

    def __init__(self, host: str, user: str, password: str):
        """
        Инициализация локального развертывателя

        Args:
            host: Хост Proxmox
            user: Пользователь Proxmox
            password: Пароль пользователя
        """
        # Создаем Proxmox клиент для общего доступа
        self.proxmox_client = ProxmoxClient(host, user, password)

        # Инициализация менеджеров - каждый менеджер использует функции из своего модуля
        # В новом проекте функции перемещены в специализированные менеджеры
        self.vm_manager = VMManager(self.proxmox_client)
        self.user_manager = UserManager(self.proxmox_client)
        self.pool_manager = PoolManager(self.proxmox_client)
        self.network_manager = NetworkManager(self.proxmox_client)
        self.other_utils = OtherUtils(self.proxmox_client)

        # Валидатор с клиентом для расширенной валидации
        self.validator = ConfigValidator(self.proxmox_client)

    def deploy_configuration(self, users: List[str], config: Dict[str, Any]) -> Dict[str, str]:
        """
        Развернуть конфигурацию виртуальных машин на локальной ноде

        Args:
            users: Список пользователей для развертывания
            config: Конфигурация развертывания

        Returns:
            Словарь {пользователь: пароль}
        """
        logger.info(f"Начинается локальное развертывание для {len(users)} пользователей")

        # Валидация конфигурации через валидатор
        if not self.validator.validate_deployment_config(config):
            error_msg = "Ошибка валидации конфигурации"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # ПРЕДВАРИТЕЛЬНЫЙ ЭТАП: Глобальное сопоставление bridge для одинаковых alias
        self._prepare_global_bridge_mapping(config, users)

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
            logger.info(f"Развертывание для пользователя {user}")

            # Проверить, существует ли уже пользователь
            if self.user_manager.check_user_exists(user):
                logger.info(f"Пользователь {user} уже существует, пропускаем создание")
                # Получить существующий пароль или сгенерировать новый через UserManager
                password = self.user_manager._generate_password()
            else:
                # Создать пользователя и пул через UserManager
                success, password = self.user_manager.create_user_and_pool(user)
                if not success:
                    raise Exception(f"Ошибка создания пользователя {user}")

            # Получить имя пула
            pool_name = self.pool_manager.extract_pool_name(user)

            # Создать виртуальные машины через VMManager
            for machine_config in config.get('machines', []):
                self._create_machine_for_user(machine_config, pool_name, config.get('global_bridge_mapping'))

            logger.info(f"Локальное развертывание для пользователя {user} завершено")
            return {user: password}

        except Exception as e:
            logger.error(f"Ошибка локального развертывания для пользователя {user}: {e}")
            raise

    def _create_machine_for_user(self, machine_config: Dict[str, Any], pool_name: str, global_bridge_mapping: Dict[str, str] = None) -> None:
        """
        Создать виртуальную машину для пользователя

        Args:
            machine_config: Конфигурация машины
            pool_name: Имя пула пользователя
            global_bridge_mapping: Глобальное сопоставление bridge для всего стенда
        """
        try:
            # Получить параметры машины
            template_node = machine_config['template_node']
            template_vmid = machine_config['template_vmid']
            device_type = machine_config.get('device_type', 'linux')
            name = machine_config.get('name', f"vm-{template_vmid}-{pool_name}")
            full_clone = machine_config.get('full_clone', False)

            # Санитизация имени машины
            name = self._sanitize_machine_name(name)

            # Проверить, существует ли уже машина с таким именем в пуле
            if self._machine_exists_in_pool(name, pool_name):
                logger.info(f"Машина {name} уже существует в пуле {pool_name}, пропускаем создание")
                return

            # Получить следующий VMID
            new_vmid = self.vm_manager.get_next_vmid()

            # Клонировать виртуальную машину на той же ноде где шаблон
            task_id = self.vm_manager.clone_vm(
                template_node=template_node,
                template_vmid=template_vmid,
                target_node=template_node,  # Развертывание на той же ноде
                new_vmid=new_vmid,
                name=name,
                pool=pool_name,
                full_clone=full_clone
            )

            # Ожидать завершения клонирования
            if not self.other_utils.wait_for_task_completion(task_id, template_node):
                raise Exception(f"Ошибка клонирования VM {new_vmid}")

            # Настроить сеть если указана - использовать глобальное mapping или создать локальное
            networks = machine_config.get('networks', [])
            if networks:
                if global_bridge_mapping:
                    # Используем глобальное mapping для правильного распределения bridge по alias
                    self._configure_machine_network_with_global_mapping(new_vmid, template_node, networks, pool_name, device_type, global_bridge_mapping)
                else:
                    # Fallback к старому методу
                    self.network_manager.configure_machine_network(
                        new_vmid, template_node, networks, pool_name, device_type
                    )

            # Выдать права пользователю на созданную VM
            user = self.user_manager.build_user_name(pool_name)
            if not self.user_manager.grant_vm_permissions(user, template_node, new_vmid):
                logger.warning(f"Не удалось выдать права пользователю {user} на VM {new_vmid}")

            logger.info(f"Машина {name} (VMID: {new_vmid}) создана локально на ноде {template_node}")

        except Exception as e:
            logger.error(f"Ошибка создания локальной машины: {e}")
            raise

    def _machine_exists_in_pool(self, machine_name: str, pool_name: str) -> bool:
        """
        Проверить, существует ли машина с таким именем в пуле

        Args:
            machine_name: Имя машины
            pool_name: Имя пула

        Returns:
            True если машина существует
        """
        try:
            pool_vms = self.pool_manager.get_pool_vms(pool_name)
            for vm_info in pool_vms:
                if vm_info.get('name') == machine_name:
                    logger.info(f"Машина {machine_name} найдена в пуле {pool_name}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки существования машины {machine_name} в пуле {pool_name}: {e}")
            return False

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

        logger.info(f"🔄 Обновление сетевых конфигураций на {len(nodes)} нодах")

        for node in nodes:
            try:
                if self.network_manager.reload_network(node):
                    logger.info(f"  ✅ Сеть ноды {node} обновлена")
                else:
                    logger.warning(f"  ⚠️ Не удалось обновить сеть ноды {node}")
            except Exception as e:
                logger.error(f"  ❌ Ошибка обновления сети ноды {node}: {e}")

    def _prepare_global_bridge_mapping(self, config: Dict[str, Any], users: List[str]) -> None:
        """
        Подготовить глобальное сопоставление bridge для всего стенда

        Args:
            config: Конфигурация развертывания
            users: Список пользователей для развертывания
        """
        # Собираем все сети из всех машин для предвычисления mapping
        all_networks = []
        for machine_config in config.get('machines', []):
            all_networks.extend(machine_config.get('networks', []))

        # Определяем ноду из первой машины (предполагаем что все на одной ноде)
        node = None
        for machine_config in config.get('machines', []):
            node = machine_config.get('template_node')
            break

        if not node:
            logger.warning("Не удалось определить ноду для глобального bridge mapping")
            config['global_bridge_mapping'] = {}
            return

        # Создаем глобальный mapping с пулом первого пользователя (для определения
        # первого пользователя используем его пул для consistency)
        global_mapping = {}
        if all_networks and users:
            pool_name = self.pool_manager.extract_pool_name(users[0])  # Используем первый пул как базовый
            global_mapping = self.network_manager._prepare_bridges_auto(node, all_networks, pool_name)

        config['global_bridge_mapping'] = global_mapping
        logger.info(f"Глобальное bridge mapping подготовлено: {global_mapping}")

    def _configure_machine_network_with_global_mapping(self, vmid: int, node: str, networks: List[Dict[str, Any]],
                                                      pool: str, device_type: str, global_mapping: Dict[str, str]) -> None:
        """
        Настроить сеть машины используя глобальное mapping

        Args:
            vmid: VMID машины
            node: Нода размещения
            networks: Сетевая конфигурация
            pool: Пул пользователя
            device_type: Тип устройства
            global_mapping: Глобальное сопоставление bridge
        """
        # Используем глобальное mapping для подготовки конфигураций сетевых интерфейсов
        network_configs = self.network_manager._prepare_network_configs(networks, global_mapping, device_type)

        # Применяем сетевые настройки напрямую
        config_params = {}
        for net_id, net_config in network_configs.items():
            config_params[net_id] = net_config

        # Конфигурируем через Proxmox API
        try:
            self.proxmox_client.api.nodes(node).qemu(vmid).config.post(**config_params)
            logger.info(f"Сетевые настройки VM {vmid} применены через глобальное mapping")
        except Exception as e:
            logger.error(f"Ошибка применения сетевых настроек VM {vmid}: {e}")
            raise

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Валидация конфигурации развертывания

        Args:
            config: Конфигурация для валидации

        Returns:
            True если конфигурация валидна
        """
        return self.validator.validate_deployment_config(config)

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
            'message': 'Локальное развертывание на ноде с шаблонами завершено',
            'method': 'refactored'  # Указываем что используется новая архитектура
        }

    def _sanitize_machine_name(self, name: str) -> str:
        """
        Санитизировать имя машины

        Args:
            name: Исходное имя машины

        Returns:
            Санитизированное имя
        """
        import re

        # Разрешены буквы, цифры, дефис, подчеркивание, точка
        sanitized = re.sub(r'[^a-zA-Z0-9._-]', '_', name)

        # Ограничение длины
        if len(sanitized) > 64:
            sanitized = sanitized[:64]

        # Убедиться, что начинается с буквы или цифры
        if sanitized and not sanitized[0].isalnum():
            sanitized = 'vm_' + sanitized

        return sanitized
