#!/usr/bin/env python3
"""
Deploy Stand - Система развертывания виртуальных стендов для студентов на базе Proxmox
Единая точка входа в приложение
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Добавляем корневую папку проекта в Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Импорт модулей
from modules.menu import run_menu
from modules.connection_manager import get_connection_manager
from modules.proxmox_client import create_proxmox_client

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('deploy_stand.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """Главная функция приложения"""
    try:
        # Очищаем экран при запуске
        import os
        os.system('clear' if os.name != 'nt' else 'cls')

        logger.info("Запуск Deploy Stand - системы развертывания стендов ВМ")

        # Создаем меню для работы с мастером подключений
        from modules.menu import DeployStandMenu
        menu = DeployStandMenu()

        # Запускаем мастер выбора/создания сервера
        server_config = await menu.run_server_selection_wizard()

        if not server_config:
            logger.error("Не удалось получить конфигурацию сервера")
            print("❌ Не удалось настроить подключение к серверу Proxmox")
            return

        # Объединяем конфигурацию из файла с переменными окружения
        config = {
            'host': os.getenv('PROXMOX_HOST', server_config.get('host', 'localhost')),
            'user': os.getenv('PROXMOX_USER', server_config.get('user', 'root@pam')),
            'password': os.getenv('PROXMOX_PASSWORD', server_config.get('password', '')),
            'token_name': server_config.get('token_name', ''),
            'token_value': server_config.get('token_value', ''),
            'verify_ssl': os.getenv('PROXMOX_VERIFY_SSL', str(server_config.get('verify_ssl', False))).lower() == 'true',
            'port': server_config.get('port', 8006),
            'server_name': server_config.get('name', 'Без имени'),
            'server_description': server_config.get('description', '')
        }

        logger.info(f"Используется сервер: {server_config.get('name', 'Без имени')} - {server_config.get('host')}")

        # Проверяем подключение к Proxmox перед запуском меню
        print("🔧 Проверка подключения к Proxmox...")
        try:
            test_client = create_proxmox_client(config)
            if test_client.connect():
                print("✅ Подключение к Proxmox успешно")
                test_client.disconnect()  # Закрываем тестовое подключение
            else:
                print("❌ Не удалось подключиться к Proxmox")
                print("Проверьте настройки подключения")
                return
        except Exception as e:
            logger.error(f"Ошибка тестирования подключения: {e}")
            print(f"❌ Ошибка подключения: {e}")
            return

        # Запуск модуля меню
        await run_menu(config)

        logger.info("Приложение завершено успешно")

    except KeyboardInterrupt:
        logger.info("Получен сигнал завершения")
    except Exception as e:
        logger.error(f"Ошибка при запуске приложения: {e}")
        raise


if __name__ == "__main__":
    # Запуск приложения
    asyncio.run(main())
