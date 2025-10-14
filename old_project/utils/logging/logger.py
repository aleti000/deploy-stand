"""
Логгер системы Deploy-Stand

Предоставляет централизованную систему логирования с различными уровнями важности
и форматированным выводом для улучшения читаемости.
"""

import logging
import sys
from typing import Optional


class Logger:
    """Централизованный логгер системы Deploy-Stand"""

    def __init__(self, name: str = "deploy-stand", level: int = logging.INFO):
        """
        Инициализация логгера

        Args:
            name: Имя логгера
            level: Уровень логирования
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # Создать форматтер для красивого вывода
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Создать консольный обработчик если обработчики не установлены
        if not self.logger.handlers:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

    def info(self, message: str):
        """Логировать информационные сообщения"""
        self.logger.info(message)

    def success(self, message: str):
        """Логировать успешные операции"""
        self.logger.info(f"✅ {message}")

    def error(self, message: str):
        """Логировать ошибки"""
        self.logger.error(f"❌ {message}")

    def warning(self, message: str):
        """Логировать предупреждения"""
        self.logger.warning(f"⚠️  {message}")

    def debug(self, message: str):
        """Логировать отладочную информацию"""
        self.logger.debug(message)

    def critical(self, message: str):
        """Логировать критические ошибки"""
        self.logger.critical(f"🚨 {message}")

    def deployment_start(self, config_name: str, user_count: int):
        """Логировать начало развертывания"""
        self.success(f"Начинается развертывание '{config_name}' для {user_count} пользователей")

    def deployment_complete(self, results: dict):
        """Логировать завершение развертывания"""
        success_count = len([r for r in results.values() if r])
        self.success(f"Развертывание завершено. Успешно создано пользователей: {success_count}")

    def deployment_failed(self, error: str):
        """Логировать неудачное развертывание"""
        self.error(f"Развертывание неудачно: {error}")

    def user_created(self, username: str, pool: str):
        """Логировать создание пользователя"""
        self.success(f"Создан пользователь {username} с пулом {pool}")

    def vm_created(self, vm_name: str, vmid: int, node: str):
        """Логировать создание виртуальной машины"""
        self.success(f"Создана VM '{vm_name}' (ID: {vmid}) на ноде {node}")

    def template_migrated(self, template_vmid: int, source_node: str, target_node: str):
        """Логировать миграцию шаблона"""
        self.info(f"Шаблон VM {template_vmid} мигрирован с {source_node} на {target_node}")

    def connection_established(self, host: str, nodes: list):
        """Логировать установку соединения"""
        self.success(f"Подключение к {host} установлено. Доступные ноды: {', '.join(nodes)}")

    def connection_failed(self, host: str, error: str):
        """Логировать неудачное подключение"""
        self.error(f"Неудачное подключение к {host}: {error}")

    def config_loaded(self, config_name: str):
        """Логировать загрузку конфигурации"""
        self.info(f"Загружена конфигурация: {config_name}")

    def config_saved(self, config_name: str):
        """Логировать сохранение конфигурации"""
        self.success(f"Конфигурация сохранена: {config_name}")

    def bridge_created(self, bridge_name: str, node: str):
        """Логировать создание bridge"""
        self.info(f"Создан bridge {bridge_name} на ноде {node}")

    def bridge_deleted(self, bridge_name: str, node: str):
        """Логировать удаление bridge"""
        self.info(f"Удален bridge {bridge_name} с ноды {node}")

    def cleanup_started(self, resource_type: str, count: int):
        """Логировать начало очистки ресурсов"""
        self.info(f"Начинается очистка {count} {resource_type}")

    def cleanup_completed(self, resource_type: str, cleaned_count: int):
        """Логировать завершение очистки ресурсов"""
        self.success(f"Очистка завершена. Удалено {cleaned_count} {resource_type}")

    def performance_metric(self, operation: str, duration: float, details: str = ""):
        """Логировать метрики производительности"""
        message = f"Операция '{operation}' выполнена за {duration:.2f}с"
        if details:
            message += f" ({details})"
        self.info(message)


def setup_logging(log_level: int = logging.INFO, log_file: Optional[str] = None) -> logging.Logger:
    """
    Настройка логирования для системы Deploy-Stand

    Args:
        log_level: Уровень логирования
        log_file: Путь к файлу логов (опционально)

    Returns:
        logging.Logger: Настроенный логгер
    """
    logger = logging.getLogger("deploy-stand")
    logger.setLevel(log_level)

    # Очистить существующие обработчики
    logger.handlers.clear()

    # Форматтер для красивого вывода
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)

    # Файловый обработчик, если указан лог-файл
    if log_file:
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(log_level)
        logger.addHandler(file_handler)

    return logger
