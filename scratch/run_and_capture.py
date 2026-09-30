import subprocess
import sys

res = subprocess.run([r"D:\conda\python.exe", r"D:\preview ai\scratch\test_all_interactions.py"], capture_output=True, text=True)
print("STDOUT:")
print(res.stdout)
print("STDERR:")
print(res.stderr)
print(f"RETURNCODE: {res.returncode}")
