"""
НИЗКОУРОВНЕВЫЙ клиент для работы с Proxmox VE API

Предоставляет ТОЛЬКО сырые вызовы к Proxmox API:
- Аутентификация и подключение
- Базовые HTTP-запросы к API
- НЕ содержит бизнес-логики

БИЗНЕС-ЛОГИКА находится в сервисных модулях:
- NetworkManager - для сетевых операций
- UserManager - для управления пользователями
- VMManager - для управления виртуальными машинами
- Deployer'ы - для логики развертывания

АРХИТЕКТУРНОЕ ПРАВИЛО: Этот модуль НЕ должен содержать:
- Логику создания/управления bridge'ами
- Логику настройки сети VM
- Логику управления пользователями и пулами
- Логику получения конфигурации VM
"""

import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from proxmoxer import ProxmoxAPI

logger = logging.getLogger(__name__)


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
        """Установить соединение с Proxmox API"""
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
            logger.info(f"Успешное подключение к Proxmox {self.host}")

        except Exception as e:
            logger.error(f"Ошибка подключения к Proxmox {self.host}: {e}")
            raise

    def get_nodes(self) -> List[str]:
        """Получить список всех нод в кластере"""
        try:
            nodes = self.api.nodes.get()
            return [node['node'] for node in nodes]
        except Exception as e:
            logger.error(f"Ошибка получения списка нод: {e}")
            raise
