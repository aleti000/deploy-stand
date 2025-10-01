# deploy-stand
Скрипт для автоматического развертывания виртуальных машин в кластере Proxmox. В AltPVE скрипт не тестировался!!!

<details>
<summary>
Особенности проекта
</summary>

1. Стенды для студентов разворачиваются из существующих шаблонов VM.

2. Поддержка равномерного развертывания стендов на множество нод в кластере proxmox.

3. Количество машин и схема сети настраивается пользователем и позволяет легко собрать стенд любой сложности и развернуть на любое количество пользователей.

4. В настоящее время поддерживается только создание связанных клонов VM.

</details>

<details>
<summary>
Структура проекта
</summary>

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

<details>
<summary>
Требования:
</summary>

Установить зависимости, для запуска скриптов:

```bash 
pip3 install -r requirements.txt
```
</details>

<details>
<summary>
Инструкция по настройке сети:
</summary>

При указывании сетевого адаптера необходимо указывать vmbr0 - для интернета. (В данном релизе не поддерживаются другие адаптеры которые можно указать явно)

Пример:

```
machines:
- device_type: ecorouter
  name: eco
  networks:
  - bridge: vmbr0
  - bridge: hq
  template_node: SRV1-PVE
  template_vmid: 100
- device_type: linux
  name: lin
  networks:
  - bridge: hq
  template_node: SRV1-PVE
  template_vmid: 101
```
В данном конфигурационном файле hq означает сеть которая будет создана (vmbr1000+), hq является псевдонимом будущего созданного моста.

</details>

<details>
<summary>
Балгодарности:
</summary>

Данный скрипт полностью сформирован с использованием ИИ Cursor. Примерное время от написания промпта до релиза проекта - 5 часов.

</details>