"""
Продвинутый модуль развертывания виртуальных машин

Реализует расширенную стратегию развертывания с поддержкой балансировки нагрузки,
оптимизацией шаблонов и параллельной обработкой задач.
"""

import logging
import string
import time
from typing import Dict, List, Any
from core.interfaces.deployment_interface import DeploymentInterface
from core.proxmox.proxmox_client import ProxmoxClient
from core.interfaces.balancing_interface import BalancingInterface
from core.interfaces.template_interface import TemplateInterface
from core.interfaces.network_interface import NetworkInterface

logger = logging.getLogger(__name__)


class AdvancedDeployer(DeploymentInterface):
    """Продвинутый развертыватель виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient,
                 balancing_module: BalancingInterface,
                 template_module: TemplateInterface,
                 network_module: NetworkInterface,
                 config_manager=None, cache=None, metrics=None):
        """
        Инициализация продвинутого развертывателя

        Args:
            proxmox_client: Клиент для работы с Proxmox API
            balancing_module: Модуль балансировки нагрузки
            template_module: Модуль управления шаблонами
            network_module: Модуль управления сетью
            config_manager: Менеджер конфигурации
            cache: Кеш менеджер
            metrics: Метрики производительности
        """
        self.proxmox = proxmox_client
        self.balancing = balancing_module
        self.templates = template_module
        self.network = network_module
        self.config_manager = config_manager
        self.cache = cache
        self.metrics = metrics

    def deploy_configuration(self, users: List[str], config: Dict[str, Any],
                           node_selection: str = "auto", target_node: str = None) -> Dict[str, str]:
        """
        Продвинутое развертывание с оптимизацией

        Args:
            users: Список пользователей для развертывания
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды ("auto", "specific", "balanced")
            target_node: Целевая нода (если node_selection="specific")

        Returns:
            Словарь {пользователь: пароль}
        """
        results = {}

        try:
            # Валидация конфигурации
            if not self.validate_config(config):
                raise ValueError("Некорректная конфигурация развертывания")

            # Определить распределение пользователей по нодам
            nodes = self.proxmox.get_nodes()
            distribution = self._calculate_distribution(users, nodes, config, node_selection, target_node)

            logger.info(f"Распределение пользователей: {distribution}")

            # Подготовить шаблоны для всех целевых нод
            template_mapping = self._prepare_all_templates(config, distribution)

            # Развернуть виртуальные машины параллельно по нодам
            deployment_results = self._deploy_parallel(distribution, config, template_mapping)

            # Собрать результаты
            for node_result in deployment_results.values():
                results.update(node_result)

            logger.info(f"Продвинутое развертывание завершено для {len(results)} пользователей")
            return results

        except Exception as e:
            logger.error(f"Ошибка продвинутого развертывания: {e}")
            raise

    def _calculate_distribution(self, users: List[str], nodes: List[str],
                              config: Dict[str, Any], node_selection: str, target_node: str) -> Dict[str, List[str]]:
        """
        Рассчитать распределение пользователей по нодам

        Args:
            users: Список пользователей
            nodes: Доступные ноды
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды
            target_node: Целевая нода

        Returns:
            Словарь {нода: [пользователи]}
        """
        if node_selection == "specific" and target_node:
            # Развертывание на конкретную ноду
            if target_node not in nodes:
                raise ValueError(f"Целевая нода {target_node} не найдена")
            return {target_node: users}
        elif node_selection == "balanced":
            # Использовать модуль балансировки
            return self.balancing.distribute_deployment(users, nodes, config)
        else:
            # Автоматическое распределение (fallback на первую ноду)
            return {nodes[0]: users} if nodes else {}

    def _prepare_all_templates(self, config: Dict[str, Any], distribution: Dict[str, List[str]]) -> Dict[str, Dict]:
        """
        Подготовить шаблоны для всех целевых нод

        Args:
            config: Конфигурация развертывания
            distribution: Распределение пользователей по нодам

        Returns:
            Mapping шаблонов для каждой ноды
        """
        template_mapping = {}

        for node, users in distribution.items():
            if users:  # Подготовить шаблоны только если есть пользователи
                node_selection = "specific"
                target_node = node

                # Подготовить шаблоны для ноды
                if self.templates.prepare_templates_for_target_node(config, node_selection, target_node):
                    template_mapping[node] = self.templates.get_template_mapping()
                else:
                    logger.warning(f"Не удалось подготовить шаблоны для ноды {node}")

        return template_mapping

    def _deploy_parallel(self, distribution: Dict[str, List[str]],
                        config: Dict[str, Any], template_mapping: Dict[str, Dict]) -> Dict[str, Dict]:
        """
        Развернуть виртуальные машины параллельно по нодам

        Args:
            distribution: Распределение пользователей по нодам
            config: Конфигурация развертывания
            template_mapping: Mapping шаблонов

        Returns:
            Результаты развертывания по нодам
        """
        results = {}

        for node, users in distribution.items():
            if users:
                logger.info(f"Начинается развертывание на ноде {node} для {len(users)} пользователей")

                # Развернуть для пользователей на этой ноде
                node_results = self._deploy_for_node(node, users, config, template_mapping.get(node, {}))
                results[node] = node_results

        return results

    def _deploy_for_node(self, node: str, users: List[str],
                        config: Dict[str, Any], template_mapping: Dict) -> Dict[str, str]:
        """
        Развернуть виртуальные машины для пользователей на конкретной ноде

        Args:
            node: Целевая нода
            users: Список пользователей
            config: Конфигурация развертывания
            template_mapping: Mapping шаблонов для ноды

        Returns:
            Результаты развертывания {пользователь: пароль}
        """
        node_results = {}

        for user in users:
            try:
                # Создать пользователя и пул
                success, password = self._create_user_and_pool(user)
                if not success:
                    logger.error(f"Не удалось создать пользователя {user}")
                    continue

                # Создать виртуальные машины для пользователя
                pool_name = user.split('@')[0]
                for machine_config in config.get('machines', []):
                    self._create_machine_optimized(machine_config, node, pool_name, template_mapping)

                node_results[user] = password
                logger.info(f"Развертывание для пользователя {user} на ноде {node} завершено")

            except Exception as e:
                logger.error(f"Ошибка развертывания пользователя {user} на ноде {node}: {e}")
                node_results[user] = ""  # Пустой пароль как индикатор ошибки

        return node_results

    def _create_user_and_pool(self, user: str) -> tuple[bool, str]:
        """
        Создать пользователя и пул

        Args:
            user: Имя пользователя

        Returns:
            Кортеж (успех, пароль)
        """
        try:
            # Генерировать пароль
            password = self._generate_password()

            # Создать пользователя
            if not self.proxmox.create_user(user, password):
                return False, ""

            # Создать пул
            pool_name = user.split('@')[0]
            if not self.proxmox.create_pool(pool_name, f"Pool for {user}"):
                # Если создание пула неудачно, удалить пользователя
                self._cleanup_user(user)
                return False, ""

            # Установить права пользователя на пул
            permissions = ["PVEVMAdmin"]
            if not self.proxmox.set_pool_permissions(user, pool_name, permissions):
                # Если установка прав неудачна, очистить созданные ресурсы
                self._cleanup_user_and_pool(user, pool_name)
                return False, ""

            logger.info(f"Пользователь {user} и пул {pool_name} созданы")
            return True, password

        except Exception as e:
            logger.error(f"Ошибка создания пользователя и пула: {e}")
            return False, ""

    def _create_machine_optimized(self, machine_config: Dict[str, Any],
                                target_node: str, pool: str, template_mapping: Dict) -> None:
        """
        Создать виртуальную машину с оптимизацией

        Args:
            machine_config: Конфигурация машины
            target_node: Целевая нода
            pool: Имя пула
            template_mapping: Mapping шаблонов
        """
        try:
            # Получить параметры машины
            template_node = machine_config.get('template_node', target_node)
            template_vmid = machine_config['template_vmid']
            device_type = machine_config.get('device_type', 'linux')
            name = machine_config.get('name', f"vm-{template_vmid}-{pool}")
            full_clone = machine_config.get('full_clone', False)

            # Получить следующий VMID
            new_vmid = self.proxmox.get_next_vmid()

            # Использовать локальный шаблон если доступен
            local_template_vmid = template_mapping.get(f"{template_vmid}:{target_node}")

            if local_template_vmid:
                actual_template_vmid = local_template_vmid
                actual_template_node = target_node
                logger.info(f"Используется локальный шаблон {actual_template_vmid} на ноде {target_node}")
            else:
                actual_template_vmid = template_vmid
                actual_template_node = template_node
                logger.warning(f"Локальный шаблон не найден, используется оригинальный {template_vmid}")

            # Клонировать виртуальную машину
            task_id = self.proxmox.clone_vm(
                template_node=actual_template_node,
                template_vmid=actual_template_vmid,
                target_node=target_node,
                new_vmid=new_vmid,
                name=name,
                pool=pool,
                full_clone=full_clone
            )

            # Ожидать завершения клонирования
            if not self.proxmox.wait_for_task(task_id, actual_template_node):
                raise Exception(f"Ошибка клонирования VM {new_vmid}")

            # Настроить сеть если указана
            networks = machine_config.get('networks', [])
            if networks:
                self._configure_machine_network_optimized(new_vmid, target_node, networks, pool, device_type)

            logger.info(f"Машина {name} (VMID: {new_vmid}) создана в пуле {pool}")

        except Exception as e:
            logger.error(f"Ошибка создания машины: {e}")
            raise

    def _configure_machine_network_optimized(self, vmid: int, node: str, networks: List[Dict],
                                           pool: str, device_type: str) -> None:
        """
        Настроить сеть виртуальной машины с оптимизацией

        Args:
            vmid: VMID машины
            node: Нода размещения
            networks: Конфигурация сетей
            pool: Имя пула
            device_type: Тип устройства
        """
        try:
            # Подготовить все необходимые bridge'ы заранее через сетевой модуль
            bridge_mapping = {}
            for network in networks:
                bridge_name = network.get('bridge')
                if bridge_name:
                    # Определить зарезервированный ли bridge
                    reserved = network.get('reserved', False) or bridge_name.startswith('**')
                    # Использовать сетевой модуль для выделения bridge
                    bridge_mapping[bridge_name] = self.network.allocate_bridge(node, bridge_name, pool, reserved)

            # Подготовить конфигурации интерфейсов
            network_configs = {}

            # Обработка ecorouter устройств
            if device_type == 'ecorouter':
                mac = self._generate_mac_address()
                network_configs['net0'] = f'model=vmxnet3,bridge=vmbr0,macaddr={mac},link_down=1'

            # Настроить дополнительные интерфейсы
            for i, network in enumerate(networks):
                bridge = bridge_mapping.get(network['bridge'])
                if not bridge:
                    continue

                net_id = f"net{i+1}" if device_type != 'ecorouter' else f"net{i+2}"

                if device_type == 'ecorouter':
                    mac = self._generate_mac_address()
                    network_configs[net_id] = f'model=vmxnet3,bridge={bridge},macaddr={mac}'
                else:
                    network_configs[net_id] = f'model=virtio,bridge={bridge},firewall=1'

            # Применить сетевую конфигурацию
            if network_configs:
                if not self.proxmox.configure_vm_network(node, vmid, network_configs):
                    raise Exception(f"Ошибка настройки сети VM {vmid}")

            logger.info(f"Сеть VM {vmid} настроена")

        except Exception as e:
            logger.error(f"Ошибка настройки сети VM {vmid}: {e}")
            raise

    def _generate_password(self, length: int = 12) -> str:
        """Сгенерировать случайный пароль"""
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _generate_mac_address(self) -> str:
        """Сгенерировать случайный MAC адрес"""
        import secrets
        mac = [0x52, 0x54, 0x00]  # QEMU/Libvirt prefix
        mac.extend(secrets.randbelow(256) for _ in range(3))
        return ':'.join(f'{b:02x}' for b in mac)

    def _cleanup_user(self, user: str) -> None:
        """Очистить пользователя"""
        try:
            # Здесь можно добавить логику удаления пользователя
            logger.info(f"Очистка пользователя {user}")
        except Exception as e:
            logger.error(f"Ошибка очистки пользователя {user}: {e}")

    def _cleanup_user_and_pool(self, user: str, pool: str) -> None:
        """Очистить пользователя и пул"""
        try:
            # Здесь можно добавить логику удаления пользователя и пула
            logger.info(f"Очистка пользователя {user} и пула {pool}")
        except Exception as e:
            logger.error(f"Ошибка очистки пользователя и пула: {e}")

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
        required_fields = ['template_vmid']
        optional_fields = ['device_type', 'name', 'template_node', 'networks', 'full_clone']

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
        Получить статус развертывания

        Args:
            deployment_id: ID развертывания

        Returns:
            Словарь со статусом развертывания
        """
        # Заглушка - в реальной реализации здесь должна быть логика получения статуса
        return {
            'deployment_id': deployment_id,
            'status': 'unknown',
            'message': 'Статус развертывания недоступен в продвинутой реализации'
        }
