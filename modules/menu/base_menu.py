#!/usr/bin/env python3
"""
Базовый модуль для интерактивных меню
Предоставляет общую функциональность для всех меню системы
"""

import asyncio
import os
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod


class BaseMenu(ABC):
    """Базовый класс для всех интерактивных меню"""

    def __init__(self):
        pass

    def clear_screen(self):
        """Очистка экрана"""
        os.system('clear' if os.name != 'nt' else 'cls')

    async def get_user_input(self, prompt: str, required: bool = True, default: str = "") -> str:
        """Получение ввода от пользователя"""
        while True:
            try:
                value = input(f"{prompt}").strip()
                if not value and required and not default:
                    print("❌ Это поле обязательно для заполнения")
                    continue
                if not value and default:
                    return default
                return value
            except KeyboardInterrupt:
                print("\n\n⏹️  Операция отменена")
                return ""

    async def show_message(self, message: str, pause: bool = True):
        """Отображение сообщения с опциональной паузой"""
        print(message)
        if pause:
            print("\nНажмите Enter для продолжения...")
            input()

    @abstractmethod
    async def show_menu(self):
        """Отображение меню - должно быть реализовано в наследниках"""
        pass

    @abstractmethod
    async def handle_choice(self, choice: str) -> bool:
        """Обработка выбора пользователя - должно быть реализовано в наследниках"""
        pass

    async def run(self):
        """Запуск меню"""
        while True:
            await self.show_menu()
            choice = await self.get_user_input("Выберите действие: ")

            if not await self.handle_choice(choice):
                break
