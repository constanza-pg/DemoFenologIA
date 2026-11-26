"""Conservación de la precisión temporal histórica.

Contrato provisional para capturas del dispositivo.
No realiza consultas ni escrituras en SQLite.
"""

import json
import math

from detector_duplicados_dispositivo import (
    construir_intervalo_temporal
)


CLAVE_TEMPORALIDAD = "temporalidad_v1"

MAX_BYTES_DATOS_JSON = 1024 * 1024


def _objeto_json_sin_duplicados(pares):

    resultado = {}

    for clave, valor in pares:

        if clave in resultado:
            raise ValueError("Clave JSON duplicada.")

        resultado[clave] = valor

    return resultado


def _rechazar_constante_json(valor):

    raise ValueError("Constante JSON no permitida.")


def _interpretar_decimal_json(valor):

    numero = float(valor)

    if not math.isfinite(numero):

        raise ValueError(
            "Número JSON fuera del rango finito."
        )

    return numero


def _resultado_temporal(estado, codigo=None):

    return {
        "estado": estado,
        "valida": False,
        "fecha_hora": None,
        "metadatos_temporales": None,
        "intervalo": None,
        "requiere_revision": True,
        "incidencias": (
            [{
                "nivel": "ERROR",
                "codigo": codigo,
                "mensaje": (
                    "No fue posible verificar "
                    "la precisión temporal."
                )
            }]
            if codigo is not None
            else []
        ),
        "listo_para_importar": False,
        "datos_guardados": False
    }


def preparar_metadatos_temporales(captura):

    resultado = _resultado_temporal(
        "METADATOS_TEMPORALES_RECHAZADOS",
        "CAPTURA_TEMPORAL_INVALIDA"
    )

    if not isinstance(captura, dict):
        return resultado

    intervalo = construir_intervalo_temporal(
        captura
    )

    if intervalo["valida"] is not True:
        return resultado

    fecha_hora = intervalo[
        "fecha_hora_normalizada"
    ]

    precision = intervalo[
        "precision_temporal"
    ]

    digitos = intervalo[
        "digitos_fraccion"
    ]

    if precision == "FRACCION_SEGUNDO":

        fecha_original = fecha_hora.split(
            ".", 1
        )[0] + "." + fecha_hora.split(
            ".", 1
        )[1][:digitos]

    else:

        fecha_original = fecha_hora

    metadatos = {
        "version": 1,
        "fecha_hora_representativa": fecha_original,
        "precision_temporal": precision,
        "digitos_fraccion": digitos,
        "zona_horaria": None
    }

    resultado.update({
        "estado": "METADATOS_TEMPORALES_PREPARADOS",
        "valida": True,
        "fecha_hora": fecha_hora,
        "metadatos_temporales": metadatos,
        "intervalo": intervalo,
        "requiere_revision": False,
        "incidencias": []
    })

    return resultado


def recuperar_intervalo_historico(
    fecha_hora,
    datos_json
):

    def rechazar(codigo):

        return _resultado_temporal(
            "INTERVALO_HISTORICO_RECHAZADO",
            codigo
        )

    if not isinstance(fecha_hora, str):

        return rechazar(
            "FECHA_HISTORICA_INVALIDA"
        )

    if not isinstance(datos_json, str):

        return rechazar(
            "DATOS_JSON_INVALIDOS"
        )

    if len(datos_json) > MAX_BYTES_DATOS_JSON:

        return rechazar(
            "LIMITE_DATOS_JSON_SUPERADO"
        )

    try:

        if len(datos_json.encode("utf-8")) > (
            MAX_BYTES_DATOS_JSON
        ):

            return rechazar(
                "LIMITE_DATOS_JSON_SUPERADO"
            )

        datos = json.loads(
            datos_json,
            object_pairs_hook=(
                _objeto_json_sin_duplicados
            ),
            parse_constant=(
                _rechazar_constante_json
            ),
            parse_float=(
                _interpretar_decimal_json
            )
        )

    except (
        ValueError,
        RecursionError,
        UnicodeError
    ):

        return rechazar(
            "DATOS_JSON_INVALIDOS"
        )

    if not isinstance(datos, dict):

        return rechazar(
            "DATOS_JSON_INVALIDOS"
        )

    if CLAVE_TEMPORALIDAD not in datos:

        return rechazar(
            "PRECISION_HISTORICA_NO_DOCUMENTADA"
        )

    metadatos = datos[CLAVE_TEMPORALIDAD]

    if not isinstance(metadatos, dict):

        return rechazar(
            "METADATOS_TEMPORALES_INVALIDOS"
        )

    campos = {
        "version",
        "fecha_hora_representativa",
        "precision_temporal",
        "digitos_fraccion",
        "zona_horaria"
    }

    if set(metadatos) != campos:

        return rechazar(
            "METADATOS_TEMPORALES_INVALIDOS"
        )

    if (
        type(metadatos["version"]) is not int
        or metadatos["version"] != 1
    ):

        return rechazar(
            "VERSION_TEMPORAL_NO_COMPATIBLE"
        )

    if metadatos["zona_horaria"] is not None:

        return rechazar(
            "ZONA_HORARIA_NO_COMPATIBLE"
        )

    precision = metadatos["precision_temporal"]
    digitos = metadatos["digitos_fraccion"]

    if precision == "FRACCION_SEGUNDO":

        if (
            type(digitos) is not int
            or not 1 <= digitos <= 6
        ):

            return rechazar(
                "PRECISION_HISTORICA_INCONSISTENTE"
            )

    elif precision in ("MINUTO", "SEGUNDO"):

        if digitos is not None:

            return rechazar(
                "PRECISION_HISTORICA_INCONSISTENTE"
            )

    else:

        return rechazar(
            "PRECISION_HISTORICA_INCONSISTENTE"
        )

    representativa = metadatos[
        "fecha_hora_representativa"
    ]

    if not isinstance(representativa, str):

        return rechazar(
            "FECHA_HISTORICA_INVALIDA"
        )

    reconstruccion = preparar_metadatos_temporales({
        "fecha_hora": representativa
    })

    if reconstruccion["valida"] is not True:

        return rechazar(
            "FECHA_HISTORICA_INVALIDA"
        )

    if (
        reconstruccion["fecha_hora"] != fecha_hora
        or reconstruccion["metadatos_temporales"]
        != metadatos
    ):

        return rechazar(
            "PRECISION_HISTORICA_INCONSISTENTE"
        )

    resultado = _resultado_temporal(
        "INTERVALO_HISTORICO_RECUPERADO"
    )

    resultado.update({
        "valida": True,
        "fecha_hora": fecha_hora,
        "metadatos_temporales": metadatos,
        "intervalo": reconstruccion["intervalo"],
        "requiere_revision": False
    })

    return resultado
