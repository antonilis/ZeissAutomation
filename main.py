import subprocess
import time

# Ścieżki
zen_exe = r"C:\Program Files\Zeiss\ZEN\ZEN.exe"
macro_path = r"C:\Temp\ExampleMacro.czmac"
result_path = r"C:\Temp\macro_result.txt"

# Usuń stary wynik (jeśli istnieje)
import os
if os.path.exists(result_path):
    os.remove(result_path)

# Odpal ZEN z makrem
subprocess.Popen([zen_exe, "/RunMacro", macro_path])

# Czekaj aż makro zapisze wynik
while not os.path.exists(result_path):
    time.sleep(1)

# Odczytaj wynik
with open(result_path, "r") as f:
    result = int(f.read().strip())

print("Wynik z makra:", result)
