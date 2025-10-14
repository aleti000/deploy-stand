"""
Модуль управления сетевыми bridge'ами

Реализует стратегию управления сетевыми интерфейсами и bridge'ами
для виртуальных машин в кластере Proxmox VE.
"""

import logging
from typing import Dict, List
from core.interfaces.network_interface import NetworkInterface
from core.proxmox.proxmox_client import ProxmoxClient

logger = logging.getLogger(__name__)


class BridgeManager(NetworkInterface):
    """Управление сетевыми bridge'ами"""

    # ГЛОБАЛЬНЫЙ КЕШ - разделяемый между всеми экземплярами BridgeManager!
    # ФОРМАТ: {node:poolsuffix:alias: allocated_bridge} для изоляции между пользователями
    _global_bridge_cache = {}  # {node:poolsuffix:alias: allocated_bridge}

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация менеджера bridge'ей

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def configure_network(self, vmid: int, node: str, networks: List[Dict],
                         pool: str, device_type: str = 'linux') -> bool:
        """
        Настроить сетевые интерфейсы виртуальной машины

        Args:
            vmid: ID виртуальной машины
            node: Нода размещения
            networks: Конфигурация сетей
            pool: Пул пользователя
            device_type: Тип устройства

        Returns:
            True если настройка успешна
        """
        try:
            # Подготовить все необходимые bridge'ы
            bridge_mapping = self._prepare_bridges(node, networks, pool)

            # Подготовить конфигурации интерфейсов
            network_configs = self._prepare_network_configs(networks, bridge_mapping, device_type)

            # Пакетная настройка всех интерфейсов
            return self.proxmox.configure_vm_network(node, vmid, network_configs)

        except Exception as e:
            logger.error(f"Ошибка настройки сети для VM {vmid}: {e}")
            return False

    def allocate_bridge(self, node: str, bridge_name: str, pool: str,
                       reserved: bool = False) -> str:
        """
        Выделить bridge для сети

        Пользователь задает ALIAS (hq, inet), скрипт выделяет реальный bridge (vmbr1000+)

        Args:
            node: Нода размещения
            bridge_name: ALIAS bridge'а из конфигурации пользователя (hq, inet, etc)
            pool: Пул пользователя
            reserved: Флаг зарезервированного bridge'а

        Returns:
            Реальное имя выделенного bridge'а (vmbrXXXX)
        """
        # Reserved bridge - прямое использование без allocation
        if reserved or bridge_name.startswith('**'):
            actual_bridge = bridge_name.strip('*')
            # Проверить существует ли зарезервированный bridge
            if not self.proxmox.bridge_exists(node, actual_bridge):
                logger.info(f"Создаем зарезервированный bridge {actual_bridge} на ноде {node}")
                self.proxmox.create_bridge(node, actual_bridge)
            return actual_bridge

        # Bridge name должен быть ALIAS, а не реальным bridge именем
        if bridge_name.startswith('vmbr'):
            logger.debug(f"Используется реальное имя bridge '{bridge_name}' вместо alias")
            return bridge_name  # Вернем как есть, но с предупреждением

        # Кеширование по node + pool + alias для ИЗОЛЯЦИИ между пользователями!
        # Каждый пользователь получает свой уникальный bridge для каждого alias
        pool_suffix = pool.split('@')[0] if '@' in pool else pool  # Извлекаем имя пула (student1)
        cache_key = f"{node}:{pool_suffix}:{bridge_name}"

        if cache_key in self._global_bridge_cache:
            allocated_bridge = self._global_bridge_cache[cache_key]
            # Валидация существующего bridge
            if not self.proxmox.bridge_exists(node, allocated_bridge):
                logger.warning(f"Bridge {allocated_bridge} не найден, создаем заново для alias '{bridge_name}' пользователя {pool_suffix}")
                self.proxmox.create_bridge(node, allocated_bridge)
            logger.debug(f"Пользователь '{pool_suffix}' - Alias '{bridge_name}' -> bridge '{allocated_bridge}' (из ГЛОБАЛЬНОГО кеша)")
            return allocated_bridge

        # Первый раз для этого пользователя+alias - выделяем новый bridge
        allocated_bridge = self._allocate_new_bridge_for_alias(node, bridge_name)

        # Сохраняем в ГЛОБАЛЬНЫЙ кеш с учетом пользователя
        self._global_bridge_cache[cache_key] = allocated_bridge
        logger.info(f"✅ Пользователь '{pool_suffix}' - Alias '{bridge_name}' -> выделен bridge '{allocated_bridge}' на ноде {node} (добавлен в глобальный кеш)")

        return allocated_bridge

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
        import time
        timestamp_bridge = f"{base_name}{int(time.time())}"
        logger.warning(f"Все стандартные bridge заняты, создаем {timestamp_bridge} для alias '{alias}'")
        self.proxmox.create_bridge(node, timestamp_bridge)
        return timestamp_bridge

    def cleanup_unused_bridges(self, nodes: List[str]) -> int:
        """
        Очистить неиспользуемые bridge'ы

        Args:
            nodes: Список нод для очистки

        Returns:
            Количество очищенных bridge'ей
        """
        cleaned_count = 0

        for node in nodes:
            # Получить все bridge'ы на ноде
            all_bridges = self.proxmox.list_bridges(node)

            for bridge in all_bridges:
                # Пропустить системные bridge'ы
                if bridge in ['vmbr0']:
                    continue

                # Проверить использование bridge'а
                if not self.proxmox.bridge_in_use(node, bridge):
                    # Удалить неиспользуемый bridge
                    if self.proxmox.delete_bridge(node, bridge):
                        cleaned_count += 1

        return cleaned_count

    def _prepare_bridges(self, node: str, networks: List[Dict], pool: str) -> Dict[str, str]:
        """
        Подготовить bridge'ы для сетевой конфигурации

        Args:
            node: Нода размещения
            networks: Конфигурация сетей
            pool: Пул пользователя

        Returns:
            Mapping bridge имен
        """
        bridge_mapping = {}

        for network in networks:
            bridge_name = network.get('bridge')
            if bridge_name:
                reserved = network.get('reserved', False) or bridge_name.startswith('**')
                allocated_bridge = self.allocate_bridge(node, bridge_name, pool, reserved)
                bridge_mapping[bridge_name] = allocated_bridge

        return bridge_mapping

    def _prepare_network_configs(self, networks: List[Dict], bridge_mapping: Dict[str, str],
                               device_type: str) -> Dict[str, str]:
        """
        Подготовить конфигурации сетевых интерфейсов согласно требованиям HOWTO

        Args:
            networks: Конфигурация сетей
            bridge_mapping: Mapping bridge имен
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
                bridge = bridge_mapping.get(network['bridge'])
                if not bridge:
                    continue

                net_id = f"net{i+2}"  # net2, net3, net4...
                mac = self._generate_ecorouter_mac()
                network_configs[net_id] = f'model=vmxnet3,bridge={bridge},macaddr={mac}'

        # Обработка Linux виртуальных машин
        else:
            for i, network in enumerate(networks):
                bridge = bridge_mapping.get(network['bridge'])
                if not bridge:
                    continue

                net_id = f"net{i+1}"  # net1, net2, net3...
                network_configs[net_id] = f'model=virtio,bridge={bridge},firewall=1'

        return network_configs

    def _find_next_available_bridge(self, node: str, base_name: str) -> str:
        """
        Найти следующее доступное имя bridge'а

        Args:
            node: Нода размещения
            base_name: Базовое имя bridge'а

        Returns:
            Доступное имя bridge'а
        """
        # Заглушка - в реальности здесь должна быть логика поиска доступного имени
        bridge_start_number = 1000  # Начальный номер для пользовательских bridge'ей

        for i in range(bridge_start_number, bridge_start_number + 1000):
            bridge_name = f"{base_name}{i}"
            if not self.proxmox.bridge_exists(node, bridge_name):
                return bridge_name

        # Fallback на случай если все имена заняты
        return f"{base_name}{int(time.time())}"

    def _generate_mac_address(self) -> str:
        """Сгенерировать случайный MAC адрес для Linux VM"""
        import secrets
        mac = [0x52, 0x54, 0x00]  # QEMU/Libvirt prefix
        mac.extend(secrets.randbelow(256) for _ in range(3))
        return ':'.join(f'{b:02x}' for b in mac)

    def _generate_ecorouter_mac(self) -> str:
        """Сгенерировать MAC адрес для ecorouter устройств из диапазона 1C:87:76:40:00:00 - 1C:87:76:4F:FF:FF"""
        import secrets
        # Специальный диапазон для ecorouter: 1C:87:76:40:XX:XX
        # Фиксированные байты: 1C:87:76:40
        # Переменные байты: XX:XX (00:00 - FF:FF)
        mac = [0x1C, 0x87, 0x76, 0x40]  # Ecorouter OUI prefix
        mac.extend(secrets.randbelow(256) for _ in range(2))  # Случайные 2 байта
        return ':'.join(f'{b:02x}' for b in mac)
