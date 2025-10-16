#!/usr/bin/env python3
"""
Тестирование модуля Validator

Ручное тестирование системы валидации для newest_project
"""

import sys
import os
from pathlib import Path

# Добавляем корневую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.utils.validator import Validator


def test_connection_validation():
    """Тестирование валидации подключения"""
    print("🔗 Тестирование валидации подключения к Proxmox...")

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
            'host': '10.0.0.1:8006',
            'user': 'user@realm',
            'password': 'password123'
        }
    ]

    for i, conn_data in enumerate(valid_connections, 1):
        if validator.validate_proxmox_connection(conn_data):
            print(f"  ✅ Тест {i}: Корректные данные подключения")
        else:
            print(f"  ❌ Тест {i}: Ошибки валидации:")
            for error in validator.get_errors():
                print(f"    - {error}")

    # Некорректные данные подключения
    print("\n  🔍 Тестирование некорректных данных:")

    invalid_connections = [
        {
            'host': 'invalid-host',
            'user': 'root@pam',
            'password': 'secret'
        },
        {
            'host': '192.168.1.100:8006',
            'user': 'invalid@user',
            'password': 'secret'
        },
        {
            'host': '192.168.1.100:99999',
            'user': 'root@pam',
            'password': 'secret'
        },
        {
            'host': '192.168.1.100:8006',
            'user': 'root@pam'
            # Нет пароля или токена
        }
    ]

    for i, conn_data in enumerate(invalid_connections, 1):
        if not validator.validate_proxmox_connection(conn_data):
            print(f"  ✅ Тест {i}: Корректно выявлены ошибки валидации")
            for error in validator.get_errors():
                print(f"    - {error}")
        else:
            print(f"  ❌ Тест {i}: Данные должны быть некорректными")


def test_config_validation():
    """Тестирование валидации конфигурации развертывания"""
    print("\n📋 Тестирование валидации конфигурации развертывания...")

    validator = Validator()

    # Корректная конфигурация
    valid_config = {
        'machines': [
            {
                'name': 'student-pc',
                'device_type': 'linux',
                'template_node': 'pve1',
                'template_vmid': 100,
                'networks': [
                    {'bridge': 'vmbr0'},
                    {'bridge': 'hq.100'},
                    {'bridge': 'inet.200'}
                ]
            },
            {
                'name': 'router',
                'device_type': 'ecorouter',
                'template_node': 'pve2',
                'template_vmid': 200,
                'networks': [
                    {'bridge': 'dmz'}
                ]
            }
        ]
    }

    if validator.validate_deployment_config(valid_config):
        print("  ✅ Корректная конфигурация прошла валидацию")
    else:
        print("  ❌ Ошибки валидации корректной конфигурации:")
        for error in validator.get_errors():
            print(f"    - {error}")

    # Некорректная конфигурация
    print("\n  🔍 Тестирование некорректной конфигурации:")

    invalid_config = {
        'machines': [
            {
                'name': '',  # Пустое имя
                'device_type': 'linux',
                'template_node': 'pve1',
                'template_vmid': 100
            },
            {
                'name': 'invalid@name',  # Некорректное имя
                'device_type': 'windows',  # Недопустимый тип
                'template_node': 'pve1',
                'template_vmid': 50  # Слишком маленький VMID
            },
            {
                'name': 'test-vm',
                'device_type': 'linux',
                'template_node': 'pve1',
                'template_vmid': 100,
                'networks': [
                    {'bridge': 'invalid@bridge'},  # Некорректный bridge
                    {'bridge': 'hq.99999'}  # Слишком большой VLAN ID
                ]
            }
        ]
    }

    if not validator.validate_deployment_config(invalid_config):
        print("  ✅ Корректно выявлены ошибки валидации")
        for error in validator.get_errors():
            print(f"    - {error}")
    else:
        print("  ❌ Конфигурация должна содержать ошибки")


def test_users_validation():
    """Тестирование валидации списка пользователей"""
    print("\n👥 Тестирование валидации пользователей...")

    validator = Validator()

    # Корректный список пользователей
    valid_users = [
        'student1@pve',
        'student2@pve',
        'admin@pam',
        'user@realm$subuser'
    ]

    if validator.validate_users_list(valid_users):
        print("  ✅ Корректный список пользователей прошел валидацию")
    else:
        print("  ❌ Ошибки валидации корректного списка:")
        for error in validator.get_errors():
            print(f"    - {error}")

    # Некорректный список пользователей
    print("\n  🔍 Тестирование некорректного списка:")

    invalid_users = [
        'student1@pve',
        '',  # Пустой пользователь
        'invalid@user@domain',  # Слишком много @
        'user with spaces@pve'  # Пробелы в имени
    ]

    if not validator.validate_users_list(invalid_users):
        print("  ✅ Корректно выявлены ошибки валидации пользователей")
        for error in validator.get_errors():
            print(f"    - {error}")
    else:
        print("  ❌ Список пользователей должен содержать ошибки")


def test_bridge_validation():
    """Тестирование валидации bridge алиасов"""
    print("\n🌉 Тестирование валидации bridge алиасов...")

    validator = Validator()

    # Корректные bridge алиасы
    valid_bridges = [
        'vmbr0',
        'hq',
        'inet',
        'dmz',
        'hq.100',
        'inet.200',
        'vlan-bridge.4094'
    ]

    print("  ✅ Корректные алиасы:")
    for bridge in valid_bridges:
        if validator._validate_bridge_alias(bridge):
            print(f"    - {bridge}")
        else:
            print(f"    ❌ {bridge} должен быть корректным")

    # Некорректные bridge алиасы
    invalid_bridges = [
        '',
        'invalid@bridge',
        'hq.vlan',
        'hq.100.200',
        'hq.0',  # VLAN ID слишком маленький
        'hq.4095',  # VLAN ID слишком большой
        'bridge with spaces',
        'hq.-100',  # Отрицательный VLAN
        'hq.abc'  # VLAN не число
    ]

    print("\n  ❌ Некорректные алиасы:")
    for bridge in invalid_bridges:
        if not validator._validate_bridge_alias(bridge):
            print(f"    - {bridge}")
        else:
            print(f"    ❌ {bridge} должен быть некорректным")


def test_file_validation():
    """Тестирование валидации файлов и директорий"""
    print("\n📁 Тестирование валидации файлов...")

    validator = Validator()

    # Тестирование существующих файлов
    existing_files = [
        'README.md',
        'requirements.txt',
        'core/utils/validator.py'
    ]

    for file_path in existing_files:
        if validator.validate_file_exists(file_path):
            print(f"  ✅ Файл существует: {file_path}")
        else:
            print(f"  ❌ Ошибки проверки файла {file_path}:")
            for error in validator.get_errors():
                print(f"    - {error}")

    # Тестирование несуществующих файлов
    non_existing_files = [
        'nonexistent.txt',
        'path/to/nonexistent/file.yml'
    ]

    for file_path in non_existing_files:
        if not validator.validate_file_exists(file_path):
            print(f"  ✅ Корректно выявлено отсутствие файла: {file_path}")
        else:
            print(f"  ❌ Файл {file_path} не должен существовать")


def main():
    """Главная функция тестирования"""
    print("🚀 Начинаем тестирование модуля Validator")
    print("=" * 50)

    try:
        # Запуск всех тестов
        test_connection_validation()
        test_config_validation()
        test_users_validation()
        test_bridge_validation()
        test_file_validation()

        print("\n" + "=" * 50)
        print("🎉 Все тесты валидатора завершены!")

        # Пауза для просмотра результатов
        input("\n⏸️  Нажмите Enter для завершения...")

    except KeyboardInterrupt:
        print("\n\n👋 Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка при тестировании: {e}")
        raise


if __name__ == "__main__":
    main()
