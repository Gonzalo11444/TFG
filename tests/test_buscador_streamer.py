import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest

# Asegurar raíz en sys.path
directorio_raiz = Path(__file__).resolve().parents[1]
if str(directorio_raiz) not in sys.path:
    sys.path.insert(0, str(directorio_raiz))

from modulos.buscador_streamer import (
    DirectoReciente,
    limpiar_nombre_canal,
    obtener_ultimos_vods,
    _formatear_duracion,
    _extraer_fecha
)
from ui.app import AppPrendeClips


class TestBuscadorStreamerUtils:
    """Pruebas unitarias para las funciones utilitarias del buscador."""

    def test_limpiar_nombre_canal(self):
        """Verifica la limpieza exhaustiva de nombres de usuario y URLs de Twitch."""
        assert limpiar_nombre_canal("ibai") == "ibai"
        assert limpiar_nombre_canal("  @ibai  ") == "ibai"
        assert limpiar_nombre_canal("@auronplay") == "auronplay"
        assert limpiar_nombre_canal("https://www.twitch.tv/ibai") == "ibai"
        assert limpiar_nombre_canal("https://www.twitch.tv/ibai/") == "ibai"
        assert limpiar_nombre_canal("https://www.twitch.tv/ibai/videos?filter=archives") == "ibai"
        assert limpiar_nombre_canal("twitch.tv/elxokas") == "elxokas"
        assert limpiar_nombre_canal("") == ""
        assert limpiar_nombre_canal("   ") == ""

    def test_formatear_duracion(self):
        """Verifica el formato de duración en HH:MM:SS y MM:SS."""
        assert _formatear_duracion(3665) == "1:01:05"
        assert _formatear_duracion(125) == "02:05"
        assert _formatear_duracion(0) == "00:00"
        assert _formatear_duracion(None) == "00:00"

    def test_extraer_fecha(self):
        """Verifica la extracción de fecha desde upload_date o epoch."""
        assert _extraer_fecha({"upload_date": "20261001"}) == "2026-10-01"
        assert _extraer_fecha({"epoch": 1790856329}).startswith("2026-")
        assert _extraer_fecha({}) == "Fecha desc."

    def test_directo_reciente_display(self):
        """Verifica la propiedad texto_display para los desplegables de la interfaz."""
        vod = DirectoReciente(
            id="v123456",
            titulo="Gran Torneo de Fall Guys",
            duracion_str="2:30:00",
            fecha="2026-10-01",
            url="https://www.twitch.tv/videos/123456"
        )
        display = vod.texto_display
        assert "[2026-10-01]" in display
        assert "Gran Torneo de Fall Guys" in display
        assert "(2:30:00)" in display


class TestObtenerUltimosVods:
    """Pruebas unitarias para la función obtener_ultimos_vods con mocks de subprocess."""

    def test_canal_vacio_devuelve_lista_vacia(self):
        """Si el canal está vacío o con espacios, no ejecuta llamadas y retorna lista vacía."""
        assert obtener_ultimos_vods("") == []
        assert obtener_ultimos_vods("   ") == []

    @patch("subprocess.run")
    def test_parsing_json_exitoso(self, mock_run):
        """Simula la salida JSON de yt-dlp y verifica la construcción de DirectoReciente."""
        salida_json = (
            '{"id": "v2885639019", "title": "AMONG US HISTORICO", "duration_string": "2:38:01", "upload_date": "20261001", "webpage_url": "https://www.twitch.tv/videos/2885639019"}\n'
            '{"id": "v2885611944", "title": "CHARLANDO UN RATO", "duration_string": "45:10", "upload_date": "20260930", "webpage_url": "https://www.twitch.tv/videos/2885611944"}\n'
        )
        mock_run.return_value = MagicMock(returncode=0, stdout=salida_json, stderr="")

        vods = obtener_ultimos_vods("ibai", limite=2)
        assert len(vods) == 2
        assert vods[0].id == "v2885639019"
        assert vods[0].titulo == "AMONG US HISTORICO"
        assert vods[0].duracion_str == "2:38:01"
        assert vods[0].fecha == "2026-10-01"
        assert vods[0].url == "https://www.twitch.tv/videos/2885639019"

    @patch("subprocess.run")
    def test_timeout_devuelve_lista_vacia(self, mock_run):
        """Si yt-dlp excede los 15s de timeout, captura la excepción y retorna []."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="yt-dlp", timeout=15)
        assert obtener_ultimos_vods("ibai") == []

    @patch("subprocess.run")
    def test_error_proceso_devuelve_lista_vacia(self, mock_run):
        """Si yt-dlp falla (código != 0), maneja el error de forma segura."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Channel not found")
        assert obtener_ultimos_vods("canal_que_no_existe_xyz_123") == []


class TestIntegracionUIBuscador:
    """Pruebas de la interfaz de búsqueda en VistaInicio y AppPrendeClips."""

    def test_controles_existentes_en_interfaz(self):
        """Comprueba la existencia de los nuevos componentes en la pantalla de inicio."""
        app = AppPrendeClips()
        app.update()

        # 1. Controles creados
        assert hasattr(app.vista_inicio, "entry_streamer")
        assert hasattr(app.vista_inicio, "btn_buscar_streamer")
        assert hasattr(app.vista_inicio, "cmb_vods_recientes")
        assert hasattr(app.vista_inicio, "entry_url")

        # 2. Propiedades delegadas en app
        assert app.entry_streamer is app.vista_inicio.entry_streamer
        assert app.btn_buscar_streamer is app.vista_inicio.btn_buscar_streamer
        assert app.cmb_vods_recientes is app.vista_inicio.cmb_vods_recientes

        # 3. Estado inicial
        assert app.btn_buscar_streamer.cget("text") == "🔍 Buscar directos"

        app.destroy()

    def test_seleccion_combobox_rellena_url(self):
        """Verifica que al seleccionar un VOD en el Combobox se rellene automáticamente el entry_url."""
        app = AppPrendeClips()
        app.update()

        vod_dummy = DirectoReciente(
            id="v999888",
            titulo="Directo Especial",
            duracion_str="1:15:00",
            fecha="2026-10-01",
            url="https://www.twitch.tv/videos/999888"
        )

        # Simulamos que la búsqueda pobló el mapa de VODs
        app.vista_inicio._actualizar_combo_vods("streamer_test", [vod_dummy])
        app.update()

        opciones = app.vista_inicio.cmb_vods_recientes.cget("values")
        assert len(opciones) == 1
        texto_opcion = opciones[0]

        # Disparamos la selección del item
        app.vista_inicio._al_seleccionar_vod_reciente(texto_opcion)
        app.update()

        # El campo de URL debe haberse rellenado con el enlace del VOD
        url_obtenida = app.vista_inicio.obtener_url()
        assert url_obtenida == "https://www.twitch.tv/videos/999888"

        app.destroy()

    def test_bloqueo_desbloqueo_durante_procesando(self):
        """Comprueba que los controles de búsqueda se deshabiliten mientras el pipeline procesa."""
        app = AppPrendeClips()
        app.update()

        app.vista_inicio.establecer_modo_procesando(True)
        assert app.entry_streamer.cget("state") == "disabled"
        assert app.btn_buscar_streamer.cget("state") == "disabled"
        assert app.cmb_vods_recientes.cget("state") == "disabled"
        assert app.vista_inicio.entry_url.cget("state") == "disabled"

        app.vista_inicio.establecer_modo_procesando(False)
        assert app.entry_streamer.cget("state") == "normal"
        assert app.btn_buscar_streamer.cget("state") == "normal"
        assert app.cmb_vods_recientes.cget("state") == "normal"
        assert app.vista_inicio.entry_url.cget("state") == "normal"

        app.destroy()
