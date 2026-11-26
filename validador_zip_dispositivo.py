"""Validación preliminar de archivos ZIP del dispositivo."""

import hashlib
import io
import stat
import unicodedata
import zipfile

from pathlib import PurePosixPath


MAX_ZIP = 250 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
MAX_ARCHIVO = 50 * 1024 * 1024
MAX_ENTRADAS = 10000
MAX_RATIO = 200


def inspeccionar_zip_dispositivo(contenido):
    """Inspecciona un ZIP sin extraer archivos."""

    if not isinstance(contenido, bytes):
        raise ValueError(
            "El contenido debe recibirse como bytes."
        )

    if not contenido:
        raise ValueError("El archivo está vacío.")

    if len(contenido) > MAX_ZIP:
        raise ValueError(
            "El ZIP supera el tamaño permitido."
        )

    buffer = io.BytesIO(contenido)

    if not zipfile.is_zipfile(buffer):
        raise ValueError(
            "El archivo no es un ZIP válido."
        )

    resultado = {
        "checksum": hashlib.sha256(
            contenido
        ).hexdigest(),
        "excel": None,
        "fotografias": [],
        "archivos_ignorados": [],
        "bytes_zip": len(contenido),
        "bytes_descomprimidos": 0
    }

    excels = []
    nombres = set()

    with zipfile.ZipFile(buffer, "r") as zip_archivo:

        entradas = zip_archivo.infolist()

        if len(entradas) > MAX_ENTRADAS:
            raise ValueError(
                "El ZIP contiene demasiadas entradas."
            )

        for entrada in entradas:

            nombre = entrada.filename
            ruta = PurePosixPath(nombre)

            if (
                not nombre
                or ruta.is_absolute()
                or ".." in ruta.parts
                or chr(92) in nombre
                or ":" in nombre
                or any(
                    ord(c) < 32
                    for c in nombre
                )
            ):
                raise ValueError(
                    "El ZIP contiene una ruta insegura."
                )

            modo = entrada.external_attr >> 16
            tipo = stat.S_IFMT(modo)

            if tipo not in (
                0,
                stat.S_IFREG,
                stat.S_IFDIR
            ):
                raise ValueError(
                    "El ZIP contiene un tipo de archivo "
                    "no permitido."
                )

            clave = unicodedata.normalize(
                "NFC", str(ruta)
            ).casefold()

            if clave in nombres:
                raise ValueError(
                    "El ZIP contiene rutas duplicadas."
                )

            nombres.add(clave)

            if entrada.flag_bits & 1:
                raise ValueError(
                    "No se admiten archivos cifrados."
                )

            if entrada.is_dir():
                if entrada.file_size != 0:
                    raise ValueError(
                        "Directorio ZIP inválido."
                    )
                continue

            if entrada.compress_type not in (
                zipfile.ZIP_STORED,
                zipfile.ZIP_DEFLATED
            ):
                raise ValueError(
                    "Método de compresión no permitido."
                )

            if entrada.file_size > MAX_ARCHIVO:
                raise ValueError(
                    "Un archivo supera el límite permitido."
                )

            resultado["bytes_descomprimidos"] += (
                entrada.file_size
            )

            if resultado["bytes_descomprimidos"] > MAX_TOTAL:
                raise ValueError(
                    "El contenido descomprimido "
                    "supera el límite permitido."
                )

            ratio = entrada.file_size / max(
                entrada.compress_size, 1
            )

            if ratio > MAX_RATIO:
                raise ValueError(
                    "Se detectó una relación de "
                    "compresión excesiva."
                )

            if (
                "__MACOSX" in ruta.parts
                or ruta.name == ".DS_Store"
                or ruta.name.startswith("._")
            ):
                resultado["archivos_ignorados"].append(
                    nombre
                )
                continue

            extension = ruta.suffix.lower()

            if extension == ".xlsx":
                excels.append(nombre)

            elif extension in (".jpg", ".jpeg"):
                resultado["fotografias"].append(
                    nombre
                )

            else:
                raise ValueError(
                    f"Archivo no permitido: {nombre}"
                )

        if len(excels) != 1:
            raise ValueError(
                "El ZIP debe contener exactamente "
                "un archivo Excel XLSX."
            )

        resultado["excel"] = excels[0]

    resultado["fotografias"].sort()

    resultado["cantidad_fotografias"] = len(
        resultado["fotografias"]
    )

    return resultado



# Límites preliminares del contenido interno.
MAX_PIXELES_JPEG = 25000000
MAX_DIMENSION_JPEG = 12000
MAX_XLSX_INTERNO = 200 * 1024 * 1024
MAX_ENTRADAS_XLSX = 2000


def _validar_rutas_internas(entradas):
    """Detecta rutas ambiguas y colisiones."""

    archivos = set()
    directorios = set()
    nombres = set()

    for entrada in entradas:

        nombre = entrada.orig_filename
        limpio = nombre.rstrip("/")

        partes = limpio.split("/")

        if (
            not limpio
            or chr(92) in nombre
            or ":" in nombre
            or any(ord(c) < 32 for c in nombre)
            or any(
                parte in ("", ".", "..")
                for parte in partes
            )
        ):
            raise ValueError(
                "Ruta interna insegura o ambigua."
            )

        modo = entrada.external_attr >> 16
        tipo = stat.S_IFMT(modo)

        if tipo not in (
            0,
            stat.S_IFREG,
            stat.S_IFDIR
        ):
            raise ValueError(
                "Tipo de archivo interno no permitido."
            )

        if (
            tipo == stat.S_IFDIR
            and not entrada.is_dir()
        ) or (
            tipo == stat.S_IFREG
            and entrada.is_dir()
        ):
            raise ValueError(
                "Tipo de entrada ZIP inconsistente."
            )

        partes = [
            unicodedata.normalize(
                "NFC", parte
            ).casefold()
            for parte in partes
        ]

        clave = "/".join(partes)

        if clave in nombres:
            raise ValueError(
                "Ruta interna duplicada."
            )

        nombres.add(clave)

        for i in range(1, len(partes)):
            directorios.add(
                "/".join(partes[:i])
            )

        if entrada.is_dir():
            directorios.add(clave)
        else:
            archivos.add(clave)

    if archivos.intersection(directorios):
        raise ValueError(
            "Colisión entre archivo y directorio."
        )


def _leer_entrada_controlada(
    archivo_zip,
    entrada,
    limite,
    conservar=False
):
    """Lee una entrada y comprueba su tamaño y CRC."""

    total = 0
    bloques = [] if conservar else None

    with archivo_zip.open(entrada, "r") as origen:

        while True:

            bloque = origen.read(1024 * 1024)

            if not bloque:
                break

            total += len(bloque)

            if total > limite:
                raise ValueError(
                    "Contenido descomprimido excesivo."
                )

            if total > entrada.file_size:
                raise ValueError(
                    "Tamaño interno inconsistente."
                )

            if conservar:
                bloques.append(bloque)

    if total != entrada.file_size:
        raise ValueError(
            "Contenido incompleto."
        )

    if conservar:
        return b"".join(bloques)

    return total


def _validar_excel_interno(contenido):
    """Comprueba la estructura básica de un XLSX."""

    buffer = io.BytesIO(contenido)

    if not zipfile.is_zipfile(buffer):
        raise ValueError(
            "El Excel no es un XLSX válido."
        )

    with zipfile.ZipFile(buffer, "r") as z:

        entradas = z.infolist()

        if len(entradas) > MAX_ENTRADAS_XLSX:
            raise ValueError(
                "El Excel contiene demasiadas entradas."
            )

        _validar_rutas_internas(entradas)

        nombres = {
            e.filename
            for e in entradas
            if not e.is_dir()
        }

        obligatorios = {
            "[Content_Types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels"
        }

        if not obligatorios.issubset(nombres):
            raise ValueError(
                "Estructura XLSX incompleta."
            )

        if not any(
            nombre.startswith("xl/worksheets/")
            and nombre.endswith(".xml")
            for nombre in nombres
        ):
            raise ValueError(
                "El Excel no contiene hojas reconocibles."
            )

        total = 0

        for entrada in entradas:

            if entrada.flag_bits & 1:
                raise ValueError(
                    "Excel interno cifrado."
                )

            if entrada.is_dir():

                if entrada.file_size != 0:
                    raise ValueError(
                        "Directorio interno inválido."
                    )

                continue

            if entrada.compress_type not in (
                zipfile.ZIP_STORED,
                zipfile.ZIP_DEFLATED
            ):
                raise ValueError(
                    "Compresión XLSX no permitida."
                )

            total += entrada.file_size

            if total > MAX_XLSX_INTERNO:
                raise ValueError(
                    "El Excel descomprimido es demasiado grande."
                )

            if entrada.file_size > MAX_ARCHIVO:
                raise ValueError(
                    "Entrada interna XLSX demasiado grande."
                )

            ratio = entrada.file_size / max(
                entrada.compress_size, 1
            )

            if ratio > MAX_RATIO:
                raise ValueError(
                    "Compresión interna XLSX excesiva."
                )

            nombre = entrada.filename.casefold()

            if (
                nombre.endswith("vbaproject.bin")
                or nombre.startswith("xl/externallinks/")
                or nombre.startswith("xl/embeddings/")
            ):
                raise ValueError(
                    "El Excel contiene componentes no permitidos."
                )

            _leer_entrada_controlada(
                z,
                entrada,
                MAX_ARCHIVO
            )

    return {
        "bytes_xlsx": len(contenido),
        "bytes_internos": total,
        "entradas_internas": len(entradas)
    }


def _validar_jpeg(contenido):
    """Verifica el formato y decodificación JPEG."""

    import warnings
    from PIL import Image, ImageFile

    if ImageFile.LOAD_TRUNCATED_IMAGES:
        raise ValueError(
            "La configuración permite imágenes truncadas."
        )

    with warnings.catch_warnings():

        warnings.simplefilter(
            "error",
            Image.DecompressionBombWarning
        )

        with Image.open(
            io.BytesIO(contenido)
        ) as imagen:

            if imagen.format != "JPEG":
                raise ValueError(
                    "El archivo no contiene un JPEG real."
                )

            ancho, alto = imagen.size

            if (
                ancho <= 0
                or alto <= 0
                or ancho > MAX_DIMENSION_JPEG
                or alto > MAX_DIMENSION_JPEG
                or ancho * alto > MAX_PIXELES_JPEG
            ):
                raise ValueError(
                    "Dimensiones JPEG no permitidas."
                )

            imagen.verify()

        with Image.open(
            io.BytesIO(contenido)
        ) as imagen:

            imagen.load()

    return {
        "ancho": ancho,
        "alto": alto,
        "bytes": len(contenido),
        "checksum": hashlib.sha256(
            contenido
        ).hexdigest()
    }


def validar_contenido_zip_dispositivo(contenido):
    """Valida estructura y contenido sin extraer archivos."""

    from PIL import Image

    try:

        resultado = inspeccionar_zip_dispositivo(
            contenido
        )

        detalles_fotos = []

        with zipfile.ZipFile(
            io.BytesIO(contenido), "r"
        ) as z:

            _validar_rutas_internas(
                z.infolist()
            )

            fotos = set(
                resultado["fotografias"]
            )

            for entrada in z.infolist():

                if entrada.is_dir():
                    continue

                nombre = entrada.filename

                if nombre == resultado["excel"]:

                    datos = _leer_entrada_controlada(
                        z,
                        entrada,
                        MAX_ARCHIVO,
                        conservar=True
                    )

                    resultado["detalle_excel"] = (
                        _validar_excel_interno(datos)
                    )

                    del datos

                elif nombre in fotos:

                    datos = _leer_entrada_controlada(
                        z,
                        entrada,
                        MAX_ARCHIVO,
                        conservar=True
                    )

                    detalle = _validar_jpeg(datos)

                    detalle["nombre"] = nombre

                    detalles_fotos.append(detalle)

                    del datos

                else:

                    _leer_entrada_controlada(
                        z,
                        entrada,
                        MAX_ARCHIVO
                    )

        resultado["detalle_fotografias"] = (
            detalles_fotos
        )

        resultado["contenido_validado"] = True

        return resultado

    except (
        zipfile.BadZipFile,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        EOFError,
        RuntimeError,
        NotImplementedError,
        SyntaxError
    ) as error:

        raise ValueError(
            "Contenido ZIP, XLSX o JPEG inválido."
        ) from error
