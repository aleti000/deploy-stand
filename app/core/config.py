import yaml
import os
from typing import Dict, List, Any

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
os.makedirs(CONFIG_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIR, 'deployment_config.yml')
USERS_FILE = os.path.join(CONFIG_DIR, 'users_list.yml')

class ConfigManager:
    @staticmethod
    def create_deployment_config(nodes: list[str] | None = None) -> Dict[str, Any]:
        config = {}
        try:
            num_machines = int(input("Сколько должно быть машин в конфигурации? "))
            config['machines'] = []
            for i in range(num_machines):
                print(f"\n--- Конфигурация машины #{i+1} ---")
                machine_config = {}
                print("Тип устройства:")
                print("1) linux")
                print("2) ecorouter")
                dtype_choice = input("Выберите тип (1/2) [1]: ").strip()
                machine_config['device_type'] = 'ecorouter' if dtype_choice == '2' else 'linux'
                machine_config['name'] = input("Имя создаваемой машины: ")
                machine_config['template_vmid'] = int(input("VMID шаблона для клонирования: "))
                # Запрашивать ноду шаблона только если в кластере > 1 ноды
                nodes = nodes or []
                if len(nodes) > 1:
                    print("Доступные ноды для шаблона:")
                    for idx, n in enumerate(nodes, start=1):
                        print(f"{idx}. {n}")
                    while True:
                        sel = input("Выберите ноду (номер): ").strip()
                        try:
                            si = int(sel)
                            if 1 <= si <= len(nodes):
                                machine_config['template_node'] = nodes[si - 1]
                                break
                        except ValueError:
                            pass
                        print("Неверный выбор, попробуйте снова.")
                else:
                    # Оставим пустым — будет использована единственная нода при деплое
                    machine_config['template_node'] = nodes[0] if nodes else ''
                if machine_config['device_type'] == 'ecorouter':
                    prompt = "Сколько нужно сетевых адаптеров? (управляющий порт net0 уже будет создан автоматически) "
                else:
                    prompt = "Сколько нужно сетевых адаптеров? "
                num_networks = int(input(prompt))
                machine_config['networks'] = []
                for j in range(num_networks):
                    bridge = input(f"Имя bridge для сетевой карты {j+1} (например vmbr0): ")
                    machine_config['networks'].append({'bridge': bridge})

                # Выбор типа клонирования
                print("Тип клонирования:")
                print("1) Linked clone (быстрое создание, экономит место)")
                print("2) Full clone (полная копия, независимая от шаблона)")
                clone_choice = input("Выберите тип клонирования (1/2) [1]: ").strip()
                machine_config['full_clone'] = clone_choice == '2'

                config['machines'].append(machine_config)
            with open(CONFIG_FILE, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            print(f"\nКонфигурация сохранена в файл: {CONFIG_FILE}")
            return config
        except ValueError as e:
            print(f"Ошибка ввода: {e}")
            return {}

    @staticmethod
    def load_deployment_config() -> Dict[str, Any]:
        if not os.path.exists(CONFIG_FILE):
            print("Файл конфигурации не найден!")
            return {}
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f)

    @staticmethod
    def save_users(users: List[str]) -> bool:
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
        if not os.path.exists(USERS_FILE):
            return []
        with open(USERS_FILE, 'r') as f:
            data = yaml.safe_load(f)
            return data.get('users', [])
