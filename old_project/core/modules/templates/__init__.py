"""
Модули управления шаблонами

Содержит реализации различных стратегий управления шаблонами виртуальных машин
в кластере Proxmox VE.
"""

from .local_templates import LocalTemplateManager
from .migration_templates import MigrationTemplateManager

__all__ = [
    'LocalTemplateManager',
    'MigrationTemplateManager'
]
