import sys
import shutil
import subprocess
from pathlib import Path

class TwitchDescarga:
    #Clase encargada de validar y coordinar la descarga de audio de Twitch empleando TwitchDownloaderCLI

    def __init__(self, path: str = "TwitchDownloaderCLI.exe", carpeta_salida : str = "downloads"):
        self.carpeta_salida = Path(carpeta_salida)
        self.cli_path = self._localizar_binario(path)
        self.carpeta_salida.mkdir(parents=True, exist_ok=True)

    def _localizar_binario(self, path: str) -> Path:
        encontrado = shutil.which(path) #Busca el binario en el PATH del sistema
        ruta = Path(encontrado) if encontrado else Path(path)   #Si no lo encuentra, asume que está en la ruta directa que le pasamos

        if not ruta.exists():
            raise FileNotFoundError(f"Ejecutable no encontrado en: '{ruta.resolve()}'.")
        
        return ruta


    def descargar_audio(self, url_twitch: str, hilos: int = 8) -> Path:
        if not url_twitch or not url_twitch.strip():
            raise ValueError("La URL de Twitch no puede estar vacía.")

        url_twitch = url_twitch.strip()

        archivo_salida = self.carpeta_salida / "audio.m4a"

        comando = [
            str(self.cli_path),            # Programa a ejecutar: TwitchDownloaderCLI.exe
            "videodownload",                # indica que queremos descargar vídeo/audio de un VOD
            "--id", url_twitch.strip(),     # Identificador: URL o ID del vídeo de Twitch a procesar
            "-o", str(archivo_salida),     
            "-q", "Audio Only",             # Quality: solo audio
            "-t", str(hilos)                # Threads 
        ]
        print(f"[*] Iniciando descarga de audio hacia: {archivo_salida}...")
        # subprocess.Popen lanza el proceso en segundo plano conectado a tuberías
        proceso = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,       # Capturamos la salida estándar
            stderr=subprocess.STDOUT,     # Redirigimos los errores al mismo flujo
            text=True,                    # Para recibir cadenas de texto (str) en vez de bytes
            encoding="utf-8",             
            bufsize=1                     # Lee línea a línea según se produce
        )

        # Leemos la salida
        for linea in proceso.stdout:
            linea_limpia = linea.strip()
            if linea_limpia:
                print(f"  [CLI] {linea_limpia}")
        # Se espera a que el proceso concluya y se recoge el código de salida
        proceso.wait()
        if proceso.returncode != 0:
            raise RuntimeError(
                f"Error: La descarga de audio falló con código de salida: {proceso.returncode}"
            )
        print(f"Audio descargado con éxito en: {archivo_salida}")
        return archivo_salida


    def descargar_chat(self, url_twitch: str) -> Path: #Descarga el chat del VOD en formato JSON estructurado
        if not url_twitch or not url_twitch.strip():
            raise ValueError("La URL de Twitch no puede estar vacía.")

        url_twitch = url_twitch.strip()
        archivo_salida = self.carpeta_salida / "chat.json"

        # Comando
        comando = [
            str(self.cli_path),        # Programa a ejecutar: TwitchDownloaderCLI.exe
            "chatdownload",             # Subcomando: indica que queremos descargar el chat del directo
            "--id", url_twitch,         # Identificador: URL o ID del vídeo del cual extraer los mensajes
            "-o", str(archivo_salida),  
        ]

        print(f"\n Iniciando descarga de chat hacia: {archivo_salida}...")

        proceso = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1
        )

        for linea in proceso.stdout:
            linea_limpia = linea.strip()
            if linea_limpia:
                print(f"  [CLI] {linea_limpia}")

        proceso.wait()

        if proceso.returncode != 0:
            raise RuntimeError(
                f"¡Error! La descarga de chat falló con código de salida: {proceso.returncode}"
            )

        print(f"Chat descargado con éxito en: {archivo_salida}")
        return archivo_salida


if __name__ == "__main__":
    vod = input("URL o ID del VOD de Twitch: ").strip()
    if not vod:
        print("URL no válida.")
        sys.exit(1)
    try:
        descargador = TwitchDescarga()
        ruta_audio = descargador.descargar_audio(vod)
        ruta_chat = descargador.descargar_chat(vod)
        print("\nDescargas completadas:")
        print(f"- Audio: {ruta_audio.resolve()}")
        print(f"- Chat:  {ruta_chat.resolve()}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
