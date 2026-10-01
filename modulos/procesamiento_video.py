# procesamiento_video.py
#
# Fase 5: Reencuadre a formato vertical (9:16) con desenfoque de fondo y pantalla dividida (Split).
# Mantiene compatibilidad total con modulos.renderizador_vertical.

from pathlib import Path
from typing import Callable
import shutil

try:
    from modulos.renderizador_vertical import RenderizadorVertical
except ImportError:
    from renderizador_vertical import RenderizadorVertical

__all__ = ["RenderizadorVertical"]


if __name__ == "__main__":
    print("Probando módulo compatibilidad procesamiento_video...")
    renderizador = RenderizadorVertical(preset="veryfast")
    print(f"Carpeta destino: {renderizador.carpeta_salida}")
    print(f"FFmpeg: {renderizador.ffmpeg}")
