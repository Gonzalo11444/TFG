"""
procesamiento_senales.py

Procesamiento y sincronización de señales de audio (volumen dBFS) 
y actividad de chat de Twitch en ventanas de 1 segundo.
"""

from pathlib import Path
from dataclasses import dataclass
from collections import Counter
import json
import math
import sys
from pydub import AudioSegment


@dataclass(frozen=True, slots=True)     #Objeto inmutable
class PuntoTemporal:
    segundo: int
    volumen_dbfs: float
    mensajes_chat: int


class ProcesadorSenales:    
    def __init__(
        self,
        ruta_audio: str | Path,
        ruta_chat: str | Path,
        piso_silencio_dbfs: float = -100.0
    ):
        self.ruta_audio = Path(ruta_audio)
        self.ruta_chat = Path(ruta_chat)
        self.piso_silencio_dbfs = piso_silencio_dbfs

        self._validar_archivos()

    def _validar_archivos(self) -> None:
        if not self.ruta_audio.exists():
            raise FileNotFoundError(f"Archivo de audio no encontrado: '{self.ruta_audio}'")
        if not self.ruta_chat.exists():
            raise FileNotFoundError(f"Archivo de chat no encontrado: '{self.ruta_chat}'")

    def procesar_audio(self, limite_segundos: int | None = None) -> list[float]:    #Calcula el volumen RMS en dBFS para cada segundo de audio, los silencios se meten en piso_silencio
        print(f"Cargando audio: {self.ruta_audio.name}...")
        audio = AudioSegment.from_file(self.ruta_audio, format="m4a")

        duracion_segundos = len(audio) // 1000
        segundos_totales = (
            min(duracion_segundos, limite_segundos)
            if limite_segundos is not None
            else duracion_segundos
        )

        print(f"Duración: {duracion_segundos}s ({duracion_segundos / 3600:.2f} h). Analizando {segundos_totales}s...")

        valores_dbfs: list[float] = []

        for seg in range(segundos_totales):
            inicio = seg * 1000
            fin = inicio + 1000

            ventana = audio[inicio:fin]
            dbfs = ventana.dBFS

            # En partes de silencio absoluto pydub devuelve -inf
            if math.isinf(dbfs) or dbfs < self.piso_silencio_dbfs:
                dbfs = self.piso_silencio_dbfs

            valores_dbfs.append(round(dbfs, 2))

            if (seg + 1) % 500 == 0 or (seg + 1) == segundos_totales:
                pct = ((seg + 1) / segundos_totales) * 100
                print(f"Progreso audio: {seg + 1}/{segundos_totales}s ({pct:.1f}%)")

        return valores_dbfs

    def procesar_chat(self) -> dict[int, int]:#Lee el json y cuenta mensajes por segundo
        print(f"Procesando chat: {self.ruta_chat.name}...")
        with open(self.ruta_chat, "r", encoding="utf-8") as f:
            datos = json.load(f)

        comentarios = datos.get("comments", [])
        mensajes_por_segundo: Counter[int] = Counter()

        for c in comentarios:
            offset = c.get("content_offset_seconds")
            if offset is not None:
                seg = int(offset)
                if seg >= 0:
                    mensajes_por_segundo[seg] += 1

        print(f"Comentarios procesados: {len(comentarios)} en {len(mensajes_por_segundo)} segundos activos.")
        return dict(mensajes_por_segundo)


    def sincronizar(self, limite_segundos: int | None = None) -> list[PuntoTemporal]:   #Combina audio y chat en una serie temporal continua a 1 Hz
        audio_dbfs = self.procesar_audio(limite_segundos=limite_segundos)
        chat_conteo = self.procesar_chat()

        print("Sincronizando señales...")
        serie: list[PuntoTemporal] = []

        for t in range(len(audio_dbfs)):
            punto = PuntoTemporal(
                segundo=t,
                volumen_dbfs=audio_dbfs[t],
                mensajes_chat=chat_conteo.get(t, 0)
            )
            serie.append(punto)

        print(f"Sincronización finalizada: {len(serie)} puntos temporales generados.")
        return serie


if __name__ == "__main__":
    AUDIO = Path("downloads/audio.m4a")
    CHAT = Path("downloads/chat.json")

    # Limite en segundos para pruebas rápidas (None para procesar todo el VOD)
    LIMITE = None      

    try:
        procesador = ProcesadorSenales(AUDIO, CHAT)
        serie = procesador.sincronizar(limite_segundos=LIMITE)

        print("\nMuestra de resultados (primeros 20s):")
        print(f"{'Segundo':<8} | {'dBFS':<8} | {'Mensajes'}")
        print("-" * 30)
        for p in serie[:20]:
            print(f"{p.segundo:<8} | {p.volumen_dbfs:<8.2f} | {p.mensajes_chat}")

        volumenes = [p.volumen_dbfs for p in serie]
        print("-" * 30)
        print(f"Resumen ({len(serie)}s): max={max(volumenes):.2f} dBFS, min={min(volumenes):.2f} dBFS, pico_chat={max(p.mensajes_chat for p in serie)} msg/s")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
