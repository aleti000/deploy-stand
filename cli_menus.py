from config import ConfigManager
from proxmox_manager import ProxmoxManager
from vm_deployer import VMDeployer
import os

class MainMenu:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.proxmox_manager = ProxmoxManager()
        self.vm_deployer = None
        self._setup_proxmox_connection()
    
    def _setup_proxmox_connection(self):
        """Настройка подключения к Proxmox"""
        print("=== Настройка подключения к Proxmox ===")
        
        host = input("Адрес Proxmox сервера (например: 192.168.1.100:8006): ")
        user = input("Имя пользователя (например: root@pam): ")
        
        use_token = input("Использовать токен для аутентификации? (y/n): ").lower() == 'y'
        
        if use_token:
            token_name = input("Имя токена: ")
            token_value = input("Значение токена: ")
            success = self.proxmox_manager.connect(host, user, 
                                                 token_name=token_name, 
                                                 token_value=token_value)
        else:
            password = input("Пароль: ")
            success = self.proxmox_manager.connect(host, user, password=password)
        
        if success:
            self.vm_deployer = VMDeployer(self.proxmox_manager)
    
    def show(self):
        """Главное меню"""
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
                self.config_manager.create_deployment_config()
            elif choice == "2":
                self._manage_users_menu()
            elif choice == "3":
                self._deploy_menu()
            elif choice == "4":
                self._delete_all_users_resources()
            elif choice == "5":
                self._delete_single_user_resources()
            elif choice == "0":
                print("Выход из программы")
                break
            else:
                print("Неверный выбор!")
    
    def _manage_users_menu(self):
        """Меню управления пользователями"""
        print("\n--- Управление пользователями ---")
        users_input = input("Введите список пользователей через запятую (формат: user1@pve,user2@pve): ")
        users = [user.strip() for user in users_input.split(',') if user.strip()]
        
        if users:
            self.config_manager.save_users(users)
        else:
            print("Список пользователей пуст!")
    
    def _deploy_menu(self):
        """Меню развертывания конфигурации"""
        if not self.vm_deployer:
            print("Нет подключения к Proxmox!")
            return
        
        config = self.config_manager.load_deployment_config()
        users = self.config_manager.load_users()
        
        if not config or not users:
            print("Необходимо создать конфигурацию и указать пользователей!")
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
        
        print("\n--- Начало развертывания ---")
        results = self.vm_deployer.deploy_configuration(users, config, node_selection, target_node)
        
        print("\n=== Результаты развертывания ===")
        for user, password in results.items():
            print(f"Пользователь: {user}, Пароль: {password}")
    
    def _delete_all_users_resources(self):
        """Удаление ресурсов всех пользователей из списка"""
        users = self.config_manager.load_users()
        if not users:
            print("Список пользователей пуст!")
            return
        
        confirm = input(f"Вы уверены, что хотите удалить ресурсы {len(users)} пользователей? (y/n): ")
        if confirm.lower() == 'y':
            for user in users:
                print(f"Удаление ресурсов пользователя: {user}")
                self.user_manager.delete_user_resources(user)
    
    def _delete_single_user_resources(self):
        """Удаление ресурсов отдельного пользователя"""
        user = input("Введите имя пользователя для удаления: ")
        if user:
            confirm = input(f"Вы уверены, что хотите удалить ресурсы пользователя {user}? (y/n): ")
            if confirm.lower() == 'y':
                self.user_manager.delete_user_resources(user)