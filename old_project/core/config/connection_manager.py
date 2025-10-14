"""
Менеджер подключений системы Deploy-Stand

Предоставляет функциональность для управления конфигурациями подключений
к кластеру Proxmox VE.
"""

import logging
from typing import Dict, List, Any, Optional
from .config_manager import ConfigManager

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Менеджер конфигураций подключений"""

    def __init__(self, config_manager: ConfigManager):
        """
        Инициализация менеджера подключений

        Args:
            config_manager: Менеджер конфигурации
        """
        self.config_manager = config_manager

    def create_connection_config(self, name: str, host: str, user: str,
                                password: str = None, token_name: str = None,
                                token_value: str = None) -> bool:
        """
        Создать конфигурацию подключения

        Args:
            name: Имя конфигурации
            host: Адрес сервера Proxmox
            user: Имя пользователя
            password: Пароль пользователя
            token_name: Имя токена (если используется)
            token_value: Значение токена

        Returns:
            True если создание успешно
        """
        try:
            # Загрузить существующие конфигурации
            connections = self.config_manager.load_connections_config() or {}

            # Создать новую конфигурацию
            connection_config = {
                'host': host,
                'user': user,
                'use_token': token_name is not None and token_value is not None
            }

            if connection_config['use_token']:
                connection_config['token_name'] = token_name
                connection_config['token_value'] = token_value
            else:
                connection_config['password'] = password

            # Добавить в список конфигураций
            connections[name] = connection_config

            # Сохранить конфигурации
            return self.config_manager.save_connections_config(connections)

        except Exception as e:
            logger.error(f"Ошибка создания конфигурации подключения {name}: {e}")
            return False

    def delete_connection_config(self, name: str) -> bool:
        """
        Удалить конфигурацию подключения

        Args:
            name: Имя конфигурации для удаления

        Returns:
            True если удаление успешно
        """
        try:
            # Загрузить существующие конфигурации
            connections = self.config_manager.load_connections_config() or {}

            if name not in connections:
                logger.warning(f"Конфигурация подключения {name} не найдена")
                return False

            # Удалить конфигурацию
            del connections[name]

            # Сохранить изменения
            return self.config_manager.save_connections_config(connections)

        except Exception as e:
            logger.error(f"Ошибка удаления конфигурации подключения {name}: {e}")
            return False

    def get_connection_config(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Получить конфигурацию подключения

        Args:
            name: Имя конфигурации

        Returns:
            Конфигурация подключения или None если не найдена
        """
        try:
            connections = self.config_manager.load_connections_config() or {}
            return connections.get(name)
        except Exception as e:
            logger.error(f"Ошибка получения конфигурации подключения {name}: {e}")
            return None

    def list_connection_configs(self) -> List[str]:
        """
        Получить список доступных конфигураций подключений

        Returns:
            Список имен конфигураций
        """
        try:
            connections = self.config_manager.load_connections_config() or {}
            return list(connections.keys())
        except Exception as e:
            logger.error(f"Ошибка получения списка конфигураций подключений: {e}")
            return []

    def test_connection_config(self, name: str) -> bool:
        """
        Протестировать конфигурацию подключения

        Args:
            name: Имя конфигурации для тестирования

        Returns:
            True если подключение успешно
        """
        try:
            config = self.get_connection_config(name)
            if not config:
                logger.error(f"Конфигурация подключения {name} не найдена")
                return False

            # Создать тестовое подключение
            from core.proxmox.proxmox_client import ProxmoxClient

            proxmox = ProxmoxClient(
                host=config['host'],
                user=config['user'],
                password=None if config.get('use_token') else config.get('password'),
                token_name=config['token_name'] if config.get('use_token') else None,
                token_value=config['token_value'] if config.get('use_token') else None
            )

            # Проверить подключение
            nodes = proxmox.get_nodes()
            logger.info(f"Подключение к {name} успешно. Доступные ноды: {', '.join(nodes)}")
            return True

        except Exception as e:
            logger.error(f"Ошибка тестирования подключения {name}: {e}")
            return False

    def update_connection_config(self, name: str, **kwargs) -> bool:
        """
        Обновить конфигурацию подключения

        Args:
            name: Имя конфигурации для обновления
            **kwargs: Параметры для обновления

        Returns:
            True если обновление успешно
        """
        try:
            # Загрузить существующие конфигурации
            connections = self.config_manager.load_connections_config() or {}

            if name not in connections:
                logger.error(f"Конфигурация подключения {name} не найдена")
                return False

            # Обновить параметры
            for key, value in kwargs.items():
                if value is not None:
                    connections[name][key] = value

            # Сохранить изменения
            return self.config_manager.save_connections_config(connections)

        except Exception as e:
            logger.error(f"Ошибка обновления конфигурации подключения {name}: {e}")
            return False

    def get_default_connection(self) -> Optional[str]:
        """
        Получить имя конфигурации подключения по умолчанию

        Returns:
            Имя конфигурации по умолчанию или None
        """
        try:
            connections = self.config_manager.load_connections_config() or {}

            # Если есть только одна конфигурация, вернуть её
            if len(connections) == 1:
                return list(connections.keys())[0]

            # Искать конфигурацию с пометкой default
            for name, config in connections.items():
                if config.get('default', False):
                    return name

            # Если нет пометки default, вернуть первую
            if connections:
                return list(connections.keys())[0]

            return None

        except Exception as e:
            logger.error(f"Ошибка получения конфигурации по умолчанию: {e}")
            return None

    def set_default_connection(self, name: str) -> bool:
        """
        Установить конфигурацию подключения по умолчанию

        Args:
            name: Имя конфигурации для установки по умолчанию

        Returns:
            True если установка успешна
        """
        try:
            # Загрузить существующие конфигурации
            connections = self.config_manager.load_connections_config() or {}

            if name not in connections:
                logger.error(f"Конфигурация подключения {name} не найдена")
                return False

            # Снять пометку default со всех конфигураций
            for config in connections.values():
                config['default'] = False

            # Установить пометку default для выбранной конфигурации
            connections[name]['default'] = True

            # Сохранить изменения
            return self.config_manager.save_connections_config(connections)

        except Exception as e:
            logger.error(f"Ошибка установки конфигурации по умолчанию {name}: {e}")
            return False
