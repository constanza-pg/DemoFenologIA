
"""Validación preliminar de pertenencia de capturas.

No registra usuarios, dispositivos, plantas ni capturas.
Utiliza exclusivamente la conexión proporcionada.
"""

import unicodedata
import math

from database import (
    verificar_permiso_mediciones
)


def _identificador_valido(valor):
    """Comprueba identificadores sin corregirlos."""

    return (
        isinstance(valor, str)
        and bool(valor)
        and valor == valor.strip()
        and not any(
            unicodedata.category(caracter).startswith("C")
            for caracter in valor
        )
    )


def validar_usuario_dispositivo(
    conexion,
    usuario_id,
    vina_id,
    device_id
):
    """Comprueba permisos y pertenencia del dispositivo."""

    incidencias = []

    def registrar(codigo, mensaje):

        incidencias.append({
            "nivel": "ERROR",
            "codigo": codigo,
            "mensaje": mensaje
        })

    usuario_autorizado = False
    dispositivo_autorizado = False

    if not (
        _identificador_valido(usuario_id)
        and _identificador_valido(vina_id)
    ):

        registrar(
            "IDENTIDAD_SESION_INVALIDA",
            "La identidad de la sesión no es válida."
        )

    else:

        try:

            permiso = verificar_permiso_mediciones(
                conexion,
                usuario_id,
                vina_id
            )

        except PermissionError:

            registrar(
                "USUARIO_NO_AUTORIZADO",
                "El usuario no tiene permisos para esta viña."
            )

        else:

            if permiso is True:

                usuario_autorizado = True

            else:

                registrar(
                    "USUARIO_NO_AUTORIZADO",
                    "No se confirmó la autorización del usuario."
                )

    # No consultar dispositivos si el usuario no está
    # autorizado para acceder a la viña.

    if usuario_autorizado:

        if not _identificador_valido(device_id):

            registrar(
                "DISPOSITIVO_NO_IDENTIFICADO",
                "Debe identificar explícitamente el dispositivo."
            )

        else:

            coincidencias = conexion.execute("""
                SELECT device_id
                FROM dispositivos
                WHERE device_id = ?
                  AND vina_id = ?
            """, (
                device_id,
                vina_id
            )).fetchall()

            if len(coincidencias) != 1:

                registrar(
                    "DISPOSITIVO_NO_AUTORIZADO",
                    "El dispositivo no está autorizado para esta viña."
                )

            elif coincidencias[0][0] != device_id:

                registrar(
                    "DISPOSITIVO_NO_AUTORIZADO",
                    "El identificador no coincide exactamente."
                )

            else:

                dispositivo_autorizado = True

    valida = (
        usuario_autorizado
        and dispositivo_autorizado
        and not incidencias
    )

    return {
        "estado": (
            "CONTEXTO_AUTORIZADO"
            if valida
            else "CONTEXTO_RECHAZADO"
        ),
        "valida": valida,
        "usuario_autorizado": usuario_autorizado,
        "dispositivo_autorizado": dispositivo_autorizado,
        "usuario_id": (
            usuario_id if valida else None
        ),
        "vina_id": (
            vina_id if valida else None
        ),
        "device_id": (
            device_id if valida else None
        ),
        "incidencias": incidencias,
        "requiere_revision": bool(incidencias),
        "listo_para_importar": False,
        "datos_guardados": False
    }



def _identificador_ausente(valor):
    """Distingue ausencia de caracteres inválidos."""

    return (
        valor is None
        or (
            isinstance(valor, str)
            and all(
                caracter == " "
                for caracter in valor
            )
        )
    )


def _representar_identificador_original(valor):
    """Representa valores no finitos sin perder su tipo."""

    if isinstance(valor, float):

        if math.isnan(valor):

            return {
                "tipo": "numero_no_finito",
                "valor": "NaN"
            }

        if math.isinf(valor):

            return {
                "tipo": "numero_no_finito",
                "valor": (
                    "+Infinity"
                    if valor > 0
                    else "-Infinity"
                )
            }

    if isinstance(valor, list):

        return [
            _representar_identificador_original(v)
            for v in valor
        ]

    if isinstance(valor, dict):

        return {
            k: _representar_identificador_original(v)
            for k, v in valor.items()
        }

    return valor


def validar_dispositivo_declarado(
    captura,
    device_id_autorizado
):
    """Compara el dispositivo del Excel con el seleccionado.

    No sustituye la autorización contra la base de datos.
    """

    if not isinstance(captura, dict):

        raise ValueError(
            "La captura debe ser un diccionario."
        )

    declarado = captura.get("device_id")

    incidencias = []

    ausente = _identificador_ausente(
        declarado
    )

    if not _identificador_valido(
        device_id_autorizado
    ):

        codigo = "DISPOSITIVO_AUTORIZADO_INVALIDO"
        mensaje = (
            "No existe un identificador de dispositivo válido."
        )

    elif ausente:

        codigo = None
        mensaje = None

    elif not _identificador_valido(declarado):

        codigo = "DISPOSITIVO_DECLARADO_INVALIDO"
        mensaje = (
            "El identificador del Excel no tiene un formato válido."
        )

    elif declarado != device_id_autorizado:

        codigo = "DISPOSITIVO_DECLARADO_NO_COINCIDE"
        mensaje = (
            "El dispositivo declarado no coincide "
            "con el seleccionado para la importación."
        )

    else:

        codigo = None
        mensaje = None

    if codigo is not None:

        incidencias.append({
            "nivel": "ERROR",
            "codigo": codigo,
            "mensaje": mensaje,
            "hoja_excel": captura.get("hoja_excel"),
            "fila_excel": captura.get("fila_excel"),
            "codigo_planta": captura.get("codigo_planta")
        })

    valida = not incidencias

    if not valida:

        estado = "DISPOSITIVO_DECLARADO_RECHAZADO"

    elif ausente:

        estado = "DISPOSITIVO_NO_DECLARADO"

    else:

        estado = "DISPOSITIVO_DECLARADO_COINCIDE"

    return {
        "estado": estado,
        "valida": valida,
        "hoja_excel": captura.get("hoja_excel"),
        "fila_excel": captura.get("fila_excel"),
        "codigo_planta": captura.get("codigo_planta"),
        "device_id_original": (
            _representar_identificador_original(
                declarado
            )
        ),
        "device_id_propuesto": (
            device_id_autorizado
            if valida
            else None
        ),
        "origen_identificador": (
            (
                "SELECCION_EXPLICITA"
                if ausente
                else "EXCEL_Y_SELECCION_EXPLICITA"
            )
            if valida
            else None
        ),
        "coincidencia_confirmada": (
            valida and not ausente
        ),
        "requiere_revision": bool(incidencias),
        "incidencias": incidencias,
        "listo_para_importar": False,
        "datos_guardados": False
    }


def validar_planta_captura(
    conexion,
    captura,
    usuario_id,
    vina_id,
    device_id
):
    """Resuelve una planta dentro del contexto autorizado.

    No crea plantas ni modifica registros existentes.
    """

    if not isinstance(captura, dict):

        raise ValueError(
            "La captura debe ser un diccionario."
        )

    contexto = validar_usuario_dispositivo(
        conexion,
        usuario_id,
        vina_id,
        device_id
    )

    codigo_planta = captura.get(
        "codigo_planta"
    )

    incidencias = []
    plant_id = None

    def registrar(codigo, mensaje):

        incidencias.append({
            "nivel": "ERROR",
            "codigo": codigo,
            "mensaje": mensaje,
            "hoja_excel": captura.get("hoja_excel"),
            "fila_excel": captura.get("fila_excel"),
            "codigo_planta": (
                codigo_planta
                if isinstance(codigo_planta, str)
                else None
            )
        })

    if contexto["valida"] is not True:

        registrar(
            "CONTEXTO_NO_AUTORIZADO",
            "No se autorizó el usuario y dispositivo."
        )

    else:

        declarado = validar_dispositivo_declarado(
            captura,
            device_id
        )

        if declarado["valida"] is not True:

            incidencias.extend(
                declarado["incidencias"]
            )

        elif _identificador_ausente(
            codigo_planta
        ):

            registrar(
                "CODIGO_PLANTA_AUSENTE",
                "La captura no contiene código de planta."
            )

        elif not _identificador_valido(
            codigo_planta
        ):

            registrar(
                "CODIGO_PLANTA_INVALIDO",
                "El código de planta tiene un formato inválido."
            )

        else:

            coincidencias = conexion.execute("""
                SELECT id, codigo_planta, vina_id
                FROM plantas
                WHERE vina_id = ?
                  AND codigo_planta = ?
            """, (
                vina_id,
                codigo_planta
            )).fetchall()

            if not coincidencias:

                registrar(
                    "PLANTA_NO_AUTORIZADA",
                    "La planta no está registrada "
                    "en la viña autorizada."
                )

            elif len(coincidencias) != 1:

                registrar(
                    "CODIGO_PLANTA_AMBIGUO",
                    "El código identifica múltiples plantas."
                )

            else:

                identificador, codigo_bd, vina_bd = (
                    coincidencias[0]
                )

                if (
                    codigo_bd != codigo_planta
                    or vina_bd != vina_id
                    or not _identificador_valido(
                        identificador
                    )
                ):

                    registrar(
                        "IDENTIDAD_PLANTA_INCONSISTENTE",
                        "No se confirmó la identidad exacta "
                        "de la planta."
                    )

                else:

                    plant_id = identificador

    valida = (
        plant_id is not None
        and not incidencias
    )

    return {
        "estado": (
            "PLANTA_VALIDADA"
            if valida
            else "PLANTA_RECHAZADA"
        ),
        "valida": valida,
        "contexto_autorizado": contexto["valida"],
        "hoja_excel": captura.get("hoja_excel"),
        "fila_excel": captura.get("fila_excel"),
        "codigo_planta": (
            codigo_planta
            if isinstance(codigo_planta, str)
            else None
        ),
        "tipo_codigo_original": type(
            codigo_planta
        ).__name__,
        "plant_id": plant_id if valida else None,
        "vina_id": vina_id if valida else None,
        "device_id": device_id if valida else None,
        "incidencias": incidencias,
        "requiere_revision": bool(incidencias),
        "listo_para_importar": False,
        "datos_guardados": False
    }
