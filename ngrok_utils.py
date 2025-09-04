import os
import shutil
import subprocess
import sys
import time


def localizar_ngrok():
    ngrok_path = shutil.which("ngrok")
    if ngrok_path:
        return ngrok_path
    if sys.platform.startswith("win"):
        caminhos_possiveis = [
            r"C:\ngrok\ngrok.exe",
            os.path.expanduser("~\\ngrok\\ngrok.exe"),
            os.path.join(os.getcwd(), "ngrok.exe"),
        ]
    else:
        caminhos_possiveis = [
            "/usr/local/bin/ngrok",
            os.path.expanduser("~/ngrok"),
            os.path.join(os.getcwd(), "ngrok"),
        ]
    for caminho in caminhos_possiveis:
        if os.path.exists(caminho) and os.access(caminho, os.X_OK):
            return caminho
    raise FileNotFoundError("O executável 'ngrok' não foi encontrado. Adicione ao PATH ou especifique o caminho.")


def localizar_configuracao_ngrok():
    arquivo_ngrok = "ngrok.yml"
    if os.path.exists(arquivo_ngrok):
        return os.path.abspath(arquivo_ngrok)
    raise FileNotFoundError("O arquivo ngrok.yml não foi encontrado.")


def start_ngrok():
    ngrok_path = localizar_ngrok()
    config_path = localizar_configuracao_ngrok()
    subprocess.run([ngrok_path, "start", "--config", config_path, "app"], check=True)


def start_ngrok_threaded(delay_seconds: int = 2):
    import threading

    thread = threading.Thread(target=start_ngrok, daemon=True)
    thread.start()
    time.sleep(delay_seconds)
    return thread


