# config/settings.py
PROXMOX_HOST = "192.168.122.201"  # без https:// и :8006
PROXMOX_USER = "root@pam"           # или другой пользователь
PROXMOX_PASSWORD = "toor"

PROXMOX_NODE = "SRV1-PVE"                # имя ноды

VERIFY_SSL = False  # False если самоподписанный сертификат