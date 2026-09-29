"""
lista_clips.py

Panel lateral con scroll que muestra las tarjetas de clips candidatos.
Permite seleccionarlos para reproducción, cambiar su estado (Aprobado / Descartado),
lanzar el análisis semántico con CLIP e inspeccionar/corregir las etiquetas visuales.
"""

from pathlib import Path
from typing import Callable
from dataclasses import replace
import re
import json
import customtkinter as ctk

# Intento de importación del modelo de datos de la Fase 3
try:
    from modulos.seleccion_temporal import CandidatoClip
except ImportError:
    from dataclasses import dataclass

    @dataclass(frozen=True, slots=True)
    class CandidatoClip:
        segundo_inicio: int
        segundo_fin: int
        puntuacion: float
        ruta_video: Path | None = None
        categoria: str = "Sin clasificar"
        confianza_ia: float = 0.0
        aprobado: bool = False

# Importación de categorías y colores de la Fase 4
try:
    from modulos.clasificador_clip import COLORES_CATEGORIA, LISTA_CATEGORIAS_DISPONIBLES
except ImportError:
    COLORES_CATEGORIA = {
        "Gameplay": "#2e7d32",
        "Charla / Cámara": "#1565c0",
        "Reacción / Risa": "#f57c00",
        "Menú / Carga": "#546e7a",
        "Pantalla Final / Despedida": "#c62828",
        "Sin clasificar": "#424242"
    }
    LISTA_CATEGORIAS_DISPONIBLES = [
        "Gameplay",
        "Charla / Cámara",
        "Reacción / Risa",
        "Menú / Carga",
        "Pantalla Final / Despedida",
        "Sin clasificar"
    ]


class PanelListaClips(ctk.CTkFrame):
    # Constructor del panel: crea la cabecera con botón IA y el contenedor con scroll
    def __init__(
        self,
        master,
        on_clip_seleccionado: Callable[[CandidatoClip], None] | None = None,
        on_estado_cambiado: Callable[[], None] | None = None,
        on_lanzar_ia: Callable[[], None] | None = None,
        on_clips_actualizados: Callable[[], None] | None = None,
        **kwargs
    ):
        super().__init__(master, **kwargs)

        self.on_clip_seleccionado = on_clip_seleccionado
        self.on_estado_cambiado = on_estado_cambiado
        self.on_lanzar_ia = on_lanzar_ia
        self.on_clips_actualizados = on_clips_actualizados

        self.clips: list[CandidatoClip] = []
        self.estados: dict[int, str] = {}
        self._tarjetas_widgets: list[ctk.CTkFrame] = []
        self._elementos_tarjetas: list[dict] = []
        self._indice_seleccionado: int | None = None
        self.navegacion_bloqueada: bool = False

        # Rejilla del panel principal
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 1. Cabecera fija con botón de análisis IA y progreso
        self._construir_cabecera()

        # 2. Contenedor desplazable con las tarjetas de clips
        self.scroll_tarjetas = ctk.CTkScrollableFrame(self)
        self.scroll_tarjetas.grid(row=1, column=0, sticky="nsew", padx=4, pady=(4, 4))
        self.scroll_tarjetas.grid_columnconfigure(0, weight=1)

    # Construye los controles superiores de la lista
    def _construir_cabecera(self) -> None:
        self.frame_cabecera = ctk.CTkFrame(self, fg_color="#242424", corner_radius=6)
        self.frame_cabecera.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        self.frame_cabecera.grid_columnconfigure(0, weight=1)

        # Fila superior de la cabecera: Título y Botón IA
        self.lbl_titulo_cabecera = ctk.CTkLabel(
            self.frame_cabecera,
            text="Clips Candidatos",
            font=("Arial", 13, "bold"),
            anchor="w"
        )
        self.lbl_titulo_cabecera.grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))

        self.btn_analizar_ia = ctk.CTkButton(
            self.frame_cabecera,
            text="✨ Analizar con IA",
            width=130,
            height=26,
            font=("Arial", 11, "bold"),
            fg_color="#6200ea",
            hover_color="#7c4dff",
            command=self._on_click_analizar_ia
        )
        self.btn_analizar_ia.grid(row=0, column=1, sticky="e", padx=10, pady=(6, 2))

        # Fila inferior de la cabecera: Barra de progreso e indicador de estado
        self.barra_progreso_ia = ctk.CTkProgressBar(self.frame_cabecera, height=6)
        self.barra_progreso_ia.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(2, 2))
        self.barra_progreso_ia.set(0.0)

        self.lbl_estado_ia = ctk.CTkLabel(
            self.frame_cabecera,
            text="Clasificación CLIP lista",
            font=("Arial", 10),
            text_color="#888888",
            anchor="w"
        )
        self.lbl_estado_ia.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))

    # Carga la lista de clips y crea las tarjetas visuales
    def cargar_clips(self, clips: list[CandidatoClip] | None) -> None:
        self.limpiar()
        self.clips = [c for c in clips if c is not None] if clips else []

        if not self.clips or len(self.clips) == 0:
            lbl_vacio = ctk.CTkLabel(
                self.scroll_tarjetas,
                text="No hay clips candidatos disponibles.",
                font=("Arial", 12),
                text_color="gray"
            )
            lbl_vacio.grid(row=0, column=0, pady=30, padx=20)
            return

        # Inicializamos los estados respetando la aprobación persistida si existe
        for i in range(len(self.clips)):
            self.estados[i] = "Aprobado" if self.clips[i].aprobado else "Descartado"

        # Creamos una tarjeta visual para cada clip
        for i in range(len(self.clips)):
            clip = self.clips[i]
            self._crear_tarjeta(i, clip)

        # Destacamos visualmente la primera tarjeta sin disparar reproducción inmediata
        if self.clips and len(self.clips) > 0:
            self.seleccionar_clip(0, reproducir=False)

    # Borra todas las tarjetas actuales del panel
    def limpiar(self) -> None:
        for widget in self.scroll_tarjetas.winfo_children():
            widget.destroy()
        self._tarjetas_widgets.clear()
        self._elementos_tarjetas.clear()
        self.clips.clear()
        self.estados.clear()
        self._indice_seleccionado = None

    # Crea el diseño visual de una tarjeta individual
    def _crear_tarjeta(self, indice: int, clip: CandidatoClip) -> None:
        tarjeta = ctk.CTkFrame(
            self.scroll_tarjetas,
            corner_radius=8,
            border_width=1,
            border_color="#333333",
            fg_color="#1e1e1e"
        )
        tarjeta.grid(row=indice, column=0, sticky="ew", padx=4, pady=4)
        tarjeta.grid_columnconfigure(0, weight=1)

        duracion = clip.segundo_fin - clip.segundo_inicio

        # Obtenemos el nombre del archivo de forma tradicional
        if clip.ruta_video is not None:
            nombre_clip = clip.ruta_video.name
        else:
            numero = indice + 1
            nombre_clip = f"Clip {numero:02d}"

        # Fila 0: Contenedor para título y badge de color de la IA
        frame_fila0 = ctk.CTkFrame(tarjeta, fg_color="transparent")
        frame_fila0.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        frame_fila0.grid_columnconfigure(0, weight=1)

        numero_visible = indice + 1
        lbl_titulo = ctk.CTkLabel(
            frame_fila0,
            text=f"{numero_visible:02d}. {nombre_clip}",
            font=("Arial", 11, "bold"),
            anchor="w"
        )
        lbl_titulo.grid(row=0, column=0, sticky="w")

        # Distintivo visual (badge) de la categoría IA
        color_badge = COLORES_CATEGORIA.get(clip.categoria, "#424242")
        frame_badge = ctk.CTkFrame(frame_fila0, corner_radius=6, fg_color=color_badge)
        frame_badge.grid(row=0, column=1, sticky="e", padx=(4, 0))

        texto_badge = self._generar_texto_badge(clip.categoria, clip.confianza_ia)
        lbl_badge = ctk.CTkLabel(
            frame_badge,
            text=texto_badge,
            font=("Arial", 10, "bold"),
            text_color="white",
            padx=6,
            pady=1
        )
        lbl_badge.pack()

        # Fila 1: Texto con intervalo de tiempo y puntuación
        info_texto = f"[{clip.segundo_inicio}s -> {clip.segundo_fin}s] ({duracion}s)  |  Score: {clip.puntuacion:.2f}"
        lbl_info = ctk.CTkLabel(
            tarjeta,
            text=info_texto,
            font=("Arial", 11),
            text_color="#aaaaaa",
            anchor="w"
        )
        lbl_info.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 4))

        # Fila 2: Selector manual de categoría para que el usuario pueda corregirla
        frame_fila2 = ctk.CTkFrame(tarjeta, fg_color="transparent")
        frame_fila2.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))
        frame_fila2.grid_columnconfigure(1, weight=1)

        lbl_cat_prompt = ctk.CTkLabel(
            frame_fila2,
            text="Categoría:",
            font=("Arial", 10),
            text_color="#999999"
        )
        lbl_cat_prompt.grid(row=0, column=0, sticky="w", padx=(0, 6))

        def al_cambiar_categoria_manual(nueva_cat: str):
            self._on_cambio_categoria_manual(indice, nueva_cat)

        opcion_categoria = ctk.CTkOptionMenu(
            frame_fila2,
            values=LISTA_CATEGORIAS_DISPONIBLES,
            height=22,
            font=("Arial", 10),
            dropdown_font=("Arial", 10),
            fg_color="#2b2b2b",
            button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
            command=al_cambiar_categoria_manual
        )
        opcion_categoria.set(clip.categoria)
        opcion_categoria.grid(row=0, column=1, sticky="ew")

        # Fila 3: Botón de dos opciones (Aprobado o Descartado)
        def al_cambiar_estado(nuevo_valor):
            self._on_cambio_estado(indice, nuevo_valor)

        seg_estado = ctk.CTkSegmentedButton(
            tarjeta,
            values=["Aprobado", "Descartado"],
            selected_color="#2e7d32",
            selected_hover_color="#1b5e20",
            unselected_color="#333333",
            unselected_hover_color="#444444",
            font=("Arial", 11),
            height=24,
            command=al_cambiar_estado
        )
        seg_estado.set(self.estados[indice])
        seg_estado.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))

        # Al hacer clic sobre el fondo o textos de la tarjeta, se selecciona
        def al_hacer_click(evento=None):
            self.seleccionar_clip(indice)

        tarjeta.bind("<Button-1>", al_hacer_click)
        lbl_titulo.bind("<Button-1>", al_hacer_click)
        lbl_info.bind("<Button-1>", al_hacer_click)
        frame_fila0.bind("<Button-1>", al_hacer_click)

        self._tarjetas_widgets.append(tarjeta)
        self._elementos_tarjetas.append({
            "frame_badge": frame_badge,
            "lbl_badge": lbl_badge,
            "opcion_categoria": opcion_categoria
        })

    # Genera el texto visible dentro del badge de color
    def _generar_texto_badge(self, categoria: str, confianza: float) -> str:
        if categoria == "Sin clasificar" or confianza <= 0.0:
            return categoria
        porcentaje = int(round(confianza * 100))
        return f"{categoria} ({porcentaje}%)"

    # Actualiza visualmente el badge y menú cuando se analiza un clip con IA
    def actualizar_clip_ia(self, indice: int, clip_actualizado: CandidatoClip) -> None:
        if not self.clips or len(self.clips) == 0:
            return
        if indice < 0 or indice >= len(self.clips):
            return

        self.clips[indice] = clip_actualizado
        if indice < len(self._elementos_tarjetas):
            elems = self._elementos_tarjetas[indice]
            nuevo_color = COLORES_CATEGORIA.get(clip_actualizado.categoria, "#424242")
            elems["frame_badge"].configure(fg_color=nuevo_color)
            elems["lbl_badge"].configure(
                text=self._generar_texto_badge(clip_actualizado.categoria, clip_actualizado.confianza_ia)
            )
            elems["opcion_categoria"].set(clip_actualizado.categoria)

    # Permite al usuario modificar la categoría desde el desplegable
    def _on_cambio_categoria_manual(self, indice: int, nueva_categoria: str) -> None:
        if self.navegacion_bloqueada:
            return
        if not self.clips or len(self.clips) == 0 or indice < 0 or indice >= len(self.clips):
            return

        clip_actual = self.clips[indice]
        # Creamos una nueva instancia con la categoría corregida manualmente (confianza 1.0)
        clip_modificado = replace(clip_actual, categoria=nueva_categoria, confianza_ia=1.0)
        self.actualizar_clip_ia(indice, clip_modificado)
        if self.on_clips_actualizados is not None:
            self.on_clips_actualizados()

    # Actualiza la barra de progreso y estado del análisis de IA
    def establecer_estado_analisis(self, analizando: bool, texto: str = "", progreso: float = 0.0) -> None:
        if analizando:
            self.btn_analizar_ia.configure(state="disabled", text="⏳ Analizando...")
        else:
            self.btn_analizar_ia.configure(state="normal", text="✨ Analizar con IA")

        if texto:
            self.lbl_estado_ia.configure(text=texto)
        self.barra_progreso_ia.set(max(0.0, min(1.0, progreso)))

    # Bloquea o desbloquea la interacción durante procesos pesados
    def establecer_bloqueo_interaccion(self, bloqueado: bool) -> None:
        self.navegacion_bloqueada = bloqueado

    # Ejecuta el callback para lanzar el análisis IA en segundo plano
    def _on_click_analizar_ia(self) -> None:
        if self.navegacion_bloqueada:
            return
        if self.on_lanzar_ia is not None:
            self.on_lanzar_ia()

    # Destaca visualmente la tarjeta pulsada y avisa al reproductor si reproducir es True
    def seleccionar_clip(self, indice: int, reproducir: bool = True) -> None:
        if self.navegacion_bloqueada:
            return

        if not self.clips or len(self.clips) == 0:
            self._indice_seleccionado = None
            return

        if indice < 0 or indice >= len(self.clips):
            return

        self._indice_seleccionado = indice

        # Cambiamos los bordes: azul para la tarjeta activa, gris oscuro para las demás
        for i in range(len(self._tarjetas_widgets)):
            tarjeta = self._tarjetas_widgets[i]
            if i == indice:
                tarjeta.configure(border_color="#1f6aa5", border_width=2, fg_color="#262626")
            else:
                tarjeta.configure(border_color="#333333", border_width=1, fg_color="#1e1e1e")

        # Avisamos a la ventana principal para que cargue el vídeo en VLC
        if self.clips and 0 <= indice < len(self.clips):
            clip = self.clips[indice]
            if reproducir and self.on_clip_seleccionado is not None:
                self.on_clip_seleccionado(clip)

    # Actualiza el estado cuando el usuario pulsa Aprobado o Descartado
    def _on_cambio_estado(self, indice: int, nuevo_estado: str) -> None:
        if self.navegacion_bloqueada:
            return
        self.estados[indice] = nuevo_estado
        if self.clips and 0 <= indice < len(self.clips):
            clip_actual = self.clips[indice]
            self.clips[indice] = replace(clip_actual, aprobado=(nuevo_estado == "Aprobado"))
        if self.on_estado_cambiado is not None:
            self.on_estado_cambiado()
        if self.on_clips_actualizados is not None:
            self.on_clips_actualizados()

    # Devuelve una lista tradicional con los clips que tengan el estado 'Aprobado'
    def obtener_clips_aprobados(self) -> list[CandidatoClip]:
        if not self.clips or len(self.clips) == 0:
            return []
        aprobados = []
        for i in range(len(self.clips)):
            if self.estados.get(i) == "Aprobado":
                aprobados.append(self.clips[i])
        return aprobados

    # Cuenta cuántos clips hay en total, cuántos aprobados y cuántos descartados
    def obtener_conteo_estados(self) -> tuple[int, int, int]:
        if not self.clips or len(self.clips) == 0:
            return 0, 0, 0
        total = len(self.clips)
        aprobados = 0

        # Bucle tradicional para contar
        for i in range(total):
            if self.estados.get(i) == "Aprobado":
                aprobados += 1

        descartados = total - aprobados
        return total, aprobados, descartados

    # Carga clips directamente desde una carpeta de candidatos hidratando metadatos
    def cargar_clips_desde_directorio(self, carpeta: str | Path) -> list[CandidatoClip]:
        clips = self.escanear_directorio_candidatos(carpeta)
        self.cargar_clips(clips)
        return clips

    # Busca archivos .mp4 en la carpeta y lee clips_info.json si existe para hidratar las etiquetas
    @staticmethod
    def escanear_directorio_candidatos(
        carpeta: str | Path,
        ruta_json_info: str | Path | None = None
    ) -> list[CandidatoClip]:
        ruta = Path(carpeta).resolve()
        if not ruta.exists():
            return []

        # Buscamos si existe un archivo de persistencia clips_info.json
        posibles_json = []
        if ruta_json_info:
            posibles_json.append(Path(ruta_json_info).resolve())
        posibles_json.extend([
            ruta / "clips_info.json",
            ruta.parent / "clips_info.json",
            Path("downloads/clips_info.json").resolve(),
            Path("modulos/downloads/clips_info.json").resolve()
        ])

        mapa_info = {}
        for pj in posibles_json:
            if pj.exists():
                try:
                    with open(pj, "r", encoding="utf-8") as f:
                        contenido = json.load(f)
                    if isinstance(contenido, dict):
                        lista_datos = contenido.get("clips", [])
                    elif isinstance(contenido, list):
                        lista_datos = contenido
                    else:
                        lista_datos = []

                    for item in lista_datos:
                        nom = item.get("nombre_archivo")
                        if nom:
                            mapa_info[nom] = item
                        # Indexamos también por patrón numérico de tiempo
                        ini = item.get("segundo_inicio")
                        fin = item.get("segundo_fin")
                        if ini is not None and fin is not None:
                            mapa_info[f"{ini}s_{fin}s"] = item
                    print(f"[PanelClips] Hidratadas {len(lista_datos)} etiquetas desde: {pj.name}")
                    break
                except Exception as err:
                    print(f"[PanelClips] Aviso al leer persistencia {pj.name}: {err}")

        archivos = sorted(ruta.glob("*.mp4"))
        clips = []

        for f in archivos:
            # Buscamos el patrón "NUMEROSs_NUMEROSs" en el nombre (ej: clip_01_87s_117s.mp4)
            coincidencia = re.search(r"(\d+)s_(\d+)s", f.name)
            if coincidencia:
                inicio = int(coincidencia.group(1))
                fin = int(coincidencia.group(2))
            else:
                inicio = 0
                fin = 30

            # Verificamos si tenemos datos persistidos en clips_info.json para este clip
            clave_tiempo = f"{inicio}s_{fin}s"
            info = mapa_info.get(f.name) or mapa_info.get(clave_tiempo)

            if info:
                categoria = info.get("categoria", "Sin clasificar")
                confianza = float(info.get("confianza", 0.0))
                puntuacion = float(info.get("puntuacion", 0.85))
                inicio = int(info.get("segundo_inicio", inicio))
                fin = int(info.get("segundo_fin", fin))
                estado_str = info.get("estado", "Aprobado")
                esta_aprobado = (estado_str != "Descartado")
            else:
                categoria = "Sin clasificar"
                confianza = 0.0
                puntuacion = 0.85
                esta_aprobado = True

            nuevo_clip = CandidatoClip(
                segundo_inicio=inicio,
                segundo_fin=fin,
                puntuacion=puntuacion,
                ruta_video=f,
                categoria=categoria,
                confianza_ia=confianza,
                aprobado=esta_aprobado
            )
            clips.append(nuevo_clip)

        return clips


if __name__ == "__main__":
    app = ctk.CTk()
    app.title("Test PanelListaClips Enriquecido")
    app.geometry("450x650")

    def al_seleccionar(c):
        print(f"Seleccionado: [{c.segundo_inicio}s -> {c.segundo_fin}s] ({c.categoria})")

    panel = PanelListaClips(app, on_clip_seleccionado=al_seleccionar)
    panel.pack(fill="both", expand=True, padx=10, pady=10)

    clips = (
        PanelListaClips.escanear_directorio_candidatos("downloads/candidatos")
        or PanelListaClips.escanear_directorio_candidatos("modulos/downloads/candidatos")
    )

    if not clips:
        clips = [
            CandidatoClip(segundo_inicio=87, segundo_fin=117, puntuacion=0.84, categoria="Gameplay", confianza_ia=0.63),
            CandidatoClip(segundo_inicio=2051, segundo_fin=2081, puntuacion=0.91, categoria="Menú / Carga", confianza_ia=0.71),
        ]

    panel.cargar_clips(clips)
    app.mainloop()
