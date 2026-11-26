"""Indexación y vinculación de fotografías del dispositivo."""

import unicodedata

from pathlib import PurePosixPath


def normalizar_nombre_fotografia(nombre):
    """Normaliza nombres únicamente para buscar coincidencias."""

    if not isinstance(nombre, str):
        raise ValueError(
            "El nombre debe ser texto."
        )

    return unicodedata.normalize(
        "NFC", nombre
    ).casefold()


def construir_indice_fotografias(validacion):
    """Construye un índice a partir de fotografías validadas."""

    if validacion.get("contenido_validado") is not True:

        raise ValueError(
            "El ZIP debe validarse antes de indexar fotografías."
        )

    fotografias = validacion["detalle_fotografias"]

    if len(fotografias) != validacion["cantidad_fotografias"]:

        raise ValueError(
            "Cantidad de fotografías inconsistente."
        )

    por_ruta = {}
    por_nombre = {}
    por_checksum = {}

    for fotografia in fotografias:

        ruta = fotografia["nombre"]

        nombre = PurePosixPath(ruta).name

        clave_ruta = normalizar_nombre_fotografia(
            ruta
        )

        clave_nombre = normalizar_nombre_fotografia(
            nombre
        )

        checksum = fotografia["checksum"]

        if clave_ruta in por_ruta:

            raise ValueError(
                "Ruta de fotografía duplicada."
            )

        detalle = {
            "ruta": ruta,
            "nombre": nombre,
            "checksum": checksum,
            "ancho": fotografia["ancho"],
            "alto": fotografia["alto"],
            "bytes": fotografia["bytes"]
        }

        por_ruta[clave_ruta] = detalle

        por_nombre.setdefault(
            clave_nombre, []
        ).append(ruta)

        por_checksum.setdefault(
            checksum, []
        ).append(ruta)

    nombres_repetidos = {
        nombre: rutas
        for nombre, rutas in por_nombre.items()
        if len(rutas) > 1
    }

    contenidos_repetidos = {
        checksum: rutas
        for checksum, rutas in por_checksum.items()
        if len(rutas) > 1
    }

    return {
        "cantidad_fotografias": len(por_ruta),
        "checksum_zip": validacion["checksum"],
        "por_ruta": por_ruta,
        "por_nombre": por_nombre,
        "por_checksum": por_checksum,
        "nombres_repetidos": nombres_repetidos,
        "contenidos_repetidos": contenidos_repetidos,
        "indice_completado": True
    }



def buscar_fotografia(referencia, indice):
    """Busca una fotografía sin realizar una vinculación definitiva."""

    if indice.get("indice_completado") is not True:

        raise ValueError(
            "El índice de fotografías no está validado."
        )

    resultado = {
        "referencia_original": referencia,
        "estado": None,
        "metodo": None,
        "coincidencias": [],
        "fotografia": None,
        "vinculacion_confirmada": False
    }

    if referencia is None:

        resultado["estado"] = "SIN_REFERENCIA"

        return resultado

    if not isinstance(referencia, str):

        resultado["estado"] = "REFERENCIA_INVALIDA"

        return resultado

    texto = referencia.strip()

    if not texto:

        resultado["estado"] = "SIN_REFERENCIA"

        return resultado

    partes = texto.split("/")

    if (
        texto.startswith("/")
        or chr(92) in texto
        or ":" in texto
        or any(
            ord(c) < 32 or ord(c) == 127
            for c in texto
        )
        or any(
            parte in ("", ".", "..")
            for parte in partes
        )
    ):

        resultado["estado"] = "REFERENCIA_INSEGURA"

        return resultado

    if not texto.casefold().endswith(
        (".jpg", ".jpeg")
    ):

        resultado["estado"] = "EXTENSION_INVALIDA"

        return resultado

    clave = normalizar_nombre_fotografia(
        texto
    )

    if "/" in texto:

        resultado["metodo"] = "RUTA_COMPLETA"

        detalle = indice["por_ruta"].get(
            clave
        )

        if detalle is not None:

            resultado["coincidencias"] = [
                detalle["ruta"]
            ]

    else:

        resultado["metodo"] = "NOMBRE_ARCHIVO"

        resultado["coincidencias"] = list(
            indice["por_nombre"].get(
                clave, []
            )
        )

    cantidad = len(
        resultado["coincidencias"]
    )

    if cantidad == 0:

        resultado["estado"] = "NO_ENCONTRADA"

    elif cantidad > 1:

        resultado["estado"] = "AMBIGUA"

    else:

        resultado["estado"] = "COINCIDENCIA_UNICA"

        ruta = resultado["coincidencias"][0]

        resultado["fotografia"] = dict(
            indice["por_ruta"][
                normalizar_nombre_fotografia(ruta)
            ]
        )

    return resultado



def interpretar_indicador_fotografia(valor):
    """Interpreta un indicador sin confundir ausencia con negación."""

    if valor is None:
        return "NO_INFORMADO"

    if isinstance(valor, bool):
        return "SI" if valor else "NO"

    if isinstance(valor, (int, float)):

        if valor == 1:
            return "SI"

        if valor == 0:
            return "NO"

        return "INVALIDO"

    if isinstance(valor, str):

        texto = unicodedata.normalize(
            "NFC", valor.strip()
        ).casefold()

        if not texto:
            return "NO_INFORMADO"

        if texto in ("si", "sí", "true", "yes", "1"):
            return "SI"

        if texto in ("no", "false", "0"):
            return "NO"

    return "INVALIDO"


def evaluar_fotografia_captura(captura, indice):
    """Evalúa una posible asociación sin guardar información."""

    if indice.get("indice_completado") is not True:

        raise ValueError(
            "Se requiere un índice validado."
        )

    if not isinstance(captura, dict):

        raise ValueError(
            "La captura debe ser un diccionario."
        )

    indicador = interpretar_indicador_fotografia(
        captura.get("tiene_fotografia")
    )

    referencia = captura.get("archivo_fotografia")

    busqueda = buscar_fotografia(
        referencia,
        indice
    )

    estado_busqueda = busqueda["estado"]

    resultado = {
        "codigo_planta": captura.get("codigo_planta"),
        "fila_excel": captura.get("fila_excel"),
        "indicador_original": captura.get(
            "tiene_fotografia"
        ),
        "indicador_interpretado": indicador,
        "referencia_original": referencia,
        "estado": None,
        "fotografia_propuesta": None,
        "busqueda": busqueda,
        "requiere_revision": True,
        "requiere_autorizacion_excepcional": False,
        "autorizacion_excepcional_confirmada": False,
        "vinculacion_confirmada": False,
        "datos_guardados": False
    }

    if indicador == "INVALIDO":

        resultado["estado"] = "INDICADOR_INVALIDO"

    elif indicador == "NO":

        if estado_busqueda == "SIN_REFERENCIA":

            resultado["estado"] = "SIN_FOTOGRAFIA"
            resultado["requiere_revision"] = True
            resultado[
                "requiere_autorizacion_excepcional"
            ] = True

        else:

            resultado["estado"] = (
                "CONFLICTO_INDICADOR_REFERENCIA"
            )

    elif estado_busqueda == "SIN_REFERENCIA":

        if indicador == "SI":

            resultado["estado"] = (
                "VINCULACION_PENDIENTE"
            )

        else:

            resultado["estado"] = (
                "INFORMACION_INSUFICIENTE"
            )

    elif estado_busqueda == "COINCIDENCIA_UNICA":

        resultado["estado"] = "FOTOGRAFIA_PROPUESTA"

        resultado["fotografia_propuesta"] = (
            busqueda["fotografia"]
        )

    elif estado_busqueda == "AMBIGUA":

        resultado["estado"] = "FOTOGRAFIA_AMBIGUA"

    elif estado_busqueda == "NO_ENCONTRADA":

        resultado["estado"] = (
            "FOTOGRAFIA_NO_ENCONTRADA"
        )

    else:

        resultado["estado"] = "REFERENCIA_INVALIDA"

    return resultado



def evaluar_conjunto_capturas(capturas, indice):
    """Evalúa asociaciones fotográficas de un conjunto de capturas."""

    if indice.get("indice_completado") is not True:

        raise ValueError(
            "Se requiere un índice validado."
        )

    if not isinstance(capturas, (list, tuple)):

        raise ValueError(
            "Las capturas deben entregarse como una lista."
        )

    evaluaciones = []
    filas_identificadas = set()
    propuestas_por_ruta = {}
    referencias_unicas_por_ruta = {}
    coincidencias_por_ruta = {}
    posibles_rutas = set()
    conteo_estados = {}

    for captura in capturas:

        if not isinstance(captura, dict):

            raise ValueError(
                "Cada captura debe ser un diccionario."
            )

        fila = captura.get("fila_excel")

        hoja = captura.get("hoja_excel", "")

        if (
            isinstance(fila, bool)
            or not isinstance(fila, int)
            or fila < 1
        ):

            raise ValueError(
                "Cada captura requiere una fila Excel válida."
            )

        if not isinstance(hoja, str):

            raise ValueError(
                "El nombre de hoja debe ser texto."
            )

        identificador = (hoja, fila)

        if identificador in filas_identificadas:

            raise ValueError(
                "Existe una fila Excel repetida."
            )

        filas_identificadas.add(identificador)

        evaluacion = evaluar_fotografia_captura(
            captura,
            indice
        )

        evaluacion["hoja_excel"] = hoja

        evaluacion["fecha_hora"] = captura.get(
            "fecha_hora"
        )

        evaluacion["referencia_compartida"] = False
        evaluacion["solapamiento_potencial"] = False

        evaluacion["advertencias"] = []

        estado = evaluacion["estado"]

        conteo_estados[estado] = (
            conteo_estados.get(estado, 0) + 1
        )

        coincidencias = evaluacion["busqueda"][
            "coincidencias"
        ]

        posibles_rutas.update(coincidencias)

        posicion_actual = len(evaluaciones)

        for ruta_candidata in dict.fromkeys(coincidencias):

            coincidencias_por_ruta.setdefault(
                ruta_candidata, []
            ).append(posicion_actual)

        if (
            evaluacion["busqueda"]["estado"]
            == "COINCIDENCIA_UNICA"
        ):

            ruta_unica = coincidencias[0]

            referencias_unicas_por_ruta.setdefault(
                ruta_unica, []
            ).append(posicion_actual)

        fotografia = evaluacion[
            "fotografia_propuesta"
        ]

        if fotografia is not None:

            ruta = fotografia["ruta"]

            propuestas_por_ruta.setdefault(
                ruta, []
            ).append(len(evaluaciones))

        evaluaciones.append(evaluacion)

    referencias_compartidas = []

    for ruta, posiciones in sorted(
        referencias_unicas_por_ruta.items()
    ):

        if len(posiciones) < 2:
            continue

        registros = []

        for posicion in posiciones:

            evaluacion = evaluaciones[posicion]

            evaluacion["referencia_compartida"] = True

            evaluacion["requiere_revision"] = True

            evaluacion["advertencias"].append(
                "FOTOGRAFIA_COMPARTIDA"
            )

            registros.append({
                "hoja_excel": evaluacion["hoja_excel"],
                "fila_excel": evaluacion["fila_excel"],
                "codigo_planta": evaluacion["codigo_planta"],
                "fecha_hora": evaluacion["fecha_hora"]
            })

        referencias_compartidas.append({
            "ruta": ruta,
            "cantidad_capturas": len(posiciones),
            "capturas": registros
        })

    solapamientos_potenciales = []

    for ruta, posiciones in sorted(
        coincidencias_por_ruta.items()
    ):

        if len(posiciones) < 2:
            continue

        if not any(
            evaluaciones[posicion]["busqueda"]["estado"]
            == "AMBIGUA"
            for posicion in posiciones
        ):
            continue

        registros = []

        for posicion in posiciones:

            evaluacion = evaluaciones[posicion]

            evaluacion["solapamiento_potencial"] = True
            evaluacion["requiere_revision"] = True

            if (
                "SOLAPAMIENTO_POTENCIAL"
                not in evaluacion["advertencias"]
            ):
                evaluacion["advertencias"].append(
                    "SOLAPAMIENTO_POTENCIAL"
                )

            registros.append({
                "hoja_excel": evaluacion["hoja_excel"],
                "fila_excel": evaluacion["fila_excel"],
                "codigo_planta": evaluacion["codigo_planta"],
                "fecha_hora": evaluacion["fecha_hora"],
                "estado": evaluacion["estado"],
                "estado_busqueda": evaluacion[
                    "busqueda"
                ]["estado"]
            })

        solapamientos_potenciales.append({
            "ruta": ruta,
            "cantidad_capturas": len(posiciones),
            "capturas": registros
        })

    todas_las_rutas = {
        detalle["ruta"]
        for detalle in indice["por_ruta"].values()
    }

    rutas_propuestas = set(
        propuestas_por_ruta
    )

    sin_propuesta = sorted(
        todas_las_rutas - rutas_propuestas
    )

    sin_referencia = sorted(
        todas_las_rutas - posibles_rutas
    )

    resumen = {
        "cantidad_capturas": len(evaluaciones),
        "cantidad_fotografias": len(todas_las_rutas),
        "capturas_con_propuesta": conteo_estados.get(
            "FOTOGRAFIA_PROPUESTA", 0
        ),
        "capturas_sin_fotografia": conteo_estados.get(
            "SIN_FOTOGRAFIA", 0
        ),
        "capturas_requieren_autorizacion_excepcional": sum(
            e["requiere_autorizacion_excepcional"]
            for e in evaluaciones
        ),
        "capturas_requieren_revision": sum(
            e["requiere_revision"]
            for e in evaluaciones
        ),
        "fotografias_con_propuesta": len(
            rutas_propuestas
        ),
        "fotografias_sin_propuesta": len(
            sin_propuesta
        ),
        "fotografias_sin_referencia": len(
            sin_referencia
        ),
        "fotografias_compartidas": len(
            referencias_compartidas
        ),
        "fotografias_con_solapamiento_potencial": len(
            solapamientos_potenciales
        ),
        "capturas_con_referencia_compartida": sum(
            e["referencia_compartida"]
            for e in evaluaciones
        ),
        "capturas_con_solapamiento_potencial": sum(
            e["solapamiento_potencial"]
            for e in evaluaciones
        ),
        "conteo_estados": conteo_estados
    }

    return {
        "estado": "EVALUACION_COMPLETADA",
        "checksum_zip": indice.get("checksum_zip"),
        "resumen": resumen,
        "evaluaciones": evaluaciones,
        "referencias_compartidas": referencias_compartidas,
        "solapamientos_potenciales": solapamientos_potenciales,
        "fotografias_sin_propuesta": sin_propuesta,
        "fotografias_sin_referencia": sin_referencia,
        "vinculaciones_confirmadas": False,
        "listo_para_importar": False,
        "datos_guardados": False
    }
