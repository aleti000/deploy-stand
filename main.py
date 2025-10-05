#!/usr/bin/env python3
"""
Deploy-Stand - Модульная система для автоматизированного развертывания виртуальных машин в кластере Proxmox VE

Точка входа в приложение
"""

import sys
import os
import logging
from typing import Optional

# Добавляем корневую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.module_factory import ModuleFactory
from core.config.config_manager import ConfigManager
from ui.cli.menu_system import MainMenu
from utils.logging.logger import setup_logging
from utils.caching.cache_manager import CacheManager
from utils.monitoring.metrics import MetricsCollector


def main():
    """Главная функция приложения"""
    try:
        # Настройка логирования
        logger = setup_logging()
        logger.info("🚀 Запуск Deploy-Stand...")

        # Инициализация компонентов системы
        logger.info("📦 Инициализация компонентов системы...")

        # Создание фабрики модулей
        module_factory = ModuleFactory()

        # Создание менеджера конфигурации
        config_manager = ConfigManager()

        # Создание кеш менеджера
        cache_manager = CacheManager()

        # Создание сборщика метрик
        metrics_collector = MetricsCollector()

        # Регистрация модулей в фабрике
        logger.info("🔧 Регистрация модулей...")

        # Импорт и регистрация модулей развертывания
        try:
            from core.modules.deployment.basic_deployer import BasicDeployer
            from core.modules.deployment.advanced_deployer import AdvancedDeployer
            from core.modules.deployment.local_deployer import LocalDeployer
            from core.modules.deployment.remote_deployer import RemoteDeployer
            from core.modules.deployment.balanced_deployer import BalancedDeployer
            from core.modules.deployment.smart_deployer import SmartDeployer
            module_factory.register_deployment_module("basic", BasicDeployer)
            module_factory.register_deployment_module("advanced", AdvancedDeployer)
            module_factory.register_deployment_module("local", LocalDeployer)
            module_factory.register_deployment_module("remote", RemoteDeployer)
            module_factory.register_deployment_module("balanced", BalancedDeployer)
            module_factory.register_deployment_module("smart", SmartDeployer)
            logger.info("✅ Модули развертывания зарегистрированы")
        except ImportError as e:
            logger.warning(f"⚠️ Не удалось зарегистрировать модули развертывания: {e}")

        # Импорт и регистрация модулей балансировки
        try:
            from core.modules.balancing.simple_balancer import SimpleBalancer
            from core.modules.balancing.smart_balancer import SmartBalancer
            module_factory.register_balancing_module("simple", SimpleBalancer)
            module_factory.register_balancing_module("smart", SmartBalancer)
            logger.info("✅ Модули балансировки зарегистрированы")
        except ImportError as e:
            logger.warning(f"⚠️ Не удалось зарегистрировать модули балансировки: {e}")

        # Импорт и регистрация модулей шаблонов
        try:
            from core.modules.templates.local_templates import LocalTemplateManager
            from core.modules.templates.migration_templates import MigrationTemplateManager
            module_factory.register_template_module("local", LocalTemplateManager)
            module_factory.register_template_module("migration", MigrationTemplateManager)
            logger.info("✅ Модули шаблонов зарегистрированы")
        except ImportError as e:
            logger.warning(f"⚠️ Не удалось зарегистрировать модули шаблонов: {e}")

        # Импорт и регистрация модулей сети
        try:
            from core.modules.network.bridge_manager import BridgeManager
            module_factory.register_network_module("bridge", BridgeManager)
            logger.info("✅ Модули сети зарегистрированы")
        except ImportError as e:
            logger.warning(f"⚠️ Не удалось зарегистрировать модули сети: {e}")

        # Создание главного меню
        logger.info("🎛️ Создание главного меню...")
        main_menu = MainMenu(
            module_factory=module_factory,
            config_manager=config_manager,
            logger_instance=logger,
            cache=cache_manager,
            metrics=metrics_collector
        )

        # Запуск главного меню
        logger.info("🚀 Запуск главного меню...")
        print("🚀 Добро пожаловать в Deploy-Stand!")
        print("=" * 50)

        main_menu.show()

        logger.info("👋 Завершение работы приложения")
        print("\n👋 До свидания!")

    except KeyboardInterrupt:
        print("\n\n👋 Приложение прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.error(f"Критическая ошибка в main(): {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
