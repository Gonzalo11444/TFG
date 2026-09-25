"""
seleccion_temporal.py

Selección temporal de momentos destacados mediante puntaje
y recorte específico de fragmentos de vídeo con yt-dlp
"""

from pathlib import Path
from dataclasses import dataclass, replace
import shutil
import subprocess
import sys

# Import de la estructura de la Fase 2
try:
    from modulos.procesamiento_senales import PuntoTemporal, ProcesadorSenales
except ImportError:
    from procesamiento_senales import PuntoTemporal, ProcesadorSenales


@dataclass(frozen=True, slots=True)
class CandidatoClip:
    segundo_inicio: int
    segundo_fin: int
    puntuacion: float
    ruta_video: Path | None = None


class SelectorMomentos:
    def __init__(
        self,
        peso_audio: float = 0.5,
        peso_chat: float = 0.5,
        duracion_clip: int = 40,
        margen_previo: int = 25,
        exclusion_deadzone: int = 60
    ):
        self.peso_audio = peso_audio
        self.peso_chat = peso_chat
        self.duracion_clip = duracion_clip
        self.margen_previo = margen_previo
        self.exclusion_deadzone = exclusion_deadzone

    def _normalizar_min_max(self, valores: list[float]) -> list[float]: #Escala los datos al rango [0, 1]
        if not valores:
            return []

        min_v = min(valores)
        max_v = max(valores)
        rango = max_v - min_v

        # Si todos los valores son iguales, evitamos dividir por cero
        if rango == 0:
            resultado = []
            for _ in valores:
                resultado.append(0.0)
            return resultado

        # Escalado normal
        resultado = []
        for v in valores:
            valor_normalizado = (v - min_v) / rango
            resultado.append(valor_normalizado)
        return resultado

    def calcular_puntuaciones(self, serie: list[PuntoTemporal]) -> list[float]: #Obtiene la puntuación combinada de las señales
        if not serie:
            return []

        # Separamos las dos señales en listas independientes
        volumenes = []
        chats = []
        for p in serie:
            volumenes.append(p.volumen_dbfs)
            chats.append(float(p.mensajes_chat))

        # Normalizamos ambas para que compitan en la misma escala (0 a 1)
        norm_audio = self._normalizar_min_max(volumenes)
        norm_chat = self._normalizar_min_max(chats)

        # Calculamos la media ponderada segundo a segundo
        scores = []
        for na, nc in zip(norm_audio, norm_chat):
            puntuacion = (self.peso_audio * na) + (self.peso_chat * nc)
            scores.append(round(puntuacion, 4))

        return scores

    def seleccionar_clips(self, serie: list[PuntoTemporal], top_k: int = 5) -> list[CandidatoClip]: #Selecciona los mejores clips usando una tecnica llamada Supresión No Máxima (NMS)  
        if not serie:
            return []

        total_segundos = len(serie)
        scores_originales = self.calcular_puntuaciones(serie)
        
        # Copiamos la lista de scores para poder tachar los ya usados
        scores_disponibles = scores_originales.copy()

        candidatos: list[CandidatoClip] = []

        for _ in range(top_k):
            # 1. Búsqueda clásica del pico más alto disponible
            pico_idx = -1
            mejor_score = -1.0

            for i in range(total_segundos):
                if scores_disponibles[i] > mejor_score:
                    mejor_score = scores_disponibles[i]
                    pico_idx = i

            # Si ya no quedan segundos con señal positiva, dejamos de buscar
            if pico_idx == -1 or mejor_score <= 0.0:
                break

            # 2. Delimitamos el inicio y fin del clip alrededor del pico
            inicio = max(0, pico_idx - self.margen_previo)
            fin = min(total_segundos, inicio + self.duracion_clip)

            # Ajuste en caso de bordes finales para mantener la duración
            if fin - inicio < self.duracion_clip and inicio > 0:
                inicio = max(0, fin - self.duracion_clip)

            candidato = CandidatoClip(
                segundo_inicio=inicio,
                segundo_fin=fin,
                puntuacion=round(scores_originales[pico_idx], 3),
                ruta_video=None
            )
            candidatos.append(candidato)

            # 3. Supresión No Máxima (NMS): Ponemos a -1.0 un radio par no sacar mismos clips
            deadzone_inicio = max(0, pico_idx - self.exclusion_deadzone)
            deadzone_fin = min(total_segundos, pico_idx + self.exclusion_deadzone + 1)

            for i in range(deadzone_inicio, deadzone_fin):
                scores_disponibles[i] = -1.0

        # Ordenamos los clips cronológicamente
        candidatos.sort(key=lambda c: c.segundo_inicio)
        return candidatos


class DescargadorFragmentos:
    def __init__(
        self,
        carpeta_salida: str | Path = "downloads/candidatos",
        ruta_ytdlp: str = "yt-dlp"
    ):
        self.carpeta_salida = Path(carpeta_salida)
        self.ruta_ytdlp = self._validar_binario(ruta_ytdlp)
        self.carpeta_salida.mkdir(parents=True, exist_ok=True)

    def _validar_binario(self, binario: str) -> Path:
        encontrado = shutil.which(binario) or Path(binario)
        if isinstance(encontrado, str):
            encontrado = Path(encontrado)

        if not encontrado.exists() and shutil.which(str(encontrado)) is None:
            raise FileNotFoundError(f"yt-dlp no encontrado en: '{binario}'.")
        return encontrado

    def descargar_clip(
        self,
        url_vod: str,
        clip: CandidatoClip,
        prefijo: str = "candidato"
    ) -> CandidatoClip:
        """Descarga únicamente el intervalo [segundo_inicio, segundo_fin] de Twitch."""
        nombre_archivo = f"{prefijo}_{clip.segundo_inicio}s_{clip.segundo_fin}s.mp4"
        ruta_destino = self.carpeta_salida / nombre_archivo

        if ruta_destino.exists():
            print(f"Clip existente en disco: {ruta_destino.name}")
            return replace(clip, ruta_video=ruta_destino)

        seccion_tiempo = f"*{clip.segundo_inicio}-{clip.segundo_fin}"
        #Comando con sus parametros
        comando = [
            str(self.ruta_ytdlp),
            "--download-sections", seccion_tiempo,
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", str(ruta_destino),
            "--no-playlist",
            url_vod.strip()
        ]

        print(f"Descargando fragmento [{clip.segundo_inicio}s -> {clip.segundo_fin}s]...")
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            check=False
        )

        if resultado.returncode != 0:
            raise RuntimeError(f"Error yt-dlp:\n{resultado.stderr.strip()}")

        print(f"Clip guardado: {ruta_destino}")
        return replace(clip, ruta_video=ruta_destino)

    def descargar_todos(
        self,
        url_vod: str,
        clips: list[CandidatoClip]
    ) -> list[CandidatoClip]:
        #Descarga secuencialmente todos los clips de la lista
        clips_descargados = []
        contador = 1

        for clip in clips:
            prefijo = f"clip_{contador:02d}"
            clip_actualizado = self.descargar_clip(url_vod, clip, prefijo=prefijo)
            clips_descargados.append(clip_actualizado)
            contador += 1

        return clips_descargados


if __name__ == "__main__":
    AUDIO_REAL = Path("downloads/audio.m4a")
    CHAT_REAL = Path("downloads/chat.json")
    URL_VOD = "https://www.twitch.tv/videos/2873857636"

    # None para procesar todo el VOD, o un número en segundos para pruebas rápidas
    LIMITE_SEGUNDOS = 120

    try:
        print("Procesando señales (Fase 2)...")
        procesador = ProcesadorSenales(AUDIO_REAL, CHAT_REAL)
        serie_real = procesador.sincronizar(limite_segundos=LIMITE_SEGUNDOS)

        print("\nSeleccionando clips candidatos...")
        selector = SelectorMomentos(
            peso_audio=0.5,
            peso_chat=0.5,
            duracion_clip=30,
            margen_previo=15,
            exclusion_deadzone=45
        )

        num_clips = 1 if LIMITE_SEGUNDOS else 5
        candidatos = selector.seleccionar_clips(serie_real, top_k=num_clips)

        print(f"Candidatos detectados: {len(candidatos)}")
        for idx, c in enumerate(candidatos, start=1):
            print(f"  Clip {idx}: [{c.segundo_inicio}s -> {c.segundo_fin}s] (Puntuación: {c.puntuacion})")

        print("\nDescargando clips con yt-dlp...")
        descargador = DescargadorFragmentos(carpeta_salida="downloads/candidatos")
        clips_descargados = descargador.descargar_todos(URL_VOD, candidatos)

        print("\nDescargas completadas:")
        for c in clips_descargados:
            print(f"- {c.ruta_video}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
