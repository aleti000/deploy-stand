#!/usr/bin/env python3
"""
Меню управления конфигурациями стендов
Управление конфигурациями развертывания стендов
"""

import os
import yaml as yaml_module
from typing import Dict, List, Any, Optional

from ..utils import Logger, ConfigValidator


class StandConfigMenu:
    """Меню управления конфигурациями стендов"""

    CONFIGS_DIR = "data/configs"

    def __init__(self, logger_instance):
        self.logger = logger_instance
        self.validator = ConfigValidator()
        self._ensure_directories()

    def _ensure_directories(self):
        """Создать необходимые директории если они не существуют"""
        try:
            os.makedirs(self.CONFIGS_DIR, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Ошибка создания директории: {e}")

    def show(self) -> str:
        """Показать меню управления конфигурациями стендов"""
        print("\n🛠️  Управление конфигурациями стендов")
        print("=" * 50)

        print("Доступные действия:")
        print("  [1] Создать конфигурацию стенда")
        print("  [2] Показать существующие конфигурации")
        print("  [3] Удалить конфигурацию стенда")
        print("  [0] Назад")

        choice = input("Выберите действие: ").strip()

        if choice == "1":
            result = self._create_stand_config()
            return result
        elif choice == "2":
            result = self._show_stand_configs()
            return result
        elif choice == "3":
            result = self._delete_stand_config()
            return result
        elif choice == "0":
            return "back"
        else:
            print("❌ Неверный выбор!")
            return "repeat"

    def _create_stand_config(self) -> str:
        """Создать конфигурацию стенда по аналогии со старым проектом"""
        print("\n📋 Создание конфигурации стенда")
        print("-" * 40)

        try:
            # Запрос имя конфигурации
            config_name = input("Имя конфигурации: ").strip()
            if not config_name:
                print("❌ Имя конфигурации обязательно!")
                return "repeat"

            # Вид клонирования общий для всего стенда
            print("\nТип клонирования:")
            print("  [1] Linked clone (связанное клонирование)")
            print("  [2] Full clone (полное клонирование)")
            clone_choice = input("Выберите тип клонирования [1]: ").strip() or "1"

            if clone_choice == "1":
                default_full_clone = False
                clone_type_name = "linked clone"
            elif clone_choice == "2":
                default_full_clone = True
                clone_type_name = "full clone"
            else:
                print("❌ Неверный выбор типа клонирования!")
                return "repeat"

            print(f"✅ Выбрано: {clone_type_name}")
            print()

            config_filename = f"{config_name}.yml"
            config_path = os.path.join(self.CONFIGS_DIR, config_filename)

            if os.path.exists(config_path):
                overwrite = input(f"Конфигурация '{config_name}' уже существует. Перезаписать? (y/N): ").strip().lower()
                if overwrite != 'y':
                    return "repeat"

            # Запрос количества машин
            while True:
                num_machines_input = input("Количество машин в конфигурации [1]: ").strip() or "1"
                try:
                    num_machines = int(num_machines_input)
                    if num_machines <= 0:
                        print("❌ Количество машин должно быть положительным числом!")
                        continue
                    break
                except ValueError:
                    print("❌ Введите корректное число!")

            machines = []

            for i in range(num_machines):
                print(f"\n🔧 Конфигурация машины {i+1}:")
                print("-" * 30)

                # Тип устройства - выбор из списка
                print("Тип устройства:")
                print("  [1] Linux")
                print("  [2] Ecorouter")
                device_choice = input("Выберите тип устройства [1]: ").strip() or "1"

                if device_choice == "1":
                    device_type = "linux"
                    device_name = "Linux"
                elif device_choice == "2":
                    device_type = "ecorouter"
                    device_name = "Ecorouter"
                else:
                    print("❌ Неверный выбор типа устройства!")
                    return "repeat"

                print(f"✅ Выбрано: {device_name}")

                # Имя машины
                machine_name = input(f"Имя машины [vm-{i+1}]: ").strip() or f"vm-{i+1}"

                # Выбор ноды и шаблона с использованием существующего подключения
                print("🔍 Получение списка шаблонов через текущее подключение...")

                # Используем единственный клиент ProxmoxAPI черезEXISTING_CONNECTION
                from ..utils.proxmox_client import ProxmoxClient

                # Получаем текущие настройки подключения из файла
                connections_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "connections_config.yml")

                try:
                    with open(connections_file, 'r', encoding='utf-8') as f:
                        conn_data = yaml_module.safe_load(f)
                        if conn_data and isinstance(conn_data, dict):
                            # Берем активное подключение
                            active_conn_name = list(conn_data.keys())[0]
                            conn_config = conn_data[active_conn_name]
                            if conn_config:
                                client = ProxmoxClient(
                                    host=conn_config['host'],
                                    user=conn_config['user'],
                                    password=conn_config['password']
                                )

                                if not client.connect():
                                    raise Exception("Подключение не удалось")

                                # Получить список нод
                                nodes = client.get_nodes()
                                if not nodes:
                                    raise Exception("Ноды не найдены")

                                # Выбор ноды
                                print("\nДоступные ноды:")
                                for idx, node in enumerate(nodes, 1):
                                    print(f"  [{idx}] {node}")

                                while True:
                                    node_choice = input(f"Выберите ноду (1-{len(nodes)}) [1]: ").strip() or "1"
                                    try:
                                        node_idx = int(node_choice) - 1
                                        if 0 <= node_idx < len(nodes):
                                            selected_node = nodes[node_idx]
                                            break
                                        else:
                                            print(f"❌ Выберите число от 1 до {len(nodes)}")
                                    except ValueError:
                                        print("❌ Введите корректное число!")

                                # Получить список ВМ на выбранной ноде (шаблоны)
                                vms = client.get_vms(selected_node)
                                templates = []
                                for vm in vms:
                                    if vm.get('template') == 1:  # Это шаблон
                                        templates.append(vm)

                                if not templates:
                                    raise Exception(f"На ноде '{selected_node}' нет шаблонов")

                                # Выбор шаблона
                                print(f"\nШаблоны на ноде '{selected_node}':")
                                for idx, template in enumerate(templates, 1):
                                    name = template.get('name', f'VM{template.get("vmid", "неизвестно")}')
                                    vmid = template.get('vmid', 'неизвестно')
                                    print(f"  [{idx}] {name} (VMID: {vmid})")

                                while True:
                                    template_choice = input(f"Выберите шаблон (1-{len(templates)}) [1]: ").strip() or "1"
                                    try:
                                        template_idx = int(template_choice) - 1
                                        if 0 <= template_idx < len(templates):
                                            selected_template = templates[template_idx]
                                            template_vmid = selected_template['vmid']
                                            template_node = selected_node
                                            print(f"✅ Выбрана нода: {selected_node}")
                                            print(f"✅ Выбран шаблон: {selected_template.get('name', f'VMID:{template_vmid}')} (VMID: {template_vmid})")
                                            break
                                        else:
                                            print(f"❌ Выберите число от 1 до {len(templates)}")
                                    except ValueError:
                                        print("❌ Введите корректное число!")

                            else:
                                raise Exception("Конфигурация подключения повреждена")
                        else:
                            raise Exception("Файл подключений пуст")

                except Exception as e:
                    print(f"❌ Ошибка работы с Proxmox API: {e}")
                    print("🔄 Переход к ручному вводу параметров")
                    # Ручной ввод как fallback
                    while True:
                        template_vmid_input = input("VMID шаблона: ").strip()
                        try:
                            template_vmid = int(template_vmid_input)
                            break
                        except ValueError:
                            print("❌ VMID должен быть числом!")
                    template_node = input("Нода шаблона (опционально): ").strip() or None

                # Сетевые интерфейсы
                networks = []
                print("\n🌐 Настройка сетевых интерфейсов:")
                print("-" * 35)
                while True:
                    bridge = input("Введите имя сетевого моста (пустой ввод для выхода): ").strip()
                    if not bridge:
                        break
                    networks.append({'bridge': bridge})
                    print(f"✅ Добавлен мост: {bridge}")

                machine_config = {
                    'device_type': device_type,
                    'name': machine_name,
                    'template_vmid': template_vmid,
                    'template_node': template_node,
                    'networks': networks,
                    'full_clone': default_full_clone
                }

                machines.append(machine_config)

            # Создать конфигурацию по аналогии со старым проектом
            config = {
                'machines': machines
            }

            # Валидация конфигурации
            if not self.validator.validate_deployment_config(config):
                print("❌ Конфигурация не прошла валидацию!")
                return "repeat"

            # Сохранить конфигурацию
            success = self._save_yaml_file(config_path, config)
            if success:
                print(f"✅ Конфигурация '{config_name}' сохранена")
                self.logger.info(f"Конфигурация стенда '{config_name}' создана")
                return "success"
            else:
                print("❌ Ошибка сохранения конфигурации")
                return "error"

        except Exception as e:
            self.logger.error(f"Ошибка при создании конфигурации стенда: {e}")
            print(f"❌ Ошибка: {e}")
            return "error"

    def _show_stand_configs(self) -> str:
        """Показать существующие конфигурации стендов"""
        print("\n📋 Существующие конфигурации стендов:")
        print("-" * 45)

        try:
            configs = self._list_configs()
            if not configs:
                print("ℹ️  Нет сохраненных конфигураций")
            else:
                for i, config_name in enumerate(configs, 1):
                    config_path = os.path.join(self.CONFIGS_DIR, config_name)
                    config = self._load_yaml_file(config_path)
                    if config and 'machines' in config:
                        num_machines = len(config['machines'])
                        print(f"{i}. {config_name} ({num_machines} машин)")
                    else:
                        print(f"{i}. {config_name} (невалидная)")
        except Exception as e:
            self.logger.error(f"Ошибка при показе конфигураций: {e}")
            print(f"❌ Ошибка: {e}")

        input("\nНажмите Enter для продолжения...")
        return "repeat"

    def _delete_stand_config(self) -> str:
        """Удалить конфигурацию стенда"""
        print("\n🗑️  Удаление конфигурации стенда")
        print("-" * 35)

        try:
            configs = self._list_configs()
            if not configs:
                print("ℹ️  Нет конфигураций для удаления")
                return "repeat"

            print("Доступные конфигурации:")
            for i, config_name in enumerate(configs, 1):
                print(f"  [{i}] {config_name}")

            while True:
                choice_input = input(f"Выберите конфигурацию для удаления (1-{len(configs)}) или 0 для отмены: ").strip()
                if choice_input == "0":
                    return "repeat"
                try:
                    choice = int(choice_input) - 1
                    if 0 <= choice < len(configs):
                        break
                    else:
                        print(f"❌ Выберите число от 1 до {len(configs)}")
                except ValueError:
                    print("❌ Введите корректное число!")

            config_name = configs[choice]
            confirm = input(f"Удалить конфигурацию '{config_name}'? (y/N): ").strip().lower()

            if confirm == 'y':
                config_path = os.path.join(self.CONFIGS_DIR, config_name)
                success = self._delete_config_file(config_path)
                if success:
                    print(f"✅ Конфигурация '{config_name}' удалена")
                    self.logger.info(f"Конфигурация стенда '{config_name}' удалена")
                    return "success"
                else:
                    print("❌ Ошибка удаления конфигурации")
                    return "error"
            else:
                print("ℹ️  Удаление отменено")
                return "repeat"

        except Exception as e:
            self.logger.error(f"Ошибка при удалении конфигурации: {e}")
            print(f"❌ Ошибка: {e}")
            return "error"

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

    def _save_yaml_file(self, file_path: str, data: Dict[str, Any]) -> bool:
        """Сохранить данные в YAML файл"""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as file:
                yaml_module.dump(
                    data,
                    file,
                    default_flow_style=False,
                    allow_unicode=True
                )

            self.logger.info(f"Данные сохранены в {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"Ошибка сохранения файла {file_path}: {e}")
            return False

    def _delete_config_file(self, config_path: str) -> bool:
        """Удалить файл конфигурации"""
        try:
            if os.path.exists(config_path):
                os.remove(config_path)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Ошибка удаления файла {config_path}: {e}")
            return False
