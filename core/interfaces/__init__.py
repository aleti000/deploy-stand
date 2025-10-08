"""
Интерфейсы модулей системы Deploy-Stand

Определяют контракты между модулями для обеспечения модульности и тестируемости.
"""

from .deployment_interface import DeploymentInterface
from .balancing_interface import BalancingInterface

__all__ = [
    'DeploymentInterface',
    'BalancingInterface'
]
