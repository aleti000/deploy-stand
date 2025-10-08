"""
Удаленный модуль развертывания виртуальных машин

Реализует развертывание на удаленной ноде с предварительной
подготовкой шаблона: full clone -> template conversion -> migration -> linked/full clone

ПОЛНОСТЬЮ НЕЗАВИСИМЫЙ МОДУЛЬ - не зависит от других модулей развертывания
"""

import logging
import os
import secrets
import string
import time
import yaml
from typing import Dict, List, Any, Optional
from core.interfaces.deployment_interface import DeploymentInterface
from core.proxmox.proxmox_client import ProxmoxClient

logger = logging.getLogger(__name__)

# ГЛОБАЛЬНЫЙ КЕШ BRIDGE'ЕЙ - разделяемый между всеми экземплярами deployer'ов!
# ФОРМАТ: {node:poolsuffix:alias: allocated_bridge} для изоляции между пользователями
_global_bridge_cache = {}  # {node:poolsuffix:alias: allocated_bridge}


class RemoteDeployer(DeploymentInterface):
    """Удаленный развертыватель виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация удаленного развертывателя

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def deploy_configuration(self, users: List[str], config: Dict[str, Any],
                           node_selection: str = "auto", target_node: str = None) -> Dict[str, str]:
        """
        Развернуть конфигурацию виртуальных машин на удаленной ноде

        Args:
            users: Список пользователей для развертывания
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды
            target_node: Целевая нода для развертывания

        Returns:
            Словарь {пользователь: пароль}
        """
        results = {}

        try:
            # Определить целевую ноду
            nodes = self.proxmox.get_nodes()
            if node_selection == "specific" and target_node:
                if target_node not in nodes:
                    raise ValueError(f"Целевая нода {target_node} не найдена")
                selected_node = target_node
            else:
                # Выбрать первую доступную ноду (не рекомендуется для production)
                selected_node = nodes[0] if nodes else None

            if not selected_node:
                raise ValueError("Нет доступных нод для развертывания")

            logger.info(f"Целевая нода для удаленного развертывания: {selected_node}")

            # Подготовить шаблоны для целевой ноды
            template_mapping = self._prepare_templates_for_target_node(config, selected_node)

            # Развернуть для каждого пользователя
            for user in users:
                user_result = self._deploy_for_user(user, config, selected_node, template_mapping)
                results.update(user_result)

            logger.info(f"Удаленное развертывание завершено для {len(results)} пользователей")
            return results

        except Exception as e:
            logger.error(f"Ошибка удаленного развертывания: {e}")
            raise

    def _prepare_templates_for_target_node(self, config: Dict[str, Any], target_node: str) -> Dict[str, int]:
        """
        Подготовить шаблоны для целевой ноды

        Процесс:
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

                if not self.proxmox.wait_for_task(migrate_task, template_node):
                    raise Exception(f"Ошибка миграции VM {clone_vmid}")

            logger.info(f"Шаблон VM {clone_vmid} подготовлен на ноде {target_node}")

            # Обновить mapper_template
            self._update_mapper_template(original_vmid, target_node, clone_vmid)

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

    def _find_existing_template_on_node(self, original_vmid: int, node: str) -> Optional[int]:
        """
        Найти существующий подготовленный шаблон на ноде

        Сначала проверяет API, затем mapper_template как кэш

        Args:
            original_vmid: VMID оригинального шаблона
            node: Нода для поиска

        Returns:
            VMID найденного шаблона или None
        """
        try:
            # 1. Сначала проверить через API (основной метод)
            vms = self.proxmox.get_vms_on_node(node)
            for vm in vms:
                vm_name = vm.get('name', '')
                if vm_name.startswith(f"template-clone-{original_vmid}-") and vm.get('template', 0) == 1:
                    found_vmid = int(vm['vmid'])
                    logger.info(f"Найден существующий шаблон {found_vmid} через API для {original_vmid} на {node}")
                    # Обновить mapper_template с актуальной информацией
                    self._update_mapper_template(original_vmid, node, found_vmid)
                    return found_vmid

            # 2. Проверить mapper_template только если API ничего не нашел
            mapper_data = self._load_mapper_template()
            template_mapping = mapper_data.get('template_mapping', {})
            original_mapping = template_mapping.get(original_vmid, {})
            local_vmid = original_mapping.get(node)

            if local_vmid:
                logger.warning(f"Шаблон {local_vmid} найден в mapper_template, но отсутствует в API для {original_vmid} на {node}")
                logger.info("Будет создан новый шаблон")
                # Удалить устаревшую запись из mapper_template
                if node in original_mapping:
                    del original_mapping[node]
                    self._save_mapper_template(mapper_data)

            return None
        except Exception as e:
            logger.warning(f"Ошибка поиска существующего шаблона: {e}")
            return None

    def _deploy_for_user(self, user: str, config: Dict[str, Any],
                        target_node: str, template_mapping: Dict[str, int]) -> Dict[str, str]:
        """
        Развертывание для одного пользователя на удаленной ноде

        Args:
            user: Имя пользователя
            config: Конфигурация развертывания
            target_node: Целевая нода
            template_mapping: Mapping шаблонов

        Returns:
            Словарь {пользователь: пароль}
        """
        try:
            # Создать пользователя и пул (или проверить существующие)
            success, password = self._create_user_and_pool(user)
            if not success:
                raise Exception(f"Ошибка создания пользователя {user}")

            # Создать виртуальные машины из локальных шаблонов (только недостающие)
            pool_name = user.split('@')[0]
            for machine_config in config.get('machines', []):
                self._create_machine_remote(machine_config, target_node, pool_name, template_mapping)

            logger.info(f"Удаленное развертывание для пользователя {user} завершено")
            return {user: password}

        except Exception as e:
            logger.error(f"Ошибка удаленного развертывания для пользователя {user}: {e}")
            raise

    def _create_machine_remote(self, machine_config: Dict[str, Any],
                              target_node: str, pool: str, template_mapping: Dict[str, int]) -> None:
        """
        Создать виртуальную машину из локального шаблона

        Проверяет наличие машины перед созданием

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

            # Проверить, существует ли уже машина с таким именем в пуле
            if self._machine_exists_in_pool(name, pool):
                logger.info(f"Машина {name} уже существует в пуле {pool}, пропускаем создание")
                return

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

            # Выдать права пользователю на созданную VM
            user = pool + '@pve'  # Восстановить полное имя пользователя из имени пула
            if not self._grant_vm_permissions(user, target_node, new_vmid):
                logger.warning(f"Не удалось выдать права пользователю {user} на VM {new_vmid}")

            logger.info(f"Машина {name} (VMID: {new_vmid}) создана на ноде {target_node} из шаблона {local_template_vmid}")

        except Exception as e:
            logger.error(f"Ошибка создания удаленной машины: {e}")
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
                    self.proxmox.create_bridge(node, actual_bridge, bridge_vlan_aware=True)
                else:
                    self.proxmox.create_bridge(node, actual_bridge)
            return actual_bridge, vlan_tag

        # Bridge name должен быть ALIAS, а не реальным bridge именем
        if base_bridge_name.startswith('vmbr'):
            logger.debug(f"Используется реальное имя bridge '{base_bridge_name}' вместо alias")
            return base_bridge_name, vlan_tag  # Вернем как есть, но с предупреждением

        # Кеширование по node + pool + БАЗОВОЕ ИМЯ BRIDGE для совместного использования VLAN и non-VLAN вариантов
        # Каждый пользователь получает один bridge для базового имени (hq), который может использоваться с разными VLAN tag'ами
        pool_suffix = pool.split('@')[0] if '@' in pool else pool  # Извлекаем имя пула (student1)
        base_cache_key = f"{node}:{pool_suffix}:{base_bridge_name}"

        if base_cache_key in _global_bridge_cache:
            allocated_bridge = _global_bridge_cache[base_cache_key]
            # Валидация существующего bridge
            if not self.proxmox.bridge_exists(node, allocated_bridge):
                logger.warning(f"Bridge {allocated_bridge} не найден, создаем заново для базового имени '{base_bridge_name}' пользователя {pool_suffix}")
                # Создать VLAN-aware bridge если указан VLAN
                if vlan_tag > 0:
                    self.proxmox.create_bridge(node, allocated_bridge, bridge_vlan_aware=True)
                else:
                    self.proxmox.create_bridge(node, allocated_bridge)
            logger.debug(f"Пользователь '{pool_suffix}' - Базовое имя '{base_bridge_name}' -> bridge '{allocated_bridge}' (из кеша)")
            return allocated_bridge, vlan_tag

        # Первый раз для этого пользователя+базовое_имя - выделяем новый bridge
        allocated_bridge = self._allocate_new_bridge_for_alias(node, base_bridge_name)

        # Создать VLAN-aware bridge если указан VLAN
        if vlan_tag > 0:
            logger.info(f"Создаем VLAN-aware bridge {allocated_bridge} для базового имени '{base_bridge_name}' на ноде {node}")
            self.proxmox.create_bridge(node, allocated_bridge, bridge_vlan_aware=True)
        else:
            self.proxmox.create_bridge(node, allocated_bridge)

        # Сохраняем в ГЛОБАЛЬНЫЙ кеш по БАЗОВОМУ имени bridge'а
        _global_bridge_cache[base_cache_key] = allocated_bridge
        logger.info(f"✅ Пользователь '{pool_suffix}' - Базовое имя '{base_bridge_name}' -> выделен bridge '{allocated_bridge}' на ноде {node}")

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
        Получить статус удаленного развертывания

        Args:
            deployment_id: ID развертывания

        Returns:
            Словарь со статусом развертывания
        """
        return {
            'deployment_id': deployment_id,
            'status': 'completed',
            'strategy': 'remote',
            'message': 'Удаленное развертывание с подготовкой шаблонов завершено'
        }

    def _load_mapper_template(self) -> Dict[str, Any]:
        """
        Загрузить mapper_template из файла

        Returns:
            Данные из mapper_template.yml
        """
        mapper_path = os.path.join('data', 'mapper_template.yml')
        try:
            if os.path.exists(mapper_path):
                with open(mapper_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            else:
                logger.warning("Файл mapper_template.yml не найден, создаем пустой")
                return {}
        except Exception as e:
            logger.error(f"Ошибка загрузки mapper_template.yml: {e}")
            return {}

    def _save_mapper_template(self, data: Dict[str, Any]) -> None:
        """
        Сохранить mapper_template в файл

        Args:
            data: Данные для сохранения
        """
        mapper_path = os.path.join('data', 'mapper_template.yml')
        try:
            os.makedirs(os.path.dirname(mapper_path), exist_ok=True)
            with open(mapper_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            logger.info("mapper_template.yml сохранен")
        except Exception as e:
            logger.error(f"Ошибка сохранения mapper_template.yml: {e}")

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
            return True  # В случае ошибки считаем что существует

    def _update_mapper_template(self, original_vmid: int, node: str, local_vmid: int) -> None:
        """
        Обновить mapper_template с новой информацией о шаблоне

        Args:
            original_vmid: VMID оригинального шаблона
            node: Нода размещения
            local_vmid: VMID локального шаблона
        """
        try:
            mapper_data = self._load_mapper_template()
            template_mapping = mapper_data.setdefault('template_mapping', {})

            original_mapping = template_mapping.setdefault(original_vmid, {})
            original_mapping[node] = local_vmid

            self._save_mapper_template(mapper_data)
            logger.info(f"_mapper_template обновлен: {original_vmid} -> {node}:{local_vmid}")
        except Exception as e:
            logger.error(f"Ошибка обновления mapper_template: {e}")

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
