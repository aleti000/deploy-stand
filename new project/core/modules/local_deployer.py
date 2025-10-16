#!/usr/bin/env python3
"""
Локальный модуль развертывания виртуальных машин для нового проекта

Упрощенная версия без избыточных зависимостей.
"""

import logging
from typing import Dict, List, Any

# Минимальные необходимые импорты
from ..utils.proxmox_client import ProxmoxClient
from ..utils.vm_manager import VMManager
from ..utils.user_manager import UserManager
from ..utils.pool_manager import PoolManager

logger = logging.getLogger(__name__)


class LocalDeployer:
    """
    Упрощенный локальный развертыватель виртуальных машин
    """

    def __init__(self, host: str, user: str, password: str):
        """
        Инициализация локального развертывателя

        Args:
            host: Хост Proxmox
            user: Пользователь Proxmox
            password: Пароль пользователя
        """
        self.proxmox_client = ProxmoxClient(host, user, password)
        self.vm_manager = VMManager(self.proxmox_client)
        self.user_manager = UserManager(self.proxmox_client)
        self.pool_manager = PoolManager(self.proxmox_client)

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

        # Базовая валидация конфигурации
        if not self._validate_config(config):
            raise ValueError("Ошибка валидации конфигурации")

        results = {}

        try:
            # Развернуть для каждого пользователя
            for user in users:
                user_result = self._deploy_for_user(user, config)
                results.update(user_result)

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
        logger.info(f"Развертывание для пользователя {user}")

        # Создать пользователя
        password = self.user_manager._generate_password()
        if not self.user_manager.create_user(user, password):
            raise Exception(f"Ошибка создания пользователя {user}")

        # Получить имя пула
        pool_name = self.pool_manager.extract_pool_name(user)

        # Создать пул для пользователя
        if not self.pool_manager.create_pool(pool_name, f"Pool for {user}"):
            raise Exception(f"Ошибка создания пула {pool_name}")

        # Установить права пользователя на пул
        if not self.pool_manager.set_pool_permissions(user, pool_name, ["PVEVMAdmin"]):
            raise Exception(f"Ошибка установки прав для пользователя {user} на пул {pool_name}")

        # СОЗДАЕМ ВСЕ МАШИНЫ ПЕРВЫМИ (без сети)
        created_vms = []
        for machine_config in config.get('machines', []):
            vm_info = self._create_machine_for_user(machine_config, pool_name, user, create_network=False)
            created_vms.append((vm_info, machine_config))

        # СОЗДАЕМ НЕОБХОДИМЫЕ BRIDGE'Ы
        bridge_mapping = self._create_user_bridges(user, pool_name, config)

        # НАСТРАИВАЕМ СЕТЬ ДЛЯ ВСЕХ СОЗДАННЫХ VM
        for vm_info, machine_config in created_vms:
            vmid, node = vm_info
            networks = machine_config.get('networks', [])
            if networks:
                self._configure_vm_network_with_mapping(vmid, node, networks, bridge_mapping)

        # ПЕРЕЗАГРУЖАЕМ СЕТЬ ПОСЛЕ РАЗВЕРТЫВАНИЯ
        self._reload_network_after_deployment(user, config)

        logger.info(f"Локальное развертывание для пользователя {user} завершено")
        return {user: password}

    def _reload_network_after_deployment(self, user: str, config: Dict[str, Any]) -> None:
        """Перезагрузить сеть после развертывания"""
        try:
            # Определяем ноды для перезагрузки
            nodes = set()
            for machine_config in config.get('machines', []):
                node = machine_config.get('template_node')
                if node:
                    nodes.add(node)

            for node in nodes:
                logger.info(f"Перезагружаем сеть на ноде {node} после развертывания")
                try:
                    from ..utils.network_manager import NetworkManager
                    network_manager = NetworkManager(self.proxmox_client)
                    if network_manager.reload_network(node):
                        logger.info(f"✅ Сеть ноды {node} перезагружена после развертывания")
                    else:
                        logger.warning(f"Не удалось перезагрузить сеть ноды {node}")
                except Exception as e:
                    logger.error(f"Ошибка перезагрузки сети ноды {node}: {e}")

        except Exception as e:
            self.logger.error(f"Ошибка перезагрузки сети после развертывания пользователя {user}: {e}")

    def _create_user_bridges(self, user: str, pool_name: str, config: Dict[str, Any]) -> Dict[str, str]:
        """
        Создать необходимые bridge'ы для пользователя с поддержкой VLAN

        Args:
            user: Имя пользователя
            pool_name: Имя пула пользователя
            config: Конфигурация развертывания

        Returns:
            Mapping bridge имен
        """
        from ..utils.network_manager import NetworkManager
        network_manager = NetworkManager(self.proxmox_client)

        # Определяем ноду
        node = config.get('machines', [{}])[0].get('template_node', 'srv1')

        # Собираем все уникальные сети из всех машин
        all_networks = []
        for machine_config in config.get('machines', []):
            all_networks.extend(machine_config.get('networks', []))

        # Используем NetworkManager для подготовки bridge mapping
        # Передаем все сети для анализа и создания необходимых bridge'ей
        bridge_mapping = network_manager._prepare_bridges_auto(node, all_networks, pool_name)

        logger.info(f"Пользователь {user}: создан bridge mapping: {bridge_mapping}")
        return bridge_mapping

    def _allocate_bridge_for_alias(self, node: str, alias: str, pool_name: str, network_manager) -> str:
        """
        Выделить bridge для alias

        Args:
            node: Нода размещения
            alias: Alias bridge'а
            pool_name: Пул пользователя
            network_manager: Экземпляр NetworkManager

        Returns:
            Имя выделенного bridge'а
        """
        # Определяем базовый номер для разных типов сетей
        alias_lower = alias.lower()
        if alias_lower == 'hq':
            base_bridge = 1000
        elif alias_lower == 'inet':
            base_bridge = 2000
        else:
            base_bridge = 9000

        # Ищем свободный bridge начиная с base_bridge
        bridge_number = base_bridge
        while True:
            candidate_bridge = f'vmbr{bridge_number:04d}'
            if not network_manager.bridge_exists(node, candidate_bridge):
                # Создаем bridge
                network_manager.create_bridge(node, candidate_bridge)
                logger.info(f"Создан bridge {candidate_bridge} для alias '{alias}' на ноде {node}")
                return candidate_bridge
            bridge_number += 1

            # Защита от бесконечного цикла
            if bridge_number > base_bridge + 100:
                logger.warning(f"Не удалось найти свободный bridge для {alias}, используем fallback")
                return f'vmbr{base_bridge:04d}'

    def _create_machine_for_user(self, machine_config: Dict[str, Any], pool_name: str, user: str, create_network: bool = True) -> tuple:
        """
        Создать виртуальную машину для пользователя

        Args:
            machine_config: Конфигурация машины
            pool_name: Имя пула пользователя
            user: Имя пользователя
            create_network: Создавать сеть сразу или позже

        Returns:
            Кортеж (vmid, node)
        """
        # Получить параметры машины
        template_node = machine_config['template_node']
        template_vmid = machine_config['template_vmid']
        name = machine_config.get('name', f"vm-{template_vmid}-{pool_name}")
        full_clone = machine_config.get('full_clone', False)

        # Санитизация имени машины
        name = self._sanitize_machine_name(name)

        # Получить следующий VMID
        new_vmid = self.vm_manager.get_next_vmid()

        # Клонировать виртуальную машину
        task_id = self.vm_manager.clone_vm(
            template_node=template_node,
            template_vmid=template_vmid,
            target_node=template_node,
            new_vmid=new_vmid,
            name=name,
            pool=pool_name,
            full_clone=full_clone
        )

        # Ожидать завершения клонирования
        if not self._wait_for_task_completion(task_id, template_node):
            raise Exception(f"Ошибка клонирования VM {new_vmid}")

        # Настроить сеть если указана и если нужно создавать сразу
        if create_network:
            networks = machine_config.get('networks', [])
            if networks:
                self._configure_machine_network(new_vmid, template_node, networks, pool_name, user)

        # Выдать права пользователю на созданную VM
        user_full = self.user_manager.build_user_name(pool_name)
        if not self.user_manager.grant_vm_permissions(user_full, template_node, new_vmid):
            logger.warning(f"Не удалось выдать права пользователю {user_full} на VM {new_vmid}")

        logger.info(f"Машина {name} (VMID: {new_vmid}) создана локально на ноде {template_node}")
        return (new_vmid, template_node)

    def _configure_vm_network_with_mapping(self, vmid: int, node: str, networks: List[Dict[str, Any]],
                                          bridge_mapping: Dict[str, str]) -> None:
        """
        Настроить сеть VM используя готовый bridge mapping

        Args:
            vmid: VMID машины
            node: Нода размещения
            networks: Сетевая конфигурация
            bridge_mapping: Готовый mapping alias -> bridge
        """
        try:
            from ..utils.network_manager import NetworkManager
            network_manager = NetworkManager(self.proxmox_client)

            # Подготовить конфигурации интерфейсов с готовым mapping
            network_configs = self._prepare_network_configs_with_mapping(networks, bridge_mapping)

            # Пакетная настройка всех интерфейсов
            config_params = {}
            for net_id, net_config in network_configs.items():
                config_params[net_id] = net_config

            self.proxmox_client.api.nodes(node).qemu(vmid).config.post(**config_params)
            logger.info(f"Сеть VM {vmid} настроена с bridge mapping: {bridge_mapping}")

        except Exception as e:
            logger.error(f"Ошибка настройки сети VM {vmid}: {e}")
            raise

    def _prepare_network_configs_with_mapping(self, networks: List[Dict[str, Any]], bridge_mapping: Dict[str, str]) -> Dict[str, str]:
        """
        Подготовить конфигурации сетевых интерфейсов с готовым mapping и поддержкой VLAN

        Args:
            networks: Конфигурация сетей
            bridge_mapping: Готовый mapping alias -> bridge

        Returns:
            Словарь конфигураций интерфейсов
        """
        from ..utils.network_manager import NetworkManager

        # Создаем временный экземпляр NetworkManager для разбора имен bridge
        temp_network_manager = NetworkManager(self.proxmox_client)

        network_configs = {}

        for i, network in enumerate(networks):
            bridge_name = network.get('bridge')

            # Определяем реальный bridge
            if bridge_name.startswith('**'):
                # Зарезервированный bridge
                actual_bridge = bridge_name.strip('*')
            elif bridge_name.startswith('vmbr') or bridge_name.isdigit():
                # Готовый bridge
                actual_bridge = bridge_name
            else:
                # Alias - используем из mapping
                actual_bridge = bridge_mapping.get(bridge_name, 'vmbr0')

            net_id = f"net{i}"

            # Разбор имени bridge для определения VLAN
            alias, vlan_id = temp_network_manager._parse_bridge_name(bridge_name)

            if vlan_id is not None:
                # VLAN интерфейс - добавляем tag
                network_configs[net_id] = f'model=virtio,bridge={actual_bridge},tag={vlan_id},firewall=1'
                logger.info(f"Настраиваем VLAN интерфейс {net_id} для VM: bridge={actual_bridge}, tag={vlan_id}")
            else:
                # Обычный интерфейс
                network_configs[net_id] = f'model=virtio,bridge={actual_bridge},firewall=1'

        return network_configs

    def _configure_machine_network(self, vmid: int, node: str, networks: List[Dict[str, Any]],
                                  pool: str, user: str) -> None:
        """
        Настроить сеть машины используя NetworkManager

        Args:
            vmid: VMID машины
            node: Нода размещения
            networks: Сетевая конфигурация
            pool: Пул пользователя
            user: Имя пользователя
        """
        try:
            from ..utils.network_manager import NetworkManager
            network_manager = NetworkManager(self.proxmox_client)

            device_type = 'linux'  # По умолчанию
            success = network_manager.configure_machine_network(vmid, node, networks, pool, device_type)

            if success:
                logger.info(f"Сеть VM {vmid} настроена через NetworkManager")
            else:
                logger.error(f"Не удалось настроить сеть VM {vmid}")

        except Exception as e:
            logger.error(f"Ошибка настройки сети VM {vmid}: {e}")
            raise

    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Базовая валидация конфигурации

        Args:
            config: Конфигурация для валидации

        Returns:
            True если конфигурация валидна
        """
        if not isinstance(config, dict):
            return False

        machines = config.get('machines', [])
        if not isinstance(machines, list):
            return False

        for machine in machines:
            if not isinstance(machine, dict):
                return False
            if 'template_node' not in machine or 'template_vmid' not in machine:
                return False

        return True

    def _wait_for_task_completion(self, task_id: str, node: str) -> bool:
        """
        Ожидать завершения задачи Proxmox

        Args:
            task_id: ID задачи
            node: Нода выполнения задачи

        Returns:
            True если задача завершилась успешно
        """
        import time

        for _ in range(30):  # 5 минут максимум
            try:
                task_status = self.proxmox_client.api.nodes(node).tasks(task_id).status.get()
                status = task_status.get('status')

                if status == 'stopped':
                    return task_status.get('exitstatus', 'OK') == 'OK'
                elif status == 'running':
                    time.sleep(10)
                    continue
                else:
                    return False
            except Exception:
                time.sleep(10)

        return False

    def _sanitize_machine_name(self, name: str) -> str:
        """
        Санитизировать имя машины

        Args:
            name: Исходное имя машины

        Returns:
            Санитизированное имя
        """
        import re

        # Разрешены буквы, цифры, дефис, подчеркивание
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)

        # Ограничение длины
        if len(sanitized) > 64:
            sanitized = sanitized[:64]

        # Убедиться, что начинается с буквы или цифры
        if sanitized and not sanitized[0].isalnum():
            sanitized = 'vm_' + sanitized

        return sanitized
