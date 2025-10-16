#!/usr/bin/env python3
"""
Менеджер сети
Отвечает за настройку сетевых адаптеров, управление bridge'ами и сетевую конфигурацию
"""

import logging
from typing import Dict, List, Any, Optional
from .proxmox_client import ProxmoxClient

# Импорт для совместимости
try:
    from .validator import ConfigValidator
    from .logger import Logger
except ImportError:
    # Fallback для обратной совместимости
    ConfigValidator = None
    Logger = None

logger = logging.getLogger(__name__)


class NetworkManager:
    """Менеджер сети для всех сетевых операций в Proxmox"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация менеджера сети

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def configure_machine_network(self, vmid: int, node: str, networks: List[Dict[str, Any]],
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
        try:
            # Используем готовый bridge mapping из кэша пользователя
            user_key = f"{node}:{pool}"
            if hasattr(self, '_global_bridge_cache') and user_key in self._global_bridge_cache:
                bridge_mapping = self._global_bridge_cache[user_key].get('bridge_mapping', {})
                logger.info(f"Используем готовый bridge mapping для пользователя {pool}: {bridge_mapping}")
            else:
                # Fallback: создаем mapping заново
                logger.warning(f"Bridge mapping не найден в кэше для пользователя {pool}, создаем заново")
                bridge_mapping = self._prepare_bridges_auto(node, networks, pool)

            # Подготовить конфигурации интерфейсов
            network_configs = self._prepare_network_configs(networks, bridge_mapping, device_type)

            # Пакетная настройка всех интерфейсов
            config_params = {}
            for net_id, net_config in network_configs.items():
                config_params[net_id] = net_config

            self.proxmox.api.nodes(node).qemu(vmid).config.post(**config_params)
            logger.info(f"Сетевые настройки для VM {vmid} применены через NetworkManager")
            return True

        except Exception as e:
            logger.error(f"Ошибка настройки сети для VM {vmid}: {e}")
            return False

    def configure_network(self, node: str, vmid: int, network_config: str, net_id: str = "net0") -> bool:
        """
        Настроить сетевой интерфейс VM

        Args:
            node: Нода размещения VM
            vmid: VMID машины
            network_config: Конфигурация сети
            net_id: ID сетевого интерфейса

        Returns:
            True если настройка успешна
        """
        try:
            success = self.proxmox.configure_vm_network_interface(node, vmid, net_id, network_config)
            if success:
                logger.info(f"✅ Сетевая конфигурация {net_id} для VM {vmid} настроена")
            else:
                logger.error(f"Не удалось настроить сеть {net_id} для VM {vmid}")
            return success
        except Exception as e:
            logger.error(f"Ошибка настройки сети {net_id} для VM {vmid}: {e}")
            return False

    def get_network_info(self, node: str, vmid: int) -> Dict[str, Any]:
        """
        Получить информацию о сетевой конфигурации VM

        Args:
            node: Нода размещения VM
            vmid: VMID машины

        Returns:
            Информация о сети VM
        """
        try:
            # Используем VMManager для получения конфигурации VM
            from .vm_manager import VMManager
            vm_manager = VMManager(self.proxmox)
            vm_info = vm_manager.get_vm_info(node, vmid)

            network_info = {}

            if vm_info:
                # Извлечь сетевые интерфейсы (net0, net1, etc.)
                for key in vm_info:
                    if key.startswith('net'):
                        network_info[key] = vm_info[key]

            return network_info

        except Exception as e:
            logger.error(f"Ошибка получения сетевой информации VM {vmid}: {e}")
            return {}

    def reload_network(self, node: str) -> bool:
        """
        Перезагрузить сеть на ноде

        Args:
            node: Нода для перезагрузки сети

        Returns:
            True если перезагрузка успешна
        """
        try:
            # Реализуем reload сети в NetworkManager
            self.proxmox.api.nodes(node).network.put()
            logger.info(f"✅ Сеть ноды {node} перезагружена через NetworkManager")
            return True
        except Exception as e:
            logger.error(f"Ошибка перезагрузки сети ноды {node} в NetworkManager: {e}")
            return False

    def list_bridges(self, node: str) -> List[str]:
        """
        Получить список bridge'ов на ноде

        Args:
            node: Нода для проверки

        Returns:
            Список bridge'ов
        """
        try:
            # Реализуем через ProxmoxClient
            try:
                network_config = self.proxmox.api.nodes(node).network.get()
                bridges = []
                for iface in network_config:
                    if iface.get('type') == 'bridge':
                        bridges.append(iface.get('iface'))
                logger.debug(f"Найдено {len(bridges)} bridge'ов на ноде {node}")
                return bridges
            except Exception:
                # Fallback: использовать известные bridges по умолчанию
                return ['vmbr0']
        except Exception as e:
            logger.error(f"Ошибка получения списка bridge'ов на ноде {node}: {e}")
            return []

    def bridge_exists(self, node: str, bridge_name: str) -> bool:
        """
        Проверить существование bridge'а

        Args:
            node: Нода для проверки
            bridge_name: Имя bridge'а

        Returns:
            True если bridge существует
        """
        try:
            bridges = self.list_bridges(node)
            return bridge_name in bridges
        except Exception:
            return False

    def create_bridge(self, node: str, bridge_name: str) -> bool:
        """
        Создать bridge на ноде

        Args:
            node: Нода для создания bridge'а
            bridge_name: Имя bridge'а

        Returns:
            True если bridge создан успешно
        """
        try:
            # Реализуем создание bridge в NetworkManager
            bridge_config = {
                'iface': bridge_name,
                'type': 'bridge',
                'autostart': 1
            }

            self.proxmox.api.nodes(node).network.post(**bridge_config)
            logger.info(f"✅ Bridge {bridge_name} создан на ноде {node} через NetworkManager")
            return True
        except Exception as e:
            logger.error(f"Ошибка создания bridge {bridge_name} на ноде {node}: {e}")
            return False

    def delete_bridge(self, node: str, bridge_name: str) -> bool:
        """
        Удалить bridge с ноды

        Args:
            node: Нода для удаления bridge'а
            bridge_name: Имя bridge'а

        Returns:
            True если bridge удален успешно
        """
        try:
            success = self.proxmox..api.nodes(node).network(bridge_name).delete()
            if success:
                logger.info(f"✅ Bridge {bridge_name} удален с ноды {node}")
            else:
                logger.error(f"Не удалось удалить bridge {bridge_name} с ноды {node}")
            return success
        except Exception as e:
            logger.error(f"Ошибка удаления bridge {bridge_name} с ноды {node}: {e}")
            return False

    def bridge_in_use(self, node: str, bridge_name: str) -> bool:
        """
        Проверить, используется ли bridge

        Args:
            node: Нода для проверки
            bridge_name: Имя bridge'а

        Returns:
            True если bridge используется
        """
        try:
            # Получить список всех VM на ноде
            vms = self.proxmox.get_vms(node)

            for vm in vms:
                vm_info = self.get_network_info(node, vm.get('vmid'))
                for net_config in vm_info.values():
                    if bridge_name in net_config:
                        return True

            return False

        except Exception as e:
            logger.error(f"Ошибка проверки использования bridge {bridge_name} на ноде {node}: {e}")
            return False

    def _prepare_bridges_auto(self, node: str, networks: List[Dict[str, Any]], pool: str) -> Dict[str, str]:
        """
        Подготовить bridge'ы автоматически с учетом одинаковых alias и VLAN

        Args:
            node: Нода размещения
            networks: Конфигурация сетей
            pool: Пул пользователя

        Returns:
            Mapping bridge имен (одинаковые alias -> один и тот же bridge)
        """
        bridge_mapping = {}

        # Глобальный кэш для всех пользователей и их alias
        if not hasattr(self, '_global_bridge_cache'):
            self._global_bridge_cache = {}

        # Создаем уникальный ключ для пользователя
        user_key = f"{node}:{pool}"

        if user_key not in self._global_bridge_cache:
            self._global_bridge_cache[user_key] = {}

        user_bridge_cache = self._global_bridge_cache[user_key]

        # Сначала собираем все алиасы и проверяем, есть ли VLAN среди них
        alias_vlan_map = {}  # alias -> max_vlan_id (или None)

        for network in networks:
            bridge_name = network.get('bridge')
            if bridge_name and not bridge_name.startswith('**') and not bridge_name.startswith('vmbr') and not bridge_name.isdigit():
                alias, vlan_id = self._parse_bridge_name(bridge_name)
                if alias not in alias_vlan_map or (vlan_id and (not alias_vlan_map[alias] or vlan_id > alias_vlan_map[alias])):
                    alias_vlan_map[alias] = vlan_id

        # Обрабатываем каждую сеть
        for network in networks:
            bridge_name = network.get('bridge')
            if bridge_name:
                # Разбор имени bridge на alias и VLAN
                alias, vlan_id = self._parse_bridge_name(bridge_name)

                # Обработка зарезервированных bridge (в двойных звездочках)
                if bridge_name.startswith('**'):
                    actual_bridge = bridge_name.strip('*')
                    if not self.bridge_exists(node, actual_bridge):
                        logger.info(f"Создаем зарезервированный bridge {actual_bridge} на ноде {node}")
                        self.create_bridge(node, actual_bridge)
                    bridge_mapping[bridge_name] = actual_bridge
                elif bridge_name.startswith('vmbr') or bridge_name.isdigit():
                    # Уже готовый bridge
                    if not self.bridge_exists(node, bridge_name):
                        logger.info(f"Автоматически создаем bridge {bridge_name} на ноде {node}")
                        self.create_bridge(node, bridge_name)
                    bridge_mapping[bridge_name] = bridge_name
                else:
                    # Это alias - должен быть одинаковым для пользователя
                    # Проверяем, должен ли bridge быть VLAN-aware (если хотя бы один алиас имеет VLAN)
                    should_be_vlan_aware = alias_vlan_map.get(alias, False)

                    cache_key = alias  # Используем только alias как ключ кэша

                    if cache_key not in user_bridge_cache:
                        # Выделяем новый bridge для этого alias пользователя
                        allocated_bridge = self._allocate_bridge_auto(node, alias, pool)

                        if not self.bridge_exists(node, allocated_bridge):
                            if should_be_vlan_aware:
                                logger.info(f"Автоматически создаем VLAN-aware bridge {allocated_bridge} для alias '{alias}' пользователя {pool} на ноде {node} (требуется VLAN)")
                                self.create_vlan_bridge(node, allocated_bridge, alias, alias_vlan_map.get(alias))
                            else:
                                logger.info(f"Автоматически создаем bridge {allocated_bridge} для alias '{alias}' пользователя {pool} на ноде {node}")
                                self.create_bridge(node, allocated_bridge)
                        else:
                            logger.info(f"Используем существующий bridge {allocated_bridge} для alias '{alias}' пользователя {pool}")

                        user_bridge_cache[cache_key] = allocated_bridge
                        logger.info(f"Пользователь {pool}: alias '{alias}' -> bridge '{allocated_bridge}' (сохранено в кэш)")

                    # Используем bridge из кэша пользователя (одинаковый для одинаковых alias)
                    bridge_mapping[bridge_name] = user_bridge_cache[cache_key]

        return bridge_mapping

    def _allocate_bridge_auto(self, node: str, bridge_name: str, pool: str) -> str:
        """
        Автоматическое выделение свободного bridge начиная с vmbr1000

        Args:
            node: Нода размещения
            bridge_name: ALIAS bridge'а (hq, inet, etc)
            pool: Пул пользователя (используется для определения области)

        Returns:
            Имя свободного bridge'а
        """
        bridge_alias = bridge_name.lower()

        # Определяем базовый номер для разных типов сетей
        if bridge_alias == 'hq':
            base_bridge = 1000
        elif bridge_alias == 'inet':
            base_bridge = 2000
        else:
            base_bridge = 9000

        # Ищем свободный bridge начиная с base_bridge
        bridge_number = base_bridge
        while True:
            candidate_bridge = f'vmbr{bridge_number:04d}'
            if not self.bridge_exists(node, candidate_bridge):
                logger.info(f"Найден свободный bridge {candidate_bridge} для alias '{bridge_name}'")
                return candidate_bridge
            bridge_number += 1

            # Защита от бесконечного цикла (максимум 100 попыток)
            if bridge_number > base_bridge + 100:
                logger.warning(f"Не удалось найти свободный bridge для {bridge_name}, используем fallback")
                return f'vmbr{base_bridge:04d}'

    def _allocate_bridge(self, node: str, bridge_name: str, pool: str) -> str:
        """
        Выделить bridge для сети (упрощенная версия без BridgeManager)

        Args:
            node: Нода размещения
            bridge_name: ALIAS bridge'а (hq, inet, etc)
            pool: Пул пользователя

        Returns:
            Имя выделенного bridge'а
        """
        # Для простоты - используем фиксированную схему именования
        # В будущем можно добавить BridgeManager для более сложной логики
        pool_suffix = pool[:4]  # Первые 4 символа пула
        bridge_alias = bridge_name.lower()

        if bridge_alias == 'hq':
            return f'vmbr100{pool_suffix}'
        elif bridge_alias == 'inet':
            return f'vmbr200{pool_suffix}'
        else:
            # Для неизвестных alias - использовать общий bridge
            return f'vmbr999{pool_suffix}'

    def _parse_bridge_name(self, bridge_name: str) -> tuple:
        """
        Разбор имени bridge на alias и VLAN ID

        Args:
            bridge_name: Имя bridge в формате 'alias' или 'alias.vlan_id'

        Returns:
            Кортеж (alias, vlan_id), где vlan_id может быть None
        """
        if '.' in bridge_name:
            parts = bridge_name.split('.')
            if len(parts) == 2:
                alias, vlan_str = parts
                try:
                    vlan_id = int(vlan_str)
                    return alias, vlan_id
                except ValueError:
                    # Если не число после точки, считаем что это часть имени
                    pass
        return bridge_name, None

    def create_vlan_bridge(self, node: str, bridge_name: str, alias: str, vlan_id: Optional[int] = None) -> bool:
        """
        Создать VLAN-aware bridge

        Args:
            node: Нода для создания bridge'а
            bridge_name: Имя bridge'а
            alias: Alias сети
            vlan_id: ID VLAN (может быть None)

        Returns:
            True если bridge создан успешно
        """
        try:
            # Базовая конфигурация bridge
            bridge_config = {
                'iface': bridge_name,
                'type': 'bridge',
                'bridge_vlan_aware': 'True',
                'autostart': 1,
                'node' : node
            }

            # Создаем bridge
            self.proxmox.api.nodes(node).network.post(**bridge_config)

            if vlan_id is not None:
                logger.info(f"✅ VLAN-aware bridge {bridge_name} создан для alias '{alias}' с VLAN {vlan_id} на ноде {node}")
            else:
                logger.info(f"✅ VLAN-aware bridge {bridge_name} создан для alias '{alias}' на ноде {node}")

            return True
        except Exception as e:
            logger.error(f"Ошибка создания VLAN-aware bridge {bridge_name} на ноде {node}: {e}")
            return False

    def _prepare_network_configs(self, networks: List[Dict[str, Any]], bridge_mapping: Dict[str, str],
                               device_type: str) -> Dict[str, str]:
        """
        Подготовить конфигурации сетевых интерфейсов с поддержкой VLAN

        Args:
            networks: Конфигурация сетей
            bridge_mapping: Mapping bridge имен
            device_type: Тип устройства

        Returns:
            Словарь конфигураций интерфейсов
        """
        network_configs = {}

        if device_type.lower() == 'ecorouter':
            # Специальная конфигурация для ecorouter
            network_configs['net0'] = 'model=vmxnet3,bridge=vmbr0,link_down=1'
            for i, network in enumerate(networks):
                bridge = bridge_mapping.get(network['bridge'])
                if not bridge:
                    continue
                net_id = f"net{i+2}"  # net2, net3, net4...
                network_configs[net_id] = f'model=vmxnet3,bridge={bridge}'

        else:
            # Стандартная конфигурация для Linux с поддержкой VLAN
            for i, network in enumerate(networks):
                bridge_name = network.get('bridge', '')
                bridge = bridge_mapping.get(bridge_name, 'vmbr0')

                # Разбор имени bridge для определения VLAN
                alias, vlan_id = self._parse_bridge_name(bridge_name)

                net_id = f"net{i}"  # net0, net1, net2...

                if vlan_id is not None:
                    # VLAN интерфейс - добавляем tag
                    network_configs[net_id] = f'model=virtio,bridge={bridge},tag={vlan_id},firewall=1'
                    logger.info(f"Настраиваем VLAN интерфейс {net_id} для VM: bridge={bridge}, tag={vlan_id}")
                else:
                    # Обычный интерфейс
                    network_configs[net_id] = f'model=virtio,bridge={bridge},firewall=1'

        return network_configs

    def validate_network_config(self, networks: List[Dict[str, Any]], node: str) -> Dict[str, Any]:
        """
        Валидация сетевой конфигурации

        Args:
            networks: Конфигурация сетей
            node: Нода для проверки

        Returns:
            Результат валидации
        """
        result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'bridge_availability': {}
        }

        if not isinstance(networks, list):
            result['is_valid'] = False
            result['errors'].append("Конфигурация сетей должна быть списком")
            return result

    def get_user_bridges(self, pool_name: str, nodes: List[str]) -> List[tuple]:
        """
        Получить список bridge'ов, созданных для пользователя

        Args:
            pool_name: Имя пула пользователя
            nodes: Список нод для проверки

        Returns:
            Список кортежей (node, bridge_name)
        """
        user_bridges = []

        try:
            # Определяем возможные bridge'ы пользователя по схеме именования
            # Берем первые 4 символа пула для идентификации
            pool_prefix = pool_name[:4] if len(pool_name) >= 4 else pool_name

            logger.info(f"Поиск bridge'ов для пула {pool_name} с префиксом '{pool_prefix}' на нодах {nodes}")

            # Стандартные диапазоны для разных типов сетей
            bridge_ranges = [
                (1000, 1999, 'hq'),      # Диапазон для HQ сетей
                (2000, 2999, 'inet'),    # Диапазон для INET сетей
                (9000, 9999, 'other')    # Диапазон для других сетей
            ]

            for start_range, end_range, bridge_type in bridge_ranges:
                for bridge_num in range(start_range, end_range + 1):
                    bridge_name = f'vmbr{bridge_num:04d}'

                    # Проверяем, содержит ли bridge имя пула
                    if pool_prefix.lower() in bridge_name.lower():
                        logger.debug(f"Проверка bridge {bridge_name} для пула {pool_name}")
                        # Проверяем на всех указанных нодах
                        for node in nodes:
                            if self.bridge_exists(node, bridge_name):
                                user_bridges.append((node, bridge_name))
                                logger.info(f"Найден пользовательский bridge {bridge_name} на ноде {node} для пула {pool_name}")

            logger.info(f"Найдено {len(user_bridges)} пользовательских bridge'ов для пула {pool_name}: {[b[1] for b in user_bridges]}")
            return user_bridges

        except Exception as e:
            logger.error(f"Ошибка получения пользовательских bridge'ов для пула {pool_name}: {e}")
            return []

    def get_all_bridges_in_ranges(self, nodes: List[str]) -> List[tuple]:
        """
        Получить список всех bridge'ов в пользовательских диапазонах

        Args:
            nodes: Список нод для проверки

        Returns:
            Список кортежей (node, bridge_name)
        """
        all_bridges = []

        try:
            # Стандартные диапазоны для пользовательских сетей
            bridge_ranges = [
                (1000, 1999, 'hq'),      # Диапазон для HQ сетей
                (2000, 2999, 'inet'),    # Диапазон для INET сетей
                (9000, 9999, 'other')    # Диапазон для других сетей
            ]

            for start_range, end_range, bridge_type in bridge_ranges:
                for bridge_num in range(start_range, end_range + 1):
                    bridge_name = f'vmbr{bridge_num:04d}'

                    # Проверяем на всех указанных нодах
                    for node in nodes:
                        if self.bridge_exists(node, bridge_name):
                            all_bridges.append((node, bridge_name))

            logger.info(f"Найдено {len(all_bridges)} bridge'ов в пользовательских диапазонах на нодах {nodes}")
            return all_bridges

        except Exception as e:
            logger.error(f"Ошибка получения всех bridge'ов в пользовательских диапазонах: {e}")
            return []

    def get_bridges_used_by_pool_vms(self, pool_name: str, nodes: List[str]) -> List[tuple]:
        """
        Получить список bridge'ов, используемых VM в пуле пользователя

        Args:
            pool_name: Имя пула пользователя
            nodes: Список нод для проверки

        Returns:
            Список кортежей (node, bridge_name)
        """
        used_bridges = []

        try:
            # Получить все VM в пуле через PoolManager
            from .pool_manager import PoolManager
            pool_manager = PoolManager(self.proxmox)

            pool_vms = pool_manager.get_pool_vms(pool_name)

            for vm_info in pool_vms:
                node = vm_info.get('node')
                vmid = vm_info.get('vmid')

                if node and vmid:
                    # Получить сетевые интерфейсы VM
                    network_info = self.get_network_info(node, vmid)

                    for net_config in network_info.values():
                        # Извлечь имя bridge из конфигурации сети
                        if isinstance(net_config, str) and 'bridge=' in net_config:
                            bridge_name = net_config.split('bridge=')[1].split(',')[0]
                            if bridge_name not in ['vmbr0']:  # Исключаем системные bridge'ы
                                used_bridges.append((node, bridge_name))

            # Удалить дубликаты
            unique_bridges = list(set(used_bridges))
            logger.info(f"Найдено {len(unique_bridges)} bridge'ов, используемых VM пула {pool_name}")
            return unique_bridges

        except Exception as e:
            logger.error(f"Ошибка получения bridge'ов, используемых VM пула {pool_name}: {e}")
            return []

    def cleanup_unused_user_bridges(self, pool_name: str, nodes: List[str]) -> bool:
        """
        Удалить неиспользуемые bridge'ы пользователя

        Args:
            pool_name: Имя пула пользователя
            nodes: Список нод для очистки

        Returns:
            True если очистка успешна
        """
        try:
            logger.info(f"Начинаем очистку неиспользуемых bridge'ов пользователя {pool_name}")

            # Получить bridge'ы, используемые VM пользователя
            used_bridges = self.get_bridges_used_by_pool_vms(pool_name, nodes)

            # Получить все пользовательские bridge'ы (по префиксу пула)
            user_bridges = self.get_user_bridges(pool_name, nodes)

            # Получить все bridge'ы в пользовательских диапазонах (альтернативный поиск)
            all_user_range_bridges = self.get_all_bridges_in_ranges(nodes)

            logger.info(f"Найдено {len(used_bridges)} используемых bridge'ов, {len(user_bridges)} пользовательских bridge'ов, {len(all_user_range_bridges)} bridge'ов в пользовательских диапазонах")

            # Определить bridge'ы для удаления
            unused_bridges = []
            used_bridge_names = {bridge_name for _, bridge_name in used_bridges}

            # Проверяем пользовательские bridge'ы
            for node, bridge_name in user_bridges:
                if bridge_name not in used_bridge_names and not self.bridge_in_use(node, bridge_name):
                    unused_bridges.append((node, bridge_name))
                    logger.info(f"Найден неиспользуемый пользовательский bridge {bridge_name} на ноде {node}")

            # Дополнительно проверяем все bridge'ы в пользовательских диапазонах
            for node, bridge_name in all_user_range_bridges:
                if bridge_name not in used_bridge_names and not self.bridge_in_use(node, bridge_name):
                    # Проверяем, что этот bridge не принадлежит другим активным пулам
                    if not self._bridge_belongs_to_other_active_pools(node, bridge_name, pool_name):
                        unused_bridges.append((node, bridge_name))
                        logger.info(f"Найден неиспользуемый bridge {bridge_name} в пользовательском диапазоне на ноде {node}")

            # Удалить неиспользуемые bridge'ы
            deleted_count = 0
            for node, bridge_name in unused_bridges:
                if self.delete_bridge(node, bridge_name):
                    logger.info(f"✅ Удален неиспользуемый bridge {bridge_name} с ноды {node}")
                    deleted_count += 1
                else:
                    logger.error(f"❌ Не удалось удалить bridge {bridge_name} с ноды {node}")

            logger.info(f"✅ Удалено {deleted_count}/{len(unused_bridges)} неиспользуемых bridge'ов пользователя {pool_name}")
            return True

        except Exception as e:
            logger.error(f"Ошибка очистки неиспользуемых bridge'ов пользователя {pool_name}: {e}")
            return False

    def _bridge_belongs_to_other_active_pools(self, node: str, bridge_name: str, exclude_pool: str) -> bool:
        """
        Проверить, принадлежит ли bridge другим активным пулам

        Args:
            node: Нода для проверки
            bridge_name: Имя bridge'а
            exclude_pool: Пул, который исключаем из проверки

        Returns:
            True если bridge принадлежит другим активным пулам
        """
        try:
            # Получить все пулы
            from .pool_manager import PoolManager
            pool_manager = PoolManager(self.proxmox)
            all_pools = pool_manager.list_pools()

            for pool_name in all_pools:
                if pool_name == exclude_pool:
                    continue

                # Проверить, содержит ли bridge префикс этого пула
                pool_prefix = pool_name[:4] if len(pool_name) >= 4 else pool_name
                if pool_prefix.lower() in bridge_name.lower():
                    # Проверить, есть ли VM в этом пуле
                    pool_vms = pool_manager.get_pool_vms(pool_name)
                    if pool_vms:
                        logger.debug(f"Bridge {bridge_name} принадлежит активному пулу {pool_name}")
                        return True

            return False

        except Exception as e:
            logger.error(f"Ошибка проверки принадлежности bridge {bridge_name} другим пулам: {e}")
            return True  # В случае ошибки считаем, что bridge используется

    def cleanup_user_bridges_and_reload_network(self, pool_name: str, nodes: List[str]) -> bool:
        """
        Удалить неиспользуемые bridge'ы пользователя и перезагрузить сеть

        Args:
            pool_name: Имя пула пользователя
            nodes: Список нод для очистки

        Returns:
            True если очистка успешна
        """
        try:
            logger.info(f"Начинаем полную очистку bridge'ов пользователя {pool_name} и перезагрузку сети")

            # ШАГ 1: Очистить неиспользуемые bridge'ы пользователя
            if not self.cleanup_unused_user_bridges(pool_name, nodes):
                logger.error(f"Не удалось очистить неиспользуемые bridge'ы пользователя {pool_name}")
                return False

            # ШАГ 2: Перезагрузить сеть на всех нодах
            reloaded_nodes = 0
            for node in nodes:
                if self.reload_network(node):
                    logger.info(f"Сеть на ноде {node} перезагружена")
                    reloaded_nodes += 1
                else:
                    logger.error(f"Не удалось перезагрузить сеть на ноде {node}")

            logger.info(f"Перезагружено сетей на нодах: {reloaded_nodes}/{len(nodes)}")
            return True

        except Exception as e:
            logger.error(f"Ошибка полной очистки bridge'ов пользователя {pool_name}: {e}")
            return False

        for i, network in enumerate(networks):
            if not isinstance(network, dict):
                result['is_valid'] = False
                result['errors'].append(f"Сеть {i}: должна быть объектом")
                continue

            bridge = network.get('bridge')
            if not bridge:
                result['is_valid'] = False
                result['errors'].append(f"Сеть {i}: отсутствует поле 'bridge'")
                continue

            # Проверить доступность bridge'а на ноде
            exists = self.bridge_exists(node, bridge)
            result['bridge_availability'][bridge] = exists

            if not exists and not bridge.startswith('**'):
                result['warnings'].append(f"Bridge '{bridge}' не существует на ноде {node}")

        return result
