#!/usr/bin/env python3
"""
BridgeManager - менеджер bridge'ей для newest_project

Управляет созданием, настройкой и удалением сетевых bridge'ей в Proxmox VE.
Интегрирует Logger, Validator, Cache для надежной работы с сетевыми интерфейсами.
"""

import re
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass

from ..utils.logger import Logger
from ..utils.validator import Validator
from ..utils.cache import Cache
from .proxmox_client import ProxmoxClient


@dataclass
class BridgeConfig:
    """Конфигурация сетевого bridge"""
    name: str
    type: str = "bridge"
    vlan_aware: bool = False
    autostart: bool = True
    ports: List[str] = None
    vlan_filtering: bool = False

    def __post_init__(self):
        if self.ports is None:
            self.ports = []


@dataclass
class BridgeInfo:
    """Информация о существующем bridge"""
    name: str
    type: str
    active: bool
    vlan_aware: bool
    ports: List[str]
    autostart: bool


class BridgeManager:
    """
    Менеджер сетевых bridge'ей

    Возможности:
    - Создание и удаление bridge'ей
    - Настройка VLAN-aware bridge'ей
    - Управление портами bridge'ей
    - Мониторинг состояния bridge'ей
    - Кеширование информации о bridge'ах
    """

    def __init__(self, proxmox_client: ProxmoxClient,
                 logger: Optional[Logger] = None,
                 validator: Optional[Validator] = None,
                 cache: Optional[Cache] = None):
        """
        Инициализация менеджера bridge'ей

        Args:
            proxmox_client: Клиент Proxmox API
            logger: Экземпляр логгера
            validator: Экземпляр валидатора
            cache: Экземпляр кеша
        """
        self.proxmox = proxmox_client
        self.logger = logger or Logger()
        self.validator = validator or Validator()
        self.cache = cache or Cache()

        # Кеш для информации о bridge'ах
        self.bridge_cache_ttl = 300  # 5 минут

    def create_bridge(self, node: str, bridge_config: BridgeConfig) -> bool:
        """
        Создание сетевого bridge

        Args:
            node: Имя ноды
            bridge_config: Конфигурация bridge

        Returns:
            True если bridge успешно создан
        """
        try:
            # Валидация имени bridge
            if not self._validate_bridge_name(bridge_config.name):
                self.logger.log_validation_error("bridge_name", bridge_config.name, "корректное имя bridge")
                return False

            # Проверяем, существует ли bridge
            if self.bridge_exists(node, bridge_config.name):
                self.logger.log_validation_error("bridge_exists", bridge_config.name, "создание нового bridge")
                return False

            # Подготавливаем параметры для API
            bridge_params = {
                'iface': bridge_config.name,
                'type': bridge_config.type,  # Обязательный параметр type=bridge
                'autostart': 1 if bridge_config.autostart else 0
            }

            if bridge_config.vlan_aware:
                bridge_params['vlan_aware'] = 'yes'

            # Создаем bridge через Proxmox API
            self.proxmox.api_call('nodes', node, 'network', 'create', **bridge_params)

            # Сохраняем информацию в кеш
            cache_key = f"bridge_info:{node}:{bridge_config.name}"
            bridge_info = {
                'name': bridge_config.name,
                'type': bridge_config.type,
                'active': True,
                'vlan_aware': bridge_config.vlan_aware,
                'ports': bridge_config.ports,
                'autostart': bridge_config.autostart
            }
            self.cache.set(cache_key, bridge_info, ttl=self.bridge_cache_ttl)

            self.logger.log_bridge_creation(bridge_config.name, bridge_config.name, bridge_config.vlan_aware)
            return True

        except Exception as e:
            self.logger.log_deployment_error(f"Ошибка создания bridge: {str(e)}", f"node={node}, bridge={bridge_config.name}")
            return False

    def delete_bridge(self, node: str, bridge_name: str) -> bool:
        """
        Удаление сетевого bridge

        Args:
            node: Имя ноды
            bridge_name: Имя bridge для удаления

        Returns:
            True если bridge успешно удален
        """
        try:
            # Проверяем, существует ли bridge
            if not self.bridge_exists(node, bridge_name):
                self.logger.log_validation_error("bridge_not_exists", bridge_name, "удаление существующего bridge")
                return False

            # Удаляем bridge через Proxmox API
            self.proxmox.api_call('nodes', node, 'network', bridge_name, 'delete')

            # Удаляем из кеша
            cache_key = f"bridge_info:{node}:{bridge_name}"
            self.cache.delete(cache_key)

            self.logger.log_cache_operation("delete_bridge", f"{node}:{bridge_name}", True)
            return True

        except Exception as e:
            self.logger.log_deployment_error(f"Ошибка удаления bridge: {str(e)}", f"node={node}, bridge={bridge_name}")
            return False

    def bridge_exists(self, node: str, bridge_name: str) -> bool:
        """
        Проверка существования bridge

        Args:
            node: Имя ноды
            bridge_name: Имя bridge

        Returns:
            True если bridge существует
        """
        cache_key = f"bridge_info:{node}:{bridge_name}"

        # Проверяем кеш
        cached_info = self.cache.get(cache_key)
        if cached_info:
            return cached_info.get('active', False)

        try:
            # Получаем список сетевых интерфейсов
            networks = self.proxmox.api_call('nodes', node, 'network', 'get')

            # Ищем bridge с указанным именем
            for network in networks:
                if network.get('iface') == bridge_name and network.get('type') == 'bridge':
                    # Сохраняем в кеш
                    bridge_info = {
                        'name': bridge_name,
                        'type': 'bridge',
                        'active': True,
                        'vlan_aware': network.get('vlan_aware', False),
                        'ports': network.get('ports', []),
                        'autostart': network.get('autostart', True)
                    }
                    self.cache.set(cache_key, bridge_info, ttl=self.bridge_cache_ttl)
                    return True

            return False

        except Exception as e:
            self.logger.log_validation_error("bridge_exists", bridge_name, f"проверка существования: {str(e)}")
            return False

    def get_bridge_info(self, node: str, bridge_name: str) -> Optional[BridgeInfo]:
        """
        Получение информации о bridge

        Args:
            node: Имя ноды
            bridge_name: Имя bridge

        Returns:
            Информация о bridge или None если не найден
        """
        cache_key = f"bridge_info:{node}:{bridge_name}"

        # Проверяем кеш
        cached_info = self.cache.get(cache_key)
        if cached_info:
            return self._dict_to_bridge_info(cached_info)

        try:
            # Получаем информацию о конкретном bridge
            bridge_data = self.proxmox.api_call('nodes', node, 'network', bridge_name, 'get')

            bridge_info = BridgeInfo(
                name=bridge_data.get('iface', bridge_name),
                type=bridge_data.get('type', 'bridge'),
                active=True,
                vlan_aware=bridge_data.get('vlan_aware', False),
                ports=bridge_data.get('ports', []),
                autostart=bridge_data.get('autostart', True)
            )

            # Сохраняем в кеш
            cache_data = {
                'name': bridge_info.name,
                'type': bridge_info.type,
                'active': bridge_info.active,
                'vlan_aware': bridge_info.vlan_aware,
                'ports': bridge_info.ports,
                'autostart': bridge_info.autostart
            }
            self.cache.set(cache_key, cache_data, ttl=self.bridge_cache_ttl)

            return bridge_info

        except Exception as e:
            self.logger.log_validation_error("bridge_info", bridge_name, f"получение информации: {str(e)}")
            return None

    def _dict_to_bridge_info(self, data: Dict[str, Any]) -> BridgeInfo:
        """Преобразование словаря в BridgeInfo"""
        return BridgeInfo(
            name=data['name'],
            type=data['type'],
            active=data['active'],
            vlan_aware=data['vlan_aware'],
            ports=data['ports'],
            autostart=data['autostart']
        )

    def list_bridges(self, node: str) -> List[BridgeInfo]:
        """
        Получение списка всех bridge'ей на ноде

        Args:
            node: Имя ноды

        Returns:
            Список bridge'ей
        """
        cache_key = f"bridges_list:{node}"

        # Проверяем кеш
        cached_bridges = self.cache.get(cache_key)
        if cached_bridges:
            return [self._dict_to_bridge_info(data) for data in cached_bridges]

        try:
            # Получаем список сетевых интерфейсов
            networks = self.proxmox.api_call('nodes', node, 'network', 'get')

            bridges = []
            for network in networks:
                if network.get('type') == 'bridge':
                    bridge_info = BridgeInfo(
                        name=network.get('iface', ''),
                        type='bridge',
                        active=True,
                        vlan_aware=network.get('vlan_aware', False),
                        ports=network.get('ports', []),
                        autostart=network.get('autostart', True)
                    )
                    bridges.append(bridge_info)

            # Сохраняем в кеш
            cache_data = [{
                'name': bridge.name,
                'type': bridge.type,
                'active': bridge.active,
                'vlan_aware': bridge.vlan_aware,
                'ports': bridge.ports,
                'autostart': bridge.autostart
            } for bridge in bridges]
            self.cache.set(cache_key, cache_data, ttl=self.bridge_cache_ttl)

            return bridges

        except Exception as e:
            self.logger.log_validation_error("list_bridges", str(e), f"список bridge на {node}")
            return []

    def _validate_bridge_name(self, bridge_name: str) -> bool:
        """Валидация имени bridge"""
        if not bridge_name:
            return False

        # Проверка формата имени bridge
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9._-]*$', bridge_name):
            return False

        # Проверка длины
        if len(bridge_name) > 50:
            return False

        return True

    def create_vlan_aware_bridge(self, node: str, bridge_name: str,
                                base_bridge: Optional[str] = None) -> bool:
        """
        Создание VLAN-aware bridge

        Args:
            node: Имя ноды
            bridge_name: Имя нового bridge
            base_bridge: Базовый bridge для наследования настроек

        Returns:
            True если bridge успешно создан
        """
        config = BridgeConfig(
            name=bridge_name,
            type="bridge",
            vlan_aware=True,
            autostart=True
        )

        return self.create_bridge(node, config)

    def configure_bridge_ports(self, node: str, bridge_name: str, ports: List[str]) -> bool:
        """
        Настройка портов bridge

        Args:
            node: Имя ноды
            bridge_name: Имя bridge
            ports: Список портов для добавления

        Returns:
            True если порты успешно настроены
        """
        try:
            # Получаем текущую информацию о bridge
            bridge_info = self.get_bridge_info(node, bridge_name)
            if not bridge_info:
                self.logger.log_validation_error("configure_ports", bridge_name, "существующий bridge")
                return False

            # Обновляем список портов
            current_ports = set(bridge_info.ports)
            new_ports = set(ports)

            # Добавляем новые порты
            for port in new_ports - current_ports:
                try:
                    self.proxmox.api_call('nodes', node, 'network', bridge_name, 'create',
                                        type='bridge_port', iface=port)
                except Exception as e:
                    self.logger.log_validation_error("add_port", port, f"добавление к {bridge_name}: {str(e)}")

            # Обновляем кеш
            cache_key = f"bridge_info:{node}:{bridge_name}"
            updated_info = {
                'name': bridge_name,
                'type': 'bridge',
                'active': True,
                'vlan_aware': bridge_info.vlan_aware,
                'ports': list(new_ports),
                'autostart': bridge_info.autostart
            }
            self.cache.set(cache_key, updated_info, ttl=self.bridge_cache_ttl)

            self.logger.log_cache_operation("configure_ports", f"{node}:{bridge_name}", True)
            return True

        except Exception as e:
            self.logger.log_deployment_error(f"Ошибка настройки портов bridge: {str(e)}", f"node={node}, bridge={bridge_name}")
            return False

    def get_bridge_statistics(self, node: str) -> Dict[str, Any]:
        """
        Получение статистики по bridge'ам на ноде

        Args:
            node: Имя ноды

        Returns:
            Статистика bridge'ей
        """
        bridges = self.list_bridges(node)

        stats = {
            'total_bridges': len(bridges),
            'vlan_aware_bridges': 0,
            'regular_bridges': 0,
            'total_ports': 0,
            'bridge_names': []
        }

        for bridge in bridges:
            stats['bridge_names'].append(bridge.name)
            stats['total_ports'] += len(bridge.ports)

            if bridge.vlan_aware:
                stats['vlan_aware_bridges'] += 1
            else:
                stats['regular_bridges'] += 1

        return stats

    def cleanup_unused_bridges(self, node: str, used_bridges: Set[str]) -> int:
        """
        Очистка неиспользуемых bridge'ей

        Args:
            node: Имя ноды
            used_bridges: Множество используемых bridge'ей

        Returns:
            Количество удаленных bridge'ей
        """
        deleted_count = 0
        bridges = self.list_bridges(node)

        for bridge in bridges:
            if bridge.name not in used_bridges:
                # Проверяем, что bridge не является системным
                if not self._is_system_bridge(bridge.name):
                    if self.delete_bridge(node, bridge.name):
                        deleted_count += 1

        if deleted_count > 0:
            self.logger.log_cache_operation("cleanup_bridges", f"{deleted_count}_bridges", True)

        return deleted_count

    def _is_system_bridge(self, bridge_name: str) -> bool:
        """Проверка, является ли bridge системным"""
        system_bridges = ['vmbr0', 'vmbr1', 'vmbr2']
        return bridge_name in system_bridges

    def clear_bridge_cache(self, node: Optional[str] = None) -> int:
        """
        Очистка кеша информации о bridge'ах

        Args:
            node: Нода для очистки (если None, то все)

        Returns:
            Количество очищенных записей
        """
        cleared_count = 0

        if node:
            # Очищаем кеш для конкретной ноды
            cache_keys = [key for key in self.cache.cache.keys() if key.startswith(f'bridge_info:{node}:')]
            for key in cache_keys:
                self.cache.delete(key)
                cleared_count += 1
        else:
            # Очищаем весь кеш bridge'ей
            cache_keys = [key for key in self.cache.cache.keys() if 'bridge' in key]
            for key in cache_keys:
                self.cache.delete(key)
                cleared_count += 1

        if cleared_count > 0:
            self.logger.log_cache_operation("clear_bridge_cache", f"{cleared_count}_entries", True)

        return cleared_count


# Глобальный экземпляр менеджера bridge'ей
_global_bridge_manager = None


def get_bridge_manager(proxmox_client: ProxmoxClient) -> BridgeManager:
    """Получить глобальный экземпляр менеджера bridge'ей"""
    global _global_bridge_manager
    if _global_bridge_manager is None:
        _global_bridge_manager = BridgeManager(proxmox_client)
    return _global_bridge_manager


# Пример использования
if __name__ == "__main__":
    print("🌉 BridgeManager - менеджер сетевых bridge'ей")
    print("📋 Доступные методы:")

    # Получаем все публичные методы
    methods = [method for method in dir(BridgeManager) if not method.startswith('_') and callable(getattr(BridgeManager, method))]
    for method in methods:
        print(f"  - {method}")

    print(f"\n📊 Всего методов: {len(methods)}")
    print("✅ Менеджер bridge'ей готов к использованию")
