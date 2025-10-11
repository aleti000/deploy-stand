#!/usr/bin/env python3
"""
Модуль управления списками пользователей
Работает со списками пользователей для развертывания стендов
"""

import os
import yaml
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class UserListManager:
    """Менеджер списков пользователей для развертывания стендов"""

    def __init__(self, data_dir: str = "data/user_list"):
        self.data_dir = Path(data_dir)
        self._ensure_data_directory()

    def _ensure_data_directory(self):
        """Создание директории для данных если она не существует"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Директория данных: {self.data_dir}")
        except Exception as e:
            logger.error(f"Ошибка создания директории {self.data_dir}: {e}")
            raise

    def create_user_list(self, list_name: str, users: List[str], description: str = "") -> bool:
        """
        Создание нового списка пользователей

        Args:
            list_name: Имя списка
            users: Список пользователей
            description: Описание списка

        Returns:
            bool: True если успешно, False иначе
        """
        try:
            # Валидация имени списка
            if not list_name or not list_name.strip():
                logger.error("Имя списка не может быть пустым")
                return False

            # Очистка имени списка
            list_name = list_name.strip()

            # Проверка существования списка
            list_file = self.data_dir / f"{list_name}.yaml"
            if list_file.exists():
                logger.error(f"Список '{list_name}' уже существует")
                return False

            # Обработка пользователей (добавление @pve если отсутствует)
            processed_users = []
            for user in users:
                user = user.strip()
                if user and not user.endswith('@pve'):
                    if '@' not in user:
                        user = f"{user}@pve"
                    processed_users.append(user)
                elif user:
                    processed_users.append(user)

            # Создание структуры списка
            user_list_data = {
                'name': list_name,
                'description': description.strip(),
                'users': processed_users,
                'count': len(processed_users),
                'created_at': str(Path(list_file).stat().st_mtime) if list_file.exists() else None
            }

            # Сохранение в YAML файл
            with open(list_file, 'w', encoding='utf-8') as file:
                yaml.dump(user_list_data, file, default_flow_style=False, allow_unicode=True, indent=2)

            logger.info(f"Создан список пользователей '{list_name}' с {len(processed_users)} пользователями")
            return True

        except Exception as e:
            logger.error(f"Ошибка создания списка пользователей: {e}")
            return False

    def get_user_lists(self) -> Dict[str, Dict[str, Any]]:
        """
        Получение всех списков пользователей

        Returns:
            Dict[str, Dict[str, Any]]: Словарь со списками пользователей
        """
        try:
            user_lists = {}

            if not self.data_dir.exists():
                return user_lists

            # Поиск всех YAML файлов в директории
            for yaml_file in self.data_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, 'r', encoding='utf-8') as file:
                        list_data = yaml.safe_load(file)

                    if list_data and isinstance(list_data, dict):
                        list_name = yaml_file.stem  # Имя файла без расширения
                        user_lists[list_name] = list_data

                except Exception as e:
                    logger.error(f"Ошибка чтения файла {yaml_file}: {e}")

            return user_lists

        except Exception as e:
            logger.error(f"Ошибка получения списков пользователей: {e}")
            return {}

    def get_user_list(self, list_name: str) -> Optional[Dict[str, Any]]:
        """
        Получение конкретного списка пользователей

        Args:
            list_name: Имя списка

        Returns:
            Optional[Dict[str, Any]]: Данные списка или None
        """
        try:
            list_file = self.data_dir / f"{list_name}.yaml"

            if not list_file.exists():
                logger.error(f"Список '{list_name}' не найден")
                return None

            with open(list_file, 'r', encoding='utf-8') as file:
                list_data = yaml.safe_load(file)

            return list_data

        except Exception as e:
            logger.error(f"Ошибка получения списка '{list_name}': {e}")
            return None

    def update_user_list(self, list_name: str, users: List[str], description: str = "") -> bool:
        """
        Обновление существующего списка пользователей

        Args:
            list_name: Имя списка
            users: Новый список пользователей
            description: Новое описание

        Returns:
            bool: True если успешно, False иначе
        """
        try:
            # Проверяем существование списка
            existing_list = self.get_user_list(list_name)
            if not existing_list:
                return False

            # Обработка пользователей
            processed_users = []
            for user in users:
                user = user.strip()
                if user and not user.endswith('@pve'):
                    if '@' not in user:
                        user = f"{user}@pve"
                    processed_users.append(user)
                elif user:
                    processed_users.append(user)

            # Обновление данных
            existing_list['users'] = processed_users
            existing_list['count'] = len(processed_users)
            if description:
                existing_list['description'] = description.strip()

            # Сохранение обновленного списка
            list_file = self.data_dir / f"{list_name}.yaml"
            with open(list_file, 'w', encoding='utf-8') as file:
                yaml.dump(existing_list, file, default_flow_style=False, allow_unicode=True, indent=2)

            logger.info(f"Обновлен список пользователей '{list_name}'")
            return True

        except Exception as e:
            logger.error(f"Ошибка обновления списка пользователей: {e}")
            return False

    def delete_user_list(self, list_name: str) -> bool:
        """
        Удаление списка пользователей

        Args:
            list_name: Имя списка для удаления

        Returns:
            bool: True если успешно, False иначе
        """
        try:
            list_file = self.data_dir / f"{list_name}.yaml"

            if not list_file.exists():
                logger.error(f"Список '{list_name}' не найден")
                return False

            # Удаление файла
            list_file.unlink()
            logger.info(f"Удален список пользователей '{list_name}'")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления списка пользователей: {e}")
            return False

    def parse_user_input(self, user_input: str) -> List[str]:
        """
        Парсинг ввода пользователя (через запятую)

        Args:
            user_input: Строка с пользователями через запятую

        Returns:
            List[str]: Список пользователей
        """
        try:
            if not user_input or not user_input.strip():
                return []

            # Разделяем по запятой и очищаем
            users = [user.strip() for user in user_input.split(',') if user.strip()]
            return users

        except Exception as e:
            logger.error(f"Ошибка парсинга ввода пользователя: {e}")
            return []

    def validate_username(self, username: str) -> bool:
        """
        Валидация имени пользователя

        Args:
            username: Имя пользователя для проверки

        Returns:
            bool: True если валидно, False иначе
        """
        try:
            if not username or not username.strip():
                return False

            # Проверяем формат username@realm
            if '@' not in username:
                return False

            parts = username.split('@')
            if len(parts) != 2:
                return False

            username_part, realm_part = parts

            # Проверяем что части не пустые
            if not username_part or not realm_part:
                return False

            # Проверяем допустимые символы в имени пользователя
            import re
            if not re.match(r'^[a-zA-Z0-9._-]+$', username_part):
                return False

            # Проверяем допустимые символы в realm
            if not re.match(r'^[a-zA-Z0-9._-]+$', realm_part):
                return False

            return True

        except Exception as e:
            logger.error(f"Ошибка валидации пользователя: {e}")
            return False

    def get_user_list_names(self) -> List[str]:
        """
        Получение имен всех списков пользователей

        Returns:
            List[str]: Список имен списков
        """
        try:
            if not self.data_dir.exists():
                return []

            list_names = [f.stem for f in self.data_dir.glob("*.yaml")]
            return sorted(list_names)

        except Exception as e:
            logger.error(f"Ошибка получения имен списков: {e}")
            return []

    
    def import_user_list(self, list_name: str, users_data: str, description: str = "") -> bool:
        """
        Импорт списка пользователей из данных

        Args:
            list_name: Имя нового списка
            users_data: Данные с пользователями
            description: Описание списка

        Returns:
            bool: True если успешно, False иначе
        """
        try:
            # Парсим данные как список пользователей через запятую
            users = self.parse_user_input(users_data)

            if not users:
                logger.error("Нет пользователей для импорта")
                return False

            # Создаем новый список
            return self.create_user_list(list_name, users, description)

        except Exception as e:
            logger.error(f"Ошибка импорта списка пользователей: {e}")
            return False

    def import_user_list_from_file(self, list_name: str, file_path: str, description: str = "") -> bool:
        """
        Импорт списка пользователей из файла

        Args:
            list_name: Имя нового списка
            file_path: Путь к файлу с пользователями
            description: Описание списка

        Returns:
            bool: True если успешно, False иначе
        """
        try:
            # Проверяем существование файла
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                logger.error(f"Файл {file_path} не найден")
                return False

            # Читаем файл построчно
            users = []
            with open(file_path_obj, 'r', encoding='utf-8') as file:
                for line_num, line in enumerate(file, 1):
                    user = line.strip()
                    if user and not user.startswith('#'):  # Игнорируем комментарии
                        users.append(user)

            if not users:
                logger.error("В файле не найдено пользователей")
                return False

            # Создаем новый список
            return self.create_user_list(list_name, users, description)

        except Exception as e:
            logger.error(f"Ошибка импорта списка пользователей из файла: {e}")
            return False


def get_user_list_manager() -> UserListManager:
    """Фабричная функция для получения менеджера списков пользователей"""
    return UserListManager()
