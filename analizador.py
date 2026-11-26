"""Analizador experimental de imágenes de viñedo.

Requisitos:
    pip install pillow numpy

Uso desde Python:
    from analizador import analizar_imagen
    resultado = analizar_imagen("ruta/a/foto.jpg")
    print(resultado)

Uso desde la terminal:
    python analizador.py "ruta/a/foto.jpg"

Los porcentajes corresponden a píxeles de la imagen completa. Esta primera
versión NO identifica racimos ni determina por sí sola la fenología.
"""

from pathlib import Path
import argparse
import json

import numpy as np
from PIL import Image


import uuid

BASE_EXPERIMENTAL = Path(__file__).resolve().parent

CARPETA_FOTOS_EXPERIMENTAL = (
    BASE_EXPERIMENTAL / "data"
    / "imagenes"
)

CARPETA_IA_EXPERIMENTAL = (
    BASE_EXPERIMENTAL / "data"
    / "analisis_dispositivo"
)


def validar_imagen_experimental(ruta_imagen):
    """Valida fotografías mediante el módulo centralizado."""

    from lectura_fotografica import (
        validar_ruta_fotografia
    )

    return validar_ruta_fotografia(ruta_imagen)


def preparar_carpeta_ia_experimental(metodo):

    if metodo not in ("hsv", "yolo", "roboflow"):
        raise ValueError("Método no autorizado.")

    raiz = CARPETA_IA_EXPERIMENTAL

    if raiz.resolve() != raiz or not raiz.is_dir():
        raise ValueError(
            "Carpeta de análisis no autorizada."
        )

    carpeta = raiz / metodo

    if carpeta.resolve() != carpeta:
        raise ValueError(
            "Ruta de salida no autorizada."
        )

    carpeta.mkdir(parents=True, exist_ok=True)

    return carpeta



def _mascaras_color(imagen_hsv: np.ndarray):
    """Crea máscaras exploratorias de verde y zonas oscuras usando HSV."""
    h = imagen_hsv[:, :, 0].astype(np.int16)  # 0..255
    s = imagen_hsv[:, :, 1].astype(np.int16)  # 0..255
    v = imagen_hsv[:, :, 2].astype(np.int16)  # 0..255

    # Umbrales iniciales orientativos; deberán calibrarse con fotos reales.
    mascara_verde = (
        (h >= 45) & (h <= 125) & (s >= 45) & (v >= 35)
    )
    # Las uvas de la imagen de referencia son muy oscuras y poco saturadas.
    # Esta máscara detecta zonas oscuras, NO identifica uvas de forma fiable.
    mascara_oscura = (v >= 20) & (v <= 105) & (s <= 145)
    mascara_oscura &= ~mascara_verde

    return mascara_verde, mascara_oscura


def analizar_imagen(ruta_imagen, guardar_diagnostico=True):
    """Analiza colores de una imagen y opcionalmente guarda una máscara visual.

    Devuelve un diccionario con dimensiones, porcentajes y ruta del diagnóstico.
    Los porcentajes se calculan sobre el total de píxeles de la imagen.
    """
    ruta = validar_imagen_experimental(ruta_imagen)
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encontró la imagen: {ruta}")

    with Image.open(ruta) as original:
        rgb = original.convert("RGB")

    hsv = np.asarray(rgb.convert("HSV"), dtype=np.uint8)
    mascara_verde, mascara_oscura = _mascaras_color(hsv)

    total_pixeles = int(hsv.shape[0] * hsv.shape[1])
    pixeles_verdes = int(np.count_nonzero(mascara_verde))
    pixeles_oscuros = int(np.count_nonzero(mascara_oscura))
    pixeles_clasificados = pixeles_verdes + pixeles_oscuros
    pixeles_otros = total_pixeles - pixeles_clasificados

    # Imagen de diagnóstico: verde detectado en verde, morado detectado en morado
    # y el resto en escala de grises para poder revisar visualmente el resultado.
    diagnostico_path = None
    if guardar_diagnostico:
        rgb_array = np.asarray(rgb, dtype=np.uint8)
        gris = np.asarray(rgb.convert("L"), dtype=np.uint8)
        diagnostico = np.stack([gris, gris, gris], axis=-1)
        diagnostico[mascara_verde] = [0, 220, 70]
        diagnostico[mascara_oscura] = [170, 50, 220]

        carpeta = preparar_carpeta_ia_experimental("hsv")
        diagnostico_path = (
            carpeta
            / f"{ruta.stem}_{uuid.uuid4().hex}_diagnostico.png"
        )
        with diagnostico_path.open("xb") as salida:
            Image.fromarray(
                diagnostico, mode="RGB"
            ).save(salida, format="PNG")

    resultado = {
        "archivo": ruta.name,
        "ancho_px": int(hsv.shape[1]),
        "alto_px": int(hsv.shape[0]),
        "total_pixeles": total_pixeles,
        "porcentaje_verde": round(pixeles_verdes / total_pixeles * 100, 2),
        "porcentaje_zonas_oscuras": round(pixeles_oscuros / total_pixeles * 100, 2),
        "porcentaje_otros": round(pixeles_otros / total_pixeles * 100, 2),
        "porcentaje_clasificado": round(pixeles_clasificados / total_pixeles * 100, 2),
        "metodo": "segmentacion HSV experimental sobre imagen completa",
        "diagnostico": str(diagnostico_path) if diagnostico_path else None,
        "advertencia": (
            "Las zonas oscuras no equivalen a uvas detectadas: también pueden "
            "incluir sombras y otros objetos. Los porcentajes son sobre toda la foto."
        ),
    }
    return resultado


def main():
    parser = argparse.ArgumentParser(
        description="Analiza de forma experimental los colores de una foto de viñedo."
    )
    parser.add_argument("imagen", help="Ruta de la fotografía que se analizará")
    args = parser.parse_args()

    try:
        resultado = analizar_imagen(args.imagen)
        print(json.dumps(resultado, ensure_ascii=False, indent=4))
        if resultado["diagnostico"]:
            print(f"\nImagen de diagnóstico guardada en: {resultado['diagnostico']}")
    except Exception as error:
        raise SystemExit(f"No se pudo analizar la imagen: {error}")


if __name__ == "__main__":
    main()

def analizar_racimos_yolo(ruta_imagen, confianza=0.25):
    """Detecta y segmenta racimos mediante nuestro modelo YOLO."""

    ruta = validar_imagen_experimental(ruta_imagen)

    from ultralytics import YOLO

    if not ruta.is_file():
        raise FileNotFoundError(f"No se encontró la imagen: {ruta}")

    ruta_modelo = (
        BASE_EXPERIMENTAL
        / "runs/segment/modelos/racimos_experimental/weights/best.pt"
    )

    if not ruta_modelo.is_file():
        raise FileNotFoundError("No se encontró el modelo YOLO.")

    modelo = YOLO(str(ruta_modelo))

    resultados = modelo.predict(
        source=str(ruta),
        conf=confianza,
        save=True,
        show=False,
        project=str(
            preparar_carpeta_ia_experimental("yolo")
        ),
        name=f"analisis_{uuid.uuid4().hex}",
        exist_ok=False
    )

    resultado = resultados[0]

    cantidad = len(resultado.boxes)

    confianzas = (
        resultado.boxes.conf.tolist()
        if cantidad > 0
        else []
    )

    imagen_resultado = (
        Path(resultado.save_dir) / ruta.name
    )

    return {
        "archivo": ruta.name,
        "cantidad_racimos": cantidad,
        "confianzas": [
            round(float(c) * 100, 2)
            for c in confianzas
        ],
        "imagen_resultado": str(imagen_resultado),
        "modelo": "YOLOv8n-seg experimental"
    }


def analizar_uvas_roboflow(ruta_imagen, confianza=0.20):
    """Detecta objetos de clase grapes mediante Roboflow.

    Las detecciones no equivalen necesariamente a racimos completos.
    Requiere conexión a internet y credenciales en secrets.toml.
    """
    import tomllib
    from PIL import ImageDraw
    from inference_sdk import (
        InferenceHTTPClient,
        InferenceConfiguration,
    )

    ruta = validar_imagen_experimental(ruta_imagen)

    if not ruta.is_file():
        raise FileNotFoundError(
            f"No se encontró la fotografía: {ruta}"
        )

    if not 0 < confianza <= 1:
        raise ValueError(
            "La confianza debe estar entre 0 y 1."
        )

    archivo_secrets = (
        Path(__file__).resolve().parent
        / ".streamlit"
        / "secrets.toml"
    )

    if not archivo_secrets.is_file():
        raise FileNotFoundError(
            "No se encontró la configuración de Roboflow."
        )

    with archivo_secrets.open("rb") as archivo:
        configuracion = tomllib.load(archivo)

    api_key = configuracion.get("ROBOFLOW_API_KEY")
    modelo_id = configuracion.get(
        "ROBOFLOW_MODEL_ID",
        "grapes-iav9u/1"
    )

    if not api_key:
        raise ValueError(
            "Falta configurar ROBOFLOW_API_KEY."
        )

    cliente = InferenceHTTPClient(
        api_url="https://serverless.roboflow.com",
        api_key=api_key
    )

    cliente.configure(
        InferenceConfiguration(
            confidence_threshold=confianza,
            api_key_transport="header"
        )
    )

    respuesta = cliente.infer(
        str(ruta),
        model_id=modelo_id
    )

    predicciones = respuesta.get("predictions", [])

    with Image.open(ruta) as original:
        imagen = original.convert("RGB")

    dibujo = ImageDraw.Draw(imagen)

    detecciones = []

    for prediccion in predicciones:
        x = float(prediccion["x"])
        y = float(prediccion["y"])
        ancho = float(prediccion["width"])
        alto = float(prediccion["height"])
        puntuacion = float(prediccion["confidence"])
        clase = str(prediccion.get("class", "grapes"))

        caja = (
            x - ancho / 2,
            y - alto / 2,
            x + ancho / 2,
            y + alto / 2
        )

        dibujo.rectangle(
            caja,
            outline="red",
            width=5
        )

        dibujo.text(
            (max(0, caja[0]), max(0, caja[1] - 18)),
            f"{clase} {puntuacion:.1%}",
            fill="red"
        )

        detecciones.append({
            "clase": clase,
            "confianza": round(puntuacion * 100, 2),
            "x": x,
            "y": y,
            "ancho": ancho,
            "alto": alto
        })

    carpeta = preparar_carpeta_ia_experimental(
        "roboflow"
    )

    carpeta.mkdir(
        parents=True,
        exist_ok=True
    )

    import uuid

    imagen_resultado = (
        carpeta / f"{ruta.stem}_{uuid.uuid4().hex[:12]}_roboflow.png"
    )

    with imagen_resultado.open("xb") as salida:
        imagen.save(salida, format="PNG")

    confianzas = [
        deteccion["confianza"]
        for deteccion in detecciones
    ]

    return {
        "archivo": ruta.name,
        "modelo": "Roboflow",
        "version_modelo": modelo_id,
        "cantidad_detecciones": len(detecciones),
        "confianzas": confianzas,
        "detecciones": detecciones,
        "imagen_resultado": str(imagen_resultado),
        "umbral_confianza": confianza,
        "advertencia": (
            "Las detecciones corresponden a objetos identificados "
            "como grapes. No equivalen necesariamente a racimos "
            "completos ni permiten determinar por sí solas "
            "la etapa fenológica."
        )
    }
