#!/usr/bin/env python3
"""
ProxmoxClient - чистый клиент Proxmox API для newest_project

Предоставляет низкоуровневый интерфейс к Proxmox VE API.
Использует библиотеку proxmoxer и интегрирует базовые утилиты.
"""

import time
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse

try:
    from proxmoxer import ProxmoxAPI
except ImportError:
    print("❌ Библиотека proxmoxer не установлена. Установите: pip install proxmoxer")
    ProxmoxAPI = None

from ..utils.logger import Logger
from ..utils.validator import Validator
from ..utils.cache import Cache
from ..interfaces.proxmox_client_interface import (
    ProxmoxClientInterface,
    ProxmoxConnectionInfo,
    ProxmoxAPIError,
    ProxmoxConnectionError,
    ProxmoxAuthenticationError,
    ProxmoxVMNotFoundError,
    ProxmoxNodeNotFoundError,
    ProxmoxPermissionError
)


class ProxmoxClient(ProxmoxClientInterface):
    """
    Чистый клиент Proxmox API с использованием proxmoxer

    Предоставляет только базовые операции API:
    - Управление подключением
    - Получение информации о кластере
    - Доступ к ресурсам через API

    НЕ содержит высокоуровневых операций по управлению VM, сетью, шаблонами.
    Эти операции должны быть реализованы в отдельных специализированных модулях.

    Интегрирует базовые утилиты:
    - Logger для логирования операций API
    - Validator для валидации данных запросов
    - Cache для кеширования ответов API
    """

    def __init__(self, host: str = "", user: str = "", password: str = "",
                 token_name: Optional[str] = None, token_value: Optional[str] = None,
                 logger: Optional[Logger] = None,
                 validator: Optional[Validator] = None,
                 cache: Optional[Cache] = None,
                 verify_ssl: bool = False):
        """
        Инициализация клиента Proxmox

        Args:
            host: Хост Proxmox
            user: Пользователь
            password: Пароль
            token_name: Имя токена API
            token_value: Значение токена API
            logger: Экземпляр логгера
            validator: Экземпляр валидатора
            cache: Экземпляр кеша
            verify_ssl: Проверять SSL сертификаты
        """
        super().__init__(logger, validator, cache)

        if ProxmoxAPI is None:
            raise ImportError("Библиотека proxmoxer не доступна")

        self.host = host
        self.user = user
        self.password = password
        self.token_name = token_name
        self.token_value = token_value
        self.verify_ssl = verify_ssl

        self.proxmox = None
        self.connection_info = None

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
        try:
            # Валидация входных данных
            connection_data = {
                'host': host,
                'user': user,
                'password': password,
                'token_name': token_name,
                'token_value': token_value
            }

            if not self.validator.validate_proxmox_connection(connection_data):
                error_msg = "Некорректные данные подключения"
                self.logger.log_connection_error(host, error_msg)
                for error in self.validator.get_errors():
                    self.logger.log_validation_error("connection", error, "корректные данные")
                return False

            # Логирование попытки подключения
            self.logger.log_connection_attempt(host, user)

            # Парсинг хоста и порта
            parsed = urlparse(f"http://{host}")
            host_clean = parsed.hostname or host.split(':')[0]
            port = parsed.port or 8006

            # Создание подключения через proxmoxer
            if password:
                # Аутентификация по паролю
                self.proxmox = ProxmoxAPI(
                    host_clean,
                    user=user,
                    password=password,
                    port=port,
                    verify_ssl=self.verify_ssl
                )
            elif token_name and token_value:
                # Аутентификация по токену
                self.proxmox = ProxmoxAPI(
                    host_clean,
                    user=user,
                    token_name=token_name,
                    token_value=token_value,
                    port=port,
                    verify_ssl=self.verify_ssl
                )
            else:
                self.logger.log_connection_error(host, "Не указаны данные аутентификации")
                return False

            # Тестирование подключения
            version = self.get_version()
            if version:
                # Сохранение информации о подключении
                self.connection_info = ProxmoxConnectionInfo(
                    host=host,
                    port=port,
                    username=user,
                    version=version,
                    authenticated=True
                )

                self.logger.log_connection_success(host, version)
                return True
            else:
                self.logger.log_connection_error(host, "Не удалось получить версию API")
                return False

        except Exception as e:
            error_msg = f"Ошибка подключения: {str(e)}"
            self.logger.log_connection_error(host, error_msg)
            raise ProxmoxConnectionError(error_msg) from e

    def disconnect(self) -> None:
        """Закрытие подключения к Proxmox API"""
        if self.proxmox:
            self.proxmox = None
            self.connection_info = None
            self.logger.log_cache_operation("disconnect", "proxmox", True)

    def is_connected(self) -> bool:
        """Проверка активного подключения"""
        if not self.proxmox or not self.connection_info:
            return False

        try:
            # Проверяем подключение простым запросом
            self.get_version()
            return True
        except Exception:
            return False

    def get_connection_info(self) -> Optional[ProxmoxConnectionInfo]:
        """Получение информации о подключении"""
        return self.connection_info

    def get_version(self) -> str:
        """Получение версии Proxmox"""
        cache_key = "proxmox_version"

        # Проверяем кеш
        cached_version = self.cache.get(cache_key)
        if cached_version:
            return cached_version

        try:
            if not self.proxmox:
                return ""

            # Получаем информацию о версии
            version_info = self.proxmox.version.get()
            version = version_info.get('version', 'unknown')

            # Сохраняем в кеш на 1 час
            self.cache.set(cache_key, version, ttl=3600)

            return version

        except Exception as e:
            self.logger.log_validation_error("version", str(e), "доступная версия")
            return ""

    def get_nodes(self) -> List[str]:
        """Получение списка нод кластера"""
        cache_key = "cluster_nodes"

        # Проверяем кеш
        cached_nodes = self.cache.get(cache_key)
        if cached_nodes:
            return cached_nodes

        try:
            if not self.proxmox:
                return []

            # Получаем список нод
            nodes_info = self.proxmox.cluster.status.get()
            nodes = [node['name'] for node in nodes_info if node.get('name')]

            # Сохраняем в кеш на 5 минут
            self.cache.set(cache_key, nodes, ttl=300)

            return nodes

        except Exception as e:
            self.logger.log_validation_error("nodes", str(e), "список нод")
            return []

    def get_node_info(self, node: str) -> Optional['NodeInfo']:
        """
        Получение информации о ноде

        Args:
            node: Имя ноды

        Returns:
            Информация о ноде или None если нода не найдена
        """
        cache_key = f"node_info:{node}"

        # Проверяем кеш
        cached_info = self.cache.get(cache_key)
        if cached_info:
            return self._dict_to_node_info(cached_info)

        try:
            if not self.proxmox:
                return None

            # Получаем информацию о ноде
            node_info = self.proxmox.nodes(node).status.get()

            # Извлекаем данные о ресурсах
            cpu_usage = node_info.get('cpu', 0)
            memory_used = node_info.get('memory', {}).get('used', 0)
            memory_total = node_info.get('memory', {}).get('total', 0)
            memory_usage = (memory_used / memory_total * 100) if memory_total > 0 else 0

            info = {
                'node': node,
                'status': node_info.get('status', 'unknown'),
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'memory_total': memory_total,
                'uptime': node_info.get('uptime', 0)
            }

            # Сохраняем в кеш на 2 минуты
            self.cache.set(cache_key, info, ttl=120)

            return self._dict_to_node_info(info)

        except Exception as e:
            self.logger.log_validation_error("node_info", node, f"доступная нода: {str(e)}")
            return None

    def _dict_to_node_info(self, data: Dict[str, Any]) -> Optional['NodeInfo']:
        """Преобразование словаря в NodeInfo"""
        try:
            return NodeInfo(
                node=data['node'],
                status=data['status'],
                cpu_usage=data['cpu_usage'],
                memory_usage=data['memory_usage'],
                memory_total=data['memory_total'],
                uptime=data['uptime']
            )
        except KeyError as e:
            self.logger.log_validation_error("node_info_dict", str(e), "полная структура данных")
            return None

    def get_cluster_resources(self) -> Dict[str, Any]:
        """Получение ресурсов кластера"""
        cache_key = "cluster_resources"

        cached_resources = self.cache.get(cache_key)
        if cached_resources:
            return cached_resources

        try:
            if not self.proxmox:
                return {}

            # Получаем ресурсы кластера
            resources = self.proxmox.cluster.resources.get()

            # Сохраняем в кеш на 3 минуты
            self.cache.set(cache_key, resources, ttl=180)

            return resources

        except Exception as e:
            self.logger.log_validation_error("cluster_resources", str(e), "ресурсы кластера")
            return {}

    def get_next_vmid(self) -> int:
        """Получение следующего доступного VMID"""
        try:
            if not self.proxmox:
                return 100  # Значение по умолчанию

            # Получаем ресурсы кластера для поиска следующего VMID
            resources = self.get_cluster_resources()

            # Находим максимальный VMID среди qemu VM
            max_vmid = 99  # Минимальное значение
            for resource in resources:
                if resource.get('type') == 'qemu' and 'vmid' in resource:
                    try:
                        vmid = int(resource['vmid'])
                        max_vmid = max(max_vmid, vmid)
                    except (ValueError, TypeError):
                        continue

            return max_vmid + 1

        except Exception as e:
            self.logger.log_validation_error("next_vmid", str(e), "доступный VMID")
            return 100  # Значение по умолчанию

    def execute_task(self, node: str, upid: str) -> Dict[str, Any]:
        """
        Получение статуса выполнения задачи

        Args:
            node: Имя ноды
            upid: UUID задачи

        Returns:
            Информация о задаче
        """
        try:
            if not self.proxmox:
                return {}

            # Получаем статус задачи
            task_info = self.proxmox.nodes(node).tasks(upid).status.get()

            return task_info

        except Exception as e:
            self.logger.log_validation_error("task_status", upid, f"статус задачи: {str(e)}")
            return {}

    # Методы для низкоуровневого доступа к API (для использования в других модулях)

    def get_api_client(self) -> Optional[Any]:
        """
        Получение низкоуровневого клиента proxmoxer

        Returns:
            Экземпляр proxmoxer.ProxmoxAPI или None
        """
        return self.proxmox

    def api_call(self, method: str, *args, **kwargs) -> Any:
        """
        Выполнение произвольного API вызова

        Args:
            method: Метод API (например, 'nodes.node.qemu.get')
            *args: Аргументы метода
            **kwargs: Параметры метода

        Returns:
            Результат API вызова
        """
        try:
            if not self.proxmox:
                raise ProxmoxConnectionError("Нет подключения к Proxmox")

            # Получаем метод из proxmox клиента
            api_method = self.proxmox
            for part in method.split('.'):
                api_method = getattr(api_method, part)

            # Выполняем вызов
            return api_method(*args, **kwargs)

        except Exception as e:
            self.logger.log_validation_error("api_call", method, f"успешный вызов: {str(e)}")
            raise ProxmoxAPIError(f"Ошибка API вызова {method}: {str(e)}") from e

    # Заглушки для интерфейса - эти методы должны быть реализованы в отдельных модулях
    # Они оставлены только для соблюдения контракта интерфейса

    def get_vms(self, node: Optional[str] = None) -> List['VMInfo']:
        """Должен быть реализован в VMManager"""
        raise NotImplementedError("Используйте VMManager для управления виртуальными машинами")

    def get_vm_info(self, node: str, vmid: int) -> Optional['VMInfo']:
        """Должен быть реализован в VMManager"""
        raise NotImplementedError("Используйте VMManager для получения информации о VM")

    def get_templates(self, node: Optional[str] = None) -> List['TemplateInfo']:
        """Должен быть реализован в TemplateManager"""
        raise NotImplementedError("Используйте TemplateManager для управления шаблонами")

    def clone_vm(self, node: str, vmid: int, new_name: str,
                 target_node: Optional[str] = None, **kwargs) -> int:
        """Должен быть реализован в VMManager"""
        raise NotImplementedError("Используйте VMManager для клонирования VM")

    def delete_vm(self, node: str, vmid: int) -> bool:
        """Должен быть реализован в VMManager"""
        raise NotImplementedError("Используйте VMManager для удаления VM")

    def start_vm(self, node: str, vmid: int) -> bool:
        """Должен быть реализован в VMManager"""
        raise NotImplementedError("Используйте VMManager для управления VM")

    def stop_vm(self, node: str, vmid: int) -> bool:
        """Должен быть реализован в VMManager"""
        raise NotImplementedError("Используйте VMManager для управления VM")

    def create_bridge(self, node: str, bridge_name: str,
                     vlan_aware: bool = False, **kwargs) -> bool:
        """Должен быть реализован в NetworkManager"""
        raise NotImplementedError("Используйте NetworkManager для управления сетью")

    def delete_bridge(self, node: str, bridge_name: str) -> bool:
        """Должен быть реализован в NetworkManager"""
        raise NotImplementedError("Используйте NetworkManager для управления сетью")

    def get_bridges(self, node: str) -> List[str]:
        """Должен быть реализован в NetworkManager"""
        raise NotImplementedError("Используйте NetworkManager для получения списка bridge")

    def configure_vm_network(self, node: str, vmid: int,
                           networks: List[Dict[str, Any]]) -> bool:
        """Должен быть реализован в NetworkManager"""
        raise NotImplementedError("Используйте NetworkManager для настройки сети VM")


# Фабрика для создания клиентов Proxmox
class ProxmoxClientFactory:
    """Фабрика для создания клиентов Proxmox"""

    @staticmethod
    def create_client(host: str = "", user: str = "", password: str = "",
                     token_name: Optional[str] = None, token_value: Optional[str] = None,
                     logger: Optional[Logger] = None,
                     validator: Optional[Validator] = None,
                     cache: Optional[Cache] = None) -> ProxmoxClient:
        """
        Создание клиента Proxmox

        Args:
            host: Хост Proxmox
            user: Пользователь
            password: Пароль
            token_name: Имя токена API
            token_value: Значение токена API
            logger: Экземпляр логгера
            validator: Экземпляр валидатора
            cache: Экземпляр кеша

        Returns:
            Настроенный клиент Proxmox
        """
        return ProxmoxClient(
            host=host,
            user=user,
            password=password,
            token_name=token_name,
            token_value=token_value,
            logger=logger,
            validator=validator,
            cache=cache
        )


# Пример использования
if __name__ == "__main__":
    print("🔗 ProxmoxClient - чистый API клиент")
    print("📋 Реализованные методы:")

    # Получаем все публичные методы
    methods = [method for method in dir(ProxmoxClient) if not method.startswith('_') and callable(getattr(ProxmoxClient, method))]
    for method in methods:
        print(f"  - {method}")

    print(f"\n📊 Всего методов: {len(methods)}")
    print("✅ Чистый API клиент готов к использованию")
    print("🔧 Высокоуровневые операции будут в отдельных модулях:")
    print("  - VMManager для управления виртуальными машинами")
    print("  - NetworkManager для управления сетью")
    print("  - TemplateManager для управления шаблонами")
