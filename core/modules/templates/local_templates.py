"""
Модуль управления локальными шаблонами виртуальных машин

Реализует стратегию создания и управления локальными шаблонами на каждой ноде
для оптимизации производительности развертывания.
"""

import logging
from typing import Dict, List, Any
from core.interfaces.template_interface import TemplateInterface
from core.proxmox.proxmox_client import ProxmoxClient
from utils.caching.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class LocalTemplateManager(TemplateInterface):
    """Управление локальными шаблонами виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient, cache: CacheManager):
        """
        Инициализация менеджера локальных шаблонов

        Args:
            proxmox_client: Клиент для работы с Proxmox API
            cache: Кеш менеджер
        """
        self.proxmox = proxmox_client
        self.cache = cache
        self.local_templates = {}  # Кеш локальных шаблонов

    def prepare_templates_for_target_node(self, config: Dict[str, Any],
                                        node_selection: str, target_node: str) -> bool:
        """
        Подготовить шаблоны для целевой ноды

        Args:
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды
            target_node: Целевая нода

        Returns:
            True если подготовка успешна
        """
        try:
            # Загрузить существующие локальные шаблоны
            self._load_local_templates_from_config()

            # Определить требуемые шаблоны
            required_templates = self._analyze_template_requirements(config, node_selection, target_node)

            # Подготовить недостающие шаблоны
            for template_key, template_info in required_templates.items():
                if not self._is_template_available(template_key, target_node):
                    success = self.create_local_template(
                        template_info['template_node'],
                        template_info['template_vmid'],
                        target_node,
                        template_info['new_vmid']
                    )
                    if not success:
                        return False

            # Сохранить mapping шаблонов
            self._save_template_mapping()
            return True

        except Exception as e:
            logger.error(f"Ошибка подготовки шаблонов: {e}")
            return False

    def create_local_template(self, template_node: str, template_vmid: int,
                            target_node: str, new_vmid: int) -> bool:
        """
        Создать локальный шаблон на целевой ноде

        Args:
            template_node: Нода где находится оригинальный шаблон
            template_vmid: VMID оригинального шаблона
            target_node: Целевая нода
            new_vmid: VMID нового локального шаблона

        Returns:
            True если создание успешно
        """
        try:
            # Проверка ресурсов перед миграцией
            if not self._check_migration_resources(template_node, target_node):
                return False

            # Проверка существования локального шаблона в кеше
            cache_key = f"{template_vmid}:{target_node}"
            if self._check_template_cache(cache_key, new_vmid):
                return True

            # Создать полный клон на исходной ноде
            clone_task = self.proxmox.clone_vm(
                template_node=template_node,
                template_vmid=template_vmid,
                target_node=template_node,
                new_vmid=new_vmid,
                name=f"template-{template_vmid}-{target_node}",
                full_clone=True
            )

            # Преобразовать в шаблон
            if not self.proxmox.wait_for_task(clone_task, template_node):
                return False

            self.proxmox.convert_to_template(template_node, new_vmid)

            # Миграция на целевую ноду если необходимо
            if template_node != target_node:
                migration_task = self.proxmox.migrate_vm(template_node, new_vmid, target_node)
                if not self.proxmox.wait_for_task(migration_task, template_node):
                    # Откат
                    self.proxmox.delete_vm(template_node, new_vmid)
                    return False

            # Сохранить в кеш
            self.local_templates[cache_key] = new_vmid

            logger.info(f"Локальный шаблон {new_vmid} создан на ноде {target_node}")
            return True

        except Exception as e:
            logger.error(f"Ошибка создания локального шаблона: {e}")
            return False

    def get_template_mapping(self) -> Dict[str, int]:
        """Получить mapping локальных шаблонов"""
        return self.local_templates.copy()

    def _load_local_templates_from_config(self):
        """Загрузить существующие локальные шаблоны из конфигурации"""
        # Заглушка - в реальности здесь должна быть логика загрузки из файла конфигурации
        pass

    def _analyze_template_requirements(self, config: Dict[str, Any],
                                     node_selection: str, target_node: str) -> Dict[str, Dict]:
        """
        Определить требуемые шаблоны

        Args:
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды
            target_node: Целевая нода

        Returns:
            Словарь требуемых шаблонов
        """
        required_templates = {}

        if 'machines' not in config:
            return required_templates

        for machine in config['machines']:
            template_vmid = machine.get('template_vmid')
            template_node = machine.get('template_node', target_node)

            if template_vmid:
                template_key = f"{template_vmid}:{target_node}"
                new_vmid = self.proxmox.get_next_vmid()

                required_templates[template_key] = {
                    'template_node': template_node,
                    'template_vmid': template_vmid,
                    'target_node': target_node,
                    'new_vmid': new_vmid
                }

        return required_templates

    def _is_template_available(self, template_key: str, target_node: str) -> bool:
        """Проверить доступность шаблона на целевой ноде"""
        # Проверить кеш локальных шаблонов
        if template_key in self.local_templates:
            return True

        # Заглушка - в реальности здесь должна быть проверка через Proxmox API
        return False

    def _check_migration_resources(self, template_node: str, target_node: str) -> bool:
        """Проверить ресурсы перед миграцией"""
        # Заглушка - в реальности здесь должна быть проверка ресурсов нод
        return True

    def _check_template_cache(self, cache_key: str, vmid: int) -> bool:
        """Проверить кеш локальных шаблонов"""
        if cache_key in self.local_templates:
            cached_vmid = self.local_templates[cache_key]
            return cached_vmid == vmid
        return False

    def _save_template_mapping(self):
        """Сохранить mapping локальных шаблонов"""
        # Заглушка - в реальности здесь должна быть логика сохранения в файл
        pass

    def convert_to_template(self, node: str, vmid: int) -> bool:
        """
        Преобразовать виртуальную машину в шаблон

        Args:
            node: Нода размещения
            vmid: VMID машины

        Returns:
            True если преобразование успешно
        """
        try:
            # Заглушка - в реальности здесь должен быть вызов Proxmox API
            logger.info(f"VM {vmid} преобразована в шаблон на ноде {node}")
            return True
        except Exception as e:
            logger.error(f"Ошибка преобразования в шаблон: {e}")
            return False

    def migrate_vm(self, source_node: str, vmid: int, target_node: str) -> bool:
        """
        Мигрировать виртуальную машину

        Args:
            source_node: Исходная нода
            vmid: VMID машины
            target_node: Целевая нода

        Returns:
            True если миграция успешна
        """
        try:
            # Заглушка - в реальности здесь должен быть вызов Proxmox API
            logger.info(f"VM {vmid} мигрирована с {source_node} на {target_node}")
            return True
        except Exception as e:
            logger.error(f"Ошибка миграции VM: {e}")
            return False
