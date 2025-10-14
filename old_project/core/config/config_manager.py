"""
Менеджер конфигурации системы Deploy-Stand

Предоставляет функциональность для загрузки, сохранения и валидации
конфигурационных файлов в формате YAML без использования pyyaml.
"""

import os
import logging
from typing import Dict, List, Any, Optional
import yaml as yaml_module  # Используем встроенный модуль yaml
from .validators import ConfigValidator

logger = logging.getLogger(__name__)


class ConfigManager:
    """Менеджер конфигурации для работы с YAML файлами"""

    # Константы для путей к файлам
    CONFIG_DIR = "data"
    CONFIG_FILE = "data/deployment_config.yml"
    USERS_FILE = "data/users_list.yml"
    CONFIGS_DIR = "data/configs"
    CONNECTIONS_FILE = "data/connections_config.yml"

    def __init__(self):
        """Инициализация менеджера конфигурации"""
        self._ensure_directories()

    def _ensure_directories(self):
        """Создать необходимые директории если они не существуют"""
        try:
            os.makedirs(self.CONFIG_DIR, exist_ok=True)
            os.makedirs(self.CONFIGS_DIR, exist_ok=True)
        except Exception as e:
            logger.error(f"Ошибка создания директорий: {e}")

    def load_deployment_config(self) -> Optional[Dict[str, Any]]:
        """
        Загрузить конфигурацию развертывания

        Returns:
            Словарь с конфигурацией или None при ошибке
        """
        return self._load_yaml_file(self.CONFIG_FILE)

    def save_deployment_config(self, config: Dict[str, Any]) -> bool:
        """
        Сохранить конфигурацию развертывания

        Args:
            config: Конфигурация для сохранения

        Returns:
            True если сохранение успешно
        """
        return self._save_yaml_file(self.CONFIG_FILE, config)

    def load_users(self, users_list_name: str = "default") -> List[str]:
        """
        Загрузить список пользователей

        Args:
            users_list_name: Имя списка пользователей (по умолчанию "default")

        Returns:
            Список пользователей
        """
        users_file = os.path.join(self.CONFIG_DIR, f"users_{users_list_name}.yml")
        config = self._load_yaml_file(users_file)
        if config and 'users' in config:
            return config['users']
        return []

    def save_users(self, users: List[str], users_list_name: str = "default") -> bool:
        """
        Сохранить список пользователей

        Args:
            users: Список пользователей для сохранения
            users_list_name: Имя списка пользователей (по умолчанию "default")

        Returns:
            True если сохранение успешно
        """
        config = {'users': users}
        users_file = os.path.join(self.CONFIG_DIR, f"users_{users_list_name}.yml")
        return self._save_yaml_file(users_file, config)

    def list_user_lists(self) -> List[str]:
        """
        Получить список доступных списков пользователей

        Returns:
            Список имен списков пользователей
        """
        try:
            if not os.path.exists(self.CONFIG_DIR):
                return []

            user_lists = []
            for file in os.listdir(self.CONFIG_DIR):
                if file.startswith('users_') and file.endswith('.yml'):
                    list_name = file[6:-4]  # Remove 'users_' prefix and '.yml' suffix
                    user_lists.append(list_name)
            return user_lists
        except Exception as e:
            logger.error(f"Ошибка получения списка пользователей: {e}")
            return []

    def delete_user_list(self, users_list_name: str) -> bool:
        """
        Удалить список пользователей

        Args:
            users_list_name: Имя списка пользователей для удаления

        Returns:
            True если удаление успешно
        """
        try:
            users_file = os.path.join(self.CONFIG_DIR, f"users_{users_list_name}.yml")
            if os.path.exists(users_file):
                os.remove(users_file)
                logger.info(f"Список пользователей {users_list_name} удален")
                return True
            else:
                logger.warning(f"Список пользователей {users_list_name} не найден")
                return False
        except Exception as e:
            logger.error(f"Ошибка удаления списка пользователей {users_list_name}: {e}")
            return False

    def load_connections_config(self) -> Optional[Dict[str, Any]]:
        """
        Загрузить конфигурацию подключений

        Returns:
            Словарь с конфигурацией подключений или None при ошибке
        """
        return self._load_yaml_file(self.CONNECTIONS_FILE)

    def save_connections_config(self, config: Dict[str, Any]) -> bool:
        """
        Сохранить конфигурацию подключений

        Args:
            config: Конфигурация подключений для сохранения

        Returns:
            True если сохранение успешно
        """
        return self._save_yaml_file(self.CONNECTIONS_FILE, config)

    def list_configs(self) -> List[str]:
        """
        Получить список доступных конфигураций

        Returns:
            Список имен конфигураций
        """
        try:
            if not os.path.exists(self.CONFIGS_DIR):
                return []

            configs = []
            for file in os.listdir(self.CONFIGS_DIR):
                if file.endswith('.yml') or file.endswith('.yaml'):
                    configs.append(file)
                elif not file.startswith('.'):  # Include files without extension but not hidden files
                    configs.append(file)
            return configs
        except Exception as e:
            logger.error(f"Ошибка получения списка конфигураций: {e}")
            return []

    def load_config(self, config_name: str) -> Optional[Dict[str, Any]]:
        """
        Загрузить именованную конфигурацию

        Args:
            config_name: Имя конфигурации

        Returns:
            Словарь с конфигурацией или None при ошибке
        """
        config_path = os.path.join(self.CONFIGS_DIR, config_name)
        return self._load_yaml_file(config_path)

    def save_config(self, config_name: str, config: Dict[str, Any]) -> bool:
        """
        Сохранить именованную конфигурацию

        Args:
            config_name: Имя конфигурации
            config: Конфигурация для сохранения

        Returns:
            True если сохранение успешно
        """
        config_path = os.path.join(self.CONFIGS_DIR, config_name)
        return self._save_yaml_file(config_path, config)

    def delete_config(self, config_name: str) -> bool:
        """
        Удалить конфигурацию

        Args:
            config_name: Имя конфигурации для удаления

        Returns:
            True если удаление успешно
        """
        try:
            config_path = os.path.join(self.CONFIGS_DIR, config_name)
            if os.path.exists(config_path):
                os.remove(config_path)
                logger.info(f"Конфигурация {config_name} удалена")
                return True
            else:
                logger.warning(f"Конфигурация {config_name} не найдена")
                return False
        except Exception as e:
            logger.error(f"Ошибка удаления конфигурации {config_name}: {e}")
            return False


    def create_named_config(self, config_name: str, nodes: List[str], proxmox_manager) -> bool:
        """
        Создать именованную конфигурацию развертывания

        Args:
            config_name: Имя конфигурации
            nodes: Список доступных нод
            proxmox_manager: Менеджер Proxmox

        Returns:
            True если создание успешно
        """
        try:
            print(f"\n📋 Создание конфигурации '{config_name}'")
            print("=" * 50)

            # Запрос количества машин
            num_machines = input("Количество машин в конфигурации [1]: ").strip() or "1"

            try:
                num_machines = int(num_machines)
                if num_machines <= 0:
                    logger.error("Количество машин должно быть положительным числом!")
                    print("❌ Количество машин должно быть положительным числом!")
                    return False
            except ValueError:
                logger.error("Введено некорректное количество машин")
                print("❌ Введите корректное число!")
                return False

            machines = []

            for i in range(num_machines):
                print(f"\n🔧 Конфигурация машины {i+1}:")
                print("-" * 30)

                # Тип устройства
                device_type = input("Тип устройства (linux/ecorouter) [linux]: ").strip() or "linux"
                if device_type not in ['linux', 'ecorouter']:
                    logger.error(f"Недопустимый тип устройства: {device_type}")
                    print("❌ Допустимые типы: linux или ecorouter")
                    return False

                # Имя машины
                machine_name = input(f"Имя машины [vm-{i+1}]: ").strip() or f"vm-{i+1}"

                # Нода шаблона
                print(f"Доступные ноды: {', '.join(nodes)}")
                template_node = input("Нода шаблона: ").strip()
                if template_node not in nodes:
                    logger.error(f"Нода {template_node} не найдена в списке доступных")
                    print(f"❌ Нода {template_node} не найдена в списке доступных")
                    return False

                # VMID шаблона
                template_vmid = input("VMID шаблона: ").strip()
                try:
                    template_vmid = int(template_vmid)
                except ValueError:
                    logger.error("Введен некорректный VMID")
                    print("❌ VMID должен быть числом!")
                    return False

                # Тип клонирования
                full_clone_input = input("Полное клонирование? (y/n) [n]: ").strip().lower()
                full_clone = full_clone_input in ['y', 'yes', 'да']

                # Сетевые интерфейсы
                networks_input = input("Количество сетевых интерфейсов [1]: ").strip() or "1"
                try:
                    num_networks = int(networks_input)
                except ValueError:
                    logger.error("Введено некорректное количество сетевых интерфейсов")
                    print("❌ Введите корректное число!")
                    return False

                networks = []
                for j in range(num_networks):
                    bridge = input(f"Bridge для интерфейса {j+1} [vmbr{j}]: ").strip() or f"vmbr{j}"
                    networks.append({'bridge': bridge})

                machine_config = {
                    'device_type': device_type,
                    'name': machine_name,
                    'template_node': template_node,
                    'template_vmid': template_vmid,
                    'networks': networks,
                    'full_clone': full_clone
                }

                machines.append(machine_config)

            # Создать конфигурацию
            config = {
                'machines': machines
            }

            # Сохранить конфигурацию
            return self.save_config(config_name, config)

        except Exception as e:
            logger.error(f"Ошибка создания конфигурации {config_name}: {e}")
            return False

    def _load_yaml_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Загрузить YAML файл

        Args:
            file_path: Путь к файлу

        Returns:
            Словарь с данными или None при ошибке
        """
        try:
            if not os.path.exists(file_path):
                logger.warning(f"Файл {file_path} не найден")
                return None

            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                if not content.strip():
                    logger.warning(f"Файл {file_path} пуст")
                    return None

                # Используем встроенный модуль yaml
                data = yaml_module.safe_load(content)
                if data is None:
                    return {}

                return data

        except yaml_module.YAMLError as e:
            logger.error(f"Ошибка парсинга YAML файла {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка чтения файла {file_path}: {e}")
            return None

    def _save_yaml_file(self, file_path: str, data: Dict[str, Any]) -> bool:
        """
        Сохранить данные в YAML файл

        Args:
            file_path: Путь к файлу
            data: Данные для сохранения

        Returns:
            True если сохранение успешно
        """
        try:
            # Создать директорию если она не существует
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as file:
                # Используем встроенный модуль yaml с настройками форматирования
                yaml_module.dump(
                    data,
                    file,
                    default_flow_style=False,
                    allow_unicode=True,
                    encoding='utf-8'
                )

            logger.info(f"Конфигурация сохранена в {file_path}")
            return True

        except Exception as e:
            logger.error(f"Ошибка сохранения файла {file_path}: {e}")
            return False

    def validate_deployment_config(self, config: Dict[str, Any]) -> bool:
        """
        Валидация конфигурации развертывания

        Args:
            config: Конфигурация для валидации

        Returns:
            True если конфигурация валидна
        """
        try:
            # Проверка наличия секции machines
            if 'machines' not in config:
                logger.error("Конфигурация не содержит секцию 'machines'")
                return False

            machines = config['machines']
            if not isinstance(machines, list) or len(machines) == 0:
                logger.error("Секция 'machines' должна быть непустым списком")
                return False

            # Валидация каждой машины
            for i, machine in enumerate(machines):
                if not self._validate_machine_config(machine, i):
                    return False

            return True

        except Exception as e:
            logger.error(f"Ошибка валидации конфигурации: {e}")
            return False

    def _validate_machine_config(self, machine: Dict[str, Any], index: int) -> bool:
        """
        Валидация конфигурации одной машины

        Args:
            machine: Конфигурация машины
            index: Индекс машины в списке

        Returns:
            True если конфигурация валидна
        """
        required_fields = ['template_vmid']
        optional_fields = ['device_type', 'name', 'template_node', 'networks', 'full_clone']

        # Проверка обязательных полей
        for field in required_fields:
            if field not in machine:
                logger.error(f"Машина {index}: отсутствует обязательное поле '{field}'")
                return False

        # Проверка типа template_vmid
        if not isinstance(machine['template_vmid'], int):
            logger.error(f"Машина {index}: поле 'template_vmid' должно быть числом")
            return False

        # Проверка допустимых значений
        if 'device_type' in machine:
            if machine['device_type'] not in ['linux', 'ecorouter']:
                logger.error(f"Машина {index}: недопустимый тип устройства '{machine['device_type']}'")
                return False

        # Проверка типа full_clone
        if 'full_clone' in machine:
            if not isinstance(machine['full_clone'], bool):
                logger.error(f"Машина {index}: поле 'full_clone' должно быть true/false")
                return False

        # Проверка сетевой конфигурации
        if 'networks' in machine:
            if not isinstance(machine['networks'], list):
                logger.error(f"Машина {index}: поле 'networks' должно быть списком")
                return False

            for j, network in enumerate(machine['networks']):
                if not isinstance(network, dict):
                    logger.error(f"Машина {index}, сеть {j}: должна быть объектом")
                    return False

                if 'bridge' not in network:
                    logger.error(f"Машина {index}, сеть {j}: отсутствует поле 'bridge'")
                    return False

        return True
