from pathlib import Path
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image
from ultralytics import SAM, YOLOWorld

BASE = Path(__file__).resolve().parent

COLORES = {
    "verde": "#659D39",
    "verde_amarillento": "#B5C653",
    "rosado_rojizo": "#C96B83",
    "morado_claro": "#B18ACD",
    "morado": "#79449B",
    "morado_oscuro": "#392044",
    "marron": "#90613D",
    "otras_areas": "#A5A5A5",
}


@lru_cache(maxsize=1)
def cargar_segmentador():
    return SAM(str(BASE / "sam2_t.pt"))


@lru_cache(maxsize=1)
def cargar_detector():
    modelo = YOLOWorld(
        str(BASE / "yolov8s-worldv2.pt")
    )
    modelo.set_classes(["grapes"])
    return modelo


def detectar_candidatos(ruta):
    resultado = cargar_detector().predict(
        source=str(ruta),
        conf=0.05,
        iou=0.35,
        max_det=15,
        imgsz=640,
        device="cpu",
        verbose=False
    )[0]

    return [
        {
            "caja": caja,
            "confianza": float(confianza)
        }
        for caja, confianza in zip(
            resultado.boxes.xyxy.cpu().tolist(),
            resultado.boxes.conf.cpu().tolist()
        )
    ]


def segmentar_racimos(ruta, cajas):
    if not cajas:
        return []

    imagen = Image.open(ruta)
    ancho, alto = imagen.size

    cajas_validas = []

    for caja in cajas:
        x1, y1, x2, y2 = map(float, caja)

        x1 = max(0, min(x1, ancho))
        x2 = max(0, min(x2, ancho))
        y1 = max(0, min(y1, alto))
        y2 = max(0, min(y2, alto))

        if x2 > x1 and y2 > y1:
            cajas_validas.append([x1, y1, x2, y2])

    if not cajas_validas:
        return []

    resultado = cargar_segmentador().predict(
        source=str(ruta),
        bboxes=cajas_validas,
        device="cpu",
        verbose=False
    )[0]

    if resultado.masks is None:
        return []

    mascaras = []

    for mascara in resultado.masks.data.cpu().numpy():
        mascara = cv2.resize(
            mascara.astype(np.float32),
            (ancho, alto),
            interpolation=cv2.INTER_NEAREST
        )

        mascara = mascara > 0.5

        if mascara.any():
            mascaras.append(mascara)

    return mascaras


def clasificar_colores(imagen_rgb, mascara):

    hsv = cv2.cvtColor(
        imagen_rgb,
        cv2.COLOR_RGB2HSV
    )

    h, s, v = cv2.split(hsv)

    condiciones = {
        "verde": (
            (h >= 36) & (h <= 95)
            & (s >= 40) & (v >= 40)
        ),
        "verde_amarillento": (
            (h >= 20) & (h < 36)
            & (s >= 35) & (v >= 90)
        ),
        "rosado_rojizo": (
            ((h <= 10) | (h >= 165))
            & (s >= 35) & (v >= 85)
        ),
        "morado_claro": (
            (h >= 96) & (h < 165)
            & (s >= 25) & (v >= 160)
        ),
        "morado": (
            (h >= 96) & (h < 165)
            & (s >= 30)
            & (v >= 75) & (v < 160)
        ),
        "morado_oscuro": (
            (h >= 96) & (h < 165)
            & (s >= 30)
            & (v >= 25) & (v < 75)
        ),
        "marron": (
            (h >= 5) & (h < 30)
            & (s >= 40)
            & (v >= 35) & (v < 140)
        )
    }

    etiquetas = np.full(
        mascara.shape, -1, dtype=np.int8
    )

    pendiente = mascara.copy()

    for i, condicion in enumerate(
        condiciones.values()
    ):
        seleccion = pendiente & condicion
        etiquetas[seleccion] = i
        pendiente[seleccion] = False

    etiquetas[pendiente] = 7

    return etiquetas


def calcular_porcentajes(etiquetas, mascara):

    total = int(np.count_nonzero(mascara))

    if total == 0:
        return {
            nombre: None for nombre in COLORES
        }

    return {
        nombre: round(
            100 * np.count_nonzero(
                (etiquetas == i) & mascara
            ) / total, 2
        )
        for i, nombre in enumerate(COLORES)
    }


def analizar_colores(ruta, mascaras):

    imagen = np.array(
        Image.open(ruta).convert("RGB")
    )

    union = np.zeros(
        imagen.shape[:2], dtype=bool
    )

    mascaras_validas = []

    for mascara in mascaras:
        mascara = np.asarray(mascara, dtype=bool)

        if mascara.shape != union.shape:
            raise ValueError(
                "Dimensiones de mascara incorrectas"
            )

        if mascara.any():
            mascaras_validas.append(mascara)
            union |= mascara

    etiquetas = clasificar_colores(imagen, union)

    porcentajes = calcular_porcentajes(
        etiquetas, union
    )

    morados = [
        "morado_claro",
        "morado",
        "morado_oscuro"
    ]

    morado_total = (
        round(sum(porcentajes[k] for k in morados), 2)
        if union.any() else None
    )

    detalle = []

    for i, mascara in enumerate(mascaras_validas, 1):

        detalle.append({
            "racimo": i,
            "pixeles": int(mascara.sum()),
            "colores": calcular_porcentajes(
                etiquetas, mascara
            )
        })

    visual = imagen.copy()

    for i, hexadecimal in enumerate(COLORES.values()):

        rgb = np.array([
            int(hexadecimal[j:j+2], 16)
            for j in (1, 3, 5)
        ])

        seleccion = etiquetas == i

        visual[seleccion] = (
            imagen[seleccion] * 0.55
            + rgb * 0.45
        ).astype(np.uint8)

    for i, mascara in enumerate(mascaras_validas, 1):

        contornos, _ = cv2.findContours(
            mascara.astype(np.uint8),
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        cv2.drawContours(
            visual, contornos, -1,
            (255, 255, 255), 2
        )

        ys, xs = np.where(mascara)

        cv2.putText(
            visual,
            f"R{i}",
            (int(xs.mean()), int(ys.mean())),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7, (255, 255, 255), 2
        )

    return {
        "cantidad_racimos": len(mascaras_validas),
        "colores": porcentajes,
        "porcentaje_morado_total": morado_total,
        "superficie_segmentada": round(
            100 * union.mean(), 2
        ),
        "detalle_racimos": detalle,
        "imagen_resultado": Image.fromarray(visual),
        "advertencia": (
            "Clasificacion cromatica experimental. "
            "La iluminacion y las sombras pueden "
            "afectar los resultados. El color no "
            "determina por si solo la madurez."
        )
    }
