"""
Модули развертывания виртуальных машин

Содержит реализации различных стратегий развертывания виртуальных машин
в кластере Proxmox VE.
"""

from .basic_deployer import BasicDeployer
from .advanced_deployer import AdvancedDeployer
from .local_deployer import LocalDeployer
from .remote_deployer import RemoteDeployer
from .balanced_deployer import BalancedDeployer
from .smart_deployer import SmartDeployer

__all__ = [
    'BasicDeployer',
    'AdvancedDeployer',
    'LocalDeployer',
    'RemoteDeployer',
    'BalancedDeployer',
    'SmartDeployer'
]
