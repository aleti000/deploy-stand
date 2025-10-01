import yaml
import json
from typing import Any, dict

def print_json(data: dict[str, Any]):
    """Красивый вывод JSON"""
    print(json.dumps(data, indent=2, ensure_ascii=False))

def validate_config(config: dict[str, Any]) -> bool:
    """Валидация конфигурации"""
    required_fields = ['machines']
    
    for field in required_fields:
        if field not in config:
            print(f"Отсутствует обязательное поле: {field}")
            return False
    
    for i, machine in enumerate(config['machines']):
        if 'name' not in machine:
            print(f"Машина #{i+1}: отсутствует имя")
            return False
        if 'template_vmid' not in machine:
            print(f"Машина #{i+1}: отсутствует VMID шаблона")
            return False
        if 'template_node' not in machine:
            print(f"Машина #{i+1}: отсутствует нода шаблона")
            return False
    
    return True