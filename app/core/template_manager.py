from typing import Dict, Any
import yaml
import os
from app.core.proxmox_manager import ProxmoxManager
from app.utils.logger import logger

# Путь к файлу конфигурации соответствия шаблонов
TEMPLATE_MAPPING_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'template_mapping.yml')

class TemplateManager:
    """Управление шаблонами виртуальных машин"""

    _instance = None

    def __init__(self, proxmox_manager: ProxmoxManager):
        self.proxmox = proxmox_manager
        self.local_templates: Dict[str, int] = {}  # Кэш для локальных шаблонов
        self.template_mapping: Dict[str, Dict[str, int]] = {}  # Соответствие шаблонов между нодами

    @classmethod
    def get_instance(cls, proxmox_manager: ProxmoxManager = None):
        """Получить singleton экземпляр TemplateManager"""
        if cls._instance is None:
            if proxmox_manager is None:
                raise ValueError("Для создания первого экземпляра TemplateManager нужен proxmox_manager")
            cls._instance = cls(proxmox_manager)
        elif proxmox_manager is not None:
            # Обновляем proxmox_manager в существующем экземпляре если передан новый
            cls._instance.proxmox = proxmox_manager
        return cls._instance

    def save_local_templates_to_config(self, config_path: str = "data/deployment_config.yml") -> bool:
        """Сохранить информацию о локальных шаблонах в конфигурационный файл (устаревшая функция)"""
        logger.warning("save_local_templates_to_config устарела. Используйте save_template_mapping()")
        return self.save_template_mapping()

    def load_local_templates_from_config(self, config_path: str = "data/deployment_config.yml") -> bool:
        """Загрузить информацию о локальных шаблонах из конфигурационного файла (устаревшая функция)"""
        logger.warning("load_local_templates_from_config устарела. Используйте load_template_mapping()")
        return self.load_template_mapping()

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
        """Получить VMID локального шаблона для целевой ноды из template_mapping"""
        # Ищем только в template_mapping (local_templates устарел)
        return self.get_mapped_template(original_vmid, target_node)

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

    def save_template_mapping(self) -> bool:
        """Сохранить соответствие шаблонов между нодами в отдельный файл"""
        try:
            # Создаем структуру данных для сохранения
            mapping_data = {
                'template_mapping': {},
                'metadata': {
                    'created_by': 'Proxmox Deployer',
                    'version': '1.0',
                    'description': 'Автоматически созданное соответствие шаблонов между нодами кластера'
                }
            }

            # Группируем шаблоны по оригинальному VMID для template_mapping
            for template_key, local_vmid in self.local_templates.items():
                original_vmid, target_node = template_key.split(':')
                original_vmid = int(original_vmid)

                if original_vmid not in mapping_data['template_mapping']:
                    mapping_data['template_mapping'][original_vmid] = {}

                mapping_data['template_mapping'][original_vmid][target_node] = local_vmid

            # Сохраняем в файл
            os.makedirs(os.path.dirname(TEMPLATE_MAPPING_FILE), exist_ok=True)
            with open(TEMPLATE_MAPPING_FILE, 'w', encoding='utf-8') as f:
                yaml.dump(mapping_data, f, default_flow_style=False, allow_unicode=True, indent=2)

            logger.success(f"Соответствие шаблонов сохранено в файл: {TEMPLATE_MAPPING_FILE}")
            return True

        except Exception as e:
            logger.error(f"Ошибка сохранения соответствия шаблонов: {e}")
            return False

    def load_template_mapping(self) -> bool:
        """Загрузить соответствие шаблонов между нодами из файла"""
        try:
            if not os.path.exists(TEMPLATE_MAPPING_FILE):
                logger.debug("Файл соответствия шаблонов не найден, создаем пустое соответствие")
                self.template_mapping = {}
                self.local_templates = {}  # Инициализируем пустой словарь локальных шаблонов
                return False

            with open(TEMPLATE_MAPPING_FILE, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            self.template_mapping = data.get('template_mapping', {})

            # ВАЖНО: Больше не загружаем local_templates из файла
            # Теперь local_templates используется только как кэш в памяти
            # Все данные хранятся в template_mapping

            logger.success(f"Загружено соответствие шаблонов для {len(self.template_mapping)} оригинальных шаблонов")
            return True

        except Exception as e:
            logger.error(f"Ошибка загрузки соответствия шаблонов: {e}")
            self.template_mapping = {}
            self.local_templates = {}
            return False

    def verify_template_exists(self, node: str, vmid: int) -> bool:
        """Проверить физическое существование шаблона на ноде"""
        try:
            # Попытаемся получить конфигурацию VM
            vm_config = self.proxmox.proxmox.nodes(node).qemu(vmid).config.get()
            if vm_config:
                # Проверяем, что это действительно шаблон
                template = vm_config.get('template', 0)
                return template == 1
            return False
        except Exception as e:
            # Если не можем получить конфигурацию, значит VM не существует
            return False

    def get_mapped_template(self, original_vmid: int, target_node: str) -> int | None:
        """Получить VMID локального шаблона для целевой ноды из соответствия"""
        # Пробуем найти как строку
        if str(original_vmid) in self.template_mapping:
            node_mapping = self.template_mapping[str(original_vmid)]
        # Пробуем найти как число
        elif original_vmid in self.template_mapping:
            node_mapping = self.template_mapping[original_vmid]
        else:
            return None

        return node_mapping.get(target_node)

    def update_template_mapping(self, original_vmid: int, template_node: str, target_node: str, local_vmid: int) -> None:
        """Обновить соответствие шаблонов после создания локального шаблона"""
        original_vmid_str = str(original_vmid)

        if original_vmid_str not in self.template_mapping:
            self.template_mapping[original_vmid_str] = {}

        self.template_mapping[original_vmid_str][target_node] = local_vmid

        logger.debug(f"Обновлено соответствие: {original_vmid} -> {target_node}: {local_vmid}")

    def remove_template_mapping(self, original_vmid: int, target_node: str) -> None:
        """Удалить соответствие шаблона для конкретной ноды"""
        original_vmid_str = str(original_vmid)

        if original_vmid_str in self.template_mapping:
            if target_node in self.template_mapping[original_vmid_str]:
                del self.template_mapping[original_vmid_str][target_node]
                logger.debug(f"Удалено соответствие: {original_vmid} -> {target_node}")

                # Если для оригинального шаблона не осталось соответствий, удаляем весь блок
                if not self.template_mapping[original_vmid_str]:
                    del self.template_mapping[original_vmid_str]

        # Также удаляем из кэша local_templates
        template_key = f"{original_vmid}:{target_node}"
        if template_key in self.local_templates:
            del self.local_templates[template_key]
