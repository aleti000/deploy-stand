# ui/menu.py
def show_main_menu():
    print("\n" + "="*40)
    print("    УПРАВЛЕНИЕ ВИРТУАЛЬНЫМИ МАШИНАМИ")
    print("="*40)
    print("1. Создать одну ВМ")
    print("2. Выход")
    return input("\nВыберите действие: ").strip()

def prompt_for_vm_name():
    return input("Введите имя для новой ВМ: ").strip()