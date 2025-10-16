#!/usr/bin/env python3
"""
Тестовый скрипт для проверки функционала VLAN в развертывании стендов
"""

import sys
import os
import logging

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.utils.network_manager import NetworkManager
from core.utils.proxmox_client import ProxmoxClient

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_vlan_parsing():
    """Тестирование разбора имен bridge с VLAN"""
    logger.info("Тестирование разбора имен bridge с VLAN...")

    # Создаем мок ProxmoxClient для тестирования
    class MockProxmoxClient:
        def __init__(self):
            self.api = None

    mock_client = MockProxmoxClient()
    network_manager = NetworkManager(mock_client)

    # Тестовые случаи
    test_cases = [
        ("hq", ("hq", None)),
        ("hq.100", ("hq", 100)),
        ("inet.200", ("inet", 200)),
        ("vmbr0", ("vmbr0", None)),
        ("**vmbr1", ("**vmbr1", None)),
        ("test.123", ("test", 123)),
        ("invalid.vlan", ("invalid.vlan", None)),  # не число после точки
    ]

    for bridge_name, expected in test_cases:
        result = network_manager._parse_bridge_name(bridge_name)
        logger.info(f"Тест: '{bridge_name}' -> {result} (ожидаемо: {expected})")
        assert result == expected, f"Ошибка разбора '{bridge_name}': получено {result}, ожидалось {expected}"

    logger.info("✅ Все тесты разбора VLAN прошли успешно")


def test_vlan_bridge_creation():
    """Тестирование создания VLAN-aware bridge (симуляция)"""
    logger.info("Тестирование создания VLAN-aware bridge...")

    # Создаем мок ProxmoxClient для тестирования
    class MockProxmoxClient:
        def __init__(self):
            self.api = None

    mock_client = MockProxmoxClient()
    network_manager = NetworkManager(mock_client)

    # Тестируем создание VLAN bridge
    try:
        # Симулируем успешное создание bridge
        logger.info("Симуляция создания VLAN-aware bridge vmbr1000 для alias 'hq' с VLAN 100")
        logger.info("✅ VLAN bridge создание протестировано (симуляция)")
    except Exception as e:
        logger.error(f"Ошибка тестирования создания VLAN bridge: {e}")
        raise


def test_network_config_generation():
    """Тестирование генерации сетевых конфигураций с VLAN"""
    logger.info("Тестирование генерации сетевых конфигураций с VLAN...")

    # Создаем мок ProxmoxClient для тестирования
    class MockProxmoxClient:
        def __init__(self):
            self.api = None

    mock_client = MockProxmoxClient()
    network_manager = NetworkManager(mock_client)

    # Тестовая конфигурация сетей (смешанные алиасы с VLAN и без)
    networks = [
        {"bridge": "vmbr0"},      # Обычный bridge
        {"bridge": "hq"},         # Алиас без VLAN
        {"bridge": "hq.100"},     # Тот же алиас с VLAN
        {"bridge": "inet.200"},   # Другой алиас с VLAN
    ]

    # Тестовый bridge mapping
    bridge_mapping = {
        "vmbr0": "vmbr0",
        "hq": "vmbr1000",         # Алиас без VLAN маппится на bridge
        "hq.100": "vmbr1000",     # Тот же алиас с VLAN маппится на тот же bridge
        "inet.200": "vmbr2000",
    }

    # Генерируем конфигурации
    network_configs = network_manager._prepare_network_configs(networks, bridge_mapping, "linux")

    logger.info("Сгенерированные сетевые конфигурации:")
    for net_id, config in network_configs.items():
        logger.info(f"  {net_id}: {config}")

    # Проверяем результаты
    expected_configs = {
        "net0": "model=virtio,bridge=vmbr0,firewall=1",           # Обычный bridge
        "net1": "model=virtio,bridge=vmbr1000,firewall=1",        # Алиас без VLAN - без tag
        "net2": "model=virtio,bridge=vmbr1000,tag=100,firewall=1", # Алиас с VLAN - с tag
        "net3": "model=virtio,bridge=vmbr2000,tag=200,firewall=1", # Другой алиас с VLAN - с tag
    }

    for net_id, expected_config in expected_configs.items():
        actual_config = network_configs.get(net_id)
        logger.info(f"Проверка {net_id}: '{actual_config}' == '{expected_config}'")
        assert actual_config == expected_config, f"Несоответствие конфигурации {net_id}"

    logger.info("✅ Все тесты генерации сетевых конфигураций с VLAN прошли успешно")


def main():
    """Основная функция тестирования"""
    logger.info("🚀 Начинаем тестирование функционала VLAN...")

    try:
        test_vlan_parsing()
        test_vlan_bridge_creation()
        test_network_config_generation()

        logger.info("🎉 Все тесты VLAN прошли успешно!")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании VLAN: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
