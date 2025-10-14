#!/usr/bin/env python3
"""
Менеджер сети
Отвечает за настройку сетевых адаптеров, управление bridge'ами и сетевую конфигурацию
"""

import logging
from typing import Dict, List, Any, Optional
from .proxmox_client import ProxmoxClient

# Импорт для совместимости
try:
    from .validator import ConfigValidator
    from .logger import Logger
except ImportError:
    # Fallback для обратной совместимости
    ConfigValidator = None
    Logger = None

logger = logging.getLogger(__name__)


class NetworkManager:
    """Менеджер сети для всех сетевых операций в Proxmox"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация менеджера сети

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def configure_machine_network(self, vmid: int, node: str, networks: List[Dict[str, Any]],
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
            # Используем готовый bridge mapping из кэша пользователя
            user_key = f"{node}:{pool}"
            if hasattr(self, '_global_bridge_cache') and user_key in self._global_bridge_cache:
                bridge_mapping = self._global_bridge_cache[user_key].get('bridge_mapping', {})
                logger.info(f"Используем готовый bridge mapping для пользователя {pool}: {bridge_mapping}")
            else:
                # Fallback: создаем mapping заново
                logger.warning(f"Bridge mapping не найден в кэше для пользователя {pool}, создаем заново")
                bridge_mapping = self._prepare_bridges_auto(node, networks, pool)

            # Подготовить конфигурации интерфейсов
            network_configs = self._prepare_network_configs(networks, bridge_mapping, device_type)

            # Пакетная настройка всех интерфейсов
            config_params = {}
            for net_id, net_config in network_configs.items():
                config_params[net_id] = net_config

            self.proxmox.api.nodes(node).qemu(vmid).config.post(**config_params)
            logger.info(f"Сетевые настройки для VM {vmid} применены через NetworkManager")
            return True

        except Exception as e:
            logger.error(f"Ошибка настройки сети для VM {vmid}: {e}")
            return False

    def configure_network(self, node: str, vmid: int, network_config: str, net_id: str = "net0") -> bool:
        """
        Настроить сетевой интерфейс VM

        Args:
            node: Нода размещения VM
            vmid: VMID машины
            network_config: Конфигурация сети
            net_id: ID сетевого интерфейса

        Returns:
            True если настройка успешна
        """
        try:
            success = self.proxmox.configure_vm_network_interface(node, vmid, net_id, network_config)
            if success:
                logger.info(f"✅ Сетевая конфигурация {net_id} для VM {vmid} настроена")
            else:
                logger.error(f"Не удалось настроить сеть {net_id} для VM {vmid}")
            return success
        except Exception as e:
            logger.error(f"Ошибка настройки сети {net_id} для VM {vmid}: {e}")
            return False

    def get_network_info(self, node: str, vmid: int) -> Dict[str, Any]:
        """
        Получить информацию о сетевой конфигурации VM

        Args:
            node: Нода размещения VM
            vmid: VMID машины

        Returns:
            Информация о сети VM
        """
        try:
            vm_info = self.proxmox.get_vm_config(node, vmid)
            network_info = {}

            if vm_info:
                # Извлечь сетевые интерфейсы (net0, net1, etc.)
                for key in vm_info:
                    if key.startswith('net'):
                        network_info[key] = vm_info[key]

            return network_info

        except Exception as e:
            logger.error(f"Ошибка получения сетевой информации VM {vmid}: {e}")
            return {}

    def reload_network(self, node: str) -> bool:
        """
        Перезагрузить сеть на ноде

        Args:
            node: Нода для перезагрузки сети

        Returns:
            True если перезагрузка успешна
        """
        try:
            # Реализуем reload сети в NetworkManager
            self.proxmox.api.nodes(node).network.put()
            logger.info(f"✅ Сеть ноды {node} перезагружена через NetworkManager")
            return True
        except Exception as e:
            logger.error(f"Ошибка перезагрузки сети ноды {node} в NetworkManager: {e}")
            return False

    def list_bridges(self, node: str) -> List[str]:
        """
        Получить список bridge'ов на ноде

        Args:
            node: Нода для проверки

        Returns:
            Список bridge'ов
        """
        try:
            # Реализуем через ProxmoxClient
            try:
                network_config = self.proxmox.api.nodes(node).network.get()
                bridges = []
                for iface in network_config:
                    if iface.get('type') == 'bridge':
                        bridges.append(iface.get('iface'))
                logger.debug(f"Найдено {len(bridges)} bridge'ов на ноде {node}")
                return bridges
            except Exception:
                # Fallback: использовать известные bridges по умолчанию
                return ['vmbr0']
        except Exception as e:
            logger.error(f"Ошибка получения списка bridge'ов на ноде {node}: {e}")
            return []

    def bridge_exists(self, node: str, bridge_name: str) -> bool:
        """
        Проверить существование bridge'а

        Args:
            node: Нода для проверки
            bridge_name: Имя bridge'а

        Returns:
            True если bridge существует
        """
        try:
            bridges = self.list_bridges(node)
            return bridge_name in bridges
        except Exception:
            return False

    def create_bridge(self, node: str, bridge_name: str) -> bool:
        """
        Создать bridge на ноде

        Args:
            node: Нода для создания bridge'а
            bridge_name: Имя bridge'а

        Returns:
            True если bridge создан успешно
        """
        try:
            # Реализуем создание bridge в NetworkManager
            bridge_config = {
                'iface': bridge_name,
                'type': 'bridge',
                'autostart': 1
            }

            self.proxmox.api.nodes(node).network.post(**bridge_config)
            logger.info(f"✅ Bridge {bridge_name} создан на ноде {node} через NetworkManager")
            return True
        except Exception as e:
            logger.error(f"Ошибка создания bridge {bridge_name} на ноде {node}: {e}")
            return False

    def delete_bridge(self, node: str, bridge_name: str) -> bool:
        """
        Удалить bridge с ноды

        Args:
            node: Нода для удаления bridge'а
            bridge_name: Имя bridge'а

        Returns:
            True если bridge удален успешно
        """
        try:
            success = self.proxmox.delete_bridge(node, bridge_name)
            if success:
                logger.info(f"✅ Bridge {bridge_name} удален с ноды {node}")
            else:
                logger.error(f"Не удалось удалить bridge {bridge_name} с ноды {node}")
            return success
        except Exception as e:
            logger.error(f"Ошибка удаления bridge {bridge_name} с ноды {node}: {e}")
            return False

    def bridge_in_use(self, node: str, bridge_name: str) -> bool:
        """
        Проверить, используется ли bridge

        Args:
            node: Нода для проверки
            bridge_name: Имя bridge'а

        Returns:
            True если bridge используется
        """
        try:
            # Получить список всех VM на ноде
            vms = self.proxmox.get_vms(node)

            for vm in vms:
                vm_info = self.get_network_info(node, vm.get('vmid'))
                for net_config in vm_info.values():
                    if bridge_name in net_config:
                        return True

            return False

        except Exception as e:
            logger.error(f"Ошибка проверки использования bridge {bridge_name} на ноде {node}: {e}")
            return False

    def _prepare_bridges_auto(self, node: str, networks: List[Dict[str, Any]], pool: str) -> Dict[str, str]:
        """
        Подготовить bridge'ы автоматически с учетом одинаковых alias

        Args:
            node: Нода размещения
            networks: Конфигурация сетей
            pool: Пул пользователя

        Returns:
            Mapping bridge имен (одинаковые alias -> один и тот же bridge)
        """
        bridge_mapping = {}

        # Глобальный кэш для всех пользователей и их alias
        if not hasattr(self, '_global_bridge_cache'):
            self._global_bridge_cache = {}

        # Создаем уникальный ключ для пользователя
        user_key = f"{node}:{pool}"

        if user_key not in self._global_bridge_cache:
            self._global_bridge_cache[user_key] = {}

        user_bridge_cache = self._global_bridge_cache[user_key]

        # Обрабатываем каждую сеть
        for network in networks:
            bridge_name = network.get('bridge')
            if bridge_name:
                # Обработка зарезервированных bridge (в двойных звездочках)
                if bridge_name.startswith('**'):
                    actual_bridge = bridge_name.strip('*')
                    if not self.bridge_exists(node, actual_bridge):
                        logger.info(f"Создаем зарезервированный bridge {actual_bridge} на ноде {node}")
                        self.create_bridge(node, actual_bridge)
                    bridge_mapping[bridge_name] = actual_bridge
                elif bridge_name.startswith('vmbr') or bridge_name.isdigit():
                    # Уже готовый bridge
                    if not self.bridge_exists(node, bridge_name):
                        logger.info(f"Автоматически создаем bridge {bridge_name} на ноде {node}")
                        self.create_bridge(node, bridge_name)
                    bridge_mapping[bridge_name] = bridge_name
                else:
                    # Это alias - должен быть одинаковым для пользователя
                    if bridge_name not in user_bridge_cache:
                        # Выделяем новый bridge для этого alias пользователя
                        allocated_bridge = self._allocate_bridge_auto(node, bridge_name, pool)
                        if not self.bridge_exists(node, allocated_bridge):
                            logger.info(f"Автоматически создаем bridge {allocated_bridge} для alias '{bridge_name}' пользователя {pool} на ноде {node}")
                            self.create_bridge(node, allocated_bridge)
                        user_bridge_cache[bridge_name] = allocated_bridge
                        logger.info(f"Пользователь {pool}: alias '{bridge_name}' -> bridge '{allocated_bridge}' (сохранено в кэш)")

                    # Используем bridge из кэша пользователя (одинаковый для одинаковых alias)
                    bridge_mapping[bridge_name] = user_bridge_cache[bridge_name]

        return bridge_mapping

    def _allocate_bridge_auto(self, node: str, bridge_name: str, pool: str) -> str:
        """
        Автоматическое выделение свободного bridge начиная с vmbr1000

        Args:
            node: Нода размещения
            bridge_name: ALIAS bridge'а (hq, inet, etc)
            pool: Пул пользователя (используется для определения области)

        Returns:
            Имя свободного bridge'а
        """
        bridge_alias = bridge_name.lower()

        # Определяем базовый номер для разных типов сетей
        if bridge_alias == 'hq':
            base_bridge = 1000
        elif bridge_alias == 'inet':
            base_bridge = 2000
        else:
            base_bridge = 9000

        # Ищем свободный bridge начиная с base_bridge
        bridge_number = base_bridge
        while True:
            candidate_bridge = f'vmbr{bridge_number:04d}'
            if not self.bridge_exists(node, candidate_bridge):
                logger.info(f"Найден свободный bridge {candidate_bridge} для alias '{bridge_name}'")
                return candidate_bridge
            bridge_number += 1

            # Защита от бесконечного цикла (максимум 100 попыток)
            if bridge_number > base_bridge + 100:
                logger.warning(f"Не удалось найти свободный bridge для {bridge_name}, используем fallback")
                return f'vmbr{base_bridge:04d}'

    def _allocate_bridge(self, node: str, bridge_name: str, pool: str) -> str:
        """
        Выделить bridge для сети (упрощенная версия без BridgeManager)

        Args:
            node: Нода размещения
            bridge_name: ALIAS bridge'а (hq, inet, etc)
            pool: Пул пользователя

        Returns:
            Имя выделенного bridge'а
        """
        # Для простоты - используем фиксированную схему именования
        # В будущем можно добавить BridgeManager для более сложной логики
        pool_suffix = pool[:4]  # Первые 4 символа пула
        bridge_alias = bridge_name.lower()

        if bridge_alias == 'hq':
            return f'vmbr100{pool_suffix}'
        elif bridge_alias == 'inet':
            return f'vmbr200{pool_suffix}'
        else:
            # Для неизвестных alias - использовать общий bridge
            return f'vmbr999{pool_suffix}'

    def _prepare_network_configs(self, networks: List[Dict[str, Any]], bridge_mapping: Dict[str, str],
                               device_type: str) -> Dict[str, str]:
        """
        Подготовить конфигурации сетевых интерфейсов

        Args:
            networks: Конфигурация сетей
            bridge_mapping: Mapping bridge имен
            device_type: Тип устройства

        Returns:
            Словарь конфигураций интерфейсов
        """
        network_configs = {}

        if device_type.lower() == 'ecorouter':
            # Специальная конфигурация для ecorouter
            network_configs['net0'] = 'model=vmxnet3,bridge=vmbr0,link_down=1'
            for i, network in enumerate(networks):
                bridge = bridge_mapping.get(network['bridge'])
                if not bridge:
                    continue
                net_id = f"net{i+2}"  # net2, net3, net4...
                network_configs[net_id] = f'model=vmxnet3,bridge={bridge}'

        else:
            # Стандартная конфигурация для Linux
            for i, network in enumerate(networks):
                bridge = bridge_mapping.get(network.get('bridge', ''))
                if not bridge:
                    bridge = 'vmbr0'  # fallback

                net_id = f"net{i}"  # net0, net1, net2...
                network_configs[net_id] = f'model=virtio,bridge={bridge},firewall=1'

        return network_configs

    def validate_network_config(self, networks: List[Dict[str, Any]], node: str) -> Dict[str, Any]:
        """
        Валидация сетевой конфигурации

        Args:
            networks: Конфигурация сетей
            node: Нода для проверки

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
            exists = self.bridge_exists(node, bridge)
            result['bridge_availability'][bridge] = exists

            if not exists and not bridge.startswith('**'):
                result['warnings'].append(f"Bridge '{bridge}' не существует на ноде {node}")

        return result
