"""
app.py

Ventana principal de la interfaz gráfica (Fase 4 del TFG).
Ensambla el panel lateral de candidatos, el reproductor de vídeo integrado,
el panel de detalles de inspección enriquecida y el clasificador visual CLIP.
"""

from pathlib import Path
from typing import Callable
from tkinter import messagebox
import json
import sys
import threading
import customtkinter as ctk

# Aseguramos que la raíz del proyecto esté en sys.path
directorio_raiz = Path(__file__).resolve().parents[1]
if str(directorio_raiz) not in sys.path:
    sys.path.insert(0, str(directorio_raiz))

# Vistas y componentes de la interfaz
from ui.vistas.inicio import VistaInicio, abrir_carpeta_sistema, purgar_archivos_sesion
from ui.componentes.reproductor import ReproductorVideo
from ui.componentes.lista_clips import PanelListaClips

# Importación de modelos y módulos del núcleo
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

try:
    from modulos.pipeline import PipelineClips
except ImportError:
    PipelineClips = None

try:
    from modulos.renderizador_vertical import RenderizadorVertical
except ImportError:
    try:
        from modulos.procesamiento_video import RenderizadorVertical
    except ImportError:
        RenderizadorVertical = None

try:
    from ui.componentes.dialogo_split import DialogoConfigurarSplit
except ImportError:
    try:
        from componentes.dialogo_split import DialogoConfigurarSplit
    except ImportError:
        DialogoConfigurarSplit = None



class VentanaExitoRender(ctk.CTkToplevel):
    # Ventana modal emergente que confirma la generación de vídeos verticales
    def __init__(self, master, total_clips: int, carpeta_salida: Path):
        super().__init__(master)
        self.carpeta_salida = carpeta_salida

        self.title("Renderizado Finalizado")
        self.geometry("460x270")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        # Centrar sobre la ventana principal
        self.transient(master)
        self.grab_set()

        # Contenido visual
        lbl_icono = ctk.CTkLabel(self, text="🎉", font=("Arial", 38))
        lbl_icono.pack(pady=(22, 6))

        lbl_titulo = ctk.CTkLabel(
            self,
            text="¡Clips Verticales Generados!",
            font=("Arial", 16, "bold")
        )
        lbl_titulo.pack(pady=(0, 6))

        lbl_msg = ctk.CTkLabel(
            self,
            text=f"Se han renderizado {total_clips} vídeo(s) en formato 9:16 (1080x1920)\nlistos para TikTok, Shorts y Reels en:\n{self.carpeta_salida.resolve()}",
            font=("Arial", 11),
            text_color="#cccccc",
            justify="center"
        )
        lbl_msg.pack(pady=(0, 20), padx=25)

        frame_acciones = ctk.CTkFrame(self, fg_color="transparent")
        frame_acciones.pack(pady=(0, 15))

        btn_abrir = ctk.CTkButton(
            frame_acciones,
            text="📁 Abrir Carpeta",
            font=("Arial", 12, "bold"),
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=self._al_abrir_carpeta
        )
        btn_abrir.pack(side="left", padx=8)

        btn_cerrar = ctk.CTkButton(
            frame_acciones,
            text="Aceptar",
            font=("Arial", 12),
            fg_color="#333333",
            hover_color="#444444",
            command=self.destroy
        )
        btn_cerrar.pack(side="left", padx=8)

    def _al_abrir_carpeta(self) -> None:
        abrir_carpeta_sistema(self.carpeta_salida)
        self.destroy()


class AppPrendeClips(ctk.CTk):
    # Ventana principal: coordina la navegación y la ejecución de tareas asíncronas
    def __init__(self, ruta_candidatos: str | Path | None = None):
        super().__init__()

        # Apariencia global
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("PrendeClips - Pipeline End-to-End de Twitch")
        self.geometry("1200x750")
        self.minsize(980, 620)

        # Variables de control de estado de hilos
        self._ejecutando_pipeline = False
        self._hilo_pipeline: threading.Thread | None = None
        self._analizando_ia = False
        self._renderizando_vertical = False

        # Configuración de rutas
        self.carpeta_base = self._localizar_carpeta_base(ruta_candidatos)
        self.carpeta_candidatos = self.carpeta_base / "candidatos"
        self.carpeta_verticales = self.carpeta_base / "clips_verticales"

        self.carpeta_candidatos.mkdir(parents=True, exist_ok=True)
        self.carpeta_verticales.mkdir(parents=True, exist_ok=True)

        # Metadatos dinámicos de extracción de la sesión
        self.peso_audio = 0.5
        self.peso_chat = 0.5
        self.perfil_nombre = "Equilibrado (50% Audio / 50% Chat)"
        self._cargar_metadatos_extraccion_disco()

        # Configuración persistente en sesión para renderizado vertical (Blur vs Split)
        self.estilo_render_vertical = "Fondo desenfocado (Blur)"
        self.split_cam_crop: tuple[float, float, float, float] | None = None
        self.split_game_crop: tuple[float, float, float, float] | None = None
        self.split_crops_por_clip: dict[str, dict] = {}

        # Contenedor principal de vistas
        self._construir_vistas()

        # Vinculación del cierre limpio para liberar recursos de VLC
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

        # Mostramos la vista de inicio por defecto
        self.mostrar_vista_inicio()

    # Carga los metadatos de extracción (pesos y perfil) desde clips_info.json si existen
    def _cargar_metadatos_extraccion_disco(self) -> None:
        posibles = [
            self.carpeta_base / "clips_info.json",
            directorio_raiz / "downloads" / "clips_info.json",
            directorio_raiz / "modulos" / "downloads" / "clips_info.json"
        ]
        for p in posibles:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        datos = json.load(f)
                    if isinstance(datos, dict) and "metadatos_extraccion" in datos:
                        meta = datos["metadatos_extraccion"]
                        self.peso_audio = float(meta.get("peso_audio", self.peso_audio))
                        self.peso_chat = float(meta.get("peso_chat", self.peso_chat))
                        self.perfil_nombre = str(meta.get("perfil_nombre", self.perfil_nombre))
                        return
                    elif isinstance(datos, list) and datos:
                        primer = datos[0]
                        if "peso_audio" in primer:
                            self.peso_audio = float(primer.get("peso_audio", self.peso_audio))
                            self.peso_chat = float(primer.get("peso_chat", self.peso_chat))
                            self.perfil_nombre = str(primer.get("perfil_nombre", self.perfil_nombre))
                            return
                except Exception:
                    pass

    # Determina la carpeta base para lecturas y descargas
    def _localizar_carpeta_base(self, ruta_manual: str | Path | None) -> Path:
        if ruta_manual:
            return Path(ruta_manual).resolve()

        if (directorio_raiz / "modulos" / "downloads").exists():
            return (directorio_raiz / "modulos" / "downloads").resolve()

        return (directorio_raiz / "downloads").resolve()

    # Inicializa las dos vistas de la aplicación: Inicio y Validación
    def _construir_vistas(self) -> None:
        # 1. Vista de Inicio
        self.vista_inicio = VistaInicio(
            self,
            on_iniciar_pipeline=self._ejecutar_pipeline_fondo,
            on_cargar_existentes=self._ir_a_clips_existentes,
            on_purgar_completado=self._al_purgar_clips,
            carpeta_salida=self.carpeta_base
        )

        # 2. Vista de Validación y Edición (contenedor de inspección)
        self.frame_validacion = ctk.CTkFrame(self, fg_color="transparent")
        self._construir_vista_validacion()

    # Construye el layout de inspección con VLC, lista de clips y barra de acciones
    def _construir_vista_validacion(self) -> None:
        self.frame_validacion.grid_rowconfigure(0, weight=1)
        self.frame_validacion.grid_rowconfigure(1, weight=0)
        self.frame_validacion.grid_rowconfigure(2, weight=0)
        self.frame_validacion.grid_columnconfigure(0, weight=0, minsize=380)
        self.frame_validacion.grid_columnconfigure(1, weight=1)

        # 1. Panel lateral izquierdo (Tarjetas de clips)
        self.panel_clips = PanelListaClips(
            self.frame_validacion,
            width=380,
            on_clip_seleccionado=self._on_clip_seleccionado,
            on_estado_cambiado=self._actualizar_estadisticas,
            on_lanzar_ia=self._iniciar_analisis_ia,
            on_clips_actualizados=self._guardar_persistencia_clips_info
        )
        self.panel_clips.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(10, 5), pady=(10, 5))

        # 2. Área principal derecha (Reproductor VLC)
        self.reproductor = ReproductorVideo(self.frame_validacion)
        self.reproductor.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=(10, 4))

        # 3. Panel de detalles del clip activo
        self.panel_detalles = ctk.CTkFrame(
            self.frame_validacion,
            corner_radius=6,
            fg_color="#1e1e1e",
            border_width=1,
            border_color="#333333"
        )
        self.panel_detalles.grid(row=1, column=1, sticky="ew", padx=(5, 10), pady=(0, 6))
        self.panel_detalles.grid_columnconfigure(0, weight=1)

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

        peso_aud_pct = int(round(self.peso_audio * 100))
        peso_chat_pct = int(round(self.peso_chat * 100))
        self.lbl_detalle_metricas = ctk.CTkLabel(
            self.panel_detalles,
            text=f"Score Algorítmico: --  |  Estimación: Audio ({peso_aud_pct}%) + Chat ({peso_chat_pct}%)",
            font=("Arial", 11),
            text_color="#aaaaaa",
            anchor="w"
        )
        self.lbl_detalle_metricas.grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6))

        # 4. Barra inferior de acciones y estado
        self.barra_inferior = ctk.CTkFrame(self.frame_validacion, height=48, corner_radius=6)
        self.barra_inferior.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        self.barra_inferior.grid_columnconfigure(1, weight=1)

        # Botón de retroceso hacia la vista de inicio
        self.btn_volver_inicio = ctk.CTkButton(
            self.barra_inferior,
            text="⬅ Volver al Inicio",
            width=140,
            font=("Arial", 11, "bold"),
            fg_color="#2c2c2c",
            hover_color="#3a3a3a",
            command=self.mostrar_vista_inicio
        )
        self.btn_volver_inicio.grid(row=0, column=0, padx=(10, 5), pady=8)

        # Etiqueta informativa del conteo de clips
        # Etiqueta informativa del conteo de clips
        self.lbl_estado = ctk.CTkLabel(
            self.barra_inferior,
            text="Esperando selección...",
            font=("Arial", 12)
        )
        self.lbl_estado.grid(row=0, column=1, sticky="w", padx=10, pady=8)

        # Selector de estilo de renderizado (Blur vs Split)
        self.cmb_estilo_render = ctk.CTkOptionMenu(
            self.barra_inferior,
            values=["Fondo desenfocado (Blur)", "Pantalla dividida (Split)"],
            width=185,
            font=("Arial", 11),
            fg_color="#37474f",
            button_color="#455a64",
            button_hover_color="#546e7a",
            command=self._al_cambiar_estilo_render
        )
        self.cmb_estilo_render.set(self.estilo_render_vertical)
        self.cmb_estilo_render.grid(row=0, column=2, padx=(4, 2), pady=8)

        # Botón para ajustar zonas de cámara y gameplay
        self.btn_configurar_split = ctk.CTkButton(
            self.barra_inferior,
            text="📐 Ajustar Zonas",
            width=115,
            font=("Arial", 11),
            fg_color="#0277bd",
            hover_color="#01579b",
            command=self._abrir_dialogo_split
        )
        self.btn_configurar_split.grid(row=0, column=3, padx=2, pady=8)

        # Botón para exportar selección a JSON
        self.btn_exportar_json = ctk.CTkButton(
            self.barra_inferior,
            text="💾 Guardar JSON",
            width=115,
            font=("Arial", 11),
            fg_color="#37474f",
            hover_color="#455a64",
            command=self._exportar_seleccion
        )
        self.btn_exportar_json.grid(row=0, column=4, padx=4, pady=8)

        # Botón para renderizar clips aprobados a vertical 9:16
        self.btn_render_vertical = ctk.CTkButton(
            self.barra_inferior,
            text="🎬  Renderizar Vertical (9:16)",
            font=("Arial", 12, "bold"),
            fg_color="#2e7d32",
            hover_color="#1b5e20",
            command=self._renderizar_verticales
        )
        self.btn_render_vertical.grid(row=0, column=5, padx=(4, 10), pady=8)

    # Cambia la visualización a la vista de bienvenida y libera descriptores de archivo
    def mostrar_vista_inicio(self) -> None:
        # Si el pipeline o procesos pesados están en ejecución en segundo plano, mostramos diálogo de alerta
        if self._hilo_pipeline is not None and self._hilo_pipeline.is_alive():
            messagebox.showwarning(
                "Análisis en curso",
                "Hay un proceso de descarga o análisis en curso en segundo plano. Espera a que finalice para evitar estados inconsistentes."
            )
            return

        if self._analizando_ia:
            messagebox.showwarning(
                "Clasificación IA en curso",
                "Se están analizando los clips con OpenAI CLIP. Espera a que finalice la inferencia antes de salir."
            )
            return

        if self._renderizando_vertical:
            messagebox.showwarning(
                "Renderizado en curso",
                "Hay un renderizado vertical en segundo plano. Espera a que termine antes de volver al inicio."
            )
            return

        # c) En la transición de salida (al pulsar volver atrás o salir), forzar obligatoriamente
        # self.reproductor.player.stop() y desvincular el medio antes de desmontar o cambiar el Frame
        try:
            if hasattr(self, "reproductor") and self.reproductor is not None:
                if hasattr(self.reproductor, "player") and self.reproductor.player is not None:
                    self.reproductor.player.stop()
                    self.reproductor.player.set_media(None)
                self.reproductor.detener()
        except Exception as e:
            print(f"[App] Aviso al detener reproductor: {e}")

        self.frame_validacion.pack_forget()
        self.vista_inicio.pack(fill="both", expand=True)
        self.update_idletasks()

    # Bloquea o desbloquea los controles de navegación y acciones durante tareas pesadas
    def _bloquear_navegacion_validacion(self, bloqueado: bool) -> None:
        estado = "disabled" if bloqueado else "normal"

        if hasattr(self, "btn_volver_inicio"):
            self.btn_volver_inicio.configure(state=estado)
        if hasattr(self, "cmb_estilo_render"):
            self.cmb_estilo_render.configure(state=estado)
        if hasattr(self, "btn_configurar_split"):
            self.btn_configurar_split.configure(state=estado)
        if hasattr(self, "btn_exportar_json"):
            self.btn_exportar_json.configure(state=estado)
        if hasattr(self, "btn_render_vertical"):
            if not bloqueado:
                self.btn_render_vertical.configure(state="normal", text="🎬  Renderizar Vertical (9:16)")
            else:
                self.btn_render_vertical.configure(state="disabled")
        if hasattr(self, "panel_clips"):
            if hasattr(self.panel_clips, "btn_analizar_ia"):
                if not bloqueado:
                    self.panel_clips.btn_analizar_ia.configure(state="normal", text="✨ Analizar con IA")
                else:
                    self.panel_clips.btn_analizar_ia.configure(state="disabled")
            self.panel_clips.establecer_bloqueo_interaccion(bloqueado)

    # Cambia la visualización a la vista de validación asegurando el mapeo del HWND de VLC
    def mostrar_vista_validacion(self, clips: list[CandidatoClip] | None = None) -> None:
        self.vista_inicio.pack_forget()
        self.frame_validacion.pack(fill="both", expand=True)

        # a) Al mostrar la vista de validación, invocar primero self.update_idletasks()
        self.update_idletasks()

        if clips is not None:
            self.panel_clips.cargar_clips(clips)
            self._actualizar_estadisticas()
        elif not self.panel_clips.clips or len(self.panel_clips.clips) == 0:
            self.panel_clips.cargar_clips_desde_directorio(self.carpeta_candidatos)
            self._actualizar_estadisticas()

        # b) Si hay clips disponibles, postergar la vinculación del HWND de VLC y la carga del primer clip unos 150 ms
        if self.panel_clips.clips and len(self.panel_clips.clips) > 0:
            self.after(150, self._seleccionar_primer_clip_seguro)
        else:
            self._limpiar_detalles_sin_clip()

    # Selecciona el primer clip de la lista de forma segura si existen elementos
    def _seleccionar_primer_clip_seguro(self) -> None:
        if self.panel_clips.clips and len(self.panel_clips.clips) > 0:
            self.panel_clips.seleccionar_clip(0, reproducir=True)
        else:
            self._limpiar_detalles_sin_clip()

    # Limpia el panel de detalles y el reproductor cuando no hay clips cargados
    def _limpiar_detalles_sin_clip(self) -> None:
        try:
            if hasattr(self, "reproductor") and self.reproductor is not None:
                self.reproductor.detener()
        except Exception:
            pass

        self.lbl_detalle_titulo.configure(text="No hay clips disponibles")
        self.frame_detalle_badge.configure(fg_color="#424242")
        self.lbl_detalle_badge.configure(text="Sin clips")
        peso_aud_pct = int(round(self.peso_audio * 100))
        peso_chat_pct = int(round(self.peso_chat * 100))
        self.lbl_detalle_metricas.configure(
            text=f"No hay clips candidatos cargados.  |  Estimación: Audio ({peso_aud_pct}%) + Chat ({peso_chat_pct}%)"
        )

    # Limpia la interfaz cuando el usuario pulsa en purgar desde la vista de inicio
    def _al_purgar_clips(self) -> None:
        self.panel_clips.cargar_clips([])
        self._actualizar_estadisticas()
        self._limpiar_detalles_sin_clip()

    # Carga directamente los clips existentes en disco sin necesidad de descargar
    def _ir_a_clips_existentes(self) -> None:
        if self._ejecutando_pipeline or (self._hilo_pipeline and self._hilo_pipeline.is_alive()):
            return

        self._cargar_metadatos_extraccion_disco()
        clips = self.panel_clips.cargar_clips_desde_directorio(self.carpeta_candidatos)
        if clips and len(clips) > 0:
            self.mostrar_vista_validacion(clips)
        else:
            self.vista_inicio.mostrar_error(
                f"No se encontraron clips en '{self.carpeta_candidatos.name}'. Pega una URL para procesar."
            )

    # Lanza el pipeline completo en un hilo secundario sin congelar la ventana
    def _ejecutar_pipeline_fondo(self, url: str) -> None:
        if self._ejecutando_pipeline:
            return

        # NUNCA se borran clips automáticamente; la persistencia está asegurada
        self._ejecutando_pipeline = True
        self.vista_inicio.establecer_modo_procesando(True)

        # Obtenemos los parámetros parametrizados de extracción configurados por el usuario
        config_extraccion = self.vista_inicio.obtener_configuracion_extraccion()
        num_clips = config_extraccion.get("num_clips", 6)
        peso_audio = config_extraccion.get("peso_audio", 0.5)
        peso_chat = config_extraccion.get("peso_chat", 0.5)
        umbral_score = config_extraccion.get("umbral_score", 0.5)
        perfil_nombre = self.vista_inicio.opt_perfil.get()

        self.peso_audio = peso_audio
        self.peso_chat = peso_chat
        self.perfil_nombre = perfil_nombre

        def tarea_hilo():
            try:
                if PipelineClips is None:
                    raise ImportError("No se pudo cargar el módulo orquestador 'PipelineClips'.")

                pipeline = PipelineClips(carpeta_base=self.carpeta_base)

                def callback_progreso(mensaje: str, porcentaje: float):
                    def actualizar():
                        self.vista_inicio.actualizar_progreso(mensaje, porcentaje)
                    try:
                        self.after(0, actualizar)
                    except Exception:
                        pass

                clips_obtenidos = pipeline.ejecutar(
                    url_vod=url,
                    callback_progreso=callback_progreso,
                    num_clips=num_clips,
                    peso_audio=peso_audio,
                    peso_chat=peso_chat,
                    umbral_score=umbral_score,
                    perfil_nombre=perfil_nombre
                )

                def exito():
                    self._ejecutando_pipeline = False
                    self._hilo_pipeline = None
                    self.vista_inicio.establecer_modo_procesando(False)
                    self.mostrar_vista_validacion(clips_obtenidos)

                try:
                    self.after(0, exito)
                except Exception:
                    pass

            except Exception as error:
                def fallo(err=str(error)):
                    self._ejecutando_pipeline = False
                    self._hilo_pipeline = None
                    self.vista_inicio.establecer_modo_procesando(False)
                    self.vista_inicio.mostrar_error(err)

                try:
                    self.after(0, fallo)
                except Exception:
                    pass

        self._hilo_pipeline = threading.Thread(target=tarea_hilo, daemon=True)
        self._hilo_pipeline.start()

    # Evento al seleccionar un clip en la lista de la vista de validación
    def _on_clip_seleccionado(self, clip: CandidatoClip | None) -> None:
        if clip is None:
            self._limpiar_detalles_sin_clip()
            return

        if clip.ruta_video and clip.ruta_video.exists():
            self.reproductor.cargar_video(clip.ruta_video)
        else:
            print(f"[Aviso] El archivo no existe en disco: {clip.ruta_video}")
            self.reproductor.detener()

        self._actualizar_panel_detalles(clip)

    # Actualiza los textos y badges del panel inferior de detalles
    def _actualizar_panel_detalles(self, clip: CandidatoClip | None) -> None:
        if clip is None:
            self._limpiar_detalles_sin_clip()
            return

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
        peso_aud_pct = int(round(self.peso_audio * 100))
        peso_chat_pct = int(round(self.peso_chat * 100))
        self.lbl_detalle_metricas.configure(
            text=f"Score Algorítmico: {clip.puntuacion:.2f}  |  Estimación: Audio ({peso_aud_pct}%) + Chat ({peso_chat_pct}%)"
        )

    # Lanza la inferencia de CLIP bajo demanda en la vista de validación
    def _iniciar_analisis_ia(self) -> None:
        if self._analizando_ia or self._renderizando_vertical:
            return

        if not self.panel_clips.clips or len(self.panel_clips.clips) == 0:
            self.lbl_estado.configure(text="No hay clips para analizar.")
            return

        self._analizando_ia = True
        self._bloquear_navegacion_validacion(True)
        self.panel_clips.establecer_estado_analisis(True, "Cargando modelo CLIP...", 0.05)
        self.lbl_estado.configure(text="Analizando clips con OpenAI CLIP...")

        def tarea_fondo():
            try:
                if ClasificadorVisual is None:
                    raise ImportError("Módulo ClasificadorVisual no disponible.")

                clasificador = ClasificadorVisual()
                clips_a_clasificar = list(self.panel_clips.clips)
                total = len(clips_a_clasificar)

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
                    clips_a_clasificar,
                    callback_progreso=callback_progreso
                )

                def al_terminar():
                    self._analizando_ia = False
                    self._bloquear_navegacion_validacion(False)
                    self.panel_clips.establecer_estado_analisis(
                        False,
                        f"¡Clasificación completada! ({len(clips_clasificados)} clips)",
                        1.0
                    )
                    self.lbl_estado.configure(
                        text=f"Análisis visual completado ({len(clips_clasificados)} clips clasificados)"
                    )
                    if self.panel_clips._indice_seleccionado is not None:
                        idx = self.panel_clips._indice_seleccionado
                        if self.panel_clips.clips and 0 <= idx < len(self.panel_clips.clips):
                            self._actualizar_panel_detalles(self.panel_clips.clips[idx])
                    # Guardamos la persistencia en clips_info.json tras la inferencia de CLIP
                    self._guardar_persistencia_clips_info()

                try:
                    self.after(0, al_terminar)
                except Exception:
                    pass

            except Exception as error:
                def al_fallar(err=error):
                    self._analizando_ia = False
                    self._bloquear_navegacion_validacion(False)
                    self.panel_clips.establecer_estado_analisis(False, f"Error: {err}", 0.0)
                    self.lbl_estado.configure(text=f"Error en análisis IA: {err}")

                try:
                    self.after(0, al_fallar)
                except Exception:
                    pass

        hilo = threading.Thread(target=tarea_fondo, daemon=True)
        hilo.start()

    # Actualiza el conteo de clips aprobados y descartados en la barra inferior
    def _actualizar_estadisticas(self) -> None:
        total, aprobados, descartados = self.panel_clips.obtener_conteo_estados()
        self.lbl_estado.configure(
            text=f"Total: {total}  |  Aprobados: {aprobados}  |  Descartados: {descartados}"
        )

    # Vuelca el estado y etiquetas actuales de todos los clips en clips_info.json para persistencia permanente
    def _guardar_persistencia_clips_info(self) -> Path | None:
        if not hasattr(self, "panel_clips") or not self.panel_clips.clips:
            return None

        ruta_json = self.carpeta_base / "clips_info.json"
        meta = {
            "peso_audio": self.peso_audio,
            "peso_chat": self.peso_chat,
            "perfil_nombre": self.perfil_nombre
        }

        datos = []
        for i, clip in enumerate(self.panel_clips.clips):
            nombre = clip.ruta_video.name if clip.ruta_video else f"clip_{clip.segundo_inicio}s_{clip.segundo_fin}s.mp4"
            estado = self.panel_clips.estados.get(i, "Aprobado" if clip.aprobado else "Pendiente")
            datos.append({
                "nombre_archivo": nombre,
                "ruta": str(clip.ruta_video.resolve()) if clip.ruta_video else None,
                "segundo_inicio": clip.segundo_inicio,
                "segundo_fin": clip.segundo_fin,
                "duracion": clip.segundo_fin - clip.segundo_inicio,
                "puntuacion": clip.puntuacion,
                "categoria": clip.categoria,
                "confianza": round(clip.confianza_ia, 4),
                "estado": estado,
                "peso_audio": self.peso_audio,
                "peso_chat": self.peso_chat,
                "perfil_nombre": self.perfil_nombre
            })

        contenido = {
            "metadatos_extraccion": meta,
            "clips": datos
        }

        try:
            ruta_json.parent.mkdir(parents=True, exist_ok=True)
            with open(ruta_json, "w", encoding="utf-8") as f:
                json.dump(contenido, f, indent=4, ensure_ascii=False)
            print(f"[App] Persistencia actualizada en: {ruta_json.resolve()}")

            # Si la carpeta base es modulos/downloads, reflejar también en downloads/ en la raíz si procede
            raiz_downloads = directorio_raiz / "downloads" / "clips_info.json"
            if ruta_json.resolve() != raiz_downloads.resolve():
                try:
                    raiz_downloads.parent.mkdir(parents=True, exist_ok=True)
                    with open(raiz_downloads, "w", encoding="utf-8") as f_raiz:
                        json.dump(contenido, f_raiz, indent=4, ensure_ascii=False)
                except Exception:
                    pass

            return ruta_json
        except Exception as error:
            print(f"[App] Error al guardar persistencia en {ruta_json}: {error}")
            return None

    # Guarda los clips aprobados en un archivo JSON estructurado
    def _exportar_seleccion(self) -> Path | None:
        if self._analizando_ia or self._renderizando_vertical:
            return None

        if not self.panel_clips.clips or len(self.panel_clips.clips) == 0:
            self.lbl_estado.configure(text="⚠️ No hay clips con estado 'Aprobado' para exportar.")
            return None

        aprobados = self.panel_clips.obtener_clips_aprobados()
        if not aprobados or len(aprobados) == 0:
            self.lbl_estado.configure(text="⚠️ No hay clips con estado 'Aprobado' para exportar.")
            return None

        # Actualizamos también la persistencia general de la sesión
        self._guardar_persistencia_clips_info()

        ruta_salida = self.carpeta_base / "clips_aprobados.json"

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
            text=f"¡Guardados {len(aprobados)} clips aprobados en '{ruta_salida.name}'!"
        )
        return ruta_salida

    # Cambia el estilo de renderizado vertical y asiste al usuario si elige Pantalla Dividida
    def _al_cambiar_estilo_render(self, nuevo_estilo: str) -> None:
        self.estilo_render_vertical = nuevo_estilo
        if "dividida" in nuevo_estilo.lower() or "split" in nuevo_estilo.lower():
            if self.split_cam_crop is None or self.split_game_crop is None:
                self._abrir_dialogo_split()

    # Abre el modal interactivo de recorte para pantalla dividida (Cámara + Gameplay)
    def _abrir_dialogo_split(self) -> None:
        if not self.panel_clips.clips or len(self.panel_clips.clips) == 0:
            messagebox.showwarning(
                "Sin clips disponibles",
                "Carga o analiza clips candidatos antes de configurar las zonas de pantalla dividida."
            )
            return

        # 1. Obtener obligatoriamente el clip activo (reproduciéndose o seleccionado)
        clip_actual = None
        if hasattr(self, "reproductor") and self.reproductor.ruta_actual:
            for c in self.panel_clips.clips:
                if c.ruta_video and Path(c.ruta_video).resolve() == Path(self.reproductor.ruta_actual).resolve():
                    clip_actual = c
                    break

        if clip_actual is None and hasattr(self.panel_clips, "obtener_clip_seleccionado"):
            clip_actual = self.panel_clips.obtener_clip_seleccionado()

        if clip_actual is None:
            idx = getattr(self.panel_clips, "_indice_seleccionado", None)
            if idx is not None and 0 <= idx < len(self.panel_clips.clips):
                clip_actual = self.panel_clips.clips[idx]

        if clip_actual is None and self.panel_clips.clips:
            clip_actual = self.panel_clips.clips[0]

        if clip_actual is None or not clip_actual.ruta_video or not Path(clip_actual.ruta_video).exists():
            messagebox.showwarning(
                "Vídeo no encontrado",
                "No se encontró el clip de vídeo en disco para extraer el fotograma de referencia."
            )
            return

        ruta_video = Path(clip_actual.ruta_video)
        nombre_clip = ruta_video.name

        # 2. Extraer obligatoriamente fotograma en el segundo medio (t = duracion / 2)
        segundo_captura = None
        try:
            cmd_probe = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(ruta_video)
            ]
            res = subprocess.run(cmd_probe, capture_output=True, text=True, check=False)
            if res.returncode == 0 and res.stdout.strip():
                dur = float(res.stdout.strip())
                segundo_captura = max(0.5, dur / 2.0)
        except Exception:
            segundo_captura = None

        if segundo_captura is None:
            dur_estimada = clip_actual.segundo_fin - clip_actual.segundo_inicio
            segundo_captura = max(0.5, dur_estimada / 2.0) if dur_estimada > 0 else 1.0

        # 3. Zonas iniciales: si este clip ya tenía un recorte configurado, usarlo; si no, plantilla por defecto
        custom_clip = self.split_crops_por_clip.get(nombre_clip) or self.split_crops_por_clip.get(str(ruta_video.resolve()))
        if custom_clip:
            cam_inicial = custom_clip.get("cam_crop", custom_clip.get("cam"))
            game_inicial = custom_clip.get("game_crop", custom_clip.get("game"))
        else:
            cam_inicial = self.split_cam_crop
            game_inicial = self.split_game_crop

        def on_guardar_split(cam_crop, game_crop, aplicar_todos=False):
            # Guardamos específicamente para el clip activo
            datos_crop = {
                "cam_crop": cam_crop,
                "game_crop": game_crop,
                "cam": cam_crop,
                "game": game_crop
            }
            self.split_crops_por_clip[nombre_clip] = datos_crop
            self.split_crops_por_clip[str(ruta_video.resolve())] = datos_crop

            # Si el usuario eligió aplicar como plantilla a todos o aún no hay plantilla global
            if aplicar_todos or self.split_cam_crop is None:
                self.split_cam_crop = cam_crop
                self.split_game_crop = game_crop

            self.estilo_render_vertical = "Pantalla dividida (Split)"
            self.cmb_estilo_render.set("Pantalla dividida (Split)")

            if aplicar_todos:
                self.lbl_estado.configure(
                    text=f"✅ Zonas guardadas para '{nombre_clip}' y aplicadas por defecto a los demás clips."
                )
            else:
                self.lbl_estado.configure(
                    text=f"✅ Zonas guardadas específicamente para el clip activo '{nombre_clip}'."
                )

        if DialogoConfigurarSplit is None:
            messagebox.showerror("Error", "No se pudo cargar el componente DialogoConfigurarSplit.")
            return

        DialogoConfigurarSplit(
            master=self,
            ruta_video=ruta_video,
            cam_crop_inicial=cam_inicial,
            game_crop_inicial=game_inicial,
            segundo_captura=segundo_captura,
            nombre_clip=nombre_clip,
            on_guardar=on_guardar_split
        )

    # Ejecuta en segundo plano la Fase 5: reencuadre vertical con FFmpeg
    def _renderizar_verticales(self) -> None:
        if self._renderizando_vertical or self._analizando_ia:
            return

        if not self.panel_clips.clips or len(self.panel_clips.clips) == 0:
            self.lbl_estado.configure(
                text="⚠️ No hay clips cargados para renderizar."
            )
            return

        aprobados = self.panel_clips.obtener_clips_aprobados()
        if not aprobados or len(aprobados) == 0:
            self.lbl_estado.configure(
                text="⚠️ Debes marcar al menos un clip como 'Aprobado' para renderizarlo."
            )
            return

        # Guardamos primero el JSON actualizado
        ruta_json = self._exportar_seleccion()
        if ruta_json is None:
            return

        # Determinamos el modo de renderizado y coordenadas
        estilo_sel = self.cmb_estilo_render.get()
        if "dividida" in estilo_sel.lower() or "split" in estilo_sel.lower():
            if self.split_cam_crop is None and not self.split_crops_por_clip:
                print("[App] Aviso: Pantalla dividida seleccionada pero sin zonas configuradas. Aplicando fondo desenfocado por seguridad.")
                modo_render = "blur"
                cam_crop = None
                game_crop = None
            else:
                modo_render = "split"
                cam_crop = self.split_cam_crop
                game_crop = self.split_game_crop
        else:
            modo_render = "blur"
            cam_crop = None
            game_crop = None

        self._renderizando_vertical = True
        self._bloquear_navegacion_validacion(True)
        self.btn_render_vertical.configure(state="disabled", text="⏳ Renderizando...")
        desc_modo = "Pantalla Dividida" if modo_render == "split" else "Fondo Desenfocado"
        self.lbl_estado.configure(
            text=f"Iniciando renderizado vertical ({desc_modo}) de {len(aprobados)} clips..."
        )

        def tarea_fondo():
            try:
                if RenderizadorVertical is None:
                    raise ImportError("Módulo RenderizadorVertical no disponible.")

                renderizador = RenderizadorVertical(
                    carpeta_salida=self.carpeta_verticales,
                    preset="veryfast"
                )

                def callback_progreso_render(actual: int, total: int, ruta_resultado: Path):
                    def en_ui():
                        self.lbl_estado.configure(
                            text=f"🎬 Renderizando [{actual}/{total}]: {ruta_resultado.name}..."
                        )
                    try:
                        self.after(0, en_ui)
                    except Exception:
                        pass

                videos_generados = renderizador.procesar_clips_aprobados(
                    ruta_json=ruta_json,
                    callback_progreso=callback_progreso_render,
                    modo=modo_render,
                    cam_crop=cam_crop,
                    game_crop=game_crop,
                    crops_por_clip=self.split_crops_por_clip
                )

                def al_terminar():
                    self._renderizando_vertical = False
                    self._bloquear_navegacion_validacion(False)
                    self.lbl_estado.configure(
                        text=f"¡Renderizado completado con éxito! ({len(videos_generados)} clips generados)"
                    )
                    # Mostramos la ventana emergente con acceso directo a la carpeta
                    VentanaExitoRender(self, len(videos_generados), self.carpeta_verticales)

                try:
                    self.after(0, al_terminar)
                except Exception:
                    pass

            except Exception as error:
                def al_fallar(err=str(error)):
                    self._renderizando_vertical = False
                    self._bloquear_navegacion_validacion(False)
                    self.lbl_estado.configure(text=f"Error en renderizado: {err}")

                try:
                    self.after(0, al_fallar)
                except Exception:
                    pass

        hilo = threading.Thread(target=tarea_fondo, daemon=True)
        hilo.start()

    # Cierre controlado al pulsar la 'X' de la ventana
    def _al_cerrar(self) -> None:
        try:
            if hasattr(self, "reproductor") and self.reproductor is not None:
                if hasattr(self.reproductor, "player") and self.reproductor.player is not None:
                    self.reproductor.player.stop()
                    self.reproductor.player.set_media(None)
                self.reproductor.liberar_recursos()
        except Exception:
            pass
        self.destroy()


# Punto de entrada para ejecutar la interfaz
def iniciar_aplicacion() -> None:
    app = AppPrendeClips()
    app.mainloop()


if __name__ == "__main__":
    iniciar_aplicacion()
