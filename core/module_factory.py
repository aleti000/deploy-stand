"""
Фабрика для создания и управления модулями

РЕФАКТОРИНГ: Улучшенная версия с dependency injection и автоматической регистрацией модулей.
Предоставляет централизованный способ создания модулей различных типов
с поддержкой динамической регистрации и конфигурации.
"""

import logging
from typing import Dict, Any, Type, List, Optional
from .interfaces.deployment_interface import DeploymentInterface
from .interfaces.balancing_interface import BalancingInterface
from .interfaces.template_interface import TemplateInterface
from .interfaces.network_interface import NetworkInterface
from .config.config_manager import ConfigManager
from .config.dependency_configurator import DependencyConfigurator, DependencyContainer

logger = logging.getLogger(__name__)


class ModuleFactory:
    """Улучшенная фабрика для создания и управления модулями"""

    def __init__(self, config_manager: ConfigManager = None):
        """
        Инициализация фабрики модулей

        Args:
            config_manager: Менеджер конфигурации (опционально)
        """
        self.config_manager = config_manager or ConfigManager()
        self.modules = {}
        self.dependency_configurator = DependencyConfigurator(self.config_manager)
        self.dependencies = self.dependency_configurator.configure_dependencies()
        self._register_available_modules()

    def _register_available_modules(self):
        """Автоматическая регистрация всех доступных модулей"""
        # Автоматическая регистрация модулей развертывания
        self._auto_register_deployment_modules()

        # Автоматическая регистрация модулей балансировки
        self._auto_register_balancing_modules()

        # Автоматическая регистрация сетевых модулей
        self._auto_register_network_modules()

        # Автоматическая регистрация модулей шаблонов
        self._auto_register_template_modules()

    def _auto_register_deployment_modules(self):
        """Автоматическая регистрация модулей развертывания"""
        deployment_modules = {
            "local": "core.modules.deployment.local_deployer.LocalDeployer",
            "remote": "core.modules.deployment.remote_deployer.RemoteDeployer",
            "balanced": "core.modules.deployment.balanced_deployer.BalancedDeployer",
            "smart": "core.modules.deployment.smart_deployer.SmartDeployer"
        }

        for name, module_path in deployment_modules.items():
            try:
                module = self._import_module(module_path)
                if module:
                    self.register_deployment_module(name, module)
                    logger.info(f"✅ Зарегистрирован модуль развертывания: {name}")
            except ImportError as e:
                logger.warning(f"⚠️ Не удалось зарегистрировать модуль развертывания {name}: {e}")

    def _auto_register_balancing_modules(self):
        """Автоматическая регистрация модулей балансировки"""
        balancing_modules = {
            "simple": "core.modules.balancing.simple_balancer.SimpleBalancer",
            "smart": "core.modules.balancing.smart_balancer.SmartBalancer"
        }

        for name, module_path in balancing_modules.items():
            try:
                module = self._import_module(module_path)
                if module:
                    self.register_balancing_module(name, module)
                    logger.info(f"✅ Зарегистрирован модуль балансировки: {name}")
            except ImportError as e:
                logger.warning(f"⚠️ Не удалось зарегистрировать модуль балансировки {name}: {e}")

    def _auto_register_network_modules(self):
        """Автоматическая регистрация сетевых модулей"""
        network_modules = {
            "bridge": "core.modules.network.bridge_manager.BridgeManager"
        }

        for name, module_path in network_modules.items():
            try:
                module = self._import_module(module_path)
                if module:
                    self.register_network_module(name, module)
                    logger.info(f"✅ Зарегистрирован сетевой модуль: {name}")
            except ImportError as e:
                logger.warning(f"⚠️ Не удалось зарегистрировать сетевой модуль {name}: {e}")

    def _auto_register_template_modules(self):
        """Автоматическая регистрация модулей шаблонов"""
        template_modules = {
            "local": "core.modules.templates.local_templates.LocalTemplateManager",
            "migration": "core.modules.templates.migration_templates.MigrationTemplateManager"
        }

        for name, module_path in template_modules.items():
            try:
                module = self._import_module(module_path)
                if module:
                    self.register_template_module(name, module)
                    logger.info(f"✅ Зарегистрирован модуль шаблонов: {name}")
            except ImportError as e:
                logger.warning(f"⚠️ Не удалось зарегистрировать модуль шаблонов {name}: {e}")

    def _import_module(self, module_path: str) -> Optional[Type]:
        """Динамический импорт модуля по пути"""
        try:
            parts = module_path.split('.')
            module_name = '.'.join(parts[:-1])
            class_name = parts[-1]

            module = __import__(module_name, fromlist=[class_name])
            return getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            logger.error(f"Ошибка импорта модуля {module_path}: {e}")
            return None

    def register_deployment_module(self, name: str, module_class: Type[DeploymentInterface]):
        """Зарегистрировать модуль развертывания"""
        self.modules[f"deployment:{name}"] = module_class

    def register_balancing_module(self, name: str, module_class: Type[BalancingInterface]):
        """Зарегистрировать модуль балансировки"""
        self.modules[f"balancing:{name}"] = module_class

    def register_template_module(self, name: str, module_class: Type[TemplateInterface]):
        """Зарегистрировать модуль шаблонов"""
        self.modules[f"template:{name}"] = module_class

    def register_network_module(self, name: str, module_class: Type[NetworkInterface]):
        """Зарегистрировать сетевой модуль"""
        self.modules[f"network:{name}"] = module_class

    def create_deployment_module(self, name: str, **kwargs) -> DeploymentInterface:
        """Создать модуль развертывания"""
        module_class = self.modules.get(f"deployment:{name}")
        if not module_class:
            raise ValueError(f"Модуль развертывания '{name}' не найден")

        # Специальная обработка для модулей, требующих балансировку
        if name in ["balanced", "smart"]:
            balancer_name = "simple" if name == "balanced" else "smart"

            # Для SimpleBalancer нужен proxmox_client
            if balancer_name == "simple":
                balancer = self.create_balancing_module(balancer_name, proxmox_client=kwargs.get("proxmox_client"))
            else:  # SmartBalancer
                balancer = self.create_balancing_module(balancer_name,
                                                      proxmox_client=kwargs.get("proxmox_client"),
                                                      metrics=None,
                                                      cache=None)
            kwargs["balancing_module"] = balancer

        return module_class(**kwargs)

    def create_balancing_module(self, name: str, **kwargs) -> BalancingInterface:
        """Создать модуль балансировки"""
        module_class = self.modules.get(f"balancing:{name}")
        if not module_class:
            raise ValueError(f"Модуль балансировки '{name}' не найден")
        return module_class(**kwargs)

    def create_template_module(self, name: str, **kwargs) -> TemplateInterface:
        """Создать модуль шаблонов"""
        module_class = self.modules.get(f"template:{name}")
        if not module_class:
            raise ValueError(f"Модуль шаблонов '{name}' не найден")
        return module_class(**kwargs)

    def create_network_module(self, name: str, **kwargs) -> NetworkInterface:
        """Создать сетевой модуль"""
        module_class = self.modules.get(f"network:{name}")
        if not module_class:
            raise ValueError(f"Сетевой модуль '{name}' не найден")
        return module_class(**kwargs)

    def list_available_modules(self, module_type: str = None) -> List[str]:
        """Получить список доступных модулей"""
        if module_type:
            return [name.split(':')[1] for name in self.modules.keys() if name.startswith(f"{module_type}:")]
        return list(self.modules.keys())
