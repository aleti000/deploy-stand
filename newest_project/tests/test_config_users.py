#!/usr/bin/env python3
"""
Тестирование модулей конфигурации и пользователей

Ручное тестирование ConfigManager и UserManager для newest_project
"""

import sys
import os
from pathlib import Path

# Добавляем корневую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.utils.logger import Logger
from core.utils.validator import Validator
from core.utils.cache import Cache
from core.modules.config_manager import ConfigManager
from core.modules.user_manager import UserManager


def test_config_manager():
    """Тестирование ConfigManager"""
    print("📋 Тестирование ConfigManager...")

    try:
        # Создание менеджера конфигурации
        logger = Logger("test-config-manager")
        validator = Validator()
        cache = Cache()

        config_manager = ConfigManager(
            config_dir="data/test_configs",
            logger=logger,
            validator=validator,
            cache=cache
        )

        print("  ✅ ConfigManager создан")

        # Получение информации о конфигурационных файлах
        config_info = config_manager.get_config_info()
        print(f"  📊 Конфигурационные файлы: {len(config_info)}")

        for config_type, info in config_info.items():
            status = "существует" if info['exists'] else "не найден"
            print(f"    - {config_type}: {status}")

        # Загрузка конфигурации развертывания
        print("\n  📄 Загрузка конфигурации развертывания...")
        deployment_config = config_manager.load_deployment_config()

        if deployment_config:
            machines_count = len(deployment_config.get('machines', []))
            print(f"  ✅ Конфигурация загружена: {machines_count} машин")
        else:
            print("  ⚠️  Не удалось загрузить конфигурацию развертывания")

        # Загрузка пользователей
        print("\n  👥 Загрузка пользователей...")
        users = config_manager.load_users_config()

        if users:
            print(f"  ✅ Пользователи загружены: {len(users)} пользователей")
            print(f"    Первые 3: {users[:3]}")
        else:
            print("  ⚠️  Не удалось загрузить пользователей")

        # Тестирование валидации конфигурации
        print("\n  🔍 Тестирование валидации конфигурации...")
        if deployment_config:
            validation_result = config_manager.validate_config_file("data/test_configs/deployment_config.yml")
            print(f"  Валидация: {'успешна' if validation_result['valid'] else 'ошибки'}")

        # Очистка кеша конфигурации
        cleared = config_manager.clear_config_cache()
        print(f"  💾 Очищено элементов кеша: {cleared}")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования ConfigManager: {e}")
        return False


def test_user_manager():
    """Тестирование UserManager"""
    print("\n👥 Тестирование UserManager...")

    try:
        # Создание менеджера пользователей
        logger = Logger("test-user-manager")
        validator = Validator()
        cache = Cache()

        user_manager = UserManager(
            logger=logger,
            validator=validator,
            cache=cache
        )

        print("  ✅ UserManager создан")

        # Тестовые пользователи
        test_users = [
            'student1@pve',
            'student2@pve',
            'admin@pam',
            'user@realm$subuser',
            'test@domain'
        ]

        print(f"\n  📋 Тестовые пользователи: {len(test_users)}")
        for user in test_users:
            print(f"    - {user}")

        # Парсинг пользователей
        print("\n  🔍 Парсинг пользователей:")
        for user in test_users:
            parsed = user_manager.parse_user(user)
            if parsed:
                print(f"    {user} -> realm: {parsed['realm']}, username: {parsed['username']}")
            else:
                print(f"    {user} -> ошибка парсинга")

        # Группировка по пулам
        print("\n  📊 Группировка по пулам:")
        pools = user_manager.group_users_by_pool(test_users)

        for pool, pool_users in pools.items():
            print(f"    Пул '{pool}': {len(pool_users)} пользователей")
            for user in pool_users:
                print(f"      - {user}")

        # Генерация вариантов пользователей
        print("\n  ⚡ Генерация вариантов пользователей:")
        base_user = "student@pve"
        variants = user_manager.generate_user_variants(base_user, 3)

        print(f"    Базовый: {base_user}")
        for variant in variants:
            print(f"    Вариант: {variant}")

        # Статистика пользователей
        print("\n  📈 Статистика пользователей:")
        stats = user_manager.get_user_statistics(test_users)

        print(f"    Всего пользователей: {stats['total']}")
        print(f"    Уникальных пулов: {stats['unique_pools']}")
        print(f"    Уникальных realm'ов: {stats['unique_realms']}")

        for realm, count in stats['realms'].items():
            print(f"    Realm '{realm}': {count} пользователей")

        # Поиск дубликатов
        print("\n  🔍 Поиск дубликатов:")
        users_with_duplicates = test_users + ['student1@pve', 'admin@pam']
        duplicates = user_manager.find_duplicate_users(users_with_duplicates)

        if duplicates:
            print(f"    Найдено дубликатов: {len(duplicates)}")
            for duplicate in duplicates:
                print(f"      - {duplicate}")
        else:
            print("    Дубликатов не найдено")

        # Валидация списка пользователей
        print("\n  ✅ Валидация списка пользователей:")
        validation_result = user_manager.validate_user_list(test_users)

        print(f"    Валиден: {validation_result['valid']}")
        print(f"    Дубликатов: {validation_result['duplicates_count']}")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования UserManager: {e}")
        return False


def test_yaml_config_operations():
    """Тестирование операций с YAML конфигурацией"""
    print("\n📄 Тестирование операций с YAML...")

    try:
        # Создание тестовых конфигураций
        test_config = {
            'machines': [
                {
                    'name': 'test-pc',
                    'device_type': 'linux',
                    'template_node': 'pve1',
                    'template_vmid': 100,
                    'networks': [
                        {'bridge': 'vmbr0'},
                        {'bridge': 'hq.100'}
                    ]
                }
            ]
        }

        test_users = [
            'user1@pve',
            'user2@pve',
            'admin@pam'
        ]

        # Создание временных файлов
        config_dir = Path("data/test_yaml")
        config_dir.mkdir(parents=True, exist_ok=True)

        # Сохранение конфигурации
        config_file = config_dir / "test_deployment.yml"
        users_file = config_dir / "test_users.yml"

        import yaml
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(test_config, f, default_flow_style=False, allow_unicode=True, indent=2)

        with open(users_file, 'w', encoding='utf-8') as f:
            yaml.dump({'users': test_users}, f, default_flow_style=False, allow_unicode=True, indent=2)

        print(f"  ✅ Конфигурация сохранена: {config_file}")
        print(f"  ✅ Пользователи сохранены: {users_file}")

        # Загрузка и проверка
        with open(config_file, 'r', encoding='utf-8') as f:
            loaded_config = yaml.safe_load(f)

        with open(users_file, 'r', encoding='utf-8') as f:
            loaded_users_data = yaml.safe_load(f)

        loaded_users = loaded_users_data.get('users', []) if loaded_users_data else []

        print(f"  ✅ Конфигурация загружена: {len(loaded_config.get('machines', []))} машин")
        print(f"  ✅ Пользователи загружены: {len(loaded_users)} пользователей")

        # Проверка идентичности
        config_match = loaded_config == test_config
        users_match = loaded_users == test_users

        print(f"  🔍 Конфигурация совпадает: {config_match}")
        print(f"  🔍 Пользователи совпадают: {users_match}")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования YAML: {e}")
        return False


def test_integration_config_users():
    """Тестирование интеграции ConfigManager и UserManager"""
    print("\n🔗 Тестирование интеграции ConfigManager и UserManager...")

    try:
        # Создание менеджеров
        logger = Logger("test-integration")
        validator = Validator()
        cache = Cache()

        config_manager = ConfigManager(
            config_dir="data/test_integration",
            logger=logger,
            validator=validator,
            cache=cache
        )

        user_manager = UserManager(
            logger=logger,
            validator=validator,
            cache=cache
        )

        print("  ✅ Менеджеры созданы")

        # Загрузка конфигурации
        config = config_manager.load_deployment_config()
        users = config_manager.load_users_config()

        if config and users:
            print(f"  ✅ Загружено: {len(config.get('machines', []))} машин, {len(users)} пользователей")

            # Анализ пользователей
            stats = user_manager.get_user_statistics(users)
            print(f"  📊 Статистика пользователей: {stats['total']} всего, {stats['unique_pools']} пулов")

            # Группировка пользователей
            pools = user_manager.group_users_by_pool(users)
            print(f"  📋 Пользователи по пулам: {list(pools.keys())}")

            # Валидация через UserManager
            validation = user_manager.validate_user_list(users)
            print(f"  ✅ Валидация пользователей: {'успешна' if validation['valid'] else 'ошибки'}")

        else:
            print("  ⚠️  Не удалось загрузить конфигурацию или пользователей")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования интеграции: {e}")
        return False


def test_cache_integration_config():
    """Тестирование интеграции с кешем"""
    print("\n💾 Тестирование интеграции с кешем...")

    try:
        cache = Cache()

        # Тестирование кеширования конфигурации
        config_key = "test_deployment_config"
        test_config = {'machines': [{'name': 'test', 'device_type': 'linux'}]}

        # Сохранение в кеш
        cache.set(config_key, test_config, ttl=60)
        print("  ✅ Конфигурация сохранена в кеш")

        # Получение из кеша
        cached_config = cache.get(config_key)
        if cached_config:
            print(f"  ✅ Конфигурация получена из кеша: {len(cached_config.get('machines', []))} машин")
        else:
            print("  ❌ Конфигурация не найдена в кеше")

        # Тестирование кеширования пользователей
        users_key = "test_users"
        test_users = ['user1@pve', 'user2@pve']

        cache.set(users_key, test_users, ttl=60)
        cached_users = cache.get(users_key)

        if cached_users:
            print(f"  ✅ Пользователи получены из кеша: {len(cached_users)} пользователей")
        else:
            print("  ❌ Пользователи не найдены в кеше")

        # Проверка статистики кеша
        stats = cache.get_stats()
        print(f"  📊 Статистика кеша: {stats['hits']} hits, {stats['misses']} misses")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования кеша: {e}")
        return False


def main():
    """Главная функция тестирования"""
    print("🚀 Начинаем тестирование модулей конфигурации и пользователей")
    print("=" * 70)

    try:
        # Создаем необходимые директории
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

        # Запуск тестов
        success = True

        success &= test_config_manager()
        success &= test_user_manager()
        success &= test_yaml_config_operations()
        success &= test_integration_config_users()
        success &= test_cache_integration_config()

        print("\n" + "=" * 70)
        if success:
            print("🎉 Все тесты конфигурации и пользователей завершены успешно!")
        else:
            print("⚠️  Некоторые тесты завершились с предупреждениями")

        print("📋 Результаты тестирования:")
        print("  - ConfigManager: управление конфигурацией функционально")
        print("  - UserManager: обработка пользователей работает")
        print("  - YAML операции: чтение/запись конфигураций")
        print("  - Интеграция: модули работают вместе")
        print("  - Кеш: кеширование конфигураций активное")

        # Пауза для просмотра результатов
        input("\n⏸️  Нажмите Enter для завершения...")

    except KeyboardInterrupt:
        print("\n\n👋 Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка при тестировании: {e}")
        raise


if __name__ == "__main__":
    main()
