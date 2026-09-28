# procesamiento_video.py
#
# Fase 5: Reencuadre a formato vertical (9:16) con desenfoque de fondo.
# Convierte los clips horizontales de Twitch a vídeos de 1080x1920 listos
# para publicar en TikTok, Instagram Reels y YouTube Shorts usando FFmpeg.

from pathlib import Path
from typing import Callable
import subprocess
import shutil
import json
import time


class RenderizadorVertical:
    # Constructor: define resolución (1080x1920), velocidad de compresión y carpeta destino
    def __init__(
        self,
        carpeta_salida: str | Path | None = None,
        ancho: int = 1080,
        alto: int = 1920,
        fps: int | None = None,
        preset: str = "veryfast",
        crf: int = 22
    ):
        self.ancho = ancho
        self.alto = alto
        self.fps = fps
        self.preset = preset
        self.crf = crf

        # Comprobamos que FFmpeg esté en el sistema
        self.ffmpeg = shutil.which("ffmpeg")
        if not self.ffmpeg:
            raise FileNotFoundError(
                "No se encontró FFmpeg. Asegúrate de tenerlo instalado y en el PATH."
            )

        # Elegimos la carpeta donde se guardarán los vídeos verticales
        if carpeta_salida is not None:
            self.carpeta_salida = Path(carpeta_salida)
        else:
            if Path("modulos/downloads").exists():
                self.carpeta_salida = Path("modulos/downloads/clips_verticales")
            else:
                self.carpeta_salida = Path("downloads/clips_verticales")

        # Creamos la carpeta si aún no existe
        self.carpeta_salida.mkdir(parents=True, exist_ok=True)

    # Crea el filtro de FFmpeg para poner el fondo borroso y el vídeo nítido centrado
    def _crear_filtro_desenfoque(self) -> str:
        # 1. Fondo: ampliado para llenar los 1080x1920 y con efecto blur
        capa_fondo = (
            f"[0:v]scale={self.ancho}:{self.alto}:force_original_aspect_ratio=increase,"
            f"crop={self.ancho}:{self.alto},"
            rf"boxblur=luma_radius=min(h\,w)/20:luma_power=2[fondo]"
        )

        # 2. Vídeo frontal: escalado a 1080 de ancho manteniendo su proporción
        capa_frente = f"[0:v]scale={self.ancho}:-2[frente]"

        # 3. Superposición: colocamos el vídeo nítido en el centro del fondo
        superposicion = "[fondo][frente]overlay=(W-w)/2:(H-h)/2[salida_video]"

        return f"{capa_fondo};{capa_frente};{superposicion}"

    # Reencuadra un vídeo individual a vertical (9:16)
    def reencuadrar_clip(
        self,
        ruta_video: Path | str,
        nombre_archivo: str | None = None
    ) -> Path:
        video = Path(ruta_video).resolve()
        if not video.exists():
            raise FileNotFoundError(f"No existe el vídeo: {video}")

        # Si no nos dan nombre, le añadimos '_vertical' al final
        if nombre_archivo:
            salida = self.carpeta_salida / nombre_archivo
        else:
            salida = self.carpeta_salida / f"{video.stem}_vertical.mp4"

        # Preparamos el filtro y los comandos para FFmpeg
        filtro = self._crear_filtro_desenfoque()

        comando = [
            self.ffmpeg,
            "-y",                     # Sobrescribir si ya existe
            "-i", str(video),
            "-filter_complex", filtro,
            "-map", "[salida_video]", # Vídeo procesado con el filtro
            "-map", "0:a?",           # Audio original
            "-c:v", "libx264",
            "-preset", self.preset,
            "-crf", str(self.crf),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k"
        ]

        if self.fps is not None:
            comando.extend(["-r", str(self.fps)])

        comando.append(str(salida))

        # Lanzamos FFmpeg
        proceso = subprocess.run(
            comando,
            capture_output=True,
            text=True
        )

        if proceso.returncode != 0:
            detalle_error = proceso.stderr[-800:] if proceso.stderr else "Error en FFmpeg"
            raise RuntimeError(f"Error al reencuadrar el vídeo:\n{detalle_error}")

        return salida

    # Lee el archivo JSON con los clips aprobados y los reencuadra todos
    def procesar_clips_aprobados(
        self,
        ruta_json: Path | str | None = None,
        callback_progreso: Callable[[int, int, Path], None] | None = None
    ) -> list[Path]:
        # Buscamos el json de la fase 4
        if ruta_json is not None:
            archivo_json = Path(ruta_json)
        else:
            if Path("modulos/downloads/clips_aprobados.json").exists():
                archivo_json = Path("modulos/downloads/clips_aprobados.json")
            else:
                archivo_json = Path("downloads/clips_aprobados.json")

        if not archivo_json.exists():
            print(f"No se encontró el archivo: {archivo_json}")
            return []

        with open(archivo_json, "r", encoding="utf-8") as f:
            clips = json.load(f)

        if not clips:
            print("No hay clips en el JSON.")
            return []

        total = len(clips)
        videos_procesados = []

        print(f"Renderizando {total} clips a formato vertical...")

        # Bucle tradicional para procesar cada clip
        for i in range(total):
            clip_info = clips[i]
            ruta = clip_info.get("archivo")

            if not ruta:
                continue

            archivo_video = Path(ruta)
            if not archivo_video.exists():
                print(f"Vídeo no encontrado en disco: {archivo_video}")
                continue

            print(f"[{i + 1}/{total}] Procesando: {archivo_video.name}...")
            inicio = time.time()

            video_vertical = self.reencuadrar_clip(archivo_video)
            segundos = time.time() - inicio

            print(f"   -> Listo en {segundos:.1f}s: {video_vertical.name}")
            videos_procesados.append(video_vertical)

            if callback_progreso is not None:
                callback_progreso(i + 1, total, video_vertical)

        return videos_procesados


if __name__ == "__main__":
    print("Probando renderizado vertical (Fase 5)...")

    renderizador = RenderizadorVertical(preset="veryfast")
    print(f"Carpeta destino: {renderizador.carpeta_salida}")

    # Buscamos un clip para la prueba
    candidatos = list(Path("modulos/downloads/candidatos").glob("*.mp4"))
    if not candidatos:
        candidatos = list(Path("downloads/candidatos").glob("*.mp4"))

    if candidatos:
        clip_ejemplo = candidatos[0]
        print(f"Reencuadrando clip de prueba: {clip_ejemplo.name}")

        t0 = time.time()
        resultado = renderizador.reencuadrar_clip(clip_ejemplo)
        total_tiempo = time.time() - t0

        print(f"Clip vertical creado en: {resultado}")
        print(f"Tiempo empleado: {total_tiempo:.1f}s")
    else:
        print("No hay vídeos para probar.")
