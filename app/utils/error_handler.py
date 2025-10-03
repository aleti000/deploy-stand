import sys
import traceback
from typing import Any, Callable, TypeVar
from functools import wraps
from app.utils.console import error, warn

F = TypeVar('F', bound=Callable[..., Any])

def handle_errors(default_return: Any = None, show_traceback: bool = False):
    """Декоратор для централизованной обработки ошибок"""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except KeyboardInterrupt:
                print("\nОперация прервана пользователем")
                sys.exit(0)
            except Exception as e:
                if show_traceback:
                    error(f"Ошибка в {func.__name__}: {e}")
                    traceback.print_exc()
                else:
                    error(f"Ошибка в {func.__name__}: {e}")
                return default_return
        return wrapper
    return decorator

def safe_execute(func: Callable, *args, default_return: Any = None, **kwargs):
    """Безопасное выполнение функции с обработкой ошибок"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        warn(f"Ошибка при выполнении {func.__name__}: {e}")
        return default_return

class ErrorHandler:
    """Централизованный обработчик ошибок"""

    @staticmethod
    def handle_critical_error(message: str, exit_code: int = 1):
        """Обработка критических ошибок с завершением программы"""
        error(f"Критическая ошибка: {message}")
        sys.exit(exit_code)

    @staticmethod
    def handle_warning(message: str):
        """Обработка предупреждений"""
        warn(f"Предупреждение: {message}")

    @staticmethod
    def handle_info(message: str):
        """Обработка информационных сообщений"""
        from app.utils.console import info
        info(message)
