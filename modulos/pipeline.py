# pipeline.py
#
# Orquestador del pipeline completo de PrendeClips (Fases 1 a 4).
# Coordina en secuencia:
#   1. Descarga de audio y chat del VOD de Twitch (Fase 1)
#   2. Análisis y sincronización de señales a 1 Hz (Fase 2)
#   3. Selección de picos algorítmicos y recorte de vídeo con yt-dlp (Fase 3)
#   4. Clasificación semántica zero-shot con OpenAI CLIP (Fase 4)

from pathlib import Path
from typing import Callable
import shutil
import re
import json

# Importación flexible de los módulos del proyecto
try:
    from modulos.descarga_twitch import TwitchDescarga
    from modulos.procesamiento_senales import ProcesadorSenales
    from modulos.seleccion_temporal import (
        SelectorMomentos,
        DescargadorFragmentos,
        CandidatoClip
    )
    from modulos.clasificador_clip import ClasificadorVisual
except ImportError:
    from descarga_twitch import TwitchDescarga
    from procesamiento_senales import ProcesadorSenales
    from seleccion_temporal import (
        SelectorMomentos,
        DescargadorFragmentos,
        CandidatoClip
    )
    from clasificador_clip import ClasificadorVisual


class PipelineClips:
    # Constructor: inicializa rutas de trabajo y parámetros de recorte
    def __init__(
        self,
        carpeta_base: str | Path | None = None,
        top_k: int = 5,
        duracion_clip: int = 30,
        margen_previo: int = 15,
        exclusion_deadzone: int = 45
    ):
        # Localizamos el directorio raíz del proyecto
        self.directorio_raiz = Path(__file__).resolve().parents[1]

        # Carpeta base para almacenar descargas y resultados
        if carpeta_base is not None:
            self.carpeta_base = Path(carpeta_base).resolve()
        else:
            # Si ya existía modulos/downloads la usamos, si no creamos downloads en la raíz
            if (self.directorio_raiz / "modulos" / "downloads").exists():
                self.carpeta_base = self.directorio_raiz / "modulos" / "downloads"
            else:
                self.carpeta_base = self.directorio_raiz / "downloads"

        # Subcarpetas organizadas para clips y derivados
        self.carpeta_candidatos = self.carpeta_base / "candidatos"
        self.carpeta_verticales = self.carpeta_base / "clips_verticales"

        self.carpeta_base.mkdir(parents=True, exist_ok=True)
        self.carpeta_candidatos.mkdir(parents=True, exist_ok=True)
        self.carpeta_verticales.mkdir(parents=True, exist_ok=True)

        # Parámetros del algoritmo de selección de momentos
        self.top_k = top_k
        self.duracion_clip = duracion_clip
        self.margen_previo = margen_previo
        self.exclusion_deadzone = exclusion_deadzone

        # Localizamos el ejecutable de TwitchDownloaderCLI
        self.ruta_twitch_cli = self._localizar_twitch_cli()

    # Busca TwitchDownloaderCLI.exe en la raíz o en el PATH del sistema
    def _localizar_twitch_cli(self) -> Path:
        posibles = [
            self.directorio_raiz / "TwitchDownloaderCLI.exe",
            Path("TwitchDownloaderCLI.exe"),
            shutil.which("TwitchDownloaderCLI.exe")
        ]
        for p in posibles:
            if p and Path(p).exists():
                return Path(p).resolve()

        # Si no lo encuentra, devolvemos el nombre por si está en variables de entorno
        return Path("TwitchDownloaderCLI.exe")

    # Valida que el texto introducido corresponda a un VOD de Twitch o un ID numérico
    def validar_url_twitch(self, url: str) -> str:
        texto = url.strip()
        if not texto:
            raise ValueError("Por favor, introduce una URL o ID de un directo de Twitch.")

        # Si es solo números (ID directo de VOD)
        if texto.isdigit():
            return texto

        # Si es un enlace de Twitch, verificamos el formato básico
        if "twitch.tv" in texto:
            return texto

        # Si no encaja con ningún patrón habitual
        raise ValueError(
            "El formato no parece ser una URL válida de Twitch (ejemplo: https://www.twitch.tv/videos/123456789)"
        )

    # Ejecuta el flujo completo de punta a punta reportando el progreso a la interfaz
    def ejecutar(
        self,
        url_vod: str,
        callback_progreso: Callable[[str, float], None] | None = None
    ) -> list[CandidatoClip]:
        url_limpia = self.validar_url_twitch(url_vod)

        # Función auxiliar para notificar avance de forma segura
        def notificar(mensaje: str, porcentaje: float):
            print(f"[Pipeline] ({porcentaje * 100:.0f}%) {mensaje}")
            if callback_progreso is not None:
                callback_progreso(mensaje, porcentaje)

        # ---------------------------------------------------------------------
        # FASE 1: Descarga de Audio y Chat del VOD con TwitchDownloaderCLI
        # ---------------------------------------------------------------------
        notificar("Fase 1/4: Iniciando descarga del audio del VOD...", 0.05)

        descargador_twitch = TwitchDescarga(
            path=str(self.ruta_twitch_cli),
            carpeta_salida=str(self.carpeta_base)
        )

        try:
            ruta_audio = descargador_twitch.descargar_audio(url_limpia)
        except Exception as error_audio:
            raise RuntimeError(f"Error al descargar el audio de Twitch: {error_audio}")

        notificar("Fase 1/4: Descargando historial de mensajes del chat...", 0.18)

        try:
            ruta_chat = descargador_twitch.descargar_chat(url_limpia)
        except Exception as error_chat:
            raise RuntimeError(f"Error al descargar el chat de Twitch: {error_chat}")

        # ---------------------------------------------------------------------
        # FASE 2: Procesamiento y Sincronización de Señales Temporales
        # ---------------------------------------------------------------------
        notificar("Fase 2/4: Analizando volumen de audio (dBFS) y mensajes/segundo...", 0.28)

        try:
            procesador_senales = ProcesadorSenales(
                ruta_audio=ruta_audio,
                ruta_chat=ruta_chat
            )
            serie_temporal = procesador_senales.sincronizar()
        except Exception as error_senales:
            raise RuntimeError(f"Error en el análisis de señales de audio y chat: {error_senales}")

        if not serie_temporal:
            raise RuntimeError("No se generaron puntos temporales válidos en el análisis de señales.")

        # ---------------------------------------------------------------------
        # FASE 3: Selección de Momentos Clave y Recorte de Fragmentos con yt-dlp
        # ---------------------------------------------------------------------
        notificar("Fase 3/4: Detectando picos de intensidad con Supresión No Máxima...", 0.45)

        selector = SelectorMomentos(
            peso_audio=0.5,
            peso_chat=0.5,
            duracion_clip=self.duracion_clip,
            margen_previo=self.margen_previo,
            exclusion_deadzone=self.exclusion_deadzone
        )

        candidatos = selector.seleccionar_clips(serie_temporal, top_k=self.top_k)

        if not candidatos:
            raise RuntimeError("No se detectaron momentos destacados en el VOD analizado.")

        total_candidatos = len(candidatos)
        notificar(f"Fase 3/4: Descargando {total_candidatos} fragmentos de vídeo con yt-dlp...", 0.55)

        descargador_fragmentos = DescargadorFragmentos(
            carpeta_salida=self.carpeta_candidatos
        )

        clips_descargados = []
        contador = 1
        for c in candidatos:
            prefijo = f"clip_{contador:02d}"
            avance_clip = 0.55 + (contador / total_candidatos) * 0.20
            notificar(f"Fase 3/4: Recortando clip {contador} de {total_candidatos} ({c.segundo_inicio}s - {c.segundo_fin}s)...", avance_clip)

            try:
                clip_listo = descargador_fragmentos.descargar_clip(url_limpia, c, prefijo=prefijo)
                clips_descargados.append(clip_listo)
            except Exception as error_clip:
                print(f"[Aviso] No se pudo descargar el fragmento {contador}: {error_clip}")

            contador += 1

        if not clips_descargados:
            raise RuntimeError("No se pudo descargar ningún fragmento de vídeo con yt-dlp.")

        # ---------------------------------------------------------------------
        # FASE 4: Clasificación Visual Zero-Shot con OpenAI CLIP
        # ---------------------------------------------------------------------
        notificar("Fase 4/4: Inicializando modelo de IA (OpenAI CLIP)...", 0.78)

        clasificador = ClasificadorVisual()

        total_descargados = len(clips_descargados)

        def callback_ia(actual: int, total: int, clip_actualizado: CandidatoClip):
            avance_ia = 0.80 + (actual / total) * 0.18
            nombre_cat = clip_actualizado.categoria
            notificar(
                f"Fase 4/4: Clasificando clip {actual} de {total} -> {nombre_cat}",
                avance_ia
            )

        try:
            clips_finales = clasificador.clasificar_candidatos(
                clips_descargados,
                callback_progreso=callback_ia
            )
        except Exception as error_ia:
            print(f"[Aviso] Falló la clasificación por IA: {error_ia}. Continuando sin clasificación.")
            clips_finales = clips_descargados

        # Volcado automático de persistencia estructurado en clips_info.json
        try:
            self.guardar_clips_info(clips_finales)
        except Exception as error_guardado:
            print(f"[Aviso] No se pudo guardar clips_info.json: {error_guardado}")

        notificar("¡Pipeline completado con éxito! Cargando clips en la interfaz...", 1.0)
        return clips_finales

    # Vuelca la información de los clips clasificados en clips_info.json para persistencia permanente
    def guardar_clips_info(
        self,
        clips: list[CandidatoClip],
        ruta_json: Path | str | None = None
    ) -> Path:
        if ruta_json is not None:
            destino = Path(ruta_json)
        else:
            destino = self.carpeta_base / "clips_info.json"

        datos = []
        for c in clips:
            nombre = c.ruta_video.name if c.ruta_video else f"clip_{c.segundo_inicio}s_{c.segundo_fin}s.mp4"
            datos.append({
                "nombre_archivo": nombre,
                "ruta": str(c.ruta_video.resolve()) if c.ruta_video else None,
                "segundo_inicio": c.segundo_inicio,
                "segundo_fin": c.segundo_fin,
                "duracion": c.segundo_fin - c.segundo_inicio,
                "puntuacion": c.puntuacion,
                "categoria": c.categoria,
                "confianza": round(c.confianza_ia, 4),
                "estado": "Aprobado" if c.aprobado else "Pendiente"
            })

        with open(destino, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)

        print(f"[Pipeline] Guardada información y clasificación de clips en: {destino}")
        return destino


if __name__ == "__main__":
    print("Probando módulo orquestador de pipeline...")
    url_ejemplo = "https://www.twitch.tv/videos/2873857636"
    pipeline = PipelineClips(top_k=2)
    print(f"Carpeta base: {pipeline.carpeta_base}")
    print(f"Twitch CLI:   {pipeline.ruta_twitch_cli}")
