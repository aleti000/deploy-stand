# core/api_client.py
from proxmoxer import ProxmoxAPI
from config.settings import (
    PROXMOX_HOST,
    PROXMOX_USER,
    PROXMOX_PASSWORD,
    VERIFY_SSL
)

class ProxmoxClient:
    def __init__(self):
        try:
            self.client = ProxmoxAPI(
                host=PROXMOX_HOST,
                user=PROXMOX_USER,
                password=PROXMOX_PASSWORD,
                verify_ssl=VERIFY_SSL
            )
            # Тест подключения
            self.client.nodes.get()
        except Exception as e:
            raise ConnectionError(f"Не удалось подключиться к Proxmox: {e}")