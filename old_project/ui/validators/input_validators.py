"""
Валидаторы ввода пользовательского интерфейса

Предоставляет функциональность для валидации и обработки пользовательского ввода
в интерактивном интерфейсе системы Deploy-Stand.
"""

import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class InputValidator:
    """Валидатор пользовательского ввода"""

    @staticmethod
    def validate_user_input(user_input: str, allow_empty: bool = False) -> Tuple[bool, str]:
        """
        Валидация пользовательского ввода

        Args:
            user_input: Введенная строка
            allow_empty: Разрешить пустой ввод

        Returns:
            Кортеж (валиден, сообщение об ошибке)
        """
        if not user_input:
            if allow_empty:
                return True, ""
            return False, "Пустой ввод не разрешен"

        if len(user_input.strip()) == 0:
            if allow_empty:
                return True, ""
            return False, "Ввод не может состоять только из пробелов"

        return True, ""

    @staticmethod
    def validate_users_list(users_str: str) -> Tuple[bool, list, str]:
        """
        Валидация списка пользователей

        Args:
            users_str: Строка со списком пользователей через запятую

        Returns:
            Кортеж (валиден, список пользователей, сообщение об ошибке)
        """
        valid, message = InputValidator.validate_user_input(users_str, allow_empty=False)
        if not valid:
            return False, [], message

        try:
            users = [user.strip() for user in users_str.split(',') if user.strip()]
            invalid_users = []

            for user in users:
                if not InputValidator.validate_user_format(user):
                    invalid_users.append(user)

            if invalid_users:
                return False, [], f"Некорректный формат пользователей: {', '.join(invalid_users)}"

            return True, users, ""

        except Exception as e:
            return False, [], f"Ошибка обработки списка пользователей: {e}"

    @staticmethod
    def validate_user_format(username: str) -> bool:
        """
        Валидация формата имени пользователя

        Args:
            username: Имя пользователя для проверки

        Returns:
            True если формат корректен
        """
        if not username or '@' not in username:
            return False

        # Проверка базового формата user@pve
        pattern = r'^[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+$'
        return bool(re.match(pattern, username))

    @staticmethod
    def validate_numeric_input(value: str, min_val: Optional[int] = None,
                             max_val: Optional[int] = None) -> Tuple[bool, int, str]:
        """
        Валидация числового ввода

        Args:
            value: Введенная строка
            min_val: Минимальное допустимое значение
            max_val: Максимальное допустимое значение

        Returns:
            Кортеж (валиден, число, сообщение об ошибке)
        """
        valid, message = InputValidator.validate_user_input(value, allow_empty=False)
        if not valid:
            return False, 0, message

        try:
            num_value = int(value)

            if min_val is not None and num_value < min_val:
                return False, 0, f"Значение должно быть не менее {min_val}"

            if max_val is not None and num_value > max_val:
                return False, 0, f"Значение должно быть не более {max_val}"

            return True, num_value, ""

        except ValueError:
            return False, 0, "Введено некорректное число"

    @staticmethod
    def validate_choice_input(value: str, valid_choices: list) -> Tuple[bool, str, str]:
        """
        Валидация выбора из списка

        Args:
            value: Введенное значение
            valid_choices: Список допустимых значений

        Returns:
            Кортеж (валиден, выбранное значение, сообщение об ошибке)
        """
        valid, message = InputValidator.validate_user_input(value, allow_empty=False)
        if not valid:
            return False, "", message

        if value not in valid_choices:
            return False, "", f"Выберите одно из: {', '.join(valid_choices)}"

        return True, value, ""

    @staticmethod
    def validate_yes_no_input(value: str) -> Tuple[bool, bool, str]:
        """
        Валидация ввода да/нет

        Args:
            value: Введенное значение

        Returns:
            Кортеж (валиден, True для да, сообщение об ошибке)
        """
        valid, message = InputValidator.validate_user_input(value, allow_empty=False)
        if not valid:
            return False, False, message

        if value.lower() in ['y', 'yes', 'да']:
            return True, True, ""
        elif value.lower() in ['n', 'no', 'нет']:
            return True, False, ""
        else:
            return False, False, "Введите 'y' для подтверждения или 'n' для отмены"

    @staticmethod
    def validate_ip_address(ip_str: str) -> Tuple[bool, str]:
        """
        Валидация IP адреса

        Args:
            ip_str: Строка с IP адресом

        Returns:
            Кортеж (валиден, сообщение об ошибке)
        """
        valid, message = InputValidator.validate_user_input(ip_str, allow_empty=False)
        if not valid:
            return False, message

        # Простая валидация IPv4
        pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(pattern, ip_str):
            return False, "Некорректный формат IP адреса"

        # Проверка диапазона октетов
        octets = ip_str.split('.')
        for octet in octets:
            try:
                num = int(octet)
                if num < 0 or num > 255:
                    return False, f"Октет {octet} вне допустимого диапазона 0-255"
            except ValueError:
                return False, f"Некорректный октет: {octet}"

        return True, ""

    @staticmethod
    def validate_port(port_str: str) -> Tuple[bool, int, str]:
        """
        Валидация порта

        Args:
            port_str: Строка с номером порта

        Returns:
            Кортеж (валиден, номер порта, сообщение об ошибке)
        """
        valid, port, message = InputValidator.validate_numeric_input(port_str, 1, 65535)
        if not valid:
            return False, 0, message

        return True, port, ""

    @staticmethod
    def validate_vmid(vmid_str: str) -> Tuple[bool, int, str]:
        """
        Валидация VMID

        Args:
            vmid_str: Строка с VMID

        Returns:
            Кортеж (валиден, VMID, сообщение об ошибке)
        """
        valid, vmid, message = InputValidator.validate_numeric_input(vmid_str, 100, 999999999)
        if not valid:
            return False, 0, message

        return True, vmid, ""

    @staticmethod
    def validate_node_name(node_name: str) -> Tuple[bool, str]:
        """
        Валидация имени ноды

        Args:
            node_name: Имя ноды для проверки

        Returns:
            Кортеж (валиден, сообщение об ошибке)
        """
        valid, message = InputValidator.validate_user_input(node_name, allow_empty=False)
        if not valid:
            return False, message

        # Проверка формата имени ноды (буквы, цифры, дефисы)
        pattern = r'^[a-zA-Z0-9_-]+$'
        if not re.match(pattern, node_name):
            return False, "Имя ноды может содержать только буквы, цифры, дефисы и подчеркивания"

        if len(node_name) > 50:
            return False, "Имя ноды слишком длинное (максимум 50 символов)"

        return True, ""

    @staticmethod
    def validate_bridge_name(bridge_name: str) -> Tuple[bool, str]:
        """
        Валидация имени bridge'а

        Args:
            bridge_name: Имя bridge'а для проверки

        Returns:
            Кортеж (валиден, сообщение об ошибке)
        """
        valid, message = InputValidator.validate_user_input(bridge_name, allow_empty=False)
        if not valid:
            return False, message

        # Проверка формата имени bridge'а
        pattern = r'^[a-zA-Z0-9_-]+$'
        if not re.match(pattern, bridge_name):
            return False, "Имя bridge'а может содержать только буквы, цифры, дефисы и подчеркивания"

        if len(bridge_name) > 20:
            return False, "Имя bridge'а слишком длинное (максимум 20 символов)"

        return True, ""

    @staticmethod
    def validate_template_name(template_name: str) -> Tuple[bool, str]:
        """
        Валидация имени шаблона

        Args:
            template_name: Имя шаблона для проверки

        Returns:
            Кортеж (валиден, сообщение об ошибке)
        """
        valid, message = InputValidator.validate_user_input(template_name, allow_empty=False)
        if not valid:
            return False, message

        # Проверка формата имени шаблона
        pattern = r'^[a-zA-Z0-9_-]+$'
        if not re.match(pattern, template_name):
            return False, "Имя шаблона может содержать только буквы, цифры, дефисы и подчеркивания"

        if len(template_name) > 50:
            return False, "Имя шаблона слишком длинное (максимум 50 символов)"

        return True, ""

    @staticmethod
    def validate_config_name(config_name: str) -> Tuple[bool, str]:
        """
        Валидация имени конфигурации

        Args:
            config_name: Имя конфигурации для проверки

        Returns:
            Кортеж (валиден, сообщение об ошибке)
        """
        valid, message = InputValidator.validate_user_input(config_name, allow_empty=False)
        if not valid:
            return False, message

        # Проверка формата имени конфигурации
        pattern = r'^[a-zA-Z0-9_-]+$'
        if not re.match(pattern, config_name):
            return False, "Имя конфигурации может содержать только буквы, цифры, дефисы и подчеркивания"

        if len(config_name) > 50:
            return False, "Имя конфигурации слишком длинное (максимум 50 символов)"

        return True, ""

    @staticmethod
    def validate_file_path(file_path: str) -> Tuple[bool, str]:
        """
        Валидация пути к файлу

        Args:
            file_path: Путь к файлу для проверки

        Returns:
            Кортеж (валиден, сообщение об ошибке)
        """
        valid, message = InputValidator.validate_user_input(file_path, allow_empty=False)
        if not valid:
            return False, message

        # Базовая проверка пути
        if '..' in file_path:
            return False, "Путь не может содержать '..'"

        if file_path.startswith('/'):
            return False, "Используйте относительный путь"

        return True, ""

    @staticmethod
    def sanitize_input(user_input: str) -> str:
        """
        Очистка пользовательского ввода

        Args:
            user_input: Ввод для очистки

        Returns:
            Очищенная строка
        """
        if not user_input:
            return ""

        # Удалить потенциально опасные символы
        dangerous_chars = ['<', '>', '|', '&', ';', '$', '`', '\\']
        sanitized = user_input

        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '')

        return sanitized.strip()

    @staticmethod
    def get_input_with_validation(prompt: str, validator_func, max_attempts: int = 3) -> Optional[str]:
        """
        Получить ввод с валидацией

        Args:
            prompt: Приглашение для ввода
            validator_func: Функция валидации
            max_attempts: Максимальное количество попыток

        Returns:
            Валидированный ввод или None при ошибке
        """
        for attempt in range(max_attempts):
            user_input = input(prompt).strip()

            valid, result, message = validator_func(user_input)

            if valid:
                return result
            else:
                print(f"❌ {message}")
                if attempt < max_attempts - 1:
                    print(f"Попробуйте еще раз (попытка {attempt + 2}/{max_attempts})")
                else:
                    print("Превышено максимальное количество попыток")
                    return None

        return None
