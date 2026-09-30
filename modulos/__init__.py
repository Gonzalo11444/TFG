# modulos/__init__.py
# Paquete principal con los módulos de las 5 fases de PrendeClips

from modulos.descarga_twitch import TwitchDescarga
from modulos.procesamiento_senales import ProcesadorSenales, PuntoTemporal
from modulos.analizador_audio import (
    AnalizadorAudio,
    normalizar_volumen_adaptativo,
    analizar_volumen,
    suavizar_media_movil
)
from modulos.seleccion_temporal import (
    SelectorMomentos,
    DescargadorFragmentos,
    CandidatoClip
)
from modulos.clasificador_clip import ClasificadorVisual
from modulos.procesamiento_video import RenderizadorVertical
from modulos.pipeline import PipelineClips

__all__ = [
    "TwitchDescarga",
    "ProcesadorSenales",
    "PuntoTemporal",
    "AnalizadorAudio",
    "normalizar_volumen_adaptativo",
    "analizar_volumen",
    "suavizar_media_movil",
    "SelectorMomentos",
    "DescargadorFragmentos",
    "CandidatoClip",
    "ClasificadorVisual",
    "RenderizadorVertical",
    "PipelineClips"
]
