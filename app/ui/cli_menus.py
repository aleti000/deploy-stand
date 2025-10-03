from app.core.config import ConfigManager
from app.core.proxmox_manager import ProxmoxManager
from app.core.vm_deployer import VMDeployer
from app.core.user_manager import UserManager
from app.utils.logger import logger

class MainMenu:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.proxmox_manager = ProxmoxManager()
        self.vm_deployer = None
        self.user_manager = None
        self._setup_proxmox_connection()
    
    def _setup_proxmox_connection(self):
        logger.info("Настройка подключения к Proxmox")
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
        else:
            logger.error("Не удалось подключиться к Proxmox")
    
    def show(self):
        while True:
            print("\n=== Главное меню Proxmox Deployer ===")
            print("1. Создать конфигурацию для развертывания")
            print("2. Указать список пользователей")
            print("3. Развернуть конфигурацию")
            print("4. Удалить машины по списку пользователей")
            print("5. Удалить машины отдельного пользователя")
            print("0. Выход")
            choice = input("Выберите действие: ")
            if choice == "1":
                # Передадим список нод, чтобы решать — запрашивать ли template_node
                nodes = self.proxmox_manager.get_nodes()
                self.config_manager.create_deployment_config(nodes)
            elif choice == "2":
                self._manage_users_menu()
            elif choice == "3":
                self._deploy_menu()
            elif choice == "4":
                self._delete_all_users_resources()
            elif choice == "5":
                self._delete_single_user_resources()
            elif choice == "0":
                logger.info("Выход из программы")
                break
            else:
                logger.warning("Неверный выбор!")
    
    def _manage_users_menu(self):
        logger.info("Управление пользователями")
        users_input = input("Введите список пользователей через запятую (формат: user1@pve,user2@pve): ")
        users = [user.strip() for user in users_input.split(',') if user.strip()]
        if users:
            if self.config_manager.save_users(users):
                logger.success("Список пользователей сохранён")
            else:
                logger.error("Ошибка сохранения списка пользователей")
        else:
            logger.warning("Список пользователей пуст!")
    
    def _deploy_menu(self):
        if not self.vm_deployer:
            logger.error("Нет подключения к Proxmox!")
            return
        config = self.config_manager.load_deployment_config()
        users = self.config_manager.load_users()
        if not config or not users:
            logger.warning("Необходимо создать конфигурацию и указать пользователей!")
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
            logger.info(f"Удаление ресурсов {len(users)} пользователей...")
            for user in users:
                self.user_manager.delete_user_resources(user)

            # Автоматическая очистка неиспользуемых сетевых адаптеров
            logger.info("Очистка неиспользуемых сетевых адаптеров...")
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
        else:
            logger.info("Неиспользуемых bridge не найдено")
