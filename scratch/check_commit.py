import subprocess

git_cmd = r"C:\Users\sai\AppData\Local\GitHubDesktop\app-3.5.7\resources\app\git\cmd\git.exe"

res = subprocess.run([git_cmd, "show", "48701ab:app/main.py"], capture_output=True, text=True, encoding="utf-8", errors="replace")
lines = res.stdout.splitlines()
print(f"Total lines in commit: {len(lines)}")
for i, line in enumerate(lines):
    if "context_menu" in line.lower():
        print(f"{i+1}: {line}")
