"""
app.py

Ventana principal de la interfaz gráfica (Fase 4 del TFG).
Ensambla el panel lateral de candidatos, el reproductor de vídeo integrado,
el panel de detalles de inspección enriquecida y el clasificador visual CLIP.
"""

from pathlib import Path
import json
import sys
import threading
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

try:
    from modulos.clasificador_clip import ClasificadorVisual, COLORES_CATEGORIA
except ImportError:
    ClasificadorVisual = None
    COLORES_CATEGORIA = {
        "Gameplay": "#2e7d32",
        "Charla / Cámara": "#1565c0",
        "Reacción / Risa": "#f57c00",
        "Menú / Carga": "#546e7a",
        "Pantalla Final / Despedida": "#c62828",
        "Sin clasificar": "#424242"
    }


class AppValidacionClips(ctk.CTk):
    # Constructor de la ventana principal: configura dimensiones, tema y componentes
    def __init__(self, ruta_candidatos: str | Path | None = None):
        super().__init__()

        # Configuración estética global
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("AutoClip Twitch - Inspección y Validación de Clips (Fase 4)")
        self.geometry("1180x720")
        self.minsize(950, 600)

        # Control de estado de fondo
        self._analizando_ia = False

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

    # Distribuye el panel lateral, el reproductor, panel de detalles y la barra inferior
    def _construir_layout(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.grid_columnconfigure(0, weight=0, minsize=380)
        self.grid_columnconfigure(1, weight=1)

        # 1. Panel lateral izquierdo (Lista de clips con cabecera y botón IA)
        self.panel_clips = PanelListaClips(
            self,
            width=380,
            on_clip_seleccionado=self._on_clip_seleccionado,
            on_estado_cambiado=self._actualizar_estadisticas,
            on_lanzar_ia=self._iniciar_analisis_ia
        )
        self.panel_clips.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(10, 5), pady=(10, 5))

        # 2. Área principal derecha (Reproductor VLC)
        self.reproductor = ReproductorVideo(self)
        self.reproductor.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=(10, 4))

        # 3. Panel de inspección y detalles del clip activo
        self.panel_detalles = ctk.CTkFrame(
            self,
            corner_radius=6,
            fg_color="#1e1e1e",
            border_width=1,
            border_color="#333333"
        )
        self.panel_detalles.grid(row=1, column=1, sticky="ew", padx=(5, 10), pady=(0, 6))
        self.panel_detalles.grid_columnconfigure(0, weight=1)

        # Fila superior de detalles: Título de clip y Badge de categoría
        self.lbl_detalle_titulo = ctk.CTkLabel(
            self.panel_detalles,
            text="Ningún clip seleccionado",
            font=("Arial", 12, "bold"),
            anchor="w"
        )
        self.lbl_detalle_titulo.grid(row=0, column=0, sticky="w", padx=12, pady=(6, 2))

        self.frame_detalle_badge = ctk.CTkFrame(
            self.panel_detalles,
            corner_radius=6,
            fg_color="#424242"
        )
        self.frame_detalle_badge.grid(row=0, column=1, sticky="e", padx=12, pady=(6, 2))

        self.lbl_detalle_badge = ctk.CTkLabel(
            self.frame_detalle_badge,
            text="Sin clasificar",
            font=("Arial", 10, "bold"),
            text_color="white",
            padx=8,
            pady=2
        )
        self.lbl_detalle_badge.pack()

        # Fila inferior de detalles: Desglose de puntuación y ponderación
        self.lbl_detalle_metricas = ctk.CTkLabel(
            self.panel_detalles,
            text="Score Algorítmico: --  |  Estimación: Audio (50%) + Chat (50%)",
            font=("Arial", 11),
            text_color="#aaaaaa",
            anchor="w"
        )
        self.lbl_detalle_metricas.grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6))

        # 4. Barra inferior de estado global y acciones
        self.barra_inferior = ctk.CTkFrame(self, height=45, corner_radius=6)
        self.barra_inferior.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
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

        self._actualizar_panel_detalles(clip)

    # Actualiza los textos y distintivos del panel de detalles inferior
    def _actualizar_panel_detalles(self, clip: CandidatoClip) -> None:
        duracion = clip.segundo_fin - clip.segundo_inicio
        nombre = clip.ruta_video.name if clip.ruta_video else "Clip"
        self.lbl_detalle_titulo.configure(
            text=f"Clip Activo: {nombre}  |  [{clip.segundo_inicio}s -> {clip.segundo_fin}s] ({duracion}s)"
        )

        color = COLORES_CATEGORIA.get(clip.categoria, "#424242")
        self.frame_detalle_badge.configure(fg_color=color)

        if clip.confianza_ia > 0:
            porcentaje = int(round(clip.confianza_ia * 100))
            texto_badge = f"{clip.categoria} ({porcentaje}%)"
        else:
            texto_badge = clip.categoria

        self.lbl_detalle_badge.configure(text=texto_badge)
        self.lbl_detalle_metricas.configure(
            text=f"Score Algorítmico: {clip.puntuacion:.2f}  |  Estimación: Audio (50%) + Chat (50%)"
        )

    # Lanza la inferencia de CLIP en un hilo secundario para no bloquear la interfaz
    def _iniciar_analisis_ia(self) -> None:
        if self._analizando_ia:
            return

        if not self.panel_clips.clips:
            self.lbl_estado.configure(text="No hay clips candidatos cargados para analizar.")
            return

        self._analizando_ia = True
        self.panel_clips.establecer_estado_analisis(True, "Cargando modelo CLIP...", 0.05)
        self.lbl_estado.configure(text="Ejecutando clasificación visual con IA (OpenAI CLIP)...")

        def tarea_fondo():
            try:
                if ClasificadorVisual is None:
                    raise ImportError("Módulo ClasificadorVisual no disponible.")

                clasificador = ClasificadorVisual()
                total = len(self.panel_clips.clips)

                def callback_progreso(actual: int, total_clips: int, clip_actualizado: CandidatoClip):
                    progreso = actual / total_clips
                    indice = actual - 1
                    texto = f"Analizando clip {actual} de {total_clips}..."

                    def en_hilo_principal(i=indice, c=clip_actualizado, t=texto, p=progreso):
                        self.panel_clips.actualizar_clip_ia(i, c)
                        self.panel_clips.establecer_estado_analisis(True, t, p)
                        if self.panel_clips._indice_seleccionado == i:
                            self._actualizar_panel_detalles(c)

                    try:
                        self.after(0, en_hilo_principal)
                    except Exception:
                        pass

                clips_clasificados = clasificador.clasificar_candidatos(
                    self.panel_clips.clips,
                    callback_progreso=callback_progreso
                )

                def al_terminar():
                    self._analizando_ia = False
                    self.panel_clips.establecer_estado_analisis(
                        False,
                        f"¡Clasificación completada! ({len(clips_clasificados)} clips)",
                        1.0
                    )
                    self.lbl_estado.configure(
                        text=f"Análisis visual completado con éxito ({len(clips_clasificados)} clips clasificados)"
                    )
                    if self.panel_clips._indice_seleccionado is not None:
                        idx = self.panel_clips._indice_seleccionado
                        if idx < len(self.panel_clips.clips):
                            self._actualizar_panel_detalles(self.panel_clips.clips[idx])

                try:
                    self.after(0, al_terminar)
                except Exception:
                    pass

            except Exception as error:
                def al_fallar(err=error):
                    self._analizando_ia = False
                    self.panel_clips.establecer_estado_analisis(False, f"Error: {err}", 0.0)
                    self.lbl_estado.configure(text=f"Error en análisis IA: {err}")

                try:
                    self.after(0, al_fallar)
                except Exception:
                    pass

        hilo = threading.Thread(target=tarea_fondo, daemon=True)
        hilo.start()

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
                "categoria": c.categoria,
                "confianza_ia": round(c.confianza_ia, 4),
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
