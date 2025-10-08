"""
Локальный модуль развертывания виртуальных машин

Развертывает виртуальные машины непосредственно на ноде,
где хранятся оригинальные шаблоны.

ПОЛНОСТЬЮ НЕЗАВИСИМЫЙ МОДУЛЬ - не зависит от других модулей развертывания
"""

import logging
import secrets
import string
import time
from typing import Dict, List, Any
from core.interfaces.deployment_interface import DeploymentInterface
from core.proxmox.proxmox_client import ProxmoxClient

logger = logging.getLogger(__name__)

# ГЛОБАЛЬНЫЙ КЕШ BRIDGE'ЕЙ - разделяемый между всеми экземплярами deployer'ов!
# ФОРМАТ: {node:poolsuffix:alias: allocated_bridge} для изоляции между пользователями
_global_bridge_cache = {}  # {node:poolsuffix:alias: allocated_bridge}


class LocalDeployer(DeploymentInterface):
    """Локальный развертыватель виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация локального развертывателя

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

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
            new_vmid = self.proxmox.get_next_vmid()

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
                self._configure_machine_network(new_vmid, template_node, networks, pool, device_type)

            # Выдать права пользователю на созданную VM
            user = pool + '@pve'  # Восстановить полное имя пользователя из имени пула
            if not self._grant_vm_permissions(user, template_node, new_vmid):
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
        Настроить сеть виртуальной машины (встроенная функциональность)

        Args:
            vmid: VMID машины
            node: Нода размещения
            networks: Конфигурация сетей (с bridge alias'ами)
            pool: Имя пула
            device_type: Тип устройства
        """
        try:
            # Подготовить все необходимые bridge'ы
            bridge_mapping = self._prepare_bridges(node, networks, pool)

            # Подготовить конфигурации интерфейсов
            network_configs = self._prepare_network_configs(networks, bridge_mapping, device_type)

            # Пакетная настройка всех интерфейсов
            if not self.proxmox.configure_vm_network(node, vmid, network_configs):
                raise Exception(f"Ошибка настройки сети VM {vmid}")

            logger.info(f"Сеть VM {vmid} настроена (встроенная функциональность)")

        except Exception as e:
            logger.error(f"Ошибка настройки сети VM {vmid}: {e}")
            raise

    def _generate_password(self, length: int = 8) -> str:
        """Сгенерировать случайный пароль для обучающих стендов"""
        alphabet = string.digits  # Только цифры для простоты использования в обучении
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _generate_mac_address(self) -> str:
        """Сгенерировать случайный MAC адрес"""
        mac = [0x52, 0x54, 0x00]  # QEMU/Libvirt prefix
        mac.extend(secrets.randbelow(256) for _ in range(3))
        return ':'.join(f'{b:02x}' for b in mac)

    def _allocate_bridge(self, node: str, bridge_name: str, pool: str,
                        reserved: bool = False) -> tuple[str, int]:
        """
        Выделить bridge для сети с поддержкой VLAN

        Пользователь задает ALIAS (hq, inet, hq.100), скрипт выделяет реальный bridge (vmbr1000+)

        Args:
            node: Нода размещения
            bridge_name: ALIAS bridge'а из конфигурации пользователя (hq, inet, hq.100, etc)
            pool: Пул пользователя
            reserved: Флаг зарезервированного bridge'а

        Returns:
            Кортеж (имя_bridge, vlan_tag)
        """
        # Разбор имени bridge на базовое имя и VLAN
        base_bridge_name, vlan_tag = self._parse_bridge_name(bridge_name)

        # Reserved bridge - прямое использование без allocation
        if reserved or bridge_name.startswith('**'):
            actual_bridge = bridge_name.strip('*')
            # Проверить существует ли зарезервированный bridge
            if not self.proxmox.bridge_exists(node, actual_bridge):
                logger.info(f"Создаем зарезервированный bridge {actual_bridge} на ноде {node}")
                # Создать VLAN-aware bridge если указан VLAN
                if vlan_tag > 0:
                    self.proxmox.create_bridge(node, actual_bridge, vlan_aware=True)
                else:
                    self.proxmox.create_bridge(node, actual_bridge)
            return actual_bridge, vlan_tag

        # Bridge name должен быть ALIAS, а не реальным bridge именем
        if base_bridge_name.startswith('vmbr'):
            logger.debug(f"Используется реальное имя bridge '{base_bridge_name}' вместо alias")
            return base_bridge_name, vlan_tag  # Вернем как есть, но с предупреждением

        # Кеширование по node + pool + alias для ИЗОЛЯЦИИ между пользователями!
        # Каждый пользователь получает свой уникальный bridge для каждого alias
        pool_suffix = pool.split('@')[0] if '@' in pool else pool  # Извлекаем имя пула (student1)
        cache_key = f"{node}:{pool_suffix}:{bridge_name}"

        if cache_key in _global_bridge_cache:
            allocated_bridge = _global_bridge_cache[cache_key]
            # Валидация существующего bridge
            if not self.proxmox.bridge_exists(node, allocated_bridge):
                logger.warning(f"Bridge {allocated_bridge} не найден, создаем заново для alias '{bridge_name}' пользователя {pool_suffix}")
                # Создать VLAN-aware bridge если указан VLAN
                if vlan_tag > 0:
                    self.proxmox.create_bridge(node, allocated_bridge, vlan_aware=True)
                else:
                    self.proxmox.create_bridge(node, allocated_bridge)
            logger.debug(f"Пользователь '{pool_suffix}' - Alias '{bridge_name}' -> bridge '{allocated_bridge}' (из кеша)")
            return allocated_bridge, vlan_tag

        # Первый раз для этого пользователя+alias - выделяем новый bridge
        allocated_bridge = self._allocate_new_bridge_for_alias(node, bridge_name)

        # Создать VLAN-aware bridge если указан VLAN
        if vlan_tag > 0:
            logger.info(f"Создаем VLAN-aware bridge {allocated_bridge} для alias '{bridge_name}' на ноде {node}")
            self.proxmox.create_bridge(node, allocated_bridge, vlan_aware=True)
        else:
            self.proxmox.create_bridge(node, allocated_bridge)

        # Сохраняем в ГЛОБАЛЬНЫЙ кеш с учетом пользователя
        _global_bridge_cache[cache_key] = allocated_bridge
        logger.info(f"✅ Пользователь '{pool_suffix}' - Alias '{bridge_name}' -> выделен bridge '{allocated_bridge}' на ноде {node}")

        return allocated_bridge, vlan_tag

    def _allocate_new_bridge_for_alias(self, node: str, alias: str) -> str:
        """
        Выделить новый bridge для alias начиная с vmbr1000

        Args:
            node: Нода где выделить bridge
            alias: Alias для которого выделяем bridge

        Returns:
            Имя выделенного bridge'а
        """
        # Всегда начинаем с vmbr1000 как указано в HOWTO
        bridge_start_number = 1000
        base_name = "vmbr"

        # Ищем первый свободный bridge
        for i in range(bridge_start_number, bridge_start_number + 1000):  # Защита от бесконечного цикла
            candidate_bridge = f"{base_name}{i}"

            # Проверяем существует ли уже такой bridge
            if not self.proxmox.bridge_exists(node, candidate_bridge):
                # Свободен! Создаем новый bridge
                logger.info(f"Создаем новый bridge {candidate_bridge} для alias '{alias}' на ноде {node}")
                if self.proxmox.create_bridge(node, candidate_bridge):
                    return candidate_bridge
                else:
                    logger.error(f"Не удалось создать bridge {candidate_bridge}")
                    continue

        # Fallback если все bridge заняты (маловероятно)
        timestamp_bridge = f"{base_name}{int(time.time())}"
        logger.warning(f"Все стандартные bridge заняты, создаем {timestamp_bridge} для alias '{alias}'")
        self.proxmox.create_bridge(node, timestamp_bridge)
        return timestamp_bridge

    def _prepare_bridges(self, node: str, networks: List[Dict], pool: str) -> Dict[str, tuple]:
        """
        Подготовить bridge'ы для сетевой конфигурации с поддержкой VLAN

        Args:
            node: Нода размещения
            networks: Конфигурация сетей
            pool: Пул пользователя

        Returns:
            Mapping bridge имен -> (имя_bridge, vlan_tag)
        """
        bridge_mapping = {}

        for network in networks:
            bridge_name = network.get('bridge')
            if bridge_name:
                reserved = network.get('reserved', False) or bridge_name.startswith('**')
                allocated_bridge, vlan_tag = self._allocate_bridge(node, bridge_name, pool, reserved)
                bridge_mapping[bridge_name] = (allocated_bridge, vlan_tag)

        return bridge_mapping

    def _prepare_network_configs(self, networks: List[Dict], bridge_mapping: Dict[str, tuple],
                               device_type: str) -> Dict[str, str]:
        """
        Подготовить конфигурации сетевых интерфейсов согласно требованиям HOWTO с поддержкой VLAN

        Args:
            networks: Конфигурация сетей
            bridge_mapping: Mapping bridge имен -> (имя_bridge, vlan_tag)
            device_type: Тип устройства

        Returns:
            Словарь конфигураций интерфейсов
        """
        network_configs = {}

        # Специальная обработка ecorouter устройств согласно HOWTO
        if device_type == 'ecorouter':
            # net0 всегда на vmbr0 с link_down=1 (управляющий интерфейс)
            mac0 = self._generate_ecorouter_mac()
            network_configs['net0'] = f'model=vmxnet3,bridge=vmbr0,macaddr={mac0},link_down=1'

            # Остальные интерфейсы начинаются с net2 (net1 пропускается)
            for i, network in enumerate(networks):
                bridge_info = bridge_mapping.get(network['bridge'])
                if not bridge_info:
                    continue

                bridge_name, vlan_tag = bridge_info
                net_id = f"net{i+2}"  # net2, net3, net4...
                mac = self._generate_ecorouter_mac()

                # Добавить VLAN tag если указан
                if vlan_tag > 0:
                    network_configs[net_id] = f'model=vmxnet3,bridge={bridge_name},macaddr={mac},tag={vlan_tag}'
                else:
                    network_configs[net_id] = f'model=vmxnet3,bridge={bridge_name},macaddr={mac}'

        # Обработка Linux виртуальных машин
        else:
            for i, network in enumerate(networks):
                bridge_info = bridge_mapping.get(network['bridge'])
                if not bridge_info:
                    continue

                bridge_name, vlan_tag = bridge_info
                net_id = f"net{i+1}"  # net1, net2, net3...

                # Добавить VLAN tag если указан
                if vlan_tag > 0:
                    network_configs[net_id] = f'model=virtio,bridge={bridge_name},firewall=1,tag={vlan_tag}'
                else:
                    network_configs[net_id] = f'model=virtio,bridge={bridge_name},firewall=1'

        return network_configs

    def _parse_bridge_name(self, bridge_name: str) -> tuple[str, int]:
        """
        Разобрать имя bridge на базовое имя и VLAN tag

        Args:
            bridge_name: Имя bridge (например, "hq.100")

        Returns:
            Кортеж (базовое_имя_bridge, vlan_tag)
        """
        if '.' in bridge_name:
            parts = bridge_name.split('.')
            if len(parts) == 2:
                base_name = parts[0]
                try:
                    vlan_tag = int(parts[1])
                    return base_name, vlan_tag
                except ValueError:
                    # Если вторая часть не число, считаем что VLAN не указан
                    pass

        return bridge_name, 0

    def _generate_ecorouter_mac(self) -> str:
        """Сгенерировать MAC адрес для ecorouter устройств из диапазона 1C:87:76:40:00:00 - 1C:87:76:4F:FF:FF"""
        # Специальный диапазон для ecorouter: 1C:87:76:40:XX:XX
        # Фиксированные байты: 1C:87:76:40
        # Переменные байты: XX:XX (00:00 - FF:FF)
        mac = [0x1C, 0x87, 0x76, 0x40]  # Ecorouter OUI prefix
        mac.extend(secrets.randbelow(256) for _ in range(2))  # Случайные 2 байта
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

    def _grant_vm_permissions(self, user: str, node: str, vmid: int) -> bool:
        """
        Выдать права пользователю на конкретную виртуальную машину

        Args:
            user: Имя пользователя (например, "student1@pve")
            node: Нода размещения VM
            vmid: VMID машины

        Returns:
            True если права выданы успешно
        """
        try:
            # Установить права PVEVMUser на конкретную VM
            # Права выдаются на путь /vms/{vmid}
            permissions = ["PVEVMUser"]

            for permission in permissions:
                self.proxmox.api.access.acl.put(
                    users=user,
                    path=f"/vms/{vmid}",
                    roles=permission,
                    propagate=0  # Не распространять на дочерние объекты
                )

            logger.info(f"Права PVEVMUser выданы пользователю {user} на VM {vmid} на ноде {node}")
            return True

        except Exception as e:
            logger.error(f"Ошибка выдачи прав пользователю {user} на VM {vmid}: {e}")
            return False

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
