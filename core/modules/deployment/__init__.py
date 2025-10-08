"""
Модули развертывания виртуальных машин

Содержит реализации различных стратегий развертывания виртуальных машин
в кластере Proxmox VE.
"""

from .local_deployer import LocalDeployer
from .remote_deployer import RemoteDeployer
from .balanced_deployer import BalancedDeployer
from .smart_deployer import SmartDeployer

__all__ = [
    'LocalDeployer',
    'RemoteDeployer',
    'BalancedDeployer',
    'SmartDeployer'
]
