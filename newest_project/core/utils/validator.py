#!/usr/bin/env python3
"""
Validator - модуль валидации данных для newest_project

Предоставляет функции для проверки корректности входных данных,
конфигурационных файлов и параметров подключения.
"""

import re
import ipaddress
from typing import Dict, List, Any, Optional, Union
from pathlib import Path


class Validator:
    """
    Класс для валидации данных в системе развертывания VM

    Поддерживает валидацию:
    - IP адресов и портов
    - Пользователей Proxmox (user@realm)
    - VM ID и имен
    - Конфигурационных параметров
    - VLAN ID
    - Bridge имен
    """

    # Регулярные выражения для валидации
    PROXMOX_USER_PATTERN = re.compile(r'^[a-zA-Z0-9._@-]+\$[a-zA-Z0-9._@-]+$|^[a-zA-Z0-9._@-]+$')
    VM_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+$')
    BRIDGE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+$')
    VLAN_PATTERN = re.compile(r'^\d+$')

    # Допустимые диапазоны
    VLAN_ID_RANGE = range(1, 4095)
    VM_ID_RANGE = range(100, 999999)
    PORT_RANGE = range(1, 65536)

    def __init__(self):
        """Инициализация валидатора"""
        self.errors = []
        self.warnings = []

    def validate_proxmox_connection(self, connection_data: Dict[str, Any]) -> bool:
        """
        Валидация данных подключения к Proxmox

        Args:
            connection_data: Данные подключения

        Returns:
            True если валидация прошла успешно
        """
        self.errors = []
        self.warnings = []

        # Проверка обязательных полей
        required_fields = ['host', 'user']
        for field in required_fields:
            if field not in connection_data:
                self.errors.append(f"Отсутствует обязательное поле: {field}")
                continue

            if not connection_data[field]:
                self.errors.append(f"Пустое значение поля: {field}")

        if self.errors:
            return False

        # Валидация хоста
        if not self._validate_host(connection_data['host']):
            self.errors.append(f"Некорректный хост: {connection_data['host']}")

        # Валидация пользователя
        if not self._validate_proxmox_user(connection_data['user']):
            self.errors.append(f"Некорректный пользователь: {connection_data['user']}")

        # Валидация пароля или токена
        if not self._validate_credentials(connection_data):
            self.errors.append("Отсутствуют данные аутентификации (пароль или токен)")

        return len(self.errors) == 0

    def _validate_host(self, host: str) -> bool:
        """Валидация хоста Proxmox"""
        if not host:
            return False

        # Проверка формата host:port
        if ':' in host:
            host_part, port_part = host.split(':', 1)
            try:
                port = int(port_part)
                if port not in self.PORT_RANGE:
                    return False
            except ValueError:
                return False
        else:
            host_part = host

        # Проверка IP адреса или домена
        try:
            ipaddress.ip_address(host_part)
            return True
        except ValueError:
            # Проверка домена
            if re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', host_part):
                return True

        return False

    def _validate_proxmox_user(self, user: str) -> bool:
        """Валидация пользователя Proxmox"""
        if not user:
            return False

        return bool(self.PROXMOX_USER_PATTERN.match(user))

    def _validate_credentials(self, connection_data: Dict[str, Any]) -> bool:
        """Валидация данных аутентификации"""
        # Проверка пароля
        if 'password' in connection_data:
            return bool(connection_data['password'])

        # Проверка токена
        if 'token_name' in connection_data and 'token_value' in connection_data:
            return bool(connection_data['token_name'] and connection_data['token_value'])

        return False

    def validate_deployment_config(self, config: Dict[str, Any]) -> bool:
        """
        Валидация конфигурации развертывания

        Args:
            config: Конфигурация развертывания

        Returns:
            True если валидация прошла успешно
        """
        self.errors = []
        self.warnings = []

        if not isinstance(config, dict):
            self.errors.append("Конфигурация должна быть словарем")
            return False

        # Проверка наличия секции machines
        if 'machines' not in config:
            self.errors.append("Отсутствует секция 'machines' в конфигурации")
            return False

        machines = config['machines']
        if not isinstance(machines, list):
            self.errors.append("Секция 'machines' должна быть списком")
            return False

        if len(machines) == 0:
            self.warnings.append("Список machines пуст")
            return True

        # Валидация каждой машины
        for i, machine in enumerate(machines):
            if not self._validate_machine_config(machine, i):
                continue

        return len(self.errors) == 0

    def _validate_machine_config(self, machine: Dict[str, Any], index: int) -> bool:
        """Валидация конфигурации одной машины"""
        if not isinstance(machine, dict):
            self.errors.append(f"Машина #{index}: должна быть словарем")
            return False

        # Проверка обязательных полей
        required_fields = ['name', 'device_type', 'template_node', 'template_vmid']
        for field in required_fields:
            if field not in machine:
                self.errors.append(f"Машина '{machine.get('name', f'#{index}')}': отсутствует поле '{field}'")
                return False

        name = machine['name']

        # Валидация имени машины
        if not self._validate_vm_name(name):
            self.errors.append(f"Машина '{name}': некорректное имя")

        # Валидация типа устройства
        device_type = machine['device_type']
        if device_type not in ['linux', 'ecorouter']:
            self.errors.append(f"Машина '{name}': недопустимый тип устройства '{device_type}'")

        # Валидация ноды шаблона
        template_node = machine['template_node']
        if not self._validate_node_name(template_node):
            self.errors.append(f"Машина '{name}': некорректное имя ноды шаблона '{template_node}'")

        # Валидация VMID шаблона
        template_vmid = machine['template_vmid']
        if not self._validate_vmid(template_vmid):
            self.errors.append(f"Машина '{name}': некорректный VMID шаблона '{template_vmid}'")

        # Валидация сетей
        if 'networks' in machine:
            if not self._validate_networks(machine['networks'], name):
                return False

        return len(self.errors) == 0

    def _validate_vm_name(self, name: str) -> bool:
        """Валидация имени виртуальной машины"""
        if not name or len(name) > 50:
            return False
        return bool(self.VM_NAME_PATTERN.match(name))

    def _validate_node_name(self, node_name: str) -> bool:
        """Валидация имени ноды"""
        if not node_name or len(node_name) > 50:
            return False
        return bool(re.match(r'^[a-zA-Z0-9._-]+$', node_name))

    def _validate_vmid(self, vmid: Union[int, str]) -> bool:
        """Валидация VMID"""
        try:
            vmid_int = int(vmid)
            return vmid_int in self.VM_ID_RANGE
        except (ValueError, TypeError):
            return False

    def _validate_networks(self, networks: List[Dict[str, Any]], machine_name: str) -> bool:
        """Валидация сетевой конфигурации"""
        if not isinstance(networks, list):
            self.errors.append(f"Машина '{machine_name}': networks должен быть списком")
            return False

        for i, network in enumerate(networks):
            if not self._validate_network(network, machine_name, i):
                return False

        return True

    def _validate_network(self, network: Dict[str, Any], machine_name: str, net_index: int) -> bool:
        """Валидация одного сетевого интерфейса"""
        if not isinstance(network, dict):
            self.errors.append(f"Машина '{machine_name}', сеть #{net_index}: должен быть словарем")
            return False

        if 'bridge' not in network:
            self.errors.append(f"Машина '{machine_name}', сеть #{net_index}: отсутствует поле 'bridge'")
            return False

        bridge = network['bridge']

        # Валидация bridge алиаса
        if not self._validate_bridge_alias(bridge):
            self.errors.append(f"Машина '{machine_name}': некорректный bridge '{bridge}'")

        return True

    def _validate_bridge_alias(self, bridge: str) -> bool:
        """Валидация алиаса bridge"""
        if not bridge:
            return False

        # Проверка формата bridge.vlan или просто bridge
        if '.' in bridge:
            parts = bridge.split('.')
            if len(parts) != 2:
                return False

            bridge_part, vlan_part = parts

            # Валидация имени bridge
            if not self.BRIDGE_NAME_PATTERN.match(bridge_part):
                return False

            # Валидация VLAN ID
            if not self.VLAN_PATTERN.match(vlan_part):
                return False

            try:
                vlan_id = int(vlan_part)
                if vlan_id not in self.VLAN_ID_RANGE:
                    return False
            except ValueError:
                return False
        else:
            # Просто bridge без VLAN
            if not self.BRIDGE_NAME_PATTERN.match(bridge):
                return False

        return True

    def validate_users_list(self, users: List[str]) -> bool:
        """
        Валидация списка пользователей

        Args:
            users: Список пользователей

        Returns:
            True если валидация прошла успешно
        """
        self.errors = []
        self.warnings = []

        if not isinstance(users, list):
            self.errors.append("Список пользователей должен быть списком")
            return False

        if len(users) == 0:
            self.warnings.append("Список пользователей пуст")
            return True

        # Валидация каждого пользователя
        for i, user in enumerate(users):
            if not self._validate_user(user, i):
                continue

        return len(self.errors) == 0

    def _validate_user(self, user: str, index: int) -> bool:
        """Валидация одного пользователя"""
        if not user:
            self.errors.append(f"Пользователь #{index}: пустое значение")
            return False

        if not self._validate_proxmox_user(user):
            self.errors.append(f"Пользователь #{index}: некорректный формат '{user}'")

        return len(self.errors) == 0

    def validate_file_exists(self, file_path: Union[str, Path]) -> bool:
        """
        Валидация существования файла

        Args:
            file_path: Путь к файлу

        Returns:
            True если файл существует
        """
        path = Path(file_path)
        if not path.exists():
            self.errors.append(f"Файл не найден: {file_path}")
            return False

        if not path.is_file():
            self.errors.append(f"Путь не является файлом: {file_path}")
            return False

        return True

    def validate_directory_writable(self, dir_path: Union[str, Path]) -> bool:
        """
        Валидация возможности записи в директорию

        Args:
            dir_path: Путь к директории

        Returns:
            True если директория доступна для записи
        """
        path = Path(dir_path)

        if not path.exists():
            self.errors.append(f"Директория не найдена: {dir_path}")
            return False

        if not path.is_dir():
            self.errors.append(f"Путь не является директорией: {dir_path}")
            return False

        if not os.access(path, os.W_OK):
            self.errors.append(f"Нет прав на запись в директорию: {dir_path}")
            return False

        return True

    def get_errors(self) -> List[str]:
        """Получить список ошибок валидации"""
        return self.errors.copy()

    def get_warnings(self) -> List[str]:
        """Получить список предупреждений валидации"""
        return self.warnings.copy()

    def has_errors(self) -> bool:
        """Проверить наличие ошибок"""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Проверить наличие предупреждений"""
        return len(self.warnings) > 0

    def get_validation_report(self) -> Dict[str, Any]:
        """
        Получить полный отчет валидации

        Returns:
            Словарь с результатами валидации
        """
        return {
            'valid': not self.has_errors(),
            'errors': self.get_errors(),
            'warnings': self.get_warnings(),
            'error_count': len(self.errors),
            'warning_count': len(self.warnings)
        }


# Глобальный экземпляр валидатора
_global_validator = None


def get_validator() -> Validator:
    """Получить глобальный экземпляр валидатора"""
    global _global_validator
    if _global_validator is None:
        _global_validator = Validator()
    return _global_validator


def validate_quick_check(data: Any, data_type: str) -> bool:
    """
    Быстрая валидация данных

    Args:
        data: Данные для проверки
        data_type: Тип данных ('ip', 'user', 'vmid', 'vlan', 'bridge')

    Returns:
        True если валидация прошла успешно
    """
    validator = Validator()

    if data_type == 'ip':
        return validator._validate_host(str(data))
    elif data_type == 'user':
        return validator._validate_proxmox_user(str(data))
    elif data_type == 'vmid':
        return validator._validate_vmid(data)
    elif data_type == 'vlan':
        return validator._validate_bridge_alias(f"test.{data}")
    elif data_type == 'bridge':
        return validator._validate_bridge_alias(str(data))

    return False


# Пример использования
if __name__ == "__main__":
    validator = Validator()

    # Тестирование валидации подключения
    print("🔧 Тестирование валидации подключения:")
    connection_data = {
        'host': '192.168.1.100:8006',
        'user': 'root@pam',
        'password': 'secret'
    }

    if validator.validate_proxmox_connection(connection_data):
        print("✅ Данные подключения корректны")
    else:
        print("❌ Ошибки валидации подключения:")
        for error in validator.get_errors():
            print(f"  - {error}")

    # Тестирование валидации конфигурации
    print("\n🔧 Тестирование валидации конфигурации:")
    config = {
        'machines': [
            {
                'name': 'test-vm',
                'device_type': 'linux',
                'template_node': 'pve1',
                'template_vmid': 100,
                'networks': [
                    {'bridge': 'vmbr0'},
                    {'bridge': 'hq.100'}
                ]
            }
        ]
    }

    if validator.validate_deployment_config(config):
        print("✅ Конфигурация развертывания корректна")
    else:
        print("❌ Ошибки валидации конфигурации:")
        for error in validator.get_errors():
            print(f"  - {error}")

    # Тестирование валидации пользователей
    print("\n🔧 Тестирование валидации пользователей:")
    users = ['user1@pve', 'user2@pve', 'admin@pam']

    if validator.validate_users_list(users):
        print("✅ Список пользователей корректен")
    else:
        print("❌ Ошибки валидации пользователей:")
        for error in validator.get_errors():
            print(f"  - {error}")

    print("\n✅ Тестирование валидатора завершено")
