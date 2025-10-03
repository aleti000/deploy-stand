import logging
import sys
from typing import Optional
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)

class ColoredFormatter(logging.Formatter):
    """Форматтер с цветным выводом для консоли"""

    COLORS = {
        'DEBUG': Fore.BLUE,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        # Добавляем цвет к уровню логирования
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{Style.RESET_ALL}"

        # Добавляем цвет к сообщению для определенных уровней
        if record.levelno >= logging.ERROR:
            record.msg = f"{Fore.RED}{record.msg}{Style.RESET_ALL}"
        elif record.levelno >= logging.WARNING:
            record.msg = f"{Fore.YELLOW}{record.msg}{Style.RESET_ALL}"
        elif record.levelno >= logging.INFO:
            record.msg = f"{Fore.GREEN}{record.msg}{Style.RESET_ALL}"

        return super().format(record)

class DeployStandLogger:
    """Централизованный логгер для Deploy-Stand"""

    def __init__(self, name: str = "deploy-stand", log_file: Optional[str] = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        # Убираем существующие обработчики, чтобы избежать дублирования
        self.logger.handlers.clear()

        # Консольный обработчик
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # Файловый обработчик (если указан)
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

    def debug(self, message: str, *args, **kwargs):
        """Отладочная информация"""
        self.logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs):
        """Информационное сообщение"""
        self.logger.info(message, *args, **kwargs)

    def success(self, message: str, *args, **kwargs):
        """Сообщение об успешном выполнении"""
        self.logger.info(f"✅ {message}", *args, **kwargs)

    def warning(self, message: str, *args, **kwargs):
        """Предупреждение"""
        self.logger.warning(f"⚠️ {message}", *args, **kwargs)

    def error(self, message: str, *args, **kwargs):
        """Ошибка"""
        self.logger.error(f"❌ {message}", *args, **kwargs)

    def critical(self, message: str, *args, **kwargs):
        """Критическая ошибка"""
        self.logger.critical(f"🚨 {message}", *args, **kwargs)

    def emphasize(self, message: str) -> str:
        """Выделить текст (для использования в сообщениях)"""
        return f"{Style.BRIGHT}{Fore.CYAN}{message}{Style.RESET_ALL}"

# Глобальный экземпляр логгера
logger = DeployStandLogger()

# Удобные функции для обратной совместимости
def debug(msg: str): logger.debug(msg)
def info(msg: str): logger.info(msg)
def success(msg: str): logger.success(msg)
def warning(msg: str): logger.warning(msg)
def error(msg: str): logger.error(msg)
def critical(msg: str): logger.critical(msg)
