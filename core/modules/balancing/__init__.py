"""
Модули балансировки нагрузки

Содержит реализации различных стратегий распределения виртуальных машин
по нодам кластера Proxmox VE.
"""

from .simple_balancer import SimpleBalancer
from .smart_balancer import SmartBalancer

__all__ = [
    'SimpleBalancer',
    'SmartBalancer'
]
