import subprocess

git_cmd = r"C:\Users\sai\AppData\Local\GitHubDesktop\app-3.5.7\resources\app\git\cmd\git.exe"

res = subprocess.run([git_cmd, "diff", "-U10", "app/main.py"], capture_output=True, text=True, encoding="utf-8", errors="replace")
diff_lines = res.stdout.splitlines()

with open("scratch/diff_5939.txt", "w", encoding="utf-8") as out:
    for i in range(max(0, 5900), min(len(diff_lines), 6200)):
        out.write(diff_lines[i] + "\n")

print("Written to scratch/diff_5939.txt")
