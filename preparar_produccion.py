"""Prepara los directorios de almacenamiento de FenologIA."""

from pathlib import Path


BASE = Path(__file__).resolve().parent

DIRECTORIOS = [
    "data",
    "data/imagenes",
    "data/analisis_dispositivo",
    "data/analisis_dispositivo/hsv",
    "data/analisis_dispositivo/yolo",
    "data/analisis_dispositivo/roboflow",
    "modelos",
    "weights/clip"
]


def preparar_directorios():

    for nombre in DIRECTORIOS:

        ruta = BASE / nombre

        if ruta.resolve() != ruta or ruta.is_symlink():
            raise RuntimeError(
                f"Ruta no autorizada: {nombre}"
            )

        ruta.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700
        )

        print("OK:", nombre)

    print("OK: directorios preparados")
    print("OK: ninguna cuenta ni dato generado")


if __name__ == "__main__":
    preparar_directorios()
