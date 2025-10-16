#!/usr/bin/env python3
"""
ConfigManager - менеджер конфигурации для newest_project

Управляет загрузкой, валидацией и сохранением YAML конфигурационных файлов.
Интегрирует Logger, Validator, Cache для надежной работы с конфигурацией.
"""

import os
from typing import Dict, List, Any, Optional, Union
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ Библиотека yaml не установлена. Установите: pip install PyYAML")
    yaml = None

from ..utils.logger import Logger
from ..utils.validator import Validator
from ..utils.cache import Cache


class ConfigManager:
    """
    Менеджер конфигурации развертывания

    Возможности:
    - Загрузка и сохранение YAML конфигураций
    - Валидация структуры конфигурации
    - Кеширование загруженных конфигураций
    - Работа с несколькими типами конфигураций
    - Автоматическое создание конфигурации по умолчанию
    """

    def __init__(self, config_dir: str = "data",
                 logger: Optional[Logger] = None,
                 validator: Optional[Validator] = None,
                 cache: Optional[Cache] = None):
        """
        Инициализация менеджера конфигурации

        Args:
            config_dir: Директория для конфигурационных файлов
            logger: Экземпляр логгера
            validator: Экземпляр валидатора
            cache: Экземпляр кеша
        """
        if yaml is None:
            raise ImportError("Библиотека yaml не доступна")

        self.config_dir = Path(config_dir)
        self.logger = logger or Logger()
        self.validator = validator or Validator()
        self.cache = cache or Cache()

        # Создаем директорию для конфигурации
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Типы конфигураций
        self.config_types = {
            'deployment': 'deployment_config.yml',
            'connections': 'connections.yml',
            'users': 'users.yml'
        }

    def load_deployment_config(self, config_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Загрузка конфигурации развертывания

        Args:
            config_file: Путь к файлу конфигурации (если None, используется значение по умолчанию)

        Returns:
            Конфигурация развертывания или None при ошибке
        """
        file_path = Path(config_file) if config_file else self.config_dir / self.config_types['deployment']

        # Проверяем кеш
        cache_key = f"deployment_config:{file_path}"
        cached_config = self.cache.get(cache_key)
        if cached_config:
            self.logger.log_cache_operation("hit", cache_key, True)
            return cached_config

        try:
            if not file_path.exists():
                self.logger.log_validation_error("config_file", str(file_path), "создание конфигурации по умолчанию")
                self._create_default_deployment_config(file_path)
                if not file_path.exists():
                    return None

            # Загружаем конфигурацию
            with open(file_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            if config is None:
                config = {'machines': []}

            # Валидация конфигурации
            if self.validator.validate_deployment_config(config):
                # Сохраняем в кеш на 10 минут
                self.cache.set(cache_key, config, ttl=600)

                self.logger.log_cache_operation("load", "deployment_config", True)
                return config
            else:
                self.logger.log_validation_error("deployment_config", "validation_failed", "корректная структура")
                for error in self.validator.get_errors():
                    self.logger.log_validation_error("config_validation", error, "исправление структуры")
                return None

        except yaml.YAMLError as e:
            self.logger.log_validation_error("yaml_parse", str(e), "корректный YAML формат")
            return None
        except Exception as e:
            self.logger.log_validation_error("config_load", str(e), "доступ к файлу конфигурации")
            return None

    def save_deployment_config(self, config: Dict[str, Any],
                              config_file: Optional[str] = None) -> bool:
        """
        Сохранение конфигурации развертывания

        Args:
            config: Конфигурация для сохранения
            config_file: Путь к файлу конфигурации

        Returns:
            True если конфигурация успешно сохранена
        """
        file_path = Path(config_file) if config_file else self.config_dir / self.config_types['deployment']

        try:
            # Валидация перед сохранением
            if not self.validator.validate_deployment_config(config):
                self.logger.log_validation_error("save_config", "validation_failed", "корректная конфигурация")
                for error in self.validator.get_errors():
                    self.logger.log_validation_error("config_validation", error, "исправление перед сохранением")
                return False

            # Создаем резервную копию если файл существует
            if file_path.exists():
                backup_path = file_path.with_suffix('.bak')
                import shutil
                shutil.copy2(file_path, backup_path)
                self.logger.log_cache_operation("backup", str(file_path), True)

            # Сохраняем конфигурацию
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)

            # Обновляем кеш
            cache_key = f"deployment_config:{file_path}"
            self.cache.set(cache_key, config, ttl=600)

            self.logger.log_cache_operation("save", "deployment_config", True)
            return True

        except Exception as e:
            self.logger.log_validation_error("config_save", str(e), "успешное сохранение")
            return False

    def load_users_config(self, config_file: Optional[str] = None) -> Optional[List[str]]:
        """
        Загрузка конфигурации пользователей

        Args:
            config_file: Путь к файлу конфигурации пользователей

        Returns:
            Список пользователей или None при ошибке
        """
        file_path = Path(config_file) if config_file else self.config_dir / self.config_types['users']

        # Проверяем кеш
        cache_key = f"users_config:{file_path}"
        cached_users = self.cache.get(cache_key)
        if cached_users:
            self.logger.log_cache_operation("hit", cache_key, True)
            return cached_users

        try:
            if not file_path.exists():
                self.logger.log_validation_error("users_file", str(file_path), "создание конфигурации по умолчанию")
                self._create_default_users_config(file_path)
                if not file_path.exists():
                    return None

            # Загружаем конфигурацию пользователей
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if data is None:
                users = []
            elif isinstance(data, dict) and 'users' in data:
                users = data['users']
            elif isinstance(data, list):
                users = data
            else:
                self.logger.log_validation_error("users_format", str(type(data)), "список пользователей")
                return None

            # Валидация пользователей
            if self.validator.validate_users_list(users):
                # Сохраняем в кеш на 5 минут
                self.cache.set(cache_key, users, ttl=300)

                self.logger.log_cache_operation("load", "users_config", True)
                return users
            else:
                self.logger.log_validation_error("users_validation", "failed", "корректный список пользователей")
                for error in self.validator.get_errors():
                    self.logger.log_validation_error("users_validation", error, "исправление списка")
                return None

        except yaml.YAMLError as e:
            self.logger.log_validation_error("yaml_parse", str(e), "корректный YAML формат")
            return None
        except Exception as e:
            self.logger.log_validation_error("users_load", str(e), "доступ к файлу пользователей")
            return None

    def save_users_config(self, users: List[str],
                         config_file: Optional[str] = None) -> bool:
        """
        Сохранение конфигурации пользователей

        Args:
            users: Список пользователей для сохранения
            config_file: Путь к файлу конфигурации пользователей

        Returns:
            True если конфигурация успешно сохранена
        """
        file_path = Path(config_file) if config_file else self.config_dir / self.config_types['users']

        try:
            # Валидация перед сохранением
            if not self.validator.validate_users_list(users):
                self.logger.log_validation_error("save_users", "validation_failed", "корректный список пользователей")
                for error in self.validator.get_errors():
                    self.logger.log_validation_error("users_validation", error, "исправление списка")
                return False

            # Создаем резервную копию если файл существует
            if file_path.exists():
                backup_path = file_path.with_suffix('.bak')
                import shutil
                shutil.copy2(file_path, backup_path)
                self.logger.log_cache_operation("backup", str(file_path), True)

            # Сохраняем конфигурацию пользователей
            config_data = {'users': users}
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True, indent=2)

            # Обновляем кеш
            cache_key = f"users_config:{file_path}"
            self.cache.set(cache_key, users, ttl=300)

            self.logger.log_cache_operation("save", "users_config", True)
            return True

        except Exception as e:
            self.logger.log_validation_error("users_save", str(e), "успешное сохранение")
            return False

    def _create_default_deployment_config(self, file_path: Path) -> None:
        """Создание конфигурации развертывания по умолчанию"""
        default_config = {
            'machines': [
                {
                    'name': 'student-pc',
                    'device_type': 'linux',
                    'template_node': 'pve1',
                    'template_vmid': 100,
                    'networks': [
                        {'bridge': 'vmbr0'},
                        {'bridge': 'hq.100'}
                    ],
                    'full_clone': False
                }
            ]
        }

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True, indent=2)
            self.logger.log_cache_operation("create", "default_deployment_config", True)
        except Exception as e:
            self.logger.log_validation_error("create_default_config", str(e), "создание файла по умолчанию")

    def _create_default_users_config(self, file_path: Path) -> None:
        """Создание конфигурации пользователей по умолчанию"""
        default_users = [
            'student1@pve',
            'student2@pve',
            'student3@pve'
        ]

        try:
            config_data = {'users': default_users}
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True, indent=2)
            self.logger.log_cache_operation("create", "default_users_config", True)
        except Exception as e:
            self.logger.log_validation_error("create_default_users", str(e), "создание файла пользователей")

    def get_config_info(self) -> Dict[str, Any]:
        """Получение информации о конфигурационных файлах"""
        info = {}

        for config_type, filename in self.config_types.items():
            file_path = self.config_dir / filename

            file_info = {
                'exists': file_path.exists(),
                'path': str(file_path),
                'size': file_path.stat().st_size if file_path.exists() else 0,
                'modified': file_path.stat().st_mtime if file_path.exists() else 0
            }

            info[config_type] = file_info

        return info

    def validate_config_file(self, config_file: str) -> Dict[str, Any]:
        """
        Валидация конфигурационного файла

        Args:
            config_file: Путь к файлу конфигурации

        Returns:
            Результат валидации с деталями
        """
        file_path = Path(config_file)

        if not file_path.exists():
            return {
                'valid': False,
                'error': 'Файл не существует',
                'path': str(file_path)
            }

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            if config is None:
                return {
                    'valid': False,
                    'error': 'Файл пуст или содержит только null',
                    'path': str(file_path)
                }

            # Определяем тип конфигурации по содержимому
            if 'machines' in config:
                config_type = 'deployment'
                is_valid = self.validator.validate_deployment_config(config)
            elif 'users' in config or isinstance(config, list):
                config_type = 'users'
                users = config.get('users', config) if isinstance(config, dict) else config
                is_valid = self.validator.validate_users_list(users)
            else:
                config_type = 'unknown'
                is_valid = False

            return {
                'valid': is_valid,
                'type': config_type,
                'path': str(file_path),
                'errors': self.validator.get_errors(),
                'warnings': self.validator.get_warnings()
            }

        except yaml.YAMLError as e:
            return {
                'valid': False,
                'error': f'Ошибка парсинга YAML: {str(e)}',
                'path': str(file_path)
            }
        except Exception as e:
            return {
                'valid': False,
                'error': f'Ошибка чтения файла: {str(e)}',
                'path': str(file_path)
            }

    def clear_config_cache(self, config_type: Optional[str] = None) -> int:
        """
        Очистка кеша конфигурации

        Args:
            config_type: Тип конфигурации для очистки (если None, то все)

        Returns:
            Количество очищенных элементов кеша
        """
        cleared_count = 0

        if config_type == 'deployment' or config_type is None:
            # Очищаем кеш конфигурации развертывания
            cache_keys = [key for key in self.cache.cache.keys() if key.startswith('deployment_config:')]
            for key in cache_keys:
                self.cache.delete(key)
                cleared_count += 1

        if config_type == 'users' or config_type is None:
            # Очищаем кеш пользователей
            cache_keys = [key for key in self.cache.cache.keys() if key.startswith('users_config:')]
            for key in cache_keys:
                self.cache.delete(key)
                cleared_count += 1

        if cleared_count > 0:
            self.logger.log_cache_operation("clear", f"{cleared_count}_config_entries", True)

        return cleared_count

    def reload_config(self, config_type: str) -> bool:
        """
        Перезагрузка конфигурации из файла

        Args:
            config_type: Тип конфигурации ('deployment' или 'users')

        Returns:
            True если конфигурация успешно перезагружена
        """
        if config_type == 'deployment':
            config = self.load_deployment_config()
            return config is not None
        elif config_type == 'users':
            users = self.load_users_config()
            return users is not None
        else:
            self.logger.log_validation_error("reload_config", config_type, "deployment или users")
            return False


# Глобальный экземпляр менеджера конфигурации
_global_config_manager = None


def get_config_manager(config_dir: str = "data") -> ConfigManager:
    """Получить глобальный экземпляр менеджера конфигурации"""
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = ConfigManager(config_dir)
    return _global_config_manager


# Пример использования
if __name__ == "__main__":
    print("📋 ConfigManager - менеджер конфигурации развертывания")
    print("📋 Доступные методы:")

    # Получаем все публичные методы
    methods = [method for method in dir(ConfigManager) if not method.startswith('_') and callable(getattr(ConfigManager, method))]
    for method in methods:
        print(f"  - {method}")

    print(f"\n📊 Всего методов: {len(methods)}")
    print("✅ Менеджер конфигурации готов к использованию")
