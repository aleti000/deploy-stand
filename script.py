#!/usr/bin/env python3
import module.user_from_file as user_from_file
import module.get_free_vmid as get_free_vmid
import module.create_vm as create_vm
import os

from proxmoxer import ProxmoxAPI
proxmox = ProxmoxAPI(
host= '192.168.100.5',
user='root@pam',
password='OsI7q3Z',
verify_ssl=False
)




def main():
    menu_options = {
        1: ("Создать ВМ для пользователей", create_vm.create_vms() ),
        2: ("Показать список всех ВМ", list_all_vms),
        3: ("Удалить ВМ по ID", delete_vm),
        4: ("Выход", exit_program)
    }

    while True:
        print("\n" + "="*40)
        print("       УПРАВЛЕНИЕ ВИРТУАЛЬНЫМИ МАШИНАМИ")
        print("="*40)

        for key, (desc, func) in menu_options.items():
            print(f"{key}. {desc}")

        try:
            choice = int(input("\nВыберите действие: "))
            if choice in menu_options:
                action = menu_options[choice][1]  # получаем функцию
                action()  # вызываем
                if choice == 4:  # если "выход"
                    break
            else:
                print("❌ Нет такого пункта. Попробуйте снова.")
        except ValueError:
            print("❌ Введите число.")
    

if __name__ == "__main__":
    main()