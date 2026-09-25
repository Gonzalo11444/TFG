"""
app.py

Ventana principal de la interfaz gráfica
Ensambla el panel lateral de candidatos con el reproductor de vídeo
para la inspección y aprobación final de clips.
"""

from pathlib import Path
import json
import sys
from dataclasses import asdict
import customtkinter as ctk

# Ajustamos rutas de importación si se ejecuta directamente
directorio_raiz = Path(__file__).resolve().parents[1]
if str(directorio_raiz) not in sys.path:
    sys.path.insert(0, str(directorio_raiz))

from ui.componentes.reproductor import ReproductorVideo
from ui.componentes.lista_clips import PanelListaClips

try:
    from modulos.seleccion_temporal import CandidatoClip
except ImportError:
    from ui.componentes.lista_clips import CandidatoClip


class AppValidacionClips(ctk.CTk):
    # Constructor de la ventana principal: configura dimensiones, tema y componentes
    def __init__(self, ruta_candidatos: str | Path | None = None):
        super().__init__()

        # Configuración estética global
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("AutoClip Twitch - Inspección y Validación de Clips (Fase 4)")
        self.geometry("1100x680")
        self.minsize(900, 550)

        # Resolución de la carpeta de clips candidatos
        self.carpeta_candidatos = self._localizar_carpeta_candidatos(ruta_candidatos)

        # Construcción visual
        self._construir_layout()

        # Vinculación del evento de cierre limpio
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

        # Cargar clips disponibles en disco al iniciar
        self._cargar_datos_iniciales()

    # Busca la carpeta donde están guardados los clips candidatos en disco
    def _localizar_carpeta_candidatos(self, ruta_manual: str | Path | None) -> Path:
        if ruta_manual:
            return Path(ruta_manual)

        posibles_rutas = [
            Path("downloads/candidatos"),
            Path("modulos/downloads/candidatos"),
            directorio_raiz / "modulos" / "downloads" / "candidatos",
            directorio_raiz / "downloads" / "candidatos",
        ]
        for p in posibles_rutas:
            if p.exists():
                return p

        # Ruta por defecto aunque aún no exista
        return Path("modulos/downloads/candidatos")

    # Distribuye el panel lateral, el reproductor y la barra inferior en una cuadrícula (grid)
    def _construir_layout(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=0, minsize=340)
        self.grid_columnconfigure(1, weight=1)

        # 1. Panel lateral izquierdo (Lista de clips)
        self.panel_clips = PanelListaClips(
            self,
            width=340,
            on_clip_seleccionado=self._on_clip_seleccionado,
            on_estado_cambiado=self._actualizar_estadisticas
        )
        self.panel_clips.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=(10, 5))

        # 2. Área principal derecha (Reproductor VLC)
        self.reproductor = ReproductorVideo(self)
        self.reproductor.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=(10, 5))

        # 3. Barra inferior de estado y acciones
        self.barra_inferior = ctk.CTkFrame(self, height=45, corner_radius=6)
        self.barra_inferior.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        self.barra_inferior.grid_columnconfigure(0, weight=1)

        self.lbl_estado = ctk.CTkLabel(
            self.barra_inferior,
            text="Cargando clips...",
            font=("Arial", 12)
        )
        self.lbl_estado.grid(row=0, column=0, sticky="w", padx=15, pady=8)

        self.btn_exportar = ctk.CTkButton(
            self.barra_inferior,
            text="Confirmar y Exportar Selección",
            font=("Arial", 12, "bold"),
            fg_color="#2e7d32",
            hover_color="#1b5e20",
            command=self._exportar_seleccion
        )
        self.btn_exportar.grid(row=0, column=1, padx=15, pady=8)

    # Escanea los archivos de clips en disco y llena el panel lateral
    def _cargar_datos_iniciales(self) -> None:
        clips = PanelListaClips.escanear_directorio_candidatos(self.carpeta_candidatos)

        if clips:
            self.panel_clips.cargar_clips(clips)
            self._actualizar_estadisticas()
        else:
            self.lbl_estado.configure(
                text=f"No se encontraron clips en: '{self.carpeta_candidatos.resolve()}'"
            )

    # Se ejecuta cuando el usuario hace clic en una tarjeta de la lista
    def _on_clip_seleccionado(self, clip: CandidatoClip) -> None:
        if clip.ruta_video and clip.ruta_video.exists():
            self.reproductor.cargar_video(clip.ruta_video)
        else:
            print(f"[Aviso] El clip no tiene archivo físico en disco: {clip}")

    # Consulta al panel de clips el recuento actual y actualiza el texto inferior
    def _actualizar_estadisticas(self) -> None:
        total, aprobados, descartados = self.panel_clips.obtener_conteo_estados()
        self.lbl_estado.configure(
            text=f"Total: {total}  |  Aprobados: {aprobados}  |  Descartados: {descartados}"
        )

    # Guarda en un archivo JSON los datos de los clips que quedaron en estado 'Aprobado'
    def _exportar_seleccion(self) -> None:
        aprobados = self.panel_clips.obtener_clips_aprobados()

        carpeta_exportacion = self.carpeta_candidatos.parent
        ruta_salida = carpeta_exportacion / "clips_aprobados.json"

        datos = []
        for c in aprobados:
            datos.append({
                "segundo_inicio": c.segundo_inicio,
                "segundo_fin": c.segundo_fin,
                "duracion": c.segundo_fin - c.segundo_inicio,
                "puntuacion": c.puntuacion,
                "archivo": str(c.ruta_video.resolve()) if c.ruta_video else None
            })

        with open(ruta_salida, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)

        print(f"Exportados {len(aprobados)} clips a: {ruta_salida.resolve()}")
        self.lbl_estado.configure(
            text=f"¡Exportados {len(aprobados)} clips aprobados en: {ruta_salida.name}!"
        )

    # Se ejecuta al pulsar la 'X' de la ventana para detener VLC antes de salir
    def _al_cerrar(self) -> None:
        try:
            self.reproductor.liberar_recursos()
        except Exception:
            pass
        self.destroy()


# Función de entrada para lanzar la interfaz gráfica
def iniciar_aplicacion() -> None:
    app = AppValidacionClips()
    app.mainloop()


if __name__ == "__main__":
    iniciar_aplicacion()
