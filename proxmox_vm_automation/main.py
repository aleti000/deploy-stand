#!/usr/bin/env python3
from ui.menu import show_main_menu, prompt_for_vm_name
from modules.vm_manager import create_simple_vm

def main():
    while True:
        choice = show_main_menu()

        if choice == "1":
            name = prompt_for_vm_name()
            if name:
                create_simple_vm(name)
            else:
                print("❌ Имя не может быть пустым.")
        
        elif choice == "2":
            print("👋 Завершение работы. Пока!")
            break
        
        else:
            print("❌ Неверный выбор. Попробуйте снова.")

if __name__ == "__main__":
    main()