#!/usr/bin/env python3
"""
Модуль конфигурирования стендов развертывания
Предоставляет интерактивный интерфейс для создания и управления конфигурациями стендов
"""

import asyncio
import logging
import yaml
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class StandConfigurer:
    """Класс для управления конфигурациями стендов"""

    def __init__(self):
        self.config_dir = Path("data/stand_config")
        self.proxmox_client = None
        self.current_stand_config = {}

    def set_proxmox_client(self, proxmox_client):
        """Установка клиента Proxmox для получения данных о нодах и шаблонах"""
        self.proxmox_client = proxmox_client

    def ensure_config_directory(self):
        """Создание каталога для конфигураций если он не существует"""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def get_stand_configs(self) -> List[str]:
        """Получение списка доступных конфигураций стендов"""
        self.ensure_config_directory()
        config_files = list(self.config_dir.glob("*.yaml"))
        return [f.stem for f in config_files]

    def load_stand_config(self, config_name: str) -> Optional[Dict[str, Any]]:
        """Загрузка конфигурации стенда"""
        config_path = self.config_dir / f"{config_name}.yaml"
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации {config_name}: {e}")
            return None

    def save_stand_config(self, config_name: str, config: Dict[str, Any]) -> bool:
        """Сохранение конфигурации стенда"""
        self.ensure_config_directory()
        config_path = self.config_dir / f"{config_name}.yaml"

        try:
            # Добавляем метаданные
            config['metadata'] = {
                'created_at': datetime.now().isoformat(),
                'version': '1.0'
            }

            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

            logger.info(f"Конфигурация {config_name} сохранена")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения конфигурации {config_name}: {e}")
            return False

    def delete_stand_config(self, config_name: str) -> bool:
        """Удаление конфигурации стенда"""
        config_path = self.config_dir / f"{config_name}.yaml"
        try:
            if config_path.exists():
                config_path.unlink()
                logger.info(f"Конфигурация {config_name} удалена")
                return True
            else:
                logger.warning(f"Конфигурация {config_name} не найдена")
                return False
        except Exception as e:
            logger.error(f"Ошибка удаления конфигурации {config_name}: {e}")
            return False

    def get_available_nodes(self) -> List[str]:
        """Получение списка доступных нод кластера"""
        if not self.proxmox_client or not self.proxmox_client.is_connected():
            return []
        try:
            nodes = self.proxmox_client.get_nodes()
            return [node.get('node', '') for node in nodes if node.get('node')]
        except Exception as e:
            logger.error(f"Ошибка получения списка нод: {e}")
            return []

    def get_templates_for_node(self, node_name: str) -> List[Dict[str, Any]]:
        """Получение списка шаблонов для указанной ноды"""
        if not self.proxmox_client or not self.proxmox_client.is_connected():
            return []
        try:
            vms = self.proxmox_client.get_vms(node_name)
            templates = []
            for vm in vms:
                if vm.get('template', 0) == 1:  # Это шаблон
                    templates.append({
                        'vmid': vm.get('vmid'),
                        'name': vm.get('name', f'VM-{vm.get("vmid")}'),
                        'node': node_name
                    })
            return templates
        except Exception as e:
            logger.error(f"Ошибка получения шаблонов для ноды {node_name}: {e}")
            return []

    def validate_stand_config(self, config: Dict[str, Any]) -> List[str]:
        """Валидация конфигурации стенда"""
        errors = []

        if not config.get('machines'):
            errors.append("Конфигурация должна содержать хотя бы одну машину")

        for i, machine in enumerate(config.get('machines', [])):
            if not machine.get('device_type') in ['linux', 'ecorouter']:
                errors.append(f"Машина {i+1}: неверный тип устройства")

            if not machine.get('name'):
                errors.append(f"Машина {i+1}: отсутствует имя")

            if not machine.get('template_node'):
                errors.append(f"Машина {i+1}: отсутствует нода шаблона")

            if not machine.get('template_vmid'):
                errors.append(f"Машина {i+1}: отсутствует VMID шаблона")

        return errors


class StandConfigMenu:
    """Класс для интерактивного меню конфигурирования стендов"""

    def __init__(self, stand_configurer: StandConfigurer):
        self.configurer = stand_configurer
        self.current_config = {
            'stand_type': None,
            'machines': []
        }

    def clear_screen(self):
        """Очистка экрана"""
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

    async def get_user_input(self, prompt: str, required: bool = True, default: str = "") -> str:
        """Получение ввода от пользователя"""
        while True:
            try:
                value = input(f"{prompt}").strip()
                if not value and required and not default:
                    print("❌ Это поле обязательно для заполнения")
                    continue
                if not value and default:
                    return default
                return value
            except KeyboardInterrupt:
                print("\n\n⏹️  Операция отменена")
                return ""

    async def show_stand_config_submenu(self):
        """Отображение подменю управления конфигурациями стендов"""
        self.clear_screen()

        print("\n" + "="*60)
        print("УПРАВЛЕНИЕ КОНФИГУРАЦИЯМИ СТЕНДОВ")
        print("="*60)
        print("1. Создать конфигурацию стенда")
        print("2. Отобразить конфигурации стендов")
        print("3. Удалить конфигурации стендов")
        print("0. Назад в главное меню")
        print("-"*60)

    async def show_create_stand_submenu(self):
        """Отображение подменю создания конфигурации стенда"""
        self.clear_screen()

        print("\n" + "="*60)
        print("СОЗДАНИЕ КОНФИГУРАЦИИ СТЕНДА")
        print("="*60)
        print("1. Выберите тип стенда")
        print("2. Добавить ВМ с настройкой сети")
        print("3. Отобразить созданные ВМ")
        print("4. Удалить предыдущую ВМ")
        print("5. Сохранить параметры стенда")
        print("0. Назад")
        print("-"*60)

    async def select_stand_type(self):
        """Выбор типа стенда"""
        self.clear_screen()

        print("\n" + "="*40)
        print("ВЫБОР ТИПА СТЕНДА")
        print("="*40)
        print("1. Полное клонирование (full)")
        print("2. Связанное клонирование (linked)")
        print("0. Назад")
        print("-"*40)

        while True:
            choice = await self.get_user_input("Выберите тип стенда: ")

            if choice == "0":
                return False
            elif choice == "1":
                self.current_config['stand_type'] = 'full'
                print("✅ Выбран тип: Полное клонирование (full)")
                return True
            elif choice == "2":
                self.current_config['stand_type'] = 'linked'
                print("✅ Выбран тип: Связанное клонирование (linked)")
                return True
            else:
                print("❌ Неверный выбор. Попробуйте еще раз.")

    async def add_vm(self):
        """Добавление виртуальной машины"""
        self.clear_screen()

        print("\n" + "="*40)
        print("ДОБАВЛЕНИЕ ВИРТУАЛЬНОЙ МАШИНЫ")
        print("="*40)

        # Выбор типа устройства
        print("\nВыберите тип устройства:")
        print("1. Linux")
        print("2. Ecorouter")

        device_type_choice = await self.get_user_input("Тип устройства: ")
        if device_type_choice == "1":
            device_type = "linux"
        elif device_type_choice == "2":
            device_type = "ecorouter"
        else:
            print("❌ Неверный выбор типа устройства")
            return False

        # Ввод имени машины
        vm_name = await self.get_user_input("Введите имя машины: ")
        if not vm_name:
            return False

        # Выбор ноды шаблона
        nodes = self.configurer.get_available_nodes()
        if not nodes:
            print("❌ Нет доступных нод кластера")
            return False

        print(f"\nДоступные ноды ({len(nodes)}):")
        for i, node in enumerate(nodes, 1):
            print(f"{i}. {node}")

        node_choice = await self.get_user_input("Выберите ноду шаблона: ")
        try:
            node_index = int(node_choice) - 1
            if not (0 <= node_index < len(nodes)):
                print("❌ Неверный номер ноды")
                return False
            template_node = nodes[node_index]
        except ValueError:
            print("❌ Введите номер ноды")
            return False

        # Выбор шаблона
        templates = self.configurer.get_templates_for_node(template_node)
        if not templates:
            print(f"❌ На ноде {template_node} нет доступных шаблонов")
            return False

        print(f"\nШаблоны на ноде {template_node} ({len(templates)}):")
        for i, template in enumerate(templates, 1):
            print(f"{i}. {template['name']} (VMID: {template['vmid']})")

        template_choice = await self.get_user_input("Выберите шаблон: ")
        try:
            template_index = int(template_choice) - 1
            if not (0 <= template_index < len(templates)):
                print("❌ Неверный номер шаблона")
                return False
            selected_template = templates[template_index]
        except ValueError:
            print("❌ Введите номер шаблона")
            return False

        # Создание конфигурации машины
        machine_config = {
            'device_type': device_type,
            'name': vm_name,
            'template_node': template_node,
            'template_vmid': selected_template['vmid'],
            'networks': []
        }

        self.current_config['machines'].append(machine_config)
        print(f"✅ Машина '{vm_name}' добавлена в конфигурацию")

        # Настройка сетевых соединений для этой машины
        print(f"\n🌐 Настройка сетевых соединений для машины '{vm_name}'")
        while True:
            bridge = await self.get_user_input("Введите название bridge (или пустое для завершения): ", required=False)
            if not bridge:
                break

            # Добавление сети к машине
            network_config = {'bridge': bridge}
            machine_config['networks'].append(network_config)
            print(f"✅ Сетевое соединение '{bridge}' добавлено")

        print(f"✅ Машина '{vm_name}' полностью настроена с {len(machine_config['networks'])} сетевыми соединениями")
        return True

    async def add_network(self):
        """Добавление сетевого соединения"""
        if not self.current_config.get('machines'):
            print("❌ Сначала добавьте хотя бы одну машину")
            return False

        self.clear_screen()

        print("\n" + "="*40)
        print("ДОБАВЛЕНИЕ СЕТЕВОГО СОЕДИНЕНИЯ")
        print("="*40)

        print("Доступные машины:")
        for i, machine in enumerate(self.current_config['machines'], 1):
            print(f"{i}. {machine['name']} ({machine['device_type']})")

        machine_choice = await self.get_user_input("Выберите машину (номер) или 0 для отмены: ")
        if machine_choice == "0":
            return False

        try:
            machine_index = int(machine_choice) - 1
            if not (0 <= machine_index < len(self.current_config['machines'])):
                print("❌ Неверный номер машины")
                return False
        except ValueError:
            print("❌ Введите номер машины")
            return False

        # Ввод bridge
        bridge = await self.get_user_input("Введите название bridge (например, vmbr0): ")
        if not bridge:
            return False

        # Добавление сети к выбранной машине
        network_config = {'bridge': bridge}
        self.current_config['machines'][machine_index]['networks'].append(network_config)

        print(f"✅ Сетевое соединение '{bridge}' добавлено к машине '{self.current_config['machines'][machine_index]['name']}'")
        return True

    async def show_machines(self):
        """Отображение созданных машин"""
        self.clear_screen()

        if not self.current_config.get('machines'):
            print("❌ Нет созданных машин")
            return

        print("\n" + "="*60)
        print("СОЗДАННЫЕ ВИРТУАЛЬНЫЕ МАШИНЫ")
        print("="*60)

        for i, machine in enumerate(self.current_config['machines'], 1):
            print(f"\n{i}. {machine['name']}")
            print(f"   Тип: {machine['device_type']}")
            print(f"   Шаблон: {machine['template_node']} / VMID: {machine['template_vmid']}")
            print(f"   Сети: {len(machine['networks'])}")

            if machine['networks']:
                for j, network in enumerate(machine['networks'], 1):
                    print(f"     {j}. {network['bridge']}")
            else:
                print("     Нет сетевых соединений")

        print(f"\nВсего машин: {len(self.current_config['machines'])}")
        print(f"Тип стенда: {self.current_config.get('stand_type', 'не выбран')}")

    async def remove_last_vm(self):
        """Удаление последней добавленной машины"""
        if not self.current_config.get('machines'):
            print("❌ Нет машин для удаления")
            return False

        last_machine = self.current_config['machines'].pop()
        print(f"✅ Машина '{last_machine['name']}' удалена")
        return True

    async def save_stand_config(self):
        """Сохранение конфигурации стенда"""
        if not self.current_config.get('machines'):
            print("❌ Нет машин для сохранения")
            return False

        if not self.current_config.get('stand_type'):
            print("❌ Не выбран тип стенда")
            return False

        self.clear_screen()

        print("\n" + "="*40)
        print("СОХРАНЕНИЕ КОНФИГУРАЦИИ СТЕНДА")
        print("="*40)

        # Ввод имени конфигурации
        config_name = await self.get_user_input("Введите имя конфигурации: ")
        if not config_name:
            return False

        # Проверка существования
        existing_configs = self.configurer.get_stand_configs()
        if config_name in existing_configs:
            confirm = await self.get_user_input(f"Конфигурация '{config_name}' уже существует. Перезаписать? (y/n): ")
            if confirm.lower() not in ['y', 'yes', 'да', 'д']:
                print("❌ Сохранение отменено")
                return False

        # Валидация конфигурации
        validation_errors = self.configurer.validate_stand_config(self.current_config)
        if validation_errors:
            print("❌ Ошибки валидации:")
            for error in validation_errors:
                print(f"   • {error}")
            return False

        # Сохранение
        if self.configurer.save_stand_config(config_name, self.current_config):
            print(f"✅ Конфигурация '{config_name}' успешно сохранена")
            # Очищаем текущую конфигурацию
            self.current_config = {'machines': []}
            return True
        else:
            print(f"❌ Ошибка сохранения конфигурации '{config_name}'")
            return False

    async def show_stand_configs(self):
        """Отображение всех конфигураций стендов"""
        self.clear_screen()

        configs = self.configurer.get_stand_configs()

        if not configs:
            print("📭 Нет сохраненных конфигураций стендов")
            return

        print("\n" + "="*60)
        print("ДОСТУПНЫЕ КОНФИГУРАЦИИ СТЕНДОВ")
        print("="*60)

        for config_name in configs:
            config = self.configurer.load_stand_config(config_name)
            if config:
                machines_count = len(config.get('machines', []))
                stand_type = config.get('stand_type', 'не указан')
                created_at = config.get('metadata', {}).get('created_at', 'неизвестно')

                print(f"\n📁 {config_name}")
                print(f"   Тип стенда: {stand_type}")
                print(f"   Количество машин: {machines_count}")
                print(f"   Создана: {created_at}")

                if machines_count > 0:
                    print("   Машины:")
                    for machine in config.get('machines', [])[:3]:  # Показываем первые 3
                        print(f"     • {machine['name']} ({machine['device_type']})")
                    if machines_count > 3:
                        print(f"     ... и еще {machines_count - 3} машин")

    async def delete_stand_config(self):
        """Удаление конфигурации стенда"""
        self.clear_screen()

        configs = self.configurer.get_stand_configs()
        if not configs:
            print("❌ Нет конфигураций для удаления")
            return

        print("\n" + "="*40)
        print("УДАЛЕНИЕ КОНФИГУРАЦИИ СТЕНДА")
        print("="*40)

        print("Доступные конфигурации:")
        for i, config_name in enumerate(configs, 1):
            print(f"{i}. {config_name}")

        choice = await self.get_user_input("Выберите конфигурацию для удаления (номер) или 0 для отмены: ")
        if choice == "0":
            return

        try:
            config_index = int(choice) - 1
            if not (0 <= config_index < len(configs)):
                print("❌ Неверный номер конфигурации")
                return

            config_to_delete = configs[config_index]

            # Подтверждение удаления
            confirm = await self.get_user_input(f"Удалить конфигурацию '{config_to_delete}'? (y/n): ")
            if confirm.lower() in ['y', 'yes', 'да', 'д']:
                if self.configurer.delete_stand_config(config_to_delete):
                    print(f"✅ Конфигурация '{config_to_delete}' удалена")
                else:
                    print(f"❌ Ошибка удаления конфигурации '{config_to_delete}'")
            else:
                print("❌ Удаление отменено")

        except ValueError:
            print("❌ Введите номер конфигурации")

    async def run_create_stand_menu(self):
        """Запуск меню создания конфигурации стенда"""
        while True:
            await self.show_create_stand_submenu()
            choice = await self.get_user_input("Выберите действие: ")

            if choice == "0":
                return
            elif choice == "1":
                await self.select_stand_type()
            elif choice == "2":
                await self.add_vm()
            elif choice == "3":
                await self.show_machines()
                print("\nНажмите Enter для продолжения...")
                input()
            elif choice == "4":
                await self.remove_last_vm()
            elif choice == "5":
                if await self.save_stand_config():
                    return
            else:
                print("❌ Неверный выбор. Попробуйте еще раз.")

    async def run(self):
        """Запуск главного меню управления конфигурациями"""
        while True:
            await self.show_stand_config_submenu()
            choice = await self.get_user_input("Выберите действие: ")

            if choice == "0":
                return
            elif choice == "1":
                await self.run_create_stand_menu()
            elif choice == "2":
                await self.show_stand_configs()
                print("\nНажмите Enter для продолжения...")
                input()
            elif choice == "3":
                await self.delete_stand_config()
            else:
                print("❌ Неверный выбор. Попробуйте еще раз.")


def get_stand_configurer() -> StandConfigurer:
    """Функция для получения экземпляра StandConfigurer"""
    return StandConfigurer()
