"""
Validación centralizada de rutas fotográficas.

Uso exclusivo del entorno experimental ZIP.
No escribe archivos ni modifica bases de datos.
"""

from pathlib import Path
import stat

BASE_DIR = Path(__file__).resolve().parent

CARPETA_FOTOGRAFIAS = (
    BASE_DIR / "data"
    / "imagenes"
)

CARPETA_RESULTADOS_IA = (
    BASE_DIR / "data"
    / "analisis_dispositivo"
)

EXTENSIONES_PERMITIDAS = {
    ".jpg", ".jpeg", ".png"
}

METODOS_PERMITIDOS = {
    "hsv", "yolo", "roboflow"
}


def _validar_raiz(raiz, autorizada):

    if (
        raiz != autorizada
        or raiz.resolve() != raiz
        or raiz.is_symlink()
        or not raiz.is_dir()
    ):

        raise ValueError(
            "Carpeta experimental no autorizada."
        )

    return raiz


def _validar_ruta_archivo(ruta_archivo, raiz):

    if not isinstance(ruta_archivo, (str, Path)):

        raise ValueError(
            "Referencia de archivo inválida."
        )

    texto = str(ruta_archivo)

    if not texto.strip():

        raise ValueError(
            "Referencia de archivo vacía."
        )

    if any(
        ord(caracter) < 32 or ord(caracter) == 127
        for caracter in texto
    ):

        raise ValueError(
            "Referencia de archivo no autorizada."
        )

    ruta = Path(texto)

    if ".." in ruta.parts:

        raise ValueError(
            "No se permiten desplazamientos de ruta."
        )

    if not ruta.is_absolute():

        ruta = BASE_DIR / ruta

    if not ruta.is_relative_to(raiz):

        raise ValueError(
            "Archivo fuera del entorno autorizado."
        )

    if ruta.suffix.lower() not in EXTENSIONES_PERMITIDAS:

        raise ValueError(
            "Extensión fotográfica no autorizada."
        )

    # Revisar cada componente de la ruta antes
    # de resolverla para detectar enlaces internos.

    actual = raiz

    for componente in ruta.relative_to(raiz).parts:

        actual = actual / componente

        if actual.is_symlink():

            raise ValueError(
                "No se permiten enlaces simbólicos."
            )

    if ruta.resolve() != ruta:

        raise ValueError(
            "La ruta del archivo no es segura."
        )

    if not ruta.is_file():

        raise FileNotFoundError(
            "Archivo fotográfico no disponible."
        )

    estado = ruta.lstat()

    if not stat.S_ISREG(estado.st_mode):

        raise ValueError(
            "El archivo no es regular."
        )

    if estado.st_nlink != 1:

        raise ValueError(
            "No se permiten enlaces físicos adicionales."
        )

    return ruta


def validar_ruta_fotografia(ruta_archivo):

    autorizada = (
        BASE_DIR / "data"
        / "imagenes"
    )

    raiz = _validar_raiz(
        CARPETA_FOTOGRAFIAS,
        autorizada
    )

    return _validar_ruta_archivo(
        ruta_archivo,
        raiz
    )


def validar_ruta_resultado_ia(
    ruta_archivo,
    metodo
):

    if metodo not in METODOS_PERMITIDOS:

        raise ValueError(
            "Método de análisis no autorizado."
        )

    autorizada = (
        BASE_DIR / "data"
        / "analisis_dispositivo"
    )

    raiz = _validar_raiz(
        CARPETA_RESULTADOS_IA,
        autorizada
    )

    carpeta_metodo = raiz / metodo

    _validar_raiz(
        carpeta_metodo,
        autorizada / metodo
    )

    return _validar_ruta_archivo(
        ruta_archivo,
        carpeta_metodo
    )


def obtener_ruta_fotografia_segura(ruta_archivo):

    try:

        return validar_ruta_fotografia(
            ruta_archivo
        )

    except (ValueError, OSError, RuntimeError):

        return None


def obtener_ruta_resultado_ia_segura(
    ruta_archivo,
    metodo
):

    try:

        return validar_ruta_resultado_ia(
            ruta_archivo,
            metodo
        )

    except (ValueError, OSError, RuntimeError):

        return None
