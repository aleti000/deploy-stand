"""
Валидаторы конфигурации системы Deploy-Stand

Предоставляет функциональность для валидации конфигурационных файлов
и параметров развертывания.
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Валидатор конфигурации развертывания"""

    @staticmethod
    def validate_deployment_config(config: Dict[str, Any]) -> bool:
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
                if not ConfigValidator._validate_machine_config(machine, i):
                    return False

            return True

        except Exception as e:
            logger.error(f"Ошибка валидации конфигурации: {e}")
            return False

    @staticmethod
    def _validate_machine_config(machine: Dict[str, Any], index: int) -> bool:
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

    @staticmethod
    def validate_users_list(users: List[str]) -> bool:
        """
        Валидация списка пользователей

        Args:
            users: Список пользователей для валидации

        Returns:
            True если список валиден
        """
        if not isinstance(users, list):
            logger.error("Список пользователей должен быть списком")
            return False

        if len(users) == 0:
            logger.error("Список пользователей не может быть пустым")
            return False

        for i, user in enumerate(users):
            if not isinstance(user, str) or '@' not in user:
                logger.error(f"Пользователь {i}: некорректный формат '{user}' (ожидается user@pve)")
                return False

        return True

    @staticmethod
    def validate_connection_config(config: Dict[str, Any]) -> bool:
        """
        Валидация конфигурации подключения

        Args:
            config: Конфигурация подключения для валидации

        Returns:
            True если конфигурация валидна
        """
        required_fields = ['host', 'user']

        for field in required_fields:
            if field not in config:
                logger.error(f"Конфигурация подключения не содержит обязательное поле '{field}'")
                return False

        # Проверка аутентификации
        use_token = config.get('use_token', False)

        if use_token:
            if 'token_name' not in config or 'token_value' not in config:
                logger.error("Для аутентификации по токену необходимы поля 'token_name' и 'token_value'")
                return False
        else:
            if 'password' not in config:
                logger.error("Для аутентификации по паролю необходимо поле 'password'")
                return False

        return True
