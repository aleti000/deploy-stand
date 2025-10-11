#!/usr/bin/env python3
"""
Модуль меню системы развертывания стендов ВМ
Основной файл для импорта в main.py - использует модульную структуру
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from proxmoxer import ProxmoxAPI

from modules.menu.base_menu import BaseMenu
from modules.menu.user_management import get_user_management_menu
from modules.menu.server_management import get_server_management_menu
from modules.connection_manager import get_connection_manager
from modules.proxmox_client import create_proxmox_client
from modules.user_list_manager import get_user_list_manager
from modules.stand_configure import get_stand_configurer, StandConfigMenu

logger = logging.getLogger(__name__)


class DeployStandMenu(BaseMenu):
    """Главное меню системы развертывания стендов"""

    def __init__(self):
        super().__init__()
        self.proxmox: Optional[ProxmoxAPI] = None
        self.is_running = False
        self.connection_manager = get_connection_manager()
        self.user_list_manager = get_user_list_manager()

    async def initialize_proxmox_connection(self, config: Dict) -> bool:
        """Инициализация подключения к Proxmox API"""
        try:
            # Создаем клиент Proxmox
            client = create_proxmox_client(config)

            # Устанавливаем подключение
            if not client.connect():
                logger.error("Не удалось подключиться к Proxmox API")
                return False

            # Сохраняем клиент для дальнейшего использования
            self.proxmox = client

            logger.info(f"Успешное подключение к Proxmox через клиент")
            return True

        except Exception as e:
            logger.error(f"Ошибка подключения к Proxmox: {e}")
            return False

    async def show_menu(self):
        """Отображение главного меню"""
        self.clear_screen()

        print("\n" + "="*50)
        print("DEPLOY STAND - Система развертывания стендов ВМ")
        print("="*50)
        print("1. Управление пользователями")
        print("2. Создание конфигурации стенда")
        print("3. Показать список виртуальных машин")
        print("4. Создать новый стенд")
        print("5. Управление шаблонами")
        print("6. Настройки")
        print("7. Управление подключениями к серверам")
        print("0. Выход")
        print("-"*50)

    async def handle_choice(self, choice: str) -> bool:
        """Обработка выбора пользователя"""
        if choice == "0":
            print("Выход из системы...")
            return False

        elif choice == "1":
            await self.manage_users()
        elif choice == "2":
            await self.manage_stand_config()
        elif choice == "3":
            await self.show_vm_list()
        elif choice == "4":
            await self.create_stand()
        elif choice == "5":
            await self.manage_templates()
        elif choice == "6":
            await self.show_settings()
        elif choice == "7":
            await self.manage_server_connections()
        else:
            print("Неверный выбор. Попробуйте еще раз.")

        return True

    async def show_vm_list(self):
        """Показать список виртуальных машин"""
        self.clear_screen()

        if not self.proxmox:
            print("❌ Клиент Proxmox не инициализирован")
            print("Сначала настройте подключение к серверу Proxmox")
            return

        if not self.proxmox.is_connected():
            print("❌ Не подключен к Proxmox серверу")
            print("Сначала подключитесь к серверу через меню управления подключениями")
            return

        try:
            print("\n📋 Получение списка виртуальных машин...")

            # Получаем список узлов через клиент
            nodes = self.proxmox.get_nodes()
            print(f"✅ Найдено узлов: {len(nodes)}")

            if not nodes:
                print("⚠️  На сервере нет доступных узлов")
                await self.show_message("", pause=True)
                return

            total_vms = 0
            for node in nodes:
                node_name = node.get('node')
                print(f"\n📁 Узел: {node_name}")

                try:
                    # Получаем список ВМ на узле через клиент
                    vms = self.proxmox.get_vms(node_name)
                    node_vm_count = len(vms)

                    if node_vm_count == 0:
                        print("  📭 Нет виртуальных машин")
                    else:
                        print(f"  🖥️  Виртуальные машины ({node_vm_count}):")
                        for vm in vms:
                            vmid = vm.get('vmid')
                            name = vm.get('name', 'Без имени')
                            status = vm.get('status', 'unknown')
                            print(f"    • VM {vmid}: {name} - {status}")
                            total_vms += 1

                except Exception as node_error:
                    logger.error(f"Ошибка получения ВМ для узла {node_name}: {node_error}")
                    print(f"  ❌ Ошибка получения данных для узла {node_name}")

            print(f"\n📊 Всего виртуальных машин: {total_vms}")
            await self.show_message("", pause=True)

        except Exception as e:
            logger.error(f"Ошибка получения списка ВМ: {e}")
            print(f"❌ Ошибка при получении списка виртуальных машин: {e}")
            print("Проверьте подключение к серверу Proxmox")
            await self.show_message("", pause=True)

    async def create_stand(self):
        """Создание нового стенда"""
        self.clear_screen()
        print("\nСоздание нового стенда...")
        print("⚠️  Функция в разработке")
        await self.show_message("", pause=True)

    async def manage_templates(self):
        """Управление шаблонами"""
        self.clear_screen()
        print("\nУправление шаблонами...")
        print("⚠️  Функция в разработке")
        await self.show_message("", pause=True)

    async def show_settings(self):
        """Показать настройки"""
        self.clear_screen()
        print("\nНастройки системы:")
        print("⚠️  Функция в разработке")
        await self.show_message("", pause=True)

    async def manage_users(self):
        """Управление списками пользователей"""
        user_menu = get_user_management_menu()
        await user_menu.run()

    async def manage_stand_config(self):
        """Управление конфигурациями стендов"""
        # Создаем конфигурер стендов
        configurer = get_stand_configurer()

        # Передаем клиент Proxmox если он доступен
        if self.proxmox and self.proxmox.is_connected():
            configurer.set_proxmox_client(self.proxmox)

        # Создаем меню конфигурирования
        config_menu = StandConfigMenu(configurer)

        # Запускаем меню
        await config_menu.run()

    async def manage_server_connections(self):
        """Управление подключениями к серверам Proxmox"""
        server_menu = get_server_management_menu()
        await server_menu.run()

    async def run_server_selection_wizard(self) -> Optional[Dict[str, Any]]:
        """Мастер выбора/создания сервера"""
        server_menu = get_server_management_menu()

        # Показываем список серверов
        available_servers = await server_menu.show_server_list()

        if available_servers:
            # Предлагаем выбрать существующий сервер
            selected_server = await server_menu.select_server_interactive(available_servers)
            if selected_server:
                # Возвращаем конфигурацию выбранного сервера
                server_config = self.connection_manager.get_server_config(selected_server)
                if server_config:
                    return server_config

        # Создаем новое подключение
        print("\n📝 Создание нового подключения...")
        new_config = await server_menu.create_new_connection_interactive()

        if new_config:
            # Предлагаем сохранить подключение
            save_choice = await self.get_user_input("Сохранить подключение в конфигурацию? (y/n): ", required=False, default="y")
            if save_choice.lower() in ['y', 'yes', 'да', 'д']:
                print(f"💾 Подключение сохранено как '{list(self.connection_manager.get_proxmox_servers().keys())[-1]}'")
            return new_config
        else:
            # Ошибка создания или отмена
            retry_choice = await self.get_user_input("Попробовать снова? (y/n): ", required=False, default="y")
            if retry_choice.lower() not in ['y', 'yes', 'да', 'д']:
                print("👋 Выход из мастера подключений")
                return None
            else:
                self.clear_screen()
                print("🔄 Повторная попытка создания подключения...")
                return await self.run_server_selection_wizard()

    async def run(self, config: Dict):
        """Запуск главного цикла меню"""
        self.is_running = True

        print("🚀 Запуск системы развертывания стендов ВМ")

        try:
            while self.is_running:
                await self.show_menu()
                choice = await self.get_user_input("Выберите действие: ")

                if not await self.handle_choice(choice):
                    break

        except KeyboardInterrupt:
            print("\n\nПолучен сигнал завершения. Выход...")

        finally:
            self.is_running = False
            print("👋 Система завершена")


async def run_menu(config: Dict):
    """Функция запуска меню для импорта в main.py"""
    menu = DeployStandMenu()
    await menu.run(config)
