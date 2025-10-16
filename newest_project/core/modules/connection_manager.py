#!/usr/bin/env python3
"""
ConnectionManager - менеджер подключений к Proxmox для newest_project

Управляет подключениями к кластеру Proxmox VE, поддерживает
множественные соединения и переключение между ними.
"""

import json
import time
from typing import Dict, List, Any, Optional
from pathlib import Path

from ..utils.logger import Logger
from ..utils.validator import Validator
from ..utils.cache import Cache
from .proxmox_client import ProxmoxClient, ProxmoxClientFactory


class ConnectionManager:
    """
    Менеджер подключений к Proxmox

    Возможности:
    - Управление множественными подключениями
    - Сохранение конфигурации подключений в файл
    - Автоматическое переподключение при ошибках
    - Валидация подключений
    - Кеширование активных соединений
    """

    def __init__(self, config_file: str = "data/connections.yml",
                 logger: Optional[Logger] = None,
                 validator: Optional[Validator] = None,
                 cache: Optional[Cache] = None):
        """
        Инициализация менеджера подключений

        Args:
            config_file: Путь к файлу конфигурации подключений
            logger: Экземпляр логгера
            validator: Экземпляр валидатора
            cache: Экземпляр кеша
        """
        self.config_file = Path(config_file)
        self.logger = logger or Logger()
        self.validator = validator or Validator()
        self.cache = cache or Cache()

        # Активные подключения
        self.connections: Dict[str, ProxmoxClient] = {}
        self.current_connection: Optional[str] = None

        # Загружаем конфигурацию подключений
        self._ensure_config_directory()
        self._load_connections_config()

    def _ensure_config_directory(self) -> None:
        """Создание директории для конфигурации если её нет"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_connections_config(self) -> None:
        """Загрузка конфигурации подключений из файла"""
        if not self.config_file.exists():
            self._create_default_config()
            return

        try:
            import yaml
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.connections_config = yaml.safe_load(f) or {}
        except Exception as e:
            self.logger.log_validation_error("connections_config", str(e), "корректный YAML файл")
            self.connections_config = {}

    def _save_connections_config(self) -> None:
        """Сохранение конфигурации подключений в файл"""
        try:
            import yaml
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.connections_config, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            self.logger.log_validation_error("save_connections_config", str(e), "успешное сохранение")

    def _create_default_config(self) -> None:
        """Создание конфигурации подключений по умолчанию"""
        self.connections_config = {
            "default": {
                "host": "192.168.1.100:8006",
                "user": "root@pam",
                "use_token": False,
                "description": "Подключение по умолчанию"
            }
        }
        self._save_connections_config()

    def add_connection(self, name: str, host: str, user: str,
                      password: Optional[str] = None,
                      token_name: Optional[str] = None,
                      token_value: Optional[str] = None,
                      description: str = "") -> bool:
        """
        Добавление нового подключения

        Args:
            name: Имя подключения
            host: Хост Proxmox
            user: Пользователь
            password: Пароль (если используется)
            token_name: Имя токена API (если используется)
            token_value: Значение токена API
            description: Описание подключения

        Returns:
            True если подключение успешно добавлено
        """
        # Валидация данных подключения
        connection_data = {
            'host': host,
            'user': user,
            'password': password,
            'token_name': token_name,
            'token_value': token_value
        }

        if not self.validator.validate_proxmox_connection(connection_data):
            self.logger.log_validation_error("add_connection", name, "добавление подключения")
            for error in self.validator.get_errors():
                self.logger.log_validation_error("connection_data", error, "корректные данные")
            return False

        # Сохраняем конфигурацию
        self.connections_config[name] = {
            'host': host,
            'user': user,
            'password': password,  # В реальности пароль должен шифроваться
            'token_name': token_name,
            'token_value': token_value,  # В реальности токен должен шифроваться
            'description': description,
            'use_token': token_name is not None
        }

        self._save_connections_config()
        self.logger.log_cache_operation("add_connection", name, True)

        return True

    def remove_connection(self, name: str) -> bool:
        """
        Удаление подключения

        Args:
            name: Имя подключения

        Returns:
            True если подключение успешно удалено
        """
        if name not in self.connections_config:
            self.logger.log_validation_error("remove_connection", name, "существующее подключение")
            return False

        # Закрываем активное подключение если удаляем текущее
        if self.current_connection == name:
            self.disconnect(name)

        # Удаляем из конфигурации
        del self.connections_config[name]
        self._save_connections_config()

        self.logger.log_cache_operation("remove_connection", name, True)
        return True

    def get_connections_list(self) -> List[Dict[str, Any]]:
        """
        Получение списка доступных подключений

        Returns:
            Список подключений с метаданными
        """
        connections = []

        for name, config in self.connections_config.items():
            # Проверяем статус подключения
            is_connected = False
            is_current = (name == self.current_connection)

            if name in self.connections:
                is_connected = self.connections[name].is_connected()

            connections.append({
                'name': name,
                'host': config['host'],
                'user': config['user'],
                'description': config.get('description', ''),
                'connected': is_connected,
                'current': is_current,
                'use_token': config.get('use_token', False)
            })

        return connections

    def connect_to(self, name: str) -> bool:
        """
        Подключение к указанному серверу Proxmox

        Args:
            name: Имя подключения

        Returns:
            True если подключение успешно установлено
        """
        if name not in self.connections_config:
            self.logger.log_validation_error("connect_to", name, "существующее подключение")
            return False

        # Закрываем текущее подключение
        if self.current_connection and self.current_connection != name:
            self.disconnect(self.current_connection)

        # Получаем конфигурацию подключения
        config = self.connections_config[name]

        try:
            # Создаем клиент Proxmox
            client = ProxmoxClientFactory.create_client(
                host=config['host'],
                user=config['user'],
                password=config.get('password'),
                token_name=config.get('token_name'),
                token_value=config.get('token_value'),
                logger=self.logger,
                validator=self.validator,
                cache=self.cache
            )

            # Устанавливаем подключение
            if client.connect(
                host=config['host'],
                user=config['user'],
                password=config.get('password'),
                token_name=config.get('token_name'),
                token_value=config.get('token_value')
            ):
                # Сохраняем подключение
                self.connections[name] = client
                self.current_connection = name

                self.logger.log_connection_success(config['host'], client.get_version())
                return True
            else:
                self.logger.log_connection_error(config['host'], "Не удалось установить подключение")
                return False

        except Exception as e:
            self.logger.log_connection_error(config['host'], str(e))
            return False

    def disconnect(self, name: Optional[str] = None) -> None:
        """
        Отключение от сервера Proxmox

        Args:
            name: Имя подключения (если None, то текущее)
        """
        connection_name = name or self.current_connection

        if connection_name and connection_name in self.connections:
            try:
                self.connections[connection_name].disconnect()
                del self.connections[connection_name]

                if self.current_connection == connection_name:
                    self.current_connection = None

                self.logger.log_cache_operation("disconnect", connection_name, True)

            except Exception as e:
                self.logger.log_validation_error("disconnect", connection_name, f"успешное отключение: {str(e)}")

    def get_current_connection(self) -> Optional[ProxmoxClient]:
        """
        Получение текущего активного подключения

        Returns:
            Клиент Proxmox или None если нет активного подключения
        """
        if self.current_connection and self.current_connection in self.connections:
            client = self.connections[self.current_connection]
            if client.is_connected():
                return client

        return None

    def get_connection(self, name: str) -> Optional[ProxmoxClient]:
        """
        Получение подключения по имени

        Args:
            name: Имя подключения

        Returns:
            Клиент Proxmox или None если подключение не найдено
        """
        if name in self.connections:
            client = self.connections[name]
            if client.is_connected():
                return client

        return None

    def test_connection(self, name: str) -> Dict[str, Any]:
        """
        Тестирование подключения

        Args:
            name: Имя подключения

        Returns:
            Результат тестирования с деталями
        """
        if name not in self.connections_config:
            return {
                'success': False,
                'error': 'Подключение не найдено в конфигурации'
            }

        config = self.connections_config[name]

        try:
            # Создаем тестовый клиент
            test_client = ProxmoxClientFactory.create_client(
                host=config['host'],
                user=config['user'],
                password=config.get('password'),
                token_name=config.get('token_name'),
                token_value=config.get('token_value'),
                logger=self.logger,
                validator=self.validator,
                cache=self.cache
            )

            # Пытаемся подключиться
            start_time = time.time()
            success = test_client.connect(
                host=config['host'],
                user=config['user'],
                password=config.get('password'),
                token_name=config.get('token_name'),
                token_value=config.get('token_value')
            )
            connection_time = time.time() - start_time

            if success:
                version = test_client.get_version()
                nodes = test_client.get_nodes()

                result = {
                    'success': True,
                    'connection_time': round(connection_time, 2),
                    'version': version,
                    'nodes_count': len(nodes),
                    'nodes': nodes[:5],  # Первые 5 нод
                    'host': config['host'],
                    'user': config['user']
                }

                test_client.disconnect()
                return result
            else:
                return {
                    'success': False,
                    'connection_time': round(connection_time, 2),
                    'error': 'Не удалось установить подключение'
                }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def reconnect(self, name: Optional[str] = None) -> bool:
        """
        Переподключение к серверу

        Args:
            name: Имя подключения (если None, то текущее)

        Returns:
            True если переподключение успешно
        """
        connection_name = name or self.current_connection

        if not connection_name:
            self.logger.log_validation_error("reconnect", "no_connection", "активное подключение")
            return False

        # Отключаемся
        self.disconnect(connection_name)

        # Подключаемся заново
        return self.connect_to(connection_name)

    def cleanup_connections(self) -> int:
        """
        Очистка неактивных подключений

        Returns:
            Количество очищенных подключений
        """
        inactive_connections = []

        for name, client in self.connections.items():
            if not client.is_connected():
                inactive_connections.append(name)

        for name in inactive_connections:
            del self.connections[name]

        if inactive_connections:
            self.logger.log_cache_operation("cleanup", f"{len(inactive_connections)}_connections", True)

        return len(inactive_connections)

    def get_connection_stats(self) -> Dict[str, Any]:
        """Получение статистики подключений"""
        active_count = sum(1 for client in self.connections.values() if client.is_connected())
        total_count = len(self.connections_config)

        return {
            'total_configured': total_count,
            'active_connections': active_count,
            'inactive_connections': total_count - active_count,
            'current_connection': self.current_connection,
            'connections_list': self.get_connections_list()
        }


# Глобальный экземпляр менеджера подключений
_global_connection_manager = None


def get_connection_manager(config_file: str = "data/connections.yml") -> ConnectionManager:
    """Получить глобальный экземпляр менеджера подключений"""
    global _global_connection_manager
    if _global_connection_manager is None:
        _global_connection_manager = ConnectionManager(config_file)
    return _global_connection_manager


# Пример использования
if __name__ == "__main__":
    print("🔗 ConnectionManager - менеджер подключений к Proxmox")
    print("📋 Доступные методы:")

    # Получаем все публичные методы
    methods = [method for method in dir(ConnectionManager) if not method.startswith('_') and callable(getattr(ConnectionManager, method))]
    for method in methods:
        print(f"  - {method}")

    print(f"\n📊 Всего методов: {len(methods)}")
    print("✅ Менеджер подключений готов к использованию")
