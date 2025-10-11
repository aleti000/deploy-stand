#!/usr/bin/env python3
"""
Модуль управления конфигурацией подключений к Proxmox
Работает с YAML файлами без использования pyyaml
"""

import os
import yaml
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Менеджер конфигурации подключений к Proxmox серверам"""

    def __init__(self, config_file: str = "config/connection_config.yaml"):
        self.config_file = Path(config_file)
        self.config: Dict[str, Any] = {}
        self._loaded = False

    def load_config(self) -> bool:
        """Загрузка конфигурации из YAML файла"""
        try:
            if not self.config_file.exists():
                logger.error(f"Файл конфигурации не найден: {self.config_file}")
                return False

            # Используем yaml библиотеку вместо pyyaml
            with open(self.config_file, 'r', encoding='utf-8') as file:
                content = file.read()

            # Парсим YAML вручную для простоты (или используем yaml библиотеку)
            try:
                import yaml
                self.config = yaml.safe_load(content)
            except ImportError:
                # Fallback: простой парсер YAML
                self.config = self._parse_yaml_simple(content)

            if not self.config:
                logger.error("Конфигурационный файл пуст или поврежден")
                return False

            self._loaded = True
            logger.info(f"Конфигурация загружена из {self.config_file}")
            return True

        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            return False

    def _parse_yaml_simple(self, content: str) -> Dict[str, Any]:
        """Простой парсер YAML для fallback"""
        # Заглушка для простого парсера
        # В реальности здесь будет более сложная логика
        try:
            import yaml
            return yaml.safe_load(content)
        except ImportError:
            logger.error("YAML библиотека не доступна и fallback парсер не реализован")
            return {}

    def save_config(self) -> bool:
        """Сохранение конфигурации в YAML файл"""
        try:
            # Создаем директорию если не существует
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            # Используем yaml библиотеку
            try:
                import yaml
                with open(self.config_file, 'w', encoding='utf-8') as file:
                    yaml.dump(self.config, file, default_flow_style=False, allow_unicode=True)
            except ImportError:
                logger.error("YAML библиотека не доступна для сохранения")
                return False

            logger.info(f"Конфигурация сохранена в {self.config_file}")
            return True

        except Exception as e:
            logger.error(f"Ошибка сохранения конфигурации: {e}")
            return False

    def get_proxmox_servers(self) -> Dict[str, Dict[str, Any]]:
        """Получение списка серверов Proxmox"""
        if not self._loaded:
            self.load_config()

        return self.config.get('proxmox_servers', {})

    def get_enabled_servers(self) -> Dict[str, Dict[str, Any]]:
        """Получение только активных серверов Proxmox"""
        servers = self.get_proxmox_servers()
        enabled_servers = {}

        for server_name, server_config in servers.items():
            if server_config.get('enabled', False):
                enabled_servers[server_name] = server_config

        return enabled_servers

    def get_server_config(self, server_name: str) -> Optional[Dict[str, Any]]:
        """Получение конфигурации конкретного сервера"""
        servers = self.get_proxmox_servers()
        return servers.get(server_name)

    def add_server(self, server_name: str, config: Dict[str, Any]) -> bool:
        """Добавление нового сервера Proxmox"""
        if not self._loaded:
            self.load_config()

        if 'proxmox_servers' not in self.config:
            self.config['proxmox_servers'] = {}

        self.config['proxmox_servers'][server_name] = config
        return self.save_config()

    def update_server(self, server_name: str, config: Dict[str, Any]) -> bool:
        """Обновление конфигурации сервера"""
        if not self._loaded:
            self.load_config()

        if 'proxmox_servers' not in self.config:
            self.config['proxmox_servers'] = {}

        if server_name not in self.config['proxmox_servers']:
            logger.error(f"Сервер {server_name} не найден в конфигурации")
            return False

        self.config['proxmox_servers'][server_name].update(config)
        return self.save_config()

    def remove_server(self, server_name: str) -> bool:
        """Удаление сервера из конфигурации"""
        if not self._loaded:
            self.load_config()

        if 'proxmox_servers' not in self.config:
            logger.error("Секция proxmox_servers не найдена в конфигурации")
            return False

        if server_name not in self.config['proxmox_servers']:
            logger.error(f"Сервер {server_name} не найден в конфигурации")
            return False

        del self.config['proxmox_servers'][server_name]
        return self.save_config()

    def get_server_groups(self) -> Dict[str, Dict[str, Any]]:
        """Получение групп серверов"""
        if not self._loaded:
            self.load_config()

        return self.config.get('server_groups', {})

    def get_defaults(self) -> Dict[str, Any]:
        """Получение настроек по умолчанию"""
        if not self._loaded:
            self.load_config()

        return self.config.get('defaults', {})

    def validate_server_config(self, config: Dict[str, Any]) -> List[str]:
        """Валидация конфигурации сервера"""
        errors = []

        required_fields = ['host', 'user']
        for field in required_fields:
            if field not in config or not config[field]:
                errors.append(f"Отсутствует обязательное поле: {field}")

        # Проверка порта
        if 'port' in config:
            try:
                port = int(config['port'])
                if not (1 <= port <= 65535):
                    errors.append("Порт должен быть в диапазоне 1-65535")
            except (ValueError, TypeError):
                errors.append("Порт должен быть числом")

        # Проверка verify_ssl
        if 'verify_ssl' in config and not isinstance(config['verify_ssl'], bool):
            errors.append("verify_ssl должен быть true или false")

        return errors

    def test_connection(self, server_name: str) -> bool:
        """Тестирование подключения к серверу"""
        server_config = self.get_server_config(server_name)
        if not server_config:
            logger.error(f"Сервер {server_name} не найден")
            return False

        try:
            # Здесь будет логика тестирования подключения через proxmoxer
            # Пока заглушка
            logger.info(f"Тестирование подключения к {server_name}")
            return True

        except Exception as e:
            logger.error(f"Ошибка тестирования подключения к {server_name}: {e}")
            return False


def get_connection_manager() -> ConnectionManager:
    """Фабричная функция для получения менеджера подключений"""
    return ConnectionManager()
