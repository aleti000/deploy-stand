#!/usr/bin/env python3
"""
Тестирование модуля Logger

Ручное тестирование системы логирования для newest_project
"""

import sys
import os
import time
from pathlib import Path

# Добавляем корневую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.utils.logger import Logger


def test_logger_basic():
    """Базовое тестирование логгера"""
    print("🧪 Тестирование базовой функциональности логгера...")

    # Создание логгера
    logger = Logger("test-basic", "DEBUG")
    logger.setup_logging()

    # Тестовые сообщения
    logger.log_deployment_start("test-config", 3)
    logger.log_connection_attempt("192.168.1.100:8006", "root@pam")
    logger.log_vm_creation("test-vm", "pve1", 100)
    logger.log_network_setup("test-vm", "vmbr0", 100)
    logger.log_deployment_success(2, 15.5)

    print("✅ Базовое тестирование завершено")


def test_logger_file_output():
    """Тестирование записи в файл"""
    print("📁 Тестирование записи в файл...")

    # Создание логгера с записью в файл
    logger = Logger("test-file", "INFO")
    logger.setup_logging(log_to_file=True, log_to_console=False)

    # Тестовые сообщения
    logger.log_connection_success("192.168.1.100:8006", "7.4-3")
    logger.log_bridge_creation("vmbr1000", "hq", vlan_aware=True)
    logger.log_performance_metric("cpu_usage", 45.2, "%")

    # Проверка создания файла
    log_file = Path("logs/test-file.log")
    if log_file.exists():
        print(f"✅ Лог-файл создан: {log_file}")
        print(f"📏 Размер файла: {log_file.stat().st_size} байт")

        # Показываем последние строки файла
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print("📄 Последние записи в лог-файле:")
            for line in lines[-3:]:
                print(f"  {line.strip()}")
    else:
        print("❌ Лог-файл не создан")


def test_logger_error_handling():
    """Тестирование обработки ошибок"""
    print("🚨 Тестирование обработки ошибок...")

    logger = Logger("test-errors", "ERROR")
    logger.setup_logging()

    # Тестовые сообщения об ошибках
    logger.log_deployment_error("Не удалось создать VM", "Недостаточно ресурсов на ноде")
    logger.log_connection_error("192.168.1.100:8006", "Connection timeout")
    logger.log_validation_error("vm_name", "", "не пустая строка")

    print("✅ Тестирование ошибок завершено")


def test_logger_different_levels():
    """Тестирование различных уровней логирования"""
    print("📊 Тестирование уровней логирования...")

    levels = ["DEBUG", "INFO", "WARNING", "ERROR"]

    for level in levels:
        print(f"\n🔧 Тестирование уровня {level}:")

        logger = Logger(f"test-{level.lower()}", level)
        logger.setup_logging(log_to_console=True, log_to_file=False)

        # Тестовые сообщения для каждого уровня
        if level == "DEBUG":
            logger.logger.debug("🐛 Отладочное сообщение")
        if level in ["DEBUG", "INFO"]:
            logger.logger.info("ℹ️ Информационное сообщение")
        if level in ["DEBUG", "INFO", "WARNING"]:
            logger.logger.warning("⚠️ Предупреждение")
        logger.logger.error("❌ Ошибка")
        logger.logger.critical("🚨 Критическая ошибка")

    print("✅ Тестирование уровней завершено")


def main():
    """Главная функция тестирования"""
    print("🚀 Начинаем тестирование модуля Logger")
    print("=" * 50)

    try:
        # Создаем директорию для логов
        Path("logs").mkdir(exist_ok=True)

        # Запуск тестов
        test_logger_basic()
        print()

        test_logger_file_output()
        print()

        test_logger_error_handling()
        print()

        test_logger_different_levels()
        print()

        print("=" * 50)
        print("🎉 Все тесты логгера завершены!")
        print("📁 Проверьте созданные лог-файлы в папке logs/")

        # Пауза для просмотра результатов
        input("\n⏸️  Нажмите Enter для завершения...")

    except KeyboardInterrupt:
        print("\n\n👋 Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка при тестировании: {e}")
        raise


if __name__ == "__main__":
    main()
