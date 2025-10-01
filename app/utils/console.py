from colorama import init, Fore, Style

init(autoreset=True)

def info(msg: str):
    print(f"{Fore.CYAN}ℹ {msg}{Style.RESET_ALL}")

def success(msg: str):
    print(f"{Fore.GREEN}✅ {msg}{Style.RESET_ALL}")

def warn(msg: str):
    print(f"{Fore.YELLOW}⚠ {msg}{Style.RESET_ALL}")

def error(msg: str):
    print(f"{Fore.RED}✖ {msg}{Style.RESET_ALL}")

def title(msg: str):
    print(f"{Style.BRIGHT}{Fore.MAGENTA}{msg}{Style.RESET_ALL}")

def emphasize(value: str) -> str:
    return f"{Style.BRIGHT}{Fore.CYAN}{value}{Style.RESET_ALL}"

def kv(label: str, value: str):
    print(f"{Fore.BLUE}{label}:{Style.RESET_ALL} {Style.BRIGHT}{Fore.WHITE}{value}{Style.RESET_ALL}")


