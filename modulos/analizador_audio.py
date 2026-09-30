"""
analizador_audio.py

Módulo especializado en análisis y normalización adaptativa de señales de audio.
Sustituye la normalización estática Min-Max por un modelo adaptativo basado en
la distribución estadística del VOD (percentiles o Z-Score), evitando distorsiones
por golpes de micrófono, ruidos impulsivos o silencios técnicos prolongados.
"""

from pathlib import Path
import math
import sys
from typing import Sequence
import numpy as np
from pydub import AudioSegment


def normalizar_volumen_adaptativo(
    volumenes: Sequence[float] | np.ndarray,
    metodo: str = "percentil",
    percentil_base: float = 50.0,
    percentil_techo: float = 95.0,
    z_score_techo: float = 2.0,
    umbral_silencio_dbfs: float = -60.0,
    descartar_silencio_stats: bool = True
) -> list[float]:
    """
    Normaliza adaptativamente una serie temporal de volumen en dBFS al rango [0.0, 1.0].

    A diferencia del Min-Max simple (que colapsa la dinámica ante un golpe de micrófono
    a 0 dBFS o ante silencios profundos a -100 dBFS), este algoritmo ancla la referencia
    en el volumen habitual del streamer y escala progresivamente hacia los picos significativos:

    1. Umbral base (p50 / mediana o media mu):
       Representa el volumen de habla habitual del creador (valores cercanos o inferiores -> ~0.0).
    2. Techo adaptativo (p90 - p95 o k*sigma en Z-Score):
       Representa gritos, risas o momentos destacados (escalan progresivamente hacia 1.0).
    3. Saturación / Recorte (np.clip(..., 0.0, 1.0)):
       Descarta outliers extremos (golpes de micro) impidiendo que aplasten el resto del VOD.
    4. Protección contra división por cero si el audio es plano.

    Parámetros:
        volumenes: Serie de valores de volumen (dBFS o RMS).
        metodo: "percentil" (recomendado por robustez ante outliers) o "zscore".
        percentil_base: Percentil para el habla habitual (defecto: 50.0, mediana).
        percentil_techo: Percentil para el techo adaptativo (defecto: 95.0).
        z_score_techo: Número de desviaciones estándar para alcanzar 1.0 en modo Z-Score (defecto: 2.0).
        umbral_silencio_dbfs: Umbral para descartar silencios técnicos profundos al calcular estadísticas.
        descartar_silencio_stats: Si True, ignora silencios prolongados para no arrastrar la mediana hacia abajo.

    Retorna:
        list[float]: Lista de puntuaciones normalizadas en el rango [0.0, 1.0].
    """
    if volumenes is None or len(volumenes) == 0:
        return []

    arr = np.asarray(volumenes, dtype=np.float64)

    # Si todos los elementos son idénticos o es un array de 1 elemento, evitamos divisiones
    if len(arr) == 1:
        return [0.0]

    # Determinamos la muestra de datos para calcular estadísticas de habla habitual.
    # Si un VOD tiene 30 minutos de mute o silencio absoluto (-100 dBFS), la mediana de todo
    # el array podría caer en el silencio en vez del habla real del streamer.
    # Por tanto, filtramos las muestras activas si hay suficiente información.
    if descartar_silencio_stats:
        muestras_activas = arr[arr > umbral_silencio_dbfs]
        min_muestras_requeridas = max(5, int(len(arr) * 0.05))
        if len(muestras_activas) >= min_muestras_requeridas:
            datos_stats = muestras_activas
        else:
            datos_stats = arr
    else:
        datos_stats = arr

    if metodo == "zscore":
        mu = float(np.mean(datos_stats))
        sigma = float(np.std(datos_stats))

        # Audio plano o variación nula
        if sigma <= 1e-6:
            return [0.0] * len(arr)

        # z = (volumen - mu) / sigma
        # El habla habitual (z <= 0) queda anclada a 0.0
        # Aumentos por encima de mu escalan hacia 1.0 al alcanzar z_score_techo
        z = (arr - mu) / sigma
        divisor = z_score_techo if z_score_techo > 1e-6 else 1.0
        scores = z / divisor
    else:
        # Método por percentiles (defecto, óptimo y no paramétrico)
        base = float(np.percentile(datos_stats, percentil_base))
        techo = float(np.percentile(datos_stats, percentil_techo))
        rango = techo - base

        # Audio plano o sin dinámica por encima del habla habitual
        if rango <= 1e-6:
            return [0.0] * len(arr)

        scores = (arr - base) / rango

    # Recorte estricto al rango [0.0, 1.0]
    scores_clipeados = np.clip(scores, 0.0, 1.0)
    return [round(float(s), 4) for s in scores_clipeados]


def suavizar_media_movil(
    serie: np.ndarray | Sequence[float],
    ventana: int = 5
) -> np.ndarray:
    """
    Aplica suavizado temporal por media móvil (Moving Average) mediante convolución uniforme.

    Penaliza ruidos o golpes secos aislados de 1 segundo (ej. un golpe accidental al micrófono)
    y realza bloques sostenidos de intensidad emocional (risas, gritos o celebraciones continuadas).

    Parámetros:
        serie: Array o secuencia temporal de valores numéricos (habitualmente en el rango [0.0, 1.0]).
        ventana: Ancho de la ventana de suavizado en segundos (defecto: 5).

    Retorna:
        np.ndarray: Serie temporal suavizada preservando la longitud original del array y recortada a [0.0, 1.0].
    """
    if serie is None:
        return np.array([], dtype=np.float64)

    try:
        arr = np.asarray(serie, dtype=np.float64)
    except (ValueError, TypeError):
        return np.array([], dtype=np.float64)

    # Casos borde defensivos: array vacío, ventana no válida o longitud menor que la ventana
    if arr.size == 0:
        return arr

    if ventana <= 1 or arr.size < ventana:
        return np.clip(arr, 0.0, 1.0)

    # Convolución uniforme con mode='same' para preservar exactamente la longitud original
    kernel = np.ones(ventana, dtype=np.float64) / ventana
    suavizado = np.convolve(arr, kernel, mode="same")

    return np.clip(suavizado, 0.0, 1.0)


def extraer_volumen_dbfs(
    ruta_audio: str | Path,
    limite_segundos: int | None = None,
    piso_silencio_dbfs: float = -100.0,
    tamano_ventana_ms: int = 1000
) -> list[float]:
    """
    Extrae la serie temporal de dBFS por segundo de un archivo de audio (m4a, mp3, wav...).

    Parámetros:
        ruta_audio: Ruta al archivo de audio.
        limite_segundos: Opcional, segundos máximos a analizar desde el inicio.
        piso_silencio_dbfs: Valor de sustitución para silencios absolutos (-inf).
        tamano_ventana_ms: Longitud de cada ventana de análisis en ms (defecto: 1000 ms = 1 Hz).

    Retorna:
        list[float]: Lista con el volumen RMS en dBFS para cada segundo.
    """
    ruta = Path(ruta_audio)
    if not ruta.exists():
        raise FileNotFoundError(f"Archivo de audio no encontrado: '{ruta}'")

    print(f"[AnalizadorAudio] Cargando audio: {ruta.name}...")
    formato = ruta.suffix.lstrip(".").lower() or "m4a"
    audio = AudioSegment.from_file(ruta, format=formato)

    duracion_segundos = len(audio) // tamano_ventana_ms
    segundos_totales = (
        min(duracion_segundos, limite_segundos)
        if limite_segundos is not None
        else duracion_segundos
    )

    print(
        f"[AnalizadorAudio] Duración: {duracion_segundos}s "
        f"({duracion_segundos / 3600:.2f} h). Analizando {segundos_totales}s..."
    )

    valores_dbfs: list[float] = []

    for seg in range(segundos_totales):
        inicio = seg * tamano_ventana_ms
        fin = inicio + tamano_ventana_ms

        ventana = audio[inicio:fin]
        dbfs = ventana.dBFS

        # Pydub devuelve -inf ante silencio absoluto o ausencia de señal
        if math.isinf(dbfs) or dbfs < piso_silencio_dbfs:
            dbfs = piso_silencio_dbfs

        valores_dbfs.append(round(dbfs, 2))

        if (seg + 1) % 500 == 0 or (seg + 1) == segundos_totales:
            pct = ((seg + 1) / segundos_totales) * 100
            print(f"[AnalizadorAudio] Progreso audio: {seg + 1}/{segundos_totales}s ({pct:.1f}%)")

    return valores_dbfs


def analizar_volumen(
    fuente: str | Path | Sequence[float] | np.ndarray,
    limite_segundos: int | None = None,
    piso_silencio_dbfs: float = -100.0,
    normalizar: bool = False,
    metodo: str = "percentil",
    percentil_base: float = 50.0,
    percentil_techo: float = 95.0,
    z_score_techo: float = 2.0,
    umbral_silencio_dbfs: float = -60.0
) -> list[float]:
    """
    Función unificada de análisis de volumen.

    Soporta dos modalidades de uso:
    1. Si 'fuente' es una ruta de archivo (str o Path):
       - Extrae la serie temporal de dBFS por segundo (estructura consumida por pipeline y PuntoTemporal).
       - Si 'normalizar=True', aplica la normalización adaptativa directamente.
    2. Si 'fuente' es una secuencia o array numérico (serie de dBFS existente):
       - Aplica la normalización adaptativa sobre los datos recibidos devolviendo puntuaciones en [0.0, 1.0].

    Retorna:
        list[float]: Serie temporal resultante (dBFS o puntuaciones normalizadas [0.0, 1.0]).
    """
    if isinstance(fuente, (str, Path)):
        valores_dbfs = extraer_volumen_dbfs(
            ruta_audio=fuente,
            limite_segundos=limite_segundos,
            piso_silencio_dbfs=piso_silencio_dbfs
        )
        if normalizar:
            return normalizar_volumen_adaptativo(
                valores_dbfs,
                metodo=metodo,
                percentil_base=percentil_base,
                percentil_techo=percentil_techo,
                z_score_techo=z_score_techo,
                umbral_silencio_dbfs=umbral_silencio_dbfs
            )
        return valores_dbfs

    # Caso en el que 'fuente' ya es una serie numérica de volúmenes
    return normalizar_volumen_adaptativo(
        volumenes=fuente,
        metodo=metodo,
        percentil_base=percentil_base,
        percentil_techo=percentil_techo,
        z_score_techo=z_score_techo,
        umbral_silencio_dbfs=umbral_silencio_dbfs
    )


class AnalizadorAudio:
    """
    Clase orquestadora para el análisis acústico y normalización estadística de volumen.
    Diseñada para integrarse directamente con ProcesadorSenales y SelectorMomentos.
    """
    def __init__(
        self,
        ruta_audio: str | Path | None = None,
        piso_silencio_dbfs: float = -100.0,
        metodo_normalizacion: str = "percentil",
        percentil_base: float = 50.0,
        percentil_techo: float = 95.0,
        z_score_techo: float = 2.0,
        umbral_silencio_dbfs: float = -60.0
    ):
        self.ruta_audio = Path(ruta_audio) if ruta_audio is not None else None
        self.piso_silencio_dbfs = piso_silencio_dbfs
        self.metodo_normalizacion = metodo_normalizacion
        self.percentil_base = percentil_base
        self.percentil_techo = percentil_techo
        self.z_score_techo = z_score_techo
        self.umbral_silencio_dbfs = umbral_silencio_dbfs

    def analizar_volumen(
        self,
        ruta_audio: str | Path | None = None,
        limite_segundos: int | None = None,
        normalizar: bool = False
    ) -> list[float]:
        """
        Analiza el audio y extrae la serie temporal de dBFS por segundo.
        Compatible con la interfaz esperada por ProcesadorSenales y modulos/pipeline.py.
        """
        archivo = ruta_audio or self.ruta_audio
        if archivo is None:
            raise ValueError("No se ha especificado ninguna ruta de audio para analizar.")

        return analizar_volumen(
            fuente=archivo,
            limite_segundos=limite_segundos,
            piso_silencio_dbfs=self.piso_silencio_dbfs,
            normalizar=normalizar,
            metodo=self.metodo_normalizacion,
            percentil_base=self.percentil_base,
            percentil_techo=self.percentil_techo,
            z_score_techo=self.z_score_techo,
            umbral_silencio_dbfs=self.umbral_silencio_dbfs
        )

    def procesar_audio(self, limite_segundos: int | None = None) -> list[float]:
        """Alias para máxima compatibilidad con ProcesadorSenales.procesar_audio()."""
        return self.analizar_volumen(limite_segundos=limite_segundos, normalizar=False)

    def suavizar(self, serie: np.ndarray | Sequence[float], ventana: int = 5) -> np.ndarray:
        """Aplica suavizado temporal por media móvil sobre la serie proporcionada."""
        return suavizar_media_movil(serie=serie, ventana=ventana)

    def normalizar(
        self,
        volumenes: Sequence[float] | np.ndarray,
        suavizar: bool = False,
        ventana_suavizado: int = 5
    ) -> list[float]:
        """Normaliza una serie de dBFS aplicando el esquema adaptativo y opcionalmente suavizado."""
        norm = normalizar_volumen_adaptativo(
            volumenes=volumenes,
            metodo=self.metodo_normalizacion,
            percentil_base=self.percentil_base,
            percentil_techo=self.percentil_techo,
            z_score_techo=self.z_score_techo,
            umbral_silencio_dbfs=self.umbral_silencio_dbfs
        )
        if suavizar:
            suavizado = suavizar_media_movil(norm, ventana=ventana_suavizado)
            return [round(float(s), 4) for s in suavizado]
        return norm


if __name__ == "__main__":
    # Demostración del comportamiento adaptativo vs Min-Max tradicional
    print("=== Test de Normalización Adaptativa vs Min-Max ===")

    # Simulación de un streamer:
    # 80 segundos de habla habitual en torno a -25 dBFS
    # 15 segundos de emoción/risas entre -20 dBFS y -15 dBFS
    # 4 segundos de grito a -12 dBFS
    # 1 segundo de golpe de micrófono extremo a 0.0 dBFS (outlier)
    habla = [-25.0] * 80
    risas = [-20.0, -18.0, -16.0] * 5
    grito = [-12.0] * 4
    golpe_micro = [0.0]  # Outlier aislado

    serie_prueba = habla + risas + grito + golpe_micro

    # Normalización Min-Max tradicional:
    min_v, max_v = min(serie_prueba), max(serie_prueba)
    rango_mm = max_v - min_v
    min_max_norm = [(v - min_v) / rango_mm for v in serie_prueba]

    # Normalización Adaptativa:
    adaptativa_norm = normalizar_volumen_adaptativo(serie_prueba, metodo="percentil")

    print(f"Total segundos simulados: {len(serie_prueba)}")
    print(f"Pico extremo (golpe micro): {max(serie_prueba)} dBFS")
    print(f"Habla habitual: -25.0 dBFS")
    print(f"Grito del streamer: -12.0 dBFS")
    print("-" * 50)
    print("Comparativa de puntuaciones obtenidas:")
    print(f"  Habla (-25 dBFS)  -> Min-Max: {min_max_norm[0]:.2f} | Adaptativa: {adaptativa_norm[0]:.2f}")
    print(f"  Risa  (-16 dBFS)  -> Min-Max: {min_max_norm[82]:.2f} | Adaptativa: {adaptativa_norm[82]:.2f}")
    print(f"  Grito (-12 dBFS)  -> Min-Max: {min_max_norm[95]:.2f} | Adaptativa: {adaptativa_norm[95]:.2f}")
    print(f"  Golpe (  0 dBFS)  -> Min-Max: {min_max_norm[-1]:.2f} | Adaptativa: {adaptativa_norm[-1]:.2f}")
    print("-" * 50)
    print("Conclusión:")
    print("En Min-Max, el grito (-12 dBFS) solo obtiene 0.52 porque el golpe de micro aplastó la escala.")
    print("En Adaptativa, el grito alcanza 1.00 destacando el momento, mientras el habla habitual queda en 0.00.")
