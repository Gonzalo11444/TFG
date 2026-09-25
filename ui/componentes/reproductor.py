"""
reproductor.py

Widget reproductor de vídeo integrado con python-vlc y CustomTkinter.
Incrusta la superficie de renderizado de VLC en Windows mediante HWND nativo.
"""

from pathlib import Path
import tkinter as tk
import customtkinter as ctk
import vlc


class ReproductorVideo(ctk.CTkFrame):
    # Constructor del reproductor: inicia VLC, variables y crea la interfaz
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        # Variables de control del reproductor
        self.ruta_actual: Path | None = None
        self._arrastrando_slider = False
        self._duracion_ms = 0
        self._loop_progreso_id = None

        # Inicialización del motor VLC
        self.vlc_instance = vlc.Instance("--no-xlib", "--quiet")
        self.player = self.vlc_instance.media_player_new()

        # Construcción visual de la pantalla y controles
        self._construir_interfaz()

        # Volumen inicial al 80%
        self.player.audio_set_volume(80)

    # Crea la pantalla negra y los botones de control inferiores
    def _construir_interfaz(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 1. Contenedor de vídeo nativo (Tkinter Frame negro)
        # VLC necesita este frame del sistema operativo para proyectar la imagen
        self.frame_pantalla = tk.Frame(self, bg="black")
        self.frame_pantalla.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 0))

        # 2. Panel inferior con los botones y sliders
        self.frame_controles = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_controles.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        self.frame_controles.grid_columnconfigure(2, weight=1)

        # Botón Play / Pausa
        self.btn_play = ctk.CTkButton(
            self.frame_controles,
            text="▶",
            width=36,
            height=32,
            font=("Arial", 16, "bold"),
            command=self._alternar_reproduccion
        )
        self.btn_play.grid(row=0, column=0, padx=(0, 8))

        # Botón Stop
        self.btn_stop = ctk.CTkButton(
            self.frame_controles,
            text="⏹",
            width=36,
            height=32,
            font=("Arial", 14),
            fg_color="#444444",
            hover_color="#555555",
            command=self.detener
        )
        self.btn_stop.grid(row=0, column=1, padx=(0, 8))

        # Barra deslizante de tiempo (seek)
        self.slider_tiempo = ctk.CTkSlider(
            self.frame_controles,
            from_=0.0,
            to=1.0,
            command=self._on_slider_arrastre
        )
        self.slider_tiempo.set(0.0)
        self.slider_tiempo.grid(row=0, column=2, sticky="ew", padx=8)

        # Eventos del slider para evitar tirones mientras el usuario arrastra con el ratón
        self.slider_tiempo.bind("<ButtonPress-1>", self._on_slider_presionado)
        self.slider_tiempo.bind("<ButtonRelease-1>", self._on_slider_soltado)

        # Etiqueta de tiempo transcurrido / total (00:00 / 00:00)
        self.lbl_tiempo = ctk.CTkLabel(
            self.frame_controles,
            text="00:00 / 00:00",
            font=("Consolas", 12),
            width=100
        )
        self.lbl_tiempo.grid(row=0, column=3, padx=8)

        # Control deslizante de volumen
        lbl_vol = ctk.CTkLabel(self.frame_controles, text="Vol:", font=("Arial", 11))
        lbl_vol.grid(row=0, column=4, padx=(8, 2))

        self.slider_volumen = ctk.CTkSlider(
            self.frame_controles,
            from_=0,
            to=100,
            width=80,
            command=self._on_volumen_cambio
        )
        self.slider_volumen.set(80)
        self.slider_volumen.grid(row=0, column=5, padx=(2, 0))

    # Conecta el identificador HWND de la ventana de Windows con VLC
    def _vincular_ventana_vlc(self) -> None:
        self.frame_pantalla.update_idletasks()
        hwnd = self.frame_pantalla.winfo_id()
        self.player.set_hwnd(hwnd)

    # Carga un archivo de vídeo local y lo prepara para reproducir
    def cargar_video(self, ruta_video: Path | str) -> None:
        ruta = Path(ruta_video).resolve()
        if not ruta.exists():
            print(f"Vídeo no encontrado: {ruta}")
            return

        self.detener()
        self.ruta_actual = ruta

        # Cargamos el archivo en VLC
        media = self.vlc_instance.media_new(str(ruta))
        self.player.set_media(media)

        # Enlazamos la pantalla negra con el reproductor
        self._vincular_ventana_vlc()

        # Iniciamos la reproducción
        self.reproducir()
        self.btn_play.configure(text="⏸")

    # Inicia la reproducción del vídeo
    def reproducir(self) -> None:
        self._vincular_ventana_vlc()
        self.player.play()
        self.btn_play.configure(text="⏸")
        self._iniciar_bucle_progreso()

    # Pausa el vídeo sin reiniciar el tiempo
    def pausar(self) -> None:
        self.player.pause()
        self.btn_play.configure(text="▶")

    # Detiene el vídeo y reinicia la barra de tiempo a cero
    def detener(self) -> None:
        self.player.stop()
        self.btn_play.configure(text="▶")
        self.slider_tiempo.set(0.0)
        self.lbl_tiempo.configure(text="00:00 / 00:00")
        self._detener_bucle_progreso()

    # Alterna entre Play y Pausa según el estado actual
    def _alternar_reproduccion(self) -> None:
        if self.player.is_playing():
            self.pausar()
        else:
            self.reproducir()

    # Arranca el temporizador de actualización periódica
    def _iniciar_bucle_progreso(self) -> None:
        self._detener_bucle_progreso()
        self._actualizar_progreso()

    # Cancela el temporizador de actualización
    def _detener_bucle_progreso(self) -> None:
        if self._loop_progreso_id is not None:
            self.after_cancel(self._loop_progreso_id)
            self._loop_progreso_id = None

    # Consulta a VLC cada 100ms para mover la barra y actualizar los minutos/segundos
    def _actualizar_progreso(self) -> None:
        try:
            if self.player.is_playing() and not self._arrastrando_slider:
                pos = self.player.get_position()  # Devuelve de 0.0 a 1.0
                tiempo_actual_ms = self.player.get_time()
                duracion_ms = self.player.get_length()

                if duracion_ms > 0:
                    self._duracion_ms = duracion_ms
                    self.slider_tiempo.set(max(0.0, min(1.0, pos)))
                    str_actual = self._formatear_ms(tiempo_actual_ms)
                    str_total = self._formatear_ms(duracion_ms)
                    self.lbl_tiempo.configure(text=f"{str_actual} / {str_total}")
        except Exception:
            pass

        # Programa la siguiente llamada dentro de 100 milisegundos
        self._loop_progreso_id = self.after(100, self._actualizar_progreso)

    # Se activa al hacer clic en el slider para pausar la sincronización automática
    def _on_slider_presionado(self, _event=None) -> None:
        self._arrastrando_slider = True

    # Se activa al soltar el ratón para saltar al segundo elegido
    def _on_slider_soltado(self, _event=None) -> None:
        self._arrastrando_slider = False
        nueva_pos = self.slider_tiempo.get()
        self.player.set_position(nueva_pos)

    # Actualiza el texto de tiempo mientras el usuario arrastra la barra
    def _on_slider_arrastre(self, valor: float) -> None:
        if self._duracion_ms > 0:
            tiempo_estimado_ms = int(valor * self._duracion_ms)
            str_actual = self._formatear_ms(tiempo_estimado_ms)
            str_total = self._formatear_ms(self._duracion_ms)
            self.lbl_tiempo.configure(text=f"{str_actual} / {str_total}")

    # Ajusta el volumen del reproductor de 0 a 100
    def _on_volumen_cambio(self, valor: float) -> None:
        vol = int(valor)
        self.player.audio_set_volume(vol)

    # Convierte milisegundos a formato MM:SS
    @staticmethod
    def _formatear_ms(milisegundos: int) -> str:
        segundos = max(0, milisegundos // 1000)
        m, s = divmod(segundos, 60)
        return f"{m:02d}:{s:02d}"

    # Detiene VLC y libera la memoria antes de cerrar la ventana
    def liberar_recursos(self) -> None:
        self._detener_bucle_progreso()
        if self.player:
            self.player.stop()
            self.player.release()


if __name__ == "__main__":
    app = ctk.CTk()
    app.title("Test Reproductor VLC")
    app.geometry("800x500")

    rep = ReproductorVideo(app)
    rep.pack(fill="both", expand=True, padx=10, pady=10)

    # Buscamos un clip local para la prueba si existe
    clips_disponibles = (
        list(Path("downloads/candidatos").glob("*.mp4"))
        or list(Path("modulos/downloads/candidatos").glob("*.mp4"))
    )

    if clips_disponibles:
        print(f"Cargando clip de prueba: {clips_disponibles[0]}")
        app.after(500, lambda: rep.cargar_video(clips_disponibles[0]))
    else:
        print("No se encontraron clips mp4 para prueba.")

    app.protocol("WM_DELETE_WINDOW", lambda: (rep.liberar_recursos(), app.destroy()))
    app.mainloop()
