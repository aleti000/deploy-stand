#!/usr/bin/env python3
import sys
from app.ui.cli_menus import MainMenu
from app.utils.logger import logger

def main():
    try:
        menu = MainMenu()
        menu.show()
    except KeyboardInterrupt:
        logger.info("Программа завершена пользователем")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
