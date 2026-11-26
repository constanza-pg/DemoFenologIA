"""Consulta autorizada del historial de capturas.

Infraestructura provisional de diagnóstico.
No realiza escrituras ni confirma duplicados.
"""

import sqlite3
import unicodedata

from validador_pertenencia_dispositivo import (
    validar_planta_captura
)

from temporalidad_historica_dispositivo import (
    recuperar_intervalo_historico,
    MAX_BYTES_DATOS_JSON
)


MAX_REGISTROS_HISTORICOS_PLANTA = 10000

MAX_BYTES_HISTORIAL_PLANTA = 32 * 1024 * 1024


def _identificador_valido(valor):

    return (
        isinstance(valor, str)
        and bool(valor)
        and valor == valor.strip()
        and not any(
            unicodedata.category(c).startswith("C")
            for c in valor
        )
    )


def consultar_historial_captura(
    conexion,
    captura,
    usuario_id,
    vina_id,
    device_id
):

    resultado = {
        "estado": "CONSULTA_CAPTURAS_RECHAZADA",
        "consulta_completada": False,
        "contexto_autorizado": False,
        "vina_id": None,
        "plant_id": None,
        "device_id": None,
        "cantidad_registros": None,
        "capturas_historicas": [],
        "bloqueo_por_historial": True,
        "requiere_revision": True,
        "incidencias": [],
        "listo_para_importar": False,
        "datos_guardados": False
    }

    def rechazar(codigo, mensaje):

        resultado["incidencias"].append({
            "nivel": "ERROR",
            "codigo": codigo,
            "mensaje": mensaje
        })

        return resultado

    if not isinstance(captura, dict):

        return rechazar(
            "CAPTURA_INVALIDA",
            "La captura no tiene un formato válido."
        )

    try:

        pertenencia = validar_planta_captura(
            conexion,
            captura,
            usuario_id,
            vina_id,
            device_id
        )

    except sqlite3.Error:

        return rechazar(
            "ERROR_CONSULTA_AUTORIZACION",
            "No fue posible verificar la pertenencia."
        )

    if pertenencia["valida"] is not True:

        return rechazar(
            "CAPTURA_NO_AUTORIZADA",
            "No existe autorización para consultar "
            "el historial solicitado."
        )

    resultado.update({
        "contexto_autorizado": True,
        "vina_id": pertenencia["vina_id"],
        "plant_id": pertenencia["plant_id"],
        "device_id": pertenencia["device_id"]
    })

    historicas = []
    identidades = set()
    bytes_acumulados = 0
    cursor = None

    try:

        cursor = conexion.execute("""
            SELECT
                c.captura_id,
                c.importacion_id,
                c.plant_id,
                c.device_id,
                c.fecha_hora,
                CASE
                    WHEN length(
                        CAST(c.datos_json AS BLOB)
                    ) <= ?
                    THEN c.datos_json
                    ELSE NULL
                END,
                i.vina_id,
                i.device_id,
                p.vina_id,
                d.vina_id,
                length(
                    CAST(c.datos_json AS BLOB)
                )
            FROM capturas_dispositivo c
            LEFT JOIN importaciones_dispositivo i
                ON i.importacion_id = c.importacion_id
            LEFT JOIN plantas p
                ON p.id = c.plant_id
            LEFT JOIN dispositivos d
                ON d.device_id = c.device_id
            WHERE c.plant_id = ?
            LIMIT ?
        """, (
            MAX_BYTES_DATOS_JSON,
            pertenencia["plant_id"],
            MAX_REGISTROS_HISTORICOS_PLANTA + 1
        ))

        for registro in cursor:

            if len(historicas) >= (
                MAX_REGISTROS_HISTORICOS_PLANTA
            ):

                return rechazar(
                    "LIMITE_HISTORIAL_SUPERADO",
                    "El historial supera el límite "
                    "de registros permitido."
                )

            (
                captura_id,
                importacion_id,
                plant_id,
                dispositivo_historico,
                fecha_hora,
                datos_json,
                vina_importacion,
                dispositivo_importacion,
                vina_planta,
                vina_dispositivo,
                cantidad_bytes
            ) = registro

            if (
                vina_importacion != pertenencia["vina_id"]
                or vina_planta != pertenencia["vina_id"]
                or plant_id != pertenencia["plant_id"]
                or dispositivo_historico
                != dispositivo_importacion
            ):

                return rechazar(
                    "RELACION_HISTORICA_INCONSISTENTE",
                    "No fue posible verificar las "
                    "relaciones del historial."
                )

            if vina_dispositivo != pertenencia["vina_id"]:

                return rechazar(
                    "PROPIEDAD_HISTORICA_NO_RESUELTA",
                    "La pertenencia actual de un "
                    "dispositivo histórico requiere revisión."
                )

            if (
                not all(
                    _identificador_valido(valor)
                    for valor in (
                        captura_id,
                        importacion_id,
                        dispositivo_historico
                    )
                )
                or captura_id in identidades
            ):

                return rechazar(
                    "IDENTIDAD_HISTORICA_INCONSISTENTE",
                    "No fue posible verificar una "
                    "identidad histórica."
                )

            if (
                type(cantidad_bytes) is not int
                or cantidad_bytes > MAX_BYTES_DATOS_JSON
            ):

                return rechazar(
                    "DATOS_HISTORICOS_INVALIDOS",
                    "Los datos históricos no cumplen "
                    "los límites establecidos."
                )

            bytes_acumulados += cantidad_bytes

            if bytes_acumulados > MAX_BYTES_HISTORIAL_PLANTA:

                return rechazar(
                    "LIMITE_BYTES_HISTORIAL_SUPERADO",
                    "El historial supera el límite "
                    "de datos permitido."
                )

            temporalidad = recuperar_intervalo_historico(
                fecha_hora,
                datos_json
            )

            if temporalidad["valida"] is not True:

                return rechazar(
                    "TEMPORALIDAD_HISTORICA_NO_VERIFICADA",
                    "Existe un registro cuya precisión "
                    "temporal requiere revisión."
                )

            identidades.add(captura_id)

            historicas.append({
                "captura_id": captura_id,
                "importacion_id": importacion_id,
                "plant_id": plant_id,
                "vina_id": pertenencia["vina_id"],
                "device_id": dispositivo_historico,
                "fecha_hora": fecha_hora,
                "intervalo": temporalidad["intervalo"]
            })

    except sqlite3.Error:

        return rechazar(
            "ERROR_CONSULTA_HISTORIAL_CAPTURAS",
            "No fue posible consultar el historial."
        )

    finally:

        if cursor is not None:
            cursor.close()

    historicas.sort(
        key=lambda registro: (
            registro["intervalo"]["inicio_microsegundos"],
            registro["intervalo"]["fin_exclusivo_microsegundos"],
            registro["captura_id"]
        )
    )

    resultado.update({
        "estado": "HISTORIAL_CAPTURAS_RECUPERADO",
        "consulta_completada": True,
        "cantidad_registros": len(historicas),
        "capturas_historicas": historicas,
        "bloqueo_por_historial": False,
        "requiere_revision": False
    })

    return resultado
