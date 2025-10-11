#!/usr/bin/env python3
"""
Модуль управления серверами Proxmox
Отдельный модуль для работы с подключениями к серверам
"""

import asyncio
import logging
import getpass
from typing import Dict, List, Optional, Any
from .base_menu import BaseMenu
from ..connection_manager import get_connection_manager

logger = logging.getLogger(__name__)


class ServerManagementMenu(BaseMenu):
    """Меню управления подключениями к серверам Proxmox"""

    def __init__(self):
        super().__init__()
        self.connection_manager = get_connection_manager()

    async def show_menu(self):
        """Отображение меню управления серверами"""
        self.clear_screen()

        print("\n" + "="*60)
        print("УПРАВЛЕНИЕ ПОДКЛЮЧЕНИЯМИ К СЕРВЕРАМ PROXMOX")
        print("="*60)
        print("1. Создать новое подключение")
        print("2. Удалить существующее подключение")
        print("3. Показать список подключений")
        print("0. Назад в главное меню")
        print("-"*60)

    async def handle_choice(self, choice: str) -> bool:
        """Обработка выбора пользователя"""
        if choice == "0":
            print("Возврат в главное меню...")
            return False

        elif choice == "1":
            await self.create_server_connection()
        elif choice == "2":
            await self.delete_server_connection()
        elif choice == "3":
            await self.show_server_list()
            await self.show_message("", pause=True)
        else:
            print("Неверный выбор. Попробуйте еще раз.")

        return True

    async def create_server_connection(self):
        """Создание нового подключения к серверу"""
        self.clear_screen()

        print("\n📝 Создание нового подключения к серверу Proxmox")
        new_config = await self.create_new_connection_interactive()

        if new_config:
            print(f"💾 Подключение '{new_config.get('name')}' сохранено в конфигурацию")
        else:
            print("❌ Не удалось создать подключение")

    async def delete_server_connection(self):
        """Удаление существующего подключения"""
        self.clear_screen()

        print("\n🗑️  Удаление подключения к серверу")

        # Показываем список серверов
        servers = self.connection_manager.get_proxmox_servers()
        if not servers:
            print("❌ Нет настроенных серверов для удаления")
            return

        print("\nДоступные серверы для удаления:")
        for i, (server_name, server_config) in enumerate(servers.items(), 1):
            name = server_config.get('name', 'Без имени')
            host = server_config.get('host', 'Не указан')
            print(f"{i}. {server_name} - {name} ({host})")

        while True:
            choice = await self.get_user_input("Выберите сервер для удаления (номер) или 0 для отмены: ")

            if choice == "0":
                print("Операция отменена")
                await self.show_menu()
                return

            try:
                server_index = int(choice) - 1
                if 0 <= server_index < len(servers):
                    server_names = list(servers.keys())
                    server_to_delete = server_names[server_index]
                    server_config = servers[server_to_delete]

                    # Подтверждение удаления
                    confirm = await self.get_user_input(
                        f"Вы уверены, что хотите удалить сервер '{server_to_delete}'? (y/n): ",
                        required=False, default="n"
                    )

                    if confirm.lower() in ['y', 'yes', 'да', 'д']:
                        if self.connection_manager.remove_server(server_to_delete):
                            print(f"✅ Сервер '{server_to_delete}' успешно удален")
                        else:
                            print(f"❌ Ошибка при удалении сервера '{server_to_delete}'")
                    else:
                        print("Операция отменена")

                    await self.show_menu()
                    return
                else:
                    print(f"❌ Выберите номер от 1 до {len(servers)}")
            except ValueError:
                print("❌ Введите номер сервера или 0 для отмены")

    async def show_server_list(self) -> List[str]:
        """Отображение списка доступных серверов"""
        print("\n" + "="*60)
        print("ДОСТУПНЫЕ СЕРВЕРЫ PROXMOX")
        print("="*60)

        # Загружаем конфигурацию
        if not self.connection_manager.load_config():
            print("❌ Ошибка загрузки конфигурации")
            return []

        servers = self.connection_manager.get_proxmox_servers()
        enabled_servers = []

        if not servers:
            print("📭 Нет настроенных серверов")
            return []

        for server_name, server_config in servers.items():
            enabled = server_config.get('enabled', False)
            status = "✅ Активен" if enabled else "❌ Отключен"
            name = server_config.get('name', 'Без имени')
            host = server_config.get('host', 'Не указан')
            description = server_config.get('description', '')

            print(f"\n🖥️  {server_name}")
            print(f"   Название: {name}")
            print(f"   Адрес: {host}")
            print(f"   Статус: {status}")
            if description:
                print(f"   Описание: {description}")

            if enabled:
                enabled_servers.append(server_name)

        print("\n" + "-"*60)
        return enabled_servers

    async def check_and_add_realm(self, username: str) -> str:
        """Проверка и дополнение realm для пользователя Proxmox"""
        # Стандартные realms в Proxmox
        common_realms = ['pam', 'pve']

        # Проверяем, содержит ли логин realm
        if '@' in username:
            # Логин уже содержит realm, возвращаем как есть
            return username

        # Логин без realm, предлагаем выбрать
        print(f"\nВведен логин без realm: '{username}'")
        print("Выберите realm для пользователя:")

        for i, realm in enumerate(common_realms, 1):
            print(f"{i}. @{realm}")

        print("0. Ввести realm вручную")

        while True:
            choice = await self.get_user_input("Выбор (0-2): ")

            if choice == "0":
                # Ввод realm вручную
                realm = await self.get_user_input("Введите realm (например, pam): ")
                if realm:
                    return f"{username}@{realm}"
                else:
                    print("❌ Realm не может быть пустым")
                    continue

            try:
                realm_index = int(choice) - 1
                if 0 <= realm_index < len(common_realms):
                    selected_realm = common_realms[realm_index]
                    print(f"✅ Выбран realm: @{selected_realm}")
                    return f"{username}@{selected_realm}"
                else:
                    print(f"❌ Выберите номер от 0 до {len(common_realms)}")
            except ValueError:
                print("❌ Введите номер или 0 для ручного ввода")

    async def create_new_connection_interactive(self) -> Optional[Dict[str, Any]]:
        """Интерактивное создание нового подключения"""
        print("\n" + "="*60)
        print("СОЗДАНИЕ НОВОГО ПОДКЛЮЧЕНИЯ К PROXMOX")
        print("="*60)

        # Ввод имени сервера
        server_name = await self.get_user_input("Введите имя сервера (например, main, backup): ")
        if not server_name:
            return None

        # Проверка существования сервера
        if self.connection_manager.get_server_config(server_name):
            print(f"❌ Сервер с именем '{server_name}' уже существует")
            return None

        # Ввод адреса сервера
        host = await self.get_user_input("Введите адрес сервера Proxmox: ")
        if not host:
            return None

        # Ввод порта
        port_input = await self.get_user_input("Введите порт (по умолчанию 8006): ", required=False, default="8006")
        try:
            port = int(port_input)
            if not (1 <= port <= 65535):
                print("❌ Порт должен быть в диапазоне 1-65535")
                return None
        except ValueError:
            print("❌ Порт должен быть числом")
            return None

        # Ввод логина
        user = await self.get_user_input("Введите имя пользователя: ")
        if not user:
            return None

        # Проверка и дополнение realm если отсутствует
        user = await self.check_and_add_realm(user)
        if not user:
            return None

        # Выбор метода аутентификации
        print("\nВыберите метод аутентификации:")
        print("1. Пароль")
        print("2. Токен API")

        auth_choice = await self.get_user_input("Выбор (1-2): ")
        if auth_choice not in ["1", "2"]:
            print("❌ Неверный выбор метода аутентификации")
            return None

        password = ""
        token_name = ""
        token_value = ""

        if auth_choice == "1":
            # Ввод пароля
            print("Введите пароль (ввод скрыт): ")
            try:
                password = getpass.getpass()
                if not password:
                    print("❌ Пароль не может быть пустым")
                    return None
            except Exception as e:
                print(f"❌ Ошибка ввода пароля: {e}")
                return None
        else:
            # Ввод токена
            token_name = await self.get_user_input("Введите имя токена: ")
            if not token_name:
                return None

            print("Введите значение токена (ввод скрыт): ")
            try:
                token_value = getpass.getpass()
                if not token_value:
                    print("❌ Значение токена не может быть пустым")
                    return None
            except Exception as e:
                print(f"❌ Ошибка ввода токена: {e}")
                return None

        # Ввод описания
        description = await self.get_user_input("Описание сервера (необязательно): ", required=False)

        # Настройки SSL
        ssl_choice = await self.get_user_input("Использовать SSL верификацию? (y/n, по умолчанию n): ", required=False, default="n")
        verify_ssl = ssl_choice.lower() in ['y', 'yes', 'да', 'д']

        # Создание конфигурации сервера
        server_config = {
            'name': server_name,
            'host': host,
            'port': port,
            'user': user,
            'password': password if password else "",
            'token_name': token_name if token_name else "",
            'token_value': token_value if token_value else "",
            'verify_ssl': verify_ssl,
            'description': description,
            'enabled': True
        }

        # Валидация конфигурации
        errors = self.connection_manager.validate_server_config(server_config)
        if errors:
            print("❌ Ошибки валидации:")
            for error in errors:
                print(f"   • {error}")
            return None

        # Сохранение сервера
        if self.connection_manager.add_server(server_name, server_config):
            print(f"✅ Сервер '{server_name}' успешно добавлен")
            return server_config
        else:
            print(f"❌ Ошибка сохранения сервера '{server_name}'")
            return None

    async def select_server_interactive(self, available_servers: List[str]) -> Optional[str]:
        """Интерактивный выбор сервера из списка"""
        if not available_servers:
            return None

        print(f"\nДоступные серверы: {len(available_servers)}")
        for i, server_name in enumerate(available_servers, 1):
            server_config = self.connection_manager.get_server_config(server_name)
            name = server_config.get('name', 'Без имени') if server_config else 'Без имени'
            host = server_config.get('host', 'Не указан') if server_config else 'Не указан'
            print(f"{i}. {server_name} - {name} ({host})")

        while True:
            choice = await self.get_user_input("Выберите сервер (номер) или 'n' для создания нового: ")

            if choice.lower() in ['n', 'new', 'новый']:
                return None  # Сигнал для создания нового сервера

            try:
                server_index = int(choice) - 1
                if 0 <= server_index < len(available_servers):
                    selected_server = available_servers[server_index]
                    server_config = self.connection_manager.get_server_config(selected_server)

                    print(f"✅ Выбран сервер: {selected_server}")
                    if server_config:
                        print(f"   Название: {server_config.get('name', 'Без имени')}")
                        print(f"   Адрес: {server_config.get('host')}:{server_config.get('port', 8006)}")

                    return selected_server
                else:
                    print(f"❌ Выберите номер от 1 до {len(available_servers)}")
            except ValueError:
                print("❌ Введите номер сервера или 'n' для создания нового")


def get_server_management_menu() -> ServerManagementMenu:
    """Функция для получения экземпляра меню управления серверами"""
    return ServerManagementMenu()
