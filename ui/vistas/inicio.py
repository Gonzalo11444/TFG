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
import customtkinter as ctk


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

    archivos_fijos = ["audio.m4a", "chat.json", "clips_aprobados.json"]

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
    # Ventana modal de confirmación estética para purgar archivos de sesión
    def __init__(self, master, on_confirmar: Callable[[], None]):
        super().__init__(master)
        self.on_confirmar = on_confirmar

        self.title("Confirmar Purga de Sesión")
        self.geometry("450x250")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self.transient(master)
        self.grab_set()

        lbl_icono = ctk.CTkLabel(self, text="⚠️", font=("Arial", 36))
        lbl_icono.pack(pady=(18, 4))

        lbl_titulo = ctk.CTkLabel(
            self,
            text="¿Purgar clips de la sesión actual?",
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
            text="🗑️ Sí, purgar sesión",
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

        # Configuración de rejilla principal centrada
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Contenedor central flotante
        self._construir_contenido()

    # Construye los elementos visuales de la vista de inicio
    def _construir_contenido(self) -> None:
        # Tarjeta central con sombra simulada
        self.card_central = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color="#1e1e1e",
            border_width=1,
            border_color="#333333",
            width=760
        )
        self.card_central.grid(row=1, column=0, padx=30, pady=20, sticky="n")

        # 1. Cabecera y logotipo del proyecto
        lbl_icono = ctk.CTkLabel(
            self.card_central,
            text="🎬",
            font=("Arial", 44)
        )
        lbl_icono.pack(pady=(24, 4))

        lbl_titulo = ctk.CTkLabel(
            self.card_central,
            text="PrendeClips",
            font=("Arial", 26, "bold"),
            text_color="#ffffff"
        )
        lbl_titulo.pack(pady=(0, 4))

        lbl_subtitulo = ctk.CTkLabel(
            self.card_central,
            text="Extracción Inteligente de Momentos Destacados de Twitch con IA",
            font=("Arial", 13),
            text_color="#aaaaaa"
        )
        lbl_subtitulo.pack(pady=(0, 16))

        # 2. Resumen visual del Pipeline (Fases 1 a 5)
        self._construir_pasos_pipeline()

        # 3. Formulario de entrada: URL de Twitch
        frame_input = ctk.CTkFrame(self.card_central, fg_color="transparent")
        frame_input.pack(fill="x", padx=40, pady=(10, 14))

        lbl_input = ctk.CTkLabel(
            frame_input,
            text="URL o ID del directo de Twitch (VOD):",
            font=("Arial", 12, "bold"),
            text_color="#cccccc",
            anchor="w"
        )
        lbl_input.pack(fill="x", pady=(0, 6))

        self.entry_url = ctk.CTkEntry(
            frame_input,
            placeholder_text="https://www.twitch.tv/videos/2873857636",
            font=("Arial", 13),
            height=44,
            corner_radius=8,
            border_color="#444444"
        )
        self.entry_url.pack(fill="x", pady=(0, 14))

        # Permite pulsar 'Enter' directamente en la caja de texto para lanzar
        self.entry_url.bind("<Return>", lambda e: self._al_pulsar_procesar())

        # 4. Botón de acción principal
        self.btn_procesar = ctk.CTkButton(
            frame_input,
            text="🚀  Procesar y Extraer Clips",
            font=("Arial", 14, "bold"),
            height=46,
            corner_radius=8,
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=self._al_pulsar_procesar
        )
        self.btn_procesar.pack(fill="x", pady=(0, 4))

        # 5. Barra de progreso y texto de fase actual
        self.frame_feedback = ctk.CTkFrame(self.card_central, fg_color="#181818", corner_radius=8)
        self.frame_feedback.pack(fill="x", padx=40, pady=(6, 16))

        self.lbl_estado = ctk.CTkLabel(
            self.frame_feedback,
            text="Listo para procesar. Pega una URL de Twitch y pulsa el botón.",
            font=("Arial", 12),
            text_color="#9e9e9e"
        )
        self.lbl_estado.pack(pady=(12, 6), padx=15)

        self.barra_progreso = ctk.CTkProgressBar(
            self.frame_feedback,
            height=8,
            corner_radius=4,
            fg_color="#2b2b2b",
            progress_color="#1f6aa5"
        )
        self.barra_progreso.pack(fill="x", padx=20, pady=(0, 14))
        self.barra_progreso.set(0.0)

        # 6. Botones secundarios de utilidad (3 columnas equilibradas)
        frame_utilidades = ctk.CTkFrame(self.card_central, fg_color="transparent")
        frame_utilidades.pack(fill="x", padx=40, pady=(0, 24))
        frame_utilidades.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_abrir_carpeta = ctk.CTkButton(
            frame_utilidades,
            text="📁 Abrir Carpeta",
            font=("Arial", 11),
            height=32,
            fg_color="#2c2c2c",
            hover_color="#3a3a3a",
            command=self._abrir_carpeta
        )
        self.btn_abrir_carpeta.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.btn_ver_existentes = ctk.CTkButton(
            frame_utilidades,
            text="👁 Ver clips guardados",
            font=("Arial", 11),
            height=32,
            fg_color="#2c2c2c",
            hover_color="#3a3a3a",
            command=self._al_cargar_existentes
        )
        self.btn_ver_existentes.grid(row=0, column=1, padx=4, sticky="ew")

        self.btn_purgar_clips = ctk.CTkButton(
            frame_utilidades,
            text="🗑️ Purgar clips de la sesión",
            font=("Arial", 11),
            height=32,
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

    # Muestra el diálogo modal para confirmar la purga
    def _al_pulsar_purgar(self) -> None:
        if self._procesando:
            return

        DialogoConfirmarPurga(self, on_confirmar=self._ejecutar_purga)

    # Ejecuta el borrado de archivos temporales
    def _ejecutar_purga(self) -> None:
        eliminados = purgar_archivos_sesion(self.carpeta_salida)
        self.lbl_estado.configure(
            text=f"🗑️ Se han eliminado {eliminados} archivos temporales de la sesión (conservando 'clips_verticales/').",
            text_color="#81c784"
        )
        if self.on_purgar_completado is not None:
            self.on_purgar_completado()

    # Abre la carpeta de descargas en el explorador de Windows
    def _abrir_carpeta(self) -> None:
        abrir_carpeta_sistema(self.carpeta_salida)

    # Devuelve el texto actualmente escrito en el campo de URL
    def obtener_url(self) -> str:
        return self.entry_url.get().strip()

    # Habilita o deshabilita los controles durante la ejecución pesada
    def establecer_modo_procesando(self, activo: bool) -> None:
        self._procesando = activo
        if activo:
            self.entry_url.configure(state="disabled")
            self.btn_procesar.configure(state="disabled", text="⏳ Procesando en segundo plano...")
            self.btn_ver_existentes.configure(state="disabled")
            self.btn_purgar_clips.configure(state="disabled")
            self.barra_progreso.configure(mode="indeterminate")
            self.barra_progreso.start()
            self.lbl_estado.configure(
                text="Iniciando pipeline de extracción... Por favor, espera.",
                text_color="#1f6aa5"
            )
        else:
            self.entry_url.configure(state="normal")
            self.btn_procesar.configure(state="normal", text="🚀  Procesar y Extraer Clips")
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
