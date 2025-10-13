#!/usr/bin/env python3
"""
Модуль логирования для приложения развертывания виртуальных машин
Упрощенная версия на основе анализа существующего проекта
"""

import logging
import sys
from typing import Optional


class Logger:
    """
    Класс для управления логированием приложения
    """

    def __init__(self, name: str = "deploy-stand"):
        """
        Инициализация логгера

        Args:
            name: Имя логгера
        """
        self.logger = logging.getLogger(name)

    def setup_logging(self, level: int = logging.INFO, log_file: Optional[str] = None) -> None:
        """
        Настройка логирования

        Args:
            level: Уровень логирования
            log_file: Путь к файлу лога (опционально)
        """
        # Настройка формата
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Настройка обработчика для консоли
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)

        # Добавление обработчиков
        self.logger.addHandler(console_handler)

        # Добавление файлового обработчика если указан файл
        if log_file:
            try:
                import os
                os.makedirs(os.path.dirname(log_file), exist_ok=True)

                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                file_handler.setFormatter(formatter)
                file_handler.setLevel(level)
                self.logger.addHandler(file_handler)
            except Exception as e:
                print(f"Ошибка настройки файлового логирования: {e}")

        self.logger.setLevel(level)

        self.info("Логирование настроено")

    def info(self, message: str) -> None:
        """Информационное сообщение"""
        self.logger.info(message)

    def warning(self, message: str) -> None:
        """Предупреждение"""
        self.logger.warning(message)

    def error(self, message: str) -> None:
        """Ошибка"""
        self.logger.error(message)

    def critical(self, message: str) -> None:
        """Критическая ошибка"""
        self.logger.critical(message)

    def debug(self, message: str) -> None:
        """Отладочное сообщение"""
        self.logger.debug(message)
