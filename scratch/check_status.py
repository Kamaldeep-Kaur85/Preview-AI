import subprocess

git_cmd = r"C:\Users\sai\AppData\Local\GitHubDesktop\app-3.5.7\resources\app\git\cmd\git.exe"

res = subprocess.run([git_cmd, "status"], capture_output=True, text=True)
print("GIT STATUS:")
print(res.stdout)

res2 = subprocess.run([git_cmd, "diff", "--stat"], capture_output=True, text=True)
print("GIT DIFF STAT:")
print(res2.stdout)
