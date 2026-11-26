"""Reconocimiento preliminar de columnas del dispositivo."""

import re
import unicodedata


ALIAS_COLUMNAS = {

    "codigo_planta": (
        "planta",
        "id planta",
        "codigo planta",
        "codigo de planta",
        "identificador planta",
        "plant id",
        "plant code"
    ),

    "fecha": (
        "fecha",
        "date",
        "fecha captura",
        "fecha de captura"
    ),

    "hora": (
        "hora",
        "time",
        "hora captura",
        "hora de captura"
    ),

    "fecha_hora": (
        "fecha hora",
        "fecha y hora",
        "timestamp",
        "datetime",
        "date time"
    ),

    "temperatura_ambiental": (
        "temperatura",
        "temp",
        "temperatura ambiental",
        "temperatura aire",
        "temperatura c",
        "temp c",
        "temperature",
        "air temperature"
    ),

    "humedad_ambiental": (
        "humedad",
        "hr",
        "humedad ambiental",
        "humedad relativa",
        "humedad aire",
        "humidity",
        "relative humidity",
        "rh"
    ),

    "tiene_fotografia": (
        "tiene foto",
        "tiene fotografia",
        "con foto",
        "foto capturada",
        "fotografia capturada",
        "photo captured",
        "has photo",
        "has image"
    ),

    "archivo_fotografia": (
        "nombre foto",
        "nombre fotografia",
        "archivo foto",
        "archivo fotografia",
        "archivo jpg",
        "photo filename",
        "image filename",
        "image file"
    ),

    "device_id": (
        "dispositivo",
        "id dispositivo",
        "codigo dispositivo",
        "device id",
        "device"
    ),

    "latitud": (
        "latitud",
        "latitude",
        "lat"
    ),

    "longitud": (
        "longitud",
        "longitude",
        "lon",
        "lng"
    )
}


ALIAS_AMBIGUOS = {

    "foto": (
        "tiene_fotografia",
        "archivo_fotografia"
    ),

    "fotografia": (
        "tiene_fotografia",
        "archivo_fotografia"
    ),

    "imagen": (
        "tiene_fotografia",
        "archivo_fotografia"
    ),

    "img": (
        "tiene_fotografia",
        "archivo_fotografia"
    ),

    "photo": (
        "tiene_fotografia",
        "archivo_fotografia"
    ),

    "image": (
        "tiene_fotografia",
        "archivo_fotografia"
    ),

    "id": (
        "codigo_planta",
        "device_id"
    ),

    "codigo": (
        "codigo_planta",
        "device_id"
    )
}


def normalizar_encabezado(valor):
    """Normaliza texto sin modificar el encabezado original."""

    if not isinstance(valor, str):
        return ""

    texto = unicodedata.normalize(
        "NFKD", valor
    )

    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )

    texto = texto.casefold()

    texto = re.sub(
        r"[^a-z0-9]+",
        " ",
        texto
    )

    return " ".join(texto.split())


def reconocer_encabezado(valor):
    """Identifica posibles equivalencias de una columna."""

    normalizado = normalizar_encabezado(valor)

    candidatos = set()

    for campo, alternativas in ALIAS_COLUMNAS.items():

        nombres = {
            normalizar_encabezado(campo)
        }

        nombres.update(
            normalizar_encabezado(alias)
            for alias in alternativas
        )

        if normalizado in nombres:

            candidatos.add(campo)

    candidatos.update(
        ALIAS_AMBIGUOS.get(
            normalizado, ()
        )
    )

    candidatos = sorted(candidatos)

    if not normalizado:

        estado = "VACIO"

    elif len(candidatos) == 1:

        estado = "RECONOCIDO"

    elif len(candidatos) > 1:

        estado = "AMBIGUO"

    else:

        estado = "DESCONOCIDO"

    return {
        "original": valor,
        "normalizado": normalizado,
        "estado": estado,
        "campo_sugerido": (
            candidatos[0]
            if estado == "RECONOCIDO"
            else None
        ),
        "candidatos": candidatos
    }


def reconocer_columnas(celdas):
    """Reconoce columnas conservando su posición original."""

    resultado = []
    posiciones = set()

    for celda in celdas:

        posicion = celda["columna"]

        if (
            not isinstance(posicion, int)
            or isinstance(posicion, bool)
            or posicion < 1
            or posicion in posiciones
        ):
            raise ValueError(
                "Posición de columna inválida o duplicada."
            )

        posiciones.add(posicion)

        detalle = reconocer_encabezado(
            celda["valor"]
        )

        detalle["columna"] = posicion

        resultado.append(detalle)

    campos = {}

    for detalle in resultado:

        campo = detalle["campo_sugerido"]

        if campo is not None:

            campos.setdefault(
                campo, []
            ).append(detalle)

    for campo, coincidencias in campos.items():

        if len(coincidencias) > 1:

            for detalle in coincidencias:

                detalle["estado"] = "CONFLICTO"
                detalle["campo_sugerido"] = None

    return sorted(
        resultado,
        key=lambda dato: dato["columna"]
    )



# Criterios preliminares de reconocimiento.
MIN_CAMPOS_ENCABEZADO = 2
MAX_CANDIDATOS_POR_HOJA = 5


def evaluar_fila_encabezado(fila):
    """Evalúa una fila como posible encabezado."""

    columnas = reconocer_columnas(
        fila["celdas"]
    )

    reconocidas = [
        c for c in columnas
        if c["estado"] == "RECONOCIDO"
    ]

    ambiguas = [
        c for c in columnas
        if c["estado"] == "AMBIGUO"
    ]

    conflictos = [
        c for c in columnas
        if c["estado"] == "CONFLICTO"
    ]

    desconocidas = [
        c for c in columnas
        if c["estado"] == "DESCONOCIDO"
    ]

    campos = {
        c["campo_sugerido"]
        for c in reconocidas
    }

    posibles_campos = set(campos)

    for columna in ambiguas + conflictos:

        posibles_campos.update(
            columna["candidatos"]
        )

    cantidad_texto = sum(
        isinstance(c["original"], str)
        and bool(c["original"].strip())
        for c in columnas
    )

    proporcion_texto = (
        cantidad_texto / len(columnas)
        if columnas else 0
    )

    tiene_planta = (
        "codigo_planta" in posibles_campos
    )

    tiene_tiempo = bool(
        posibles_campos.intersection({
            "fecha",
            "hora",
            "fecha_hora"
        })
    )

    coincidencias = (
        len(reconocidas)
        + len(ambiguas)
    )

    es_candidato = (
        coincidencias >= MIN_CAMPOS_ENCABEZADO
        and proporcion_texto >= 0.75
        and (tiene_planta or tiene_tiempo)
    )

    puntuacion = (
        len(reconocidas) * 3
        + len(ambiguas)
        + int(tiene_planta) * 3
        + int(tiene_tiempo) * 2
        - len(conflictos) * 2
    )

    return {
        "fila": fila["fila"],
        "es_candidato": es_candidato,
        "puntuacion": puntuacion,
        "proporcion_texto": proporcion_texto,
        "reconocidas": len(reconocidas),
        "ambiguas": len(ambiguas),
        "conflictos": len(conflictos),
        "desconocidas": len(desconocidas),
        "campos_reconocidos": sorted(campos),
        "columnas": columnas,
        "requiere_confirmacion": True
    }


def detectar_encabezados_excel(inspeccion):
    """Sugiere encabezados sin seleccionar uno definitivamente."""

    resultado = {
        "hojas": [],
        "cantidad_candidatos": 0,
        "seleccion_confirmada": False
    }

    for hoja in inspeccion["hojas"]:

        candidatos = []

        if not hoja["vacia"]:

            for fila in hoja["vista_previa"]:

                evaluacion = evaluar_fila_encabezado(
                    fila
                )

                if evaluacion["es_candidato"]:

                    candidatos.append(evaluacion)

        candidatos.sort(
            key=lambda c: (
                -c["puntuacion"],
                c["fila"]
            )
        )

        cantidad_total = len(candidatos)

        candidatos = candidatos[
            :MAX_CANDIDATOS_POR_HOJA
        ]

        resultado["hojas"].append({
            "nombre": hoja["nombre"],
            "visibilidad": hoja["visibilidad"],
            "vacia": hoja["vacia"],
            "cantidad_candidatos": cantidad_total,
            "candidatos": candidatos,
            "requiere_confirmacion": True
        })

        resultado["cantidad_candidatos"] += (
            cantidad_total
        )

    return resultado



MIN_VALORES_SUGERENCIA = 2


def clasificar_valor_fotografia(valor):
    """Clasifica un valor sin confirmar su significado."""

    if valor is None:
        return "VACIO"

    if isinstance(valor, bool):
        return "INDICADOR"

    if isinstance(valor, (int, float)):

        if valor in (0, 1):
            return "INDICADOR"

        return "DESCONOCIDO"

    if not isinstance(valor, str):
        return "DESCONOCIDO"

    texto = valor.strip()

    if not texto:
        return "VACIO"

    normalizado = normalizar_encabezado(texto)

    indicadores = {
        "si", "no",
        "true", "false",
        "yes",
        "1", "0"
    }

    if normalizado in indicadores:
        return "INDICADOR"

    if texto.casefold().endswith(
        (".jpg", ".jpeg")
    ):
        return "ARCHIVO_JPEG"

    return "DESCONOCIDO"


def analizar_columna_fotografia(valores):
    """Sugiere el significado de una columna de fotografías."""

    conteo = {
        "VACIO": 0,
        "INDICADOR": 0,
        "ARCHIVO_JPEG": 0,
        "DESCONOCIDO": 0
    }

    for valor in valores:

        categoria = clasificar_valor_fotografia(
            valor
        )

        conteo[categoria] += 1

    cantidad_util = (
        conteo["INDICADOR"]
        + conteo["ARCHIVO_JPEG"]
        + conteo["DESCONOCIDO"]
    )

    sugerencia = None

    if cantidad_util < MIN_VALORES_SUGERENCIA:

        estado = "INFORMACION_INSUFICIENTE"

    elif (
        conteo["INDICADOR"] > 0
        and conteo["ARCHIVO_JPEG"] > 0
    ):

        estado = "VALORES_MIXTOS"

    elif conteo["DESCONOCIDO"] > 0:

        estado = "VALORES_NO_RECONOCIDOS"

    elif conteo["INDICADOR"] == cantidad_util:

        estado = "SUGERENCIA_DISPONIBLE"
        sugerencia = "tiene_fotografia"

    elif conteo["ARCHIVO_JPEG"] == cantidad_util:

        estado = "SUGERENCIA_DISPONIBLE"
        sugerencia = "archivo_fotografia"

    else:

        estado = "SIN_SUGERENCIA"

    return {
        "estado": estado,
        "campo_sugerido": sugerencia,
        "conteo": conteo,
        "cantidad_valores": cantidad_util,
        "requiere_confirmacion": True
    }


def sugerir_columnas_ambiguas(
    hoja,
    candidato
):
    """Analiza valores posteriores al posible encabezado."""

    resultado = []

    fila_encabezado = candidato["fila"]

    filas_datos = [
        fila
        for fila in hoja["vista_previa"]
        if fila["fila"] > fila_encabezado
    ]

    for columna in candidato["columnas"]:

        if columna["estado"] != "AMBIGUO":
            continue

        posicion = columna["columna"]

        valores = []

        for fila in filas_datos:

            valor = next(
                (
                    celda["valor"]
                    for celda in fila["celdas"]
                    if celda["columna"] == posicion
                ),
                None
            )

            valores.append(valor)

        posibles = set(
            columna["candidatos"]
        )

        if posibles == {
            "tiene_fotografia",
            "archivo_fotografia"
        }:

            analisis = analizar_columna_fotografia(
                valores
            )

        else:

            analisis = {
                "estado": "REQUIERE_CONTEXTO",
                "campo_sugerido": None,
                "cantidad_valores": sum(
                    valor is not None
                    and (
                        not isinstance(valor, str)
                        or bool(valor.strip())
                    )
                    for valor in valores
                ),
                "requiere_confirmacion": True
            }

        resultado.append({
            "columna": posicion,
            "encabezado": columna["original"],
            "candidatos": columna["candidatos"],
            "valores_muestra": valores,
            **analisis
        })

    return {
        "hoja": hoja["nombre"],
        "fila_encabezado": fila_encabezado,
        "columnas_ambiguas": resultado,
        "filas_analizadas": len(filas_datos),
        "seleccion_confirmada": False
    }
