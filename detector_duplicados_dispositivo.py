
"""Identificación preliminar de coincidencias temporales.

No registra, elimina ni modifica capturas.
No presupone una zona horaria.
"""

from datetime import datetime

from validador_capturas_dispositivo import (
    validar_fecha_hora_captura
)


def _instante_microsegundos(instante):
    """Representación entera sin conversiones de zona horaria."""

    return (
        (
            (
                (instante.toordinal() - 1) * 24
                + instante.hour
            ) * 60
            + instante.minute
        ) * 60
        + instante.second
    ) * 1000000 + instante.microsecond


def construir_intervalo_temporal(captura):
    """Conserva la precisión original del registro."""

    validacion = validar_fecha_hora_captura(
        captura
    )

    resultado = {
        "estado": "INTERVALO_TEMPORAL_RECHAZADO",
        "valida": False,
        "fecha_hora_normalizada": (
            validacion["fecha_hora_normalizada"]
        ),
        "precision_temporal": (
            validacion["precision_temporal"]
        ),
        "digitos_fraccion": None,
        "inicio_microsegundos": None,
        "fin_exclusivo_microsegundos": None,
        "duracion_microsegundos": None,
        "zona_horaria": None,
        "hoja_excel": captura.get("hoja_excel"),
        "fila_excel": captura.get("fila_excel"),
        "incidencias": validacion["incidencias"],
        "listo_para_importar": False,
        "datos_guardados": False
    }

    if validacion["valida"] is not True:

        return resultado

    instante = datetime.fromisoformat(
        validacion["fecha_hora_normalizada"]
    )

    precision = validacion["precision_temporal"]

    originales = validacion["valores_originales"]

    hora_original = (
        originales["fecha_hora"][11:]
        if validacion["origen_temporal"] == "COMBINADO"
        else originales["hora"]
    )

    digitos = None

    if precision == "MINUTO":

        duracion = 60 * 1000000

    elif precision == "SEGUNDO":

        duracion = 1000000

    elif precision == "FRACCION_SEGUNDO":

        digitos = len(
            hora_original.split(".", 1)[1]
        )

        if not 1 <= digitos <= 6:

            raise ValueError(
                "Precisión fraccionaria no reconocida."
            )

        duracion = 10 ** (6 - digitos)

    else:

        raise ValueError(
            "Precisión temporal no reconocida."
        )

    inicio = _instante_microsegundos(
        instante
    )

    resultado.update({
        "estado": "INTERVALO_TEMPORAL_VALIDADO",
        "valida": True,
        "digitos_fraccion": digitos,
        "inicio_microsegundos": inicio,
        "fin_exclusivo_microsegundos": (
            inicio + duracion
        ),
        "duracion_microsegundos": duracion
    })

    return resultado


def comparar_temporalidad_capturas(
    captura_a,
    captura_b
):
    """Compara intervalos sin declarar duplicados."""

    a = construir_intervalo_temporal(
        captura_a
    )

    b = construir_intervalo_temporal(
        captura_b
    )

    comparables = (
        a["valida"] is True
        and b["valida"] is True
    )

    coincidencia = False
    solapamiento = False

    if not comparables:

        estado = "COMPARACION_TEMPORAL_NO_VALIDA"

    else:

        inicio_a = a["inicio_microsegundos"]
        inicio_b = b["inicio_microsegundos"]

        fin_a = a["fin_exclusivo_microsegundos"]
        fin_b = b["fin_exclusivo_microsegundos"]

        coincidencia = (
            inicio_a == inicio_b
            and fin_a == fin_b
        )

        solapamiento = (
            max(inicio_a, inicio_b)
            < min(fin_a, fin_b)
        )

        if coincidencia:

            estado = "COINCIDENCIA_TEMPORAL_EXACTA"

        elif solapamiento:

            estado = "SOLAPAMIENTO_TEMPORAL"

        else:

            estado = "INTERVALOS_INDEPENDIENTES"

    return {
        "estado": estado,
        "comparables": comparables,
        "coincidencia_exacta": coincidencia,
        "existe_solapamiento": solapamiento,
        "intervalo_a": a,
        "intervalo_b": b,
        "requiere_revision": (
            not comparables or solapamiento
        ),
        "duplicado_confirmado": False,
        "listo_para_importar": False,
        "datos_guardados": False
    }


from validador_pertenencia_dispositivo import (
    validar_planta_captura
)


def preparar_captura_para_comparacion(
    conexion,
    captura,
    usuario_id,
    vina_id,
    device_id
):
    """Prepara una identidad autorizada y temporal."""

    pertenencia = validar_planta_captura(
        conexion,
        captura,
        usuario_id,
        vina_id,
        device_id
    )

    resultado = {
        "estado": "CAPTURA_NO_COMPARABLE",
        "comparable": False,
        "hoja_excel": captura.get("hoja_excel"),
        "fila_excel": captura.get("fila_excel"),
        "codigo_planta": pertenencia["codigo_planta"],
        "vina_id": None,
        "plant_id": None,
        "device_id": None,
        "intervalo": None,
        "incidencias": list(
            pertenencia["incidencias"]
        ),
        "requiere_revision": True,
        "listo_para_importar": False,
        "datos_guardados": False
    }

    if pertenencia["valida"] is not True:

        return resultado

    intervalo = construir_intervalo_temporal(
        captura
    )

    if intervalo["valida"] is not True:

        resultado["incidencias"].extend(
            intervalo["incidencias"]
        )

        return resultado

    resultado.update({
        "estado": "CAPTURA_COMPARABLE",
        "comparable": True,
        "vina_id": pertenencia["vina_id"],
        "plant_id": pertenencia["plant_id"],
        "device_id": pertenencia["device_id"],
        "intervalo": intervalo,
        "requiere_revision": False
    })

    return resultado


MAX_CAPTURAS_COMPARACION = 50000
MAX_PARES_COINCIDENCIAS = 20000


def detectar_coincidencias_internas(
    conexion,
    capturas,
    usuario_id,
    vina_id,
    device_id
):
    """Detecta coincidencias sin confirmar duplicados."""

    if not isinstance(capturas, list):

        raise ValueError(
            "Las capturas deben entregarse en una lista."
        )

    if len(capturas) > MAX_CAPTURAS_COMPARACION:

        raise ValueError(
            "El conjunto supera el máximo de "
            "capturas permitido para comparación."
        )

    referencias = set()

    for captura in capturas:

        if not isinstance(captura, dict):

            raise ValueError(
                "Cada captura debe ser un diccionario."
            )

        hoja = captura.get("hoja_excel")
        fila = captura.get("fila_excel")

        if (
            not isinstance(hoja, str)
            or not hoja.strip()
            or type(fila) is not int
            or fila < 1
        ):

            raise ValueError(
                "Trazabilidad de captura inválida."
            )

        referencia = (hoja, fila)

        if referencia in referencias:

            raise ValueError(
                "Referencia de fila repetida."
            )

        referencias.add(referencia)

    preparadas = []
    grupos = {}
    excluidas = []

    for posicion, captura in enumerate(capturas):

        preparada = preparar_captura_para_comparacion(
            conexion,
            captura,
            usuario_id,
            vina_id,
            device_id
        )

        preparada["posicion"] = posicion

        preparadas.append(preparada)

        if preparada["comparable"] is not True:

            excluidas.append(posicion)

            continue

        clave = (
            preparada["vina_id"],
            preparada["plant_id"]
        )

        grupos.setdefault(
            clave, []
        ).append(preparada)

    coincidencias = []

    conteos = {
        "POSIBLE_DUPLICADO_TEMPORAL": 0,
        "SOLAPAMIENTO_PRECISION_TEMPORAL": 0,
        "COINCIDENCIA_ENTRE_DISPOSITIVOS": 0
    }

    posiciones_afectadas = set()

    limite_pares_alcanzado = False

    for grupo in grupos.values():

        if limite_pares_alcanzado:

            break

        ordenadas = sorted(
            grupo,
            key=lambda r: (
                r["intervalo"]["inicio_microsegundos"],
                r["intervalo"]["fin_exclusivo_microsegundos"],
                r["posicion"]
            )
        )

        activas = []

        for actual in ordenadas:

            if limite_pares_alcanzado:

                break

            intervalo = actual["intervalo"]

            inicio = intervalo[
                "inicio_microsegundos"
            ]

            fin = intervalo[
                "fin_exclusivo_microsegundos"
            ]

            activas = [
                previa
                for previa in activas
                if previa["intervalo"][
                    "fin_exclusivo_microsegundos"
                ] > inicio
            ]

            for previa in activas:

                if len(coincidencias) >= MAX_PARES_COINCIDENCIAS:

                    limite_pares_alcanzado = True

                    break

                anterior = previa["intervalo"]

                exacta = (
                    anterior["inicio_microsegundos"]
                    == inicio
                    and anterior["fin_exclusivo_microsegundos"]
                    == fin
                )

                mismo_dispositivo = (
                    previa["device_id"]
                    == actual["device_id"]
                )

                if not mismo_dispositivo:

                    codigo = (
                        "COINCIDENCIA_ENTRE_DISPOSITIVOS"
                    )

                elif exacta:

                    codigo = (
                        "POSIBLE_DUPLICADO_TEMPORAL"
                    )

                else:

                    codigo = (
                        "SOLAPAMIENTO_PRECISION_TEMPORAL"
                    )

                conteos[codigo] += 1

                posiciones_afectadas.update([
                    previa["posicion"],
                    actual["posicion"]
                ])

                coincidencias.append({
                    "codigo": codigo,
                    "vina_id": actual["vina_id"],
                    "plant_id": actual["plant_id"],
                    "posicion_a": previa["posicion"],
                    "posicion_b": actual["posicion"],
                    "hoja_excel_a": previa["hoja_excel"],
                    "fila_excel_a": previa["fila_excel"],
                    "hoja_excel_b": actual["hoja_excel"],
                    "fila_excel_b": actual["fila_excel"],
                    "device_id_a": previa["device_id"],
                    "device_id_b": actual["device_id"],
                    "coincidencia_exacta": exacta,
                    "requiere_revision": True,
                    "duplicado_confirmado": False
                })

            activas.append(actual)

    if limite_pares_alcanzado:

        for preparada in preparadas:

            if preparada["comparable"] is True:

                preparada["requiere_revision"] = True

    for posicion in posiciones_afectadas:

        preparadas[posicion][
            "requiere_revision"
        ] = True

    cantidad_comparables = (
        len(capturas) - len(excluidas)
    )

    return {
        "estado": (
            "DETECCION_INTERNA_INCOMPLETA"
            if limite_pares_alcanzado
            else "DETECCION_INTERNA_COMPLETADA"
        ),
        "diagnostico_completo": (
            not limite_pares_alcanzado
        ),
        "limite_pares_alcanzado": (
            limite_pares_alcanzado
        ),
        "bloqueo_por_limite": (
            limite_pares_alcanzado
        ),
        "limites_seguridad": {
            "max_capturas": MAX_CAPTURAS_COMPARACION,
            "max_pares": MAX_PARES_COINCIDENCIAS
        },
        "incidencias_globales": (
            [{
                "nivel": "ERROR",
                "codigo": "LIMITE_COINCIDENCIAS_SUPERADO",
                "mensaje": (
                    "Existen coincidencias adicionales "
                    "no detalladas. El diagnóstico "
                    "está incompleto y requiere revisión."
                )
            }]
            if limite_pares_alcanzado
            else []
        ),
        "resumen": {
            "cantidad_capturas": len(capturas),
            "capturas_comparables": cantidad_comparables,
            "capturas_excluidas": len(excluidas),
            "grupos_de_plantas": len(grupos),
            "pares_con_coincidencia": (
                None
                if limite_pares_alcanzado
                else len(coincidencias)
            ),
            "pares_detallados": len(coincidencias),
            "pares_totales_minimos": (
                len(coincidencias)
                + int(limite_pares_alcanzado)
            ),
            "capturas_con_coincidencia": (
                None
                if limite_pares_alcanzado
                else len(posiciones_afectadas)
            ),
            "capturas_con_coincidencia_detallada": (
                len(posiciones_afectadas)
            ),
            "capturas_independientes": (
                None
                if limite_pares_alcanzado
                else cantidad_comparables
                - len(posiciones_afectadas)
            ),
            "capturas_pendientes_revision_por_limite": (
                cantidad_comparables
                if limite_pares_alcanzado
                else 0
            ),
            "conteo_coincidencias": (
                None
                if limite_pares_alcanzado
                else conteos
            ),
            "conteo_coincidencias_detalladas": conteos
        },
        "capturas_evaluadas": preparadas,
        "coincidencias": coincidencias,
        "posiciones_excluidas": excluidas,
        "requiere_revision": bool(
            excluidas
            or coincidencias
            or limite_pares_alcanzado
        ),
        "duplicados_confirmados": 0,
        "listo_para_importar": False,
        "datos_guardados": False
    }
