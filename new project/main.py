#!/usr/bin/env python3
"""
Точка входа для асинхронного приложения развертывания виртуальных машин
Упрощенная версия на основе анализа существующего проекта
"""

import sys
import asyncio
import logging
from typing import Optional, Dict, Any

from core.utils import Logger
from core.ui import MainMenu

# Глобальная переменная для текущего подключения
_current_connection = None

def get_current_connection() -> Optional[Dict[str, Any]]:
    """Получить текущее активное подключение"""
    global _current_connection
    return _current_connection

def set_current_connection(connection: Dict[str, Any]) -> None:
    """Установить текущее активное подключение"""
    global _current_connection
    _current_connection = connection


def main() -> None:
    """
    Асинхронная главная функция приложения - точка входа

    Инициализирует компоненты и запускает меню
    """
    try:
        # Настройка логирования через наш логгер
        logger = Logger("deploy-stand")
        logger.setup_logging()

        # Инициализация базовых компонентов
        # Создание экземпляра меню
        menu = MainMenu(logger_instance=logger.logger)

        # Запуск главного меню
        print("🚀 Приложение развертывания виртуальных машин запущено")
        menu.show()

    except Exception as e:
        logging.error(f"Критическая ошибка в главной функции: {e}")
        sys.exit(1)


def setup_logging() -> None:
    """
    Настройка системы логирования
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Создание логгера
    logger = logging.getLogger(__name__)
    logger.info("Логирование настроено")


if __name__ == "__main__":
    main()
