import subprocess

res = subprocess.run([r"D:\conda\python.exe", "-m", "pytest", r"tests/unit/test_theme_and_navigation.py::test_gui_window_theme_switching_and_navigation", "-v"], capture_output=True, text=True)
print("STDOUT:", res.stdout)
print("STDERR:", res.stderr)
print(f"RETURNCODE: {res.returncode}")
