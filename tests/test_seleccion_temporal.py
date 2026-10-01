import sys
from pathlib import Path
import pytest

# Asegurar que la raíz del proyecto está en sys.path
directorio_raiz = Path(__file__).resolve().parents[1]
if str(directorio_raiz) not in sys.path:
    sys.path.insert(0, str(directorio_raiz))

from modulos.seleccion_temporal import SelectorMomentos, PuntoTemporal, CandidatoClip


class TestUmbralMinMensajesChat:
    """Pruebas unitarias para el filtro de umbral mínimo de actividad en chat."""

    def test_canal_tranquilo_con_1_o_2_mensajes_devuelve_cero(self):
        """Comprueba que con 1 o 2 mensajes en un canal tranquilo el score resultante es 0.0."""
        selector = SelectorMomentos(umbral_min_mensajes_chat=3)

        # 1. Comprobación directa en _normalizar_min_max
        chats_tranquilo = [0.0, 1.0, 0.0, 2.0, 1.0, 0.0]
        norm_chat = selector._normalizar_min_max(chats_tranquilo)

        assert len(norm_chat) == len(chats_tranquilo)
        # Todo valor menor a 3 debe forzarse a 0.0
        assert all(val == 0.0 for val in norm_chat), f"Esperado todo 0.0, obtenido: {norm_chat}"

        # 2. Comprobación en calcular_puntuaciones evaluando serie completa
        # Configuramos peso_audio=0.0 y peso_chat=1.0 para aislar el score de chat
        selector_solo_chat = SelectorMomentos(peso_audio=0.0, peso_chat=1.0, umbral_min_mensajes_chat=3)
        serie_tranquila = [
            PuntoTemporal(segundo=s, volumen_dbfs=-20.0, mensajes_chat=(2 if s == 5 else (1 if s == 8 else 0)))
            for s in range(15)
        ]
        scores = selector_solo_chat.calcular_puntuaciones(serie_tranquila)
        assert len(scores) == 15
        assert all(s == 0.0 for s in scores), f"Esperado score de chat 0.0 en toda la serie, obtenido: {scores}"

    def test_escalado_normal_al_superar_umbral(self):
        """Comprueba que al superar el umbral mínimo se escala progresivamente en [0.0, 1.0]."""
        selector = SelectorMomentos(umbral_min_mensajes_chat=3)

        chats_activos = [0.0, 1.0, 2.0, 5.0, 10.0]
        norm_chat = selector._normalizar_min_max(chats_activos)

        # Valores inferiores a 3 se anulan a 0.0
        assert norm_chat[0] == 0.0  # 0 mensajes
        assert norm_chat[1] == 0.0  # 1 mensaje
        assert norm_chat[2] == 0.0  # 2 mensajes

        # Valores >= 3 se escalan respecto al rango [0, 10]
        assert norm_chat[3] == 0.5  # 5 mensajes -> (5-0)/10 = 0.5
        assert norm_chat[4] == 1.0  # 10 mensajes -> (10-0)/10 = 1.0

        # Verificación con serie temporal completa
        serie = [
            PuntoTemporal(segundo=i, volumen_dbfs=-30.0, mensajes_chat=m)
            for i, m in enumerate(chats_activos)
        ]
        selector_chat = SelectorMomentos(peso_audio=0.0, peso_chat=1.0, umbral_min_mensajes_chat=3)
        scores = selector_chat.calcular_puntuaciones(serie)
        assert scores[4] == 1.0
        assert scores[3] == 0.5
        assert scores[0] == 0.0


class TestVentanaSupresionNMS:
    """Pruebas unitarias para la ventana de supresión y exclusión deadzone en NMS."""

    def test_supresion_de_picos_cercanos_y_seleccion_de_pico_lejano(self):
        """
        Simula una serie con picos cercanos (t=100s y t=120s) y verifica que el segundo
        queda suprimido dentro de la ventana de 90s, mientras que t=250s sí es seleccionado.
        """
        selector = SelectorMomentos(
            peso_audio=0.5,
            peso_chat=0.5,
            duracion_clip=30,
            margen_previo=15,
            ventana_supresion=90,
            umbral_min_mensajes_chat=3
        )

        total_segundos = 350
        serie = []
        for s in range(total_segundos):
            if s == 100:
                # Pico 1: Intensidad máxima
                vol, chat = -5.0, 50
            elif s == 120:
                # Pico 2: Intensidad alta, pero a solo 20s de t=100s (misma jugada)
                vol, chat = -7.0, 45
            elif s == 250:
                # Pico 3: Intensidad destacada, a 150s de t=100s (jugada independiente)
                vol, chat = -8.0, 40
            else:
                vol, chat = -40.0, 0
            serie.append(PuntoTemporal(segundo=s, volumen_dbfs=vol, mensajes_chat=chat))

        candidatos = selector.seleccionar_clips(serie, top_k=2)

        # Deben seleccionarse exactamente 2 clips
        assert len(candidatos) == 2, f"Se esperaban 2 clips, obtenidos {len(candidatos)}"

        clip_1, clip_2 = candidatos[0], candidatos[1]

        # 1. El primer clip debe contener el pico de t=100s (rango aproximado [85s, 115s])
        assert clip_1.segundo_inicio <= 100 <= clip_1.segundo_fin, (
            f"El Clip 1 [{clip_1.segundo_inicio}, {clip_1.segundo_fin}] no contiene t=100s"
        )

        # 2. El segundo pico en t=120s DEBE quedar suprimido por la ventana de exclusión de 90s:
        # [85 - 90, 115 + 90] = [0, 205]. Como 120 <= 205, ningún clip debe contener t=120s.
        for c in candidatos:
            assert not (c.segundo_inicio <= 120 <= c.segundo_fin), (
                f"ERROR: Se generó el clip [{c.segundo_inicio}, {c.segundo_fin}] que contiene t=120s, "
                "el cual debió haber sido suprimido por la ventana de 90s."
            )

        # 3. El segundo clip seleccionado debe corresponder al pico de t=250s
        assert clip_2.segundo_inicio <= 250 <= clip_2.segundo_fin, (
            f"El Clip 2 [{clip_2.segundo_inicio}, {clip_2.segundo_fin}] debería contener t=250s"
        )

    def test_defaults_y_retrocompatibilidad(self):
        """Verifica los valores por defecto y la compatibilidad con exclusion_deadzone."""
        # Valores por defecto
        s_default = SelectorMomentos()
        assert s_default.umbral_min_mensajes_chat == 3
        assert s_default.ventana_supresion == 90
        assert s_default.exclusion_deadzone == 90

        # Retrocompatibilidad cuando se pasa exclusion_deadzone explícito
        s_legacy = SelectorMomentos(exclusion_deadzone=40)
        assert s_legacy.ventana_supresion == 40
        assert s_legacy.exclusion_deadzone == 40
