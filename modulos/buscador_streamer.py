"""
buscador_streamer.py

Módulo para consultar y listar los directos recientes (VODs) de un streamer
en Twitch mediante yt-dlp, permitiendo seleccionar rápidamente el VOD a procesar.
"""

from dataclasses import dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import shutil
import subprocess
import sys

logger = logging.getLogger("buscador_streamer")


@dataclass
class DirectoReciente:
    id: str
    titulo: str
    duracion_str: str
    fecha: str
    url: str

    @property
    def texto_display(self) -> str:
        """Formatea el VOD para mostrarlo en desplegables: [Fecha] Título (Duración)."""
        fecha_str = f"[{self.fecha}] " if self.fecha else ""
        duracion = f" ({self.duracion_str})" if self.duracion_str else ""
        tit = self.titulo if len(self.titulo) <= 55 else f"{self.titulo[:52]}..."
        return f"{fecha_str}{tit}{duracion}"


def limpiar_nombre_canal(canal: str) -> str:
    """
    Limpia y extrae el identificador o nombre de usuario de Twitch.
    Soporta nombres con @, espacios y URLs completas del canal.
    Ejemplos:
      - '  @ibai  ' -> 'ibai'
      - 'https://www.twitch.tv/ibai' -> 'ibai'
      - 'https://www.twitch.tv/ibai/videos?filter=archives' -> 'ibai'
    """
    texto = (canal or "").strip()
    if not texto:
        return ""

    # Quitar arroba inicial si está presente
    if texto.startswith("@"):
        texto = texto[1:].strip()

    # Si contiene twitch.tv, parseamos la URL
    if "twitch.tv" in texto:
        parte_tras_dominio = texto.split("twitch.tv/")[-1]
        segmentos = parte_tras_dominio.split("/")
        for seg in segmentos:
            seg_limpio = seg.split("?")[0].strip()
            if seg_limpio and seg_limpio.lower() not in ("videos", "clips", "about", "schedule", "following", "followers"):
                return seg_limpio

    # Quitar parámetros de consulta y barras
    texto = texto.split("?")[0].rstrip("/")
    if "/" in texto:
        texto = texto.split("/")[-1]

    return texto.strip().lstrip("@")


def _formatear_duracion(segundos: float | int | None) -> str:
    """Convierte segundos a formato HH:MM:SS o MM:SS."""
    if segundos is None or segundos < 0:
        return "00:00"
    seg = int(segundos)
    horas = seg // 3600
    minutos = (seg % 3600) // 60
    seg_restantes = seg % 60
    if horas > 0:
        return f"{horas}:{minutos:02d}:{seg_restantes:02d}"
    return f"{minutos:02d}:{seg_restantes:02d}"


def _extraer_fecha(datos: dict) -> str:
    """Extrae y formatea la fecha del directo en formato YYYY-MM-DD."""
    # 1. Intentar fecha de subida 'YYYYMMDD'
    raw_date = datos.get("upload_date")
    if raw_date and isinstance(raw_date, str) and len(raw_date) == 8 and raw_date.isdigit():
        return f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"

    # 2. Intentar timestamps Unix (epoch o timestamp)
    for campo in ("epoch", "timestamp"):
        ts = datos.get(campo)
        if ts is not None:
            try:
                return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
            except (ValueError, TypeError, OSError):
                pass

    return "Fecha desc."


def _localizar_ytdlp() -> str | list[str]:
    """Localiza el ejecutable de yt-dlp o el intérprete de Python con el módulo."""
    encontrado = shutil.which("yt-dlp")
    if encontrado:
        return encontrado
    # Si no está en PATH directo, usamos el módulo de python
    return [sys.executable, "-m", "yt_dlp"]


def obtener_ultimos_vods(canal: str, limite: int = 5) -> list[DirectoReciente]:
    """
    Consulta los directos recientes de un canal de Twitch mediante yt-dlp.

    Parámetros:
        canal: Nombre de usuario de Twitch o URL del canal.
        limite: Cantidad máxima de directos a devolver (defecto: 5).

    Retorna:
        list[DirectoReciente]: Lista ordenada de directos recientes encontrados.
        En caso de error, timeout o canal inexistente, devuelve lista vacía.
    """
    canal_limpio = limpiar_nombre_canal(canal)
    if not canal_limpio:
        logger.warning("[BuscadorStreamer] Nombre de canal vacío o inválido.")
        return []

    url_archivo = f"https://www.twitch.tv/{canal_limpio}/videos?filter=archives"
    ytdlp_cmd = _localizar_ytdlp()

    if isinstance(ytdlp_cmd, list):
        comando = ytdlp_cmd + [
            "--flat-playlist",
            "--dump-json",
            "--playlist-end", str(limite),
            url_archivo
        ]
    else:
        comando = [
            ytdlp_cmd,
            "--flat-playlist",
            "--dump-json",
            "--playlist-end", str(limite),
            url_archivo
        ]

    kwargs = {
        "capture_output": True,
        "text": True,
        "timeout": 15,
        "check": False
    }
    # En Windows, ocultamos la ventana de consola emergente
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        resultado = subprocess.run(comando, **kwargs)
    except subprocess.TimeoutExpired:
        logger.warning(f"[BuscadorStreamer] Timeout de 15s al buscar VODs de '{canal_limpio}'.")
        return []
    except Exception as e:
        logger.error(f"[BuscadorStreamer] Excepción al invocar yt-dlp para '{canal_limpio}': {e}")
        return []

    if resultado.returncode != 0:
        logger.warning(
            f"[BuscadorStreamer] yt-dlp devolvió código {resultado.returncode} para '{canal_limpio}': "
            f"{resultado.stderr.strip()[:150]}"
        )
        return []

    directos: list[DirectoReciente] = []
    for linea in resultado.stdout.splitlines():
        linea = linea.strip()
        if not linea or not linea.startswith("{"):
            continue

        try:
            datos = json.loads(linea)
            vod_id = str(datos.get("id", "")).strip()
            titulo = str(datos.get("title", "")).strip() or "Directo sin título"

            # URL del VOD
            url_vod = (
                datos.get("webpage_url")
                or datos.get("url")
                or f"https://www.twitch.tv/videos/{vod_id.lstrip('v')}"
            )

            # Duración
            duracion_sec = datos.get("duration")
            duracion_str = datos.get("duration_string") or _formatear_duracion(duracion_sec)

            # Fecha
            fecha = _extraer_fecha(datos)

            directos.append(
                DirectoReciente(
                    id=vod_id,
                    titulo=titulo,
                    duracion_str=duracion_str,
                    fecha=fecha,
                    url=url_vod
                )
            )
        except json.JSONDecodeError:
            continue

    return directos
