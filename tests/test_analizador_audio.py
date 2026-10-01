import sys
from pathlib import Path
import numpy as np
import pytest

# Asegurar que la raíz del proyecto está en sys.path
directorio_raiz = Path(__file__).resolve().parents[1]
if str(directorio_raiz) not in sys.path:
    sys.path.insert(0, str(directorio_raiz))

from modulos.analizador_audio import normalizar_volumen_adaptativo, suavizar_media_movil


class TestNormalizarVolumenAdaptativo:
    """Pruebas unitarias para normalizar_volumen_adaptativo."""

    def test_variacion_dinamica_normal(self):
        """Verifica la normalización con un perfil de audio dinámico y variado."""
        # Generamos 100 segundos con habla de fondo (-25 dBFS) y picos de hype (-10 a -5 dBFS)
        volumenes = [-26.0] * 40 + [-10.0, -8.0, -5.0, -6.0, -9.0] + [-25.0] * 40 + [-5.0] * 5 + [-24.0] * 10

        scores = normalizar_volumen_adaptativo(volumenes, metodo="percentil")

        assert len(scores) == len(volumenes)
        # Todos los scores deben estar estrictamente acotados a [0.0, 1.0]
        assert all(0.0 <= s <= 1.0 for s in scores)
        # El habla habitual (-26 dBFS) debe recibir puntuaciones nulas o prácticamente nulas
        assert scores[0] == 0.0
        # Los picos emocionales (-5 dBFS) deben recibir la máxima puntuación (1.0)
        assert max(scores) == 1.0

        # Mismo comportamiento con el método zscore
        scores_zscore = normalizar_volumen_adaptativo(volumenes, metodo="zscore")
        assert len(scores_zscore) == len(volumenes)
        assert all(0.0 <= s <= 1.0 for s in scores_zscore)
        assert max(scores_zscore) == 1.0

    def test_audio_plano_evita_division_por_cero(self):
        """Verifica que audios planos o con variación nula no causen ZeroDivisionError."""
        # Caso 1: Todos los valores idénticos a -30 dBFS
        volumenes_planos = [-30.0] * 50
        scores_percentil = normalizar_volumen_adaptativo(volumenes_planos, metodo="percentil")
        scores_zscore = normalizar_volumen_adaptativo(volumenes_planos, metodo="zscore")

        assert scores_percentil == [0.0] * 50
        assert scores_zscore == [0.0] * 50

        # Caso 2: Audio completamente silencioso a -100 dBFS
        silencio = [-100.0] * 20
        assert normalizar_volumen_adaptativo(silencio) == [0.0] * 20

        # Caso 3: Array de un solo elemento
        assert normalizar_volumen_adaptativo([-20.0]) == [0.0]

        # Caso 4: Secuencia vacía o None
        assert normalizar_volumen_adaptativo([]) == []
        assert normalizar_volumen_adaptativo(None) == []

    def test_descarte_silencios_profundos_para_estadisticas(self):
        """Comprueba que descarta silencios por debajo de -60 dBFS para el cálculo estadístico."""
        # Simulamos 60s de silencio técnico (-80 dBFS) y 40s de habla activa (-30 dBFS a -10 dBFS)
        silencio_profundo = [-80.0] * 60
        habla_y_gritos = [-25.0] * 35 + [-10.0] * 5
        serie_completa = silencio_profundo + habla_y_gritos

        # Con descarte de silencio activo (por defecto umbral_silencio_dbfs=-60.0):
        scores_con_filtro = normalizar_volumen_adaptativo(
            serie_completa,
            descartar_silencio_stats=True,
            umbral_silencio_dbfs=-60.0
        )

        # Sin descarte de silencios: el 60% de silencios arrastra la mediana hacia -80 dBFS
        scores_sin_filtro = normalizar_volumen_adaptativo(
            serie_completa,
            descartar_silencio_stats=False
        )

        # En el caso filtrado, el silencio profundo en t=0 recibe 0.0
        assert scores_con_filtro[0] == 0.0
        # El habla habitual (-25 dBFS) con filtro es la base activa -> se evalúa cerca de 0.0
        assert scores_con_filtro[60] <= 0.15
        # El pico en -10 dBFS se destaca con la máxima puntuación
        assert max(scores_con_filtro) == 1.0

        # Sin filtro, como la mediana cayó en -80 dBFS, el habla normal (-25 dBFS)
        # se infla artificialmente respecto al caso filtrado
        assert scores_sin_filtro[60] > scores_con_filtro[60]


class TestSuavizarMediaMovil:
    """Pruebas unitarias para suavizar_media_movil."""

    def test_atenuacion_pico_aislado_ruido_seco(self):
        """Verifica la atenuación de picos impulsivos de 1 segundo (ruido seco <= 0.25)."""
        # Pico de 1 segundo (1.0) rodeado de silencio (0.0) con ventana de 5 segundos
        serie_impulso = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        suavizado = suavizar_media_movil(serie_impulso, ventana=5)

        # La convolución con ventana 5 debe promediar 1.0 / 5 = 0.20
        max_valor = float(np.max(suavizado))
        assert max_valor <= 0.25, f"El pico impulsivo no fue suficientemente atenuado: {max_valor}"
        assert np.isclose(max_valor, 0.20, atol=1e-4)

    def test_preservacion_bloque_sostenido(self):
        """Verifica la preservación de bloques sostenidos de hype o intensidad (>= 0.8)."""
        # Bloque de intensidad sostenida durante 5 segundos consecutivos (1.0)
        serie_sostenida = [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0]
        suavizado = suavizar_media_movil(serie_sostenida, ventana=5)

        # En el centro del bloque sostenido (índice 4), el promedio de 5 unos debe ser 1.0
        valor_central = float(suavizado[4])
        assert valor_central >= 0.8, f"El bloque sostenido se atenuó excesivamente: {valor_central}"
        assert np.isclose(valor_central, 1.0, atol=1e-4)

        # Los índices adyacentes dentro del bloque también deben mantenerse >= 0.8
        assert float(suavizado[3]) >= 0.8
        assert float(suavizado[5]) >= 0.8

    def test_casos_borde(self):
        """Verifica el comportamiento defensivo ante arrays vacíos, ventanas pequeñas y longitudes cortas."""
        # 1. Array vacío
        vacio = suavizar_media_movil([])
        assert isinstance(vacio, np.ndarray)
        assert vacio.size == 0

        # 2. Entrada None
        nulo = suavizar_media_movil(None)
        assert isinstance(nulo, np.ndarray)
        assert nulo.size == 0

        # 3. Longitud menor que la ventana (longitud 3 < ventana 5)
        corto = [0.2, 0.9, 0.4]
        res_corto = suavizar_media_movil(corto, ventana=5)
        assert len(res_corto) == 3
        np.testing.assert_allclose(res_corto, np.array([0.2, 0.9, 0.4]))

        # 4. Ventana <= 1 (debe devolver el array recortado sin alterar)
        res_ventana_1 = suavizar_media_movil([0.3, 1.2, -0.1], ventana=1)
        np.testing.assert_allclose(res_ventana_1, np.array([0.3, 1.0, 0.0]))
