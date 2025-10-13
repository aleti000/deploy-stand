#!/usr/bin/env python3
"""
Менеджер подключений к Proxmox серверам
"""

import os
import logging
from typing import Dict, List, Any, Optional
import yaml as yaml_module


class ConnectionManager:
    """Менеджер подключений к Proxmox серверам"""

    CONNECTIONS_DIR = "data"
    CONNECTIONS_FILE = "data/connections_config.yml"

    def __init__(self, logger_instance=None):
        """
        Инициализация менеджера подключений

        Args:
            logger_instance: Экземпляр логгера (опционально)
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self._ensure_directories()

    def _ensure_directories(self):
        """Создать необходимые директории если они не существуют"""
        try:
            os.makedirs(self.CONNECTIONS_DIR, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Ошибка создания директории: {e}")

    def load_connections(self) -> Dict[str, Any]:
        """
        Загрузить сохраненные подключения

        Returns:
            Словарь с подключениями
        """
        return self._load_yaml_file(self.CONNECTIONS_FILE) or {}

    def save_connection(self, connection_name: str, connection_data: Dict[str, Any]) -> bool:
        """
        Сохранить новое подключение

        Args:
            connection_name: Имя подключения
            connection_data: Данные подключения

        Returns:
            True если сохранение успешно
        """
        try:
            connections = self.load_connections()

            # Добавляем или обновляем подключение
            connections[connection_name] = {
                'name': connection_name,
                'host': connection_data['host'],
                'username': connection_data['username'],
                'password': connection_data.get('password'),
                'timestamp': connection_data.get('timestamp', None)
            }

            return self._save_yaml_file(self.CONNECTIONS_FILE, connections)

        except Exception as e:
            self.logger.error(f"Ошибка сохранения подключения {connection_name}: {e}")
            return False

    def get_connection(self, connection_name: str) -> Optional[Dict[str, Any]]:
        """
        Получить подключение по имени

        Args:
            connection_name: Имя подключения

        Returns:
            Данные подключения или None
        """
        connections = self.load_connections()
        return connections.get(connection_name)

    def list_connections(self) -> List[str]:
        """
        Получить список имен сохраненных подключений

        Returns:
            Список имен подключений
        """
        connections = self.load_connections()
        return list(connections.keys())

    def delete_connection(self, connection_name: str) -> bool:
        """
        Удалить подключение

        Args:
            connection_name: Имя подключения для удаления

        Returns:
            True если удаление успешно
        """
        try:
            connections = self.load_connections()

            if connection_name in connections:
                del connections[connection_name]
                success = self._save_yaml_file(self.CONNECTIONS_FILE, connections)
                if success:
                    self.logger.info(f"Подключение {connection_name} удалено")
                return success
            else:
                self.logger.warning(f"Подключение {connection_name} не найдено")
                return False

        except Exception as e:
            self.logger.error(f"Ошибка удаления подключения {connection_name}: {e}")
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
                return None

            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                if not content.strip():
                    return None

                data = yaml_module.safe_load(content)
                return data if data is not None else {}

        except yaml_module.YAMLError as e:
            self.logger.error(f"Ошибка парсинга YAML файла {file_path}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Ошибка чтения файла {file_path}: {e}")
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
