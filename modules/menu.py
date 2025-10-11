#!/usr/bin/env python3
"""
Модуль меню системы развертывания стендов ВМ
Предоставляет интерфейс для управления виртуальными стендами
"""

import asyncio
import logging
import getpass
from typing import Dict, List, Optional, Any
from .connection_manager import get_connection_manager
from .proxmox_client import create_proxmox_client
from .user_list_manager import get_user_list_manager

logger = logging.getLogger(__name__)


class DeployStandMenu:
    """Класс для управления меню системы развертывания стендов"""

    def __init__(self):
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

    async def show_main_menu(self):
        """Отображение главного меню"""
        # Очищаем экран перед показом меню
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        print("\n" + "="*50)
        print("DEPLOY STAND - Система развертывания стендов ВМ")
        print("="*50)
        print("1. Управление пользователями")
        print("2. Показать список виртуальных машин")
        print("3. Создать новый стенд")
        print("4. Управление шаблонами")
        print("5. Настройки")
        print("6. Управление подключениями к серверам")
        print("0. Выход")
        print("-"*50)

    async def get_user_choice(self) -> str:
        """Получение выбора пользователя"""
        try:
            choice = input("Выберите действие: ").strip()
            return choice
        except KeyboardInterrupt:
            return "0"

    async def handle_menu_choice(self, choice: str, config: Dict) -> bool:
        """Обработка выбора пользователя"""
        if choice == "0":
            print("Выход из системы...")
            return False

        elif choice == "1":
            await self.manage_users()

        elif choice == "2":
            await self.show_vm_list()

        elif choice == "3":
            await self.create_stand()

        elif choice == "4":
            await self.manage_templates()

        elif choice == "5":
            await self.show_settings()

        elif choice == "6":
            await self.manage_server_connections()

        else:
            print("Неверный выбор. Попробуйте еще раз.")

        return True

    async def connect_to_proxmox(self, config: Dict):
        """Подключение к Proxmox серверу"""
        print("\nПодключение к Proxmox серверу...")
        success = await self.initialize_proxmox_connection(config)
        if success:
            print("✅ Успешное подключение к Proxmox")
        else:
            print("❌ Ошибка подключения к Proxmox")

    async def show_vm_list(self):
        """Показать список виртуальных машин"""
        # Очищаем экран перед показом списка ВМ
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

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

            # Добавляем паузу для просмотра списка
            print("\n" + "="*50)
            print("Нажмите Enter для возврата в главное меню...")
            print("="*50)
            input()

        except Exception as e:
            logger.error(f"Ошибка получения списка ВМ: {e}")
            print(f"❌ Ошибка при получении списка виртуальных машин: {e}")
            print("Проверьте подключение к серверу Proxmox")
            print("\nНажмите Enter для возврата в главное меню...")
            input()

    async def create_stand(self):
        """Создание нового стенда"""
        # Очищаем экран перед созданием стенда
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        print("\nСоздание нового стенда...")
        print("⚠️  Функция в разработке")

    async def manage_templates(self):
        """Управление шаблонами"""
        # Очищаем экран перед управлением шаблонами
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        print("\nУправление шаблонами...")
        print("⚠️  Функция в разработке")

    async def show_settings(self):
        """Показать настройки"""
        # Очищаем экран перед показом настроек
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        print("\nНастройки системы:")
        print("⚠️  Функция в разработке")

    async def manage_users(self):
        """Управление списками пользователей"""
        # Очищаем экран перед показом подменю
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        print("\n" + "="*50)
        print("УПРАВЛЕНИЕ СПИСКАМИ ПОЛЬЗОВАТЕЛЕЙ")
        print("="*50)
        print("1. Ввести список пользователей (через запятую)")
        print("2. Импорт из списка")
        print("3. Вывести существующие списки")
        print("4. Удалить список пользователей")
        print("0. Назад в главное меню")
        print("-"*50)

        while True:
            choice = await self.get_user_input("Выберите действие: ")

            if choice == "0":
                print("Возврат в главное меню...")
                break
            elif choice == "1":
                await self.create_user_list_interactive()
            elif choice == "2":
                await self.import_user_list_interactive()
            elif choice == "3":
                await self.show_user_lists()
                print("\nНажмите Enter для продолжения...")
                input()
                # Очищаем экран и показываем меню снова
                import os
                os.system('clear' if os.name != 'nt' else 'cls')
                print("\n" + "="*50)
                print("УПРАВЛЕНИЕ СПИСКАМИ ПОЛЬЗОВАТЕЛЕЙ")
                print("="*50)
                print("1. Ввести список пользователей (через запятую)")
                print("2. Импорт из списка")
                print("3. Вывести существующие списки")
                print("4. Удалить список пользователей")
                print("0. Назад в главное меню")
                print("-"*50)
            elif choice == "4":
                await self.delete_user_list_interactive()
            else:
                print("Неверный выбор. Попробуйте еще раз.")

    async def create_user_list_interactive(self):
        """Интерактивное создание списка пользователей"""
        # Очищаем экран перед созданием списка
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        print("\n📝 Создание нового списка пользователей")
        print("Введите пользователей через запятую (например: user1, user2, user3)")
        print("Если пользователь указан без @pve, он будет добавлен автоматически")

        # Ввод имени списка
        list_name = await self.get_user_input("Введите имя списка пользователей: ")
        if not list_name:
            return

        # Ввод пользователей
        users_input = await self.get_user_input("Введите пользователей через запятую: ")
        if not users_input:
            print("❌ Список пользователей не может быть пустым")
            return

        # Парсинг пользователей
        users = self.user_list_manager.parse_user_input(users_input)
        if not users:
            print("❌ Не удалось распознать пользователей")
            return

        # Ввод описания
        description = await self.get_user_input("Описание списка (необязательно): ", required=False)

        # Создание списка
        if self.user_list_manager.create_user_list(list_name, users, description):
            print(f"✅ Список '{list_name}' создан с {len(users)} пользователями")
        else:
            print(f"❌ Ошибка создания списка '{list_name}'")
            return

        # Очищаем экран и возвращаемся в меню управления пользователями
        import os
        os.system('clear' if os.name != 'nt' else 'cls')
        print("\n" + "="*50)
        print("УПРАВЛЕНИЕ СПИСКАМИ ПОЛЬЗОВАТЕЛЕЙ")
        print("="*50)
        print("1. Ввести список пользователей (через запятую)")
        print("2. Импорт из списка")
        print("3. Вывести существующие списки")
        print("4. Удалить список пользователей")
        print("0. Назад в главное меню")
        print("-"*50)

    async def import_user_list_interactive(self):
        """Интерактивный импорт списка пользователей"""
        # Очищаем экран перед импортом
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        print("\n📥 Импорт списка пользователей из файла")
        print("Файл должен содержать пользователей (по одному на строку)")
        print("Строки начинающиеся с # считаются комментариями")
        print("Если пользователь указан без @pve, он будет добавлен автоматически")

        # Ввод имени списка
        list_name = await self.get_user_input("Введите имя нового списка: ")
        if not list_name:
            return

        # Ввод пути к файлу
        file_path = await self.get_user_input("Введите путь к файлу со списком пользователей: ")
        if not file_path:
            print("❌ Путь к файлу не может быть пустым")
            return

        # Проверка существования файла
        from pathlib import Path
        if not Path(file_path).exists():
            print(f"❌ Файл '{file_path}' не найден")
            return

        # Ввод описания
        description = await self.get_user_input("Описание списка (необязательно): ", required=False)

        # Импорт списка из файла
        if self.user_list_manager.import_user_list_from_file(list_name, file_path, description):
            print(f"✅ Список '{list_name}' импортирован из файла '{file_path}'")
        else:
            print(f"❌ Ошибка импорта списка '{list_name}' из файла '{file_path}'")

    async def show_user_lists(self):
        """Показать все списки пользователей"""
        # Очищаем экран перед показом
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        print("\n📋 Существующие списки пользователей:")

        user_lists = self.user_list_manager.get_user_lists()

        if not user_lists:
            print("📭 Нет созданных списков пользователей")
            return

        for list_name, list_data in user_lists.items():
            print(f"\n📁 {list_name}")
            print(f"   Описание: {list_data.get('description', 'Без описания')}")
            print(f"   Количество пользователей: {list_data.get('count', 0)}")

            users = list_data.get('users', [])
            if users:
                print("   Пользователи:")
                for i, user in enumerate(users[:5], 1):  # Показываем первых 5
                    print(f"     {i}. {user}")
                if len(users) > 5:
                    print(f"     ... и еще {len(users) - 5} пользователей")

    async def delete_user_list_interactive(self):
        """Интерактивное удаление списка пользователей"""
        # Очищаем экран перед удалением
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        print("\n🗑️  Удаление списка пользователей")

        # Показываем доступные списки
        list_names = self.user_list_manager.get_user_list_names()
        if not list_names:
            print("❌ Нет списков пользователей для удаления")
            return

        print("\nДоступные списки пользователей:")
        for i, list_name in enumerate(list_names, 1):
            print(f"{i}. {list_name}")

        while True:
            choice = await self.get_user_input("Выберите список для удаления (номер) или 0 для отмены: ")

            if choice == "0":
                print("Операция отменена")
                # Очищаем экран и возвращаемся в меню управления пользователями
                import os
                os.system('clear' if os.name != 'nt' else 'cls')
                print("\n" + "="*50)
                print("УПРАВЛЕНИЕ СПИСКАМИ ПОЛЬЗОВАТЕЛЕЙ")
                print("="*50)
                print("1. Ввести список пользователей (через запятую)")
                print("2. Импорт из списка")
                print("3. Вывести существующие списки")
                print("4. Удалить список пользователей")
                print("0. Назад в главное меню")
                print("-"*50)
                return

            try:
                list_index = int(choice) - 1
                if 0 <= list_index < len(list_names):
                    list_to_delete = list_names[list_index]

                    # Подтверждение удаления
                    confirm = await self.get_user_input(
                        f"Вы уверены, что хотите удалить список '{list_to_delete}'? (y/n): ",
                        required=False, default="n"
                    )

                    if confirm.lower() in ['y', 'yes', 'да', 'д']:
                        if self.user_list_manager.delete_user_list(list_to_delete):
                            print(f"✅ Список '{list_to_delete}' успешно удален")
                            # Очищаем экран и возвращаемся в меню управления пользователями
                            import os
                            os.system('clear' if os.name != 'nt' else 'cls')
                            print("\n" + "="*50)
                            print("УПРАВЛЕНИЕ СПИСКАМИ ПОЛЬЗОВАТЕЛЕЙ")
                            print("="*50)
                            print("1. Ввести список пользователей (через запятую)")
                            print("2. Импорт из списка")
                            print("3. Вывести существующие списки")
                            print("4. Удалить список пользователей")
                            print("0. Назад в главное меню")
                            print("-"*50)
                        else:
                            print(f"❌ Ошибка при удалении списка '{list_to_delete}'")
                    else:
                        print("Операция отменена")

                    return
                else:
                    print(f"❌ Выберите номер от 1 до {len(list_names)}")
            except ValueError:
                print("❌ Введите номер списка или 0 для отмены")

    async def manage_server_connections(self):
        """Управление подключениями к серверам Proxmox"""
        # Очищаем экран перед показом подменю
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        print("\n" + "="*60)
        print("УПРАВЛЕНИЕ ПОДКЛЮЧЕНИЯМИ К СЕРВЕРАМ PROXMOX")
        print("="*60)
        print("1. Создать новое подключение")
        print("2. Удалить существующее подключение")
        print("3. Показать список подключений")
        print("0. Назад в главное меню")
        print("-"*60)

        while True:
            choice = await self.get_user_input("Выберите действие: ")

            if choice == "0":
                print("Возврат в главное меню...")
                break
            elif choice == "1":
                await self.create_server_connection()
            elif choice == "2":
                await self.delete_server_connection()
            elif choice == "3":
                await self.show_server_list()
                print("\nНажмите Enter для продолжения...")
                input()
                # Очищаем экран и показываем меню снова
                import os
                os.system('clear' if os.name != 'nt' else 'cls')
                print("\n" + "="*60)
                print("УПРАВЛЕНИЕ ПОДКЛЮЧЕНИЯМИ К СЕРВЕРАМ PROXMOX")
                print("="*60)
                print("1. Создать новое подключение")
                print("2. Удалить существующее подключение")
                print("3. Показать список подключений")
                print("0. Назад в главное меню")
                print("-"*60)
            else:
                print("Неверный выбор. Попробуйте еще раз.")

    async def create_server_connection(self):
        """Создание нового подключения к серверу"""
        # Очищаем экран перед созданием подключения
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        print("\n📝 Создание нового подключения к серверу Proxmox")
        new_config = await self.create_new_connection_interactive()

        if new_config:
            print(f"💾 Подключение '{new_config.get('name')}' сохранено в конфигурацию")
        else:
            print("❌ Не удалось создать подключение")

    async def delete_server_connection(self):
        """Удаление существующего подключения"""
        # Очищаем экран перед удалением подключения
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

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
                # Очищаем экран и возвращаемся в меню управления подключениями
                import os
                os.system('clear' if os.name != 'nt' else 'cls')
                print("\n" + "="*60)
                print("УПРАВЛЕНИЕ ПОДКЛЮЧЕНИЯМИ К СЕРВЕРАМ PROXMOX")
                print("="*60)
                print("1. Создать новое подключение")
                print("2. Удалить существующее подключение")
                print("3. Показать список подключений")
                print("0. Назад в главное меню")
                print("-"*60)
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

    async def run_server_selection_wizard(self) -> Optional[Dict[str, Any]]:
        """Мастер выбора/создания сервера"""
        # Очищаем экран для лучшего отображения
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        print("🚀 Мастер настройки подключений к Proxmox")

        while True:
            # Показываем список серверов
            available_servers = await self.show_server_list()

            if available_servers:
                # Предлагаем выбрать существующий сервер
                selected_server = await self.select_server_interactive(available_servers)
                if selected_server:
                    # Возвращаем конфигурацию выбранного сервера
                    server_config = self.connection_manager.get_server_config(selected_server)
                    if server_config:
                        return server_config

            # Создаем новое подключение
            print("\n📝 Создание нового подключения...")
            new_config = await self.create_new_connection_interactive()

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
                    # Очищаем экран перед повторной попыткой
                    import os
                    os.system('clear' if os.name != 'nt' else 'cls')
                    print("🔄 Повторная попытка создания подключения...")

    async def run(self, config: Dict):
        """Запуск главного цикла меню"""
        self.is_running = True

        print("🚀 Запуск системы развертывания стендов ВМ")

        try:
            while self.is_running:
                await self.show_main_menu()
                choice = await self.get_user_choice()

                if not await self.handle_menu_choice(choice, config):
                    break

        except KeyboardInterrupt:
            print("\n\nПолучен сигнал завершения. Выход...")

        finally:
            self.is_running = False
            print("👋 Система завершена")


async def run_menu(config: Dict):
    """Функция запуска меню для импорта в main.py"""
    menu = DeployStandMenu()

    # Инициализируем подключение к Proxmox при запуске меню
    print("🔌 Подключение к Proxmox серверу...")
    if await menu.initialize_proxmox_connection(config):
        print("✅ Успешное подключение к Proxmox")
    else:
        print("❌ Не удалось подключиться к Proxmox")
        print("Некоторые функции будут недоступны")

    # Запускаем главное меню
    await menu.run(config)
