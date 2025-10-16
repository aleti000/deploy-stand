#!/usr/bin/env python3
"""
VMManager - менеджер виртуальных машин для newest_project

Управляет жизненным циклом виртуальных машин в кластере Proxmox VE,
включая создание, запуск, остановку, удаление и мониторинг VM.
"""

from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass

from ..utils.logger import Logger
from ..utils.validator import Validator
from ..utils.cache import Cache
from .proxmox_client import ProxmoxClient


@dataclass
class VMConfig:
    """Конфигурация виртуальной машины"""
    name: str
    memory: int
    cpus: int
    disk_size: int
    template_vmid: int
    template_node: str
    target_node: str
    vmid: Optional[int] = None
    description: str = ""
    full_clone: bool = False
    pool: Optional[str] = None


@dataclass
class VMOperationResult:
    """Результат операции с виртуальной машиной"""
    success: bool
    vmid: Optional[int] = None
    error: str = ""
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class VMManager:
    """
    Менеджер виртуальных машин

    Возможности:
    - Создание VM из шаблонов
    - Управление жизненным циклом VM (запуск/остановка/перезапуск)
    - Удаление VM
    - Мониторинг состояния VM
    - Клонирование VM
    - Массовые операции с VM
    """

    def __init__(self, proxmox_client: ProxmoxClient,
                 logger: Optional[Logger] = None,
                 validator: Optional[Validator] = None,
                 cache: Optional[Cache] = None):
        """
        Инициализация менеджера VM

        Args:
            proxmox_client: Клиент Proxmox API
            logger: Экземпляр логгера
            validator: Экземпляр валидатора
            cache: Экземпляр кеша
        """
        self.proxmox = proxmox_client
        self.logger = logger or Logger()
        self.validator = validator or Validator()
        self.cache = cache or Cache()

        # Кеш для VM
        self.vm_cache_ttl = 60  # 1 минута

    def create_vm(self, vm_config: VMConfig) -> VMOperationResult:
        """
        Создание виртуальной машины из шаблона

        Args:
            vm_config: Конфигурация новой VM

        Returns:
            Результат операции с VMID созданной машины
        """
        try:
            # Валидация конфигурации
            if not self._validate_vm_config(vm_config):
                return VMOperationResult(
                    success=False,
                    error="Некорректная конфигурация VM",
                    details={'config_errors': self.validator.get_errors()}
                )

            # Логирование начала создания
            self.logger.log_vm_creation(vm_config.name, vm_config.target_node, vm_config.vmid or 0)

            # Подготавливаем параметры клонирования
            clone_params = {
                'name': vm_config.name,
                'full': 1 if vm_config.full_clone else 0
            }

            if vm_config.vmid:
                clone_params['newid'] = vm_config.vmid

            if vm_config.pool:
                clone_params['pool'] = vm_config.pool

            if vm_config.description:
                clone_params['description'] = vm_config.description

            # Выполняем клонирование
            new_vmid = self.proxmox.clone_vm(
                node=vm_config.template_node,
                vmid=vm_config.template_vmid,
                new_name=vm_config.name,
                target_node=vm_config.target_node,
                **clone_params
            )

            # Очищаем кеш для новой VM
            self._clear_vm_cache(vm_config.target_node, new_vmid)

            self.logger.log_vm_creation(vm_config.name, vm_config.target_node, new_vmid)

            return VMOperationResult(
                success=True,
                vmid=new_vmid,
                details={'cloned_from': vm_config.template_vmid, 'target_node': vm_config.target_node}
            )

        except Exception as e:
            error_msg = f"Ошибка создания VM: {str(e)}"
            self.logger.log_deployment_error(error_msg, f"name={vm_config.name}")
            return VMOperationResult(success=False, error=error_msg)

    def delete_vm(self, node: str, vmid: int) -> VMOperationResult:
        """
        Удаление виртуальной машины

        Args:
            node: Имя ноды
            vmid: VMID для удаления

        Returns:
            Результат операции удаления
        """
        try:
            # Проверяем существование VM
            vm_info = self.get_vm_info(node, vmid)
            if not vm_info:
                return VMOperationResult(
                    success=False,
                    error=f"VM {vmid} не найдена на ноде {node}"
                )

            # Логирование удаления
            self.logger.log_validation_error("delete_vm", f"{node}:{vmid}", "удаление VM")

            # Удаляем VM
            success = self.proxmox.delete_vm(node, vmid)

            if success:
                # Очищаем кеш
                self._clear_vm_cache(node, vmid)

                return VMOperationResult(
                    success=True,
                    details={'deleted_vm': vm_info.name}
                )
            else:
                return VMOperationResult(
                    success=False,
                    error="Не удалось удалить VM через API"
                )

        except Exception as e:
            error_msg = f"Ошибка удаления VM: {str(e)}"
            self.logger.log_deployment_error(error_msg, f"node={node}, vmid={vmid}")
            return VMOperationResult(success=False, error=error_msg)

    def start_vm(self, node: str, vmid: int) -> VMOperationResult:
        """Запуск виртуальной машины"""
        try:
            vm_info = self.get_vm_info(node, vmid)
            if not vm_info:
                return VMOperationResult(
                    success=False,
                    error=f"VM {vmid} не найдена на ноде {node}"
                )

            success = self.proxmox.start_vm(node, vmid)

            if success:
                # Очищаем кеш для обновления статуса
                self._clear_vm_cache(node, vmid)

                return VMOperationResult(
                    success=True,
                    details={'started_vm': vm_info.name}
                )
            else:
                return VMOperationResult(
                    success=False,
                    error="Не удалось запустить VM через API"
                )

        except Exception as e:
            error_msg = f"Ошибка запуска VM: {str(e)}"
            self.logger.log_deployment_error(error_msg, f"node={node}, vmid={vmid}")
            return VMOperationResult(success=False, error=error_msg)

    def stop_vm(self, node: str, vmid: int) -> VMOperationResult:
        """Остановка виртуальной машины"""
        try:
            vm_info = self.get_vm_info(node, vmid)
            if not vm_info:
                return VMOperationResult(
                    success=False,
                    error=f"VM {vmid} не найдена на ноде {node}"
                )

            success = self.proxmox.stop_vm(node, vmid)

            if success:
                # Очищаем кеш для обновления статуса
                self._clear_vm_cache(node, vmid)

                return VMOperationResult(
                    success=True,
                    details={'stopped_vm': vm_info.name}
                )
            else:
                return VMOperationResult(
                    success=False,
                    error="Не удалось остановить VM через API"
                )

        except Exception as e:
            error_msg = f"Ошибка остановки VM: {str(e)}"
            self.logger.log_deployment_error(error_msg, f"node={node}, vmid={vmid}")
            return VMOperationResult(success=False, error=error_msg)

    def get_vm_info(self, node: str, vmid: int) -> Optional[Dict[str, Any]]:
        """
        Получение информации о виртуальной машине

        Args:
            node: Имя ноды
            vmid: VMID машины

        Returns:
            Информация о VM или None если не найдена
        """
        cache_key = f"vm_info:{node}:{vmid}"

        # Проверяем кеш
        cached_info = self.cache.get(cache_key)
        if cached_info:
            return cached_info

        try:
            # Получаем информацию через Proxmox API
            vm_data = self.proxmox.api_call('nodes', node, 'qemu', vmid, 'status', 'current', 'get')

            # Получаем конфигурацию VM
            vm_config = self.proxmox.api_call('nodes', node, 'qemu', vmid, 'config', 'get')

            vm_info = {
                'vmid': vmid,
                'name': vm_data.get('name', f'VM-{vmid}'),
                'node': node,
                'status': vm_data.get('status', 'unknown'),
                'memory': vm_config.get('memory', 0),
                'cpus': vm_config.get('cores', 1),
                'uptime': vm_data.get('uptime', 0),
                'cpu_usage': vm_data.get('cpu', 0),
                'memory_usage': vm_data.get('mem', 0)
            }

            # Сохраняем в кеш
            self.cache.set(cache_key, vm_info, ttl=self.vm_cache_ttl)

            return vm_info

        except Exception as e:
            self.logger.log_validation_error("vm_info", f"{node}:{vmid}", f"получение информации: {str(e)}")
            return None

    def list_vms(self, node: Optional[str] = None, include_templates: bool = False) -> List[Dict[str, Any]]:
        """
        Получение списка виртуальных машин

        Args:
            node: Имя ноды (если None, то все ноды)
            include_templates: Включать шаблоны в список

        Returns:
            Список виртуальных машин
        """
        try:
            vms = []

            if node:
                nodes_to_check = [node]
            else:
                nodes_to_check = self.proxmox.get_nodes()

            for current_node in nodes_to_check:
                try:
                    # Получаем список VM на ноде
                    node_vms = self.proxmox.api_call('nodes', current_node, 'qemu', 'get')

                    for vm_data in node_vms:
                        # Пропускаем шаблоны если не требуется
                        if not include_templates and vm_data.get('template') == 1:
                            continue

                        vm_info = self.get_vm_info(current_node, vm_data['vmid'])
                        if vm_info:
                            vms.append(vm_info)

                except Exception as e:
                    self.logger.log_validation_error("list_vms", current_node, f"список VM: {str(e)}")
                    continue

            return vms

        except Exception as e:
            self.logger.log_validation_error("list_vms", str(e), "получение списка VM")
            return []

    def _validate_vm_config(self, vm_config: VMConfig) -> bool:
        """Валидация конфигурации VM"""
        errors = []

        if not vm_config.name:
            errors.append("Имя VM не может быть пустым")

        if vm_config.memory <= 0:
            errors.append("Размер памяти должен быть положительным")

        if vm_config.cpus <= 0:
            errors.append("Количество CPU должно быть положительным")

        if vm_config.template_vmid <= 0:
            errors.append("VMID шаблона должен быть положительным")

        if not vm_config.template_node:
            errors.append("Нода шаблона не указана")

        if not vm_config.target_node:
            errors.append("Целевая нода не указана")

        # Сохраняем ошибки в валидаторе для доступа извне
        for error in errors:
            self.validator.log_validation_error("vm_config", error, "корректная конфигурация")

        return len(errors) == 0

    def _clear_vm_cache(self, node: str, vmid: int) -> None:
        """Очистка кеша для VM"""
        cache_key = f"vm_info:{node}:{vmid}"
        self.cache.delete(cache_key)

    def get_vm_statistics(self, node: Optional[str] = None) -> Dict[str, Any]:
        """
        Получение статистики по виртуальным машинам

        Args:
            node: Имя ноды (если None, то все ноды)

        Returns:
            Статистика VM
        """
        vms = self.list_vms(node)

        if not vms:
            return {
                'total_vms': 0,
                'running_vms': 0,
                'stopped_vms': 0,
                'total_memory': 0,
                'total_cpus': 0,
                'nodes': {}
            }

        stats = {
            'total_vms': len(vms),
            'running_vms': 0,
            'stopped_vms': 0,
            'total_memory': 0,
            'total_cpus': 0,
            'nodes': {}
        }

        for vm in vms:
            # Подсчет по статусам
            if vm['status'] == 'running':
                stats['running_vms'] += 1
            else:
                stats['stopped_vms'] += 1

            # Суммирование ресурсов
            stats['total_memory'] += vm.get('memory', 0)
            stats['total_cpus'] += vm.get('cpus', 1)

            # Статистика по нодам
            vm_node = vm['node']
            if vm_node not in stats['nodes']:
                stats['nodes'][vm_node] = {'total': 0, 'running': 0}
            stats['nodes'][vm_node]['total'] += 1
            if vm['status'] == 'running':
                stats['nodes'][vm_node]['running'] += 1

        return stats

    def bulk_start_vms(self, vm_list: List[Dict[str, Any]]) -> Dict[str, VMOperationResult]:
        """
        Массовый запуск виртуальных машин

        Args:
            vm_list: Список VM для запуска [{'node': str, 'vmid': int}, ...]

        Returns:
            Словарь результатов операций
        """
        results = {}

        for vm in vm_list:
            node = vm['node']
            vmid = vm['vmid']

            result = self.start_vm(node, vmid)
            results[f"{node}:{vmid}"] = result

        return results

    def bulk_stop_vms(self, vm_list: List[Dict[str, Any]]) -> Dict[str, VMOperationResult]:
        """
        Массовая остановка виртуальных машин

        Args:
            vm_list: Список VM для остановки [{'node': str, 'vmid': int}, ...]

        Returns:
            Словарь результатов операций
        """
        results = {}

        for vm in vm_list:
            node = vm['node']
            vmid = vm['vmid']

            result = self.stop_vm(node, vmid)
            results[f"{node}:{vmid}"] = result

        return results

    def bulk_delete_vms(self, vm_list: List[Dict[str, Any]]) -> Dict[str, VMOperationResult]:
        """
        Массовое удаление виртуальных машин

        Args:
            vm_list: Список VM для удаления [{'node': str, 'vmid': int}, ...]

        Returns:
            Словарь результатов операций
        """
        results = {}

        for vm in vm_list:
            node = vm['node']
            vmid = vm['vmid']

            result = self.delete_vm(node, vmid)
            results[f"{node}:{vmid}"] = result

        return results

    def find_vms_by_name(self, name_pattern: str, node: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Поиск VM по имени

        Args:
            name_pattern: Шаблон имени для поиска
            node: Имя ноды (если None, то все ноды)

        Returns:
            Список найденных VM
        """
        import re

        vms = self.list_vms(node)
        pattern = re.compile(name_pattern, re.IGNORECASE)

        matching_vms = []
        for vm in vms:
            if pattern.search(vm['name']):
                matching_vms.append(vm)

        return matching_vms

    def get_vms_by_user(self, user: str, node: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получение VM пользователя

        Args:
            user: Имя пользователя
            node: Имя ноды (если None, то все ноды)

        Returns:
            Список VM пользователя
        """
        # В будущем здесь будет логика определения VM пользователя
        # Пока возвращаем пустой список
        self.logger.log_validation_error("get_vms_by_user", user, "логика определения VM пользователя")
        return []

    def cleanup_user_vms(self, user: str) -> Dict[str, VMOperationResult]:
        """
        Очистка всех VM пользователя

        Args:
            user: Имя пользователя

        Returns:
            Результаты очистки
        """
        user_vms = self.get_vms_by_user(user)
        return self.bulk_delete_vms(user_vms)

    def clear_vm_cache(self, node: Optional[str] = None, vmid: Optional[int] = None) -> int:
        """
        Очистка кеша VM

        Args:
            node: Нода для очистки (если None, то все)
            vmid: VMID для очистки (если None, то все VM)

        Returns:
            Количество очищенных записей
        """
        cleared_count = 0

        if node and vmid:
            # Очищаем кеш для конкретной VM
            cache_key = f"vm_info:{node}:{vmid}"
            if self.cache.delete(cache_key):
                cleared_count += 1
        elif node:
            # Очищаем кеш для всей ноды
            cache_keys = [key for key in self.cache.cache.keys() if key.startswith(f'vm_info:{node}:')]
            for key in cache_keys:
                self.cache.delete(key)
                cleared_count += 1
        else:
            # Очищаем весь кеш VM
            cache_keys = [key for key in self.cache.cache.keys() if key.startswith('vm_info:')]
            for key in cache_keys:
                self.cache.delete(key)
                cleared_count += 1

        if cleared_count > 0:
            self.logger.log_cache_operation("clear_vm_cache", f"{cleared_count}_entries", True)

        return cleared_count


# Глобальный экземпляр менеджера VM
_global_vm_manager = None


def get_vm_manager(proxmox_client: ProxmoxClient) -> VMManager:
    """Получить глобальный экземпляр менеджера VM"""
    global _global_vm_manager
    if _global_vm_manager is None:
        _global_vm_manager = VMManager(proxmox_client)
    return _global_vm_manager


# Пример использования
if __name__ == "__main__":
    print("🖥️  VMManager - менеджер виртуальных машин")
    print("📋 Доступные методы:")

    # Получаем все публичные методы
    methods = [method for method in dir(VMManager) if not method.startswith('_') and callable(getattr(VMManager, method))]
    for method in methods:
        print(f"  - {method}")

    print(f"\n📊 Всего методов: {len(methods)}")
    print("✅ Менеджер VM готов к использованию")
