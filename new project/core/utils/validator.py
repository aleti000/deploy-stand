#!/usr/bin/env python3
"""
Модуль валидации конфигураций для приложения развертывания
Обновленная версия с учетом новой архитектуры менеджеров
"""

import logging
from typing import Dict, List, Any, Optional

# Импорт менеджеров для перекрестной валидации
try:
    from .pool_manager import PoolManager
    from .user_manager import UserManager
    from .vm_manager import VMManager
    from .network_manager import NetworkManager
except ImportError:
    # Fallback для обратной совместимости
    PoolManager = None
    UserManager = None
    VMManager = None
    NetworkManager = None


class ConfigValidator:
    """
    Класс для валидации конфигураций развертывания
    Расширен с учетом всех менеджеров
    """

    def __init__(self, proxmox_client=None):
        """
        Инициализация валидатора

        Args:
            proxmox_client: Клиент Proxmox для дополнительной валидации
        """
        self.logger = logging.getLogger(__name__)
        self.proxmox_client = proxmox_client

        # Инициализация менеджеров если клиент доступен
        if proxmox_client:
            self.pool_manager = PoolManager(proxmox_client) if PoolManager else None
            self.user_manager = UserManager(proxmox_client) if UserManager else None
            self.vm_manager = VMManager(proxmox_client) if VMManager else None
            self.network_manager = NetworkManager(proxmox_client) if NetworkManager else None
        else:
            self.pool_manager = None
            self.user_manager = None
            self.vm_manager = None
            self.network_manager = None

    def validate_deployment_config(self, config: Dict[str, Any]) -> bool:
        """
        Валидация общей конфигурации развертывания

        Args:
            config: Конфигурация для валидации

        Returns:
            True если конфигурация валидна
        """
        if not isinstance(config, dict):
            self.logger.error("Конфигурация должна быть словарем")
            return False

        # Проверка наличия секции machines
        if 'machines' not in config:
            self.logger.error("Конфигурация не содержит секцию 'machines'")
            return False

        machines = config.get('machines', [])
        if not isinstance(machines, list) or len(machines) == 0:
            self.logger.error("Секция 'machines' должна быть непустым списком")
            return False

        # Валидация каждой машины
        for i, machine in enumerate(machines):
            if not self.validate_machine_config(machine, i):
                return False

        self.logger.info("Конфигурация развертывания валидна")
        return True

    def validate_users_list(self, users: List[str]) -> bool:
        """
        Валидация списка пользователей

        Args:
            users: Список пользователей для валидации

        Returns:
            True если список пользователей валиден
        """
        if not users:
            self.logger.error("Список пользователей не может быть пустым")
            return False

        if not isinstance(users, list):
            self.logger.error("Список пользователей должен быть списком")
            return False

        invalid_users = []
        seen_users = set()

        for user in users:
            if not isinstance(user, str):
                invalid_users.append(str(user))
                continue

            # Проверка формата
            if '@' not in user:
                invalid_users.append(user)
                continue

            # Проверка дубликатов
            user_lower = user.lower()
            if user_lower in seen_users:
                self.logger.warning(f"Пользователь '{user}' уже есть в списке")
                invalid_users.append(user)
                continue

            seen_users.add(user_lower)

            # Проверка корректности домена
            username, domain = user.split('@', 1)
            if not username or not domain:
                invalid_users.append(user)
                continue

            # Дополнительная валидация: отсутствие пробелов и специальных символов
            if any(char in username for char in [' ', '\t', '\n', '\r', '"', "'", ',', ';', ':']):
                invalid_users.append(user)
                continue

        if invalid_users:
            self.logger.error(f"Найдены некорректные пользователи: {', '.join(invalid_users)}")
            return False

        # Дополнительная валидация через UserManager если доступен
        if self.user_manager and self.proxmox_client:
            for user in users:
                # Проверка существования пользователя если менеджер доступен
                try:
                    # Можно добавить дополнительную валидацию через менеджеры
                    pass
                except Exception as e:
                    self.logger.warning(f"Ошибка перекрестной валидации пользователя {user}: {e}")

        self.logger.info(f"Список пользователей валиден: {len(users)} пользователей")
        return True

    def validate_machine_network_config(self, machine: Dict[str, Any], node: str, index: int) -> bool:
        """
        Валидация сетевой конфигурации машины

        Args:
            machine: Конфигурация машины
            node: Нода размещения
            index: Индекс машины в списке

        Returns:
            True если сетевая конфигурация валидна
        """
        if 'networks' not in machine:
            # Сеть не указана - ок для некоторых конфигураций
            return True

        networks = machine.get('networks', [])
        if not isinstance(networks, list):
            self.logger.error(f"Машина {index}: поле 'networks' должно быть списком")
            return False

        # Использовать NetworkManager для валидации если доступен
        if self.network_manager:
            try:
                validation_result = self.network_manager.validate_network_config(networks, node)
                if not validation_result['is_valid']:
                    for error in validation_result['errors']:
                        self.logger.error(f"Машина {index}: {error}")
                    return False

                for warning in validation_result['warnings']:
                    self.logger.warning(f"Машина {index}: {warning}")

            except Exception as e:
                self.logger.warning(f"Машина {index}: ошибка валидации сети через NetworkManager: {e}")
                # Продолжить с базовой валидацией

        # Базовая валидация сетевых интерфейсов
        for i, network in enumerate(networks):
            if not isinstance(network, dict):
                self.logger.error(f"Машина {index}, сеть {i}: должна быть словарем")
                return False

            if 'bridge' not in network:
                self.logger.error(f"Машина {index}, сеть {i}: отсутствует поле 'bridge'")
                return False

        return True

    def validate_pool_config(self, pool_name: str) -> Dict[str, Any]:
        """
        Валидация конфигурации пула

        Args:
            pool_name: Имя пула для валидации

        Returns:
            Результат валидации
        """
        result = {
            'is_valid': True,
            'exists': False,
            'has_vms': 0,
            'message': ''
        }

        if not pool_name:
            result['is_valid'] = False
            result['message'] = "Имя пула не может быть пустым"
            return result

        # Использовать PoolManager для проверки если доступен
        if self.pool_manager:
            try:
                result['exists'] = self.pool_manager.check_pool_exists(pool_name)
                if result['exists']:
                    pool_vms = self.pool_manager.get_pool_vms(pool_name)
                    result['has_vms'] = len(pool_vms)
                    result['message'] = f"Пул '{pool_name}' существует, содержит {len(pool_vms)} VM"
                else:
                    result['message'] = f"Пул '{pool_name}' не существует"
            except Exception as e:
                result['message'] = f"Ошибка проверки пула: {e}"
        else:
            result['message'] = "PoolManager недоступен для проверки"

        return result

    def validate_machine_config(self, machine: Dict[str, Any], index: int) -> bool:
        """
        Валидация конфигурации одной машины

        Args:
            machine: Конфигурация машины
            index: Индекс машины в списке

        Returns:
            True если конфигурация валидна
        """
        if not isinstance(machine, dict):
            self.logger.error(f"Машина {index}: должна быть словарем")
            return False

        # Обязательные поля
        required_fields = ['template_vmid']
        for field in required_fields:
            if field not in machine:
                self.logger.error(f"Машина {index}: отсутствует обязательное поле '{field}'")
                return False

        # Валидация типа template_vmid
        if not isinstance(machine['template_vmid'], int):
            self.logger.error(f"Машина {index}: поле 'template_vmid' должно быть числом")
            return False

        # Опциональные поля
        if 'device_type' in machine:
            if machine['device_type'] not in ['linux', 'ecorouter']:
                self.logger.error(f"Машина {index}: недопустимый тип устройства '{machine['device_type']}'")
                return False

        if 'template_node' in machine:
            if not isinstance(machine['template_node'], str):
                self.logger.error(f"Машина {index}: поле 'template_node' должно быть строкой")
                return False

        return True
