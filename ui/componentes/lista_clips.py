"""
lista_clips.py

Panel lateral con scroll que muestra las tarjetas de clips candidatos.
Permite seleccionarlos para reproducción y cambiar su estado (Aprobado / Descartado).
"""

from pathlib import Path
from typing import Callable
import re
import customtkinter as ctk

# Intento de importación del modelo de datos de la Fase 3
try:
    from modulos.seleccion_temporal import CandidatoClip
except ImportError:
    # Definición de respaldo por si se prueba este componente de forma aislada
    from dataclasses import dataclass

    @dataclass(frozen=True, slots=True)
    class CandidatoClip:
        segundo_inicio: int
        segundo_fin: int
        puntuacion: float
        ruta_video: Path | None = None


class PanelListaClips(ctk.CTkScrollableFrame):
    # Constructor del panel: inicializa variables, callbacks y la lista vacía de clips
    def __init__(
        self,
        master,
        on_clip_seleccionado: Callable[[CandidatoClip], None] | None = None,
        on_estado_cambiado: Callable[[], None] | None = None,
        **kwargs
    ):
        # super() llama al constructor del padre (CTkScrollableFrame) para heredar el scroll
        super().__init__(master, **kwargs)

        self.on_clip_seleccionado = on_clip_seleccionado
        self.on_estado_cambiado = on_estado_cambiado

        self.clips: list[CandidatoClip] = []
        self.estados: dict[int, str] = {}  # Guarda el estado de cada clip: {0: "Aprobado", 1: "Descartado"...}
        self._tarjetas_widgets: list[ctk.CTkFrame] = []
        self._indice_seleccionado: int | None = None

        # weight=1 hace que la columna se estire y ocupe todo el ancho del panel lateral
        self.grid_columnconfigure(0, weight=1)

    # Carga la lista de clips y crea las tarjetas visuales
    def cargar_clips(self, clips: list[CandidatoClip]) -> None:
        self.limpiar()
        self.clips = list(clips)

        # Por defecto, todos los candidatos empiezan marcados como 'Aprobado'
        for i in range(len(self.clips)):
            self.estados[i] = "Aprobado"

        if not self.clips:
            lbl_vacio = ctk.CTkLabel(
                self,
                text="No hay clips candidatos disponibles.",
                text_color="gray"
            )
            lbl_vacio.grid(row=0, column=0, pady=20)
            return

        # Creamos una tarjeta visual para cada clip
        for i in range(len(self.clips)):
            clip = self.clips[i]
            self._crear_tarjeta(i, clip)
        # Seleccionamos el primer clip por defecto para que se cargue en el reproductor
        self.seleccionar_clip(0)

    # Borra todas las tarjetas actuales del panel
    def limpiar(self) -> None:
        for widget in self.winfo_children():
            widget.destroy()
        self._tarjetas_widgets.clear()
        self.clips.clear()
        self.estados.clear()
        self._indice_seleccionado = None

    # Crea el diseño visual de una tarjeta individual
    def _crear_tarjeta(self, indice: int, clip: CandidatoClip) -> None:
        tarjeta = ctk.CTkFrame(
            self,
            corner_radius=8,
            border_width=1,
            border_color="#333333",
            fg_color="#1e1e1e"
        )
        tarjeta.grid(row=indice, column=0, sticky="ew", padx=6, pady=4)
        tarjeta.grid_columnconfigure(0, weight=1)

        duracion = clip.segundo_fin - clip.segundo_inicio

        # Obtenemos el nombre del archivo de forma tradicional
        if clip.ruta_video is not None:
            nombre_clip = clip.ruta_video.name
        else:
            numero = indice + 1
            nombre_clip = f"Clip {numero:02d}"

        # Fila 1: Título con el nombre del clip
        numero_visible = indice + 1
        lbl_titulo = ctk.CTkLabel(
            tarjeta,
            text=f"{numero_visible:02d}. {nombre_clip}",
            font=("Arial", 12, "bold"),
            anchor="w"
        )
        lbl_titulo.grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))

        # Fila 2: Texto con intervalo de tiempo y puntuación
        info_texto = f"[{clip.segundo_inicio}s -> {clip.segundo_fin}s] ({duracion}s)  |  Score: {clip.puntuacion:.2f}"
        lbl_info = ctk.CTkLabel(
            tarjeta,
            text=info_texto,
            font=("Arial", 11),
            text_color="#aaaaaa",
            anchor="w"
        )
        lbl_info.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 6))

        # Función sencilla para capturar el cambio de opción sin usar lambda
        def al_cambiar_opcion(nuevo_valor):
            self._on_cambio_estado(indice, nuevo_valor)

        # Fila 3: Botón de dos opciones (Aprobado o Descartado)
        seg_estado = ctk.CTkSegmentedButton(
            tarjeta,
            values=["Aprobado", "Descartado"],
            selected_color="#2e7d32",
            selected_hover_color="#1b5e20",
            unselected_color="#333333",
            unselected_hover_color="#444444",
            font=("Arial", 11),
            height=26,
            command=al_cambiar_opcion
        )
        seg_estado.set(self.estados[indice])
        seg_estado.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))

        # Al hacer clic sobre cualquier parte de la tarjeta, se selecciona
        def al_hacer_click(evento=None):
            self.seleccionar_clip(indice)

        tarjeta.bind("<Button-1>", al_hacer_click)
        lbl_titulo.bind("<Button-1>", al_hacer_click)
        lbl_info.bind("<Button-1>", al_hacer_click)

        self._tarjetas_widgets.append(tarjeta)

    # Destaca visualmente la tarjeta pulsada y avisa al reproductor
    def seleccionar_clip(self, indice: int) -> None:
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
        clip = self.clips[indice]
        if self.on_clip_seleccionado is not None:
            self.on_clip_seleccionado(clip)

    # Actualiza el estado cuando el usuario pulsa Aprobado o Descartado
    def _on_cambio_estado(self, indice: int, nuevo_estado: str) -> None:
        self.estados[indice] = nuevo_estado
        if self.on_estado_cambiado is not None:
            self.on_estado_cambiado()

    # Devuelve una lista tradicional con los clips que tengan el estado 'Aprobado'
    def obtener_clips_aprobados(self) -> list[CandidatoClip]:
        aprobados = []
        for i in range(len(self.clips)):
            if self.estados[i] == "Aprobado":
                aprobados.append(self.clips[i])
        return aprobados

    # Cuenta cuántos clips hay en total, cuántos aprobados y cuántos descartados
    def obtener_conteo_estados(self) -> tuple[int, int, int]:
        total = len(self.clips)
        aprobados = 0

        # Bucle tradicional para contar
        for estado in self.estados.values():
            if estado == "Aprobado":
                aprobados += 1

        descartados = total - aprobados
        return total, aprobados, descartados

    # Busca archivos .mp4 en la carpeta y extrae los segundos de inicio y fin del nombre
    @staticmethod
    def escanear_directorio_candidatos(carpeta: str | Path) -> list[CandidatoClip]:
        ruta = Path(carpeta)
        if not ruta.exists():
            return []

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

            nuevo_clip = CandidatoClip(
                segundo_inicio=inicio,
                segundo_fin=fin,
                puntuacion=0.85,
                ruta_video=f
            )
            clips.append(nuevo_clip)

        return clips


if __name__ == "__main__":
    app = ctk.CTk()
    app.title("Test PanelListaClips")
    app.geometry("400x600")

    def al_seleccionar(c):
        print(f"Seleccionado: [{c.segundo_inicio}s -> {c.segundo_fin}s] ({c.ruta_video})")

    panel = PanelListaClips(app, on_clip_seleccionado=al_seleccionar)
    panel.pack(fill="both", expand=True, padx=10, pady=10)

    # Buscamos clips reales en disco
    clips = (
        PanelListaClips.escanear_directorio_candidatos("downloads/candidatos")
        or PanelListaClips.escanear_directorio_candidatos("modulos/downloads/candidatos")
    )

    if not clips:
        clips = [
            CandidatoClip(segundo_inicio=87, segundo_fin=117, puntuacion=0.84),
            CandidatoClip(segundo_inicio=2051, segundo_fin=2081, puntuacion=0.91),
        ]

    panel.cargar_clips(clips)
    app.mainloop()
