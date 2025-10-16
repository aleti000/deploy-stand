# Краткое руководство по использованию VLAN

## Пример конфигурации

Файл `data/configs/test.yml` содержит пример правильного использования VLAN:

```yaml
machines:
- device_type: linux
  full_clone: false
  name: gw              # Первая машина
  networks:
  - bridge: vmbr0
  - bridge: hq          # Алиас без VLAN - НЕ использует tag
  template_node: pve1
  template_vmid: 100

- device_type: linux
  full_clone: false
  name: hq-server       # Вторая машина
  networks:
  - bridge: hq.100      # Тот же алиас с VLAN 100 - использует tag=100
  template_node: pve1
  template_vmid: 100
```

## Что происходит при развертывании

1. **Анализ сетей**: Система анализирует все алиасы и определяет, что алиас `hq` используется с VLAN в одной из машин
2. **Создание VLAN-aware bridge**: Создается bridge `vmbr1000` с параметрами `bridge_vlan_aware=yes` и `type=bridge`
3. **Настройка интерфейсов**:
   - VM `gw`: `model=virtio,bridge=vmbr1000,firewall=1` (без tag)
   - VM `hq-server`: `model=virtio,bridge=vmbr1000,tag=100,firewall=1` (с tag=100)

## Ключевые правила

- **VLAN только с одной стороны**: VLAN указывается только в конфигурации машины, где нужен тег
- **Общий bridge**: Все машины с одинаковыми алиасами используют один bridge
- **Автоматическое создание**: Bridge создается автоматически как VLAN-aware, если хотя бы один алиас содержит VLAN

## Тестирование

Запустите тест для проверки функционала:

```bash
python3 test_vlan.py
```

## Результаты

После развертывания:
- Создается VLAN-aware bridge `vmbr1000`
- Машина `gw` подключается к bridge без VLAN тега
- Машина `hq-server` подключается к тому же bridge с тегом VLAN 100
