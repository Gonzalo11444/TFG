# inicio.py
#
# Vista de Inicio de PrendeClips.
# Permite ingresar la URL del VOD de Twitch, iniciar el pipeline completo
# en segundo plano, monitorizar el progreso, gestionar/purgar clips anteriores
# y acceder a las carpetas de salida.

from pathlib import Path
from typing import Callable
import os
import platform
import subprocess
import threading
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

try:
    from modulos.buscador_streamer import DirectoReciente, obtener_ultimos_vods
except ImportError:
    try:
        from buscador_streamer import DirectoReciente, obtener_ultimos_vods
    except ImportError:
        DirectoReciente = None
        obtener_ultimos_vods = None

# Mapeo de perfiles de detección y pesos (Audio / Chat)
MAPA_PERFILES_DETECCION = {
    "Equilibrado (50% Audio / 50% Chat)": {"peso_audio": 0.5, "peso_chat": 0.5},
    "Streamer Emergente / Reacciones (80% Audio / 20% Chat)": {"peso_audio": 0.8, "peso_chat": 0.2},
    "Comunidad Grande (30% Audio / 70% Chat)": {"peso_audio": 0.3, "peso_chat": 0.7}
}

# Mapeo de niveles de sensibilidad y umbral mínimo de puntuación
MAPA_SENSIBILIDAD_DETECCION = {
    "Normal (Recomendada)": 0.5,
    "Alta (Más momentos)": 0.35,
    "Estricta (Solo picos muy claros)": 0.65
}


# Abre la carpeta en el explorador de archivos según el sistema operativo
def abrir_carpeta_sistema(ruta: Path | str) -> None:
    carpeta = Path(ruta).resolve()
    carpeta.mkdir(parents=True, exist_ok=True)
    sistema = platform.system()
    if sistema == "Windows":
        os.startfile(str(carpeta))
    elif sistema == "Darwin":
        subprocess.run(["open", str(carpeta)], check=False)
    else:
        subprocess.run(["xdg-open", str(carpeta)], check=False)


# Elimina los archivos de la sesión previa manteniendo la estructura de directorios
# y conservando estrictamente la carpeta 'clips_verticales' con los resultados finales
def purgar_archivos_sesion(carpeta_base: Path | str) -> int:
    base = Path(carpeta_base).resolve()
    eliminados = 0

    rutas_a_revisar = [base]
    raiz = base.parent
    if (raiz / "downloads").exists() and (raiz / "downloads").resolve() not in rutas_a_revisar:
        rutas_a_revisar.append((raiz / "downloads").resolve())
    if (raiz / "modulos" / "downloads").exists() and (raiz / "modulos" / "downloads").resolve() not in rutas_a_revisar:
        rutas_a_revisar.append((raiz / "modulos" / "downloads").resolve())

    archivos_fijos = ["audio.m4a", "chat.json", "clips_info.json", "clips_aprobados.json"]

    for cb in rutas_a_revisar:
        # 1. Eliminamos archivos de señales y metadatos no exportados
        for nombre in archivos_fijos:
            archivo = cb / nombre
            if archivo.exists():
                try:
                    archivo.unlink()
                    eliminados += 1
                except Exception as err:
                    print(f"[Purga] No se pudo eliminar {archivo.name}: {err}")

        # 2. Eliminamos los fragmentos de vídeo brutos de candidatos
        carpeta_candidatos = cb / "candidatos"
        if carpeta_candidatos.exists():
            for clip in carpeta_candidatos.glob("*"):
                if clip.is_file():
                    try:
                        clip.unlink()
                        eliminados += 1
                    except Exception as err:
                        print(f"[Purga] No se pudo eliminar clip {clip.name}: {err}")

        # NOTA: cb / "clips_verticales" se conserva intacta con los vídeos 9:16 exportados

    return eliminados


class DialogoConfirmarPurga(ctk.CTkToplevel):
    # Ventana modal de confirmación estética para borrar clips anteriores
    def __init__(self, master, on_confirmar: Callable[[], None]):
        super().__init__(master)
        self.on_confirmar = on_confirmar

        self.title("Confirmar Borrado de Clips Anteriores")
        self.geometry("450x250")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self.transient(master)
        self.grab_set()

        lbl_icono = ctk.CTkLabel(self, text="⚠️", font=("Arial", 36))
        lbl_icono.pack(pady=(18, 4))

        lbl_titulo = ctk.CTkLabel(
            self,
            text="¿Borrar clips anteriores?",
            font=("Arial", 15, "bold")
        )
        lbl_titulo.pack(pady=(0, 6))

        lbl_desc = ctk.CTkLabel(
            self,
            text="Se eliminarán los fragmentos temporales en 'candidatos/',\nel audio y el historial de chat.\n\nLos vídeos renderizados en 'clips_verticales/' se conservarán intactos.",
            font=("Arial", 11),
            text_color="#cccccc",
            justify="center"
        )
        lbl_desc.pack(pady=(0, 18), padx=20)

        frame_botones = ctk.CTkFrame(self, fg_color="transparent")
        frame_botones.pack(pady=(0, 15))

        btn_eliminar = ctk.CTkButton(
            frame_botones,
            text="🗑️ Sí, borrar clips anteriores",
            font=("Arial", 11, "bold"),
            fg_color="#c62828",
            hover_color="#b71c1c",
            command=self._al_confirmar
        )
        btn_eliminar.pack(side="left", padx=8)

        btn_cancelar = ctk.CTkButton(
            frame_botones,
            text="Cancelar",
            font=("Arial", 11),
            fg_color="#333333",
            hover_color="#444444",
            command=self.destroy
        )
        btn_cancelar.pack(side="left", padx=8)

    def _al_confirmar(self) -> None:
        self.destroy()
        if self.on_confirmar is not None:
            self.on_confirmar()


class VistaInicio(ctk.CTkFrame):
    # Constructor de la pantalla de bienvenida y lanzamiento del pipeline
    def __init__(
        self,
        master,
        on_iniciar_pipeline: Callable[[str], None],
        on_cargar_existentes: Callable[[], None] | None = None,
        on_purgar_completado: Callable[[], None] | None = None,
        carpeta_salida: Path | str | None = None,
        **kwargs
    ):
        super().__init__(master, **kwargs)

        self.on_iniciar_pipeline = on_iniciar_pipeline
        self.on_cargar_existentes = on_cargar_existentes
        self.on_purgar_completado = on_purgar_completado

        if carpeta_salida is not None:
            self.carpeta_salida = Path(carpeta_salida)
        else:
            self.carpeta_salida = Path("downloads")

        self._procesando = False

        # ---------------------------------------------------------------------
        # Contenedor responsive y desplazable: Frame central + Canvas + Scrollbar
        # ---------------------------------------------------------------------
        color_fondo = self._apply_appearance_mode(self.cget("fg_color"))
        if not color_fondo or color_fondo == "transparent":
            color_fondo = "gray17"

        # Frame central contenedor que agrupa el Canvas y el Scrollbar inmediatamente pegados
        self.frame_central = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_central.pack(expand=True, fill="both")

        self.canvas = tk.Canvas(
            self.frame_central,
            bg=color_fondo,
            highlightthickness=0,
            bd=0
        )
        self.scrollbar = ttk.Scrollbar(
            self.frame_central,
            orient="vertical",
            command=self.canvas.yview
        )

        self._scrollbar_visible = True

        def _al_actualizar_scroll(first, last):
            try:
                f1, f2 = float(first), float(last)
                self.scrollbar.set(first, last)
                # Scrollbar condicional: si el contenido cabe entero verticalmente, ocultar barra
                if (f2 - f1) >= 0.999:
                    if f1 > 0.001:
                        try:
                            self.canvas.yview_moveto(0.0)
                        except Exception:
                            pass
                    if self._scrollbar_visible:
                        self.scrollbar.pack_forget()
                        self._scrollbar_visible = False
                else:
                    if not self._scrollbar_visible:
                        self.scrollbar.pack(side="right", fill="y")
                        self._scrollbar_visible = True
            except Exception:
                pass

        self.canvas.configure(yscrollcommand=_al_actualizar_scroll)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        # Frame interior que aloja todo el contenido de la vista
        self.frame_interior = ctk.CTkFrame(self.canvas, fg_color="transparent")

        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.frame_interior,
            anchor="nw"
        )

        # Ajuste dinámico de la región desplazable cada vez que cambie el contenido interior
        def _al_configurar_interior(event=None):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.frame_interior.bind("<Configure>", _al_configurar_interior)

        # Ajuste dinámico del ancho del frame interior al ancho visible del Canvas
        def _al_configurar_canvas(event):
            self.canvas.itemconfig(self.canvas_window, width=event.width)

        self.canvas.bind("<Configure>", _al_configurar_canvas)

        # Adaptabilidad responsive ante el cambio de tamaño de la ventana
        self._ultimo_ancho_vista = 0
        def _al_configurar_vista(event):
            if event.widget in (self, getattr(self, "_canvas", None)):
                if abs(event.width - self._ultimo_ancho_vista) >= 4:
                    self._ultimo_ancho_vista = event.width
                    self.actualizar_adaptabilidad(event.width)

        self.bind("<Configure>", _al_configurar_vista)

        # Configuración de scroll natural con rueda del ratón
        self._configurar_eventos_scroll()

        # Construcción del contenido dentro del frame interior
        self._construir_contenido()

    def actualizar_adaptabilidad(self, ancho_total: int | None = None) -> None:
        """Ajusta dinámicamente el centrado y los márgenes laterales del frame central."""
        try:
            if not self.winfo_exists():
                return
            if ancho_total is None or ancho_total <= 1:
                ancho_total = self.winfo_width()
            if ancho_total <= 1:
                return

            # Ancho proporcional armónico:
            # - En resoluciones reducidas (960px): ancho ~900-912px (márgenes laterales ~24px)
            # - En resolución base (1020px): ancho ~950-960px (márgenes laterales ~30px)
            # - En pantallas maximizadas (1200px - 1920px+): ancho máximo armónico de 960px centrado
            ancho_deseado = min(960, max(840, ancho_total - 60))
            pad_x = max(10, (ancho_total - ancho_deseado) // 2)

            if hasattr(self, "frame_central") and self.frame_central.winfo_exists():
                self.frame_central.pack_configure(padx=pad_x, pady=(6, 10))
        except Exception as e:
            print(f"[VistaInicio] Error en actualizar_adaptabilidad: {e}")

    def _configurar_eventos_scroll(self) -> None:
        """Configura los bindings de la rueda del ratón para Windows y Linux."""
        self.bind("<Enter>", self._al_entrar_vista)
        self.bind("<Leave>", self._al_salir_vista)
        self.canvas.bind("<MouseWheel>", self._al_mousewheel)
        self.canvas.bind("<Button-4>", self._al_mousewheel)
        self.canvas.bind("<Button-5>", self._al_mousewheel)
        self.frame_interior.bind("<MouseWheel>", self._al_mousewheel)
        self.frame_interior.bind("<Button-4>", self._al_mousewheel)
        self.frame_interior.bind("<Button-5>", self._al_mousewheel)
        if hasattr(self, "frame_central"):
            self.frame_central.bind("<MouseWheel>", self._al_mousewheel)
            self.frame_central.bind("<Button-4>", self._al_mousewheel)
            self.frame_central.bind("<Button-5>", self._al_mousewheel)

    def _al_entrar_vista(self, event=None) -> None:
        """Activa el scroll con ratón en toda la ventana al entrar a VistaInicio."""
        try:
            self.bind_all("<MouseWheel>", self._al_mousewheel)
            self.bind_all("<Button-4>", self._al_mousewheel)
            self.bind_all("<Button-5>", self._al_mousewheel)
        except Exception:
            pass

    def _al_salir_vista(self, event=None) -> None:
        """Desvincula los eventos globales de rueda al salir de VistaInicio."""
        try:
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")
        except Exception:
            pass

    def _al_mousewheel(self, event) -> None:
        """Maneja el desplazamiento vertical con la rueda del ratón."""
        try:
            if not self.winfo_exists():
                return
            if event.delta:
                # En Windows event.delta suele ser múltiplo de 120
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif getattr(event, "num", None) == 4:
                # Linux scroll up
                self.canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                # Linux scroll down
                self.canvas.yview_scroll(1, "units")
        except Exception:
            pass

    def resetear_scroll(self) -> None:
        """Reinicia la posición de scroll al inicio superior."""
        try:
            if hasattr(self, "canvas") and self.canvas.winfo_exists():
                self.canvas.yview_moveto(0.0)
        except Exception:
            pass

    # Construye los elementos visuales de la vista de inicio
    def _construir_contenido(self) -> None:
        # Tarjeta central responsive: se expande horizontalmente ocupando el ancho del canvas
        self.card_central = ctk.CTkFrame(
            self.frame_interior,
            corner_radius=12,
            fg_color="#1e1e1e",
            border_width=1,
            border_color="#333333"
        )
        self.card_central.pack(fill="x", expand=True, padx=4, pady=(8, 14))

        # 1. Cabecera y logotipo del proyecto
        lbl_icono = ctk.CTkLabel(
            self.card_central,
            text="🎬",
            font=("Arial", 38)
        )
        lbl_icono.pack(pady=(14, 2))

        lbl_titulo = ctk.CTkLabel(
            self.card_central,
            text="PrendeClips",
            font=("Arial", 24, "bold"),
            text_color="#ffffff"
        )
        lbl_titulo.pack(pady=(0, 2))

        lbl_subtitulo = ctk.CTkLabel(
            self.card_central,
            text="Extracción Inteligente de Momentos Destacados de Twitch con IA",
            font=("Arial", 12),
            text_color="#aaaaaa"
        )
        lbl_subtitulo.pack(pady=(0, 10))

        # 2. Resumen visual del Pipeline (Fases 1 a 5)
        self._construir_pasos_pipeline()

        # 3. Formulario de entrada: Streamer o URL de Twitch
        frame_input = ctk.CTkFrame(self.card_central, fg_color="transparent")
        frame_input.pack(fill="x", padx=36, pady=(6, 10))

        # 3.0 Búsqueda rápida de directos recientes por streamer
        frame_streamer = ctk.CTkFrame(
            frame_input,
            fg_color="#18181b",
            corner_radius=8,
            border_width=1,
            border_color="#333333"
        )
        frame_streamer.pack(fill="x", pady=(0, 10))

        lbl_streamer = ctk.CTkLabel(
            frame_streamer,
            text="Buscar directos recientes por streamer:",
            font=("Arial", 11, "bold"),
            text_color="#a970ff",
            anchor="w"
        )
        lbl_streamer.pack(fill="x", padx=12, pady=(6, 2))

        fila_streamer = ctk.CTkFrame(frame_streamer, fg_color="transparent")
        fila_streamer.pack(fill="x", padx=12, pady=(0, 6))

        self.entry_streamer = ctk.CTkEntry(
            fila_streamer,
            placeholder_text="Nombre del streamer (ej: ibai)...",
            font=("Arial", 12),
            height=34,
            corner_radius=6,
            border_color="#444444"
        )
        self.entry_streamer.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_streamer.bind("<Return>", lambda e: self._al_buscar_streamer())

        self.btn_buscar_streamer = ctk.CTkButton(
            fila_streamer,
            text="🔍 Buscar directos",
            font=("Arial", 12, "bold"),
            height=34,
            width=140,
            corner_radius=6,
            fg_color="#6441a5",
            hover_color="#7d5bbe",
            command=self._al_buscar_streamer
        )
        self.btn_buscar_streamer.pack(side="right")

        self.cmb_vods_recientes = ctk.CTkComboBox(
            frame_streamer,
            values=["Seleccionar directo reciente..."],
            font=("Arial", 11),
            height=32,
            corner_radius=6,
            command=self._al_seleccionar_vod_reciente
        )
        self.cmb_vods_recientes.set("Seleccionar directo reciente...")
        self.cmb_vods_recientes.pack(fill="x", padx=12, pady=(0, 8))

        # 3.1 Formulario manual: URL o ID del directo
        lbl_input = ctk.CTkLabel(
            frame_input,
            text="O introduce la URL o ID del directo manualmente:",
            font=("Arial", 11, "bold"),
            text_color="#cccccc",
            anchor="w"
        )
        lbl_input.pack(fill="x", pady=(0, 4))

        self.entry_url = ctk.CTkEntry(
            frame_input,
            placeholder_text="https://www.twitch.tv/videos/2873857636",
            font=("Arial", 12),
            height=40,
            corner_radius=8,
            border_color="#444444"
        )
        self.entry_url.pack(fill="x", pady=(0, 8))

        # Permite pulsar 'Enter' directamente en la caja de texto para lanzar
        self.entry_url.bind("<Return>", lambda e: self._al_pulsar_procesar())

        # 3.1 Sección de Configuración de Extracción de Clips
        self._construir_seccion_configuracion(frame_input)

        # 4. Botón de acción principal
        self.btn_procesar = ctk.CTkButton(
            frame_input,
            text="🚀  Procesar y Extraer Clips",
            font=("Arial", 13, "bold"),
            height=42,
            corner_radius=8,
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=self._al_pulsar_procesar
        )
        self.btn_procesar.pack(fill="x", pady=(2, 4))

        # 5. Barra de progreso y texto de fase actual
        self.frame_feedback = ctk.CTkFrame(self.card_central, fg_color="#181818", corner_radius=8)
        self.frame_feedback.pack(fill="x", padx=36, pady=(4, 10))

        self.lbl_estado = ctk.CTkLabel(
            self.frame_feedback,
            text="Listo para procesar. Pega una URL de Twitch y pulsa el botón.",
            font=("Arial", 11),
            text_color="#9e9e9e"
        )
        self.lbl_estado.pack(pady=(8, 3), padx=15)

        self.barra_progreso = ctk.CTkProgressBar(
            self.frame_feedback,
            height=6,
            corner_radius=3,
            fg_color="#2b2b2b",
            progress_color="#1f6aa5"
        )
        self.barra_progreso.pack(fill="x", padx=20, pady=(0, 8))
        self.barra_progreso.set(0.0)

        # 6. Botones secundarios de utilidad (3 columnas equilibradas)
        frame_utilidades = ctk.CTkFrame(self.card_central, fg_color="transparent")
        frame_utilidades.pack(fill="x", padx=36, pady=(0, 16))
        frame_utilidades.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_abrir_carpeta = ctk.CTkButton(
            frame_utilidades,
            text="📁 Abrir Carpeta",
            font=("Arial", 11),
            height=30,
            fg_color="#2c2c2c",
            hover_color="#3a3a3a",
            command=self._abrir_carpeta
        )
        self.btn_abrir_carpeta.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.btn_ver_existentes = ctk.CTkButton(
            frame_utilidades,
            text="👁 Ver clips guardados",
            font=("Arial", 11),
            height=30,
            fg_color="#2c2c2c",
            hover_color="#3a3a3a",
            command=self._al_cargar_existentes
        )
        self.btn_ver_existentes.grid(row=0, column=1, padx=4, sticky="ew")

        self.btn_purgar_clips = ctk.CTkButton(
            frame_utilidades,
            text="🗑️ Borrar clips anteriores",
            font=("Arial", 11),
            height=30,
            fg_color="#37474f",
            hover_color="#455a64",
            command=self._al_pulsar_purgar
        )
        self.btn_purgar_clips.grid(row=0, column=2, padx=(4, 0), sticky="ew")

    # Muestra los pequeños badges explicativos de las fases del TFG
    def _construir_pasos_pipeline(self) -> None:
        frame_pasos = ctk.CTkFrame(self.card_central, fg_color="transparent")
        frame_pasos.pack(padx=20, pady=(0, 8))

        pasos = [
            "1. Audio/Chat",
            "2. Señales 1Hz",
            "3. Recorte yt-dlp",
            "4. CLIP IA",
            "5. Render 9:16"
        ]

        for i, paso in enumerate(pasos):
            lbl_paso = ctk.CTkLabel(
                frame_pasos,
                text=paso,
                font=("Arial", 10, "bold"),
                fg_color="#2a2a2a",
                corner_radius=4,
                padx=8,
                pady=3,
                text_color="#888888"
            )
            lbl_paso.pack(side="left", padx=4)

            # Flecha entre fases
            if i < len(pasos) - 1:
                lbl_flecha = ctk.CTkLabel(
                    frame_pasos,
                    text="➔",
                    font=("Arial", 10),
                    text_color="#555555"
                )
                lbl_flecha.pack(side="left", padx=2)

    # -------------------------------------------------------------------------
    # Gestión de Búsqueda de Directos por Streamer (yt-dlp)
    # -------------------------------------------------------------------------
    def _al_buscar_streamer(self) -> None:
        """Inicia la búsqueda asíncrona de los últimos directos del streamer."""
        if self._procesando:
            return

        canal = self.entry_streamer.get().strip()
        if not canal:
            self.lbl_estado.configure(
                text="Por favor, escribe el nombre de un streamer para buscar sus directos.",
                text_color="#e06c75"
            )
            return

        # Feedback visual mientras se ejecuta la búsqueda
        self.btn_buscar_streamer.configure(state="disabled", text="⏳ Buscando...")
        self.cmb_vods_recientes.set(f"Buscando directos de '{canal}'...")
        self.lbl_estado.configure(
            text=f"Consultando directos recientes de '{canal}' con yt-dlp...",
            text_color="#a970ff"
        )

        threading.Thread(
            target=self._hilo_buscar_streamer,
            args=(canal,),
            daemon=True
        ).start()

    def _hilo_buscar_streamer(self, canal: str) -> None:
        """Hilo en segundo plano para no congelar la GUI durante la llamada a yt-dlp."""
        vods = []
        if obtener_ultimos_vods is not None:
            try:
                vods = obtener_ultimos_vods(canal, limite=5)
            except Exception as e:
                print(f"[VistaInicio] Error al buscar VODs de '{canal}': {e}")
                vods = []

        # Retornamos los resultados al hilo principal de Tkinter
        self.after(0, self._actualizar_combo_vods, canal, vods)

    def _actualizar_combo_vods(self, canal: str, vods: list) -> None:
        """Puebla el Combobox con el formato '[Fecha] Título (Duración)'."""
        self.btn_buscar_streamer.configure(state="normal", text="🔍 Buscar directos")

        if not vods:
            self.cmb_vods_recientes.configure(values=["No se encontraron directos"])
            self.cmb_vods_recientes.set(f"No se encontraron directos para '{canal}'")
            self.lbl_estado.configure(
                text=f"No se encontraron directos recientes para '{canal}'. Comprueba el nombre o escribe la URL manual.",
                text_color="#e5c07b"
            )
            self._mapa_vods = {}
            return

        self._mapa_vods = {}
        opciones = []
        for v in vods:
            # Formato requerido: "[Fecha] Título (Duración)"
            texto_item = v.texto_display
            opciones.append(texto_item)
            self._mapa_vods[texto_item] = v

        self.cmb_vods_recientes.configure(values=opciones)
        self.cmb_vods_recientes.set(f"Seleccionar directo ({len(vods)} disponibles)...")
        self.lbl_estado.configure(
            text=f"Directos encontrados para '{canal}'. Selecciona uno del desplegable para rellenar la URL.",
            text_color="#98c379"
        )

    def _al_seleccionar_vod_reciente(self, eleccion: str) -> None:
        """Rellena automáticamente el campo principal de URL al elegir un directo."""
        vod = getattr(self, "_mapa_vods", {}).get(eleccion)
        if vod is not None and getattr(vod, "url", None):
            self.entry_url.delete(0, "end")
            self.entry_url.insert(0, vod.url)
            self.lbl_estado.configure(
                text=f"Directo seleccionado: {vod.titulo} ({vod.duracion_str})",
                text_color="#98c379"
            )

    # Invoca el callback configurado al pulsar el botón principal
    def _al_pulsar_procesar(self) -> None:
        if self._procesando:
            return

        url = self.entry_url.get().strip()
        if not url:
            self.mostrar_error("Por favor, introduce una URL o ID de un VOD de Twitch.")
            return

        if self.on_iniciar_pipeline is not None:
            self.on_iniciar_pipeline(url)

    # Abre la vista de validación con los clips que ya estén en disco
    def _al_cargar_existentes(self) -> None:
        if self._procesando:
            return
        if self.on_cargar_existentes is not None:
            self.on_cargar_existentes()

    # Muestra el diálogo modal para confirmar el borrado de clips anteriores
    def _al_pulsar_purgar(self) -> None:
        if self._procesando:
            return

        DialogoConfirmarPurga(self, on_confirmar=self._ejecutar_purga)

    # Ejecuta el borrado de archivos temporales de clips anteriores
    def _ejecutar_purga(self) -> None:
        eliminados = purgar_archivos_sesion(self.carpeta_salida)
        self.lbl_estado.configure(
            text=f"🗑️ Se han borrado {eliminados} archivos de clips anteriores (conservando 'clips_verticales/').",
            text_color="#81c784"
        )
        if self.on_purgar_completado is not None:
            self.on_purgar_completado()

    # Abre la carpeta de descargas en el explorador de Windows si no hay proceso activo
    def _abrir_carpeta(self) -> None:
        if self._procesando:
            return
        abrir_carpeta_sistema(self.carpeta_salida)

    # Construye el panel visual integrado de configuración de extracción
    def _construir_seccion_configuracion(self, parent: ctk.CTkFrame) -> None:
        frame_config = ctk.CTkFrame(
            parent,
            fg_color="#181818",
            corner_radius=10,
            border_width=1,
            border_color="#2c2c2c"
        )
        frame_config.pack(fill="x", pady=(0, 10))

        # Cabecera de la sección
        frame_header = ctk.CTkFrame(frame_config, fg_color="transparent")
        frame_header.pack(fill="x", padx=16, pady=(8, 4))

        lbl_titulo_config = ctk.CTkLabel(
            frame_header,
            text="⚙️  Configuración de Extracción",
            font=("Arial", 12, "bold"),
            text_color="#e0e0e0"
        )
        lbl_titulo_config.pack(side="left")

        lbl_badge_config = ctk.CTkLabel(
            frame_header,
            text="Parámetros Fases 2 y 3",
            font=("Arial", 10),
            text_color="#90caf9",
            fg_color="#132433",
            corner_radius=4,
            padx=7,
            pady=1
        )
        lbl_badge_config.pack(side="right")

        # a) Control deslizante (CTkSlider) para el número de clips (3 a 15, default 6)
        frame_slider = ctk.CTkFrame(frame_config, fg_color="transparent")
        frame_slider.pack(fill="x", padx=16, pady=(0, 8))

        frame_slider_header = ctk.CTkFrame(frame_slider, fg_color="transparent")
        frame_slider_header.pack(fill="x", pady=(0, 4))

        lbl_slider_desc = ctk.CTkLabel(
            frame_slider_header,
            text="Número de clips candidatos:",
            font=("Arial", 11),
            text_color="#b0b0b0"
        )
        lbl_slider_desc.pack(side="left")

        self.lbl_num_clips = ctk.CTkLabel(
            frame_slider_header,
            text="6 clips",
            font=("Arial", 11, "bold"),
            text_color="#ffffff",
            fg_color="#1f6aa5",
            corner_radius=6,
            padx=8,
            pady=1
        )
        self.lbl_num_clips.pack(side="right")

        self.slider_num_clips = ctk.CTkSlider(
            frame_slider,
            from_=3,
            to=15,
            number_of_steps=12,
            height=16,
            button_color="#1f6aa5",
            button_hover_color="#144870",
            progress_color="#1f6aa5",
            fg_color="#2b2b2b",
            command=self._al_cambiar_slider_clips
        )
        self.slider_num_clips.set(6)
        self.slider_num_clips.pack(fill="x", pady=(2, 0))

        # b y c) Selectores en 2 columnas: Perfil de Detección y Sensibilidad
        frame_selectores = ctk.CTkFrame(frame_config, fg_color="transparent")
        frame_selectores.pack(fill="x", padx=16, pady=(0, 10))
        frame_selectores.grid_columnconfigure(0, weight=3)
        frame_selectores.grid_columnconfigure(1, weight=2)

        # Columna 1: Perfil de detección (Audio / Chat)
        frame_col_perfil = ctk.CTkFrame(frame_selectores, fg_color="transparent")
        frame_col_perfil.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        lbl_perfil = ctk.CTkLabel(
            frame_col_perfil,
            text="Perfil de detección:",
            font=("Arial", 11),
            text_color="#b0b0b0",
            anchor="w"
        )
        lbl_perfil.pack(fill="x", pady=(0, 4))

        self.opt_perfil = ctk.CTkOptionMenu(
            frame_col_perfil,
            values=list(MAPA_PERFILES_DETECCION.keys()),
            font=("Arial", 11),
            dropdown_font=("Arial", 11),
            fg_color="#262626",
            button_color="#1f6aa5",
            button_hover_color="#144870",
            dropdown_fg_color="#1c1c1c",
            height=32
        )
        self.opt_perfil.set("Equilibrado (50% Audio / 50% Chat)")
        self.opt_perfil.pack(fill="x")

        # Columna 2: Sensibilidad (Umbral de puntuación)
        frame_col_sens = ctk.CTkFrame(frame_selectores, fg_color="transparent")
        frame_col_sens.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        lbl_sens = ctk.CTkLabel(
            frame_col_sens,
            text="Sensibilidad:",
            font=("Arial", 11),
            text_color="#b0b0b0",
            anchor="w"
        )
        lbl_sens.pack(fill="x", pady=(0, 4))

        self.opt_sensibilidad = ctk.CTkOptionMenu(
            frame_col_sens,
            values=list(MAPA_SENSIBILIDAD_DETECCION.keys()),
            font=("Arial", 11),
            dropdown_font=("Arial", 11),
            fg_color="#262626",
            button_color="#1f6aa5",
            button_hover_color="#144870",
            dropdown_fg_color="#1c1c1c",
            height=32
        )
        self.opt_sensibilidad.set("Normal (Recomendada)")
        self.opt_sensibilidad.pack(fill="x")

    # Actualiza dinámicamente la etiqueta de número de clips al mover el slider
    def _al_cambiar_slider_clips(self, valor: float) -> None:
        clips = int(round(valor))
        self.lbl_num_clips.configure(text=f"{clips} clips")

    # Devuelve los parámetros de extracción configurados por el usuario
    def obtener_configuracion_extraccion(self) -> dict:
        num_clips = int(round(self.slider_num_clips.get()))
        num_clips = max(3, min(15, num_clips))

        perfil_elegido = self.opt_perfil.get()
        sensibilidad_elegida = self.opt_sensibilidad.get()

        pesos = MAPA_PERFILES_DETECCION.get(
            perfil_elegido,
            {"peso_audio": 0.5, "peso_chat": 0.5}
        )
        umbral = MAPA_SENSIBILIDAD_DETECCION.get(
            sensibilidad_elegida,
            0.5
        )

        return {
            "num_clips": num_clips,
            "peso_audio": float(pesos["peso_audio"]),
            "peso_chat": float(pesos["peso_chat"]),
            "umbral_score": float(umbral)
        }

    # Devuelve el texto actualmente escrito en el campo de URL
    def obtener_url(self) -> str:
        return self.entry_url.get().strip()

    # Habilita o deshabilita los controles durante la ejecución pesada
    def establecer_modo_procesando(self, activo: bool) -> None:
        self._procesando = activo
        if activo:
            if hasattr(self, "entry_streamer"):
                self.entry_streamer.configure(state="disabled")
            if hasattr(self, "btn_buscar_streamer"):
                self.btn_buscar_streamer.configure(state="disabled")
            if hasattr(self, "cmb_vods_recientes"):
                self.cmb_vods_recientes.configure(state="disabled")
            self.entry_url.configure(state="disabled")
            self.slider_num_clips.configure(state="disabled")
            self.opt_perfil.configure(state="disabled")
            self.opt_sensibilidad.configure(state="disabled")
            self.btn_procesar.configure(state="disabled", text="⏳ Procesando en segundo plano...")
            self.btn_abrir_carpeta.configure(state="disabled")
            self.btn_ver_existentes.configure(state="disabled")
            self.btn_purgar_clips.configure(state="disabled")
            self.barra_progreso.configure(mode="indeterminate")
            self.barra_progreso.start()
            self.lbl_estado.configure(
                text="Iniciando pipeline de extracción... Por favor, espera.",
                text_color="#1f6aa5"
            )
        else:
            if hasattr(self, "entry_streamer"):
                self.entry_streamer.configure(state="normal")
            if hasattr(self, "btn_buscar_streamer"):
                self.btn_buscar_streamer.configure(state="normal")
            if hasattr(self, "cmb_vods_recientes"):
                self.cmb_vods_recientes.configure(state="normal")
            self.entry_url.configure(state="normal")
            self.slider_num_clips.configure(state="normal")
            self.opt_perfil.configure(state="normal")
            self.opt_sensibilidad.configure(state="normal")
            self.btn_procesar.configure(state="normal", text="🚀  Procesar y Extraer Clips")
            self.btn_abrir_carpeta.configure(state="normal")
            self.btn_ver_existentes.configure(state="normal")
            self.btn_purgar_clips.configure(state="normal")
            self.barra_progreso.stop()
            self.barra_progreso.configure(mode="determinate")
            self.barra_progreso.set(0.0)

    # Actualiza el mensaje descriptivo y la barra de progreso
    def actualizar_progreso(self, mensaje: str, porcentaje: float) -> None:
        self.lbl_estado.configure(text=mensaje, text_color="#e0e0e0")

        # Si pasamos un porcentaje válido, cambiamos a modo determinate para mostrarlo
        if 0.0 <= porcentaje <= 1.0:
            if self.barra_progreso.cget("mode") != "determinate":
                self.barra_progreso.stop()
                self.barra_progreso.configure(mode="determinate")
            self.barra_progreso.set(porcentaje)

    # Muestra un mensaje de advertencia o error en color rojizo
    def mostrar_error(self, mensaje: str) -> None:
        self.lbl_estado.configure(text=f"⚠️ {mensaje}", text_color="#ef5350")
