#!/usr/bin/env python3
"""
ProxmoxClientInterface - интерфейс для клиента Proxmox API

Определяет контракт для работы с Proxmox API в системе newest_project.
Интегрирует базовые утилиты: Logger, Validator, Cache.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from ..utils.logger import Logger
from ..utils.validator import Validator
from ..utils.cache import Cache


@dataclass
class ProxmoxConnectionInfo:
    """Информация о подключении к Proxmox"""
    host: str
    port: int
    username: str
    realm: Optional[str] = None
    version: Optional[str] = None
    authenticated: bool = False


@dataclass
class VMInfo:
    """Информация о виртуальной машине"""
    vmid: int
    name: str
    node: str
    status: str
    cpus: int
    memory: int
    disk: int
    networks: List[Dict[str, Any]]


@dataclass
class NodeInfo:
    """Информация о ноде кластера"""
    node: str
    status: str
    cpu_usage: float
    memory_usage: float
    memory_total: int
    uptime: int


@dataclass
class TemplateInfo:
    """Информация о шаблоне VM"""
    vmid: int
    name: str
    node: str
    memory: int
    cpus: int
    disk_size: int


class ProxmoxClientInterface(ABC):
    """
    Интерфейс для клиента Proxmox API

    Определяет методы для работы с Proxmox VE API:
    - Управление подключением
    - Работа с виртуальными машинами
    - Управление нодами кластера
    - Работа с шаблонами
    - Управление сетью

    Интегрирует базовые утилиты:
    - Logger для логирования операций
    - Validator для валидации данных
    - Cache для кеширования результатов
    """

    def __init__(self, logger: Optional[Logger] = None,
                 validator: Optional[Validator] = None,
                 cache: Optional[Cache] = None):
        """
        Инициализация интерфейса с базовыми утилитами

        Args:
            logger: Экземпляр логгера
            validator: Экземпляр валидатора
            cache: Экземпляр кеша
        """
        self.logger = logger or Logger()
        self.validator = validator or Validator()
        self.cache = cache or Cache()

    @abstractmethod
    def connect(self, host: str, user: str, password: Optional[str] = None,
                token_name: Optional[str] = None, token_value: Optional[str] = None) -> bool:
        """
        Установка подключения к Proxmox API

        Args:
            host: Хост Proxmox (например, "192.168.1.100:8006")
            user: Пользователь (например, "root@pam")
            password: Пароль пользователя
            token_name: Имя токена API (если используется токен)
            token_value: Значение токена API

        Returns:
            True если подключение успешно установлено
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Закрытие подключения к Proxmox API"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Проверка активного подключения"""
        pass

    @abstractmethod
    def get_connection_info(self) -> Optional[ProxmoxConnectionInfo]:
        """Получение информации о подключении"""
        pass

    @abstractmethod
    def get_version(self) -> str:
        """Получение версии Proxmox"""
        pass

    @abstractmethod
    def get_nodes(self) -> List[str]:
        """Получение списка нод кластера"""
        pass

    @abstractmethod
    def get_node_info(self, node: str) -> Optional[NodeInfo]:
        """
        Получение информации о ноде

        Args:
            node: Имя ноды

        Returns:
            Информация о ноде или None если нода не найдена
        """
        pass

    @abstractmethod
    def get_vms(self, node: Optional[str] = None) -> List[VMInfo]:
        """
        Получение списка виртуальных машин

        Args:
            node: Имя ноды (если None, то все ноды)

        Returns:
            Список виртуальных машин
        """
        pass

    @abstractmethod
    def get_vm_info(self, node: str, vmid: int) -> Optional[VMInfo]:
        """
        Получение информации о конкретной VM

        Args:
            node: Имя ноды
            vmid: ID виртуальной машины

        Returns:
            Информация о VM или None если не найдена
        """
        pass

    @abstractmethod
    def get_templates(self, node: Optional[str] = None) -> List[TemplateInfo]:
        """
        Получение списка шаблонов VM

        Args:
            node: Имя ноды (если None, то все ноды)

        Returns:
            Список шаблонов
        """
        pass

    @abstractmethod
    def clone_vm(self, node: str, vmid: int, new_name: str,
                 target_node: Optional[str] = None, **kwargs) -> int:
        """
        Клонирование виртуальной машины

        Args:
            node: Нода источника
            vmid: VMID источника
            new_name: Имя новой VM
            target_node: Целевая нода (если None, то та же что и источник)
            **kwargs: Дополнительные параметры клонирования

        Returns:
            VMID созданной виртуальной машины
        """
        pass

    @abstractmethod
    def delete_vm(self, node: str, vmid: int) -> bool:
        """
        Удаление виртуальной машины

        Args:
            node: Имя ноды
            vmid: VMID виртуальной машины

        Returns:
            True если VM успешно удалена
        """
        pass

    @abstractmethod
    def start_vm(self, node: str, vmid: int) -> bool:
        """
        Запуск виртуальной машины

        Args:
            node: Имя ноды
            vmid: VMID виртуальной машины

        Returns:
            True если VM успешно запущена
        """
        pass

    @abstractmethod
    def stop_vm(self, node: str, vmid: int) -> bool:
        """
        Остановка виртуальной машины

        Args:
            node: Имя ноды
            vmid: VMID виртуальной машины

        Returns:
            True если VM успешно остановлена
        """
        pass

    @abstractmethod
    def create_bridge(self, node: str, bridge_name: str,
                     vlan_aware: bool = False, **kwargs) -> bool:
        """
        Создание сетевого bridge

        Args:
            node: Имя ноды
            bridge_name: Имя bridge
            vlan_aware: Создать VLAN-aware bridge
            **kwargs: Дополнительные параметры

        Returns:
            True если bridge успешно создан
        """
        pass

    @abstractmethod
    def delete_bridge(self, node: str, bridge_name: str) -> bool:
        """
        Удаление сетевого bridge

        Args:
            node: Имя ноды
            bridge_name: Имя bridge

        Returns:
            True если bridge успешно удален
        """
        pass

    @abstractmethod
    def get_bridges(self, node: str) -> List[str]:
        """
        Получение списка bridge на ноде

        Args:
            node: Имя ноды

        Returns:
            Список имен bridge
        """
        pass

    @abstractmethod
    def configure_vm_network(self, node: str, vmid: int,
                           networks: List[Dict[str, Any]]) -> bool:
        """
        Настройка сети виртуальной машины

        Args:
            node: Имя ноды
            vmid: VMID виртуальной машины
            networks: Конфигурация сетевых интерфейсов

        Returns:
            True если сеть успешно настроена
        """
        pass

    @abstractmethod
    def get_cluster_resources(self) -> Dict[str, Any]:
        """Получение ресурсов кластера"""
        pass

    @abstractmethod
    def get_next_vmid(self) -> int:
        """Получение следующего доступного VMID"""
        pass

    @abstractmethod
    def execute_task(self, node: str, upid: str) -> Dict[str, Any]:
        """
        Получение статуса выполнения задачи

        Args:
            node: Имя ноды
            upid: UUID задачи

        Returns:
            Информация о задаче
        """
        pass


class ProxmoxClientFactoryInterface(ABC):
    """Интерфейс фабрики клиентов Proxmox"""

    @abstractmethod
    def create_client(self, connection_type: str = "default") -> ProxmoxClientInterface:
        """
        Создание клиента Proxmox

        Args:
            connection_type: Тип подключения

        Returns:
            Экземпляр клиента Proxmox
        """
        pass


# Исключения для работы с Proxmox API
class ProxmoxAPIError(Exception):
    """Базовое исключение для ошибок Proxmox API"""
    pass


class ProxmoxConnectionError(ProxmoxAPIError):
    """Ошибка подключения к Proxmox API"""
    pass


class ProxmoxAuthenticationError(ProxmoxAPIError):
    """Ошибка аутентификации в Proxmox API"""
    pass


class ProxmoxVMNotFoundError(ProxmoxAPIError):
    """Виртуальная машина не найдена"""
    pass


class ProxmoxNodeNotFoundError(ProxmoxAPIError):
    """Нода не найдена"""
    pass


class ProxmoxPermissionError(ProxmoxAPIError):
    """Ошибка прав доступа"""
    pass


# Пример использования интерфейса
if __name__ == "__main__":
    print("📋 Интерфейс ProxmoxClientInterface определен")
    print("🔧 Интегрированы базовые утилиты: Logger, Validator, Cache")
    print("📊 Доступные методы:")

    # Получаем все методы интерфейса
    methods = [method for method in dir(ProxmoxClientInterface) if not method.startswith('_')]
    for method in methods:
        print(f"  - {method}")

    print(f"\n📊 Всего методов: {len(methods)}")
    print("✅ Интерфейс готов к реализации")
