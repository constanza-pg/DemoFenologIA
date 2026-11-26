"""Inspección centralizada del ZIP del dispositivo."""

import io
import zipfile

from validador_zip_dispositivo import (
    validar_contenido_zip_dispositivo,
    _leer_entrada_controlada,
    MAX_ARCHIVO
)

from lector_excel_dispositivo import (
    inspeccionar_hojas_excel
)

from interpretador_excel_dispositivo import (
    detectar_encabezados_excel,
    sugerir_columnas_ambiguas
)


def inspeccionar_zip_completo(contenido):
    """Inspecciona un ZIP sin guardar datos ni fotografías."""

    validacion = validar_contenido_zip_dispositivo(
        contenido
    )

    with zipfile.ZipFile(
        io.BytesIO(contenido), "r"
    ) as z:

        entrada = z.getinfo(
            validacion["excel"]
        )

        excel = _leer_entrada_controlada(
            z,
            entrada,
            MAX_ARCHIVO,
            conservar=True
        )

    inspeccion = inspeccionar_hojas_excel(
        excel
    )

    encabezados = detectar_encabezados_excel(
        inspeccion
    )

    sugerencias = []
    advertencias = []

    if validacion["cantidad_fotografias"] == 0:

        advertencias.append({
            "codigo": "SIN_FOTOGRAFIAS",
            "mensaje": (
                "El ZIP no contiene fotografías JPG."
            )
        })

    if encabezados["cantidad_candidatos"] == 0:

        advertencias.append({
            "codigo": "SIN_ENCABEZADOS",
            "mensaje": (
                "No se detectaron posibles encabezados "
                "en las filas examinadas."
            )
        })

    for hoja, deteccion in zip(
        inspeccion["hojas"],
        encabezados["hojas"]
    ):

        if hoja["vacia"]:

            advertencias.append({
                "codigo": "HOJA_VACIA",
                "hoja": hoja["nombre"],
                "mensaje": (
                    "La hoja no contiene datos."
                )
            })

        if hoja["visibilidad"] != "visible":

            advertencias.append({
                "codigo": "HOJA_OCULTA",
                "hoja": hoja["nombre"],
                "mensaje": (
                    "El Excel contiene una hoja oculta."
                )
            })

        for candidato in deteccion["candidatos"]:

            sugerencia = sugerir_columnas_ambiguas(
                hoja,
                candidato
            )

            sugerencias.append(sugerencia)

            for columna in candidato["columnas"]:

                estado = columna["estado"]

                if estado not in (
                    "AMBIGUO",
                    "CONFLICTO",
                    "DESCONOCIDO"
                ):
                    continue

                advertencias.append({
                    "codigo": "COLUMNA_" + estado,
                    "hoja": hoja["nombre"],
                    "fila": candidato["fila"],
                    "columna": columna["columna"],
                    "encabezado": columna["original"],
                    "mensaje": (
                        "La columna requiere revisión "
                        "antes de importar."
                    )
                })

    resumen = {
        "archivo_excel": validacion["excel"],
        "checksum_zip": validacion["checksum"],
        "bytes_zip": validacion["bytes_zip"],
        "cantidad_fotografias": (
            validacion["cantidad_fotografias"]
        ),
        "cantidad_hojas": inspeccion["cantidad_hojas"],
        "cantidad_hojas_vacias": sum(
            hoja["vacia"]
            for hoja in inspeccion["hojas"]
        ),
        "cantidad_encabezados_candidatos": (
            encabezados["cantidad_candidatos"]
        ),
        "cantidad_advertencias": len(advertencias)
    }

    return {
        "version_inspector": "1.0-preliminar",
        "estado": "INSPECCION_COMPLETADA",
        "resumen": resumen,
        "zip": validacion,
        "excel": inspeccion,
        "encabezados": encabezados,
        "sugerencias": sugerencias,
        "advertencias": advertencias,
        "seleccion_confirmada": False,
        "listo_para_importar": False,
        "datos_guardados": False
    }
