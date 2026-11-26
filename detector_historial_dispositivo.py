"""Detección histórica de importaciones del dispositivo.

Este módulo realiza consultas de diagnóstico.
No registra importaciones ni modifica SQLite.
"""

import re
import sqlite3
import unicodedata

from validador_pertenencia_dispositivo import (
    validar_usuario_dispositivo
)


PATRON_CHECKSUM_SHA256 = re.compile(
    r"[0-9a-f]{64}"
)


def validar_checksum_zip(checksum_zip):
    """Valida la representación canónica de SHA-256."""

    return (
        isinstance(checksum_zip, str)
        and PATRON_CHECKSUM_SHA256.fullmatch(
            checksum_zip
        ) is not None
    )


def _identificador_historico_valido(valor):
    """Comprueba la identidad de un registro histórico."""

    return (
        isinstance(valor, str)
        and bool(valor)
        and valor == valor.strip()
        and not any(
            unicodedata.category(caracter).startswith("C")
            for caracter in valor
        )
    )


def detectar_zip_previamente_importado(
    conexion,
    checksum_zip,
    usuario_id,
    vina_id,
    device_id
):
    """Consulta importaciones de la viña autorizada."""

    resultado = {
        "estado": "CONSULTA_HISTORICA_RECHAZADA",
        "consulta_completada": False,
        "contexto_autorizado": False,
        "checksum_zip": None,
        "vina_id": None,
        "device_id": None,
        "zip_previamente_importado": None,
        "importacion_existente": None,
        "bloqueo_reimportacion": True,
        "requiere_revision": True,
        "incidencias": [],
        "listo_para_importar": False,
        "datos_guardados": False
    }

    try:

        contexto = validar_usuario_dispositivo(
            conexion,
            usuario_id,
            vina_id,
            device_id
        )

    except sqlite3.Error:

        resultado["incidencias"].append({
            "nivel": "ERROR",
            "codigo": "ERROR_CONSULTA_AUTORIZACION",
            "mensaje": (
                "No fue posible verificar la autorización "
                "para consultar el historial."
            )
        })

        return resultado

    if contexto["valida"] is not True:

        resultado["incidencias"].append({
            "nivel": "ERROR",
            "codigo": "CONTEXTO_NO_AUTORIZADO",
            "mensaje": (
                "No existe autorización para consultar "
                "el historial solicitado."
            )
        })

        return resultado

    resultado.update({
        "contexto_autorizado": True,
        "vina_id": contexto["vina_id"],
        "device_id": contexto["device_id"]
    })

    if not validar_checksum_zip(checksum_zip):

        resultado["incidencias"].append({
            "nivel": "ERROR",
            "codigo": "CHECKSUM_ZIP_INVALIDO",
            "mensaje": (
                "El checksum debe ser un SHA-256 "
                "hexadecimal canónico de 64 caracteres."
            )
        })

        return resultado

    resultado["checksum_zip"] = checksum_zip

    try:

        registros = conexion.execute("""
            SELECT
                importacion_id,
                vina_id,
                checksum
            FROM importaciones_dispositivo
            WHERE vina_id = ?
              AND checksum = ?
            LIMIT 2
        """, (
            contexto["vina_id"],
            checksum_zip
        )).fetchall()

    except sqlite3.Error:

        resultado["incidencias"].append({
            "nivel": "ERROR",
            "codigo": "ERROR_CONSULTA_HISTORIAL",
            "mensaje": (
                "No fue posible completar la consulta "
                "del historial de importaciones."
            )
        })

        return resultado

    if len(registros) > 1:

        resultado["incidencias"].append({
            "nivel": "ERROR",
            "codigo": "HISTORIAL_IMPORTACION_AMBIGUO",
            "mensaje": (
                "El historial contiene más de una "
                "importación para el mismo checksum."
            )
        })

        return resultado

    if registros:

        registro = registros[0]

        if (
            not _identificador_historico_valido(
                registro[0]
            )
            or registro[1] != contexto["vina_id"]
            or registro[2] != checksum_zip
        ):

            resultado["incidencias"].append({
                "nivel": "ERROR",
                "codigo": "HISTORIAL_IMPORTACION_INCONSISTENTE",
                "mensaje": (
                    "La identidad de la importación "
                    "histórica no pudo verificarse."
                )
            })

            return resultado

        resultado.update({
            "estado": "ZIP_PREVIAMENTE_IMPORTADO",
            "consulta_completada": True,
            "zip_previamente_importado": True,
            "importacion_existente": {
                "importacion_id": registro[0]
            }
        })

        resultado["incidencias"].append({
            "nivel": "ERROR",
            "codigo": "ZIP_PREVIAMENTE_IMPORTADO",
            "mensaje": (
                "Este contenido ZIP ya fue registrado "
                "en la viña."
            )
        })

        return resultado

    resultado.update({
        "estado": "ZIP_SIN_IMPORTACION_PREVIA",
        "consulta_completada": True,
        "zip_previamente_importado": False,
        "bloqueo_reimportacion": False,
        "requiere_revision": False
    })

    return resultado
