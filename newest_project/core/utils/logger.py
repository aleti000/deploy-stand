#!/usr/bin/env python3
"""
Logger - модульная система логирования для newest_project

Предоставляет унифицированный интерфейс для логирования операций
развертывания виртуальных машин с поддержкой различных уровней детализации.
"""

import logging
import logging.handlers
import sys
from typing import Optional
from pathlib import Path


class Logger:
    """
    Централизованная система логирования для приложения развертывания VM

    Поддерживает:
    - Различные уровни логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - Логирование в файл и консоль одновременно
    - Ротацию лог-файлов
    - Структурированное форматирование сообщений
    """

    def __init__(self, name: str = "deploy-stand", log_level: str = "INFO"):
        """
        Инициализация системы логирования

        Args:
            name: Имя логгера (обычно название приложения)
            log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.name = name
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger = None
        self.log_file = None

        # Создаем директорию для логов если её нет
        self._ensure_log_directory()

    def _ensure_log_directory(self) -> None:
        """Создание директории для лог-файлов"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

    def setup_logging(self, log_to_file: bool = True, log_to_console: bool = True) -> logging.Logger:
        """
        Настройка системы логирования

        Args:
            log_to_file: Включить логирование в файл
            log_to_console: Включить логирование в консоль

        Returns:
            Настроенный экземпляр логгера
        """
        # Создание логгера
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(self.log_level)

        # Убираем существующие обработчики для избежания дублирования
        self.logger.handlers.clear()

        # Форматирование сообщений
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Обработчик для консоли
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.log_level)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

        # Обработчик для файла с ротацией
        if log_to_file:
            self.log_file = Path("logs") / f"{self.name}.log"
            file_handler = logging.handlers.RotatingFileHandler(
                self.log_file,
                maxBytes=10*1024*1024,  # 10 MB
                backupCount=5
            )
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        return self.logger

    def get_logger(self) -> logging.Logger:
        """
        Получить экземпляр логгера

        Returns:
            Экземпляр логгера или None если не настроен
        """
        return self.logger

    def log_deployment_start(self, config_name: str, user_count: int) -> None:
        """Логирование начала развертывания"""
        if self.logger:
            self.logger.info("🚀 Начинаем развертывание стендов")
            self.logger.info(f"📋 Конфигурация: {config_name}")
            self.logger.info(f"👥 Пользователей: {user_count}")

    def log_deployment_success(self, created_vms: int, duration: float) -> None:
        """Логирование успешного завершения развертывания"""
        if self.logger:
            self.logger.info("✅ Развертывание завершено успешно")
            self.logger.info(f"🖥️  Создано VM: {created_vms}")
            self.logger.info(f"⏱️  Время выполнения: {duration:.2f} сек")

    def log_deployment_error(self, error: str, details: Optional[str] = None) -> None:
        """Логирование ошибки развертывания"""
        if self.logger:
            self.logger.error(f"❌ Ошибка развертывания: {error}")
            if details:
                self.logger.error(f"📝 Детали: {details}")

    def log_connection_attempt(self, host: str, user: str) -> None:
        """Логирование попытки подключения"""
        if self.logger:
            self.logger.info(f"🔗 Подключение к {host} пользователем {user}")

    def log_connection_success(self, host: str, version: str) -> None:
        """Логирование успешного подключения"""
        if self.logger:
            self.logger.info(f"✅ Подключение установлено: {host}")
            self.logger.info(f"📦 Версия Proxmox: {version}")

    def log_connection_error(self, host: str, error: str) -> None:
        """Логирование ошибки подключения"""
        if self.logger:
            self.logger.error(f"❌ Ошибка подключения к {host}: {error}")

    def log_vm_creation(self, vm_name: str, node: str, vmid: int) -> None:
        """Логирование создания VM"""
        if self.logger:
            self.logger.info(f"🖥️  Создание VM: {vm_name} (ID: {vmid}) на ноде {node}")

    def log_network_setup(self, vm_name: str, bridge: str, vlan: Optional[int] = None) -> None:
        """Логирование настройки сети"""
        if self.logger:
            if vlan:
                self.logger.info(f"🌐 Настройка сети: {vm_name} -> {bridge} (VLAN {vlan})")
            else:
                self.logger.info(f"🌐 Настройка сети: {vm_name} -> {bridge}")

    def log_bridge_creation(self, bridge: str, alias: str, vlan_aware: bool = False) -> None:
        """Логирование создания bridge"""
        if self.logger:
            if vlan_aware:
                self.logger.info(f"🌉 Создан VLAN-aware bridge: {bridge} для алиаса {alias}")
            else:
                self.logger.info(f"🌉 Создан bridge: {bridge} для алиаса {alias}")

    def log_cache_operation(self, operation: str, key: str, success: bool = True) -> None:
        """Логирование операций с кешем"""
        if self.logger:
            if success:
                self.logger.debug(f"💾 Кеш {operation}: {key}")
            else:
                self.logger.warning(f"⚠️  Ошибка кеша {operation}: {key}")

    def log_validation_error(self, field: str, value: str, expected: str) -> None:
        """Логирование ошибок валидации"""
        if self.logger:
            self.logger.error(f"🔍 Ошибка валидации: {field} = '{value}', ожидалось: {expected}")

    def log_performance_metric(self, metric: str, value: float, unit: str = "") -> None:
        """Логирование метрик производительности"""
        if self.logger:
            self.logger.info(f"📊 Метрика {metric}: {value}{unit}")


# Глобальный экземпляр логгера для удобства использования
_global_logger = None


def get_logger(name: str = "deploy-stand") -> Logger:
    """
    Получить глобальный экземпляр логгера

    Args:
        name: Имя логгера

    Returns:
        Экземпляр Logger
    """
    global _global_logger
    if _global_logger is None:
        _global_logger = Logger(name)
    return _global_logger


def setup_global_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Настройка глобального логирования

    Args:
        log_level: Уровень логирования

    Returns:
        Настроенный логгер
    """
    global _global_logger
    if _global_logger is None:
        _global_logger = Logger(log_level=log_level)
    return _global_logger.setup_logging()


# Пример использования
if __name__ == "__main__":
    # Тестирование логгера
    logger = Logger("test-app", "DEBUG")
    logger.setup_logging()

    # Тестовые сообщения
    logger.log_deployment_start("test-config", 5)
    logger.log_connection_attempt("192.168.1.100:8006", "root@pam")
    logger.log_vm_creation("test-vm", "pve1", 100)
    logger.log_network_setup("test-vm", "vmbr0", 100)
    logger.log_deployment_success(3, 45.2)

    print("✅ Тестирование логгера завершено. Проверьте файл logs/test-app.log")
