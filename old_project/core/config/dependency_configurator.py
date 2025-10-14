"""
Конфигуратор зависимостей модулей

Предоставляет автоматическую настройку зависимостей между модулями
с использованием dependency injection паттерна.
"""

import logging
from typing import Dict, Any, Type, Optional, List
from .config_manager import ConfigManager


class DependencyContainer:
    """Контейнер зависимостей для dependency injection"""

    def __init__(self):
        self._services = {}
        self._singletons = {}

    def register(self, interface: str, implementation: Type, singleton: bool = False):
        """Зарегистрировать реализацию интерфейса"""
        if singleton:
            self._singletons[interface] = implementation
        else:
            self._services[interface] = implementation

    def resolve(self, interface: str, *args, **kwargs) -> Any:
        """Получить реализацию интерфейса"""
        if interface in self._singletons:
            if interface not in self._services:
                # Создать singleton экземпляр
                implementation = self._singletons[interface]
                self._services[interface] = implementation(*args, **kwargs)
            return self._services[interface]

        if interface in self._services:
            implementation = self._services[interface]
            return implementation(*args, **kwargs)

        raise ValueError(f"Interface {interface} not registered")

logger = logging.getLogger(__name__)


class DependencyConfigurator:
    """Конфигуратор зависимостей модулей"""

    def __init__(self, config_manager: ConfigManager = None):
        """
        Инициализация конфигуратора зависимостей

        Args:
            config_manager: Менеджер конфигурации
        """
        self.config_manager = config_manager or ConfigManager()
        self.container = DependencyContainer()

    def configure_dependencies(self) -> DependencyContainer:
        """
        Настроить все зависимости модулей

        Returns:
            Настроенный контейнер зависимостей
        """
        # Регистрация базовых сервисов
        self._register_core_services()

        # Регистрация утилит
        self._register_utility_services()

        # Регистрация менеджеров
        self._register_manager_services()

        # Регистрация фабрик
        self._register_factory_services()

        logger.info("✅ Зависимости модулей настроены")
        return self.container

    def _register_core_services(self):
        """Регистрация базовых сервисов"""
        # Конфигурация
        self.container.register("config_manager", lambda: self.config_manager, singleton=True)

        # Proxmox клиент (будет создан при необходимости)
        from ..proxmox.proxmox_client import ProxmoxClient
        self.container.register("proxmox_client", ProxmoxClient, singleton=False)

    def _register_utility_services(self):
        """Регистрация утилитарных сервисов"""
        # Утилиты развертывания
        from ..modules.common.deployment_utils import DeploymentUtils
        self.container.register("deployment_utils", DeploymentUtils, singleton=True)

        # Валидатор конфигурации
        from ..modules.common.config_validator import ConfigValidator
        self.container.register("config_validator", ConfigValidator, singleton=True)

        # Логгер
        import logging
        self.container.register("logger", lambda: logging.getLogger("deploy-stand"), singleton=True)

    def _register_manager_services(self):
        """Регистрация менеджеров"""
        # Менеджер пользователей
        from ..modules.users.user_manager import UserManager
        self.container.register("user_manager", UserManager, singleton=False)

        # Менеджер шаблонов
        from ..modules.templates.template_manager import TemplateManager
        self.container.register("template_manager", TemplateManager, singleton=False)

        # Менеджер сети
        from ..modules.network.network_configurator import NetworkConfigurator
        self.container.register("network_configurator", NetworkConfigurator, singleton=False)

    def _register_factory_services(self):
        """Регистрация фабрик"""
        # Фабрика виртуальных машин
        from ..modules.deployment.vm_factory import VMFactory
        self.container.register("vm_factory", VMFactory, singleton=False)

    def create_deployment_module_dependencies(self, module_name: str) -> Dict[str, Any]:
        """
        Создать зависимости для модуля развертывания

        Args:
            module_name: Имя модуля развертывания

        Returns:
            Словарь зависимостей
        """
        dependencies = {}

        # Базовые зависимости для всех модулей развертывания
        dependencies.update({
            "config_validator": self.container.resolve("config_validator"),
            "deployment_utils": self.container.resolve("deployment_utils"),
            "logger": self.container.resolve("logger")
        })

        # Специфичные зависимости в зависимости от типа модуля
        if module_name in ["local"]:
            # LocalDeployer нуждается в UserManager и VMFactory
            dependencies.update({
                "user_manager": self.container.resolve("user_manager"),
                "vm_factory": self.container.resolve("vm_factory")
            })

        elif module_name in ["remote"]:
            # RemoteDeployer нуждается в UserManager, TemplateManager и VMFactory
            dependencies.update({
                "user_manager": self.container.resolve("user_manager"),
                "template_manager": self.container.resolve("template_manager"),
                "vm_factory": self.container.resolve("vm_factory")
            })

        elif module_name in ["balanced", "smart"]:
            # Balanced/Smart Deployer нуждаются в UserManager, TemplateManager, VMFactory и балансировщике
            dependencies.update({
                "user_manager": self.container.resolve("user_manager"),
                "template_manager": self.container.resolve("template_manager"),
                "vm_factory": self.container.resolve("vm_factory")
            })

        return dependencies

    def create_balancing_module_dependencies(self, module_name: str) -> Dict[str, Any]:
        """
        Создать зависимости для модуля балансировки

        Args:
            module_name: Имя модуля балансировки

        Returns:
            Словарь зависимостей
        """
        dependencies = {
            "deployment_utils": self.container.resolve("deployment_utils"),
            "logger": self.container.resolve("logger")
        }

        if module_name == "smart":
            # SmartBalancer нуждается в метриках и кеше
            from ...utils.monitoring.metrics import MetricsCollector
            from ...utils.caching.cache_manager import CacheManager

            dependencies.update({
                "metrics": MetricsCollector(),
                "cache": CacheManager()
            })

        return dependencies

    def validate_dependencies(self) -> Dict[str, Any]:
        """
        Проверить корректность настройки зависимостей

        Returns:
            Результат валидации зависимостей
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }

        try:
            # Проверить базовые зависимости (singleton)
            required_singleton_interfaces = [
                "config_manager",
                "deployment_utils",
                "config_validator",
                "logger"
            ]

            for interface in required_singleton_interfaces:
                try:
                    # Для singleton зависимостей проверяем что они зарегистрированы
                    if interface in self.container._singletons:
                        # Попытаться создать экземпляр
                        self.container.resolve(interface)
                    else:
                        validation_result["errors"].append(f"Singleton зависимость не зарегистрирована: {interface}")
                        validation_result["valid"] = False
                except Exception as e:
                    validation_result["errors"].append(f"Ошибка создания singleton зависимости {interface}: {e}")
                    validation_result["valid"] = False

            # Проверить менеджеры
            manager_interfaces = [
                "user_manager",
                "template_manager",
                "network_configurator",
                "vm_factory"
            ]

            for interface in manager_interfaces:
                try:
                    # Попытаться создать менеджер (не singleton)
                    if interface == "user_manager":
                        self.container.resolve(interface, None)  # ProxmoxClient будет передан позже
                    elif interface == "template_manager":
                        self.container.resolve(interface, None)  # ProxmoxClient будет передан позже
                    elif interface == "network_configurator":
                        self.container.resolve(interface, None)  # ProxmoxClient будет передан позже
                    elif interface == "vm_factory":
                        self.container.resolve(interface, None)  # ProxmoxClient будет передан позже
                except Exception as e:
                    validation_result["warnings"].append(f"Не удалось создать менеджер {interface}: {e}")

        except Exception as e:
            validation_result["errors"].append(f"Ошибка валидации зависимостей: {e}")
            validation_result["valid"] = False

        return validation_result

    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """
        Получить граф зависимостей модулей

        Returns:
            Граф зависимостей в виде словаря
        """
        graph = {
            "deployment_modules": {
                "local": ["user_manager", "vm_factory", "config_validator"],
                "remote": ["user_manager", "template_manager", "vm_factory", "config_validator"],
                "balanced": ["user_manager", "template_manager", "vm_factory", "balancing_module", "config_validator"],
                "smart": ["user_manager", "template_manager", "vm_factory", "balancing_module", "config_validator"]
            },
            "balancing_modules": {
                "simple": ["deployment_utils"],
                "smart": ["deployment_utils", "metrics", "cache"]
            },
            "utility_modules": {
                "config_validator": ["deployment_utils"],
                "user_manager": ["deployment_utils"],
                "template_manager": ["deployment_utils"],
                "vm_factory": ["user_manager", "network_configurator"],
                "network_configurator": ["deployment_utils"]
            }
        }

        return graph
