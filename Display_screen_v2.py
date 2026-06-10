#!/usr/bin/env python3
import serial
import subprocess
import socket
import time
import sys
import os
import json
import signal

# ==========================
# CONFIGURATION
# ==========================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MPV_WORKDIR = SCRIPT_DIR  # /home/cerveau/Desktop

SERIAL_PORT = "/dev/ttyACM0"   # adapte si besoin
BAUDRATE = 9600

VIDEO_ROUGE = os.path.join(SCRIPT_DIR, "videos/V5_A.mp4")
VIDEO_VERT  = os.path.join(SCRIPT_DIR, "videos/V4_B.mp4")

MPV_SOCKET = "/tmp/mpv-socket"
MPV_LOG    = os.path.join(SCRIPT_DIR, "mpv_debug.log")


# ==========================
# OUTILS DEBUG
# ==========================

def debug_print_header():
    print("=======================================")
    print("  LANCEUR VIDÉO MPV - DEBUG")
    print("  SCRIPT_DIR :", SCRIPT_DIR)
    print("  MPV_WORKDIR:", MPV_WORKDIR)
    print("=======================================")


def check_video_file(path: str, label: str) -> bool:
    if not os.path.isfile(path):
        print(f"ERREUR: fichier vidéo pour {label} introuvable : {path}")
        return False
    if not os.access(path, os.R_OK):
        print(f"ERREUR: fichier vidéo pour {label} non lisible (permissions) : {path}")
        return False
    return True


# ==========================
# FONCTIONS MPV
# ==========================

def start_mpv():
    """Lance mpv avec IPC et log dans mpv_debug.log."""
    if os.path.exists(MPV_SOCKET):
        try:
            os.remove(MPV_SOCKET)
        except OSError as e:
            print(f"ERREUR: impossible de supprimer l'ancien socket {MPV_SOCKET} : {e}")
            sys.exit(1)

    cmd = [
    "mpv",
    "--no-config",
    "--idle=yes",
    "--force-window=yes",
    "--fullscreen",
    "--osc=no",        # pas d'interface violette
    "--osd-level=0",   # pas de texte
    "--vo=x11",        # sortie vidéo simple et compatible
    "--hwdec=no",      # pas de décodage matériel (évite certains bugs)
    "--video-rotate=90",
    f"--input-ipc-server={MPV_SOCKET}",
    ]


    print("INFO: lancement de mpv avec la commande :")
    print("     ", " ".join(cmd))
    print("INFO: dossier de travail mpv :", MPV_WORKDIR)
    print("INFO: log mpv ->", MPV_LOG)

    try:
        log_file = open(MPV_LOG, "w")
    except Exception as e:
        print(f"ERREUR: impossible d'ouvrir le fichier de log {MPV_LOG} : {e}")
        sys.exit(1)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=MPV_WORKDIR,
            stdout=log_file,
            stderr=subprocess.STDOUT
        )
    except FileNotFoundError:
        print("ERREUR: 'mpv' introuvable. Installe-le avec : sudo apt-get install mpv")
        sys.exit(1)
    except PermissionError as e:
        print(f"ERREUR: permission refusée pour lancer mpv : {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERREUR inattendue au lancement de mpv : {e}")
        sys.exit(1)

    return proc


def wait_for_mpv_socket(mpv_proc, timeout=5.0):
    """Attend la création du socket IPC et affiche le log si mpv meurt."""
    start = time.time()
    while time.time() - start < timeout:
        # mpv a-t-il crash ?
        ret = mpv_proc.poll()
        if ret is not None:
            print(f"ERREUR: mpv s'est terminé prématurément (code retour {ret}).")
            print(f"→ Regarde le log : {MPV_LOG}")
            if os.path.isfile(MPV_LOG):
                print("=== APERCU DE LA FIN DU LOG MPV ===")
                try:
                    with open(MPV_LOG, "r") as f:
                        lines = f.readlines()[-30:]
                    for l in lines:
                        print(l.rstrip())
                except Exception as e:
                    print(f"(Impossible de lire le log mpv: {e})")
            return False

        if os.path.exists(MPV_SOCKET):
            return True

        time.sleep(0.1)

    print(f"ERREUR: le socket mpv ({MPV_SOCKET}) n'a pas été créé dans les {timeout} secondes.")
    return False


def connect_mpv_socket():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(MPV_SOCKET)
    return sock


def mpv_command(sock, command_list):
    payload = json.dumps({"command": command_list})
    sock.sendall(payload.encode("utf-8") + b"\n")


# ==========================
# MAIN
# ==========================

def main():
    debug_print_header()

    ok_rouge = check_video_file(VIDEO_ROUGE, "ROUGE")
    ok_vert  = check_video_file(VIDEO_VERT,  "VERT")
    if not (ok_rouge and ok_vert):
        print("ERREUR: au moins une des vidéos est invalide.")
        sys.exit(1)

    mpv_proc = start_mpv()

    def handle_sigint(sig, frame):
        print("\nArrêt demandé, fermeture...")
        try:
            mpv_proc.terminate()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    if not wait_for_mpv_socket(mpv_proc):
        print("ERREUR: initialisation de mpv échouée.")
        try:
            mpv_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

    print("INFO: socket mpv prêt, connexion...")
    try:
        mpv_sock = connect_mpv_socket()
    except Exception as e:
        print(f"ERREUR: impossible de se connecter à mpv: {e}")
        try:
            mpv_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

    # Port série
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
        print(f"INFO: port série ouvert sur {SERIAL_PORT} à {BAUDRATE} bauds.")
    except serial.SerialException as e:
        print(f"ERREUR: impossible d'ouvrir {SERIAL_PORT} : {e}")
        mpv_sock.close()
        try:
            mpv_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

    print("=======================================")
    print("En attente de 'rouge' ou 'vert' sur le port USB...")
    print("Ctrl+C pour quitter.")
    print("=======================================")

    while True:
        # Vérifier que mpv est toujours vivant
        if mpv_proc.poll() is not None:
            print("ERREUR: mpv s'est arrêté pendant l'exécution.")
            if os.path.isfile(MPV_LOG):
                print("=== APERCU DE LA FIN DU LOG MPV ===")
                try:
                    with open(MPV_LOG, "r") as f:
                        lines = f.readlines()[-30:]
                    for l in lines:
                        print(l.rstrip())
                except Exception as e:
                    print(f"(Impossible de lire le log mpv: {e})")
            break

        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip().lower()

            if line:
                print(f"USB → '{line}'")

                if "rouge" in line:
                    print("ACTION: vidéo ROUGE")
                    mpv_command(mpv_sock, ["loadfile", VIDEO_ROUGE, "replace"])

                elif "vert" in line:
                    print("ACTION: vidéo VERT")
                    mpv_command(mpv_sock, ["loadfile", VIDEO_VERT, "replace"])

        except serial.SerialException as e:
            print(f"ERREUR série: {e}")
            time.sleep(1)
        except BrokenPipeError:
            print("ERREUR: connexion à mpv perdue (BrokenPipe).")
            break
        except Exception as e:
            print(f"ERREUR inattendue: {e}")
            time.sleep(0.5)

    print("Fermeture des ressources...")
    try:
        ser.close()
    except Exception:
        pass
    try:
        mpv_sock.close()
    except Exception:
        pass
    try:
        mpv_proc.terminate()
    except Exception:
        pass
    print("Programme terminé.")


if __name__ == "__main__":
    main()
