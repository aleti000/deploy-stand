#!/usr/bin/env python3
import sys
from app.ui.cli_menus import MainMenu

def main():
    try:
        menu = MainMenu()
        menu.show()
    except KeyboardInterrupt:
        print("\n\nПрограмма завершена пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()