import yaml
import os
from typing import Dict, List, Any

CONFIG_FILE = "deployment_config.yml"
USERS_FILE = "users_list.yml"

class ConfigManager:
    @staticmethod
    def create_deployment_config() -> Dict[str, Any]:
        """Создание конфигурации развертывания через диалог с пользователем"""
        config = {}
        
        try:
            num_machines = int(input("Сколько должно быть машин в конфигурации? "))
            config['machines'] = []
            
            for i in range(num_machines):
                print(f"\n--- Конфигурация машины #{i+1} ---")
                machine_config = {}
                
                machine_config['name'] = input("Имя создаваемой машины: ")
                machine_config['template_vmid'] = int(input("VMID шаблона для клонирования: "))
                machine_config['template_node'] = input("Нода, на которой находится шаблон: ")
                
                # Конфигурация сетевых адаптеров
                num_networks = int(input("Сколько нужно сетевых адаптеров? "))
                machine_config['networks'] = []
                
                for j in range(num_networks):
                    bridge = input(f"Имя bridge для сетевой карты {j+1} (например vmbr0): ")
                    machine_config['networks'].append({'bridge': bridge})
                
                config['machines'].append(machine_config)
            
            # Сохранение в файл
            with open(CONFIG_FILE, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
            print(f"\nКонфигурация сохранена в файл: {CONFIG_FILE}")
            return config
            
        except ValueError as e:
            print(f"Ошибка ввода: {e}")
            return {}
    
    @staticmethod
    def load_deployment_config() -> Dict[str, Any]:
        """Загрузка конфигурации из файла"""
        if not os.path.exists(CONFIG_FILE):
            print("Файл конфигурации не найден!")
            return {}
        
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f)
    
    @staticmethod
    def save_users(users: List[str]) -> bool:
        """Сохранение списка пользователей"""
        try:
            users_data = {'users': users}
            with open(USERS_FILE, 'w') as f:
                yaml.dump(users_data, f, default_flow_style=False, allow_unicode=True)
            print(f"Список пользователей сохранен в: {USERS_FILE}")
            return True
        except Exception as e:
            print(f"Ошибка сохранения пользователей: {e}")
            return False
    
    @staticmethod
    def load_users() -> List[str]:
        """Загрузка списка пользователей"""
        if not os.path.exists(USERS_FILE):
            return []
        
        with open(USERS_FILE, 'r') as f:
            data = yaml.safe_load(f)
            return data.get('users', [])