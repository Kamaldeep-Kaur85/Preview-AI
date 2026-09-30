import subprocess

git_cmd = r"C:\Users\sai\AppData\Local\GitHubDesktop\app-3.5.7\resources\app\git\cmd\git.exe"

res = subprocess.run([git_cmd, "log", "-S", "_show_context_menu", "--oneline"], capture_output=True, text=True)
print("COMMITS with _show_context_menu:")
print(res.stdout)

res2 = subprocess.run([git_cmd, "log", "-G", "context_menu", "--oneline"], capture_output=True, text=True)
print("COMMITS with context_menu:")
print(res2.stdout)
