# deploy-stand
Скрипт для автоматического развертывания виртуальных машин в кластере Proxmox.

<details>
<summary>## Структура проекта</summary>
- `main.py` — точка входа

- `app/` — исходный код

  - `app/ui/cli_menus.py` — CLI-меню

  - `app/core/` — логика (Proxmox, deploy, users, config)

  - `app/utils/console.py` — цветной вывод
  
- `data/` — сохраняются файлы конфигурации (`deployment_config.yml`, `users_list.yml`)

Запуск:
```bash
python3 main.py
```
</details>