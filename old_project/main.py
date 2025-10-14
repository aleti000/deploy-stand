#!/usr/bin/env python3
"""
Deploy-Stand - Модульная система для автоматизированного развертывания виртуальных машин в кластере Proxmox VE

РЕФАКТОРИНГ: Улучшенная точка входа с dependency injection и модульной архитектурой
"""

import sys
import os
import logging
from typing import Optional

# Добавляем корневую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.module_factory import ModuleFactory
from core.config.config_manager import ConfigManager
from core.config.dependency_configurator import DependencyConfigurator
from ui.cli.menu_system import MainMenu
from utils.logging.logger import setup_logging
from utils.caching.cache_manager import CacheManager
from utils.monitoring.metrics import MetricsCollector


def main():
    """Главная функция приложения с улучшенной архитектурой"""
    app = None
    try:
        # Настройка логирования
        logger = setup_logging()
        logger.info("🚀 Запуск Deploy-Stand с улучшенной архитектурой...")

        # Создание приложения с dependency injection
        app = DeployStandApplication()
        app.initialize()

        # Запуск главного меню
        logger.info("🚀 Запуск главного меню...")
        print("🚀 Добро пожаловать в Deploy-Stand!")
        print("=" * 50)

        app.main_menu.show()

        logger.info("👋 Завершение работы приложения")
        print("\n👋 До свидания!")

    except KeyboardInterrupt:
        print("\n\n👋 Приложение прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.error(f"Критическая ошибка в main(): {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Очистка ресурсов при завершении
        if app:
            app.cleanup()


class DeployStandApplication:
    """Основное приложение с dependency injection архитектурой"""

    def __init__(self):
        """Инициализация приложения"""
        self.logger = None
        self.config_manager = None
        self.module_factory = None
        self.dependency_configurator = None
        self.cache_manager = None
        self.metrics_collector = None
        self.main_menu = None

    def initialize(self):
        """Инициализация всех компонентов приложения"""
        # Настройка логирования
        self.logger = setup_logging()
        self.logger.info("📦 Инициализация компонентов системы...")

        # Создание базовых компонентов
        self.config_manager = ConfigManager()
        self.cache_manager = CacheManager()
        self.metrics_collector = MetricsCollector()

        # Создание конфигуратора зависимостей
        self.dependency_configurator = DependencyConfigurator(self.config_manager)
        self.dependencies = self.dependency_configurator.configure_dependencies()

        # Создание фабрики модулей с dependency injection
        self.module_factory = ModuleFactory(self.config_manager)

        # Валидация зависимостей
        self._validate_dependencies()

        # Создание главного меню
        self.main_menu = MainMenu(
            module_factory=self.module_factory,
            config_manager=self.config_manager,
            logger_instance=self.logger,
            cache=self.cache_manager,
            metrics=self.metrics_collector
        )

        self.logger.info("✅ Все компоненты инициализированы")

    def _validate_dependencies(self):
        """Валидация зависимостей модулей"""
        validation_result = self.dependency_configurator.validate_dependencies()

        if not validation_result["valid"]:
            error_msg = "Ошибка валидации зависимостей:\n"
            error_msg += "\n".join(f"  ❌ {error}" for error in validation_result["errors"])
            error_msg += "\n".join(f"  ⚠️  {warning}" for warning in validation_result["warnings"])

            self.logger.error(error_msg)
            raise RuntimeError("Некорректная настройка зависимостей модулей")

        # Дополнительная проверка базовых зависимостей
        try:
            # Попытаться получить базовые зависимости из фабрики модулей
            config_manager = self.module_factory.dependencies.resolve("config_manager")
            deployment_utils = self.module_factory.dependencies.resolve("deployment_utils")
            config_validator = self.module_factory.dependencies.resolve("config_validator")
            logger = self.module_factory.dependencies.resolve("logger")

            self.logger.info("✅ Базовые зависимости проверены")

        except Exception as e:
            self.logger.error(f"Ошибка проверки базовых зависимостей: {e}")
            raise RuntimeError(f"Не удалось получить базовые зависимости: {e}")

        self.logger.info("✅ Зависимости модулей валидированы")

    def cleanup(self):
        """Очистка ресурсов приложения"""
        try:
            self.logger.info("🧹 Очистка ресурсов приложения...")

            # Очистка кеша
            if self.cache_manager:
                # Здесь можно добавить логику очистки кеша
                pass

            # Очистка неиспользуемых ресурсов
            if self.module_factory:
                # Здесь можно добавить логику очистки ресурсов модулей
                pass

            self.logger.info("✅ Очистка ресурсов завершена")

        except Exception as e:
            self.logger.error(f"Ошибка очистки ресурсов: {e}")


if __name__ == "__main__":
    main()
