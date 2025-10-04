from app.core.config import ConfigManager
from app.core.proxmox_manager import ProxmoxManager
from app.core.vm_deployer import VMDeployer
from app.core.user_manager import UserManager
from app.utils.logger import logger
from app.utils.console import emphasize

class MainMenu:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.proxmox_manager = ProxmoxManager()
        self.vm_deployer = None
        self.user_manager = None
        self._setup_proxmox_connection()
    
    def _setup_proxmox_connection(self):
        logger.info("Настройка подключения к Proxmox")

        # Получаем список сохраненных конфигураций подключения
        connection_names = self.config_manager.list_connection_configs()

        if connection_names:
            print("Найденные конфигурации подключения:")
            connections = self.config_manager.load_connections_config()

            for i, name in enumerate(connection_names, 1):
                config = connections[name]
                print(f"{i}. {name} | {config.get('host')} | {config.get('user')}")

            print(f"{len(connection_names) + 1}. Ввести новые данные подключения")
            print("0. Выход")

            while True:
                try:
                    choice = input("Выберите конфигурацию (номер): ").strip()
                    if choice == "0":
                        logger.info("Выход из программы")
                        exit(0)

                    choice_num = int(choice)
                    if 1 <= choice_num <= len(connection_names):
                        selected_name = connection_names[choice_num - 1]
                        selected_config = connections[selected_name]

                        # Используем выбранную конфигурацию
                        host = selected_config['host']
                        user = selected_config['user']
                        use_token = selected_config['use_token']

                        if use_token:
                            token_name = selected_config.get('token_name')
                            token_value = selected_config.get('token_value')
                            success_conn = self.proxmox_manager.connect(host, user, token_name=token_name, token_value=token_value)
                        else:
                            password = selected_config.get('password')
                            success_conn = self.proxmox_manager.connect(host, user, password=password)

                        if success_conn:
                            logger.success(f"Успешное подключение к Proxmox с использованием конфигурации '{selected_name}'")
                            self.vm_deployer = VMDeployer(self.proxmox_manager)
                            self.user_manager = UserManager(self.proxmox_manager)
                            return
                        else:
                            logger.warning(f"Не удалось подключиться с использованием конфигурации '{selected_name}'")
                            retry = input("Попробовать другую конфигурацию? (y/n): ").lower() == 'y'
                            if not retry:
                                break
                    elif choice_num == len(connection_names) + 1:
                        break
                    else:
                        print(f"Выберите номер от 1 до {len(connection_names) + 1}")
                except ValueError:
                    print("Введите корректный номер")
        else:
            print("Сохраненные конфигурации подключения не найдены")

        # Ввод новых данных подключения
        print("\nВведите данные для подключения:")
        host = input("Адрес Proxmox сервера (например: 192.168.1.100:8006): ")
        user = input("Имя пользователя (например: root@pam): ")
        use_token = input("Использовать токен для аутентификации? (y/n): ").lower() == 'y'

        if use_token:
            token_name = input("Имя токена: ")
            token_value = input("Значение токена: ")
            success_conn = self.proxmox_manager.connect(host, user, token_name=token_name, token_value=token_value)
        else:
            password = input("Пароль: ")
            success_conn = self.proxmox_manager.connect(host, user, password=password)

        if success_conn:
            logger.success("Успешное подключение к Proxmox")
            self.vm_deployer = VMDeployer(self.proxmox_manager)
            self.user_manager = UserManager(self.proxmox_manager)

            # Предлагаем сохранить конфигурацию подключения
            save_config = input("Сохранить конфигурацию подключения для будущих сессий? (y/n): ").lower() == 'y'
            if save_config:
                config_name = input("Введите имя для конфигурации подключения: ").strip()
                if config_name:
                    self.config_manager.save_connection_config(config_name, host, user, use_token,
                                                             token_name if use_token else None,
                                                             token_value if use_token else None,
                                                             password if not use_token else None)
        else:
            logger.error("Не удалось подключиться к Proxmox")
    
    def show(self):
        while True:
            print("\n=== Главное меню Proxmox Deployer ===")
            print("1. Создать конфигурацию для развертывания")
            print("2. Управление конфигурациями")
            print("3. Указать список пользователей")
            print("4. Развернуть конфигурацию")
            print("5. Удалить машины по списку пользователей")
            print("6. Удалить машины отдельного пользователя")
            print("7. Управление конфигурацией подключения")
            print("0. Выход")
            choice = input("Выберите действие: ")
            if choice == "1":
                # Передадим список нод, чтобы решать — запрашивать ли template_node
                nodes = self.proxmox_manager.get_nodes()
                self.config_manager.create_deployment_config(nodes, self.proxmox_manager)
            elif choice == "2":
                self._manage_configs_menu()
            elif choice == "3":
                self._manage_users_menu()
            elif choice == "4":
                self._deploy_menu()
            elif choice == "5":
                self._delete_all_users_resources()
            elif choice == "6":
                self._delete_single_user_resources()
            elif choice == "7":
                self._manage_connection_config_menu()
            elif choice == "0":
                logger.info("Выход из программы")
                break
            else:
                logger.warning("Неверный выбор!")
    
    def _manage_users_menu(self):
        logger.info("Управление пользователями")
        print("\n=== Управление пользователями ===")
        print("1. Ввести список пользователей вручную")
        print("2. Загрузить пользователей из файла")
        print("0. Назад")

        choice = input("Выберите действие: ")
        if choice == "1":
            users_input = input("Введите список пользователей через запятую (формат: user1@pve,user2@pve): ")
            users = [user.strip() for user in users_input.split(',') if user.strip()]
            if users:
                if self.config_manager.save_users(users):
                    logger.success("Список пользователей сохранён")
                else:
                    logger.error("Ошибка сохранения списка пользователей")
            else:
                logger.warning("Список пользователей пуст!")
        elif choice == "2":
            file_path = input("Введите путь к файлу со списком пользователей: ").strip()
            if file_path:
                if self.config_manager.save_users_from_file(file_path):
                    logger.success("Пользователи загружены из файла")
                else:
                    logger.error("Ошибка загрузки пользователей из файла")
            else:
                logger.warning("Путь к файлу не указан!")
        elif choice == "0":
            return
        else:
            logger.warning("Неверный выбор!")
    
    def _manage_configs_menu(self):
        """Меню управления конфигурациями развертывания"""
        while True:
            print("\n=== Управление конфигурациями ===")
            print("1. Создать новую конфигурацию")
            print("2. Показать список конфигураций")
            print("3. Удалить конфигурацию")
            print("0. Назад")

            choice = input("Выберите действие: ")
            if choice == "1":
                config_name = input("Введите имя новой конфигурации: ").strip()
                if config_name:
                    nodes = self.proxmox_manager.get_nodes()
                    self.config_manager.create_named_config(config_name, nodes, self.proxmox_manager)
                else:
                    logger.warning("Имя конфигурации не может быть пустым!")
            elif choice == "2":
                configs = self.config_manager.list_configs()
                if configs:
                    print("\nДоступные конфигурации:")
                    for i, config_name in enumerate(configs, 1):
                        print(f"{i}. {config_name}")
                else:
                    print("Нет доступных конфигураций")
            elif choice == "3":
                config_name = input("Введите имя конфигурации для удаления: ").strip()
                if config_name:
                    confirm = input(f"Удалить конфигурацию '{config_name}'? (y/n): ")
                    if confirm.lower() == 'y':
                        self.config_manager.delete_config(config_name)
                else:
                    logger.warning("Имя конфигурации не может быть пустым!")
            elif choice == "0":
                break
            else:
                logger.warning("Неверный выбор!")

    def _deploy_menu(self):
        if not self.vm_deployer:
            logger.error("Нет подключения к Proxmox!")
            return

        # Выбор конфигурации для развертывания
        configs = self.config_manager.list_configs()
        if not configs:
            logger.warning("Нет доступных конфигураций! Создайте конфигурацию в меню 2.")
            return

        print("\nДоступные конфигурации:")
        for i, config_name in enumerate(configs, 1):
            print(f"{i}. {config_name}")

        while True:
            try:
                choice = input("Выберите конфигурацию (номер) или 'default' для использования deployment_config.yml: ")
                if choice.lower() == 'default' or choice == '':
                    config = self.config_manager.load_deployment_config()
                    if not config:
                        logger.warning("Файл deployment_config.yml не найден!")
                        return
                    break
                else:
                    config_index = int(choice) - 1
                    if 0 <= config_index < len(configs):
                        config = self.config_manager.load_config(configs[config_index])
                        if not config:
                            logger.warning(f"Не удалось загрузить конфигурацию '{configs[config_index]}'")
                            return
                        break
                    else:
                        print(f"Выберите номер от 1 до {len(configs)}")
            except ValueError:
                print("Введите номер или 'default'")

        users = self.config_manager.load_users()
        if not users:
            logger.warning("Необходимо указать список пользователей!")
            return

        nodes = self.proxmox_manager.get_nodes()
        node_selection = "auto"
        target_node = None
        if len(nodes) > 1:
            print("\n--- Выбор стратегии размещения ---")
            print("Доступные ноды:", ", ".join(nodes))
            print("1. Указать конкретную ноду")
            print("2. Распределить равномерно")
            choice = input("Выберите стратегию: ")
            if choice == "1":
                node_selection = "specific"
                target_node = input("Введите имя целевой ноды: ")
            elif choice == "2":
                node_selection = "balanced"

        logger.info("Начало развертывания")
        results = self.vm_deployer.deploy_configuration(users, config, node_selection, target_node)
        print("\n=== Результаты развертывания ===")
        for user, password in results.items():
            print(f"Пользователь: {emphasize(user)} | Пароль: {emphasize(password)}")
    
    def _delete_all_users_resources(self):
        users = self.config_manager.load_users()
        if not users:
            logger.warning("Список пользователей пуст!")
            return
        confirm = input(f"Вы уверены, что хотите удалить ресурсы {len(users)} пользователей? (y/n): ")
        if confirm.lower() == 'y':
            logger.info(f"🗑️ Удаление ресурсов {len(users)} пользователей...")
            deleted_count = 0
            failed_users = []

            # Используем оптимизированную пакетную обработку
            results = self.user_manager.delete_user_resources_batch(users)

            # Вывод итогов только если есть успешные удаления или ошибки
            if results['successful'] or results['failed']:
                logger.info(f"📊 Итоги удаления: успешно {len(results['successful'])}, ошибок {len(results['failed'])}, пропущено {len(results['skipped'])}")
                if results['failed']:
                    logger.warning(f"⚠️ Не удалось удалить ресурсы следующих пользователей: {', '.join(results['failed'])}")

            # Автоматическая очистка неиспользуемых сетевых адаптеров
            logger.info("🧹 Очистка неиспользуемых сетевых адаптеров...")
            self._cleanup_unused_bridges()
    
    def _delete_single_user_resources(self):
        user = input("Введите имя пользователя для удаления: ")
        if user:
            confirm = input(f"Вы уверены, что хотите удалить ресурсы пользователя {user}? (y/n): ")
            if confirm.lower() == 'y':
                self.user_manager.delete_user_resources(user)
                logger.success(f"Ресурсы пользователя {user} удалены")

    def _cleanup_unused_bridges(self):
        """Найти и удалить неиспользуемые сетевые адаптеры"""
        if not self.proxmox_manager or not self.proxmox_manager.proxmox:
            logger.error("Нет подключения к Proxmox!")
            return

        nodes = self.proxmox_manager.get_nodes()
        if not nodes:
            logger.warning("Не найдено доступных нод!")
            return

        total_bridges_found = 0
        total_bridges_deleted = 0

        for node in nodes:
            # Получить список всех bridge на ноде
            all_bridges = self.proxmox_manager.list_bridges(node)
            unused_bridges = []

            for bridge in all_bridges:
                # Пропустить vmbr0 - системный bridge
                if bridge == 'vmbr0':
                    continue

                # Проверить, используется ли bridge
                if not self.proxmox_manager.bridge_in_use(node, bridge):
                    unused_bridges.append(bridge)
                    total_bridges_found += 1

            # Удалить неиспользуемые bridge
            for bridge in unused_bridges:
                if self.proxmox_manager.delete_bridge(node, bridge):
                    total_bridges_deleted += 1

        # Вывод результатов
        if total_bridges_deleted > 0:
            logger.success(f"Очистка завершена: удалено {total_bridges_deleted} неиспользуемых bridge")
            print("⚠️  НАПОМИНАНИЕ: После удаления сетевых bridge рекомендуется перезагрузить сеть на нодах:")
            print(f"   Выполните команды на каждой ноде: systemctl restart networking")
            print(f"   Или: systemctl restart systemd-networkd")
        else:
            logger.info("Неиспользуемых bridge не найдено")

    def _manage_connection_config_menu(self):
        """Меню управления конфигурациями подключения"""
        while True:
            print("\n=== Управление конфигурациями подключения ===")

            # Получаем список сохраненных конфигураций подключения
            connection_names = self.config_manager.list_connection_configs()

            if connection_names:
                print("Сохраненные конфигурации подключения:")
                connections = self.config_manager.load_connections_config()

                for i, name in enumerate(connection_names, 1):
                    config = connections[name]
                    print(f"{i}. {name} | {config.get('host')} | {config.get('user')}")

                print(f"\nДоступные действия:")
                print(f"{len(connection_names) + 1}. Создать новую конфигурацию подключения")
                print(f"{len(connection_names) + 2}. Показать детали конфигурации")
                print(f"{len(connection_names) + 3}. Удалить конфигурацию подключения")
                print("0. Назад")
            else:
                print("Сохраненные конфигурации подключения не найдены")
                print("\nДоступные действия:")
                print("1. Создать новую конфигурацию подключения")
                print("0. Назад")

            choice = input("Выберите действие: ")

            if connection_names:
                max_choice = len(connection_names) + 3
                if choice == "0":
                    break
                elif choice == str(len(connection_names) + 1):
                    # Создать новую конфигурацию
                    self._create_new_connection_config()
                elif choice == str(len(connection_names) + 2):
                    # Показать детали конфигурации
                    while True:
                        print("\nВыберите конфигурацию для просмотра деталей:")
                        for i, name in enumerate(connection_names, 1):
                            print(f"{i}. {name}")
                        print("0. Назад")

                        detail_choice = input("Выберите конфигурацию: ")
                        if detail_choice == "0":
                            break

                        try:
                            detail_num = int(detail_choice)
                            if 1 <= detail_num <= len(connection_names):
                                selected_name = connection_names[detail_num - 1]
                                selected_config = connections[selected_name]

                                print(f"\nДетали конфигурации '{selected_name}':")
                                print(f"  Сервер: {selected_config.get('host')}")
                                print(f"  Пользователь: {selected_config.get('user')}")
                                if selected_config.get('use_token'):
                                    print(f"  Тип аутентификации: Токен")
                                    print(f"  Имя токена: {selected_config.get('token_name')}")
                                    print(f"  Значение токена: {'*' * len(selected_config.get('token_value', ''))}")
                                else:
                                    print(f"  Тип аутентификации: Пароль")
                                    print(f"  Пароль: {'*' * len(selected_config.get('password', ''))}")
                                input("\nНажмите Enter для продолжения...")
                                break
                            else:
                                print(f"Выберите номер от 1 до {len(connection_names)}")
                        except ValueError:
                            print("Введите корректный номер")
                elif choice == str(len(connection_names) + 3):
                    # Удалить конфигурацию
                    while True:
                        print("\nВыберите конфигурацию для удаления:")
                        for i, name in enumerate(connection_names, 1):
                            print(f"{i}. {name}")
                        print("0. Назад")

                        delete_choice = input("Выберите конфигурацию: ")
                        if delete_choice == "0":
                            break

                        try:
                            delete_num = int(delete_choice)
                            if 1 <= delete_num <= len(connection_names):
                                selected_name = connection_names[delete_num - 1]
                                confirm = input(f"Вы уверены, что хотите удалить конфигурацию '{selected_name}'? (y/n): ")
                                if confirm.lower() == 'y':
                                    self.config_manager.delete_connection_config(selected_name)
                                break
                            else:
                                print(f"Выберите номер от 1 до {len(connection_names)}")
                        except ValueError:
                            print("Введите корректный номер")
                else:
                    logger.warning("Неверный выбор!")
            else:
                # Если нет сохраненных конфигураций
                if choice == "0":
                    break
                elif choice == "1":
                    self._create_new_connection_config()
                else:
                    logger.warning("Неверный выбор!")

    def _create_new_connection_config(self):
        """Создать новую конфигурацию подключения"""
        print("\nВведите данные для подключения:")
        host = input("Адрес Proxmox сервера (например: 192.168.1.100:8006): ")
        user = input("Имя пользователя (например: root@pam): ")
        use_token = input("Использовать токен для аутентификации? (y/n): ").lower() == 'y'

        if use_token:
            token_name = input("Имя токена: ")
            token_value = input("Значение токена: ")
            success_conn = self.proxmox_manager.connect(host, user, token_name=token_name, token_value=token_value)
        else:
            password = input("Пароль: ")
            success_conn = self.proxmox_manager.connect(host, user, password=password)

        if success_conn:
            logger.success("Успешное подключение к Proxmox")
            self.vm_deployer = VMDeployer(self.proxmox_manager)
            self.user_manager = UserManager(self.proxmox_manager)

            # Предлагаем сохранить конфигурацию подключения
            save_config = input("Сохранить конфигурацию подключения? (y/n): ").lower() == 'y'
            if save_config:
                config_name = input("Введите имя для конфигурации подключения: ").strip()
                if config_name:
                    self.config_manager.save_connection_config(config_name, host, user, use_token,
                                                             token_name if use_token else None,
                                                             token_value if use_token else None,
                                                             password if not use_token else None)
        else:
            logger.error("Не удалось подключиться к Proxmox")
