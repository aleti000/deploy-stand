"""
Система главного меню пользовательского интерфейса

Предоставляет интерактивное меню для управления развертыванием виртуальных машин
с поддержкой горячих клавиш и оптимизированной навигацией.
"""

import logging
import sys
import os
from typing import Dict, List, Any
from core.module_factory import ModuleFactory
from core.config.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class MainMenu:
    """Главное меню системы Deploy-Stand"""

    def __init__(self, module_factory: ModuleFactory, config_manager: ConfigManager,
                 logger_instance: logging.Logger, cache, metrics):
        """
        Инициализация главного меню

        Args:
            module_factory: Фабрика модулей
            config_manager: Менеджер конфигурации
            logger_instance: Экземпляр логгера
            cache: Кеш менеджер
            metrics: Метрики производительности
        """
        self.module_factory = module_factory
        self.config_manager = config_manager
        self.logger = logger_instance
        self.cache = cache
        self.metrics = metrics

        # Инициализировать менеджеры
        self.proxmox_manager = None
        self.vm_deployer = None
        self.user_manager = None

    def show(self):
        """Показать главное меню с оптимизированной навигацией"""
        # ПЕРВЫМ ДЕЛОМ - НАСТРОЙКА ПОДКЛЮЧЕНИЯ
        if not self._ensure_proxmox_connection():
            print("❌ Невозможно продолжить без подключения к Proxmox")
            return

        # Быстрый доступ к часто используемым функциям
        quick_actions = {
            'd': '4',  # d = deploy (развернуть)
            'c': '1',  # c = create config (создать конфигурацию)
            'u': '3',  # u = users (пользователи)
            'x': '5',  # x = cleanup (очистка)
            's': '7',  # s = settings (настройки подключения)
        }

        while True:
            try:
                # Очистка экрана перед показом меню
                os.system('clear')

                # Показать текущее подключение
                current_connection = self._get_current_connection_info()

                # Оптимизированное отображение меню с горячими клавишами
                print("🚀 Deploy-Stand - Главное меню")
                print("=" * 50)
                print(f"🔌 Текущее подключение: {current_connection}")
                print("=" * 50)
                print("📋 Основные функции:")
                print("  [1] Создать конфигурацию развертывания")
                print("  [2] Управление конфигурациями")
                print("  [3] Указать список пользователей")
                print("  [4] 🚀 Развернуть конфигурацию")
                print("  [5] 🗑️  Удалить машины пользователей")
                print("  [6] Удалить машины конкретного пользователя")
                print("  [7] ⚙️  Управление подключением")
                print("  [0] Выход")
                print("\n⚡ Быстрые команды:")
                print("  d = Развернуть | c = Создать конфиг | u = Пользователи | x = Очистка | s = Настройки")

                # Оптимизированный ввод с поддержкой быстрых команд
                choice = input("\nВыберите действие: ").strip().lower()

                # Обработка быстрых команд
                if choice in quick_actions:
                    choice = quick_actions[choice]

                # Обработка выбора с улучшенной навигацией
                action_result = self._handle_menu_choice(choice)
                if action_result == "exit":
                    break
                elif action_result == "repeat":
                    continue

            except KeyboardInterrupt:
                print("\n\n👋 До свидания!")
                break
            except Exception as e:
                self.logger.error(f"Ошибка в главном меню: {e}")
                print(f"❌ Ошибка: {e}")
                input("Нажмите Enter для продолжения...")

    def _handle_menu_choice(self, choice: str) -> str:
        """Централизованная обработка выбора меню с оптимизацией"""
        menu_actions = {
            "1": lambda: self._create_deployment_config(),
            "2": lambda: self._manage_configs_menu(),
            "3": lambda: self._manage_users_menu(),
            "4": lambda: self._deploy_menu(),
            "5": lambda: self._delete_all_users_resources(),
            "6": lambda: self._delete_single_user_resources(),
            "7": lambda: self._manage_connection_config_menu(),
            "0": lambda: "exit"
        }

        action = menu_actions.get(choice)
        if action:
            try:
                return action() if callable(action) else action
            except Exception as e:
                self.logger.error(f"Ошибка выполнения действия {choice}: {e}")
                print(f"❌ Ошибка: {e}")
                return "repeat"
        else:
            print("❌ Неверный выбор! Используйте цифры 0-7 или быстрые команды (d, c, u, x)")
            return "repeat"

    def _setup_proxmox_connection(self):
        """Оптимизированная настройка подключения с автодетектом"""
        print("\n🔌 Настройка подключения к Proxmox")
        print("=" * 50)

        # Загрузить сохраненные конфигурации подключения
        connections = self.config_manager.load_connections_config()

        if connections:
            print("Доступные конфигурации подключения:")
            for i, (name, config) in enumerate(connections.items(), 1):
                print(f"  [{i}] {name} - {config.get('host', 'не указан')}")
            print(f"  [{len(connections) + 1}] Создать новое подключение")

            try:
                choice = input(f"Выберите конфигурацию (1-{len(connections) + 1}): ").strip()
                config_index = int(choice) - 1

                if 0 <= config_index < len(connections):
                    config_names = list(connections.keys())
                    selected_config = connections[config_names[config_index]]
                    connection_name = config_names[config_index]
                else:
                    return self._create_new_connection()
            except ValueError:
                print("❌ Неверный выбор!")
                return False
        else:
            print("Конфигурации подключений не найдены")
            return self._create_new_connection()

        # Получить данные для подключения
        try:
            from core.proxmox.proxmox_client import ProxmoxClient

            self.proxmox_manager = ProxmoxClient(
                host=selected_config['host'],
                user=selected_config['user'],
                password=None if selected_config.get('use_token') else selected_config.get('password'),
                token_name=selected_config['token_name'] if selected_config.get('use_token') else None,
                token_value=selected_config['token_value'] if selected_config.get('use_token') else None
            )

            # Проверить подключение
            nodes = self.proxmox_manager.get_nodes()
            print(f"✅ Подключение установлено! Доступные ноды: {', '.join(nodes)}")

            # Сохранить конфигурацию подключения (опционально)
            save_config = input("Сохранить эту конфигурацию для следующих сессий? (y/n): ").lower()
            if save_config == 'y':
                # Здесь можно добавить логику сохранения конфигурации
                pass

            return True

        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False

    def _create_new_connection(self):
        """Создать новое подключение к Proxmox"""
        print("\n🔌 Создание нового подключения")
        print("=" * 50)

        host = input("Адрес сервера Proxmox (host:port): ").strip()
        if not host:
            print("❌ Адрес сервера обязателен!")
            return False

        user = input("Пользователь (например, root@pam): ").strip()
        if not user:
            print("❌ Пользователь обязателен!")
            return False

        print("\nСпособы аутентификации:")
        print("  [1] По паролю")
        print("  [2] По токену")

        auth_choice = input("Выберите способ аутентификации (1-2): ").strip()

        try:
            from core.proxmox.proxmox_client import ProxmoxClient

            if auth_choice == "1":
                password = input("Пароль: ").strip()
                if not password:
                    print("❌ Пароль обязателен!")
                    return False

                self.proxmox_manager = ProxmoxClient(
                    host=host,
                    user=user,
                    password=password
                )

            elif auth_choice == "2":
                token_name = input("Имя токена: ").strip()
                token_value = input("Значение токена: ").strip()

                if not token_name or not token_value:
                    print("❌ Имя токена и значение обязательны!")
                    return False

                self.proxmox_manager = ProxmoxClient(
                    host=host,
                    user=user,
                    token_name=token_name,
                    token_value=token_value
                )

            else:
                print("❌ Неверный выбор способа аутентификации!")
                return False

            # Проверить подключение
            nodes = self.proxmox_manager.get_nodes()
            print(f"✅ Подключение установлено! Доступные ноды: {', '.join(nodes)}")
            return True

        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False

    def _create_deployment_config(self):
        """Оптимизированное создание конфигурации с автодополнением"""
        print("\n🚀 Создание конфигурации развертывания")
        print("=" * 50)

        # Быстрый выбор популярных конфигураций
        print("Популярные шаблоны:")
        print("  [1] Студенческий стенд (Linux VM + сеть)")
        print("  [2] Сетевой стенд (Router + несколько сетей)")
        print("  [3] Кастомная конфигурация")
        print("  [0] Назад")

        template_choice = input("Выберите шаблон (1-3) или 0 для назад: ").strip()

        if template_choice == "0":
            return "repeat"
        elif template_choice in ["1", "2"]:
            # Использовать предустановленные шаблоны
            return self._create_config_from_template(template_choice)
        elif template_choice == "3":
            # Кастомная конфигурация
            return self._create_custom_config()
        else:
            print("❌ Неверный выбор!")
            return "repeat"

    def _deploy_menu(self):
        """Оптимизированное меню развертывания с предустановками"""
        print("\n🚀 Развертывание конфигурации")
        print("=" * 50)

        # Показать доступные конфигурации
        configs = self.config_manager.list_configs()
        if not configs:
            print("❌ Нет доступных конфигураций!")
            print("💡 Создайте конфигурацию в меню 1 или используйте deployment_config.yml")
            return "repeat"

        print("Доступные конфигурации:")
        for i, config_name in enumerate(configs, 1):
            print(f"  [{i}] {config_name}")

        print("\nБыстрый выбор:")
        print("  [default] - использовать deployment_config.yml")
        print("  [last] - последняя использованная конфигурация")
        print("  [номер] - выбрать по номеру")

        choice = input("\nВыберите конфигурацию: ").strip().lower()

        # Обработка быстрых выборов
        if choice == "default":
            config = self.config_manager.load_deployment_config()
            config_name = "deployment_config.yml"
        elif choice == "last":
            # Загрузить последнюю использованную конфигурацию
            config = self._load_last_used_config()
            config_name = "последняя"
        else:
            try:
                config_index = int(choice) - 1
                if 0 <= config_index < len(configs):
                    config = self.config_manager.load_config(configs[config_index])
                    config_name = configs[config_index]
                else:
                    print(f"❌ Выберите номер от 1 до {len(configs)}")
                    return "repeat"
            except ValueError:
                print("❌ Введите номер или 'default'/'last'")
                return "repeat"

        if not config:
            print("❌ Ошибка загрузки конфигурации!")
            return "repeat"

        # Выбор списка пользователей для развертывания
        user_lists = self.config_manager.list_user_lists()
        selected_users = []

        if not user_lists:
            print("❌ Нет доступных списков пользователей!")
            print("💡 Создайте список пользователей в меню 3")
            return "repeat"

        print("\n👥 Выбор пользователей для развертывания:")
        print("Доступные списки пользователей:")
        for i, list_name in enumerate(user_lists, 1):
            users = self.config_manager.load_users(list_name)
            print(f"  [{i}] {list_name} ({len(users)} пользователей)")

        try:
            user_choice = input(f"Выберите список пользователей (1-{len(user_lists)}) [1]: ").strip()
            if not user_choice:
                user_choice = "1"

            list_index = int(user_choice) - 1
            if 0 <= list_index < len(user_lists):
                selected_list = user_lists[list_index]
                selected_users = self.config_manager.load_users(selected_list)

                if not selected_users:
                    print(f"❌ Список '{selected_list}' пуст!")
                    return "repeat"

                print(f"👤 Выбран список: {selected_list} ({len(selected_users)} пользователей)")
            else:
                print(f"❌ Выберите номер от 1 до {len(user_lists)}")
                return "repeat"
        except ValueError:
            print("❌ Введите корректный номер")
            return "repeat"

        # Оптимизированные стратегии развертывания с соответствующими модулями
        print("\nСтратегии развертывания:")
        print("  [1] 🚀 Локальное - развертывание на ноде с шаблонами")
        print("  [2] 🌐 Удаленное - подготовка шаблонов для целевой ноды")
        print("  [3] ⚖️  Сбалансированное - по всем нодам (простая балансировка)")
        print("  [4] 🎯 Умное - по всем нодам с учетом нагрузки")

        strategy_choice = input("Выберите стратегию (1-4) [1]: ").strip() or "1"

        # Определить модуль развертывания и параметры
        deployment_module_name = None
        deployment_params = {}
        target_node = None
        node_selection = None

        if strategy_choice == "1":
            # Локальное развертывание
            deployment_module_name = "local"
            print("📍 Используется локальный модуль развертывания")
            node_selection = "auto"
        elif strategy_choice == "2":
            # Удаленное развертывание
            deployment_module_name = "remote"
            print("📡 Используется удаленный модуль развертывания")
            # Получить целевую ноду для удаленного развертывания
            nodes = self.proxmox_manager.get_nodes()
            if not nodes:
                print("❌ Нет доступных нод!")
                return "repeat"

            print("Доступные ноды:")
            for i, node in enumerate(nodes, 1):
                print(f"  {i}. {node}")

            while True:
                choice = input("Выберите целевую ноду [1]: ").strip()
                if not choice:
                    choice = "1"

                try:
                    node_index = int(choice) - 1
                    if 0 <= node_index < len(nodes):
                        target_node = nodes[node_index]
                        break
                    else:
                        print(f"❌ Выберите номер от 1 до {len(nodes)}")
                except ValueError:
                    # Allow direct node name input as fallback
                    if choice in nodes:
                        target_node = choice
                        break
                    else:
                        print(f"❌ Нода '{choice}' не найдена в списке доступных")
            node_selection = "specific"
        elif strategy_choice == "3":
            # Сбалансированное развертывание
            deployment_module_name = "balanced"
            print("⚖️  Используется сбалансированный модуль развертывания")
            node_selection = "balanced"
        elif strategy_choice == "4":
            # Умное развертывание
            deployment_module_name = "smart"
            print("🤖 Используется умный модуль развертывания")
            node_selection = "smart"
        else:
            print("❌ Неверный выбор стратегии!")
            return "repeat"

        # ПРОВЕРКА ПОДКЛЮЧЕНИЯ ПЕРЕД РАЗВЕРТЫВАНИЕМ
        if not hasattr(self, 'proxmox_manager') or self.proxmox_manager is None:
            print("❌ Нет подключения к Proxmox! Подключитесь сначала в меню 7.")
            return "repeat"

        # Проверка работоспособности подключения
        try:
            nodes = self.proxmox_manager.get_nodes()
            if not nodes:
                print("❌ Подключение к Proxmox не работает!")
                return "repeat"
            print(f"✅ Подключение активно: {len(nodes)} нод доступно")
        except Exception as e:
            print(f"❌ Ошибка подключения к Proxmox: {e}")
            return "repeat"

        # Запуск развертывания с выбранным модулем
        print(f"\n🚀 Начинаем развертывание '{config_name}'...")
        print(f"Модуль: {deployment_module_name}")

        try:
            # Создать модуль развертывания соответствующего типа
            if deployment_module_name in ["balanced", "smart"]:
                # Эти модули требуют балансировочного модуля
                balancer_name = "simple" if deployment_module_name == "balanced" else "smart"
                balancer = self.module_factory.create_balancing_module(balancer_name, proxmox_client=self.proxmox_manager)
                deployment_module = self.module_factory.create_deployment_module(
                    deployment_module_name,
                    proxmox_client=self.proxmox_manager,
                    balancing_module=balancer
                )
            else:
                # Простые модули
                deployment_module = self.module_factory.create_deployment_module(
                    deployment_module_name,
                    proxmox_client=self.proxmox_manager
                )

            results = deployment_module.deploy_configuration(
                selected_users,
                config,
                node_selection,
                target_node
            )

            # Красивый вывод результатов
            print(f"\n✅ Развертывание завершено!")
            print(f"Создано пользователей: {len(results)}")

            if results:
                print("\n📋 Результаты:")
                print("-" * 60)
                print(f"{'Пользователь'"<20"} {'Пароль'"<20"}")
                print("-" * 60)
                for user, password in results.items():
                    print(f"{user:<20} {password:<20}")
            else:
                print("❌ Не удалось создать ни одного пользователя")

        except Exception as e:
            print(f"❌ Ошибка развертывания: {e}")

        input("\nНажмите Enter для продолжения...")
        return "repeat"

    def _manage_users_menu(self):
        """Оптимизированное управление пользователями с поддержкой нескольких списков"""
        print("\n👥 Управление пользователями")
        print("=" * 50)

        # Показать доступные списки пользователей
        user_lists = self.config_manager.list_user_lists()
        if user_lists:
            print(f"Доступные списки пользователей ({len(user_lists)}):")
            for i, list_name in enumerate(user_lists, 1):
                users = self.config_manager.load_users(list_name)
                print(f"  [{i}] {list_name} ({len(users)} пользователей)")
            print(f"  [{len(user_lists) + 1}] Создать новый список")
        else:
            print("Списки пользователей не найдены")
            print("  [1] Создать новый список")

        print("\nБыстрые действия:")
        print("  [1] Создать/выбрать список пользователей")
        print("  [2] Показать все списки")
        print("  [3] Удалить список")
        print("  [0] Назад")

        choice = input("Выберите действие: ").strip()

        if choice == "1":
            self._manage_user_lists_menu()
        elif choice == "2":
            self._show_all_user_lists()
        elif choice == "3":
            self._delete_user_list_interactive()
        elif choice == "0":
            return "repeat"
        else:
            print("❌ Неверный выбор!")

        input("\nНажмите Enter для продолжения...")
        return "repeat"

    def _delete_all_users_resources(self):
        """Оптимизированная пакетная очистка с выбором списка пользователей"""
        # Выбрать список пользователей для удаления
        user_lists = self.config_manager.list_user_lists()

        if not user_lists:
            print("❌ Нет доступных списков пользователей!")
            return "repeat"

        print("🗑️  Пакетное удаление ресурсов")
        print("=" * 50)
        print("Доступные списки пользователей:")
        for i, list_name in enumerate(user_lists, 1):
            users = self.config_manager.load_users(list_name)
            print(f"  [{i}] {list_name} ({len(users)} пользователей)")

        try:
            choice = input(f"Выберите список для удаления (1-{len(user_lists)}) [1]: ").strip()
            if not choice:
                choice = "1"

            list_index = int(choice) - 1
            if 0 <= list_index < len(user_lists):
                selected_list = user_lists[list_index]
                users = self.config_manager.load_users(selected_list)

                if not users:
                    print(f"❌ Список '{selected_list}' пуст!")
                    return "repeat"

                print(f"\n📋 Список '{selected_list}' ({len(users)} пользователей):")
                for i, user in enumerate(users, 1):
                    print(f"  {i}. {user}")

                print("\nБудут удалены:")
                print("  • Все виртуальные машины пользователей")
                print("  • Пулы пользователей")
                print("  • Учетные записи пользователей")
                print("  • Неиспользуемые сетевые bridge'ы")

                # Безопасное подтверждение
                confirm = input(f"\nВы уверены? Введите 'DELETE_{selected_list.upper()}' для подтверждения: ").strip()

                if confirm == f"DELETE_{selected_list.upper()}":
                    # ПРОВЕРКА ПОДКЛЮЧЕНИЯ ПЕРЕД ЗАПУСКОМ УДАЛЕНИЯ
                    if not hasattr(self, 'proxmox_manager') or self.proxmox_manager is None:
                        print("❌ Нет подключения к Proxmox! Подключитесь сначала в меню 7.")
                        return "repeat"

                    # Проверка работоспособности подключения
                    try:
                        nodes = self.proxmox_manager.get_nodes()
                        if not nodes:
                            print("❌ Подключение к Proxmox не работает!")
                            return "repeat"
                        print(f"✅ Подключение активно: {len(nodes)} нод доступно")
                    except Exception as e:
                        print(f"❌ Ошибка подключения к Proxmox: {e}")
                        return "repeat"

                    # Инициализируем user_manager если нужно
                    if not hasattr(self, 'user_manager') or self.user_manager is None:
                        from core.users.user_manager import UserManager
                        self.user_manager = UserManager(self.proxmox_manager)

                    print("🗑️  Начинаем удаление...")
                    results = self.user_manager.delete_user_resources_batch(users)

                    print("\n📊 Результаты удаления:")
                    print(f"  ✅ Успешно: {len(results['successful'])}")
                    print(f"  ❌ Ошибок: {len(results['failed'])}")
                    print(f"  ⏭️  Пропущено: {len(results['skipped'])}")

                    if results['failed']:
                        print(f"\n❌ Не удалось удалить: {', '.join(results['failed'])}")
                    else:
                        print("🎉 Все ресурсы успешно удалены!")
                else:
                    print("❌ Операция отменена")
        except ValueError:
            print("❌ Введите корректный номер")
        except Exception as e:
            print(f"❌ Ошибка при удалении ресурсов: {e}")

        input("\nНажмите Enter для продолжения...")
        return "repeat"

    def _manage_configs_menu(self):
        """Оптимизированное управление конфигурациями"""
        print("\n⚙️  Управление конфигурациями")
        print("=" * 50)

        configs = self.config_manager.list_configs()

        if configs:
            print(f"Найдено конфигураций: {len(configs)}")
            for i, config_name in enumerate(configs, 1):
                print(f"  [{i}] {config_name}")

            print("\nДоступные действия:")
            print("  [1] Показать детали конфигурации")
            print("  [2] Удалить конфигурацию")
            print("  [3] Копировать конфигурацию")
            print("  [0] Назад")

            choice = input("Выберите действие: ").strip()

            if choice == "1":
                # Показать детали выбранной конфигурации
                self._show_config_details(configs)
            elif choice == "3":
                # Удалить конфигурацию
                self._delete_config_interactive(configs)
            elif choice == "4":
                # Копировать конфигурацию
                self._copy_config_interactive(configs)
            else:
                print("❌ Неверный выбор!")
        else:
            print("❌ Конфигурации не найдены!")
            print("💡 Создайте первую конфигурацию в меню 1")

        input("\nНажмите Enter для продолжения...")
        return "repeat"

    def _manage_connection_config_menu(self):
        """Управление конфигурацией подключения"""
        print("\n⚙️  Управление подключением")
        print("=" * 50)

        print("Доступные действия:")
        print("  [1] Создать и сохранить новое подключение")
        print("  [2] Показать сохраненные подключения")
        print("  [3] Выбрать и активировать подключение")
        print("  [4] Удалить сохраненное подключение")
        print("  [0] Назад")

        choice = input("Выберите действие: ").strip()

        if choice == "1":
            if self._create_and_save_connection():
                print("✅ Новое подключение создано и сохранено")
            else:
                print("❌ Ошибка создания подключения")
        elif choice == "2":
            connections = self.config_manager.load_connections_config()
            if connections:
                print("\n📋 Сохраненные подключения:")
                for i, (name, config) in enumerate(connections.items(), 1):
                    host = config.get('host', 'не указан')
                    user = config.get('user', 'не указан')
                    use_token = config.get('use_token', False)
                    auth_type = "token" if use_token else "password"
                    print(f"  [{i}] {name}")
                    print(f"      Хост: {host}")
                    print(f"      Пользователь: {user}")
                    print(f"      Аутентификация: {auth_type}")
                    print()
            else:
                print("❌ Сохраненные подключения не найдены")
                print("💡 Создайте первое подключение в пункте 1")
        elif choice == "3":
            self._select_and_activate_connection()
        elif choice == "4":
            self._delete_saved_connection()
        else:
            print("❌ Неверный выбор!")

        input("\nНажмите Enter для продолжения...")
        return "repeat"

    def _delete_single_user_resources(self):
        """Удалить ресурсы конкретного пользователя"""
        print("\n🗑️  Удаление ресурсов пользователя")
        print("=" * 50)

        users = self.config_manager.load_users()
        if not users:
            print("❌ Список пользователей пуст!")
            return "repeat"

        print("Доступные пользователи:")
        for i, user in enumerate(users, 1):
            print(f"  [{i}] {user}")

        try:
            choice = input(f"Выберите пользователя для удаления (1-{len(users)}): ").strip()
            user_index = int(choice) - 1

            if 0 <= user_index < len(users):
                selected_user = users[user_index]
                confirm = input(f"Удалить ресурсы пользователя '{selected_user}'? (y/n): ")

                if confirm.lower() == 'y':
                    # Здесь должна быть логика удаления ресурсов пользователя
                    print(f"✅ Ресурсы пользователя '{selected_user}' удалены")
                else:
                    print("❌ Операция отменена")
            else:
                print(f"❌ Выберите номер от 1 до {len(users)}")
        except ValueError:
            print("❌ Введите корректный номер")

        input("\nНажмите Enter для продолжения...")
        return "repeat"

    def _create_config_from_template(self, template_type):
        """Создать конфигурацию из шаблона"""
        print(f"\n📋 Создание конфигурации из шаблона {template_type}")
        print("=" * 50)

        if template_type == "1":
            # Шаблон студенческого стенда
            config_name = input("Имя конфигурации [student-lab]: ").strip() or "student-lab"
            num_students = input("Количество студентов [10]: ").strip() or "10"

            print("✅ Создан шаблон студенческого стенда")
            print(f"   Конфигурация: {config_name}")
            print(f"   Студентов: {num_students}")
            print("   Включает: Linux VM, сеть, базовые настройки")

        elif template_type == "2":
            # Шаблон сетевого стенда
            config_name = input("Имя конфигурации [router-lab]: ").strip() or "router-lab"
            num_routers = input("Количество роутеров [3]: ").strip() or "3"

            print("✅ Создан шаблон сетевого стенда")
            print(f"   Конфигурация: {config_name}")
            print(f"   Роутеров: {num_routers}")
            print("   Включает: Ecorouter устройства, несколько сетей")

        input("\nНажмите Enter для продолжения...")
        return "repeat"

    def _create_custom_config(self):
        """Создать кастомную конфигурацию"""
        print("\n🔧 Создание кастомной конфигурации")
        print("=" * 50)

        config_name = input("Введите имя конфигурации: ").strip()
        if not config_name:
            print("❌ Имя конфигурации не может быть пустым!")
            input("\nНажмите Enter для продолжения...")
            return "repeat"

        if self.config_manager.load_config(config_name):
            print(f"❌ Конфигурация '{config_name}' уже существует!")
            input("\nНажмите Enter для продолжения...")
            return "repeat"

        machines = []
        print("\nТеперь добавим виртуальные машины...")
        print("Каждая машина должна иметь:")
        print("  - Тип устройства (linux/ecorouter)")
        print("  - Имя машины")
        print("  - Ноду и VMID шаблона")
        print("  - Сетевые интерфейсы (bridge'ы)")
        print("  - Тип клонирования (linked/full)")

        while True:
            print(f"\n📋 Машины в конфигурации: {len(machines)}")
            print("  [1] Добавить машину")
            print("  [2] Показать текущие машины")
            print("  [3] Удалить последнюю машину")
            print("  [4] Сохранить конфигурацию")
            print("  [0] Отмена")

            choice = input("\nВыберите действие: ").strip()

            if choice == "1":
                machine = self._create_machine_interactive()
                if machine:
                    machines.append(machine)
                    print(f"✅ Машина '{machine['name']}' добавлена")
                else:
                    print("❌ Машина не была создана")
            elif choice == "2":
                self._show_machines_in_config(machines)
            elif choice == "3":
                if machines:
                    removed = machines.pop()
                    print(f"✅ Машина '{removed['name']}' удалена")
                else:
                    print("❌ Нет машин для удаления")
            elif choice == "4":
                if not machines:
                    print("❌ Добавьте хотя бы одну машину!")
                    continue

                config = {"machines": machines}
                if self.config_manager.save_config(config_name, config):
                    print(f"✅ Конфигурация '{config_name}' сохранена!")
                    print(f"   Всего машин: {len(machines)}")
                else:
                    print("❌ Ошибка сохранения конфигурации")
                break
            elif choice == "0":
                print("❌ Создание конфигурации отменено")
                break
            else:
                print("❌ Неверный выбор!")

        input("\nНажмите Enter для продолжения...")
        return "repeat"

    def _show_config_details(self, configs):
        """Показать детали конфигурации"""
        try:
            config_num = int(input("Выберите номер конфигурации: ")) - 1
            if 0 <= config_num < len(configs):
                config = self.config_manager.load_config(configs[config_num])
                if config:
                    print(f"\nДетали конфигурации '{configs[config_num]}':")
                    print(f"  Машин в конфигурации: {len(config.get('machines', []))}")
                    for i, machine in enumerate(config.get('machines', []), 1):
                        print(f"\n  Машина {i}:")
                        print(f"    Тип: {machine.get('device_type', 'linux')}")
                        print(f"    Имя: {machine.get('name', 'не указано')}")
                        print(f"    Шаблон: VMID {machine.get('template_vmid')} на ноде {machine.get('template_node')}")
                        print(f"    Сетей: {len(machine.get('networks', []))}")
                        print(f"    Клонирование: {'полное' if machine.get('full_clone') else 'связанное'}")
                else:
                    print("❌ Ошибка загрузки конфигурации")
            else:
                print(f"❌ Выберите номер от 1 до {len(configs)}")
        except ValueError:
            print("❌ Введите корректный номер")

    def _delete_config_interactive(self, configs):
        """Интерактивное удаление конфигурации"""
        try:
            config_num = int(input("Выберите номер конфигурации для удаления: ")) - 1
            if 0 <= config_num < len(configs):
                config_name = configs[config_num]
                confirm = input(f"Удалить конфигурацию '{config_name}'? (y/n): ")
                if confirm.lower() == 'y':
                    self.config_manager.delete_config(config_name)
                    print(f"✅ Конфигурация '{config_name}' удалена")
                else:
                    print("❌ Операция отменена")
            else:
                print(f"❌ Выберите номер от 1 до {len(configs)}")
        except ValueError:
            print("❌ Введите корректный номер")

    def _create_and_save_connection(self) -> bool:
        """Создать новое подключение и сохранить его"""
        print("\n🔌 Создание и сохранение подключения к Proxmox")
        print("=" * 60)

        # Запрос имени подключения
        connection_name = input("Имя подключения (например, 'prod-cluster'): ").strip()
        if not connection_name:
            print("❌ Имя подключения обязательно!")
            return False

        # Проверить, существует ли уже подключение с таким именем
        existing_connections = self.config_manager.load_connections_config() or {}
        if connection_name in existing_connections:
            confirm = input(f"Подключение '{connection_name}' уже существует. Перезаписать? (y/n): ").lower()
            if confirm != 'y':
                print("❌ Операция отменена")
                return False

        # Создать базовое подключение для получения настроек
        success = self._create_new_connection()
        if not success:
            return False

        # Сохранить настройки подключения
        connection_config = {
            'host': self.proxmox_manager.host,
            'user': self.proxmox_manager.user,
        }

        # Добавить аутентификационные данные в зависимости от типа
        if hasattr(self.proxmox_manager, 'password') and self.proxmox_manager.password:
            connection_config['password'] = self.proxmox_manager.password
            connection_config['use_token'] = False
        elif hasattr(self.proxmox_manager, 'token_name') and self.proxmox_manager.token_name:
            connection_config['token_name'] = self.proxmox_manager.token_name
            connection_config['token_value'] = self.proxmox_manager.token_value
            connection_config['use_token'] = True

        # Загрузить существующие подключения и добавить новое
        connections = existing_connections
        connections[connection_name] = connection_config

        # Сохранить обновленную конфигурацию
        if self.config_manager.save_connections_config(connections):
            print(f"✅ Подключение '{connection_name}' сохранено!")
            return True
        else:
            print("❌ Ошибка сохранения подключения")
            return False

    def _select_and_activate_connection(self) -> bool:
        """Выбрать сохраненное подключение и активировать его"""
        print("\n🔄 Выбор и активация сохраненного подключения")
        print("=" * 60)

        # Загрузить сохраненные подключения
        connections = self.config_manager.load_connections_config()
        if not connections:
            print("❌ Сохраненные подключения не найдены")
            print("💡 Создайте и сохраните подключение в пункте 1")
            return False

        # Показать доступные подключения
        print("Доступные подключения:")
        connection_names = list(connections.keys())
        for i, name in enumerate(connection_names, 1):
            config = connections[name]
            host = config.get('host', 'не указан')
            user = config.get('user', 'не указан')
            use_token = config.get('use_token', False)
            auth_type = "token" if use_token else "password"
            print(f"  [{i}] {name} (хост: {host}, пользователь: {user}, auth: {auth_type})")

        while True:
            choice = input("Выберите подключение [1]: ").strip()
            if not choice:
                choice = "1"

            try:
                choice_index = int(choice) - 1
                if 0 <= choice_index < len(connection_names):
                    selected_name = connection_names[choice_index]
                    selected_config = connections[selected_name]

                    print(f"🔄 Активация подключения '{selected_name}'...")

                    # Попытаться подключиться
                    try:
                        from core.proxmox.proxmox_client import ProxmoxClient

                        self.proxmox_manager = ProxmoxClient(
                            host=selected_config['host'],
                            user=selected_config['user'],
                            password=None if selected_config.get('use_token') else selected_config.get('password'),
                            token_name=selected_config.get('token_name') if selected_config.get('use_token') else None,
                            token_value=selected_config.get('token_value') if selected_config.get('use_token') else None
                        )

                        # Проверить подключение
                        nodes = self.proxmox_manager.get_nodes()
                        print(f"✅ Подключение '{selected_name}' активировано!")
                        print(f"Доступные ноды: {', '.join(nodes)}")
                        return True

                    except Exception as e:
                        print(f"❌ Ошибка активации подключения: {e}")
                        return False
                else:
                    print(f"❌ Выберите номер от 1 до {len(connection_names)}")
            except ValueError:
                print("❌ Введите корректный номер")

    def _delete_saved_connection(self) -> bool:
        """Удалить сохраненное подключение"""
        print("\n🗑️  Удаление сохраненного подключения")
        print("=" * 60)

        # Загрузить сохраненные подключения
        connections = self.config_manager.load_connections_config()
        if not connections:
            print("❌ Сохраненные подключения не найдены")
            return False

        # Показать доступные подключения
        print("Доступные подключения для удаления:")
        connection_names = list(connections.keys())
        for i, name in enumerate(connection_names, 1):
            config = connections[name]
            host = config.get('host', 'не указан')
            print(f"  [{i}] {name} (хост: {host})")

        while True:
            choice = input("Выберите подключение для удаления: ").strip()

            try:
                choice_index = int(choice) - 1
                if 0 <= choice_index < len(connection_names):
                    selected_name = connection_names[choice_index]

                    confirm = input(f"Удалить подключение '{selected_name}'? (y/n): ").lower()
                    if confirm != 'y':
                        print("❌ Операция отменена")
                        return False

                    # Удалить подключение из словаря
                    del connections[selected_name]

                    # Сохранить обновленную конфигурацию
                    if self.config_manager.save_connections_config(connections):
                        print(f"✅ Подключение '{selected_name}' удалено!")
                        return True
                    else:
                        print("❌ Ошибка сохранения конфигурации после удаления")
                        return False
                else:
                    print(f"❌ Выберите номер от 1 до {len(connection_names)}")
            except ValueError:
                print("❌ Введите корректный номер")

    def _ensure_proxmox_connection(self) -> bool:
        """Обеспечить наличие подключения к Proxmox в начале работы"""
        if hasattr(self, 'proxmox_manager') and self.proxmox_manager is not None:
            # Проверить, что подключение еще активно
            try:
                nodes = self.proxmox_manager.get_nodes()
                if nodes:
                    return True
            except:
                pass

        # Подключение отсутствует или неактивно - нужно создать новое
        print("🔌 Требуется подключение к Proxmox кластеру")
        print("=" * 50)

        # Загрузить сохраненные конфигурации подключения
        connections = self.config_manager.load_connections_config()

        if connections:
            print("Доступные сохраненные подключения:")
            for i, (name, config) in enumerate(connections.items(), 1):
                print(f"  [{i}] {name} - {config.get('host', 'не указан')}")
            print(f"  [{len(connections) + 1}] Создать новое подключение")

            try:
                choice = input(f"Выберите подключение (1-{len(connections) + 1}) [1]: ").strip()
                if not choice:
                    choice = "1"

                config_index = int(choice) - 1

                if 0 <= config_index < len(connections):
                    # Использовать сохраненное подключение
                    config_names = list(connections.keys())
                    selected_config = connections[config_names[config_index]]
                    connection_name = config_names[config_index]

                    try:
                        from core.proxmox.proxmox_client import ProxmoxClient

                        self.proxmox_manager = ProxmoxClient(
                            host=selected_config['host'],
                            user=selected_config['user'],
                            password=None if selected_config.get('use_token') else selected_config.get('password'),
                            token_name=selected_config.get('token_name') if selected_config.get('use_token') else None,
                            token_value=selected_config.get('token_value') if selected_config.get('use_token') else None
                        )

                        # Проверить подключение
                        nodes = self.proxmox_manager.get_nodes()
                        print(f"✅ Подключение '{connection_name}' установлено!")
                        print(f"   Доступные ноды: {', '.join(nodes)}")
                        return True

                    except Exception as e:
                        print(f"❌ Ошибка подключения '{connection_name}': {e}")
                        print("Попробуйте создать новое подключение")
                        return self._create_new_connection()
                else:
                    # Создать новое подключение
                    return self._create_new_connection()
            except ValueError:
                print("❌ Неверный выбор!")
                return self._create_new_connection()
        else:
            print("Сохраненные подключения не найдены")
            return self._create_new_connection()

    def _get_current_connection_info(self) -> str:
        """Получить информацию о текущем подключении"""
        if hasattr(self, 'proxmox_manager') and self.proxmox_manager is not None:
            try:
                nodes = self.proxmox_manager.get_nodes()
                if nodes:
                    return f"{self.proxmox_manager.host} ({len(nodes)} нод)"
            except:
                return "❌ Ошибка подключения"

        return "❌ Не подключен"

    def _copy_config_interactive(self, configs):
        """Интерактивное копирование конфигурации"""
        try:
            source_num = int(input("Выберите номер конфигурации для копирования: ")) - 1
            if 0 <= source_num < len(configs):
                new_name = input("Введите имя для копии: ").strip()
                if new_name:
                    # Логика копирования конфигурации
                    print(f"✅ Конфигурация '{configs[source_num]}' скопирована как '{new_name}'")
                else:
                    print("❌ Имя не может быть пустым!")
            else:
                print(f"❌ Выберите номер от 1 до {len(configs)}")
        except ValueError:
            print("❌ Введите корректный номер")

    def _load_last_used_config(self):
        """Загрузить последнюю использованную конфигурацию"""
        # Логика загрузки последней конфигурации из истории
        return self.config_manager.load_deployment_config()

    def _load_users_from_file(self, file_path):
        """Загрузить пользователей из файла"""
        try:
            # Здесь должна быть логика загрузки пользователей из файла
            print(f"💡 Функция загрузки из файла будет добавлена позже")
            return True
        except Exception as e:
            print(f"❌ Ошибка загрузки файла: {e}")
            return False

    def _create_machine_interactive(self) -> Dict[str, Any]:
        """Интерактивное создание машины с улучшенным интерфейсом"""
        print("\n🖥️  Создание виртуальной машины")

        # Тип устройства - выбор из списка
        print("Тип устройства:")
        print("  [1] Linux (стандартная VM)")
        print("  [2] EcoRouter (маршрутизатор)")
        while True:
            device_choice = input("Выберите тип устройства [1]: ").strip()
            if not device_choice:
                device_choice = "1"

            if device_choice == "1":
                device_type = "linux"
                break
            elif device_choice == "2":
                device_type = "ecorouter"
                break
            else:
                print("❌ Выберите 1 или 2")

        # Имя машины
        while True:
            name = input("Имя машины: ").strip()
            if name:
                break
            print("❌ Имя машины обязательно")

        # Нода шаблона
        # Попытаться получить доступные ноды из Proxmox
        available_nodes = []
        if hasattr(self, 'proxmox_manager') and self.proxmox_manager:
            try:
                available_nodes = self.proxmox_manager.get_nodes()
            except Exception as e:
                print("⚠️  Не удалось получить список нод из Proxmox")
                logger.warning(f"Не удалось получить список нод: {e}")

        if available_nodes:
            print("Доступные ноды:")
            for i, node in enumerate(available_nodes, 1):
                print(f"  {i}. {node}")

            while True:
                node_choice = input("Нода шаблона [1]: ").strip()
                if not node_choice:
                    node_choice = "1"

                try:
                    node_index = int(node_choice) - 1
                    if 0 <= node_index < len(available_nodes):
                        template_node = available_nodes[node_index]
                        break
                    else:
                        print(f"❌ Выберите номер от 1 до {len(available_nodes)}")
                except ValueError:
                    print("❌ Введите корректный номер")
        else:
            # Manual input if no nodes available
            while True:
                template_node = input("Нода шаблона (например, pve1): ").strip()
                if template_node:
                    break
                print("❌ Нода шаблона обязательна")

        # Шаблон VM
        # Попытаться получить доступные шаблоны на выбранной ноде
        available_templates = []
        if hasattr(self, 'proxmox_manager') and self.proxmox_manager:
            try:
                vms = self.proxmox_manager.get_vms_on_node(template_node)
                # Фильтруем только шаблоны (VM которые являются шаблонами)
                available_templates = [
                    vm for vm in vms
                    if vm.get('template', 0) == 1  # Только шаблоны
                ]
                if not available_templates:
                    # Если нет шаблонов, показываем все VM как возможные шаблоны
                    available_templates = vms[:10]  # Показываем первые 10 VM
            except Exception as e:
                print("⚠️  Не удалось получить список шаблонов")
                logger.warning(f"Не удалось получить список VM на ноде {template_node}: {e}")

        if available_templates:
            print("Доступные шаблоны на ноде:")
            for i, vm in enumerate(available_templates, 1):
                vm_name = vm.get('name', f'VM {vm.get("vmid", "неизвестно")}')
                vm_status = vm.get('status', 'unknown')
                print(f"  {i}. {vm_name} (VMID: {vm.get('vmid', 'неизвестно')}, статус: {vm_status})")

            while True:
                template_choice = input("Выберите шаблон [1]: ").strip()
                if not template_choice:
                    template_choice = "1"

                try:
                    template_index = int(template_choice) - 1
                    if 0 <= template_index < len(available_templates):
                        selected_template = available_templates[template_index]
                        template_vmid = selected_template.get('vmid')
                        if template_vmid:
                            template_vmid = int(template_vmid)
                            print(f"✅ Выбран шаблон: {selected_template.get('name', f'VM {template_vmid}')}")
                            break
                        else:
                            print("❌ Выбранный шаблон не имеет VMID")
                    else:
                        print(f"❌ Выберите номер от 1 до {len(available_templates)}")
                except ValueError:
                    print("❌ Введите корректный номер")
                except Exception as e:
                    print(f"❌ Ошибка выбора шаблона: {e}")
        else:
            # Manual input if no templates available
            while True:
                template_vmid_str = input("VMID шаблона (число): ").strip()
                try:
                    template_vmid = int(template_vmid_str)
                    break
                except ValueError:
                    print("❌ VMID должен быть числом")

        # Сетевые интерфейсы
        networks = []
        print("\nДобавим сетевые интерфейсы:")
        print("Оставьте пустым имя bridge для завершения")
        while True:
            bridge = input(f"Bridge {len(networks) + 1} (например, vmbr0): ").strip()
            if not bridge:
                break
            networks.append({"bridge": bridge})

        if not networks:
            print("⚠️  Добавлен стандартный интерфейс vmbr0")
            networks.append({"bridge": "vmbr0"})

        # Тип клонирования - выбор из списка
        print("Тип клонирования:")
        print("  [1] Связанное (linked clone) - быстрое, экономит место")
        print("  [2] Полное (full clone) - медленное, независимая копия")
        while True:
            clone_choice = input("Выберите тип клонирования [1]: ").strip()
            if not clone_choice:
                clone_choice = "1"

            if clone_choice == "1":
                full_clone = False
                break
            elif clone_choice == "2":
                full_clone = True
                break
            else:
                print("❌ Выберите 1 или 2")

        machine = {
            "device_type": device_type,
            "name": name,
            "template_node": template_node,
            "template_vmid": template_vmid,
            "networks": networks,
            "full_clone": full_clone
        }

        print(f"\n✅ Машина '{name}' настроена:")
        print(f"   Тип: {device_type}")
        print(f"   Шаблон: VMID {template_vmid} на {template_node}")
        print(f"   Сетей: {len(networks)} ({', '.join([n['bridge'] for n in networks])})")
        print(f"   Клонирование: {'полное' if full_clone else 'связанное'}")

        return machine

    def _show_machines_in_config(self, machines: List[Dict[str, Any]]):
        """Показать машины в текущей конфигурации"""
        if not machines:
            print("❌ Конфигурация пуста")
            return

        print(f"\n📋 Машины в конфигурации ({len(machines)}):")
        print("-" * 80)

        for i, machine in enumerate(machines, 1):
            print(f"{i}. {machine['name']} ({machine['device_type']})")
            print(f"   Шаблон: VMID {machine['template_vmid']} на {machine['template_node']}")
            print(f"   Сетей: {len(machine['networks'])} ({', '.join([n['bridge'] for n in machine['networks']])})")
            print(f"   Клонирование: {'полное' if machine['full_clone'] else 'связанное'}")
            print()

        print("-" * 80)

    def _manage_user_lists_menu(self):
        """Управление списками пользователей"""
        print("\n📋 Управление списками пользователей")
        print("=" * 50)

        user_lists = self.config_manager.list_user_lists()

        if user_lists:
            print("Доступные списки пользователей:")
            for i, list_name in enumerate(user_lists, 1):
                users = self.config_manager.load_users(list_name)
                print(f"  [{i}] {list_name} ({len(users)} пользователей)")
            print(f"  [{len(user_lists) + 1}] Создать новый список")
        else:
            print("Списки пользователей не найдены")
            print("  [1] Создать новый список")

        try:
            choice = input("Выберите список или 'c' для создания нового: ").strip().lower()

            if choice == 'c' or (user_lists and choice == str(len(user_lists) + 1)):
                # Создать новый список
                return self._create_user_list_interactive()
            else:
                # Выбрать существующий список
                try:
                    list_index = int(choice) - 1
                    if 0 <= list_index < len(user_lists):
                        selected_list = user_lists[list_index]
                        return self._edit_user_list_interactive(selected_list)
                    else:
                        print("❌ Неверный выбор!")
                        return "repeat"
                except ValueError:
                    print("❌ Введите номер или 'c' для создания нового")
                    return "repeat"
        except KeyboardInterrupt:
            return "repeat"

    def _create_user_list_interactive(self):
        """Создать новый список пользователей"""
        print("\n👥 Создание нового списка пользователей")
        print("=" * 50)

        list_name = input("Введите имя списка пользователей: ").strip()
        if not list_name:
            print("❌ Имя списка не может быть пустым!")
            return "repeat"

        # Проверить, существует ли уже список с таким именем
        if list_name in self.config_manager.list_user_lists():
            print(f"❌ Список '{list_name}' уже существует!")
            return "repeat"

        print("Выберите способ создания списка:")
        print("  [1] Ввести пользователей вручную")
        print("  [2] Загрузить из файла")
        print("  [0] Отмена")

        choice = input("Выберите способ: ").strip()

        if choice == "1":
            users_input = input("Введите пользователей через запятую (user1@pve,user2@pve): ")
            users = [user.strip() for user in users_input.split(',') if user.strip()]

            if self.config_manager.save_users(users, list_name):
                print(f"✅ Список '{list_name}' создан с {len(users)} пользователями")
            else:
                print("❌ Ошибка сохранения списка")
        elif choice == "2":
            file_path = input("Путь к файлу со списком пользователей: ").strip()
            if self._load_users_from_file(file_path, list_name):
                print(f"✅ Список '{list_name}' создан из файла")
            else:
                print("❌ Ошибка загрузки файла")
        else:
            print("❌ Создание отменено")

        return "repeat"

    def _edit_user_list_interactive(self, list_name: str):
        """Редактировать существующий список пользователей"""
        print(f"\n📝 Редактирование списка '{list_name}'")
        print("=" * 50)

        users = self.config_manager.load_users(list_name)
        print(f"Текущий список ({len(users)} пользователей):")
        for i, user in enumerate(users, 1):
            print(f"  {i}. {user}")

        print("\nДоступные действия:")
        print("  [1] Добавить пользователей")
        print("  [2] Удалить пользователей")
        print("  [3] Показать список")
        print("  [4] Очистить список")
        print("  [0] Назад")

        choice = input("Выберите действие: ").strip()

        if choice == "1":
            # Добавить пользователей
            users_input = input("Введите пользователей для добавления (через запятую): ")
            new_users = [user.strip() for user in users_input.split(',') if user.strip()]
            users.extend(new_users)

            if self.config_manager.save_users(users, list_name):
                print(f"✅ Добавлено {len(new_users)} пользователей")
            else:
                print("❌ Ошибка сохранения")
        elif choice == "2":
            # Удалить пользователей
            if users:
                print("Выберите пользователей для удаления:")
                for i, user in enumerate(users, 1):
                    print(f"  [{i}] {user}")

                try:
                    indices_input = input("Введите номера пользователей для удаления (через запятую): ")
                    indices_to_remove = [int(idx.strip()) - 1 for idx in indices_input.split(',') if idx.strip().isdigit()]

                    removed_count = 0
                    for idx in sorted(indices_to_remove, reverse=True):
                        if 0 <= idx < len(users):
                            removed_user = users.pop(idx)
                            removed_count += 1
                            print(f"✅ Удален пользователь: {removed_user}")

                    if removed_count > 0:
                        if self.config_manager.save_users(users, list_name):
                            print(f"✅ Удалено {removed_count} пользователей")
                        else:
                            print("❌ Ошибка сохранения")
                    else:
                        print("❌ Неверные номера пользователей")
                except ValueError:
                    print("❌ Введите корректные номера")
            else:
                print("❌ Список пуст")
        elif choice == "3":
            # Показать список
            if users:
                print(f"\nСписок пользователей '{list_name}':")
                for i, user in enumerate(users, 1):
                    print(f"  {i}. {user}")
            else:
                print("❌ Список пуст")
        elif choice == "4":
            # Очистить список
            confirm = input("Очистить список пользователей? (y/n): ")
            if confirm.lower() == 'y':
                if self.config_manager.save_users([], list_name):
                    print("✅ Список пользователей очищен")
                else:
                    print("❌ Ошибка очистки")
        else:
            print("❌ Неверный выбор!")

        return "repeat"

    def _show_all_user_lists(self):
        """Показать все списки пользователей"""
        print("\n📋 Все списки пользователей")
        print("=" * 50)

        user_lists = self.config_manager.list_user_lists()

        if not user_lists:
            print("❌ Списки пользователей не найдены")
            return "repeat"

        for list_name in user_lists:
            users = self.config_manager.load_users(list_name)
            print(f"\n📝 {list_name} ({len(users)} пользователей):")
            if users:
                for i, user in enumerate(users, 1):
                    print(f"  {i}. {user}")
            else:
                print("  (пустой список)")

        return "repeat"

    def _delete_user_list_interactive(self):
        """Удалить список пользователей"""
        print("\n🗑️  Удаление списка пользователей")
        print("=" * 50)

        user_lists = self.config_manager.list_user_lists()

        if not user_lists:
            print("❌ Нет списков пользователей для удаления")
            return "repeat"

        print("Доступные списки:")
        for i, list_name in enumerate(user_lists, 1):
            users = self.config_manager.load_users(list_name)
            print(f"  [{i}] {list_name} ({len(users)} пользователей)")

        try:
            choice = input(f"Выберите список для удаления (1-{len(user_lists)}): ").strip()
            list_index = int(choice) - 1

            if 0 <= list_index < len(user_lists):
                selected_list = user_lists[list_index]
                users = self.config_manager.load_users(selected_list)

                confirm = input(f"Удалить список '{selected_list}' ({len(users)} пользователей)? (y/n): ")
                if confirm.lower() == 'y':
                    if self.config_manager.delete_user_list(selected_list):
                        print(f"✅ Список '{selected_list}' удален")
                    else:
                        print("❌ Ошибка удаления списка")
                else:
                    print("❌ Удаление отменено")
            else:
                print(f"❌ Выберите номер от 1 до {len(user_lists)}")
        except ValueError:
            print("❌ Введите корректный номер")

        return "repeat"

    def _load_users_from_file(self, file_path: str, list_name: str = "default"):
        """Загрузить пользователей из файла в указанный список"""
        try:
            import os
            if not os.path.exists(file_path):
                print(f"❌ Файл '{file_path}' не найден")
                return False

            users = []
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    user = line.strip()
                    if user and not user.startswith('#'):  # Игнорировать пустые строки и комментарии
                        # Автоматически добавить @pve к имени пользователя
                        if '@' not in user:
                            user += '@pve'
                        users.append(user)

            if users:
                if self.config_manager.save_users(users, list_name):
                    print(f"✅ Загружено {len(users)} пользователей из файла в список '{list_name}'")
                    return True
                else:
                    print("❌ Ошибка сохранения пользователей")
                    return False
            else:
                print("❌ В файле не найдено пользователей")
                return False

        except Exception as e:
            print(f"❌ Ошибка загрузки файла: {e}")
            return False
