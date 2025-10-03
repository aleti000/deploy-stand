from typing import Dict, Any
import yaml
import os
from app.core.proxmox_manager import ProxmoxManager
from app.utils.logger import logger

class TemplateManager:
    """Управление шаблонами виртуальных машин"""

    def __init__(self, proxmox_manager: ProxmoxManager):
        self.proxmox = proxmox_manager
        self.local_templates: Dict[str, int] = {}  # Кэш для локальных шаблонов

    def save_local_templates_to_config(self, config_path: str = "data/deployment_config.yml") -> bool:
        """Сохранить информацию о локальных шаблонах в конфигурационный файл"""
        try:
            # Загружаем существующий конфиг
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
            else:
                config = {}

            # Добавляем или обновляем информацию о локальных шаблонах
            if 'local_templates' not in config:
                config['local_templates'] = {}

            for template_key, template_vmid in self.local_templates.items():
                original_vmid, target_node = template_key.split(':')
                config['local_templates'][template_key] = {
                    'vmid': template_vmid,
                    'node': target_node,
                    'original_vmid': original_vmid
                }

            # Сохраняем обновленный конфиг
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)

            return True

        except Exception as e:
            logger.error(f"Ошибка сохранения локальных шаблонов в конфиг: {e}")
            return False

    def load_local_templates_from_config(self, config_path: str = "data/deployment_config.yml") -> bool:
        """Загрузить информацию о локальных шаблонах из конфигурационного файла"""
        try:
            if not os.path.exists(config_path):
                return False

            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}

            local_templates_info = config.get('local_templates', {})

            # Загружаем информацию о локальных шаблонах
            for template_key, template_info in local_templates_info.items():
                if isinstance(template_info, dict):
                    vmid = template_info.get('vmid')
                    if vmid:
                        self.local_templates[template_key] = vmid
                else:
                    # Обратная совместимость со старым форматом
                    self.local_templates[template_key] = template_info

            return True

        except Exception as e:
            logger.error(f"Ошибка загрузки локальных шаблонов из конфига: {e}")
            return False

    def prepare_template_for_node(self, original_vmid: int, template_node: str,
                                 target_node: str) -> int | None:
        """Подготовить локальный шаблон для целевой ноды"""
        try:
            template_key = f"{original_vmid}:{target_node}"

            # Проверяем, существует ли уже локальный шаблон
            if template_key in self.local_templates:
                return self.local_templates[template_key]

            # Генерируем уникальный VMID для локального шаблона
            temp_vmid = self.proxmox.get_next_vmid()
            while not self.proxmox.check_vmid_unique(temp_vmid):
                temp_vmid += 1

            # Создаем локальный шаблон через миграцию
            template_create_ok = self.proxmox._create_local_template_via_migration(
                template_node=template_node,
                template_vmid=original_vmid,
                target_node=target_node,
                new_vmid=temp_vmid,
                name=f"template-{original_vmid}-{target_node}",
                pool=None
            )

            if template_create_ok:
                # Сохраняем информацию о локальном шаблоне
                self.local_templates[template_key] = temp_vmid
                return temp_vmid
            else:
                return None

        except Exception as e:
            logger.error(f"Ошибка подготовки шаблона: {e}")
            return None

    def get_template_for_node(self, original_vmid: int, target_node: str) -> int | None:
        """Получить VMID локального шаблона для целевой ноды"""
        template_key = f"{original_vmid}:{target_node}"
        return self.local_templates.get(template_key)

    def cleanup_template(self, original_vmid: int, target_node: str) -> bool:
        """Удалить локальный шаблон"""
        try:
            template_key = f"{original_vmid}:{target_node}"

            if template_key not in self.local_templates:
                return False

            template_vmid = self.local_templates[template_key]

            # Удаляем шаблон через Proxmox API
            if self.proxmox.delete_vm(target_node, template_vmid):
                # Удаляем из кэша
                del self.local_templates[template_key]
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"Ошибка удаления локального шаблона: {e}")
            return False
