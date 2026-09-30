import subprocess

git_cmd = r"C:\Users\sai\AppData\Local\GitHubDesktop\app-3.5.7\resources\app\git\cmd\git.exe"

res = subprocess.run([git_cmd, "show", "48701ab:app/main.py"], capture_output=True, text=True, encoding="utf-8", errors="replace")
lines = res.stdout.splitlines()

start = 3130
end = 3300
with open("scratch/old_menu_extracted.py", "w", encoding="utf-8") as out:
    for i in range(start, min(end, len(lines))):
        out.write(f"{i+1}: {lines[i]}\n")

print(f"Extracted lines {start+1} to {end} to scratch/old_menu_extracted.py")
