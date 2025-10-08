"""
Фабрика для создания и управления модулями

Предоставляет централизованный способ создания модулей различных типов
с поддержкой динамической регистрации и конфигурации.
"""

from typing import Dict, Any, Type, List
from .interfaces.deployment_interface import DeploymentInterface
from .interfaces.balancing_interface import BalancingInterface




class ModuleFactory:
    """Фабрика для создания и управления модулями"""

    def __init__(self):
        self.modules = {}
        self.interfaces = {}
        self._register_available_modules()

    def _register_available_modules(self):
        """Регистрация всех доступных модулей"""
        try:
            # Регистрация модулей развертывания
            from .modules.deployment.local_deployer import LocalDeployer
            from .modules.deployment.remote_deployer import RemoteDeployer
            from .modules.deployment.balanced_deployer import BalancedDeployer
            from .modules.deployment.smart_deployer import SmartDeployer

            self.register_deployment_module("local", LocalDeployer)
            self.register_deployment_module("remote", RemoteDeployer)
            self.register_deployment_module("balanced", BalancedDeployer)
            self.register_deployment_module("smart", SmartDeployer)

            # Модули балансировки больше не используются после рефакторинга
            # (модули развертывания содержат встроенную балансировку)





        except ImportError as e:
            # В случае ошибок импорта, модули просто не будут зарегистрированы
            pass

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
