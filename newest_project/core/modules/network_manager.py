#!/usr/bin/env python3
"""
NetworkManager - менеджер сети для newest_project

Управляет настройкой сети виртуальных машин с поддержкой VLAN,
созданием bridge'ей и кешированием сетевых конфигураций.
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from ..utils.logger import Logger
from ..utils.validator import Validator
from ..utils.cache import Cache, BridgeMappingCache


@dataclass
class BridgeAlias:
    """Алиас сетевого bridge с поддержкой VLAN"""
    alias: str
    bridge_name: str
    vlan_id: Optional[int] = None
    node: str = ""

    def __str__(self) -> str:
        if self.vlan_id:
            return f"{self.alias} -> {self.bridge_name} (VLAN {self.vlan_id})"
        return f"{self.alias} -> {self.bridge_name}"


@dataclass
class NetworkConfig:
    """Конфигурация сети для виртуальной машины"""
    bridge: str
    vlan_id: Optional[int] = None
    model: str = "virtio"
    firewall: bool = True
    mac_address: Optional[str] = None


class NetworkManager:
    """
    Менеджер сетевой инфраструктуры

    Возможности:
    - Разбор алиасов сетей (bridge.vlan)
    - Создание VLAN-aware bridge'ей
    - Генерация конфигурации сетевых интерфейсов
    - Кеширование соответствий алиасов bridge'ам
    - Управление сетевыми настройками VM
    """

    def __init__(self, logger: Optional[Logger] = None,
                 validator: Optional[Validator] = None,
                 cache: Optional[Cache] = None):
        """
        Инициализация менеджера сети

        Args:
            logger: Экземпляр логгера
            validator: Экземпляр валидатора
            cache: Экземпляр кеша
        """
        self.logger = logger or Logger()
        self.validator = validator or Validator()
        self.cache = cache or Cache()

        # Кеш для bridge mapping
        self.bridge_cache = BridgeMappingCache(self.cache)

        # Счетчики для автоматического выделения bridge'ей
        self.bridge_counters = {
            'default': 1000,
            'inet': 2000,
            'hq': 1000,
            'dmz': 3000
        }

        # Регулярное выражение для разбора алиасов
        self.alias_pattern = re.compile(r'^([a-zA-Z0-9._-]+?)(?:\.(\d+))?$')

    def parse_bridge_alias(self, alias: str) -> Optional[BridgeAlias]:
        """
        Разбор алиаса bridge на компоненты

        Args:
            alias: Алиас в формате bridge.vlan или просто bridge

        Returns:
            BridgeAlias объект или None при ошибке
        """
        match = self.alias_pattern.match(alias.strip())

        if not match:
            self.logger.log_validation_error("bridge_alias", alias, "формат bridge.vlan_id")
            return None

        bridge_part, vlan_part = match.groups()

        vlan_id = None
        if vlan_part:
            try:
                vlan_id = int(vlan_part)
                if not (1 <= vlan_id <= 4094):
                    self.logger.log_validation_error("vlan_id", vlan_id, "диапазон 1-4094")
                    return None
            except ValueError:
                self.logger.log_validation_error("vlan_id", vlan_part, "числовое значение")
                return None

        return BridgeAlias(
            alias=alias,
            bridge_name=bridge_part,
            vlan_id=vlan_id
        )

    def generate_bridge_name(self, base_alias: str) -> str:
        """
        Генерация уникального имени bridge

        Args:
            base_alias: Базовый алиас для генерации имени

        Returns:
            Уникальное имя bridge
        """
        # Определяем префикс для разных типов сетей
        if base_alias.startswith('vmbr'):
            prefix = 'vmbr'
            counter_key = 'default'
        elif base_alias in ['inet', 'internet', 'ext']:
            prefix = 'vmbr'
            counter_key = 'inet'
        elif base_alias in ['hq', 'headquarters', 'corp']:
            prefix = 'vmbr'
            counter_key = 'hq'
        elif base_alias in ['dmz', 'demilitarized']:
            prefix = 'vmbr'
            counter_key = 'dmz'
        else:
            prefix = 'vmbr'
            counter_key = 'default'

        # Генерируем уникальное имя
        while True:
            bridge_name = f"{prefix}{self.bridge_counters[counter_key]}"
            self.bridge_counters[counter_key] += 1

            # Проверяем, что такое имя не используется
            if not self._is_bridge_exists(bridge_name):
                return bridge_name

    def _is_bridge_exists(self, bridge_name: str) -> bool:
        """Проверка существования bridge (заглушка для будущего использования)"""
        # В будущем здесь будет проверка через Proxmox API
        return False

    def resolve_bridge_aliases(self, networks: List[str], user: str, node: str) -> List[BridgeAlias]:
        """
        Разрешение алиасов сетей в реальные bridge'ы

        Args:
            networks: Список алиасов сетей
            user: Имя пользователя
            node: Имя ноды

        Returns:
            Список разрешенных BridgeAlias
        """
        resolved_bridges = []

        # Получаем существующий mapping из кеша
        existing_mapping = self.bridge_cache.get_bridge_mapping(user, node) or {}

        for alias in networks:
            # Проверяем кеш
            if alias in existing_mapping:
                cached_bridge = existing_mapping[alias]
                bridge_alias = self.parse_bridge_alias(alias)
                if bridge_alias:
                    bridge_alias.bridge_name = cached_bridge
                    resolved_bridges.append(bridge_alias)
                    self.logger.log_cache_operation("bridge_hit", f"{user}:{node}:{alias}", True)
                continue

            # Разбираем алиас
            bridge_alias = self.parse_bridge_alias(alias)
            if not bridge_alias:
                self.logger.log_validation_error("resolve_alias", alias, "корректный алиас сети")
                continue

            # Генерируем имя bridge если не найдено в кеше
            if bridge_alias.bridge_name not in [b.bridge_name for b in resolved_bridges]:
                # Определяем базовое имя для генерации
                base_name = bridge_alias.bridge_name

                # Проверяем, нужно ли создавать VLAN-aware bridge
                vlan_aware_needed = self._check_vlan_aware_needed(networks, base_name)

                if vlan_aware_needed:
                    # Создаем VLAN-aware bridge
                    bridge_name = self.generate_bridge_name(base_name)
                    self.logger.log_bridge_creation(bridge_name, bridge_alias.alias, vlan_aware=True)
                else:
                    # Создаем обычный bridge
                    bridge_name = self.generate_bridge_name(base_name)
                    self.logger.log_bridge_creation(bridge_name, bridge_alias.alias, vlan_aware=False)

                bridge_alias.bridge_name = bridge_name

            resolved_bridges.append(bridge_alias)

        # Сохраняем mapping в кеш
        new_mapping = {ba.alias: ba.bridge_name for ba in resolved_bridges}
        self.bridge_cache.set_bridge_mapping(user, node, new_mapping)

        self.logger.log_cache_operation("bridge_mapping", f"{user}:{node}", True)
        return resolved_bridges

    def _check_vlan_aware_needed(self, networks: List[str], base_bridge: str) -> bool:
        """Проверка необходимости VLAN-aware bridge"""
        for alias in networks:
            if alias.startswith(f"{base_bridge}."):
                return True
        return False

    def generate_network_config(self, bridge_alias: BridgeAlias) -> NetworkConfig:
        """
        Генерация конфигурации сетевого интерфейса

        Args:
            bridge_alias: Алиас bridge с параметрами

        Returns:
            Конфигурация сети для VM
        """
        config = NetworkConfig(
            bridge=bridge_alias.bridge_name,
            vlan_id=bridge_alias.vlan_id,
            model="virtio",
            firewall=True
        )

        return config

    def generate_qemu_network_string(self, network_config: NetworkConfig) -> str:
        """
        Генерация строки конфигурации сети для QEMU

        Args:
            network_config: Конфигурация сети

        Returns:
            Строка в формате QEMU для сетевого интерфейса
        """
        parts = [
            f"model={network_config.model}",
            f"bridge={network_config.bridge}",
            "firewall=1"
        ]

        if network_config.vlan_id:
            parts.append(f"tag={network_config.vlan_id}")

        if network_config.mac_address:
            parts.append(f"macaddr={network_config.mac_address}")

        return ",".join(parts)

    def validate_network_config(self, networks: List[str]) -> Dict[str, Any]:
        """
        Валидация конфигурации сети

        Args:
            networks: Список алиасов сетей

        Returns:
            Результат валидации
        """
        errors = []
        warnings = []

        if not isinstance(networks, list):
            errors.append("Список сетей должен быть массивом")
            return {'valid': False, 'errors': errors, 'warnings': warnings}

        if len(networks) == 0:
            warnings.append("Список сетей пуст")
            return {'valid': True, 'errors': errors, 'warnings': warnings}

        # Валидация каждого алиаса
        for i, alias in enumerate(networks):
            bridge_alias = self.parse_bridge_alias(alias)
            if not bridge_alias:
                errors.append(f"Некорректный алиас сети #{i}: {alias}")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }

    def get_network_statistics(self, networks: List[str]) -> Dict[str, Any]:
        """
        Получение статистики по сетевой конфигурации

        Args:
            networks: Список алиасов сетей

        Returns:
            Статистика сети
        """
        stats = {
            'total_networks': len(networks),
            'vlan_networks': 0,
            'regular_networks': 0,
            'bridges': set(),
            'vlans': set()
        }

        for alias in networks:
            bridge_alias = self.parse_bridge_alias(alias)
            if bridge_alias:
                stats['bridges'].add(bridge_alias.bridge_name)
                if bridge_alias.vlan_id:
                    stats['vlan_networks'] += 1
                    stats['vlans'].add(bridge_alias.vlan_id)
                else:
                    stats['regular_networks'] += 1

        stats['bridges'] = list(stats['bridges'])
        stats['vlans'] = list(stats['vlans'])
        stats['unique_bridges'] = len(stats['bridges'])
        stats['unique_vlans'] = len(stats['vlans'])

        return stats

    def optimize_network_config(self, networks: List[str]) -> List[str]:
        """
        Оптимизация конфигурации сети

        Args:
            networks: Исходная конфигурация сети

        Returns:
            Оптимизированная конфигурация
        """
        # Убираем дубликаты
        unique_networks = []
        seen = set()

        for alias in networks:
            if alias not in seen:
                unique_networks.append(alias)
                seen.add(alias)

        # Сортируем для консистентности
        unique_networks.sort()

        return unique_networks

    def create_vlan_aware_bridges(self, networks: List[str], node: str) -> Dict[str, str]:
        """
        Создание VLAN-aware bridge'ей для списка сетей

        Args:
            networks: Список алиасов сетей
            node: Имя ноды

        Returns:
            Соответствие алиасов bridge'ам
        """
        bridge_mapping = {}

        # Группируем алиасы по базовым bridge'ам
        bridge_groups = {}
        for alias in networks:
            bridge_alias = self.parse_bridge_alias(alias)
            if bridge_alias:
                base_bridge = bridge_alias.bridge_name
                if base_bridge not in bridge_groups:
                    bridge_groups[base_bridge] = []
                bridge_groups[base_bridge].append(bridge_alias)

        # Создаем bridge'ы для каждой группы
        for base_bridge, aliases in bridge_groups.items():
            # Проверяем, нужен ли VLAN-aware bridge
            needs_vlan = any(alias.vlan_id for alias in aliases)

            if needs_vlan:
                bridge_name = self.generate_bridge_name(base_bridge)
                bridge_mapping[base_bridge] = bridge_name

                self.logger.log_bridge_creation(bridge_name, base_bridge, vlan_aware=True)

                # Здесь будет вызов к Proxmox API для создания bridge
                # client.create_bridge(node, bridge_name, vlan_aware=True)

        return bridge_mapping

    def generate_mac_address(self) -> str:
        """
        Генерация уникального MAC адреса

        Returns:
            MAC адрес в формате QEMU
        """
        import random

        # Генерируем случайный MAC адрес
        mac = [0x52, 0x54, 0x00,  # QEMU префикс
               random.randint(0x00, 0xFF),
               random.randint(0x00, 0xFF),
               random.randint(0x00, 0xFF)]

        return ':'.join(f'{b:02x}' for b in mac)

    def clear_bridge_cache(self, user: Optional[str] = None) -> int:
        """
        Очистка кеша bridge mapping

        Args:
            user: Пользователь для очистки (если None, то все)

        Returns:
            Количество очищенных записей
        """
        if user:
            self.bridge_cache.clear_user_bridges(user)
            return 1  # Заглушка, в реальности нужно считать очищенные записи
        else:
            # Очищаем все bridge mapping
            cache_keys = [key for key in self.cache.cache.keys() if key.startswith('bridge_mapping:')]
            for key in cache_keys:
                self.cache.delete(key)
            return len(cache_keys)


# Глобальный экземпляр менеджера сети
_global_network_manager = None


def get_network_manager() -> NetworkManager:
    """Получить глобальный экземпляр менеджера сети"""
    global _global_network_manager
    if _global_network_manager is None:
        _global_network_manager = NetworkManager()
    return _global_network_manager


# Пример использования
if __name__ == "__main__":
    print("🌐 NetworkManager - менеджер сетевой инфраструктуры")
    print("📋 Доступные методы:")

    # Получаем все публичные методы
    methods = [method for method in dir(NetworkManager) if not method.startswith('_') and callable(getattr(NetworkManager, method))]
    for method in methods:
        print(f"  - {method}")

    print(f"\n📊 Всего методов: {len(methods)}")
    print("✅ Менеджер сети готов к использованию")
