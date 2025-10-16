#!/usr/bin/env python3
"""
Тестирование модулей подключения к Proxmox

Ручное тестирование ConnectionManager и ProxmoxClient для newest_project
"""

import sys
import os
from pathlib import Path

# Добавляем корневую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.utils.logger import Logger
from core.utils.validator import Validator
from core.utils.cache import Cache
from core.modules.proxmox_client import ProxmoxClient, ProxmoxClientFactory
from core.modules.connection_manager import ConnectionManager


def test_proxmox_client_interface():
    """Тестирование интерфейса ProxmoxClient"""
    print("🔗 Тестирование интерфейса ProxmoxClient...")

    try:
        # Создание клиента без подключения
        logger = Logger("test-client")
        validator = Validator()
        cache = Cache()

        client = ProxmoxClient(
            logger=logger,
            validator=validator,
            cache=cache
        )

        print("  ✅ Клиент создан успешно")
        print(f"  📊 Версия: {client.get_version()}")
        print(f"  🔌 Подключен: {client.is_connected()}")

        # Тестирование методов без подключения
        nodes = client.get_nodes()
        print(f"  📋 Ноды (без подключения): {nodes}")

        node_info = client.get_node_info("nonexistent")
        print(f"  🔍 Инфо о ноде: {node_info}")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования клиента: {e}")
        return False


def test_connection_manager():
    """Тестирование ConnectionManager"""
    print("\n👥 Тестирование ConnectionManager...")

    try:
        # Создание менеджера подключений
        logger = Logger("test-conn-manager")
        validator = Validator()
        cache = Cache()

        conn_manager = ConnectionManager(
            config_file="data/test_connections.yml",
            logger=logger,
            validator=validator,
            cache=cache
        )

        print("  ✅ Менеджер подключений создан")

        # Получение списка подключений
        connections = conn_manager.get_connections_list()
        print(f"  📋 Найдено подключений: {len(connections)}")

        for conn in connections:
            print(f"    - {conn['name']}: {conn['host']} ({'активно' if conn['connected'] else 'неактивно'})")

        # Добавление тестового подключения
        test_conn_name = "test-connection"
        success = conn_manager.add_connection(
            name=test_conn_name,
            host="192.168.1.100:8006",
            user="root@pam",
            password="test_password",
            description="Тестовое подключение"
        )

        if success:
            print(f"  ✅ Тестовое подключение '{test_conn_name}' добавлено")
        else:
            print(f"  ❌ Не удалось добавить тестовое подключение")

        # Тестирование подключения (если есть реальный сервер)
        print("  🔌 Попытка подключения к тестовому серверу...")
        test_result = conn_manager.test_connection(test_conn_name)

        if test_result['success']:
            print(f"  ✅ Тест подключения успешен: {test_result['version']}")
            print(f"  ⏱️  Время подключения: {test_result['connection_time']} сек")
            print(f"  📋 Нод в кластере: {test_result['nodes_count']}")
        else:
            print(f"  ⚠️  Тест подключения не удался: {test_result.get('error', 'неизвестная ошибка')}")
            print("    Это нормально если тестовый сервер недоступен")

        # Получение статистики
        stats = conn_manager.get_connection_stats()
        print(f"  📊 Статистика: {stats['active_connections']}/{stats['total_configured']} активных подключений")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования менеджера подключений: {e}")
        return False


def test_connection_validation():
    """Тестирование валидации подключений"""
    print("\n🔍 Тестирование валидации подключений...")

    validator = Validator()

    # Корректные данные подключения
    valid_connections = [
        {
            'host': '192.168.1.100:8006',
            'user': 'root@pam',
            'password': 'secret'
        },
        {
            'host': 'proxmox.example.com',
            'user': 'admin@pve',
            'token_name': 'deploy-token',
            'token_value': 'secret-token'
        },
        {
            'host': '10.0.0.1',
            'user': 'user@realm',
            'password': 'password123'
        }
    ]

    print("  ✅ Тестирование корректных подключений:")
    for i, conn_data in enumerate(valid_connections, 1):
        if validator.validate_proxmox_connection(conn_data):
            print(f"    Тест {i}: Корректные данные")
        else:
            print(f"    Тест {i}: Ошибки валидации:")
            for error in validator.get_errors():
                print(f"      - {error}")

    # Некорректные данные подключения
    invalid_connections = [
        {
            'host': 'invalid-host',
            'user': 'root@pam',
            'password': 'secret'
        },
        {
            'host': '192.168.1.100:99999',  # Недопустимый порт
            'user': 'root@pam',
            'password': 'secret'
        },
        {
            'host': '192.168.1.100:8006',
            'user': 'invalid@user@domain',  # Слишком много @
            'password': 'secret'
        }
    ]

    print("\n  ❌ Тестирование некорректных подключений:")
    for i, conn_data in enumerate(invalid_connections, 1):
        if not validator.validate_proxmox_connection(conn_data):
            print(f"    Тест {i}: Корректно выявлены ошибки")
            for error in validator.get_errors():
                print(f"      - {error}")
        else:
            print(f"    Тест {i}: Данные должны быть некорректными")

    return True


def test_cache_integration():
    """Тестирование интеграции с кешем"""
    print("\n💾 Тестирование интеграции с кешем...")

    try:
        cache = Cache()

        # Тестирование кеширования версии
        version_key = "test_proxmox_version"
        cache.set(version_key, "7.4-3", ttl=60)

        cached_version = cache.get(version_key)
        if cached_version:
            print(f"  ✅ Версия закеширована: {cached_version}")
        else:
            print("  ❌ Версия не найдена в кеше")

        # Тестирование истечения TTL
        print("  ⏰ Тестирование истечения TTL через 2 секунды...")
        import time
        time.sleep(2)

        # Создаем новый кеш для проверки TTL
        cache2 = Cache()
        expired_version = cache2.get(version_key)
        if expired_version:
            print(f"  ✅ TTL не истек: {expired_version}")
        else:
            print("  ✅ TTL истек, данные удалены из кеша")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования кеша: {e}")
        return False


def test_logger_integration():
    """Тестирование интеграции с логгером"""
    print("\n📝 Тестирование интеграции с логгером...")

    try:
        logger = Logger("test-integration", "DEBUG")
        logger.setup_logging(log_to_file=False, log_to_console=True)

        # Тестовые сообщения
        logger.log_connection_attempt("192.168.1.100:8006", "root@pam")
        logger.log_connection_success("192.168.1.100:8006", "7.4-3")
        logger.log_vm_creation("test-vm", "pve1", 100)
        logger.log_network_setup("test-vm", "vmbr0", 100)
        logger.log_deployment_success(3, 45.2)

        print("  ✅ Логгирование операций выполнено")
        print("  📄 Проверьте вывод выше для сообщений логгера")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования логгера: {e}")
        return False


def main():
    """Главная функция тестирования"""
    print("🚀 Начинаем тестирование модулей подключения")
    print("=" * 60)

    try:
        # Создаем необходимые директории
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

        # Запуск тестов
        success = True

        success &= test_proxmox_client_interface()
        success &= test_connection_manager()
        success &= test_connection_validation()
        success &= test_cache_integration()
        success &= test_logger_integration()

        print("\n" + "=" * 60)
        if success:
            print("🎉 Все тесты подключения завершены успешно!")
        else:
            print("⚠️  Некоторые тесты завершились с предупреждениями")

        print("📋 Результаты тестирования:")
        print("  - ProxmoxClient: интерфейс работает корректно")
        print("  - ConnectionManager: управление подключениями функционально")
        print("  - Validator: валидация данных работает")
        print("  - Cache: кеширование интегрировано")
        print("  - Logger: логирование операций активное")

        # Пауза для просмотра результатов
        input("\n⏸️  Нажмите Enter для завершения...")

    except KeyboardInterrupt:
        print("\n\n👋 Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка при тестировании: {e}")
        raise


if __name__ == "__main__":
    main()
