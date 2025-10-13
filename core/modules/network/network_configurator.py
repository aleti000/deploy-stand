"""
Конфигуратор сети виртуальных машин

Предоставляет централизованную настройку сетевых интерфейсов для всех стратегий развертывания,
включая управление bridge'ами и конфигурацию сетевых параметров.
"""

import logging
from typing import Dict, List, Any
from core.proxmox.proxmox_client import ProxmoxClient
from core.modules.common.deployment_utils import DeploymentUtils

logger = logging.getLogger(__name__)


class NetworkConfigurator:
    """Конфигуратор сети виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация конфигуратора сети

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client
        self.utils = DeploymentUtils()

    def configure_machine_network(self, vmid: int, node: str, networks: List[Dict],
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
                allocated_bridge = self._allocate_bridge(node, bridge_name, pool, reserved)
                bridge_mapping[bridge_name] = allocated_bridge

        return bridge_mapping

    def _allocate_bridge(self, node: str, bridge_name: str, pool: str, reserved: bool = False) -> str:
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
        pool_suffix = self.utils.extract_pool_name(pool)
        cache_key = f"{node}:{pool_suffix}:{bridge_name}"

        # Используем глобальный кеш из BridgeManager для совместимости
        from core.modules.network.bridge_manager import BridgeManager
        bridge_manager = BridgeManager(self.proxmox)

        return bridge_manager.allocate_bridge(node, bridge_name, pool, reserved)

    def _prepare_network_configs(self, networks: List[Dict], bridge_mapping: Dict[str, str],
                               device_type: str) -> Dict[str, str]:
        """
        Подготовить конфигурации сетевых интерфейсов согласно требованиям

        Args:
            networks: Конфигурация сетей
            bridge_mapping: Mapping bridge имен
            device_type: Тип устройства

        Returns:
            Словарь конфигураций интерфейсов
        """
        network_configs = {}

        # Специальная обработка ecorouter устройств
        if device_type == 'ecorouter':
            # net0 всегда на vmbr0 с link_down=1 (управляющий интерфейс)
            mac0 = self.utils.generate_ecorouter_mac()
            network_configs['net0'] = f'model=vmxnet3,bridge=vmbr0,macaddr={mac0},link_down=1'

            # Остальные интерфейсы начинаются с net2 (net1 пропускается)
            for i, network in enumerate(networks):
                bridge = bridge_mapping.get(network['bridge'])
                if not bridge:
                    continue

                net_id = f"net{i+2}"  # net2, net3, net4...
                mac = self.utils.generate_ecorouter_mac()
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

    def validate_network_config(self, networks: List[Dict], node: str) -> Dict[str, Any]:
        """
        Валидация сетевой конфигурации

        Args:
            networks: Конфигурация сетей
            node: Нода для проверки доступности bridge'ей

        Returns:
            Результат валидации
        """
        result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'bridge_availability': {}
        }

        if not isinstance(networks, list):
            result['is_valid'] = False
            result['errors'].append("Конфигурация сетей должна быть списком")
            return result

        # Проверка каждого сетевого интерфейса
        for i, network in enumerate(networks):
            if not isinstance(network, dict):
                result['is_valid'] = False
                result['errors'].append(f"Сеть {i}: должна быть объектом")
                continue

            bridge = network.get('bridge')
            if not bridge:
                result['is_valid'] = False
                result['errors'].append(f"Сеть {i}: отсутствует поле 'bridge'")
                continue

            # Проверить доступность bridge'а на ноде
            try:
                exists = self.proxmox.bridge_exists(node, bridge)
                result['bridge_availability'][bridge] = exists

                if not exists and not bridge.startswith('**'):
                    result['warnings'].append(f"Bridge '{bridge}' не существует на ноде {node}")
            except Exception as e:
                result['warnings'].append(f"Ошибка проверки bridge '{bridge}': {e}")

        return result

    def get_network_statistics(self, node: str) -> Dict[str, Any]:
        """
        Получить статистику сетевой конфигурации ноды

        Args:
            node: Нода для анализа

        Returns:
            Статистика сети
        """
        stats = {
            'total_bridges': 0,
            'system_bridges': [],
            'user_bridges': [],
            'available_bridges': []
        }

        try:
            bridges = self.proxmox.list_bridges(node)

            for bridge in bridges:
                if bridge in ['vmbr0']:  # Системные bridge'ы
                    stats['system_bridges'].append(bridge)
                else:
                    stats['user_bridges'].append(bridge)

            stats['total_bridges'] = len(bridges)

        except Exception as e:
            logger.error(f"Ошибка получения статистики сети для ноды {node}: {e}")

        return stats

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
            try:
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
                            logger.info(f"Удален неиспользуемый bridge {bridge} на ноде {node}")

            except Exception as e:
                logger.error(f"Ошибка очистки bridge'ей на ноде {node}: {e}")

        return cleaned_count
