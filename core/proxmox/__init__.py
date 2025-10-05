"""
Модуль Proxmox API

Предоставляет интерфейс для работы с Proxmox VE API через библиотеку proxmoxer.
"""

from .proxmox_client import ProxmoxClient
from .api_wrapper import ProxmoxAPIWrapper

__all__ = [
    'ProxmoxClient',
    'ProxmoxAPIWrapper'
]
