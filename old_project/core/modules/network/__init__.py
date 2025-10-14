"""
Модули управления сетью

Содержит реализации различных стратегий настройки сети виртуальных машин
в кластере Proxmox VE.
"""

from .bridge_manager import BridgeManager

__all__ = [
    'BridgeManager'
]
