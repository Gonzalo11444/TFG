# modulos/__init__.py
# Paquete principal con los módulos de las 5 fases de PrendeClips

from modulos.descarga_twitch import TwitchDescarga
from modulos.procesamiento_senales import ProcesadorSenales, PuntoTemporal
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
    "SelectorMomentos",
    "DescargadorFragmentos",
    "CandidatoClip",
    "ClasificadorVisual",
    "RenderizadorVertical",
    "PipelineClips"
]
