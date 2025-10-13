"""
Утилиты развертывания виртуальных машин

Содержит общие вспомогательные функции, используемые всеми модулями развертывания:
генерация паролей, MAC адресов, проверка существования ресурсов и т.д.
"""

import logging
import secrets
import string
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class DeploymentUtils:
    """Утилиты для операций развертывания"""

    @staticmethod
    def generate_password(length: int = 8) -> str:
        """
        Сгенерировать случайный пароль для обучающих стендов

        Args:
            length: Длина пароля

        Returns:
            Случайный пароль из цифр
        """
        alphabet = string.digits  # Только цифры для простоты использования в обучении
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def generate_mac_address() -> str:
        """
        Сгенерировать случайный MAC адрес

        Returns:
            MAC адрес в формате XX:XX:XX:XX:XX:XX
        """
        mac = [0x52, 0x54, 0x00]  # QEMU/Libvirt prefix
        mac.extend(secrets.randbelow(256) for _ in range(3))
        return ':'.join(f'{b:02x}' for b in mac)

    @staticmethod
    def generate_ecorouter_mac() -> str:
        """
        Сгенерировать MAC адрес для ecorouter устройств

        Использует специальный диапазон: 1C:87:76:40:XX:XX

        Returns:
            MAC адрес для ecorouter в формате XX:XX:XX:XX:XX:XX
        """
        mac = [0x1C, 0x87, 0x76, 0x40]  # Ecorouter OUI prefix
        mac.extend(secrets.randbelow(256) for _ in range(2))  # Случайные 2 байта
        return ':'.join(f'{b:02x}' for b in mac)

    @staticmethod
    def extract_pool_name(user: str) -> str:
        """
        Извлечь имя пула из имени пользователя

        Args:
            user: Имя пользователя в формате user@pve

        Returns:
            Имя пула (часть до @)
        """
        return user.split('@')[0] if '@' in user else user

    @staticmethod
    def extract_user_realm(user: str) -> str:
        """
        Извлечь realm из имени пользователя

        Args:
            user: Имя пользователя в формате user@pve

        Returns:
            Realm пользователя (часть после @) или 'pve' по умолчанию
        """
        return user.split('@')[1] if '@' in user else 'pve'

    @staticmethod
    def build_user_name(pool_name: str, realm: str = 'pve') -> str:
        """
        Собрать полное имя пользователя из пула и realm

        Args:
            pool_name: Имя пула
            realm: Realm пользователя

        Returns:
            Полное имя пользователя в формате pool@realm
        """
        return f"{pool_name}@{realm}"

    @staticmethod
    def validate_machine_name(name: str) -> bool:
        """
        Проверить корректность имени виртуальной машины

        Args:
            name: Имя для проверки

        Returns:
            True если имя корректное
        """
        if not name or len(name) > 40:  # Proxmox ограничение
            return False

        # Допустимые символы: буквы, цифры, дефис, подчеркивание
        import re
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))

    @staticmethod
    def sanitize_machine_name(name: str) -> str:
        """
        Очистить имя машины от недопустимых символов

        Args:
            name: Исходное имя

        Returns:
            Очищенное имя
        """
        import re
        # Заменить недопустимые символы на дефис
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '-', name)
        # Убедиться что имя не пустое
        return sanitized if sanitized else f"vm-{int(secrets.randbelow(10000))}"

    @staticmethod
    def get_next_vmid(proxmox_client) -> int:
        """
        Получить следующий доступный VMID используя Proxmox API

        Args:
            proxmox_client: Клиент Proxmox

        Returns:
            Следующий доступный VMID
        """
        try:
            # Использовать встроенный метод Proxmox API для получения следующего VMID
            nextid_response = proxmox_client.api.cluster.nextid.get()
            next_vmid = int(nextid_response)

            logger.info(f"Получен следующий VMID от Proxmox API: {next_vmid}")
            return next_vmid

        except Exception as e:
            logger.warning(f"Ошибка получения следующего VMID через API: {e}")
            # Fallback: ручной поиск доступного VMID
            try:
                # Начать поиск с VMID 200 (избежать использования VMID шаблонов)
                start_vmid = 200

                # Проверка доступности VMID начиная с 200
                while True:
                    try:
                        # Попытаться получить информацию о VM с таким ID
                        vm_info = proxmox_client.api.cluster.resources.get(type='vm', vmid=start_vmid)
                        if vm_info:
                            # VM существует, попробовать следующий ID
                            start_vmid += 1
                            continue
                        else:
                            # VM не существует, можно использовать этот ID
                            logger.info(f"Найден доступный VMID (fallback): {start_vmid}")
                            return start_vmid
                    except:
                        # VM не существует (ошибка получения информации)
                        logger.info(f"VMID {start_vmid} доступен (ошибка API)")
                        return start_vmid

            except Exception as fallback_error:
                logger.error(f"Ошибка fallback метода получения VMID: {fallback_error}")
                # Final fallback: использовать timestamp-based VMID
                import time
                base_vmid = int(time.time()) % 100000 + 1000
                logger.warning(f"Используем timestamp-based VMID: {base_vmid}")
                return base_vmid

    @staticmethod
    def wait_for_task_completion(proxmox_client, task_id: str, node: str,
                                timeout: int = 300) -> bool:
        """
        Ожидать завершения задачи Proxmox

        Args:
            proxmox_client: Клиент Proxmox
            task_id: ID задачи
            node: Нода выполнения
            timeout: Таймаут ожидания в секундах

        Returns:
            True если задача завершилась успешно
        """
        import time

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                status = proxmox_client.api.nodes(node).tasks(task_id).status.get()
                task_status = status.get('status')

                if task_status == 'stopped':
                    exit_code = status.get('exitstatus', 1)
                    return exit_code == 'OK'
                elif task_status == 'running':
                    time.sleep(2)  # Проверять каждые 2 секунды
                    continue
                else:
                    logger.error(f"Неизвестный статус задачи {task_id}: {task_status}")
                    return False

            except Exception as e:
                logger.error(f"Ошибка проверки статуса задачи {task_id}: {e}")
                time.sleep(2)
                continue

        logger.error(f"Таймаут ожидания задачи {task_id}")
        return False

    @staticmethod
    def cleanup_on_failure(user: str, pool: str = None, vms: List[int] = None):
        """
        Очистка ресурсов при неудачном развертывании

        Args:
            user: Имя пользователя для очистки
            pool: Имя пула для очистки
            vms: Список VMID для удаления
        """
        logger.info(f"Начинается очистка ресурсов для пользователя {user}")

        # Здесь должна быть логика очистки
        # Пока только логирование
        if pool:
            logger.info(f"Очистка пула: {pool}")
        if vms:
            logger.info(f"Удаление VM: {vms}")
        if user:
            logger.info(f"Удаление пользователя: {user}")

    @staticmethod
    def reload_node_network(proxmox_client, node: str) -> bool:
        """
        Перезагрузить сетевые адаптеры ноды

        Args:
            proxmox_client: Клиент Proxmox
            node: Имя ноды

        Returns:
            True если перезагрузка успешна
        """
        try:
            logger.info(f"🔄 Перезагрузка сети ноды {node}...")

            # Выполнить перезагрузку сети через Proxmox API
            # Правильный endpoint: PUT /api2/json/nodes/{node}/network
            response = proxmox_client.api.nodes(node).network.put()

            logger.info(f"✅ Сеть ноды {node} успешно перезагружена")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка перезагрузки сети ноды {node}: {e}")
            return False

    @staticmethod
    def format_deployment_summary(results: Dict[str, str]) -> str:
        """
        Форматировать результаты развертывания для вывода

        Args:
            results: Результаты развертывания {пользователь: пароль}

        Returns:
            Отформатированная строка с результатами
        """
        if not results:
            return "❌ Развертывание не удалось"

        success_count = len(results)
        summary = [f"✅ Развертывание завершено. Создано пользователей: {success_count}"]
        summary.append("")
        summary.append(f"{'Пользователь'"<20"} {'Пароль'"<15"}")
        summary.append("-" * 35)

        for user, password in results.items():
            summary.append(f"{user:<20} {password:<15}")

        return "\n".join(summary)
