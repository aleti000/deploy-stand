#!/usr/bin/env python3
"""
Меню удаления стендов
Удаление стендов пользователей с различными опциями
"""

from ..utils import Logger


class DeleteStandMenu:
    """Меню удаления стендов"""

    def __init__(self, logger_instance):
        self.logger = logger_instance

    def show(self) -> str:
        """Показать меню удаления стендов"""
        print("\n🗑️  Удаление стендов")
        print("=" * 50)

        print("Доступные действия:")
        print("  [1] 🗑️  Удалить все стенды (пакетное удаление)")
        print("  [2] 🗑️  Удалить стенд конкретного пользователя")
        print("  [3] 🗑️  Выбрать стенды для удаления")
        print("  [4] 🔍 Проверить существующие стенды")
        print("  [0] Назад")

        choice = input("Выберите действие: ").strip()

        if choice in ["1", "2", "3", "4"]:
            print(f"Функция {choice} будет реализована в следующих обновлениях")
            return "repeat"
        elif choice == "0":
            return "back"
        else:
            print("❌ Неверный выбор!")
            return "repeat"
