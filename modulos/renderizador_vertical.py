"""
renderizador_vertical.py

Fase 5: Reencuadre y renderizado en formato vertical (9:16) con FFmpeg.
Soporta dos estilos de composición visual:
1. Fondo desenfocado (Blur): vídeo horizontal nítido centrado sobre un fondo desenfocado.
2. Pantalla dividida (Split Cámara + Gameplay): recorte de la región de la cámara
   y del juego, escalado a 1080px de ancho y apilado vertical para TikTok, Reels y Shorts.
"""

from pathlib import Path
from typing import Callable, Sequence
import subprocess
import shutil
import json
import time


class RenderizadorVertical:
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

        # Localizamos el binario de FFmpeg en el sistema
        self.ffmpeg = self.localizar_ffmpeg()
        if not self.ffmpeg:
            raise FileNotFoundError(
                "No se encontró FFmpeg. Asegúrate de tenerlo instalado y añadido al PATH del sistema."
            )

        # Carpeta destino para vídeos verticales 9:16
        if carpeta_salida is not None:
            self.carpeta_salida = Path(carpeta_salida)
        else:
            if Path("modulos/downloads").exists():
                self.carpeta_salida = Path("modulos/downloads/clips_verticales")
            else:
                self.carpeta_salida = Path("downloads/clips_verticales")

        self.carpeta_salida.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def localizar_ffmpeg() -> str | None:
        """Busca el ejecutable de ffmpeg en el PATH o en ubicaciones típicas del proyecto."""
        binario = shutil.which("ffmpeg")
        if binario:
            return binario

        posibles = [
            Path("ffmpeg.exe"),
            Path("bin/ffmpeg.exe"),
            Path("../ffmpeg.exe")
        ]
        for p in posibles:
            if p.exists():
                return str(p.resolve())
        return None

    def _crear_filtro_desenfoque(self) -> str:
        """
        Genera el pipeline filter_complex para composición 9:16 con fondo desenfocado (Blur).
        """
        # 1. Capa fondo: escala rellenando 1080x1920 y aplica desenfoque gaussiano/boxblur
        capa_fondo = (
            f"[0:v]scale={self.ancho}:{self.alto}:force_original_aspect_ratio=increase,"
            f"crop={self.ancho}:{self.alto},"
            rf"boxblur=luma_radius=min(h\,w)/20:luma_power=2[fondo]"
        )

        # 2. Capa frente: vídeo original nítido escalado a 1080px de ancho
        capa_frente = f"[0:v]scale={self.ancho}:-2[frente]"

        # 3. Superposición centrada vertical y horizontalmente
        superposicion = "[fondo][frente]overlay=(W-w)/2:(H-h)/2[salida_video]"

        return f"{capa_fondo};{capa_frente};{superposicion}"

    def _crear_filtro_split(
        self,
        cam_crop: tuple[float, float, float, float] | Sequence[float],
        game_crop: tuple[float, float, float, float] | Sequence[float],
        fondo: str = "blur"
    ) -> str:
        """
        Genera el pipeline filter_complex para composición 'Split' (Cámara superior + Gameplay inferior).

        Parámetros:
            cam_crop: (x, y, w, h) de la cámara (valores en [0.0, 1.0] o píxeles absolutos).
            game_crop: (x, y, w, h) del gameplay (valores en [0.0, 1.0] o píxeles absolutos).
            fondo: "blur" para fondo desenfocado o "black" para fondo negro sólido.
        """
        def formatear_crop(c: Sequence[float]) -> str:
            x, y, w, h = c[0], c[1], c[2], c[3]
            # Si los valores son relativos / normalizados en [0.0, 1.0]
            if w <= 1.0 and h <= 1.0:
                cw = max(0.02, min(1.0, float(w)))
                ch = max(0.02, min(1.0, float(h)))
                cx = max(0.0, min(1.0 - cw, float(x)))
                cy = max(0.0, min(1.0 - ch, float(y)))
                # trunc(.../2)*2 garantiza dimensiones pares requeridas por libx264/yuv420p
                return (
                    f"crop=w='trunc(in_w*{cw:.4f}/2)*2':"
                    f"h='trunc(in_h*{ch:.4f}/2)*2':"
                    f"x='trunc(in_w*{cx:.4f}/2)*2':"
                    f"y='trunc(in_h*{cy:.4f}/2)*2'"
                )
            # Si los valores son píxeles absolutos
            pw = max(32, int(w))
            ph = max(32, int(h))
            px = max(0, int(x))
            py = max(0, int(y))
            return (
                f"crop=w='trunc({pw}/2)*2':"
                f"h='trunc({ph}/2)*2':"
                f"x='trunc({px}/2)*2':"
                f"y='trunc({py}/2)*2'"
            )

        filtro_cam_crop = formatear_crop(cam_crop)
        filtro_game_crop = formatear_crop(game_crop)

        # 1. Recortar cámara manteniendo su relación de aspecto y escalar al ancho completo de 1080px
        flujo_cam = f"[0:v]{filtro_cam_crop},scale={self.ancho}:-2[cam]"

        # 2. Recortar gameplay manteniendo su relación de aspecto y escalar al ancho completo de 1080px
        flujo_game = f"[0:v]{filtro_game_crop},scale={self.ancho}:-2[game]"

        # 3. Apilar verticalmente: cámara en la parte superior (y=0) y gameplay directamente debajo
        apilado = "[cam][game]vstack=inputs=2[apilado]"

        # 4. Composición limpia sobre lienzo negro de 1080x1920 con la cámara anclada en y=0
        # pad añade fondo negro en la parte inferior si la suma de alturas es < 1920
        # crop asegura la resolución estricta 1080x1920 si el contenido supera la altura
        ajuste_lienzo = (
            f"[apilado]pad={self.ancho}:max({self.alto}\\,ih):0:0:black,"
            f"crop={self.ancho}:{self.alto}:0:0[salida_video]"
        )

        return f"{flujo_cam};{flujo_game};{apilado};{ajuste_lienzo}"

    def obtener_duracion(self, ruta_video: Path | str) -> float:
        """Obtiene la duración en segundos del archivo de vídeo mediante ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(ruta_video)
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return max(0.5, float(res.stdout.strip()))
        except Exception:
            return 10.0

    def extraer_fotograma(
        self,
        ruta_video: Path | str,
        segundo: float | None = None,
        ruta_salida: Path | str | None = None
    ) -> Path:
        """
        Extrae un fotograma del clip de vídeo. Si segundo es None, extrae automáticamente
        el fotograma medio (t = duracion / 2) para asegurar una captura representativa del clip activo.
        """
        video = Path(ruta_video).resolve()
        if not video.exists():
            raise FileNotFoundError(f"Vídeo no encontrado: {video}")

        if segundo is None:
            duracion = self.obtener_duracion(video)
            t_captura = max(0.5, duracion / 2.0)
        else:
            t_captura = max(0.0, float(segundo))

        if ruta_salida is not None:
            destino = Path(ruta_salida)
        else:
            destino = self.carpeta_salida / f"frame_{video.stem}_{int(t_captura*10)}.jpg"

        comando = [
            self.ffmpeg,
            "-y",
            "-ss", f"{t_captura:.2f}",
            "-i", str(video),
            "-vframes", "1",
            "-q:v", "2",
            str(destino)
        ]

        proceso = subprocess.run(comando, capture_output=True, text=True, check=False)
        if proceso.returncode != 0 or not destino.exists():
            # Intento en el segundo 0 si el clip es muy corto
            comando[2] = "0.0"
            subprocess.run(comando, capture_output=True, check=False)

        return destino

    def reencuadrar_clip(
        self,
        ruta_video: Path | str,
        nombre_archivo: str | None = None,
        modo: str = "blur",
        cam_crop: tuple[float, float, float, float] | None = None,
        game_crop: tuple[float, float, float, float] | None = None,
        fondo_split: str = "black"
    ) -> Path:
        """
        Reencuadra un clip a formato vertical 9:16 (1080x1920).

        Parámetros:
            ruta_video: Ruta al clip original.
            nombre_archivo: Opcional, nombre del archivo resultante.
            modo: 'blur' (fondo desenfocado) o 'split' (pantalla dividida cámara + gameplay).
            cam_crop: Coordenadas de la cámara para split (x, y, w, h).
            game_crop: Coordenadas del gameplay para split (x, y, w, h).
            fondo_split: Fondo para el split ('black').
        """
        video = Path(ruta_video).resolve()
        if not video.exists():
            raise FileNotFoundError(f"No existe el vídeo: {video}")

        if nombre_archivo:
            salida = self.carpeta_salida / nombre_archivo
        else:
            sufijo = "_split" if modo == "split" else "_vertical"
            salida = self.carpeta_salida / f"{video.stem}{sufijo}.mp4"

        # Construcción del filtro según el modo seleccionado
        if modo == "split" and cam_crop is not None and game_crop is not None:
            filtro = self._crear_filtro_split(cam_crop=cam_crop, game_crop=game_crop, fondo=fondo_split)
        else:
            if modo == "split":
                print("[Renderizador] Aviso: Split solicitado sin coordenadas completas. Aplicando fondo desenfocado seguro.")
            filtro = self._crear_filtro_desenfoque()

        comando = [
            self.ffmpeg,
            "-y",
            "-i", str(video),
            "-filter_complex", filtro,
            "-map", "[salida_video]",
            "-map", "0:a?",
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

        proceso = subprocess.run(
            comando,
            capture_output=True,
            text=True
        )

        if proceso.returncode != 0:
            detalle_error = proceso.stderr[-800:] if proceso.stderr else "Error desconocido en FFmpeg"
            raise RuntimeError(f"Error al reencuadrar el vídeo con FFmpeg:\n{detalle_error}")

        return salida

    def procesar_clips_aprobados(
        self,
        ruta_json: Path | str | None = None,
        callback_progreso: Callable[[int, int, Path], None] | None = None,
        modo: str = "blur",
        cam_crop: tuple[float, float, float, float] | None = None,
        game_crop: tuple[float, float, float, float] | None = None,
        crops_por_clip: dict[str, dict] | None = None
    ) -> list[Path]:
        """
        Procesa secuencialmente todos los clips marcados en el JSON de clips aprobados.
        Permite usar coordenadas de split específicas por clip o la plantilla por defecto.
        """
        if ruta_json is not None:
            archivo_json = Path(ruta_json)
        else:
            if Path("modulos/downloads/clips_aprobados.json").exists():
                archivo_json = Path("modulos/downloads/clips_aprobados.json")
            else:
                archivo_json = Path("downloads/clips_aprobados.json")

        if not archivo_json.exists():
            print(f"[Renderizador] No se encontró el archivo de clips aprobados: {archivo_json}")
            return []

        with open(archivo_json, "r", encoding="utf-8") as f:
            clips = json.load(f)

        if not clips:
            print("[Renderizador] La lista de clips aprobados está vacía.")
            return []

        total = len(clips)
        videos_procesados: list[Path] = []

        print(f"[Renderizador] Renderizando {total} clips a formato vertical (Modo: {modo.upper()})...")

        for i in range(total):
            clip_info = clips[i]
            ruta = clip_info.get("archivo") or clip_info.get("ruta")
            if not ruta:
                continue

            archivo_video = Path(ruta)
            if not archivo_video.exists():
                print(f"[Renderizador] Vídeo no encontrado en disco: {archivo_video}")
                continue

            # Determinamos si este clip concreto tiene recorte personalizado
            nombre_archivo = archivo_video.name
            c_crop = cam_crop
            g_crop = game_crop

            if crops_por_clip:
                custom = (
                    crops_por_clip.get(nombre_archivo)
                    or crops_por_clip.get(str(archivo_video))
                    or crops_por_clip.get(str(archivo_video.resolve()))
                )
                if custom:
                    c_crop = custom.get("cam_crop", custom.get("cam", c_crop))
                    g_crop = custom.get("game_crop", custom.get("game", g_crop))

            print(f"[{i + 1}/{total}] Renderizando: {archivo_video.name}...")
            inicio = time.time()

            video_vertical = self.reencuadrar_clip(
                ruta_video=archivo_video,
                modo=modo,
                cam_crop=c_crop,
                game_crop=g_crop
            )
            segundos = time.time() - inicio

            print(f"   -> Listo en {segundos:.1f}s: {video_vertical.name}")
            videos_procesados.append(video_vertical)

            if callback_progreso is not None:
                callback_progreso(i + 1, total, video_vertical)

        return videos_procesados


if __name__ == "__main__":
    print("Probando RenderizadorVertical (Fase 5)...")
    try:
        renderizador = RenderizadorVertical()
        print(f"FFmpeg localizado: {renderizador.ffmpeg}")
        print(f"Carpeta salida:    {renderizador.carpeta_salida}")
    except Exception as e:
        print(f"Error: {e}")
