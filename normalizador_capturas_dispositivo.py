"""Normalización estructural de capturas del dispositivo."""

from interpretador_excel_dispositivo import ALIAS_COLUMNAS

from lector_excel_dispositivo import (
    MAX_COLUMNAS_EXCEL,
    MAX_FILAS_EXCEL
)


CAMPOS_CAPTURA = tuple(ALIAS_COLUMNAS)


def validar_asignaciones_captura(asignaciones):
    """Valida las asignaciones sin inferir nuevos campos."""

    if not isinstance(asignaciones, dict):
        raise ValueError(
            "Las asignaciones deben ser un diccionario."
        )

    asignaciones_validas = {}
    campos_utilizados = set()

    for columna, campo in asignaciones.items():

        if (
            type(columna) is not int
            or not 1 <= columna <= MAX_COLUMNAS_EXCEL
        ):
            raise ValueError(
                "Posición de columna inválida."
            )

        if not isinstance(campo, str):
            raise ValueError(
                "El campo asignado debe ser texto."
            )

        if campo == "":
            continue

        if campo not in CAMPOS_CAPTURA:
            raise ValueError(
                f"Campo desconocido: {campo}"
            )

        if campo in campos_utilizados:
            raise ValueError(
                f"Campo asignado más de una vez: {campo}"
            )

        campos_utilizados.add(campo)
        asignaciones_validas[columna] = campo

    if "codigo_planta" not in campos_utilizados:
        raise ValueError(
            "Se requiere asignar el código de planta."
        )

    if (
        "fecha_hora" in campos_utilizados
        and (
            "fecha" in campos_utilizados
            or "hora" in campos_utilizados
        )
    ):
        raise ValueError(
            "Asignación temporal incompatible."
        )

    return asignaciones_validas


def normalizar_capturas_excel(
    lectura,
    nombre_hoja,
    fila_encabezado,
    asignaciones
):
    """Organiza filas completas sin validar su significado."""

    if (
        not isinstance(lectura, dict)
        or lectura.get("lectura_completa") is not True
    ):
        raise ValueError(
            "Se requiere una lectura completa del Excel."
        )

    if (
        not isinstance(nombre_hoja, str)
        or not nombre_hoja.strip()
    ):
        raise ValueError(
            "Nombre de hoja inválido."
        )

    if (
        type(fila_encabezado) is not int
        or not 1 <= fila_encabezado <= MAX_FILAS_EXCEL
    ):
        raise ValueError(
            "Fila de encabezado inválida."
        )

    asignaciones_validas = (
        validar_asignaciones_captura(asignaciones)
    )

    coincidencias = [
        hoja for hoja in lectura["hojas"]
        if hoja["nombre"] == nombre_hoja
    ]

    if len(coincidencias) != 1:
        raise ValueError(
            "La hoja seleccionada no es única o no existe."
        )

    hoja = coincidencias[0]
    filas = hoja.get("filas_completas")

    if (
        not isinstance(filas, list)
        or len(filas) != hoja["filas_con_datos"]
    ):
        raise ValueError(
            "Las filas completas son inconsistentes."
        )

    if any(
        columna > hoja["ultima_columna_con_datos"]
        for columna in asignaciones_validas
    ):
        raise ValueError(
            "Existe una asignación fuera de las columnas."
        )

    capturas = []
    encabezado_encontrado = False
    encabezados_originales = {}
    fila_anterior = 0
    filas_anteriores = 0

    for fila in filas:

        numero = fila["fila"]

        if (
            type(numero) is not int
            or not 1 <= numero <= MAX_FILAS_EXCEL
            or numero <= fila_anterior
        ):
            raise ValueError(
                "Fila inválida, duplicada o desordenada."
            )

        fila_anterior = numero

        celdas = {}

        for celda in fila["celdas"]:

            columna = celda["columna"]

            if (
                type(columna) is not int
                or not 1 <= columna <= MAX_COLUMNAS_EXCEL
                or columna in celdas
            ):
                raise ValueError(
                    "Columna inválida o duplicada."
                )

            celdas[columna] = celda

        if not celdas:
            raise ValueError(
                "Fila completa sin celdas."
            )

        if numero < fila_encabezado:
            filas_anteriores += 1
            continue

        if numero == fila_encabezado:

            encabezados_originales = {
                columna: {
                    "valor": celda["valor"],
                    "tipo": celda["tipo"]
                }
                for columna, celda in celdas.items()
            }

            encabezado_encontrado = True
            continue

        captura = {
            campo: None
            for campo in CAMPOS_CAPTURA
        }

        captura["hoja_excel"] = nombre_hoja
        captura["fila_excel"] = numero

        for columna, campo in asignaciones_validas.items():

            celda = celdas.get(columna)

            if celda is not None:
                captura[campo] = celda["valor"]

        datos_adicionales = []
        celdas_originales = []

        for columna, celda in sorted(celdas.items()):

            encabezado = encabezados_originales.get(
                columna, {}
            )

            registro_celda = {
                "columna": columna,
                "encabezado": encabezado.get("valor"),
                "tipo_encabezado": encabezado.get("tipo"),
                "valor": celda["valor"],
                "tipo": celda["tipo"],
                "campo_asignado": asignaciones_validas.get(
                    columna
                )
            }

            celdas_originales.append(
                registro_celda
            )

            if columna not in asignaciones_validas:

                datos_adicionales.append(
                    registro_celda.copy()
                )

        captura["datos_adicionales"] = datos_adicionales

        captura["trazabilidad"] = {
            "hoja_excel": nombre_hoja,
            "fila_excel": numero,
            "fila_encabezado": fila_encabezado,
            "celdas_originales": celdas_originales
        }

        capturas.append(captura)

    if not encabezado_encontrado:
        raise ValueError(
            "No existe el encabezado seleccionado."
        )

    if not capturas:
        raise ValueError(
            "No existen filas posteriores al encabezado."
        )

    if (
        len(capturas) + filas_anteriores + 1
        != len(filas)
    ):
        raise ValueError(
            "Cantidad de filas normalizadas inconsistente."
        )

    return {
        "estado": "NORMALIZACION_COMPLETADA",
        "hoja_excel": nombre_hoja,
        "fila_encabezado": fila_encabezado,
        "asignaciones": asignaciones_validas,
        "cantidad_capturas": len(capturas),
        "filas_anteriores_encabezado": filas_anteriores,
        "capturas": capturas,
        "encabezados_originales": encabezados_originales,
        "cantidad_capturas_con_datos_adicionales": sum(
            bool(c["datos_adicionales"])
            for c in capturas
        ),
        "cantidad_celdas_adicionales": sum(
            len(c["datos_adicionales"])
            for c in capturas
        ),
        "trazabilidad_incorporada": True,
        "validacion_semantica_completada": False,
        "listo_para_importar": False,
        "datos_guardados": False
    }
