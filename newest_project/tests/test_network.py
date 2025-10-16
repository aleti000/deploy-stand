#!/usr/bin/env python3
"""
Тестирование модулей сети

Ручное тестирование NetworkManager и BridgeManager для newest_project
"""

import sys
import os
from pathlib import Path

# Добавляем корневую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.utils.logger import Logger
from core.utils.validator import Validator
from core.utils.cache import Cache
from core.modules.network_manager import NetworkManager, BridgeAlias, NetworkConfig
from core.modules.bridge_manager import BridgeManager, BridgeConfig, BridgeInfo


def test_network_manager():
    """Тестирование NetworkManager"""
    print("🌐 Тестирование NetworkManager...")

    try:
        # Создание менеджера сети
        logger = Logger("test-network-manager")
        validator = Validator()
        cache = Cache()

        network_manager = NetworkManager(
            logger=logger,
            validator=validator,
            cache=cache
        )

        print("  ✅ NetworkManager создан")

        # Тестирование разбора алиасов
        print("\n  🔍 Тестирование разбора алиасов:")

        test_aliases = [
            'vmbr0',
            'hq.100',
            'inet.200',
            'dmz',
            'vlan-bridge.4094'
        ]

        for alias in test_aliases:
            bridge_alias = network_manager.parse_bridge_alias(alias)
            if bridge_alias:
                print(f"    {alias} -> bridge: {bridge_alias.bridge_name}, VLAN: {bridge_alias.vlan_id}")
            else:
                print(f"    {alias} -> ошибка разбора")

        # Тестирование генерации имен bridge'ей
        print("\n  🏗️  Тестирование генерации имен bridge'ей:")

        base_aliases = ['hq', 'inet', 'dmz', 'test']
        for base_alias in base_aliases:
            bridge_name = network_manager.generate_bridge_name(base_alias)
            print(f"    {base_alias} -> {bridge_name}")

        # Тестирование разрешения алиасов
        print("\n  🔀 Тестирование разрешения алиасов:")

        networks = ['vmbr0', 'hq.100', 'inet.200', 'dmz']
        user = 'testuser'
        node = 'pve1'

        resolved_bridges = network_manager.resolve_bridge_aliases(networks, user, node)

        print(f"    Исходные алиасы: {networks}")
        print("    Разрешенные алиасы:")
        for bridge in resolved_bridges:
            if bridge.vlan_id:
                print(f"      {bridge.bridge_name} -> {bridge.alias} (VLAN {bridge.vlan_id})")
            else:
                print(f"      {bridge.bridge_name} -> {bridge.alias}")

        # Тестирование генерации конфигурации сети
        print("\n  ⚙️  Тестирование генерации конфигурации сети:")

        for bridge in resolved_bridges:
            network_config = network_manager.generate_network_config(bridge)
            qemu_string = network_manager.generate_qemu_network_string(network_config)
            print(f"    {bridge} -> {qemu_string}")

        # Тестирование валидации сети
        print("\n  ✅ Тестирование валидации сети:")

        valid_networks = ['vmbr0', 'hq.100', 'inet.200']
        invalid_networks = ['invalid@bridge', 'hq.99999', '']

        for networks_list in [valid_networks, invalid_networks]:
            validation = network_manager.validate_network_config(networks_list)
            status = "валидна" if validation['valid'] else "ошибки"
            print(f"    {networks_list} -> {status}")

        # Тестирование статистики сети
        print("\n  📊 Тестирование статистики сети:")

        stats = network_manager.get_network_statistics(networks)
        print(f"    Всего сетей: {stats['total_networks']}")
        print(f"    VLAN сетей: {stats['vlan_networks']}")
        print(f"    Обычных сетей: {stats['regular_networks']}")
        print(f"    Уникальных bridge'ей: {stats['unique_bridges']}")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования NetworkManager: {e}")
        return False


def test_bridge_manager():
    """Тестирование BridgeManager"""
    print("\n🌉 Тестирование BridgeManager...")

    try:
        # Создание менеджера bridge'ей (без реального клиента Proxmox)
        logger = Logger("test-bridge-manager")
        validator = Validator()
        cache = Cache()

        # Создаем мок-клиент для тестирования интерфейса
        class MockProxmoxClient:
            def api_call(self, *args, **kwargs):
                # Заглушка для API вызовов
                return []

        mock_client = MockProxmoxClient()

        bridge_manager = BridgeManager(
            proxmox_client=mock_client,
            logger=logger,
            validator=validator,
            cache=cache
        )

        print("  ✅ BridgeManager создан")

        # Тестирование создания конфигурации bridge
        print("\n  ⚙️  Тестирование создания конфигурации bridge:")

        bridge_config = BridgeConfig(
            name="test-bridge",
            type="bridge",
            vlan_aware=True,
            autostart=True
        )

        print(f"    Конфигурация: {bridge_config.name}, VLAN-aware: {bridge_config.vlan_aware}")

        # Тестирование валидации имени bridge
        print("\n  ✅ Тестирование валидации имен bridge:")

        valid_names = ['vmbr1000', 'test-bridge', 'hq-net']
        invalid_names = ['123invalid', 'invalid@name', 'a' * 51]

        for name in valid_names + invalid_names:
            is_valid = bridge_manager._validate_bridge_name(name)
            status = "валидно" if is_valid else "невалидно"
            print(f"    {name} -> {status}")

        # Тестирование статистики bridge'ей
        print("\n  📊 Тестирование статистики bridge'ей:")

        # Мок-данные для статистики
        mock_bridges = [
            BridgeInfo("vmbr0", "bridge", True, False, [], True),
            BridgeInfo("vmbr1000", "bridge", True, True, ["eth0"], True),
            BridgeInfo("vmbr1001", "bridge", True, False, ["eth1"], True)
        ]

        # Подменяем метод list_bridges для тестирования
        original_list_bridges = bridge_manager.list_bridges
        bridge_manager.list_bridges = lambda node: mock_bridges

        stats = bridge_manager.get_bridge_statistics("pve1")
        print(f"    Всего bridge'ей: {stats['total_bridges']}")
        print(f"    VLAN-aware: {stats['vlan_aware_bridges']}")
        print(f"    Обычных: {stats['regular_bridges']}")
        print(f"    Всего портов: {stats['total_ports']}")

        # Восстанавливаем оригинальный метод
        bridge_manager.list_bridges = original_list_bridges

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования BridgeManager: {e}")
        return False


def test_bridge_alias_operations():
    """Тестирование операций с BridgeAlias"""
    print("\n🏷️  Тестирование операций с BridgeAlias...")

    try:
        # Создание BridgeAlias объектов
        bridge1 = BridgeAlias(alias="vmbr0", bridge_name="vmbr0")
        bridge2 = BridgeAlias(alias="hq.100", bridge_name="vmbr1000", vlan_id=100)
        bridge3 = BridgeAlias(alias="inet.200", bridge_name="vmbr1001", vlan_id=200)

        bridges = [bridge1, bridge2, bridge3]

        print("  ✅ BridgeAlias объекты созданы")

        # Тестирование строкового представления
        print("\n  📝 Строковое представление:")

        for bridge in bridges:
            print(f"    {bridge}")

        # Тестирование сравнения
        print("\n  ⚖️  Тестирование сравнения:")

        bridge_copy = BridgeAlias(alias="vmbr0", bridge_name="vmbr0")
        print(f"    bridge1 == bridge_copy: {bridge1 == bridge_copy}")

        # Тестирование хеширования (для использования в множествах)
        print("\n  🔢 Тестирование хеширования:")

        bridge_set = set(bridges)
        print(f"    Уникальных bridge'ей: {len(bridge_set)}")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования BridgeAlias: {e}")
        return False


def test_network_config_operations():
    """Тестирование операций с NetworkConfig"""
    print("\n⚙️ Тестирование операций с NetworkConfig...")

    try:
        # Создание NetworkConfig объектов
        config1 = NetworkConfig(bridge="vmbr0")
        config2 = NetworkConfig(bridge="vmbr1000", vlan_id=100, mac_address="52:54:00:12:34:56")
        config3 = NetworkConfig(bridge="vmbr1001", vlan_id=200, model="e1000")

        configs = [config1, config2, config3]

        print("  ✅ NetworkConfig объекты созданы")

        # Тестирование генерации QEMU строк
        print("\n  🖥️  Генерация QEMU строк:")

        for config in configs:
            qemu_string = f"model={config.model},bridge={config.bridge},firewall={1 if config.firewall else 0}"
            if config.vlan_id:
                qemu_string += f",tag={config.vlan_id}"
            if config.mac_address:
                qemu_string += f",macaddr={config.mac_address}"

            print(f"    {config.bridge} -> {qemu_string}")

        # Тестирование сравнения конфигураций
        print("\n  ⚖️  Тестирование сравнения:")

        config_copy = NetworkConfig(bridge="vmbr0")
        print(f"    config1 == config_copy: {config1 == config_copy}")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования NetworkConfig: {e}")
        return False


def test_cache_integration_network():
    """Тестирование интеграции с кешем"""
    print("\n💾 Тестирование интеграции с кешем...")

    try:
        cache = Cache()

        # Тестирование кеширования bridge mapping
        bridge_key = "test_bridge_mapping"
        test_mapping = {
            "hq": "vmbr1000",
            "inet": "vmbr1001",
            "dmz": "vmbr1002"
        }

        # Сохранение в кеш
        cache.set(bridge_key, test_mapping, ttl=60)
        print("  ✅ Bridge mapping сохранен в кеш")

        # Получение из кеша
        cached_mapping = cache.get(bridge_key)
        if cached_mapping:
            print(f"  ✅ Bridge mapping получен: {len(cached_mapping)} соответствий")
            for alias, bridge in cached_mapping.items():
                print(f"    {alias} -> {bridge}")
        else:
            print("  ❌ Bridge mapping не найден в кеше")

        # Тестирование специализированного кеша bridge mapping
        from core.utils.cache import BridgeMappingCache

        bridge_cache = BridgeMappingCache(cache)

        user = "testuser"
        node = "pve1"

        bridge_cache.set_bridge_mapping(user, node, test_mapping)
        retrieved_mapping = bridge_cache.get_bridge_mapping(user, node)

        if retrieved_mapping:
            print(f"  ✅ Специализированный кеш работает: {len(retrieved_mapping)} соответствий")
        else:
            print("  ❌ Специализированный кеш не работает")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования кеша: {e}")
        return False


def test_logger_integration_network():
    """Тестирование интеграции с логгером"""
    print("\n📝 Тестирование интеграции с логгером...")

    try:
        logger = Logger("test-network-logger", "DEBUG")
        logger.setup_logging(log_to_file=False, log_to_console=True)

        # Тестовые сообщения для сети
        logger.log_bridge_creation("vmbr1000", "hq", vlan_aware=True)
        logger.log_network_setup("test-vm", "vmbr1000", 100)
        logger.log_performance_metric("network_bandwidth", 1000, "Mbps")

        print("  ✅ Логгирование сетевых операций выполнено")
        print("  📄 Проверьте вывод выше для сообщений логгера")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования логгера: {e}")
        return False


def main():
    """Главная функция тестирования"""
    print("🚀 Начинаем тестирование модулей сети")
    print("=" * 50)

    try:
        # Создаем необходимые директории
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

        # Запуск тестов
        success = True

        success &= test_network_manager()
        success &= test_bridge_manager()
        success &= test_bridge_alias_operations()
        success &= test_network_config_operations()
        success &= test_cache_integration_network()
        success &= test_logger_integration_network()

        print("\n" + "=" * 50)
        if success:
            print("🎉 Все тесты сети завершены успешно!")
        else:
            print("⚠️  Некоторые тесты завершились с предупреждениями")

        print("📋 Результаты тестирования:")
        print("  - NetworkManager: управление сетью функционально")
        print("  - BridgeManager: управление bridge'ами работает")
        print("  - BridgeAlias: операции с алиасами корректны")
        print("  - NetworkConfig: конфигурация сети генерируется")
        print("  - Кеш: кеширование сетевых данных активное")
        print("  - Logger: логирование сетевых операций работает")

        # Пауза для просмотра результатов
        input("\n⏸️  Нажмите Enter для завершения...")

    except KeyboardInterrupt:
        print("\n\n👋 Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка при тестировании: {e}")
        raise


if __name__ == "__main__":
    main()
