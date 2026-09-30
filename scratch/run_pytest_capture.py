import subprocess

res = subprocess.run([r"D:\conda\python.exe", "-m", "pytest", r"tests/unit/test_gui_startup_and_context_menu.py", "-v"], capture_output=True, text=True)
print("STDOUT:")
print(res.stdout)
print("STDERR:")
print(res.stderr)
print(f"RETURNCODE: {res.returncode}")
