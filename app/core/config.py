import yaml
import os
from typing import Dict, List, Any
from app.utils.logger import logger

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
os.makedirs(CONFIG_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIR, 'deployment_config.yml')
USERS_FILE = os.path.join(CONFIG_DIR, 'users_list.yml')
CONFIGS_DIR = os.path.join(CONFIG_DIR, 'configs')
os.makedirs(CONFIGS_DIR, exist_ok=True)

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
                    # Сортируем ноды по алфавиту для удобства выбора
                    sorted_nodes = sorted(nodes)
                    print("Доступные ноды для шаблона:")
                    for idx, n in enumerate(sorted_nodes, start=1):
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
                    bridge_input = input(f"Имя bridge для сетевой карты {j+1} (например vmbr0 или **vmbr100** для зарезервированного): ")
                    # Проверяем, является ли bridge зарезервированным (заключен в **)
                    if bridge_input.startswith('**') and bridge_input.endswith('**'):
                        bridge = bridge_input[2:-2]  # Удаляем **
                        reserved = True
                    else:
                        bridge = bridge_input
                        reserved = False
                    machine_config['networks'].append({'bridge': bridge, 'reserved': reserved})

                # Выбор типа клонирования
                print("Тип клонирования:")
                print("1) Linked clone (быстрое создание, экономит место)")
                print("2) Full clone (полная копия, независимая от шаблона)")
                clone_choice = input("Выберите тип клонирования (1/2) [1]: ").strip()
                machine_config['full_clone'] = clone_choice == '2'

                config['machines'].append(machine_config)
            with open(CONFIG_FILE, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            logger.success(f"Конфигурация сохранена в файл: {CONFIG_FILE}")
            return config
        except ValueError as e:
            logger.error(f"Ошибка ввода: {e}")
            return {}

    @staticmethod
    def load_deployment_config() -> Dict[str, Any]:
        if not os.path.exists(CONFIG_FILE):
            logger.warning("Файл конфигурации не найден!")
            return {}
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f)

    @staticmethod
    def save_users(users: List[str]) -> bool:
        try:
            users_data = {'users': users}
            with open(USERS_FILE, 'w') as f:
                yaml.dump(users_data, f, default_flow_style=False, allow_unicode=True)
            logger.success(f"Список пользователей сохранен в: {USERS_FILE}")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения пользователей: {e}")
            return False

    @staticmethod
    def load_users() -> List[str]:
        if not os.path.exists(USERS_FILE):
            return []
        with open(USERS_FILE, 'r') as f:
            data = yaml.safe_load(f)
            return data.get('users', [])

    @staticmethod
    def create_named_config(config_name: str, nodes: list[str] | None = None) -> Dict[str, Any]:
        """Создать именованную конфигурацию развертывания"""
        config = {}
        try:
            print(f"\n=== Создание конфигурации: {config_name} ===")
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
                    # Сортируем ноды по алфавиту для удобства выбора
                    sorted_nodes = sorted(nodes)
                    print("Доступные ноды для шаблона:")
                    for idx, n in enumerate(sorted_nodes, start=1):
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
                    bridge_input = input(f"Имя bridge для сетевой карты {j+1} (например vmbr0 или **vmbr100** для зарезервированного): ")
                    # Проверяем, является ли bridge зарезервированным (заключен в **)
                    if bridge_input.startswith('**') and bridge_input.endswith('**'):
                        bridge = bridge_input[2:-2]  # Удаляем **
                        reserved = True
                    else:
                        bridge = bridge_input
                        reserved = False
                    machine_config['networks'].append({'bridge': bridge, 'reserved': reserved})

                # Выбор типа клонирования
                print("Тип клонирования:")
                print("1) Linked clone (быстрое создание, экономит место)")
                print("2) Full clone (полная копия, независимая от шаблона)")
                clone_choice = input("Выберите тип клонирования (1/2) [1]: ").strip()
                machine_config['full_clone'] = clone_choice == '2'

                config['machines'].append(machine_config)

            # Сохраняем конфигурацию с указанным именем
            config_file = os.path.join(CONFIGS_DIR, f'{config_name}.yml')
            with open(config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            logger.success(f"Конфигурация '{config_name}' сохранена в файл: {config_file}")
            return config
        except ValueError as e:
            logger.error(f"Ошибка ввода: {e}")
            return {}

    @staticmethod
    def list_configs() -> List[str]:
        """Получить список доступных конфигураций"""
        if not os.path.exists(CONFIGS_DIR):
            return []
        config_files = [f for f in os.listdir(CONFIGS_DIR) if f.endswith('.yml')]
        return [os.path.splitext(f)[0] for f in config_files]

    @staticmethod
    def load_config(config_name: str) -> Dict[str, Any]:
        """Загрузить конкретную конфигурацию по имени"""
        config_file = os.path.join(CONFIGS_DIR, f'{config_name}.yml')
        if not os.path.exists(config_file):
            logger.warning(f"Конфигурация '{config_name}' не найдена!")
            return {}
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)

    @staticmethod
    def delete_config(config_name: str) -> bool:
        """Удалить конфигурацию"""
        config_file = os.path.join(CONFIGS_DIR, f'{config_name}.yml')
        if os.path.exists(config_file):
            try:
                os.remove(config_file)
                logger.success(f"Конфигурация '{config_name}' удалена")
                return True
            except Exception as e:
                logger.error(f"Ошибка удаления конфигурации '{config_name}': {e}")
                return False
        else:
            logger.warning(f"Конфигурация '{config_name}' не найдена")
            return False
