#!/usr/bin/env python3
"""
Клиент для работы с Proxmox VE API - упрощенная версия

Предоставляет базовый интерфейс для подключения и получения списка нод.
"""

import logging
from typing import List, Any, Optional
from proxmoxer import ProxmoxAPI


class ProxmoxClient:
    """Клиент для работы с Proxmox VE API"""

    def __init__(self, host: str, user: str, password: str = None, token_name: str = None, token_value: str = None):
        """
        Инициализация клиента Proxmox

        Args:
            host: Адрес сервера Proxmox (например, "192.168.1.100:8006")
            user: Имя пользователя (например, "root@pam")
            password: Пароль пользователя
            token_name: Имя токена (если используется аутентификация по токену)
            token_value: Значение токена
        """
        self.host = host
        self.user = user
        self.password = password
        self.token_name = token_name
        self.token_value = token_value
        self.api = None
        self._connect()

    def _connect(self):
        """
        Установить соединение с Proxmox API

        Returns:
            True если соединение установлено успешно
        """
        try:
            if self.token_name and self.token_value:
                # Аутентификация по токену
                self.api = ProxmoxAPI(
                    self.host,
                    user=self.user,
                    token_name=self.token_name,
                    token_value=self.token_value,
                    verify_ssl=False
                )
            elif self.password:
                # Аутентификация по паролю
                self.api = ProxmoxAPI(
                    self.host,
                    user=self.user,
                    password=self.password,
                    verify_ssl=False
                )
            else:
                raise ValueError("Не указаны данные для аутентификации")

            # Проверка соединения
            self.api.version.get()
            return True

        except Exception as e:
            logging.error(f"Ошибка подключения к Proxmox {self.host}: {e}")
            return False

    def get_nodes(self) -> List[str]:
        """
        Получить список всех нод в кластере

        Returns:
            Список имен нод
        """
        try:
            nodes = self.api.nodes.get()
            return [node['node'] for node in nodes]
        except Exception as e:
            logging.error(f"Ошибка получения списка нод: {e}")
            return []

    def get_vms(self, node: str) -> List[dict]:
        """
        Получить список всех ВМ на указанной ноде

        Args:
            node: Имя ноды

        Returns:
            Список словарей с информацией о ВМ
        """
        try:
            vms = self.api.nodes(node).qemu.get()
            return vms
        except Exception as e:
            logging.error(f"Ошибка получения списка ВМ для ноды {node}: {e}")
            return []
