#!/usr/bin/env python3
"""
Модуль клиента для работы с Proxmox API
Централизованное управление подключением и операциями с Proxmox
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from proxmoxer import ProxmoxAPI
import requests
from urllib3.exceptions import InsecureRequestWarning
import warnings

logger = logging.getLogger(__name__)


class ProxmoxClient:
    """Клиент для работы с Proxmox API"""

    def __init__(self, host: str, user: str, password: str = None, token_name: str = None,
                 token_value: str = None, port: int = 8006, verify_ssl: bool = False):
        """
        Инициализация клиента Proxmox

        Args:
            host: Адрес сервера Proxmox
            user: Имя пользователя (с realm, например: root@pam)
            password: Пароль пользователя
            token_name: Имя токена API (если используется токен)
            token_value: Значение токена API
            port: Порт API сервера (по умолчанию 8006)
            verify_ssl: Проверять SSL сертификат
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.token_name = token_name
        self.token_value = token_value
        self.verify_ssl = verify_ssl

        self.proxmox: Optional[ProxmoxAPI] = None
        self._connected = False
        self._version_info = None

    def connect(self) -> bool:
        """
        Установка подключения к Proxmox API

        Returns:
            bool: True если подключение успешно, False иначе
        """
        try:
            # Отключаем предупреждения SSL если верификация отключена
            if not self.verify_ssl:
                warnings.filterwarnings("ignore", category=InsecureRequestWarning)
                requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

            # Создаем подключение через proxmoxer
            if self.token_name and self.token_value:
                # Аутентификация по токену
                self.proxmox = ProxmoxAPI(
                    host=self.host,
                    user=self.user,
                    token_name=self.token_name,
                    token_value=self.token_value,
                    port=self.port,
                    verify_ssl=self.verify_ssl
                )
            else:
                # Аутентификация по паролю
                self.proxmox = ProxmoxAPI(
                    host=self.host,
                    user=self.user,
                    password=self.password,
                    port=self.port,
                    verify_ssl=self.verify_ssl
                )

            # Тестируем подключение
            self._version_info = self.proxmox.version.get()
            self._connected = True

            logger.info(f"Успешное подключение к Proxmox {self.host}:{self.port}")
            logger.info(f"Версия Proxmox: {self._version_info}")
            return True

        except Exception as e:
            logger.error(f"Ошибка подключения к Proxmox {self.host}:{self.port}: {e}")
            self._connected = False
            self.proxmox = None
            return False

    def disconnect(self):
        """Отключение от Proxmox API"""
        if self.proxmox:
            self.proxmox = None
            self._connected = False
            logger.info(f"Отключено от Proxmox {self.host}:{self.port}")

    def is_connected(self) -> bool:
        """Проверка статуса подключения"""
        return self._connected and self.proxmox is not None

    def get_version(self) -> Optional[Dict[str, Any]]:
        """Получение информации о версии Proxmox"""
        if not self.is_connected():
            return None
        return self._version_info

    def get_nodes(self) -> List[Dict[str, Any]]:
        """
        Получение списка узлов (nodes)

        Returns:
            List[Dict[str, Any]]: Список узлов с их информацией
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            nodes = self.proxmox.nodes.get()
            logger.debug(f"Получено {len(nodes)} узлов")
            return nodes
        except Exception as e:
            logger.error(f"Ошибка получения списка узлов: {e}")
            raise

    
    def get_vms(self, node_name: str) -> List[Dict[str, Any]]:
        """
        Получение списка виртуальных машин на узле

        Args:
            node_name: Имя узла

        Returns:
            List[Dict[str, Any]]: Список виртуальных машин
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            vms = self.proxmox.nodes(node_name).qemu.get()
            logger.debug(f"Получено {len(vms)} ВМ на узле {node_name}")
            return vms
        except Exception as e:
            logger.error(f"Ошибка получения списка ВМ на узле {node_name}: {e}")
            raise

    def get_vm_info(self, node_name: str, vmid: int) -> Dict[str, Any]:
        """
        Получение информации о виртуальной машине

        Args:
            node_name: Имя узла
            vmid: ID виртуальной машины

        Returns:
            Dict[str, Any]: Информация о ВМ
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            vm_info = self.proxmox.nodes(node_name).qemu(vmid).get()
            logger.debug(f"Получена информация о ВМ {vmid} на узле {node_name}")
            return vm_info
        except Exception as e:
            logger.error(f"Ошибка получения информации о ВМ {vmid}: {e}")
            raise

    def get_vm_status(self, node_name: str, vmid: int) -> Dict[str, Any]:
        """
        Получение статуса виртуальной машины

        Args:
            node_name: Имя узла
            vmid: ID виртуальной машины

        Returns:
            Dict[str, Any]: Статус ВМ
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            vm_status = self.proxmox.nodes(node_name).qemu(vmid).status.current.get()
            logger.debug(f"Получен статус ВМ {vmid} на узле {node_name}")
            return vm_status
        except Exception as e:
            logger.error(f"Ошибка получения статуса ВМ {vmid}: {e}")
            raise

    def start_vm(self, node_name: str, vmid: int) -> Dict[str, Any]:
        """
        Запуск виртуальной машины

        Args:
            node_name: Имя узла
            vmid: ID виртуальной машины

        Returns:
            Dict[str, Any]: Результат операции
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            result = self.proxmox.nodes(node_name).qemu(vmid).status.start.post()
            logger.info(f"Запущена ВМ {vmid} на узле {node_name}")
            return result
        except Exception as e:
            logger.error(f"Ошибка запуска ВМ {vmid}: {e}")
            raise

    def stop_vm(self, node_name: str, vmid: int) -> Dict[str, Any]:
        """
        Остановка виртуальной машины

        Args:
            node_name: Имя узла
            vmid: ID виртуальной машины

        Returns:
            Dict[str, Any]: Результат операции
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            result = self.proxmox.nodes(node_name).qemu(vmid).status.stop.post()
            logger.info(f"Остановлена ВМ {vmid} на узле {node_name}")
            return result
        except Exception as e:
            logger.error(f"Ошибка остановки ВМ {vmid}: {e}")
            raise

    def shutdown_vm(self, node_name: str, vmid: int) -> Dict[str, Any]:
        """
        Корректное выключение виртуальной машины

        Args:
            node_name: Имя узла
            vmid: ID виртуальной машины

        Returns:
            Dict[str, Any]: Результат операции
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            result = self.proxmox.nodes(node_name).qemu(vmid).status.shutdown.post()
            logger.info(f"Выключена ВМ {vmid} на узле {node_name}")
            return result
        except Exception as e:
            logger.error(f"Ошибка выключения ВМ {vmid}: {e}")
            raise

    def reboot_vm(self, node_name: str, vmid: int) -> Dict[str, Any]:
        """
        Перезагрузка виртуальной машины

        Args:
            node_name: Имя узла
            vmid: ID виртуальной машины

        Returns:
            Dict[str, Any]: Результат операции
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            result = self.proxmox.nodes(node_name).qemu(vmid).status.reboot.post()
            logger.info(f"Перезагружена ВМ {vmid} на узле {node_name}")
            return result
        except Exception as e:
            logger.error(f"Ошибка перезагрузки ВМ {vmid}: {e}")
            raise

    def create_vm(self, node_name: str, vm_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создание новой виртуальной машины

        Args:
            node_name: Имя узла
            vm_config: Конфигурация виртуальной машины

        Returns:
            Dict[str, Any]: Результат операции
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            result = self.proxmox.nodes(node_name).qemu.post(**vm_config)
            logger.info(f"Создана ВМ на узле {node_name} с конфигурацией: {vm_config}")
            return result
        except Exception as e:
            logger.error(f"Ошибка создания ВМ: {e}")
            raise

    def delete_vm(self, node_name: str, vmid: int) -> Dict[str, Any]:
        """
        Удаление виртуальной машины

        Args:
            node_name: Имя узла
            vmid: ID виртуальной машины

        Returns:
            Dict[str, Any]: Результат операции
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            result = self.proxmox.nodes(node_name).qemu(vmid).delete()
            logger.info(f"Удалена ВМ {vmid} на узле {node_name}")
            return result
        except Exception as e:
            logger.error(f"Ошибка удаления ВМ {vmid}: {e}")
            raise

    def get_storage(self, node_name: str) -> List[Dict[str, Any]]:
        """
        Получение списка хранилищ на узле

        Args:
            node_name: Имя узла

        Returns:
            List[Dict[str, Any]]: Список хранилищ
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            storage = self.proxmox.nodes(node_name).storage.get()
            logger.debug(f"Получено {len(storage)} хранилищ на узле {node_name}")
            return storage
        except Exception as e:
            logger.error(f"Ошибка получения списка хранилищ на узле {node_name}: {e}")
            raise

    def get_cluster_status(self) -> Dict[str, Any]:
        """
        Получение статуса кластера

        Returns:
            Dict[str, Any]: Статус кластера
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            cluster_status = self.proxmox.cluster.status.get()
            logger.debug("Получен статус кластера")
            return cluster_status
        except Exception as e:
            logger.error(f"Ошибка получения статуса кластера: {e}")
            raise

    def get_tasks(self, node_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Получение списка задач на узле

        Args:
            node_name: Имя узла
            limit: Максимальное количество задач для получения

        Returns:
            List[Dict[str, Any]]: Список задач
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            tasks = self.proxmox.nodes(node_name).tasks.get(limit=limit)
            logger.debug(f"Получено {len(tasks)} задач на узле {node_name}")
            return tasks
        except Exception as e:
            logger.error(f"Ошибка получения списка задач на узле {node_name}: {e}")
            raise

    def get_task_status(self, node_name: str, upid: str) -> Dict[str, Any]:
        """
        Получение статуса задачи

        Args:
            node_name: Имя узла
            upid: ID задачи (upid)

        Returns:
            Dict[str, Any]: Статус задачи
        """
        if not self.is_connected():
            raise ConnectionError("Не подключен к Proxmox API")

        try:
            task_status = self.proxmox.nodes(node_name).tasks(upid).status.get()
            logger.debug(f"Получен статус задачи {upid} на узле {node_name}")
            return task_status
        except Exception as e:
            logger.error(f"Ошибка получения статуса задачи {upid}: {e}")
            raise

    def wait_for_task_completion(self, node_name: str, upid: str, timeout: int = 300) -> Dict[str, Any]:
        """
        Ожидание завершения задачи

        Args:
            node_name: Имя узла
            upid: ID задачи (upid)
            timeout: Таймаут ожидания в секундах

        Returns:
            Dict[str, Any]: Финальный статус задачи
        """
        import time

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                task_status = self.get_task_status(node_name, upid)

                if task_status.get('status') == 'stopped':
                    logger.info(f"Задача {upid} завершена")
                    return task_status

                # Ждем 2 секунды перед следующей проверкой
                time.sleep(2)

            except Exception as e:
                logger.error(f"Ошибка при проверке статуса задачи {upid}: {e}")
                break

        logger.warning(f"Таймаут ожидания задачи {upid}")
        return {'status': 'timeout', 'upid': upid}

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'ProxmoxClient':
        """
        Создание клиента из конфигурации

        Args:
            config: Конфигурация подключения

        Returns:
            ProxmoxClient: Настроенный клиент
        """
        return cls(
            host=config.get('host', 'localhost'),
            port=config.get('port', 8006),
            user=config.get('user', 'root@pam'),
            password=config.get('password'),
            token_name=config.get('token_name'),
            token_value=config.get('token_value'),
            verify_ssl=config.get('verify_ssl', False)
        )


def create_proxmox_client(config: Dict[str, Any]) -> ProxmoxClient:
    """
    Фабричная функция для создания клиента Proxmox

    Args:
        config: Конфигурация подключения

    Returns:
        ProxmoxClient: Настроенный клиент
    """
    return ProxmoxClient.from_config(config)
