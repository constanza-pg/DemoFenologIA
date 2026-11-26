"""Comparación temporal de capturas nuevas e históricas.

Infraestructura provisional de diagnóstico.
No confirma duplicados ni realiza escrituras.
"""

from datetime import datetime


def _intervalo_valido(intervalo):
    """Comprueba la coherencia de un intervalo temporal."""

    if not isinstance(intervalo, dict):
        return False

    if intervalo.get("valida") is not True:
        return False

    if (
        "zona_horaria" not in intervalo
        or intervalo["zona_horaria"] is not None
    ):
        return False

    inicio = intervalo.get("inicio_microsegundos")
    fin = intervalo.get("fin_exclusivo_microsegundos")
    duracion = intervalo.get("duracion_microsegundos")

    if not all(
        type(valor) is int
        for valor in (inicio, fin, duracion)
    ):
        return False

    if inicio < 0 or fin <= inicio:
        return False

    if duracion != fin - inicio:
        return False

    precision = intervalo.get("precision_temporal")
    digitos = intervalo.get("digitos_fraccion")

    if precision == "MINUTO":

        esperada = 60000000

        if digitos is not None:
            return False

    elif precision == "SEGUNDO":

        esperada = 1000000

        if digitos is not None:
            return False

    elif precision == "FRACCION_SEGUNDO":

        if type(digitos) is not int:
            return False

        if not 1 <= digitos <= 6:
            return False

        esperada = 10 ** (6 - digitos)

    else:

        return False

    if duracion != esperada:
        return False

    if inicio % esperada != 0:
        return False

    fecha = intervalo.get("fecha_hora_normalizada")

    if not isinstance(fecha, str):
        return False

    try:

        instante = datetime.fromisoformat(fecha)

    except (ValueError, OverflowError):

        return False

    if instante.tzinfo is not None:
        return False

    inicio_esperado = (
        (
            (
                (instante.toordinal() - 1) * 24
                + instante.hour
            ) * 60
            + instante.minute
        ) * 60
        + instante.second
    ) * 1000000 + instante.microsecond

    return inicio == inicio_esperado


def comparar_intervalos_historicos(
    intervalo_nuevo,
    intervalo_historico
):
    """Compara dos intervalos sin confirmar duplicados."""

    resultado = {
        "estado": "COMPARACION_HISTORICA_NO_VALIDA",
        "comparables": False,
        "coincidencia_exacta": None,
        "existe_solapamiento": None,
        "duracion_solapamiento_microsegundos": None,
        "requiere_revision": True,
        "incidencias": [],
        "duplicado_confirmado": False,
        "listo_para_importar": False,
        "datos_guardados": False
    }

    if not _intervalo_valido(intervalo_nuevo):

        resultado["incidencias"].append({
            "nivel": "ERROR",
            "codigo": "INTERVALO_NUEVO_INVALIDO",
            "mensaje": (
                "No fue posible verificar "
                "el intervalo de la captura nueva."
            )
        })

    if not _intervalo_valido(intervalo_historico):

        resultado["incidencias"].append({
            "nivel": "ERROR",
            "codigo": "INTERVALO_HISTORICO_INVALIDO",
            "mensaje": (
                "No fue posible verificar "
                "el intervalo de la captura histórica."
            )
        })

    if resultado["incidencias"]:
        return resultado

    inicio_nuevo = intervalo_nuevo[
        "inicio_microsegundos"
    ]

    fin_nuevo = intervalo_nuevo[
        "fin_exclusivo_microsegundos"
    ]

    inicio_historico = intervalo_historico[
        "inicio_microsegundos"
    ]

    fin_historico = intervalo_historico[
        "fin_exclusivo_microsegundos"
    ]

    exacta = (
        inicio_nuevo == inicio_historico
        and fin_nuevo == fin_historico
    )

    duracion_solapamiento = max(
        0,
        min(fin_nuevo, fin_historico)
        - max(inicio_nuevo, inicio_historico)
    )

    solapamiento = duracion_solapamiento > 0

    if exacta:

        estado = "COINCIDENCIA_TEMPORAL_EXACTA"

    elif solapamiento:

        estado = "SOLAPAMIENTO_TEMPORAL"

    else:

        estado = "INTERVALOS_INDEPENDIENTES"

    resultado.update({
        "estado": estado,
        "comparables": True,
        "coincidencia_exacta": exacta,
        "existe_solapamiento": solapamiento,
        "duracion_solapamiento_microsegundos":
            duracion_solapamiento,
        "requiere_revision": solapamiento
    })

    return resultado


import sqlite3

from detector_duplicados_dispositivo import (
    preparar_captura_para_comparacion
)

from consulta_historial_capturas_dispositivo import (
    consultar_historial_captura,
    MAX_REGISTROS_HISTORICOS_PLANTA
)


def comparar_captura_con_historial(
    conexion,
    captura,
    usuario_id,
    vina_id,
    device_id
):
    """Compara una captura con su historial autorizado.

    No confirma duplicados ni realiza escrituras.
    No autoriza importaciones.
    """

    resultado = {
        "estado": "COMPARACION_HISTORICA_RECHAZADA",
        "comparacion_completada": False,
        "contexto_autorizado": False,
        "captura_comparable": False,
        "vina_id": None,
        "plant_id": None,
        "device_id": None,
        "hoja_excel": None,
        "fila_excel": None,
        "codigo_planta": None,
        "intervalo_nuevo": None,
        "cantidad_registros_historicos": None,
        "cantidad_coincidencias": None,
        "coincidencias": [],
        "conteo_coincidencias": None,
        "independiente_del_historial": None,
        "bloqueo_por_historial": True,
        "requiere_revision": True,
        "incidencias": [],
        "duplicados_confirmados": 0,
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

    hoja = captura.get("hoja_excel")
    fila = captura.get("fila_excel")

    if (
        not isinstance(hoja, str)
        or not hoja.strip()
        or type(fila) is not int
        or fila < 1
    ):

        return rechazar(
            "TRAZABILIDAD_CAPTURA_INVALIDA",
            "La referencia de origen de la captura "
            "no pudo verificarse."
        )

    resultado["hoja_excel"] = hoja
    resultado["fila_excel"] = fila

    try:

        preparada = preparar_captura_para_comparacion(
            conexion,
            captura,
            usuario_id,
            vina_id,
            device_id
        )

    except sqlite3.Error:

        return rechazar(
            "ERROR_PREPARACION_CAPTURA",
            "No fue posible verificar la captura."
        )

    if preparada["comparable"] is not True:

        resultado["incidencias"].extend(
            preparada["incidencias"]
        )

        return rechazar(
            "CAPTURA_NO_COMPARABLE",
            "La captura nueva requiere revisión."
        )

    intervalo_nuevo = preparada["intervalo"]

    if not _intervalo_valido(intervalo_nuevo):

        return rechazar(
            "INTERVALO_NUEVO_INVALIDO",
            "El intervalo nuevo no pudo verificarse."
        )

    resultado.update({
        "contexto_autorizado": True,
        "captura_comparable": True,
        "vina_id": preparada["vina_id"],
        "plant_id": preparada["plant_id"],
        "device_id": preparada["device_id"],
        "codigo_planta": preparada["codigo_planta"],
        "intervalo_nuevo": intervalo_nuevo
    })

    historial = consultar_historial_captura(
        conexion,
        captura,
        usuario_id,
        vina_id,
        device_id
    )

    if (
        historial["consulta_completada"] is not True
        or historial["contexto_autorizado"] is not True
        or historial["bloqueo_por_historial"] is not False
    ):

        resultado["contexto_autorizado"] = (
            historial["contexto_autorizado"] is True
        )

        resultado["incidencias"].extend(
            historial["incidencias"]
        )

        return rechazar(
            "COMPARACION_BLOQUEADA_POR_HISTORIAL",
            "El historial no pudo verificarse."
        )

    return _comparar_con_historial_verificado(
        preparada,
        historial,
        resultado,
        hoja,
        fila
    )


def _comparar_con_historial_verificado(
    preparada,
    historial,
    resultado,
    hoja,
    fila
):
    """Motor interno de comparación histórica.

    Recibe exclusivamente resultados preparados por
    las capas autorizadas de consulta y validación.

    No consulta SQLite ni autoriza importaciones.
    No debe recibir datos históricos externos.
    """

    intervalo_nuevo = preparada["intervalo"]

    def rechazar(codigo, mensaje):

        resultado["incidencias"].append({
            "nivel": "ERROR",
            "codigo": codigo,
            "mensaje": mensaje
        })

        return resultado

    if any(
        historial[campo] != preparada[campo]
        for campo in (
            "vina_id",
            "plant_id",
            "device_id"
        )
    ):

        return rechazar(
            "CONTEXTO_HISTORICO_INCONSISTENTE",
            "Las identidades autorizadas no coinciden."
        )

    historicas = historial["capturas_historicas"]

    if (
        not isinstance(historicas, list)
        or type(historial["cantidad_registros"]) is not int
        or historial["cantidad_registros"] != len(historicas)
        or len(historicas) > MAX_REGISTROS_HISTORICOS_PLANTA
    ):

        return rechazar(
            "CANTIDAD_HISTORICA_INCONSISTENTE",
            "No pudo verificarse la cantidad "
            "de registros históricos."
        )

    coincidencias = []

    conteos = {
        "POSIBLE_DUPLICADO_TEMPORAL": 0,
        "SOLAPAMIENTO_PRECISION_TEMPORAL": 0,
        "COINCIDENCIA_ENTRE_DISPOSITIVOS": 0
    }

    for historica in historicas:

        if (
            historica["vina_id"] != preparada["vina_id"]
            or historica["plant_id"] != preparada["plant_id"]
        ):

            return rechazar(
                "PERTENENCIA_HISTORICA_INCONSISTENTE",
                "Una captura histórica no corresponde "
                "a la planta autorizada."
            )

        comparacion = comparar_intervalos_historicos(
            intervalo_nuevo,
            historica["intervalo"]
        )

        if comparacion["comparables"] is not True:

            resultado["incidencias"].extend(
                comparacion["incidencias"]
            )

            return rechazar(
                "COMPARACION_TEMPORAL_INCOMPLETA",
                "Un intervalo histórico no pudo compararse."
            )

        if comparacion["existe_solapamiento"] is not True:

            continue

        mismo_dispositivo = (
            preparada["device_id"]
            == historica["device_id"]
        )

        exacta = comparacion["coincidencia_exacta"]

        if not mismo_dispositivo:

            codigo = "COINCIDENCIA_ENTRE_DISPOSITIVOS"

        elif exacta:

            codigo = "POSIBLE_DUPLICADO_TEMPORAL"

        else:

            codigo = "SOLAPAMIENTO_PRECISION_TEMPORAL"

        conteos[codigo] += 1

        coincidencias.append({
            "codigo": codigo,
            "vina_id": preparada["vina_id"],
            "plant_id": preparada["plant_id"],
            "codigo_planta": preparada["codigo_planta"],
            "hoja_excel": hoja,
            "fila_excel": fila,
            "device_id_nuevo": preparada["device_id"],
            "device_id_historico": historica["device_id"],
            "captura_id_historica": historica["captura_id"],
            "importacion_id_historica":
                historica["importacion_id"],
            "fecha_hora_nueva":
                intervalo_nuevo["fecha_hora_normalizada"],
            "fecha_hora_historica": historica["fecha_hora"],
            "intervalo_nuevo": intervalo_nuevo,
            "intervalo_historico": historica["intervalo"],
            "mismo_dispositivo": mismo_dispositivo,
            "coincidencia_exacta": exacta,
            "existe_solapamiento": True,
            "duracion_solapamiento_microsegundos":
                comparacion[
                    "duracion_solapamiento_microsegundos"
                ],
            "requiere_revision": True,
            "duplicado_confirmado": False
        })

    resultado.update({
        "estado": (
            "COMPARACION_HISTORICA_CON_COINCIDENCIAS"
            if coincidencias
            else "COMPARACION_HISTORICA_SIN_COINCIDENCIAS"
        ),
        "comparacion_completada": True,
        "cantidad_registros_historicos": len(historicas),
        "cantidad_coincidencias": len(coincidencias),
        "coincidencias": coincidencias,
        "conteo_coincidencias": conteos,
        "independiente_del_historial": not coincidencias,
        "bloqueo_por_historial": False,
        "requiere_revision": bool(coincidencias)
    })

    return resultado


from uuid import uuid4

from detector_duplicados_dispositivo import (
    MAX_CAPTURAS_COMPARACION,
    MAX_PARES_COINCIDENCIAS
)


MAX_REGISTROS_HISTORICOS_LOTE = 100000
MAX_EVALUACIONES_TEMPORALES_LOTE = 1000000


def comparar_lote_con_historial(
    conexion,
    capturas,
    usuario_id,
    vina_id,
    device_id
):
    """Compara un lote con historiales autorizados.

    Recupera cada historial una vez por grupo.
    Conserva el orden original de las capturas.
    No confirma duplicados ni guarda datos.
    """

    resultado = {
        "estado": "COMPARACION_LOTE_RECHAZADA",
        "diagnostico_completo": False,
        "recuperacion_transaccional_pendiente": False,
        "savepoint_pendiente": None,
        "contexto_autorizado": False,
        "cantidad_capturas": (
            len(capturas)
            if isinstance(capturas, list)
            else None
        ),
        "cantidad_capturas_comparables": None,
        "cantidad_grupos": None,
        "consultas_historial_realizadas": 0,
        "registros_historicos_procesados": 0,
        "evaluaciones_temporales": 0,
        "cantidad_coincidencias": None,
        "capturas_con_coincidencias": None,
        "capturas_independientes": None,
        "conteo_coincidencias": None,
        "capturas_evaluadas": [],
        "coincidencias": [],
        "bloqueo_por_historial": True,
        "bloqueo_por_limite": False,
        "requiere_revision": True,
        "incidencias": [],
        "duplicados_confirmados": 0,
        "listo_para_importar": False,
        "datos_guardados": False,
        "limites_seguridad": {
            "max_capturas":
                MAX_CAPTURAS_COMPARACION,
            "max_registros_historicos_planta":
                MAX_REGISTROS_HISTORICOS_PLANTA,
            "max_registros_historicos_lote":
                MAX_REGISTROS_HISTORICOS_LOTE,
            "max_evaluaciones_temporales":
                MAX_EVALUACIONES_TEMPORALES_LOTE,
            "max_coincidencias":
                MAX_PARES_COINCIDENCIAS
        }
    }

    def rechazar(
        codigo,
        mensaje,
        limite=False,
        posicion=None
    ):

        resultado["bloqueo_por_limite"] = limite

        incidencia = {
            "nivel": "ERROR",
            "codigo": codigo,
            "mensaje": mensaje
        }

        if posicion is not None:
            incidencia["posicion"] = posicion

        resultado["incidencias"].append(
            incidencia
        )

        return resultado

    if not isinstance(capturas, list):

        return rechazar(
            "LOTE_INVALIDO",
            "Las capturas deben entregarse en una lista."
        )

    if not capturas:

        return rechazar(
            "LOTE_VACIO",
            "No existen capturas para comparar."
        )

    if len(capturas) > MAX_CAPTURAS_COMPARACION:

        return rechazar(
            "LIMITE_CAPTURAS_LOTE_SUPERADO",
            "Se superó el máximo de capturas.",
            limite=True
        )

    referencias = set()

    for posicion, captura in enumerate(capturas):

        if not isinstance(captura, dict):

            return rechazar(
                "CAPTURA_INVALIDA",
                "Una captura no tiene formato válido.",
                posicion=posicion
            )

        hoja = captura.get("hoja_excel")
        fila = captura.get("fila_excel")

        if (
            not isinstance(hoja, str)
            or not hoja.strip()
            or type(fila) is not int
            or fila < 1
        ):

            return rechazar(
                "TRAZABILIDAD_CAPTURA_INVALIDA",
                "Una referencia de origen no es válida.",
                posicion=posicion
            )

        referencia = (hoja, fila)

        if referencia in referencias:

            return rechazar(
                "REFERENCIA_CAPTURA_REPETIDA",
                "Existe una referencia de origen repetida.",
                posicion=posicion
            )

        referencias.add(referencia)

    def procesar():

        grupos = {}

        for posicion, captura in enumerate(capturas):

            preparada = preparar_captura_para_comparacion(
                conexion,
                captura,
                usuario_id,
                vina_id,
                device_id
            )

            if preparada["comparable"] is not True:

                resultado["incidencias"].extend(
                    preparada["incidencias"]
                )

                return rechazar(
                    "CAPTURA_NO_COMPARABLE",
                    "Una captura del lote requiere revisión.",
                    posicion=posicion
                )

            if not _intervalo_valido(
                preparada["intervalo"]
            ):

                return rechazar(
                    "INTERVALO_NUEVO_INVALIDO",
                    "Un intervalo nuevo no pudo verificarse.",
                    posicion=posicion
                )

            clave = (
                preparada["vina_id"],
                preparada["plant_id"],
                preparada["device_id"]
            )

            grupos.setdefault(
                clave, []
            ).append((
                posicion,
                preparada
            ))

        resultado["contexto_autorizado"] = True

        resultado["cantidad_capturas_comparables"] = (
            len(capturas)
        )

        resultado["cantidad_grupos"] = len(grupos)

        evaluadas = [None] * len(capturas)

        total_coincidencias = 0

        conteos = {
            "POSIBLE_DUPLICADO_TEMPORAL": 0,
            "SOLAPAMIENTO_PRECISION_TEMPORAL": 0,
            "COINCIDENCIA_ENTRE_DISPOSITIVOS": 0
        }

        for clave, grupo in grupos.items():

            posicion_referencia = grupo[0][0]

            resultado[
                "consultas_historial_realizadas"
            ] += 1

            historial = consultar_historial_captura(
                conexion,
                capturas[posicion_referencia],
                usuario_id,
                vina_id,
                device_id
            )

            if (
                historial["consulta_completada"] is not True
                or historial["contexto_autorizado"] is not True
                or historial["bloqueo_por_historial"] is not False
            ):

                resultado["incidencias"].extend(
                    historial["incidencias"]
                )

                if historial["contexto_autorizado"] is not True:
                    resultado["contexto_autorizado"] = False

                limite_historico = any(
                    i.get("codigo") in (
                        "LIMITE_HISTORIAL_SUPERADO",
                        "LIMITE_BYTES_HISTORIAL_SUPERADO"
                    )
                    for i in historial["incidencias"]
                )

                return rechazar(
                    "COMPARACION_BLOQUEADA_POR_HISTORIAL",
                    "Un historial del lote no pudo verificarse.",
                    limite=limite_historico,
                    posicion=posicion_referencia
                )

            if (
                historial["vina_id"],
                historial["plant_id"],
                historial["device_id"]
            ) != clave:

                return rechazar(
                    "CONTEXTO_HISTORICO_INCONSISTENTE",
                    "El historial no corresponde al grupo.",
                    posicion=posicion_referencia
                )

            historicas = historial["capturas_historicas"]
            cantidad = historial["cantidad_registros"]

            if (
                not isinstance(historicas, list)
                or type(cantidad) is not int
                or cantidad != len(historicas)
                or cantidad > MAX_REGISTROS_HISTORICOS_PLANTA
            ):

                return rechazar(
                    "CANTIDAD_HISTORICA_INCONSISTENTE",
                    "No pudo verificarse el tamaño del historial.",
                    posicion=posicion_referencia
                )

            acumulado = (
                resultado["registros_historicos_procesados"]
                + cantidad
            )

            if acumulado > MAX_REGISTROS_HISTORICOS_LOTE:

                return rechazar(
                    "LIMITE_REGISTROS_HISTORICOS_LOTE_SUPERADO",
                    "Se superó el máximo histórico del lote.",
                    limite=True,
                    posicion=posicion_referencia
                )

            resultado[
                "registros_historicos_procesados"
            ] = acumulado

            pares_grupo = cantidad * len(grupo)

            if (
                resultado["evaluaciones_temporales"]
                + pares_grupo
                > MAX_EVALUACIONES_TEMPORALES_LOTE
            ):

                return rechazar(
                    "LIMITE_EVALUACIONES_TEMPORALES_SUPERADO",
                    "El grupo supera el presupuesto temporal.",
                    limite=True,
                    posicion=posicion_referencia
                )

            for posicion, preparada in grupo:

                captura = capturas[posicion]

                individual = {
                    "estado":
                        "COMPARACION_HISTORICA_RECHAZADA",
                    "comparacion_completada": False,
                    "contexto_autorizado": True,
                    "captura_comparable": True,
                    "vina_id": preparada["vina_id"],
                    "plant_id": preparada["plant_id"],
                    "device_id": preparada["device_id"],
                    "hoja_excel": captura["hoja_excel"],
                    "fila_excel": captura["fila_excel"],
                    "codigo_planta": preparada["codigo_planta"],
                    "intervalo_nuevo": preparada["intervalo"],
                    "cantidad_registros_historicos": None,
                    "cantidad_coincidencias": None,
                    "coincidencias": [],
                    "conteo_coincidencias": None,
                    "independiente_del_historial": None,
                    "bloqueo_por_historial": True,
                    "requiere_revision": True,
                    "incidencias": [],
                    "duplicados_confirmados": 0,
                    "listo_para_importar": False,
                    "datos_guardados": False
                }

                individual = _comparar_con_historial_verificado(
                    preparada,
                    historial,
                    individual,
                    captura["hoja_excel"],
                    captura["fila_excel"]
                )

                if individual["comparacion_completada"] is not True:

                    resultado["incidencias"].extend(
                        individual["incidencias"]
                    )

                    return rechazar(
                        "COMPARACION_LOTE_INCOMPLETA",
                        "Una comparación no pudo completarse.",
                        posicion=posicion
                    )

                resultado[
                    "evaluaciones_temporales"
                ] += cantidad

                nuevas_coincidencias = (
                    individual["cantidad_coincidencias"]
                )

                if (
                    total_coincidencias
                    + nuevas_coincidencias
                    > MAX_PARES_COINCIDENCIAS
                ):

                    return rechazar(
                        "LIMITE_COINCIDENCIAS_LOTE_SUPERADO",
                        "Se superó el máximo de coincidencias.",
                        limite=True,
                        posicion=posicion
                    )

                total_coincidencias += nuevas_coincidencias

                for codigo in conteos:

                    conteos[codigo] += (
                        individual["conteo_coincidencias"][codigo]
                    )

                evaluadas[posicion] = {
                    "posicion": posicion,
                    "resultado": individual
                }

            del historial
            del historicas

        coincidencias = [
            {
                "posicion": elemento["posicion"],
                **coincidencia
            }
            for elemento in evaluadas
            for coincidencia in elemento[
                "resultado"
            ]["coincidencias"]
        ]

        con_coincidencias = sum(
            elemento["resultado"][
                "cantidad_coincidencias"
            ] > 0
            for elemento in evaluadas
        )

        resultado.update({
            "estado": (
                "COMPARACION_LOTE_CON_COINCIDENCIAS"
                if coincidencias
                else "COMPARACION_LOTE_SIN_COINCIDENCIAS"
            ),
            "diagnostico_completo": True,
            "cantidad_coincidencias": total_coincidencias,
            "capturas_con_coincidencias": con_coincidencias,
            "capturas_independientes": (
                len(capturas) - con_coincidencias
            ),
            "conteo_coincidencias": conteos,
            "capturas_evaluadas": evaluadas,
            "coincidencias": coincidencias,
            "bloqueo_por_historial": False,
            "requiere_revision": bool(coincidencias)
        })

        return resultado

    nombre_savepoint = (
        "diagnostico_historial_" + uuid4().hex
    )

    iniciado = False

    def recuperar_savepoint():
        """
        Intenta revertir y cerrar exclusivamente el
        SAVEPOINT interno.

        No realiza COMMIT ni ROLLBACK global.
        Si falla la reversión, no intenta liberar
        el SAVEPOINT.
        """

        try:

            conexion.execute(
                f"ROLLBACK TO SAVEPOINT {nombre_savepoint}"
            )

        except BaseException as error:

            return "ROLLBACK_TO", error

        try:

            conexion.execute(
                f"RELEASE SAVEPOINT {nombre_savepoint}"
            )

        except BaseException as error:

            return "RELEASE", error

        return None, None

    try:

        conexion.execute(
            f"SAVEPOINT {nombre_savepoint}"
        )

        iniciado = True

        salida = procesar()

        conexion.execute(
            f"RELEASE SAVEPOINT {nombre_savepoint}"
        )

        iniciado = False

        return salida

    except sqlite3.Error:

        if iniciado:

            etapa, error_recuperacion = (
                recuperar_savepoint()
            )

            if error_recuperacion is not None:

                resultado[
                    "recuperacion_transaccional_pendiente"
                ] = True

                resultado[
                    "savepoint_pendiente"
                ] = nombre_savepoint

                resultado["incidencias"].append({
                    "nivel": "ERROR",
                    "codigo": "ERROR_CIERRE_LECTURA_LOTE",
                    "mensaje": (
                        "No pudo confirmarse el cierre "
                        "seguro de la lectura del lote."
                    ),
                    "etapa_recuperacion": etapa
                })

                resultado["incidencias"].append({
                    "nivel": "ERROR",
                    "codigo":
                        "RECUPERACION_TRANSACCIONAL_PENDIENTE",
                    "mensaje": (
                        "No reutilizar la conexión hasta "
                        "resolver su estado transaccional."
                    )
                })

                if not isinstance(
                    error_recuperacion,
                    Exception
                ):

                    error_recuperacion.add_note(
                        "RECUPERACION_TRANSACCIONAL_PENDIENTE: "
                        f"{nombre_savepoint}; "
                        f"etapa={etapa}. "
                        "No reutilizar la conexión hasta "
                        "resolver su estado transaccional."
                    )

                    raise error_recuperacion

            else:

                iniciado = False

        resultado.update({
            "estado": "COMPARACION_LOTE_RECHAZADA",
            "diagnostico_completo": False,
            "contexto_autorizado": False,
            "cantidad_coincidencias": None,
            "capturas_con_coincidencias": None,
            "capturas_independientes": None,
            "conteo_coincidencias": None,
            "capturas_evaluadas": [],
            "coincidencias": [],
            "bloqueo_por_historial": True,
            "requiere_revision": True
        })

        return rechazar(
            "ERROR_SQLITE_COMPARACION_LOTE",
            "No pudo completarse la lectura consistente."
        )

    except BaseException as error_original:

        if iniciado:

            etapa, error_recuperacion = (
                recuperar_savepoint()
            )

            if error_recuperacion is not None:

                error_original.add_note(
                    "RECUPERACION_TRANSACCIONAL_PENDIENTE: "
                    f"{nombre_savepoint}; "
                    f"etapa={etapa}; "
                    "error secundario="
                    f"{type(error_recuperacion).__name__}. "
                    "No reutilizar la conexión hasta "
                    "resolver su estado transaccional."
                )

            else:

                iniciado = False

        raise
