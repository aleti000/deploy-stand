"""
Локальный модуль развертывания виртуальных машин

Развертывает виртуальные машины непосредственно на ноде,
где хранятся оригинальные шаблоны.

ПОЛНОСТЬЮ НЕЗАВИСИМЫЙ МОДУЛЬ - не зависит от других модулей развертывания
"""

import logging
from typing import Dict, List, Any
from core.interfaces.deployment_interface import DeploymentInterface
from core.proxmox.proxmox_client import ProxmoxClient
from core.modules.network_manager import NetworkManager
from core.modules.vm_manager import VMManager
from core.services.user_service import UserService

logger = logging.getLogger(__name__)


class LocalDeployer(DeploymentInterface):
    """Локальный развертыватель виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация локального развертывателя

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client
        self.network_manager = NetworkManager(proxmox_client)
        self.vm_manager = VMManager(proxmox_client)
        self.user_service = UserService(proxmox_client)

    def deploy_configuration(self, users: List[str], config: Dict[str, Any],
                           node_selection: str = "auto", target_node: str = None) -> Dict[str, str]:
        """
        Развернуть конфигурацию виртуальных машин на локальной ноде

        Args:
            users: Список пользователей для развертывания
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды (игнорируется, всегда использует ноду с шаблонами)
            target_node: Целевая нода (игнорируется, используется нода шаблона)

        Returns:
            Словарь {пользователь: пароль}
        """
        results = {}

        try:
            # Развернуть для каждого пользователя
            for user in users:
                user_result = self._deploy_for_user(user, config)
                results.update(user_result)

            logger.info(f"Локальное развертывание завершено для {len(results)} пользователей")
            return results

        except Exception as e:
            logger.error(f"Ошибка локального развертывания: {e}")
            raise

    def _deploy_for_user(self, user: str, config: Dict[str, Any]) -> Dict[str, str]:
        """
        Развертывание для одного пользователя на локальной ноде

        Args:
            user: Имя пользователя
            config: Конфигурация развертывания

        Returns:
            Словарь {пользователь: пароль}
        """
        try:
            # Создать пользователя и пул
            success, password = self._create_user_and_pool(user)
            if not success:
                raise Exception(f"Ошибка создания пользователя {user}")

            # Создать виртуальные машины на локальной ноде (где хранятся шаблоны)
            pool_name = user.split('@')[0]
            for machine_config in config.get('machines', []):
                self._create_machine_local(machine_config, pool_name)

            logger.info(f"Локальное развертывание для пользователя {user} завершено")
            return {user: password}

        except Exception as e:
            logger.error(f"Ошибка локального развертывания для пользователя {user}: {e}")
            raise

    def _create_machine_local(self, machine_config: Dict[str, Any], pool: str) -> None:
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

            # Получить следующий VMID
            new_vmid = self.vm_service.get_next_vmid()

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
            if not self.proxmox.wait_for_task(task_id, template_node):
                raise Exception(f"Ошибка клонирования VM {new_vmid}")

            # Настроить сеть если указана
            networks = machine_config.get('networks', [])
            if networks:
                self.network_manager.configure_machine_network(new_vmid, template_node, networks, pool, device_type)

            # Выдать права пользователю на созданную VM
            user = pool + '@pve'  # Восстановить полное имя пользователя из имени пула
            if not self.vm_manager.grant_vm_permissions(user, template_node, new_vmid):
                logger.warning(f"Не удалось выдать права пользователю {user} на VM {new_vmid}")

            # 🔄 Перезагрузка сетевых подключений после создания VM
            try:
                logger.info(f"🔄 Перезагрузка сети на ноде {template_node} после создания VM {new_vmid}")
                if self.proxmox.reload_node_network(template_node):
                    logger.info(f"✅ Сеть на ноде {template_node} успешно перезагружена")
                else:
                    logger.warning(f"⚠️ Не удалось перезагрузить сеть на ноде {template_node}")
            except Exception as e:
                logger.error(f"❌ Ошибка перезагрузки сети на ноде {template_node}: {e}")
                # Не прерываем выполнение, если перезагрузка сети неудачна

            logger.info(f"Машина {name} (VMID: {new_vmid}) создана локально на ноде {template_node}")

        except Exception as e:
            logger.error(f"Ошибка создания локальной машины: {e}")
            raise

    def _create_user_and_pool(self, user: str) -> tuple[bool, str]:
        """
        Создать пользователя и пул

        Args:
            user: Имя пользователя

        Returns:
            Кортеж (успех, пароль)
        """
        try:
            # Используем UserService для создания пользователя и пула
            success, password = self.user_service.create_user_and_pool(user, "test123")
            if not success:
                logger.error(f"Не удалось создать пользователя и пул для {user}")
                return False, ""

            logger.info(f"Пользователь {user} и пул созданы через UserService")
            return True, password

        except Exception as e:
            logger.error(f"Ошибка создания пользователя и пула: {e}")
            return False, ""



    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Валидация конфигурации развертывания

        Args:
            config: Конфигурация для валидации

        Returns:
            True если конфигурация валидна
        """
        try:
            # Проверка наличия секции machines
            if 'machines' not in config:
                logger.error("Конфигурация не содержит секцию 'machines'")
                return False

            machines = config['machines']
            if not isinstance(machines, list) or len(machines) == 0:
                logger.error("Секция 'machines' должна быть непустым списком")
                return False

            # Валидация каждой машины
            for i, machine in enumerate(machines):
                if not self._validate_machine_config(machine, i):
                    return False

            return True

        except Exception as e:
            logger.error(f"Ошибка валидации конфигурации: {e}")
            return False

    def _validate_machine_config(self, machine: Dict[str, Any], index: int) -> bool:
        """
        Валидация конфигурации одной машины

        Args:
            machine: Конфигурация машины
            index: Индекс машины в списке

        Returns:
            True если конфигурация валидна
        """
        required_fields = ['template_vmid', 'template_node']
        optional_fields = ['device_type', 'name', 'networks', 'full_clone']

        # Проверка обязательных полей
        for field in required_fields:
            if field not in machine:
                logger.error(f"Машина {index}: отсутствует обязательное поле '{field}'")
                return False

        # Проверка типа template_vmid
        if not isinstance(machine['template_vmid'], int):
            logger.error(f"Машина {index}: поле 'template_vmid' должно быть числом")
            return False

        # Проверка допустимых значений
        if 'device_type' in machine:
            if machine['device_type'] not in ['linux', 'ecorouter']:
                logger.error(f"Машина {index}: недопустимый тип устройства '{machine['device_type']}'")
                return False

        # Проверка типа full_clone
        if 'full_clone' in machine:
            if not isinstance(machine['full_clone'], bool):
                logger.error(f"Машина {index}: поле 'full_clone' должно быть true/false")
                return False

        # Проверка сетевой конфигурации
        if 'networks' in machine:
            if not isinstance(machine['networks'], list):
                logger.error(f"Машина {index}: поле 'networks' должно быть списком")
                return False

            for j, network in enumerate(machine['networks']):
                if not isinstance(network, dict):
                    logger.error(f"Машина {index}, сеть {j}: должна быть объектом")
                    return False

                if 'bridge' not in network:
                    logger.error(f"Машина {index}, сеть {j}: отсутствует поле 'bridge'")
                    return False

        return True

    def get_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        """
        Получить статус локального развертывания

        Args:
            deployment_id: ID развертывания

        Returns:
            Словарь со статусом развертывания
        """
        return {
            'deployment_id': deployment_id,
            'status': 'completed',
            'strategy': 'local',
            'message': 'Локальное развертывание на ноде с шаблонами завершено'
        }
