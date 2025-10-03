# Модуль устарел - используйте app.utils.logger вместо него
# Оставлен для обратной совместимости

from app.utils.logger import logger, info as log_info, success as log_success, warning as log_warning, error as log_error

def info(msg: str):
    """Информационное сообщение"""
    log_info(f"ℹ {msg}")

def success(msg: str):
    """Сообщение об успехе"""
    log_success(msg)

def warn(msg: str):
    """Предупреждение"""
    log_warning(f"⚠ {msg}")

def error(msg: str):
    """Ошибка"""
    log_error(f"✖ {msg}")

def title(msg: str):
    """Заголовок"""
    print(f"{logger.emphasize(msg)}")

def emphasize(value: str) -> str:
    """Выделить текст"""
    return logger.emphasize(value)
