import subprocess, time, os

socket = "/home/cerveau/mpv-socket"
try:
    os.remove(socket)
except:
    pass

p = subprocess.Popen([
    "mpv",
    "--idle=yes",
    f"--input-ipc-server={socket}"
])

print("mpv lancé, attente...")
time.sleep(2)

print("socket existe ?", os.path.exists(socket))
