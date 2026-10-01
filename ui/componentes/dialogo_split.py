"""
dialogo_split.py

Diálogo modal interactivo para configurar las zonas de recorte de Pantalla Dividida
(Split Cámara + Gameplay). Extrae un fotograma del clip actual con FFmpeg, lo proyecta
en un Canvas con Pillow y permite dibujar/ajustar interactivamente las cajas de recorte.
"""

from pathlib import Path
from typing import Callable, Sequence
import tempfile
import subprocess
import shutil
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk


class DialogoConfigurarSplit(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        ruta_video: Path | str,
        cam_crop_inicial: tuple[float, float, float, float] | None = None,
        game_crop_inicial: tuple[float, float, float, float] | None = None,
        segundo_captura: float | None = None,
        nombre_clip: str = "",
        on_guardar: Callable[..., None] | None = None,
        on_cancelar: Callable[[], None] | None = None
    ):
        super().__init__(master)
        self.ruta_video = Path(ruta_video)
        self.segundo_captura = segundo_captura
        self.nombre_clip = nombre_clip or self.ruta_video.name
        self.t_captura = 1.0
        self.on_guardar = on_guardar
        self.on_cancelar = on_cancelar

        self.title(f"Configuración de Pantalla Dividida - {self.nombre_clip}")
        self.geometry("980x740")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(master)

        # Coordenadas normalizadas [x, y, w, h] en el rango 0.0 a 1.0
        self.cam_crop = list(cam_crop_inicial) if cam_crop_inicial else [0.72, 0.05, 0.25, 0.32]
        self.game_crop = list(game_crop_inicial) if game_crop_inicial else [0.0, 0.0, 1.0, 1.0]

        # Modo de edición actual: 'cam' o 'game'
        self.modo_edicion = tk.StringVar(value="cam")

        # Variables de arrastre en Canvas
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_rect_id = None

        # Dimensiones del Canvas
        self.canvas_w = 854
        self.canvas_h = 480
        self.img_tk = None

        # Extraemos y cargamos obligatoriamente el fotograma del clip activo (t = duracion / 2)
        self._cargar_fotograma()

        # Construcción de la interfaz
        self._construir_interfaz()

        # Dibujamos las cajas iniciales
        self._redibujar_superposiciones()

        # Captura modal obligatoria
        self.grab_set()

    def _cargar_fotograma(self) -> None:
        """Extrae el fotograma del clip actual con FFmpeg en su segundo medio y lo prepara para el Canvas."""
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        ruta_frame = Path(tempfile.gettempdir()) / f"split_preview_{self.ruta_video.stem}.jpg"

        # Determinamos el segundo medio (t = duracion / 2) si no viene especificado
        t_captura = 1.0
        if self.segundo_captura is not None and self.segundo_captura >= 0:
            t_captura = float(self.segundo_captura)
        elif ffprobe and self.ruta_video.exists():
            try:
                cmd_dur = [
                    ffprobe, "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(self.ruta_video)
                ]
                res = subprocess.run(cmd_dur, capture_output=True, text=True, check=False)
                if res.returncode == 0 and res.stdout.strip():
                    dur = float(res.stdout.strip())
                    t_captura = max(0.5, dur / 2.0)
            except Exception:
                t_captura = 1.0

        self.t_captura = t_captura

        if ffmpeg and self.ruta_video.exists():
            comando = [
                ffmpeg, "-y",
                "-ss", f"{t_captura:.2f}",
                "-i", str(self.ruta_video),
                "-vframes", "1",
                "-q:v", "2",
                str(ruta_frame)
            ]
            proceso = subprocess.run(comando, capture_output=True, check=False)
            if proceso.returncode != 0 or not ruta_frame.exists():
                comando[2] = "0.0"
                subprocess.run(comando, capture_output=True, check=False)

        if ruta_frame.exists():
            try:
                img_pil = Image.open(ruta_frame)
            except Exception:
                img_pil = Image.new("RGB", (1920, 1080), (30, 30, 30))
        else:
            img_pil = Image.new("RGB", (1920, 1080), (30, 30, 30))

        # Escalamos manteniendo proporción al tamaño del canvas
        img_redimensionada = img_pil.resize((self.canvas_w, self.canvas_h), Image.Resampling.LANCZOS)
        self.img_tk = ImageTk.PhotoImage(img_redimensionada)

    def _construir_interfaz(self) -> None:
        """Construye los controles interactivos, el Canvas y los botones de acción."""
        # 1. Cabecera explicativa con datos del clip activo
        frame_cabecera = ctk.CTkFrame(self, fg_color="transparent")
        frame_cabecera.pack(fill="x", padx=16, pady=(10, 4))

        lbl_titulo = ctk.CTkLabel(
            frame_cabecera,
            text=f"📐 Ajuste de Regiones para Pantalla Dividida (Clip: {self.nombre_clip})",
            font=("Arial", 15, "bold")
        )
        lbl_titulo.pack(anchor="w")

        lbl_desc = ctk.CTkLabel(
            frame_cabecera,
            text=f"Fotograma de referencia extraído en t = {self.t_captura:.1f}s (segundo medio). Arrastra para delimitar Cámara y Gameplay.",
            font=("Arial", 11),
            text_color="#aaaaaa"
        )
        lbl_desc.pack(anchor="w")

        # 2. Barra de selección de modo de edición y presets
        frame_herramientas = ctk.CTkFrame(self, fg_color="#222222", corner_radius=6)
        frame_herramientas.pack(fill="x", padx=16, pady=4)

        lbl_modo = ctk.CTkLabel(frame_herramientas, text="Zona a dibujar:", font=("Arial", 11, "bold"))
        lbl_modo.pack(side="left", padx=(10, 8), pady=8)

        rb_cam = ctk.CTkRadioButton(
            frame_herramientas,
            text="📷 Cámara (Azul)",
            variable=self.modo_edicion,
            value="cam",
            fg_color="#0288d1",
            hover_color="#03a9f4",
            text_color="#03a9f4",
            font=("Arial", 11, "bold")
        )
        rb_cam.pack(side="left", padx=8, pady=8)

        rb_game = ctk.CTkRadioButton(
            frame_herramientas,
            text="🎮 Gameplay (Verde)",
            variable=self.modo_edicion,
            value="game",
            fg_color="#2e7d32",
            hover_color="#4caf50",
            text_color="#4caf50",
            font=("Arial", 11, "bold")
        )
        rb_game.pack(side="left", padx=8, pady=8)

        # Presets rápidos
        lbl_preset = ctk.CTkLabel(frame_herramientas, text="Presets rápidos:", font=("Arial", 11, "bold"))
        lbl_preset.pack(side="left", padx=(18, 6), pady=8)

        btn_game_full = ctk.CTkButton(
            frame_herramientas,
            text="Gameplay Completo",
            width=120,
            height=26,
            font=("Arial", 10),
            fg_color="#37474f",
            hover_color="#455a64",
            command=self._preset_gameplay_completo
        )
        btn_game_full.pack(side="left", padx=4, pady=8)

        btn_cam_arriba_der = ctk.CTkButton(
            frame_herramientas,
            text="Cam Arriba-Der",
            width=100,
            height=26,
            font=("Arial", 10),
            fg_color="#37474f",
            hover_color="#455a64",
            command=lambda: self._preset_camara(0.72, 0.05, 0.25, 0.32)
        )
        btn_cam_arriba_der.pack(side="left", padx=4, pady=8)

        btn_cam_arriba_izq = ctk.CTkButton(
            frame_herramientas,
            text="Cam Arriba-Izq",
            width=100,
            height=26,
            font=("Arial", 10),
            fg_color="#37474f",
            hover_color="#455a64",
            command=lambda: self._preset_camara(0.03, 0.05, 0.25, 0.32)
        )
        btn_cam_arriba_izq.pack(side="left", padx=4, pady=8)

        # 3. Canvas central con la imagen
        frame_canvas = ctk.CTkFrame(self, fg_color="black", corner_radius=6)
        frame_canvas.pack(padx=16, pady=6)

        self.canvas = tk.Canvas(
            frame_canvas,
            width=self.canvas_w,
            height=self.canvas_h,
            bg="black",
            highlightthickness=0,
            cursor="cross"
        )
        self.canvas.pack()

        # Vinculación de eventos de ratón sobre el Canvas
        self.canvas.bind("<ButtonPress-1>", self._al_iniciar_arrastre)
        self.canvas.bind("<B1-Motion>", self._al_arrastrar)
        self.canvas.bind("<ButtonRelease-1>", self._al_finalizar_arrastre)

        # 4. Barra inferior de coordenadas informativas, opción para todos y botones Guardar/Cancelar
        frame_inferior = ctk.CTkFrame(self, fg_color="transparent")
        frame_inferior.pack(fill="x", padx=16, pady=(4, 10))

        frame_info_opciones = ctk.CTkFrame(frame_inferior, fg_color="transparent")
        frame_info_opciones.pack(side="left", fill="y", padx=4)

        self.lbl_info_coords = ctk.CTkLabel(
            frame_info_opciones,
            text="Cámara: [72%, 5%, 25%, 32%]  |  Gameplay: [0%, 0%, 100%, 100%]",
            font=("Arial", 11),
            text_color="#cccccc",
            anchor="w"
        )
        self.lbl_info_coords.pack(anchor="w", pady=(0, 2))

        self.chk_aplicar_todos = ctk.CTkCheckBox(
            frame_info_opciones,
            text="Aplicar también estas zonas como plantilla por defecto para los demás clips",
            font=("Arial", 11),
            checkbox_width=18,
            checkbox_height=18
        )
        self.chk_aplicar_todos.pack(anchor="w")
        self.chk_aplicar_todos.deselect()

        frame_botones = ctk.CTkFrame(frame_inferior, fg_color="transparent")
        frame_botones.pack(side="right", fill="y", padx=4)

        btn_guardar = ctk.CTkButton(
            frame_botones,
            text="💾 Guardar Zonas",
            font=("Arial", 12, "bold"),
            fg_color="#2e7d32",
            hover_color="#1b5e20",
            width=140,
            command=self._guardar
        )
        btn_guardar.pack(side="right", padx=(6, 0), pady=4)

        btn_cancelar = ctk.CTkButton(
            frame_botones,
            text="❌ Cancelar",
            font=("Arial", 11),
            fg_color="#424242",
            hover_color="#616161",
            width=100,
            command=self._cancelar
        )
        btn_cancelar.pack(side="right", padx=6, pady=4)

    # -------------------------------------------------------------------------
    # Gestión de interacción con el Canvas y dibujo interactivo
    # -------------------------------------------------------------------------
    def _al_iniciar_arrastre(self, event: tk.Event) -> None:
        self._drag_start_x = max(0, min(self.canvas_w, event.x))
        self._drag_start_y = max(0, min(self.canvas_h, event.y))

        color = "#00b0ff" if self.modo_edicion.get() == "cam" else "#00e676"
        if self._drag_rect_id:
            self.canvas.delete(self._drag_rect_id)

        self._drag_rect_id = self.canvas.create_rectangle(
            self._drag_start_x, self._drag_start_y,
            self._drag_start_x, self._drag_start_y,
            outline=color,
            width=2,
            dash=(4, 2)
        )

    def _al_arrastrar(self, event: tk.Event) -> None:
        cur_x = max(0, min(self.canvas_w, event.x))
        cur_y = max(0, min(self.canvas_h, event.y))

        if self._drag_rect_id:
            self.canvas.coords(
                self._drag_rect_id,
                self._drag_start_x, self._drag_start_y,
                cur_x, cur_y
            )

    def _al_finalizar_arrastre(self, event: tk.Event) -> None:
        cur_x = max(0, min(self.canvas_w, event.x))
        cur_y = max(0, min(self.canvas_h, event.y))

        x1 = min(self._drag_start_x, cur_x)
        y1 = min(self._drag_start_y, cur_y)
        x2 = max(self._drag_start_x, cur_x)
        y2 = max(self._drag_start_y, cur_y)

        # Evitamos clics accidentales sin tamaño
        ancho_px = x2 - x1
        alto_px = y2 - y1

        if ancho_px >= 16 and alto_px >= 16:
            norm_x = round(x1 / self.canvas_w, 4)
            norm_y = round(y1 / self.canvas_h, 4)
            norm_w = round(ancho_px / self.canvas_w, 4)
            norm_h = round(alto_px / self.canvas_h, 4)

            if self.modo_edicion.get() == "cam":
                self.cam_crop = [norm_x, norm_y, norm_w, norm_h]
            else:
                self.game_crop = [norm_x, norm_y, norm_w, norm_h]

        if self._drag_rect_id:
            self.canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None

        self._redibujar_superposiciones()

    def _redibujar_superposiciones(self) -> None:
        """Dibuja en el Canvas la imagen de fondo y los dos rectángulos con sus etiquetas."""
        self.canvas.delete("all")

        # Dibujar imagen de fondo
        if self.img_tk:
            self.canvas.create_image(0, 0, anchor="nw", image=self.img_tk)

        # 1. Rectángulo Gameplay (Verde)
        gx1 = int(self.game_crop[0] * self.canvas_w)
        gy1 = int(self.game_crop[1] * self.canvas_h)
        gx2 = gx1 + int(self.game_crop[2] * self.canvas_w)
        gy2 = gy1 + int(self.game_crop[3] * self.canvas_h)

        self.canvas.create_rectangle(gx1, gy1, gx2, gy2, outline="#00e676", width=2)
        self.canvas.create_text(
            gx1 + 6, gy1 + 12,
            text="🎮 Gameplay",
            fill="#00e676",
            anchor="w",
            font=("Arial", 10, "bold")
        )

        # 2. Rectángulo Cámara (Azul)
        cx1 = int(self.cam_crop[0] * self.canvas_w)
        cy1 = int(self.cam_crop[1] * self.canvas_h)
        cx2 = cx1 + int(self.cam_crop[2] * self.canvas_w)
        cy2 = cy1 + int(self.cam_crop[3] * self.canvas_h)

        self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="#00b0ff", width=2)
        self.canvas.create_text(
            cx1 + 6, cy1 + 12,
            text="📷 Cámara",
            fill="#00b0ff",
            anchor="w",
            font=("Arial", 10, "bold")
        )

        # Actualizar texto informativo
        c_pct = [int(v * 100) for v in self.cam_crop]
        g_pct = [int(v * 100) for v in self.game_crop]
        self.lbl_info_coords.configure(
            text=f"Cámara: [{c_pct[0]}%, {c_pct[1]}%, {c_pct[2]}%, {c_pct[3]}%]  |  Gameplay: [{g_pct[0]}%, {g_pct[1]}%, {g_pct[2]}%, {g_pct[3]}%]"
        )

    # -------------------------------------------------------------------------
    # Presets y acciones de cierre
    # -------------------------------------------------------------------------
    def _preset_gameplay_completo(self) -> None:
        self.game_crop = [0.0, 0.0, 1.0, 1.0]
        self._redibujar_superposiciones()

    def _preset_camara(self, x: float, y: float, w: float, h: float) -> None:
        self.cam_crop = [x, y, w, h]
        self._redibujar_superposiciones()

    def _guardar(self) -> None:
        cam_tupla = (float(self.cam_crop[0]), float(self.cam_crop[1]), float(self.cam_crop[2]), float(self.cam_crop[3]))
        game_tupla = (float(self.game_crop[0]), float(self.game_crop[1]), float(self.game_crop[2]), float(self.game_crop[3]))
        aplicar_todos = bool(self.chk_aplicar_todos.get()) if hasattr(self, "chk_aplicar_todos") else False

        if self.on_guardar:
            try:
                self.on_guardar(cam_tupla, game_tupla, aplicar_todos)
            except TypeError:
                self.on_guardar(cam_tupla, game_tupla)
        self.destroy()

    def _cancelar(self) -> None:
        if self.on_cancelar:
            self.on_cancelar()
        self.destroy()
