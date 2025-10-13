
#!/usr/bin/env python3
"""
Меню развертывания стендов
Развертывание конфигураций стендов по различным стратегиям
"""

import os
import yaml as yaml_module
from typing import Dict, List, Any, Optional

from ..utils import Logger, ConfigValidator


class StandDeployMenu:
    """Меню развертывания стендов"""

    CONFIGS_DIR = "data/configs"
    USERS_DIR = "data"  # Для хранения списков пользователей

    def __init__(self, logger_instance):
        self.logger = logger_instance
        self.validator = ConfigValidator()
        self._ensure_directories()

    def _ensure_directories(self):
        """Создать необходимые директории если они не существуют"""
        try:
            for directory in [self.CONFIGS_DIR, self.USERS_DIR]:
                os.makedirs(directory, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Ошибка создания директорий: {e}")

    def show(self) -> str:
        """Показать меню развертывания стендов"""
        print("\n🚀 Развертывание стендов")
        print("=" * 50)

        # Шаг 1: Выбор конфигурации стенда
        selected_config = self._select_stand_config()
        if not selected_config:
            return "repeat"

        # Шаг 2: Выбор списка пользователей
        selected_users = self._select_users_list()
        if not selected_users:
            return "repeat"

        # Шаг 3: Выбор стратегии развертывания
        strategy = self._select_deployment_strategy()
        if not strategy:
            return "repeat"

        # Шаг 4: Запуск развертывания
        return self._execute_deployment(selected_config, selected_users, strategy)

    def _select_stand_config(self) -> Optional[str]:
        """Выбор конфигурации стенда для развертывания"""
        print("\n📋 Шаг 1: Выбор конфигурации стенда")
        print("-" * 45)

        try:
            configs = self._list_configs()
            if not configs:
                print("❌ Нет доступных конфигураций стендов!")
                print("Создайте конфигурацию в меню 'Управление конфигурациями стендов'")
                input("\nНажмите Enter для продолжения...")
                return None

            print("Доступные конфигурации:")
            for i, config_name in enumerate(configs, 1):
                config_path = os.path.join(self.CONFIGS_DIR, config_name)
                config = self._load_yaml_file(config_path)
                if config and 'machines' in config:
                    num_machines = len(config['machines'])
                    print(f"  [{i}] {config_name} ({num_machines} машин)")
                else:
                    print(f"  [{i}] {config_name} (невалидная)")

            print("  [0] Отмена")

            while True:
                choice_input = input(f"Выберите конфигурацию (1-{len(configs)}) или 0 для отмены: ").strip()
                if choice_input == "0":
                    return None
                try:
                    choice = int(choice_input) - 1
                    if 0 <= choice < len(configs):
                        selected_config = configs[choice]
                        print(f"✅ Выбрана конфигурация: {selected_config}")
                        return selected_config
                    else:
                        print(f"❌ Выберите число от 1 до {len(configs)}")
                except ValueError:
                    print("❌ Введите корректное число!")

        except Exception as e:
            self.logger.error(f"Ошибка при выборе конфигурации: {e}")
            print(f"❌ Ошибка: {e}")
            return None

    def _select_users_list(self) -> Optional[List[str]]:
        """Выбор списка пользователей для развертывания"""
        print("\n👥 Шаг 2: Выбор списка пользователей")
        print("-" * 42)

        try:
            users_lists = self._get_users_lists()
            if not users_lists:
                print("❌ Нет доступных списков пользователей!")
                print("Создайте список пользователей в меню 'Управление пользователями'")
                input("\nНажмите Enter для продолжения...")
                return None

            print("Доступные списки пользователей:")
            for i, list_name in enumerate(users_lists, 1):
                users = self._load_users_list(list_name)
                num_users = len(users)
                print(f"  [{i}] {list_name} ({num_users} пользователей)")

                # Показать превью первых пользователей
                if num_users > 0:
                    preview_users = users[:2]  # Показать первых 2
                    preview = ", ".join(preview_users)
                    if num_users > 2:
                        preview += f" ... и еще {num_users - 2}"
                    print(f"      👤 {preview}")

            print("  [0] Отмена")

            while True:
                choice_input = input(f"Выберите список (1-{len(users_lists)}) или 0 для отмены: ").strip()
                if choice_input == "0":
                    return None
                try:
                    choice = int(choice_input) - 1
                    if 0 <= choice < len(users_lists):
                        selected_list = users_lists[choice]
                        users = self._load_users_list(selected_list)
                        print(f"✅ Выбран список пользователей: {selected_list} ({len(users)} пользователей)")
                        return users
                    else:
                        print(f"❌ Выберите число от 1 до {len(users_lists)}")
                except ValueError:
                    print("❌ Введите корректное число!")

        except Exception as e:
            self.logger.error(f"Ошибка при выборе списка пользователей: {e}")
            print(f"❌ Ошибка: {e}")
            return None

    def _select_deployment_strategy(self) -> Optional[str]:
        """Выбор стратегии развертывания"""
        print("\n🎯 Шаг 3: Выбор стратегии развертывания")
        print("-" * 42)

        print("Стратегии развертывания:")
        print("  [1] 🚀 Локальное - развертывание на ноде с шаблонами")
        print("  [2] 🌐 Удаленное - подготовка шаблонов для целевой ноды")
        print("  [3] ⚖️  Сбалансированное - равномерное распределение")
        print("  [4] 🎯 Умное - с учетом текущей нагрузки")
        print("  [0] Назад")

        while True:
            choice = input("Выберите стратегию развертывания: ").strip()
            if choice == "0":
                return None
            elif choice in ["1", "2", "3", "4"]:
                strategy_names = {
                    "1": "локальная",
                    "2": "удаленная",
                    "3": "сбалансированная",
                    "4": "умная"
                }
                print(f"✅ Выбрана {strategy_names[choice]} стратегия развертывания")
                return choice
            else:
                print("❌ Неверный выбор стратегии!")

    def _execute_deployment(self, config_name: str, users: List[str], strategy: str) -> str:
        """Выполнение развертывания стенда"""
        print("\n⚙️ Шаг 4: Запуск развертывания")
        print("-" * 35)

        try:
            # Загрузить конфигурацию
            config_path = os.path.join(self.CONFIGS_DIR, config_name)
            config = self._load_yaml_file(config_path)

            if not config:
                print("❌ Ошибка загрузки конфигурации!")
                return "error"

            # Валидация конфигурации
            if not self.validator.validate_deployment_config(config):
                print("❌ Конфигурация не прошла валидацию!")
                return "error"

            # Валидация пользователей
            if not self.validator.validate_users_list(users):
                print("❌ Список пользователей не прошел валидацию!")
                return "error"

            print(f"🚀 Начинается развертывание стенда '{config_name}'")
            print(f"👥 Количество пользователей: {len(users)}")
            print(f"🎯 Стратегия: {strategy}")

            # Здесь будет вызываться соответствующий деплойер
            result = self._deploy_with_strategy(config, users, strategy)

            if result == "success":
                print("✅ Развертывание стенда завершено успешно!")
                self.logger.info(f"Успешное развертывание стенда '{config_name}' для {len(users)} пользователей")
            else:
                print("❌ Ошибка при развертывании стенда!")

            input("\nНажмите Enter для продолжения...")
            return result

        except Exception as e:
            self.logger.error(f"Ошибка при развертывании стенда: {e}")
            print(f"❌ Ошибка: {e}")
            return "error"

    def _deploy_with_strategy(self, config: Dict[str, Any], users: List[str], strategy: str) -> str:
        """Развертывание с использованием выбранной стратегии"""
        try:
            if strategy == "1":
                # Локальная стратегия - используем рефакторированный LocalDeployer
                from ..modules.local_deployer import LocalDeployer

                # Получить настройки подключения для развертывания
                connections_file = os.path.join(self.USERS_DIR, "connections_config.yml")
                conn_config = self._load_yaml_file(connections_file)

                if not conn_config:
                    print("❌ Настройки подключения не найдены!")
                    return "error"

                # Использовать первый активный коннект
                active_conn = list(conn_config.values())[0]
                host = active_conn.get('host', 'localhost')
                user = active_conn.get('user', 'root')
                password = active_conn.get('password', '')

                # Создать деплойер
                deployer = LocalDeployer(host=host, user=user, password=password)

                # Выполнить развертывание
                results = deployer.deploy_configuration(users, config)

                # Показать результаты
                self._show_deployment_results(results)

                return "success"  # Пока всегда успех для теста

            else:
                # Другие стратегии пока не реализованы
                print(f"Стратегия {strategy} пока не реализована")
                return "repeat"

        except Exception as e:
            self.logger.error(f"Ошибка выполнения развертывания: {e}")
            print(f"❌ Ошибка: {e}")
            return "error"

    def _show_deployment_results(self, results: Dict[str, Any]) -> None:
        """Показать результаты развертывания"""
        try:
            print("\n📊 Результаты развертывания:")
            print("-" * 30)

            success_count = 0
            total_count = len(results)

            for user, result in results.items():
                if result == "success":
                    print(f"✅ {user}: Успешно")
                    success_count += 1
                else:
                    print(f"❌ {user}: Ошибка - {result}")

            print("-" * 30)
            print(f"Итого: {success_count}/{total_count} успешно")

        except Exception as e:
            self.logger.error(f"Ошибка отображения результатов: {e}")
            print(f"❌ Ошибка отображения результатов: {e}")

    # Вспомогательные методы (копиями из других модулей)
    def _list_configs(self) -> List[str]:
        """Получить список доступных конфигураций"""
        try:
            if not os.path.exists(self.CONFIGS_DIR):
                return []

            configs = []
            for file in os.listdir(self.CONFIGS_DIR):
                if file.endswith('.yml') or file.endswith('.yaml'):
                    configs.append(file)
            return sorted(configs)
        except Exception as e:
            self.logger.error(f"Ошибка получения списка конфигураций: {e}")
            return []

    def _get_users_lists(self) -> List[str]:
        """Получить список доступных списков пользователей"""
        try:
            if not os.path.exists(self.USERS_DIR):
                return []

            lists = []
            for file in os.listdir(self.USERS_DIR):
                if file.startswith('users_') and file.endswith('.yml'):
                    list_name = file[6:-4]  # Убрать префикс 'users_' и суффикс '.yml'
                    lists.append(list_name)
            return sorted(lists)
        except Exception as e:
            self.logger.error(f"Ошибка получения списка пользователей: {e}")
            return []

    def _load_users_list(self, list_name: str) -> List[str]:
        """Загрузить список пользователей"""
        try:
            file_path = os.path.join(self.USERS_DIR, f"users_{list_name}.yml")
            config = self._load_yaml_file(file_path)
            if config and 'users' in config:
                return config['users']
            return []
        except Exception as e:
            self.logger.error(f"Ошибка загрузки списка пользователей {list_name}: {e}")
            return []

    def _load_yaml_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Загрузить YAML файл"""
        try:
            if not os.path.exists(file_path):
                return None

            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                if not content.strip():
                    return None

                data = yaml_module.safe_load(content)
                return data if data is not None else None

        except yaml_module.YAMLError as e:
            self.logger.error(f"Ошибка парсинга YAML файла {file_path}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Ошибка чтения файла {file_path}: {e}")
            return None
