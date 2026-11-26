"""
Almacenamiento fotográfico experimental de FenologIA.

No registra fotografías en SQLite.
No realiza operaciones de escritura al importarse.
"""

from pathlib import Path
import hashlib
import io
import os
import uuid
import warnings

from PIL import Image, ImageFile


BASE_DIR = Path(__file__).resolve().parent

CARPETA_FOTOGRAFIAS = (
    BASE_DIR / "data"
    / "imagenes"
)

MAX_BYTES_FOTOGRAFIA = 50 * 1024 * 1024
MAX_PIXELES_FOTOGRAFIA = 25_000_000
MAX_DIMENSION_FOTOGRAFIA = 12_000

FORMATOS_PERMITIDOS = {
    "JPEG": ".jpg",
    "PNG": ".png"
}

EXTENSIONES_PERMITIDAS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG"
}


def validar_contenido_fotografico(contenido, nombre_original):
    """Valida el contenido real sin escribir archivos."""

    if not isinstance(contenido, bytes):
        raise ValueError(
            "El contenido fotográfico debe estar en bytes."
        )

    if not contenido:
        raise ValueError("La fotografía está vacía.")

    if len(contenido) > MAX_BYTES_FOTOGRAFIA:
        raise ValueError(
            "La fotografía supera el tamaño permitido."
        )

    if not isinstance(nombre_original, str):
        raise ValueError("Nombre de fotografía inválido.")

    extension = Path(nombre_original).suffix.lower()

    if extension not in EXTENSIONES_PERMITIDAS:
        raise ValueError(
            "La extensión de la fotografía no está permitida."
        )

    if ImageFile.LOAD_TRUNCATED_IMAGES:
        raise RuntimeError(
            "La configuración de Pillow permite imágenes truncadas."
        )

    try:

        with warnings.catch_warnings():

            warnings.simplefilter(
                "error",
                Image.DecompressionBombWarning
            )

            with Image.open(io.BytesIO(contenido)) as imagen:

                formato = imagen.format
                ancho, alto = imagen.size

                if formato not in FORMATOS_PERMITIDOS:
                    raise ValueError(
                        "Formato fotográfico no permitido."
                    )

                if formato != EXTENSIONES_PERMITIDAS[extension]:
                    raise ValueError(
                        "La extensión no coincide con el formato real."
                    )

                if (
                    ancho <= 0
                    or alto <= 0
                    or ancho > MAX_DIMENSION_FOTOGRAFIA
                    or alto > MAX_DIMENSION_FOTOGRAFIA
                    or ancho * alto > MAX_PIXELES_FOTOGRAFIA
                ):
                    raise ValueError(
                        "Las dimensiones superan los límites permitidos."
                    )

                if getattr(imagen, "n_frames", 1) != 1:
                    raise ValueError(
                        "No se permiten imágenes animadas."
                    )

                imagen.verify()

            with Image.open(io.BytesIO(contenido)) as imagen:

                imagen.load()

    except ValueError:
        raise

    except Exception as error:

        raise ValueError(
            "La fotografía está dañada o no es válida."
        ) from error

    return {
        "formato": formato,
        "extension": FORMATOS_PERMITIDOS[formato],
        "ancho": ancho,
        "alto": alto,
        "bytes": len(contenido),
        "checksum": hashlib.sha256(contenido).hexdigest()
    }


def validar_carpeta_fotografica():
    """Comprueba la carpeta experimental sin crear directorios."""

    autorizada = (
        BASE_DIR / "data"
        / "imagenes"
    )

    if (
        CARPETA_FOTOGRAFIAS != autorizada
        or autorizada.resolve() != autorizada
        or not autorizada.is_dir()
        or autorizada.is_symlink()
    ):
        raise RuntimeError(
            "Carpeta fotográfica experimental no autorizada."
        )

    return autorizada


def guardar_fotografia_protegida(contenido, nombre_original):
    """Guarda una fotografía validada mediante escritura exclusiva."""

    metadatos = validar_contenido_fotografico(
        contenido,
        nombre_original
    )

    carpeta = validar_carpeta_fotografica()

    nombre = (
        uuid.uuid4().hex
        + metadatos["extension"]
    )

    ruta = carpeta / nombre

    creada = False
    identidad = None

    try:

        with ruta.open("xb") as salida:

            creada = True

            estado = os.fstat(salida.fileno())

            identidad = (
                estado.st_dev,
                estado.st_ino
            )

            cantidad = salida.write(contenido)

            if cantidad != len(contenido):
                raise OSError(
                    "Escritura fotográfica incompleta."
                )

            salida.flush()
            os.fsync(salida.fileno())

        if (
            ruta.is_symlink()
            or ruta.resolve() != ruta
            or not ruta.is_file()
            or ruta.stat().st_nlink != 1
        ):
            raise RuntimeError(
                "La fotografía guardada no superó la revisión de ruta."
            )

        estado_final = ruta.stat()

        if (
            estado_final.st_dev,
            estado_final.st_ino
        ) != identidad:
            raise RuntimeError(
                "La identidad del archivo cambió."
            )

        checksum_guardado = hashlib.sha256(
            ruta.read_bytes()
        ).hexdigest()

        if checksum_guardado != metadatos["checksum"]:
            raise OSError(
                "El contenido guardado no coincide con el original."
            )

    except Exception:

        if creada and identidad is not None:

            try:

                validar_carpeta_fotografica()

                estado_actual = ruta.lstat()

                if (
                    not ruta.is_symlink()
                    and ruta.resolve() == ruta
                    and estado_actual.st_nlink == 1
                    and (
                        estado_actual.st_dev,
                        estado_actual.st_ino
                    ) == identidad
                ):
                    ruta.unlink()

            except Exception:
                raise RuntimeError(
                    "No fue posible verificar la limpieza "
                    "del archivo experimental."
                )

        raise

    return {
        **metadatos,
        "nombre": nombre,
        "ruta_absoluta": str(ruta),
        "ruta_relativa": str(
            ruta.relative_to(BASE_DIR)
        ),
        "fotografia_guardada": True,
        "registro_bd_realizado": False
    }
