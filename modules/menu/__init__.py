#!/usr/bin/env python3
"""
Пакет модулей меню системы развертывания стендов ВМ
"""

# Экспортируем основные классы для удобного импорта
from .base_menu import BaseMenu
from .user_management import UserManagementMenu, get_user_management_menu
from .server_management import ServerManagementMenu, get_server_management_menu

__all__ = [
    'BaseMenu',
    'UserManagementMenu',
    'ServerManagementMenu',
    'get_user_management_menu',
    'get_server_management_menu'
]
