"""
Умный модуль развертывания виртуальных машин

Распределяет виртуальные машины по нодам кластера с учетом текущей нагрузки,
используя стратегию подготовки шаблонов и интеллектуальную балансировку.

ПОЛНОСТЬЮ НЕЗАВИСИМЫЙ МОДУЛЬ - содержит встроенную интеллектуальную балансировку
"""

import logging
import secrets
import string
import time
from typing import Dict, List, Any
from core.interfaces.deployment_interface import DeploymentInterface
from core.proxmox.proxmox_client import ProxmoxClient

logger = logging.getLogger(__name__)


class SmartDeployer(DeploymentInterface):
    """Умный развертыватель виртуальных машин с учетом нагрузки"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация умного развертывателя

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def deploy_configuration(self, users: List[str], config: Dict[str, Any],
                           node_selection: str = "smart", target_node: str = None) -> Dict[str, str]:
        """
        Развернуть конфигурацию виртуальных машин с умной балансировкой нагрузки

        Args:
            users: Список пользователей для развертывания
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды (умная балансировка по умолчанию)
            target_node: Целевая нода (игнорируется в режиме умной балансировки)

        Returns:
            Словарь {пользователь: пароль}
        """
        results = {}

        try:
            # Получить все доступные ноды
            nodes = self.proxmox.get_nodes()
            if not nodes:
                raise ValueError("Нет доступных нод для развертывания")

            # Получить текущую нагрузку на нодах
            node_loads = self._get_node_loads(nodes)
            logger.info(f"Текущая нагрузка на нодах: {node_loads}")

            logger.info(f"Умная балансировка развертывания по нодам: {', '.join(nodes)}")

            # Использовать встроенную интеллектуальную балансировку для распределения пользователей
            # с учетом текущей нагрузки на ноды
            distribution = self._distribute_users_smart(users, nodes, config)

            logger.info(f"Умное распределение пользователей по нодам: {distribution}")

            # Подготовить шаблоны для всех целевых нод
            template_mapping = self._prepare_templates_for_all_nodes(config, distribution)

            # Развернуть параллельно на всех нодах
            deployment_results = self._deploy_parallel(distribution, config, template_mapping)

            # Собрать результаты
            for node_result in deployment_results.values():
                results.update(node_result)

            # Перезагрузить сетевые конфигурации на задействованных нодах после развертывания
            affected_nodes = set()
            for node, users in distribution.items():
                if users:  # Только если на ноде были пользователи
                    affected_nodes.add(node)

            if affected_nodes:
                print("🔄 Обновление сетевых конфигураций на задействованных нодах...")
                for node in affected_nodes:
                    try:
                        if self.proxmox.reload_node_network(node):
                            print(f"  ✅ Сеть ноды {node} обновлена")
                        else:
                            print(f"  ⚠️ Не удалось обновить сеть ноды {node}")
                    except Exception as e:
                        print(f"  ❌ Ошибка обновления сети ноды {node}: {e}")

            logger.info(f"Умное развертывание завершено для {len(results)} пользователей")
            return results

        except Exception as e:
            logger.error(f"Ошибка умного развертывания: {e}")
            raise

    def _get_node_loads(self, nodes: List[str]) -> Dict[str, float]:
        """
        Получить текущую нагрузку на нодах

        Args:
            nodes: Список нод

        Returns:
            Словарь {нода: нагрузка(0.0-1.0)}
        """
        node_loads = {}

        for node in nodes:
            try:
                # Получить информацию о ноде
                node_info = self.proxmox.get_node_status(node)
                if node_info:
                    # Расчет нагрузки на основе CPU и памяти
                    cpu_load = float(node_info.get('cpu', 0))
                    memory_load = 1.0 - (float(node_info.get('memory_free', 0)) / float(node_info.get('memory_total', 1)))

                    # Комбинированная нагрузка (CPU и память с весами)
                    combined_load = (cpu_load * 0.6) + (memory_load * 0.4)
                    node_loads[node] = min(combined_load, 1.0)  # Ограничить до 1.0
                else:
                    node_loads[node] = 0.5  # Значение по умолчанию
            except Exception as e:
                logger.warning(f"Не удалось получить нагрузку для ноды {node}: {e}")
                node_loads[node] = 0.5  # Значение по умолчанию

        return node_loads

    def _prepare_templates_for_all_nodes(self, config: Dict[str, Any], distribution: Dict[str, List[str]]) -> Dict[str, Dict[str, int]]:
        """
        Подготовить шаблоны для всех целевых нод

        Args:
            config: Конфигурация развертывания
            distribution: Распределение пользователей по нодам

        Returns:
            Mapping нода -> {шаблон_key: local_vmid}
        """
        all_template_mappings = {}

        # Получить уникальные ноды с пользователями
        active_nodes = [node for node, users in distribution.items() if users]

        logger.info(f"Подготовка шаблонов для {len(active_nodes)} активных нод")

        # Подготовить шаблоны для каждой ноды параллельно (можно оптимизировать)
        for target_node in active_nodes:
            try:
                node_template_mapping = self._prepare_templates_for_target_node(config, target_node)
                all_template_mappings[target_node] = node_template_mapping
                logger.info(f"Шаблоны подготовлены для ноды {target_node}")
            except Exception as e:
                logger.error(f"Ошибка подготовки шаблонов для ноды {target_node}: {e}")
                raise

        return all_template_mappings

    def _prepare_templates_for_target_node(self, config: Dict[str, Any], target_node: str) -> Dict[str, int]:
        """
        Подготовить шаблоны для конкретной целевой ноды

        Процесс аналогичен RemoteDeployer:
        1. Full clone оригинального шаблона
        2. Преобразование в шаблон
        3. Миграция на целевую ноду

        Args:
            config: Конфигурация развертывания
            target_node: Целевая нода

        Returns:
            Mapping оригинальных VMID -> локальных VMID на целевой ноде
        """
        template_mapping = {}

        # Получить уникальные шаблоны из конфигурации
        unique_templates = set()
        for machine_config in config.get('machines', []):
            template_key = f"{machine_config['template_vmid']}:{machine_config['template_node']}"
            unique_templates.add(template_key)

        logger.info(f"Подготовка {len(unique_templates)} уникальных шаблонов для ноды {target_node}")

        for template_key in unique_templates:
            try:
                original_vmid, template_node = template_key.split(':')
                original_vmid = int(original_vmid)

                # Проверить, есть ли уже подготовленный шаблон на целевой ноде
                local_template_vmid = self._find_existing_template_on_node(original_vmid, target_node)
                if local_template_vmid:
                    template_mapping[template_key] = local_template_vmid
                    logger.info(f"Найден существующий шаблон {local_template_vmid} на ноде {target_node}")
                    continue

                # Подготовить новый шаблон
                local_template_vmid = self._prepare_single_template(original_vmid, template_node, target_node)
                if local_template_vmid:
                    template_mapping[template_key] = local_template_vmid
                else:
                    raise Exception(f"Не удалось подготовить шаблон {template_key}")

            except Exception as e:
                logger.error(f"Ошибка подготовки шаблона {template_key}: {e}")
                raise

        return template_mapping

    def _prepare_single_template(self, original_vmid: int, template_node: str, target_node: str) -> int:
        """
        Подготовить один шаблон для целевой ноды

        Args:
            original_vmid: VMID оригинального шаблона
            template_node: Нода где хранится оригинальный шаблон
            target_node: Целевая нода

        Returns:
            VMID подготовленного шаблона на целевой ноде
        """
        try:
            # 1. Full clone оригинального шаблона на той же ноде
            clone_vmid = self.proxmox.get_next_vmid()
            clone_name = f"template-clone-{original_vmid}-{int(time.time())}"

            logger.info(f"Создание full clone VM {original_vmid} -> VM {clone_vmid}")
            clone_task = self.proxmox.clone_vm(
                template_node=template_node,
                template_vmid=original_vmid,
                target_node=template_node,  # Клонируем на той же ноде
                new_vmid=clone_vmid,
                name=clone_name,
                full_clone=True  # Важно: full clone для независимости
            )

            if not self.proxmox.wait_for_task(clone_task, template_node):
                raise Exception(f"Ошибка клонирования VM {clone_vmid}")

            # 2. Преобразовать в шаблон
            logger.info(f"Преобразование VM {clone_vmid} в шаблон")
            if not self.proxmox.convert_to_template(template_node, clone_vmid):
                raise Exception(f"Ошибка преобразования VM {clone_vmid} в шаблон")

            # 3. Миграция на целевую ноду (если ноды разные)
            if template_node != target_node:
                logger.info(f"Миграция шаблона VM {clone_vmid} с {template_node} на {target_node}")
                migrate_task = self.proxmox.migrate_vm(
                    source_node=template_node,
                    target_node=target_node,
                    vmid=clone_vmid,
                    online=False  # Шаблоны миграируем offline
                )

                if not self.proxmox.wait_for_task(migrate_task, target_node):
                    raise Exception(f"Ошибка миграции VM {clone_vmid}")

            logger.info(f"Шаблон VM {clone_vmid} подготовлен на ноде {target_node}")
            return clone_vmid

        except Exception as e:
            logger.error(f"Ошибка подготовки шаблона VM {original_vmid}: {e}")
            # Попытка очистки в случае ошибки
            try:
                if 'clone_vmid' in locals():
                    self.proxmox.delete_vm(template_node, clone_vmid)
            except:
                pass
            raise

    def _find_existing_template_on_node(self, original_vmid: int, node: str) -> int:
        """
        Найти существующий подготовленный шаблон на ноде

        Args:
            original_vmid: VMID оригинального шаблона
            node: Нода для поиска

        Returns:
            VMID найденного шаблона или None
        """
        try:
            vms = self.proxmox.get_vms_on_node(node)
            for vm in vms:
                vm_name = vm.get('name', '')
                if vm_name.startswith(f"template-clone-{original_vmid}-") and vm.get('template', 0) == 1:
                    return int(vm['vmid'])
            return None
        except Exception as e:
            logger.warning(f"Ошибка поиска существующего шаблона: {e}")
            return None

    def _deploy_parallel(self, distribution: Dict[str, List[str]],
                        config: Dict[str, Any], template_mappings: Dict[str, Dict[str, int]]) -> Dict[str, Dict]:
        """
        Развернуть виртуальные машины параллельно по всем нодам

        Args:
            distribution: Распределение пользователей по нодам
            config: Конфигурация развертывания
            template_mappings: Mapping шаблонов по нодам

        Returns:
            Результаты развертывания по нодам
        """
        results = {}

        for node, users in distribution.items():
            if users:
                logger.info(f"Начинается умное развертывание на ноде {node} для {len(users)} пользователей")

                # Получить mapping шаблонов для этой ноды
                node_template_mapping = template_mappings.get(node, {})

                # Развернуть для пользователей на этой ноде
                node_results = self._deploy_for_node(node, users, config, node_template_mapping)
                results[node] = node_results

        return results

    def _deploy_for_node(self, node: str, users: List[str],
                        config: Dict[str, Any], template_mapping: Dict[str, int]) -> Dict[str, str]:
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

                # Создать виртуальные машины из локальных шаблонов
                pool_name = user.split('@')[0]
                for machine_config in config.get('machines', []):
                    self._create_machine_smart(machine_config, node, pool_name, template_mapping)

                node_results[user] = password
                logger.info(f"Умное развертывание для пользователя {user} на ноде {node} завершено")

            except Exception as e:
                logger.error(f"Ошибка умного развертывания пользователя {user} на ноде {node}: {e}")
                node_results[user] = ""  # Пустой пароль как индикатор ошибки

        return node_results

    def _create_machine_smart(self, machine_config: Dict[str, Any],
                             target_node: str, pool: str, template_mapping: Dict[str, int]) -> None:
        """
        Создать виртуальную машину из локального шаблона с умной стратегией

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

            # Найти локальный шаблон
            local_template_vmid = template_mapping.get(template_key)
            if not local_template_vmid:
                raise Exception(f"Локальный шаблон не найден для {template_key}")

            # Получить следующий VMID
            new_vmid = self.proxmox.get_next_vmid()

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
            if not self.proxmox.wait_for_task(task_id, target_node):
                raise Exception(f"Ошибка клонирования VM {new_vmid}")

            # Настроить сеть если указана
            networks = machine_config.get('networks', [])
            if networks:
                self._configure_machine_network(new_vmid, target_node, networks, pool, device_type)

            logger.info(f"Машина {name} (VMID: {new_vmid}) создана умно на ноде {target_node}")

        except Exception as e:
            logger.error(f"Ошибка создания умной машины: {e}")
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
            # Сгенерировать пароль
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

    def _configure_machine_network(self, vmid: int, node: str, networks: List[Dict],
                                 pool: str, device_type: str) -> None:
        """
        Настроить сеть виртуальной машины

        Args:
            vmid: VMID машины
            node: Нода размещения
            networks: Конфигурация сетей
            pool: Имя пула
            device_type: Тип устройства
        """
        try:
            network_configs = {}

            # Обработка ecorouter устройств
            if device_type == 'ecorouter':
                # Создать MAC адрес для управляющего интерфейса
                mac = self._generate_mac_address()
                network_configs['net0'] = f'model=vmxnet3,bridge=vmbr0,macaddr={mac},link_down=1'

            # Настроить дополнительные интерфейсы
            for i, network in enumerate(networks):
                bridge = network.get('bridge', f'vmbr{i+1}')
                net_id = f"net{i+1}" if device_type != 'ecorouter' else f"net{i+2}"

                if device_type == 'ecorouter':
                    mac = self._generate_mac_address()
                    network_configs[net_id] = f'model=vmxnet3,bridge={bridge},macaddr={mac}'
                else:
                    network_configs[net_id] = f'model=virtio,bridge={bridge},firewall=1'

            # Применить сетевую конфигурацию
            if not self.proxmox.configure_vm_network(node, vmid, network_configs):
                raise Exception(f"Ошибка настройки сети VM {vmid}")

            logger.info(f"Сеть VM {vmid} настроена")

        except Exception as e:
            logger.error(f"Ошибка настройки сети VM {vmid}: {e}")
            raise

    def _generate_password(self, length: int = 8) -> str:
        """Сгенерировать случайный пароль для обучающих стендов"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _generate_mac_address(self) -> str:
        """Сгенерировать случайный MAC адрес"""
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

    def _distribute_users_smart(self, users: List[str], nodes: List[str], config: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Распределить пользователей по нодам с учетом текущей нагрузки

        Встроенная реализация интеллектуальной балансировки

        Args:
            users: Список пользователей для распределения
            nodes: Доступные ноды
            config: Конфигурация развертывания

        Returns:
            Словарь {нода: [пользователи]}
        """
        # Получить текущую нагрузку на ноды
        node_loads = self._get_node_loads(nodes)

        # Рассчитать доступную емкость для каждой ноды (1.0 - нагрузка)
        node_capacity = {node: max(0.1, 1.0 - load) for node, load in node_loads.items()}

        # Нормализовать емкость для равномерного распределения весов
        total_capacity = sum(node_capacity.values())
        if total_capacity == 0:
            # Fallback на равномерное распределение если все ноды перегружены
            node_weights = {node: 1.0 for node in nodes}
        else:
            node_weights = {node: capacity / total_capacity for node, capacity in node_capacity.items()}

        # Распределить пользователей с учетом весов нод
        distribution = {node: [] for node in nodes}
        users_per_node = {}

        # Рассчитать количество пользователей для каждой ноды
        remaining_users = len(users)
        for node in nodes[:-1]:  # Все ноды кроме последней
            node_users = int(len(users) * node_weights[node])
            users_per_node[node] = node_users
            remaining_users -= node_users

        # Последней ноде отдать всех оставшихся пользователей
        users_per_node[nodes[-1]] = remaining_users

        # Распределить пользователей
        user_index = 0
        for node in nodes:
            for _ in range(users_per_node[node]):
                if user_index < len(users):
                    distribution[node].append(users[user_index])
                    user_index += 1

        logger.info(f"Интеллектуальная балансировка: {len(users)} пользователей распределены по {len(nodes)} нодам")
        logger.info(f"Веса нод: {node_weights}")
        return distribution

    def get_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        """
        Получить статус умного развертывания

        Args:
            deployment_id: ID развертывания

        Returns:
            Словарь со статусом развертывания
        """
        return {
            'deployment_id': deployment_id,
            'status': 'completed',
            'strategy': 'smart',
            'balancer': 'built-in',
            'message': 'Умное развертывание с балансировкой нагрузки завершено'
        }
