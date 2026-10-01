import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

# Asegurar raíz en sys.path
directorio_raiz = Path(__file__).resolve().parents[1]
if str(directorio_raiz) not in sys.path:
    sys.path.insert(0, str(directorio_raiz))

from ui.app import AppPrendeClips


class TestScrollRedimensionAdaptativa:
    """Pruebas unitarias para la redimensión y el contenedor con scroll de VistaInicio."""

    @pytest.fixture
    def app(self):
        """Instancia la aplicación para pruebas de interfaz."""
        aplicacion = AppPrendeClips()
        aplicacion.update()
        yield aplicacion
        try:
            aplicacion.destroy()
        except Exception:
            pass

    def test_geometria_y_minsize(self, app):
        """Verifica que la resolución inicial sea 1020x840 y la mínima 960x780."""
        # Comprobar minsize en CustomTkinter
        min_w = getattr(app, "_min_width", None)
        min_h = getattr(app, "_min_height", None)
        assert min_w == 960, f"Esperado min_w=960, obtenido {min_w}"
        assert min_h == 780, f"Esperado min_h=780, obtenido {min_h}"

        # Comprobar geometry
        geom = app.geometry()
        # Formato habitual en Tkinter: '1020x840+X+Y'
        dimensiones = geom.split("+")[0]
        ancho, alto = map(int, dimensiones.split("x"))
        assert ancho >= 1020, f"Esperado ancho >= 1020, obtenido {ancho}"
        assert alto >= 840, f"Esperado alto >= 840, obtenido {alto}"

    def test_componentes_scroll_existen_y_conectados(self, app):
        """Comprueba la existencia del Canvas, Scrollbar y Frame interior en VistaInicio."""
        vista = app.vista_inicio

        assert hasattr(vista, "canvas"), "Falta el atributo canvas en VistaInicio"
        assert hasattr(vista, "scrollbar"), "Falta el atributo scrollbar en VistaInicio"
        assert hasattr(vista, "frame_interior"), "Falta el atributo frame_interior en VistaInicio"
        assert hasattr(vista, "canvas_window"), "Falta el atributo canvas_window en VistaInicio"

        # Verificar vinculación del scrollbar y canvas
        assert str(vista.scrollbar.cget("orient")) == "vertical"

    def test_todos_los_elementos_interactivos_accesibles(self, app):
        """Verifica que todos los controles clave estén presentes dentro del contenedor."""
        vista = app.vista_inicio

        # 1. Buscador de streamers
        assert hasattr(vista, "entry_streamer")
        assert hasattr(vista, "btn_buscar_streamer")
        assert hasattr(vista, "cmb_vods_recientes")

        # 2. Entrada de URL
        assert hasattr(vista, "entry_url")

        # 3. Parámetros de extracción
        assert hasattr(vista, "slider_num_clips")
        assert hasattr(vista, "opt_perfil")
        assert hasattr(vista, "opt_sensibilidad")

        # 4. Botón principal y estado
        assert hasattr(vista, "btn_procesar")
        assert hasattr(vista, "lbl_estado")
        assert hasattr(vista, "barra_progreso")

        # 5. Barra inferior de utilidades
        assert hasattr(vista, "btn_abrir_carpeta")
        assert hasattr(vista, "btn_ver_existentes")
        assert hasattr(vista, "btn_purgar_clips")

    def test_funcionamiento_scroll_raton_y_reset(self, app):
        """Verifica que el scroll con ratón y la función resetear_scroll operen correctamente."""
        vista = app.vista_inicio
        vista.resetear_scroll()
        app.update()

        pos_inicial = vista.canvas.yview()
        assert pos_inicial[0] == 0.0, f"El scroll debería empezar arriba (0.0), obtenido {pos_inicial}"

        # Simulamos un evento de rueda del ratón hacia abajo (delta negativo en Windows)
        evento_scroll_down = MagicMock(delta=-120, num=None)
        vista._al_mousewheel(evento_scroll_down)
        app.update()

        # Reseteamos el scroll de vuelta a la parte superior
        vista.resetear_scroll()
        app.update()
        pos_reset = vista.canvas.yview()
        assert pos_reset[0] == 0.0

    def test_adaptacion_ancho_canvas(self, app):
        """Comprueba que el frame_interior se ajuste al ancho del Canvas al redimensionar."""
        vista = app.vista_inicio
        app.geometry("1100x850")
        app.update()

        ancho_canvas = vista.canvas.winfo_width()
        ancho_frame_interior = vista.canvas.itemcget(vista.canvas_window, "width")

        # En Tkinter itemcget devuelve string o int
        assert int(float(ancho_frame_interior)) == ancho_canvas

    def test_responsividad_tarjeta_y_centrado(self, app):
        """Verifica que la tarjeta central se ensanche proporcionalmente (no fija en 760px ni 592px)."""
        vista = app.vista_inicio
        app.geometry("1020x840")
        app.update()

        # En 1020x840 la tarjeta debe tener un ancho holgado (>= 900px)
        ancho_card_base = vista.card_central.winfo_width()
        assert ancho_card_base >= 900, f"La tarjeta debería ser >= 900px en 1020px, obtenido {ancho_card_base}"

        # Al maximizar o agrandar a 1920x1080
        app.geometry("1920x1080")
        app.update()

        ancho_card_max = vista.card_central.winfo_width()
        assert ancho_card_max >= 900, f"La tarjeta en maximizado debería ser >= 900px, obtenido {ancho_card_max}"
        assert ancho_card_max <= 1000, f"La tarjeta no debe deformarse excesivamente en 1920px, obtenido {ancho_card_max}"

        # El frame central debe estar centrado con márgenes amplios en modo maximizado
        pad_x = int(vista.frame_central.pack_info().get("padx", 0))
        assert pad_x >= 400, f"En 1920px el padding lateral debería centrar la vista (>= 400px), obtenido {pad_x}"

    def test_scrollbar_condicional_y_adyacente(self, app):
        """Verifica que el scrollbar se oculte cuando cabe el contenido y aparezca pegado al canvas cuando no cabe."""
        vista = app.vista_inicio

        # 1. En ventana grande (1020x950), el contenido cabe completo: el scrollbar debe ocultarse condicionalmente
        app.geometry("1020x950")
        app.update()
        assert not vista.scrollbar.winfo_ismapped(), "El scrollbar debería ocultarse automáticamente si el contenido cabe entero"

        # 2. En ventana reducida (por debajo de la altura de la tarjeta, p.ej. 600px), el scrollbar debe mostrarse
        app.minsize(300, 300)
        app.geometry("960x600")
        app.update()
        assert vista.scrollbar.winfo_ismapped(), "El scrollbar debe aparecer cuando la altura es insuficiente"

        # 3. La barra de scroll debe estar pegada justo al borde del Canvas (adyacente a la tarjeta)
        pos_x_scrollbar = vista.scrollbar.winfo_x()
        ancho_canvas = vista.canvas.winfo_width()
        assert abs(pos_x_scrollbar - ancho_canvas) <= 4, (
            f"El scrollbar (x={pos_x_scrollbar}) debe estar inmediatamente adyacente al canvas (w={ancho_canvas})"
        )

        # Restaurar minsize
        app.minsize(960, 780)
        app.update()

