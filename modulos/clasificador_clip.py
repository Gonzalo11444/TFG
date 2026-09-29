""" clasificador_clip.py

Módulo de clasificación visual mediante Inteligencia Artificial (Fase 4 del TFG).
Utiliza el modelo zero-shot OpenAI CLIP (vía Hugging Face Transformers y PyTorch)
y OpenCV para analizar fotogramas de los vídeos y etiquetarlos automáticamente."""

from pathlib import Path
from dataclasses import replace
from typing import Callable
import os
import json

#Se desactivan avisos internos de TensorFlow para que no salgan en interfaz
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

try:
    import cv2
    from PIL import Image
    import torch
    from transformers import CLIPProcessor, CLIPModel
    IA_DISPONIBLE = True
except ImportError:
    IA_DISPONIBLE = False

# Se importa la estructura de fase 3.
try:
    from modulos.seleccion_temporal import CandidatoClip
except ImportError:
    from seleccion_temporal import CandidatoClip


# Etiquetas en inglés para CLIP
# Necesario que sepa que estamos en un directo de twitch.
ETIQUETAS_CLIP = [
    "video game gameplay footage, in-game dialogue or playthrough",
    "streamer talking on webcam facecam",
    "streamer laughing or screaming emotional reaction",
    "video game options settings menu or inventory screen",
    "stream ending screen, farewell outro scene or illustrated room with twitch chat"
]

# 2. Diccionario para traducir cada etiqueta técnica de CLIP al nombre en español de la interfaz
MAPA_CATEGORIAS = {
    "video game gameplay footage, in-game dialogue or playthrough": "Gameplay",
    "streamer talking on webcam facecam": "Charla / Cámara",
    "streamer laughing or screaming emotional reaction": "Reacción / Risa",
    "video game options settings menu or inventory screen": "Menú / Carga",
    "stream ending screen, farewell outro scene or illustrated room with twitch chat": "Pantalla Final / Despedida"
}


COLORES_CATEGORIA = {
    "Gameplay": "#2e7d32",                     # Verde
    "Charla / Cámara": "#1565c0",              # Azul
    "Reacción / Risa": "#f57c00",              # Naranja
    "Menú / Carga": "#546e7a",                 # Gris azulado
    "Pantalla Final / Despedida": "#c62828",   # Rojo apagado
    "Sin clasificar": "#424242"                # Gris oscuro neutro
}


LISTA_CATEGORIAS_DISPONIBLES = [
    "Gameplay",
    "Charla / Cámara",
    "Reacción / Risa",
    "Menú / Carga",
    "Pantalla Final / Despedida",
    "Sin clasificar"
]


# Constructor: detecta si el ordenador tiene tarjeta gráfica Nvidia (CUDA) o usa CPU
class ClasificadorVisual:
    def __init__(self, modelo_id: str = "openai/clip-vit-base-patch32"):
        self.modelo_id = modelo_id
        self.dispositivo = "cpu"
        self.modelo = None
        self.procesador = None

        if IA_DISPONIBLE:
            if torch.cuda.is_available():
                self.dispositivo = "cuda"
            else:
                self.dispositivo = "cpu"

    # Carga el modelo CLIP en memoria solo cuando realmente se necesita
    def cargar_modelo(self) -> bool:
        if not IA_DISPONIBLE:
            print("Librerías de IA (torch / transformers / cv2) no instaladas.")
            return False

        # Si el modelo ya está cargado previamente en memoria, no hacemos nada
        if self.modelo is not None and self.procesador is not None:
            return True

        try:
            print(f"Cargando modelo CLIP ({self.modelo_id}) en {self.dispositivo.upper()}...")

            # Cargamos la red neuronal usando pesos seguros (.safetensors)
            self.modelo = CLIPModel.from_pretrained(
                self.modelo_id,
                use_safetensors=True
            ).to(self.dispositivo)

            # Ponemos el modelo en modo evaluación (desactiva capas de entrenamiento)
            self.modelo.eval()

            # Cargamos el procesador de imágenes y texto asociado a este modelo
            self.procesador = CLIPProcessor.from_pretrained(self.modelo_id, use_fast=False)
            print("Modelo CLIP listo")
            return True

        except Exception as error:
            print(f"No se pudo cargar el modelo CLIP: {error}")
            self.modelo = None
            self.procesador = None
            return False

    # Extrae fotogramas representativos a lo largo del clip usando OpenCV
    def extraer_fotogramas(self, ruta_video: Path | str, cantidad: int = 4) -> list:
        ruta = Path(ruta_video)
        if not ruta.exists() or not IA_DISPONIBLE:
            return []

        cap = cv2.VideoCapture(str(ruta)) #Se abre el archivo de vídeo con OpenCV
        if not cap.isOpened():
            return []

        # Contamos cuántos fotogramas totales componen el fragmento
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            cap.release()
            return []

        # Calculamos posiciones de muestreo equidistantes (por ejemplo: 20%, 40%, 60%, 80%)
        # Esto asegura ver cómo evoluciona el clip desde el principio hasta el final
        paso = 1.0 / (cantidad + 1)
        ratios = []
        for i in range(1, cantidad + 1):
            ratios.append(i * paso)

        fotogramas = []
        for r in ratios:
            # Saltamos directamente al fotograma correspondiente en el archivo de vídeo
            indice_frame = int(total_frames * r)
            cap.set(cv2.CAP_PROP_POS_FRAMES, indice_frame)

            leido, frame_bgr = cap.read()
            if leido and frame_bgr is not None:
                # OpenCV lee las imágenes en orden BGR (Azul, Verde, Rojo).
                # PyTorch y Pillow necesitan RGB (Rojo, Verde, Azul), así que lo convertimos:
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                imagen_pil = Image.fromarray(frame_rgb)
                fotogramas.append(imagen_pil)

        # Cerramos siempre el archivo de vídeo para liberar recursos del sistema
        cap.release()
        return fotogramas

    # Clasifica un vídeo individual calculando la similitud visual con las etiquetas
    def clasificar_video(self, ruta_video: Path | str) -> tuple[str, float, dict[str, float]]:
        if not self.cargar_modelo():
            return "Sin clasificar", 0.0, {}

        # Obtenemos los fotogramas clave del vídeo
        fotogramas = self.extraer_fotogramas(ruta_video, cantidad=4)
        if not fotogramas:
            return "Sin clasificar", 0.0, {}

        try:
            # Convertimos las imágenes y las etiquetas de texto a tensores numéricos para PyTorch
            entradas = self.procesador(
                text=ETIQUETAS_CLIP,
                images=fotogramas,
                return_tensors="pt",
                padding=True
            )

            # Enviamos los datos al dispositivo correspondiente (CPU o tarjeta gráfica)
            entradas_disp = {}
            for clave, valor in entradas.items():
                entradas_disp[clave] = valor.to(self.dispositivo)

            # torch.no_grad() desactiva el cálculo de gradientes para ahorrar memoria y acelerar la inferencia
            with torch.no_grad():
                salidas = self.modelo(**entradas_disp)

                # logits_per_image mide la similitud matemática entre cada fotograma y cada texto
                logits = salidas.logits_per_image

                # softmax convierte las puntuaciones en probabilidades porcentuales que suman 1.0 (100%)
                probs = logits.softmax(dim=1)

                # Promediamos las probabilidades de los 4 fotogramas para tener un veredicto global del clip
                prob_promedio = probs.mean(dim=0).cpu()

            # Guardamos el desglose de probabilidades con nombres legibles en español
            desglose = {}
            for i in range(len(ETIQUETAS_CLIP)):
                etiqueta_original = ETIQUETAS_CLIP[i]
                etiqueta_es = MAPA_CATEGORIAS[etiqueta_original]
                probabilidad_float = float(prob_promedio[i].item())
                desglose[etiqueta_es] = round(probabilidad_float, 4)

            # argmax encuentra cuál de las etiquetas obtuvo la puntuación más alta
            indice_ganador = int(torch.argmax(prob_promedio).item())
            etiqueta_ganadora_orig = ETIQUETAS_CLIP[indice_ganador]
            categoria_final = MAPA_CATEGORIAS[etiqueta_ganadora_orig]
            confianza_final = float(prob_promedio[indice_ganador].item())

            return categoria_final, confianza_final, desglose

        except Exception as error:
            print(f"Fallo durante la inferencia CLIP: {error}")
            return "Sin clasificar", 0.0, {}

    # Procesa una lista completa de clips candidatos informando del avance a la interfaz
    def clasificar_candidatos(
        self,
        clips: list[CandidatoClip],
        callback_progreso: Callable[[int, int, CandidatoClip], None] | None = None
    ) -> list[CandidatoClip]:
        if not clips:
            return []

        self.cargar_modelo()
        clips_actualizados = []
        total = len(clips)

        for i in range(total):
            c = clips[i]

            # Si el clip tiene un archivo .mp4 real en disco, lo analizamos con CLIP
            if c.ruta_video and c.ruta_video.exists():
                cat, conf, _ = self.clasificar_video(c.ruta_video)
            else:
                cat = "Sin clasificar"
                conf = 0.0

            # Como CandidatoClip es inmutable (frozen=True), usamos replace() para generar una copia limpia con la nueva categoría y su confianza
            nuevo_clip = replace(c, categoria=cat, confianza_ia=conf)
            clips_actualizados.append(nuevo_clip)

            # Si nos han pasado una función callback (la barra de progreso de la UI), la llamamos
            if callback_progreso is not None:
                callback_progreso(i + 1, total, nuevo_clip)

        return clips_actualizados


# Vuelca la lista de clips clasificados en el archivo de persistencia clips_info.json
def guardar_clips_info_json(
    clips: list[CandidatoClip],
    ruta_destino: Path | str,
    metadatos_extraccion: dict | None = None
) -> Path:
    destino = Path(ruta_destino).resolve()
    destino.parent.mkdir(parents=True, exist_ok=True)

    meta = metadatos_extraccion or {
        "peso_audio": 0.5,
        "peso_chat": 0.5,
        "perfil_nombre": "Equilibrado (50% Audio / 50% Chat)"
    }

    datos = []
    for c in clips:
        nombre = c.ruta_video.name if c.ruta_video else f"clip_{c.segundo_inicio}s_{c.segundo_fin}s.mp4"
        datos.append({
            "nombre_archivo": nombre,
            "ruta": str(c.ruta_video.resolve()) if c.ruta_video else None,
            "segundo_inicio": c.segundo_inicio,
            "segundo_fin": c.segundo_fin,
            "duracion": c.segundo_fin - c.segundo_inicio,
            "puntuacion": c.puntuacion,
            "categoria": c.categoria,
            "confianza": round(c.confianza_ia, 4),
            "estado": "Aprobado" if c.aprobado else "Pendiente",
            "peso_audio": meta.get("peso_audio", 0.5),
            "peso_chat": meta.get("peso_chat", 0.5),
            "perfil_nombre": meta.get("perfil_nombre", "")
        })

    contenido = {
        "metadatos_extraccion": meta,
        "clips": datos
    }

    with open(destino, "w", encoding="utf-8") as f:
        json.dump(contenido, f, indent=4, ensure_ascii=False)

    print(f"[ClasificadorCLIP] Guardada persistencia en: {destino}")
    return destino


# Carga la información persistida desde clips_info.json si existe
def cargar_clips_info_json(ruta_json: Path | str) -> list[dict]:
    origen = Path(ruta_json).resolve()
    if not origen.exists():
        return []

    try:
        with open(origen, "r", encoding="utf-8") as f:
            datos = json.load(f)
        if isinstance(datos, dict):
            return datos.get("clips", [])
        elif isinstance(datos, list):
            return datos
    except Exception as error:
        print(f"[ClasificadorCLIP] Error al leer {origen.name}: {error}")

    return []


if __name__ == "__main__":
    from pprint import pprint

    print("Probando ClasificadorVisual con clips locales...")
    clasificador = ClasificadorVisual()

    # Buscamos vídeos de muestra en las carpetas habituales
    archivos = list(Path("modulos/downloads/candidatos").glob("*.mp4"))
    if not archivos:
        archivos = list(Path("downloads/candidatos").glob("*.mp4"))

    if archivos:
        clip_test = archivos[0]
        print(f"Analizando vídeo de prueba: {clip_test.name}")
        categoria, confianza, probabilidades = clasificador.clasificar_video(clip_test)
        print(f"Categoría elegida: {categoria} (Confianza: {confianza * 100:.1f}%)")
        print("Desglose completo de probabilidades:")
        pprint(probabilidades)
    else:
        print("No se encontraron vídeos .mp4 en downloads/candidatos para probar.")
