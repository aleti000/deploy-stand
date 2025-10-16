#!/usr/bin/env python3
"""
DeploymentManager - менеджер развертывания для newest_project

Основной модуль для автоматизированного развертывания виртуальных машин
с использованием всех созданных компонентов системы.
"""

import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ..utils.logger import Logger
from ..utils.validator import Validator
from ..utils.cache import Cache
from .proxmox_client import ProxmoxClient
from .config_manager import ConfigManager
from .user_manager import UserManager
from .network_manager import NetworkManager
from .bridge_manager import BridgeManager
from .template_manager import TemplateManager
from .vm_manager import VMManager, VMConfig, VMOperationResult


@dataclass
class DeploymentConfig:
    """Конфигурация развертывания"""
    machines: List[Dict[str, Any]]
    users: List[str]
    deployment_name: str = "default"
    description: str = ""


@dataclass
class DeploymentResult:
    """Результат развертывания"""
    success: bool
    total_machines: int
    created_machines: int
    failed_machines: int
    duration: float
    errors: List[str]
    warnings: List[str]
    created_vms: List[Dict[str, Any]]


class DeploymentManager:
    """
    Менеджер развертывания виртуальных машин

    Основной модуль, координирующий работу всех компонентов системы:
    - Загрузка конфигурации развертывания
    - Обработка пользователей
    - Создание сетевой инфраструктуры
    - Развертывание VM из шаблонов
    - Управление жизненным циклом VM
    """

    def __init__(self, proxmox_client: ProxmoxClient,
                 config_manager: Optional[ConfigManager] = None,
                 user_manager: Optional[UserManager] = None,
                 network_manager: Optional[NetworkManager] = None,
                 bridge_manager: Optional[BridgeManager] = None,
                 template_manager: Optional[TemplateManager] = None,
                 vm_manager: Optional[VMManager] = None,
                 logger: Optional[Logger] = None,
                 validator: Optional[Validator] = None,
                 cache: Optional[Cache] = None):
        """
        Инициализация менеджера развертывания

        Args:
            proxmox_client: Клиент Proxmox API
            config_manager: Менеджер конфигурации
            user_manager: Менеджер пользователей
            network_manager: Менеджер сети
            bridge_manager: Менеджер bridge'ей
            template_manager: Менеджер шаблонов
            vm_manager: Менеджер VM
            logger: Экземпляр логгера
            validator: Экземпляр валидатора
            cache: Экземпляр кеша
        """
        self.proxmox = proxmox_client
        self.config_manager = config_manager or ConfigManager()
        self.user_manager = user_manager or UserManager()
        self.network_manager = network_manager or NetworkManager()
        self.bridge_manager = bridge_manager or BridgeManager(proxmox_client)
        self.template_manager = template_manager or TemplateManager(proxmox_client)
        self.vm_manager = vm_manager or VMManager(proxmox_client)

        self.logger = logger or Logger()
        self.validator = validator or Validator()
        self.cache = cache or Cache()

    def deploy_stands(self, deployment_config: DeploymentConfig) -> DeploymentResult:
        """
        Развертывание стендов по конфигурации

        Args:
            deployment_config: Конфигурация развертывания

        Returns:
            Результат развертывания
        """
        start_time = time.time()
        errors = []
        warnings = []
        created_vms = []

        try:
            # Логирование начала развертывания
            self.logger.log_deployment_start(deployment_config.deployment_name, len(deployment_config.users))

            # Шаг 1: Валидация конфигурации
            if not self._validate_deployment_config(deployment_config):
                errors.append("Некорректная конфигурация развертывания")
                return DeploymentResult(
                    success=False,
                    total_machines=len(deployment_config.machines),
                    created_machines=0,
                    failed_machines=len(deployment_config.machines),
                    duration=time.time() - start_time,
                    errors=errors,
                    warnings=warnings,
                    created_vms=[]
                )

            # Шаг 2: Обработка пользователей
            user_validation = self.user_manager.validate_user_list(deployment_config.users)
            if not user_validation['valid']:
                errors.extend(user_validation['errors'])
                warnings.extend(user_validation['warnings'])

            # Шаг 3: Развертывание машин для каждого пользователя
            total_machines = len(deployment_config.machines)
            created_count = 0
            failed_count = 0

            for user in deployment_config.users:
                try:
                    # Развертывание машин для пользователя
                    user_results = self._deploy_user_stands(user, deployment_config.machines)

                    for result in user_results:
                        if result.success:
                            created_count += 1
                            if result.vmid:
                                created_vms.append({
                                    'user': user,
                                    'vmid': result.vmid,
                                    'name': result.details.get('vm_name', ''),
                                    'node': result.details.get('node', '')
                                })
                        else:
                            failed_count += 1
                            errors.append(f"Ошибка создания VM для {user}: {result.error}")

                except Exception as e:
                    failed_count += 1
                    errors.append(f"Критическая ошибка развертывания для {user}: {str(e)}")

            # Шаг 4: Финализация развертывания
            duration = time.time() - start_time
            success = len(errors) == 0

            if success:
                self.logger.log_deployment_success(created_count, duration)
            else:
                self.logger.log_deployment_error(f"Развертывание завершено с ошибками", f"Создано: {created_count}, Ошибок: {failed_count}")

            return DeploymentResult(
                success=success,
                total_machines=total_machines,
                created_machines=created_count,
                failed_machines=failed_count,
                duration=duration,
                errors=errors,
                warnings=warnings,
                created_vms=created_vms
            )

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Критическая ошибка развертывания: {str(e)}"
            errors.append(error_msg)

            self.logger.log_deployment_error(error_msg)

            return DeploymentResult(
                success=False,
                total_machines=len(deployment_config.machines),
                created_machines=0,
                failed_machines=len(deployment_config.machines),
                duration=duration,
                errors=errors,
                warnings=warnings,
                created_vms=[]
            )

    def _validate_deployment_config(self, deployment_config: DeploymentConfig) -> bool:
        """Валидация конфигурации развертывания"""
        if not deployment_config.machines:
            self.logger.log_validation_error("deployment_config", "no_machines", "список машин")
            return False

        if not deployment_config.users:
            self.logger.log_validation_error("deployment_config", "no_users", "список пользователей")
            return False

        # Валидация каждой машины
        for i, machine in enumerate(deployment_config.machines):
            if not self._validate_machine_config(machine, i):
                return False

        return True

    def _validate_machine_config(self, machine: Dict[str, Any], index: int) -> bool:
        """Валидация конфигурации одной машины"""
        required_fields = ['name', 'device_type', 'template_node', 'template_vmid']

        for field in required_fields:
            if field not in machine:
                self.logger.log_validation_error("machine_config", f"#{index}", f"отсутствует поле {field}")
                return False

        # Валидация имени машины
        if not machine['name'] or len(machine['name']) > 50:
            self.logger.log_validation_error("machine_name", machine.get('name', ''), "корректное имя")
            return False

        # Валидация типа устройства
        if machine['device_type'] not in ['linux', 'ecorouter']:
            self.logger.log_validation_error("device_type", machine['device_type'], "linux или ecorouter")
            return False

        # Валидация ноды шаблона
        if not machine['template_node']:
            self.logger.log_validation_error("template_node", machine.get('template_node', ''), "существующая нода")
            return False

        # Валидация VMID шаблона
        try:
            vmid = int(machine['template_vmid'])
            if vmid <= 0:
                self.logger.log_validation_error("template_vmid", vmid, "положительное число")
                return False
        except (ValueError, TypeError):
            self.logger.log_validation_error("template_vmid", machine.get('template_vmid', ''), "числовое значение")
            return False

        return True

    def _deploy_user_stands(self, user: str, machines: List[Dict[str, Any]]) -> List[VMOperationResult]:
        """
        Развертывание стендов для одного пользователя

        Args:
            user: Имя пользователя
            machines: Конфигурация машин

        Returns:
            Список результатов создания VM
        """
        results = []

        for machine in machines:
            try:
                # Создаем конфигурацию VM для пользователя
                vm_config = self._create_vm_config_for_user(user, machine)

                # Создаем VM
                result = self.vm_manager.create_vm(vm_config)
                results.append(result)

            except Exception as e:
                self.logger.log_deployment_error(f"Ошибка создания машины для {user}", str(e))
                results.append(VMOperationResult(success=False, error=str(e)))

        return results

    def _create_vm_config_for_user(self, user: str, machine: Dict[str, Any]) -> VMConfig:
        """Создание конфигурации VM для пользователя"""
        # Генерируем уникальное имя VM
        vm_name = f"{user}-{machine['name']}"

        # Определяем целевую ноду (в будущем здесь будет балансировка нагрузки)
        target_node = machine['template_node']

        return VMConfig(
            name=vm_name,
            memory=machine.get('memory', 2048),
            cpus=machine.get('cpus', 2),
            disk_size=machine.get('disk_size', 0),
            template_vmid=machine['template_vmid'],
            template_node=machine['template_node'],
            target_node=target_node,
            description=f"VM для пользователя {user}",
            full_clone=machine.get('full_clone', False),
            pool=user  # Используем имя пользователя как имя пула
        )

    def deploy_from_config_files(self, deployment_config_file: str, users_config_file: str) -> DeploymentResult:
        """
        Развертывание из конфигурационных файлов

        Args:
            deployment_config_file: Путь к файлу конфигурации развертывания
            users_config_file: Путь к файлу списка пользователей

        Returns:
            Результат развертывания
        """
        try:
            # Загружаем конфигурацию развертывания
            deployment_config = self.config_manager.load_deployment_config(deployment_config_file)
            if not deployment_config:
                return DeploymentResult(
                    success=False,
                    total_machines=0,
                    created_machines=0,
                    failed_machines=0,
                    duration=0,
                    errors=["Не удалось загрузить конфигурацию развертывания"],
                    warnings=[],
                    created_vms=[]
                )

            # Загружаем список пользователей
            users = self.config_manager.load_users_config(users_config_file)
            if not users:
                return DeploymentResult(
                    success=False,
                    total_machines=len(deployment_config.get('machines', [])),
                    created_machines=0,
                    failed_machines=len(deployment_config.get('machines', [])),
                    duration=0,
                    errors=["Не удалось загрузить список пользователей"],
                    warnings=[],
                    created_vms=[]
                )

            # Создаем объект конфигурации развертывания
            config = DeploymentConfig(
                machines=deployment_config['machines'],
                users=users,
                deployment_name="file_based_deployment"
            )

            # Выполняем развертывание
            return self.deploy_stands(config)

        except Exception as e:
            return DeploymentResult(
                success=False,
                total_machines=0,
                created_machines=0,
                failed_machines=0,
                duration=0,
                errors=[f"Ошибка развертывания из файлов: {str(e)}"],
                warnings=[],
                created_vms=[]
            )

    def cleanup_deployment(self, deployment_name: str) -> Dict[str, Any]:
        """
        Очистка развертывания

        Args:
            deployment_name: Имя развертывания для очистки

        Returns:
            Результат очистки
        """
        try:
            # Получаем все VM развертывания
            all_vms = self.vm_manager.list_vms()

            # Фильтруем VM по имени развертывания
            deployment_vms = []
            for vm in all_vms:
                if deployment_name in vm['name']:
                    deployment_vms.append({'node': vm['node'], 'vmid': vm['vmid']})

            if not deployment_vms:
                return {
                    'success': True,
                    'deleted_count': 0,
                    'message': 'VM развертывания не найдены'
                }

            # Удаляем VM
            results = self.vm_manager.bulk_delete_vms(deployment_vms)

            deleted_count = sum(1 for result in results.values() if result.success)

            return {
                'success': True,
                'deleted_count': deleted_count,
                'total_count': len(deployment_vms),
                'results': results
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_deployment_status(self, deployment_name: str) -> Dict[str, Any]:
        """
        Получение статуса развертывания

        Args:
            deployment_name: Имя развертывания

        Returns:
            Статус развертывания
        """
        try:
            # Получаем все VM развертывания
            all_vms = self.vm_manager.list_vms()

            # Фильтруем VM по имени развертывания
            deployment_vms = []
            for vm in all_vms:
                if deployment_name in vm['name']:
                    deployment_vms.append(vm)

            if not deployment_vms:
                return {
                    'found': False,
                    'message': 'VM развертывания не найдены'
                }

            # Анализируем статус VM
            running_count = sum(1 for vm in deployment_vms if vm['status'] == 'running')
            stopped_count = sum(1 for vm in deployment_vms if vm['status'] == 'stopped')

            return {
                'found': True,
                'total_vms': len(deployment_vms),
                'running_vms': running_count,
                'stopped_vms': stopped_count,
                'vms': deployment_vms
            }

        except Exception as e:
            return {
                'found': False,
                'error': str(e)
            }


# Глобальный экземпляр менеджера развертывания
_global_deployment_manager = None


def get_deployment_manager(proxmox_client: ProxmoxClient) -> DeploymentManager:
    """Получить глобальный экземпляр менеджера развертывания"""
    global _global_deployment_manager
    if _global_deployment_manager is None:
        _global_deployment_manager = DeploymentManager(proxmox_client)
    return _global_deployment_manager


# Пример использования
if __name__ == "__main__":
    print("🚀 DeploymentManager - менеджер развертывания виртуальных машин")
    print("📋 Доступные методы:")

    # Получаем все публичные методы
    methods = [method for method in dir(DeploymentManager) if not method.startswith('_') and callable(getattr(DeploymentManager, method))]
    for method in methods:
        print(f"  - {method}")

    print(f"\n📊 Всего методов: {len(methods)}")
    print("✅ Менеджер развертывания готов к использованию")
