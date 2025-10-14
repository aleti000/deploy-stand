"""
Менеджер шаблонов виртуальных машин

Предоставляет централизованное управление шаблонами для всех стратегий развертывания,
включая подготовку, миграцию и кеширование шаблонов.
"""

import logging
import os
import time
import yaml
from typing import Dict, List, Any, Optional
from core.proxmox.proxmox_client import ProxmoxClient
from core.modules.common.deployment_utils import DeploymentUtils

logger = logging.getLogger(__name__)


class TemplateManager:
    """Менеджер шаблонов виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация менеджера шаблонов

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client
        self.utils = DeploymentUtils()
        self.mapper_file = os.path.join('data', 'mapper_template.yml')

    def prepare_templates_for_target_node(self, config: Dict[str, Any], target_node: str) -> Dict[str, int]:
        """
        Подготовить шаблоны для целевой ноды

        Процесс:
        1. Full clone оригинального шаблона
        2. Преобразование в шаблон
        3. Миграция на целевую ноду

        Args:
            config: Конфигурация развертывания
            target_node: Целевая нода

        Returns:
            Mapping оригинальных VMID -> локальных VMID на целевой ноде
        """
        template_mapping = {}

        # Получить уникальные шаблоны из конфигурации
        unique_templates = self._get_unique_templates(config)

        logger.info(f"Подготовка {len(unique_templates)} уникальных шаблонов для ноды {target_node}")

        for template_key in unique_templates:
            try:
                original_vmid, template_node = template_key.split(':')
                original_vmid = int(original_vmid)

                # Проверить, есть ли уже подготовленный шаблон на целевой ноде
                local_template_vmid = self.find_existing_template_on_node(original_vmid, target_node)
                if local_template_vmid:
                    template_mapping[template_key] = local_template_vmid
                    logger.info(f"Найден существующий шаблон {local_template_vmid} на ноде {target_node}")
                    continue

                # Подготовить новый шаблон
                local_template_vmid = self.prepare_single_template(original_vmid, template_node, target_node)
                if local_template_vmid:
                    template_mapping[template_key] = local_template_vmid
                else:
                    raise Exception(f"Не удалось подготовить шаблон {template_key}")

            except Exception as e:
                logger.error(f"Ошибка подготовки шаблона {template_key}: {e}")
                raise

        return template_mapping

    def prepare_single_template(self, original_vmid: int, template_node: str, target_node: str) -> int:
        """
        Подготовить один шаблон для целевой ноды

        Args:
            original_vmid: VMID оригинального шаблона
            template_node: Нода где хранится оригинальный шаблон
            target_node: Целевая нода

        Returns:
            VMID подготовленного шаблона на целевой ноде
        """
        try:
            # 1. Full clone оригинального шаблона на той же ноде
            clone_vmid = self.utils.get_next_vmid(self.proxmox)
            clone_name = f"template-clone-{original_vmid}-{int(time.time())}"

            logger.info(f"Создание full clone VM {original_vmid} -> VM {clone_vmid}")
            clone_task = self.proxmox.clone_vm(
                template_node=template_node,
                template_vmid=original_vmid,
                target_node=template_node,  # Клонируем на той же ноде
                new_vmid=clone_vmid,
                name=clone_name,
                full_clone=True  # Важно: full clone для независимости
            )

            if not self.utils.wait_for_task_completion(self.proxmox, clone_task, template_node):
                raise Exception(f"Ошибка клонирования VM {clone_vmid}")

            # 2. Преобразовать в шаблон
            logger.info(f"Преобразование VM {clone_vmid} в шаблон")
            if not self.proxmox.convert_to_template(template_node, clone_vmid):
                raise Exception(f"Ошибка преобразования VM {clone_vmid} в шаблон")

            # 3. Миграция на целевую ноду (если ноды разные)
            if template_node != target_node:
                logger.info(f"Миграция шаблона VM {clone_vmid} с {template_node} на {target_node}")
                migrate_task = self.proxmox.migrate_vm(
                    source_node=template_node,
                    target_node=target_node,
                    vmid=clone_vmid,
                    online=False  # Шаблоны миграируем offline
                )

                if not self.utils.wait_for_task_completion(self.proxmox, migrate_task, template_node):
                    raise Exception(f"Ошибка миграции VM {clone_vmid}")

            logger.info(f"Шаблон VM {clone_vmid} подготовлен на ноде {target_node}")

            # Обновить mapper_template
            self.update_template_mapper(original_vmid, target_node, clone_vmid)

            return clone_vmid

        except Exception as e:
            logger.error(f"Ошибка подготовки шаблона VM {original_vmid}: {e}")
            # Попытка очистки в случае ошибки
            try:
                if 'clone_vmid' in locals():
                    self.proxmox.delete_vm(template_node, clone_vmid)
            except:
                pass
            raise

    def find_existing_template_on_node(self, original_vmid: int, node: str) -> Optional[int]:
        """
        Найти существующий подготовленный шаблон на ноде

        Сначала проверяет API, затем mapper_template как кэш

        Args:
            original_vmid: VMID оригинального шаблона
            node: Нода для поиска

        Returns:
            VMID найденного шаблона или None
        """
        try:
            # 1. Сначала проверить через API (основной метод)
            vms = self.proxmox.get_vms_on_node(node)
            for vm in vms:
                vm_name = vm.get('name', '')
                if vm_name.startswith(f"template-clone-{original_vmid}-") and vm.get('template', 0) == 1:
                    found_vmid = int(vm['vmid'])
                    logger.info(f"Найден существующий шаблон {found_vmid} через API для {original_vmid} на {node}")
                    # Обновить mapper_template с актуальной информацией
                    self.update_template_mapper(original_vmid, node, found_vmid)
                    return found_vmid

            # 2. Проверить mapper_template только если API ничего не нашел
            mapper_data = self.load_template_mapper()
            template_mapping = mapper_data.get('template_mapping', {})
            original_mapping = template_mapping.get(original_vmid, {})
            local_vmid = original_mapping.get(node)

            if local_vmid:
                logger.warning(f"Шаблон {local_vmid} найден в mapper_template, но отсутствует в API для {original_vmid} на {node}")
                logger.info("Будет создан новый шаблон")
                # Удалить устаревшую запись из mapper_template
                if node in original_mapping:
                    del original_mapping[node]
                    self.save_template_mapper(mapper_data)

            return None
        except Exception as e:
            logger.warning(f"Ошибка поиска существующего шаблона: {e}")
            return None

    def load_template_mapper(self) -> Dict[str, Any]:
        """
        Загрузить mapper_template из файла

        Returns:
            Данные из mapper_template.yml
        """
        try:
            if os.path.exists(self.mapper_file):
                with open(self.mapper_file, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            else:
                logger.warning("Файл mapper_template.yml не найден, создаем пустой")
                return {}
        except Exception as e:
            logger.error(f"Ошибка загрузки mapper_template.yml: {e}")
            return {}

    def save_template_mapper(self, data: Dict[str, Any]) -> None:
        """
        Сохранить mapper_template в файл

        Args:
            data: Данные для сохранения
        """
        try:
            os.makedirs(os.path.dirname(self.mapper_file), exist_ok=True)
            with open(self.mapper_file, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            logger.info("mapper_template.yml сохранен")
        except Exception as e:
            logger.error(f"Ошибка сохранения mapper_template.yml: {e}")

    def update_template_mapper(self, original_vmid: int, node: str, local_vmid: int) -> None:
        """
        Обновить mapper_template с новой информацией о шаблоне

        Args:
            original_vmid: VMID оригинального шаблона
            node: Нода размещения
            local_vmid: VMID локального шаблона
        """
        try:
            mapper_data = self.load_template_mapper()
            template_mapping = mapper_data.setdefault('template_mapping', {})

            original_mapping = template_mapping.setdefault(original_vmid, {})
            original_mapping[node] = local_vmid

            self.save_template_mapper(mapper_data)
            logger.info(f"mapper_template обновлен: {original_vmid} -> {node}:{local_vmid}")
        except Exception as e:
            logger.error(f"Ошибка обновления mapper_template: {e}")

    def cleanup_unused_templates(self, nodes: List[str]) -> int:
        """
        Очистить неиспользуемые шаблоны

        Args:
            nodes: Список нод для очистки

        Returns:
            Количество очищенных шаблонов
        """
        cleaned_count = 0

        for node in nodes:
            try:
                vms = self.proxmox.get_vms_on_node(node)
                templates = [vm for vm in vms if vm.get('template', 0) == 1]

                for template in templates:
                    vmid = template.get('vmid')
                    name = template.get('name', '')

                    # Пропустить системные шаблоны
                    if name.startswith('template-clone-'):
                        # Проверить использование шаблона в mapper
                        mapper_data = self.load_template_mapper()
                        template_mapping = mapper_data.get('template_mapping', {})

                        # Если шаблон не используется ни в одном mapping, удалить
                        is_used = False
                        for original_vmid, node_mappings in template_mapping.items():
                            if isinstance(node_mappings, dict) and node in node_mappings:
                                if node_mappings[node] == vmid:
                                    is_used = True
                                    break

                        if not is_used:
                            if self.proxmox.delete_vm(node, vmid):
                                cleaned_count += 1
                                logger.info(f"Удален неиспользуемый шаблон {vmid} на ноде {node}")
                            else:
                                logger.error(f"Не удалось удалить шаблон {vmid} на ноде {node}")

            except Exception as e:
                logger.error(f"Ошибка очистки шаблонов на ноде {node}: {e}")

        return cleaned_count

    def get_template_statistics(self, nodes: List[str]) -> Dict[str, Any]:
        """
        Получить статистику по шаблонам

        Args:
            nodes: Список нод для анализа

        Returns:
            Статистика по шаблонам
        """
        stats = {
            'total_templates': 0,
            'templates_by_node': {},
            'unused_templates': 0,
            'template_sizes': {}
        }

        try:
            for node in nodes:
                node_templates = 0
                node_stats = {'total': 0, 'unused': 0}

                vms = self.proxmox.get_vms_on_node(node)
                templates = [vm for vm in vms if vm.get('template', 0) == 1]

                node_stats['total'] = len(templates)
                stats['total_templates'] += len(templates)

                # Анализ использования шаблонов
                mapper_data = self.load_template_mapper()
                template_mapping = mapper_data.get('template_mapping', {})

                for template in templates:
                    vmid = template.get('vmid')
                    name = template.get('name', '')

                    if name.startswith('template-clone-'):
                        # Проверить использование в mapper
                        is_used = False
                        for original_vmid, node_mappings in template_mapping.items():
                            if isinstance(node_mappings, dict) and node in node_mappings:
                                if node_mappings[node] == vmid:
                                    is_used = True
                                    break

                        if not is_used:
                            node_stats['unused'] += 1
                            stats['unused_templates'] += 1

                stats['templates_by_node'][node] = node_stats

        except Exception as e:
            logger.error(f"Ошибка получения статистики шаблонов: {e}")

        return stats

    def _get_unique_templates(self, config: Dict[str, Any]) -> set:
        """
        Получить уникальные шаблоны из конфигурации

        Args:
            config: Конфигурация развертывания

        Returns:
            Множество уникальных шаблонов в формате "vmid:node"
        """
        unique_templates = set()

        for machine_config in config.get('machines', []):
            template_key = f"{machine_config['template_vmid']}:{machine_config['template_node']}"
            unique_templates.add(template_key)

        return unique_templates

    def validate_template_availability(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Проверить доступность всех шаблонов в конфигурации

        Args:
            config: Конфигурация развертывания

        Returns:
            Результат проверки доступности шаблонов
        """
        result = {
            'available': [],
            'missing': [],
            'inaccessible': []
        }

        try:
            unique_templates = self._get_unique_templates(config)

            for template_key in unique_templates:
                original_vmid, template_node = template_key.split(':')
                original_vmid = int(original_vmid)

                try:
                    # Проверить доступность ноды
                    nodes = self.proxmox.get_nodes()
                    if template_node not in nodes:
                        result['inaccessible'].append({
                            'template_key': template_key,
                            'reason': f'Нода {template_node} недоступна'
                        })
                        continue

                    # Проверить существование шаблона
                    vms = self.proxmox.get_vms_on_node(template_node)
                    template_exists = any(
                        vm.get('vmid') == original_vmid and vm.get('template', 0) == 1
                        for vm in vms
                    )

                    if template_exists:
                        result['available'].append(template_key)
                    else:
                        result['missing'].append({
                            'template_key': template_key,
                            'reason': f'Шаблон VM {original_vmid} не найден на ноде {template_node}'
                        })

                except Exception as e:
                    result['inaccessible'].append({
                        'template_key': template_key,
                        'reason': f'Ошибка доступа: {e}'
                    })

        except Exception as e:
            logger.error(f"Ошибка проверки доступности шаблонов: {e}")

        return result
