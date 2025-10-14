"""
Фабрика виртуальных машин

Предоставляет централизованное создание виртуальных машин для всех стратегий развертывания,
включая локальное и удаленное создание с унифицированным интерфейсом.
"""

import logging
from typing import Dict, List, Any
from core.proxmox.proxmox_client import ProxmoxClient
from core.modules.common.deployment_utils import DeploymentUtils
from core.modules.users.user_manager import UserManager
from core.modules.network.network_configurator import NetworkConfigurator

logger = logging.getLogger(__name__)


class VMFactory:
    """Фабрика виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация фабрики VM

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client
        self.utils = DeploymentUtils()
        self.user_manager = UserManager(proxmox_client)
        self.network_configurator = NetworkConfigurator(proxmox_client)

    def create_machine_local(self, machine_config: Dict[str, Any], pool: str) -> None:
        """
        Создать виртуальную машину на локальной ноде с шаблонами

        Args:
            machine_config: Конфигурация машины
            pool: Имя пула
        """
        try:
            # Получить параметры машины
            template_node = machine_config['template_node']
            template_vmid = machine_config['template_vmid']
            device_type = machine_config.get('device_type', 'linux')
            name = machine_config.get('name', f"vm-{template_vmid}-{pool}")
            full_clone = machine_config.get('full_clone', False)

            # Санитизация имени машины
            name = self.utils.sanitize_machine_name(name)

            # Проверить, существует ли уже машина с таким именем в пуле
            if self._machine_exists_in_pool(name, pool):
                logger.info(f"Машина {name} уже существует в пуле {pool}, пропускаем создание")
                return

            # Получить следующий VMID
            new_vmid = self.get_available_vmid()

            # Клонировать виртуальную машину на той же ноде где шаблон
            task_id = self.proxmox.clone_vm(
                template_node=template_node,
                template_vmid=template_vmid,
                target_node=template_node,  # Развертывание на той же ноде
                new_vmid=new_vmid,
                name=name,
                pool=pool,
                full_clone=full_clone
            )

            # Ожидать завершения клонирования
            if not self.utils.wait_for_task_completion(self.proxmox, task_id, template_node):
                raise Exception(f"Ошибка клонирования VM {new_vmid}")

            # Настроить сеть если указана
            networks = machine_config.get('networks', [])
            if networks:
                self.network_configurator.configure_machine_network(
                    new_vmid, template_node, networks, pool, device_type
                )

            # Выдать права пользователю на созданную VM
            user = self.utils.build_user_name(pool)
            if not self.user_manager.grant_vm_permissions(user, template_node, new_vmid):
                logger.warning(f"Не удалось выдать права пользователю {user} на VM {new_vmid}")

            logger.info(f"Машина {name} (VMID: {new_vmid}) создана локально на ноде {template_node}")

        except Exception as e:
            logger.error(f"Ошибка создания локальной машины: {e}")
            raise

    def create_machine_remote(self, machine_config: Dict[str, Any],
                            target_node: str, pool: str, template_mapping: Dict[str, int]) -> None:
        """
        Создать виртуальную машину из локального шаблона

        Args:
            machine_config: Конфигурация машины
            target_node: Целевая нода
            pool: Имя пула
            template_mapping: Mapping шаблонов
        """
        try:
            # Получить параметры машины
            original_vmid = machine_config['template_vmid']
            template_node = machine_config['template_node']
            template_key = f"{original_vmid}:{template_node}"
            device_type = machine_config.get('device_type', 'linux')
            name = machine_config.get('name', f"vm-{original_vmid}-{pool}")
            full_clone = machine_config.get('full_clone', False)

            # Санитизация имени машины
            name = self.utils.sanitize_machine_name(name)

            # Проверить, существует ли уже машина с таким именем в пуле
            if self._machine_exists_in_pool(name, pool):
                logger.info(f"Машина {name} уже существует в пуле {pool}, пропускаем создание")
                return

            # Найти локальный шаблон
            local_template_vmid = template_mapping.get(template_key)
            if not local_template_vmid:
                raise Exception(f"Локальный шаблон не найден для {template_key}")

            # Получить следующий VMID
            new_vmid = self.utils.get_next_vmid(self.proxmox)

            # Клонировать из локального шаблона
            task_id = self.proxmox.clone_vm(
                template_node=target_node,
                template_vmid=local_template_vmid,
                target_node=target_node,
                new_vmid=new_vmid,
                name=name,
                pool=pool,
                full_clone=full_clone
            )

            # Ожидать завершения клонирования
            if not self.utils.wait_for_task_completion(self.proxmox, task_id, target_node):
                raise Exception(f"Ошибка клонирования VM {new_vmid}")

            # Настроить сеть если указана
            networks = machine_config.get('networks', [])
            if networks:
                self.network_configurator.configure_machine_network(
                    new_vmid, target_node, networks, pool, device_type
                )

            # Выдать права пользователю на созданную VM
            user = self.utils.build_user_name(pool)
            if not self.user_manager.grant_vm_permissions(user, target_node, new_vmid):
                logger.warning(f"Не удалось выдать права пользователю {user} на VM {new_vmid}")

            logger.info(f"Машина {name} (VMID: {new_vmid}) создана на ноде {target_node} из шаблона {local_template_vmid}")

        except Exception as e:
            logger.error(f"Ошибка создания удаленной машины: {e}")
            raise

    def _machine_exists_in_pool(self, machine_name: str, pool: str) -> bool:
        """
        Проверить, существует ли машина с таким именем в пуле

        Args:
            machine_name: Имя машины
            pool: Имя пула

        Returns:
            True если машина существует
        """
        try:
            pool_vms = self.proxmox.get_pool_vms(pool)
            for vm_info in pool_vms:
                if vm_info.get('name') == machine_name:
                    logger.info(f"Машина {machine_name} найдена в пуле {pool}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки существования машины {machine_name} в пуле {pool}: {e}")
            # В случае ошибки API лучше пропустить создание, чем создать дубликат
            logger.warning(f"Предполагаем что машина {machine_name} существует из-за ошибки API")
            return True

    def check_vmid_available(self, vmid: int) -> bool:
        """
        Проверить доступность VMID

        Args:
            vmid: VMID для проверки

        Returns:
            True если VMID доступен
        """
        try:
            # Попытаться получить информацию о VM с таким ID
            vm_info = self.proxmox.api.cluster.resources.get(type='vm', vmid=vmid)
            if vm_info:
                logger.warning(f"VMID {vmid} уже занят")
                return False
            return True
        except Exception:
            # VMID доступен (ошибка получения информации)
            return True

    def get_available_vmid(self) -> int:
        """
        Получить доступный VMID используя Proxmox API

        Returns:
            Доступный VMID
        """
        try:
            # Использовать встроенный метод Proxmox API для получения следующего VMID
            nextid_response = self.proxmox.api.cluster.nextid.get()
            next_vmid = int(nextid_response)

            logger.info(f"Получен следующий VMID от Proxmox API: {next_vmid}")
            return next_vmid

        except Exception as e:
            logger.warning(f"Ошибка получения следующего VMID через API: {e}")
            # Fallback: использовать утилиту
            return self.utils.get_next_vmid(self.proxmox)

    def delete_machine(self, vmid: int, node: str) -> bool:
        """
        Удалить виртуальную машину

        Args:
            vmid: VMID машины
            node: Нода размещения

        Returns:
            True если удаление успешно
        """
        try:
            return self.proxmox.delete_vm(node, vmid)
        except Exception as e:
            logger.error(f"Ошибка удаления VM {vmid} на ноде {node}: {e}")
            return False

    def get_machine_info(self, vmid: int, node: str) -> Dict[str, Any]:
        """
        Получить информацию о виртуальной машине

        Args:
            vmid: VMID машины
            node: Нода размещения

        Returns:
            Информация о машине
        """
        try:
            vm_info = self.proxmox.get_vm_info(node, vmid)
            return vm_info if vm_info else {}
        except Exception as e:
            logger.error(f"Ошибка получения информации о VM {vmid} на ноде {node}: {e}")
            return {}

    def list_machines_in_pool(self, pool: str) -> List[Dict[str, Any]]:
        """
        Получить список машин в пуле

        Args:
            pool: Имя пула

        Returns:
            Список машин в пуле
        """
        try:
            return self.proxmox.get_pool_vms(pool)
        except Exception as e:
            logger.error(f"Ошибка получения списка машин в пуле {pool}: {e}")
            return []

    def validate_machine_config(self, machine_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Валидация конфигурации машины

        Args:
            machine_config: Конфигурация машины

        Returns:
            Результат валидации
        """
        from core.modules.common.config_validator import ConfigValidator

        validator = ConfigValidator()
        result = validator.validate_machine_config(machine_config, 0)

        return {
            'is_valid': result.is_valid,
            'errors': result.errors,
            'warnings': result.warnings
        }

    def estimate_machine_resources(self, machine_config: Dict[str, Any]) -> Dict[str, float]:
        """
        Оценить потребление ресурсов машиной

        Args:
            machine_config: Конфигурация машины

        Returns:
            Оценка потребления ресурсов
        """
        # Базовые оценки ресурсов
        base_cpu = 1.0
        base_memory = 2.0  # GB
        base_storage = 20.0  # GB

        # Коэффициенты в зависимости от типа устройства
        device_type = machine_config.get('device_type', 'linux')
        if device_type == 'ecorouter':
            base_cpu *= 0.5  # Роутеры обычно требуют меньше CPU
            base_memory *= 0.75

        # Коэффициенты в зависимости от типа клонирования
        if machine_config.get('full_clone', False):
            base_storage *= 2  # Полные клоны занимают больше места

        # Коэффициенты в зависимости от количества сетевых интерфейсов
        network_count = len(machine_config.get('networks', []))
        base_cpu *= (1 + network_count * 0.1)  # Каждый интерфейс добавляет 10% CPU
        base_memory *= (1 + network_count * 0.05)  # Каждый интерфейс добавляет 5% памяти

        return {
            'cpu_cores': base_cpu,
            'memory_gb': base_memory,
            'storage_gb': base_storage,
            'network_interfaces': network_count
        }
