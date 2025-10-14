"""
Модуль миграции шаблонов виртуальных машин

Реализует стратегию миграции шаблонов между нодами кластера
для оптимизации развертывания виртуальных машин.
"""

import logging
from typing import Dict, List, Any
from core.interfaces.template_interface import TemplateInterface
from core.proxmox.proxmox_client import ProxmoxClient
from utils.caching.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class MigrationTemplateManager(TemplateInterface):
    """Управление миграцией шаблонов виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient, cache: CacheManager):
        """
        Инициализация менеджера миграции шаблонов

        Args:
            proxmox_client: Клиент для работы с Proxmox API
            cache: Кеш менеджер
        """
        self.proxmox = proxmox_client
        self.cache = cache
        self.migration_cache = {}  # Кеш мигрированных шаблонов

    def prepare_templates_for_target_node(self, config: Dict[str, Any],
                                        node_selection: str, target_node: str) -> bool:
        """
        Подготовить шаблоны для целевой ноды через миграцию

        Args:
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды
            target_node: Целевая нода

        Returns:
            True если подготовка успешна
        """
        try:
            # Загрузить существующие миграции шаблонов
            self._load_migration_cache()

            # Определить требуемые шаблоны
            required_templates = self._analyze_template_requirements(config, node_selection, target_node)

            # Выполнить миграции недостающих шаблонов
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

            # Сохранить кеш миграций
            self._save_migration_cache()
            return True

        except Exception as e:
            logger.error(f"Ошибка подготовки шаблонов через миграцию: {e}")
            return False

    def create_local_template(self, template_node: str, template_vmid: int,
                            target_node: str, new_vmid: int) -> bool:
        """
        Создать локальный шаблон через миграцию

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
            if not self._check_migration_feasibility(template_node, target_node):
                return False

            # Проверка кеша миграций
            cache_key = f"{template_vmid}:{template_node}:{target_node}"
            if self._check_migration_cache(cache_key, new_vmid):
                return True

            # Создать полный клон на исходной ноде
            clone_task = self.proxmox.clone_vm(
                template_node=template_node,
                template_vmid=template_vmid,
                target_node=template_node,
                new_vmid=new_vmid,
                name=f"migration-template-{template_vmid}-{target_node}",
                full_clone=True
            )

            # Преобразовать в шаблон
            if not self.proxmox.wait_for_task(clone_task, template_node):
                return False

            self.proxmox.convert_to_template(template_node, new_vmid)

            # Миграция на целевую ноду
            if template_node != target_node:
                migration_task = self.proxmox.migrate_vm(template_node, new_vmid, target_node)
                if not self.proxmox.wait_for_task(migration_task, template_node):
                    # Откат
                    self.proxmox.delete_vm(template_node, new_vmid)
                    return False

            # Сохранить в кеш миграций
            self.migration_cache[cache_key] = {
                'new_vmid': new_vmid,
                'migration_time': time.time()
            }

            logger.info(f"Шаблон {template_vmid} мигрирован с {template_node} на {target_node}")
            return True

        except Exception as e:
            logger.error(f"Ошибка миграции шаблона: {e}")
            return False

    def get_template_mapping(self) -> Dict[str, int]:
        """Получить mapping мигрированных шаблонов"""
        return {key: value['new_vmid'] for key, value in self.migration_cache.items()}

    def _load_migration_cache(self):
        """Загрузить кеш миграций шаблонов"""
        # Заглушка - в реальности здесь должна быть логика загрузки из файла
        pass

    def _save_migration_cache(self):
        """Сохранить кеш миграций шаблонов"""
        # Заглушка - в реальности здесь должна быть логика сохранения в файл
        pass

    def _analyze_template_requirements(self, config: Dict[str, Any],
                                     node_selection: str, target_node: str) -> Dict[str, Dict]:
        """
        Определить требуемые шаблоны для миграции

        Args:
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды
            target_node: Целевая нода

        Returns:
            Словарь требуемых шаблонов для миграции
        """
        required_templates = {}

        if 'machines' not in config:
            return required_templates

        for machine in config['machines']:
            template_vmid = machine.get('template_vmid')
            template_node = machine.get('template_node', target_node)

            if template_vmid and template_node != target_node:
                template_key = f"{template_vmid}:{template_node}:{target_node}"
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
        # Проверить кеш миграций
        if template_key in self.migration_cache:
            return True

        # Заглушка - в реальности здесь должна быть проверка через Proxmox API
        return False

    def _check_migration_feasibility(self, template_node: str, target_node: str) -> bool:
        """Проверить возможность миграции между нодами"""
        try:
            # Проверить доступность нод
            nodes = self.proxmox.get_nodes()
            if template_node not in nodes or target_node not in nodes:
                return False

            # Проверить сетевую связанность (заглушка)
            # В реальности здесь должна быть проверка сети между нодами

            return True

        except Exception as e:
            logger.error(f"Ошибка проверки возможности миграции: {e}")
            return False

    def _check_migration_cache(self, cache_key: str, vmid: int) -> bool:
        """Проверить кеш миграций шаблонов"""
        if cache_key in self.migration_cache:
            cached_info = self.migration_cache[cache_key]
            return cached_info['new_vmid'] == vmid
        return False

    def get_migration_history(self) -> List[Dict[str, Any]]:
        """Получить историю миграций шаблонов"""
        history = []

        for cache_key, migration_info in self.migration_cache.items():
            template_vmid, template_node, target_node = cache_key.split(':')

            history.append({
                'template_vmid': int(template_vmid),
                'template_node': template_node,
                'target_node': target_node,
                'new_vmid': migration_info['new_vmid'],
                'migration_time': migration_info['migration_time']
            })

        return history

    def cleanup_old_migrations(self, max_age_hours: int = 24) -> int:
        """
        Очистить старые миграции шаблонов

        Args:
            max_age_hours: Максимальный возраст миграции в часах

        Returns:
            Количество очищенных миграций
        """
        import time

        current_time = time.time()
        max_age_seconds = max_age_hours * 3600

        cleaned_count = 0
        keys_to_remove = []

        for cache_key, migration_info in self.migration_cache.items():
            migration_time = migration_info['migration_time']

            if current_time - migration_time > max_age_seconds:
                keys_to_remove.append(cache_key)
                cleaned_count += 1

        # Удалить старые записи
        for key in keys_to_remove:
            del self.migration_cache[key]

        if cleaned_count > 0:
            logger.info(f"Очищено {cleaned_count} старых миграций шаблонов")
            self._save_migration_cache()

        return cleaned_count
