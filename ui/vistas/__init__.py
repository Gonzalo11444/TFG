# vistas/__init__.py
# Paquete de vistas para PrendeClips

from ui.vistas.inicio import (
    VistaInicio,
    abrir_carpeta_sistema,
    purgar_archivos_sesion,
    DialogoConfirmarPurga
)

__all__ = [
    "VistaInicio",
    "abrir_carpeta_sistema",
    "purgar_archivos_sesion",
    "DialogoConfirmarPurga"
]
