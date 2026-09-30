import subprocess

git_cmd = r"C:\Users\sai\AppData\Local\GitHubDesktop\app-3.5.7\resources\app\git\cmd\git.exe"

res = subprocess.run([git_cmd, "diff", "-U5", "app/main.py"], capture_output=True, text=True, encoding="utf-8", errors="replace")
diff_lines = res.stdout.splitlines()

for i, line in enumerate(diff_lines):
    if "_show_context_menu" in line:
        print(f"Diff around line {i}:")
        for j in range(max(0, i-15), min(len(diff_lines), i+25)):
            print(diff_lines[j])
        print("="*60)
