"""Validación semántica de capturas del dispositivo."""

from datetime import date, time, datetime
import re


PATRON_FECHA = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
)

PATRON_HORA = re.compile(
    r"[0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]{1,6})?)?"
)

PATRON_FECHA_HORA = re.compile(
    PATRON_FECHA.pattern
    + r"[T ]"
    + PATRON_HORA.pattern
)


def _valor_ausente(valor):
    """Distingue valores ausentes de valores inválidos."""

    return (
        valor is None
        or (
            isinstance(valor, str)
            and not valor.strip()
        )
    )


def _interpretar_fecha(valor):
    """Interpreta fechas ISO sin inferir otros formatos."""

    if (
        not isinstance(valor, str)
        or not PATRON_FECHA.fullmatch(valor)
    ):
        raise ValueError(
            "La fecha debe tener formato AAAA-MM-DD."
        )

    return date.fromisoformat(valor)


def _interpretar_hora(valor):
    """Interpreta horas locales sin inventar zona horaria."""

    if (
        not isinstance(valor, str)
        or not PATRON_HORA.fullmatch(valor)
    ):
        raise ValueError(
            "La hora no tiene un formato reconocido."
        )

    return time.fromisoformat(valor)


def _interpretar_fecha_hora(valor):
    """Interpreta una fecha y hora combinadas."""

    if (
        not isinstance(valor, str)
        or not PATRON_FECHA_HORA.fullmatch(valor)
    ):
        raise ValueError(
            "La fecha y hora no tienen un formato reconocido."
        )

    return datetime.fromisoformat(valor)


def validar_fecha_hora_captura(captura):
    """Valida el instante registrado sin modificar la captura."""

    if not isinstance(captura, dict):
        raise ValueError(
            "La captura debe ser un diccionario."
        )

    fecha = captura.get("fecha")
    hora = captura.get("hora")
    combinada = captura.get("fecha_hora")

    tiene_fecha = not _valor_ausente(fecha)
    tiene_hora = not _valor_ausente(hora)
    tiene_combinada = not _valor_ausente(combinada)

    incidencias = []

    def registrar_error(codigo, campo, mensaje):

        incidencias.append({
            "nivel": "ERROR",
            "codigo": codigo,
            "campo": campo,
            "mensaje": mensaje,
            "hoja_excel": captura.get("hoja_excel"),
            "fila_excel": captura.get("fila_excel"),
            "codigo_planta": captura.get("codigo_planta")
        })

    instante = None
    origen = None
    precision = None

    if tiene_combinada:

        if tiene_fecha or tiene_hora:

            registrar_error(
                "FORMATO_TEMPORAL_CONTRADICTORIO",
                "fecha_hora",
                "Existen valores temporales combinados y separados."
            )

        else:

            try:

                instante = _interpretar_fecha_hora(
                    combinada
                )

                origen = "COMBINADO"

            except ValueError:

                registrar_error(
                    "FECHA_HORA_INVALIDA",
                    "fecha_hora",
                    "La fecha y hora combinadas no son válidas."
                )

    else:

        fecha_validada = None
        hora_validada = None

        if not tiene_fecha:

            registrar_error(
                "FECHA_AUSENTE",
                "fecha",
                "La captura no contiene una fecha."
            )

        else:

            try:

                fecha_validada = _interpretar_fecha(
                    fecha
                )

            except ValueError:

                registrar_error(
                    "FECHA_INVALIDA",
                    "fecha",
                    "La fecha de captura no es válida."
                )

        if not tiene_hora:

            registrar_error(
                "HORA_AUSENTE",
                "hora",
                "La captura no contiene una hora."
            )

        else:

            try:

                hora_validada = _interpretar_hora(
                    hora
                )

            except ValueError:

                registrar_error(
                    "HORA_INVALIDA",
                    "hora",
                    "La hora de captura no es válida."
                )

        if not incidencias:

            instante = datetime.combine(
                fecha_validada,
                hora_validada
            )

            origen = "SEPARADO"

    fecha_hora_normalizada = None

    if instante is not None and not incidencias:

        hora_original = (
            combinada[11:]
            if origen == "COMBINADO"
            else hora
        )

        if "." in hora_original:

            precision = "FRACCION_SEGUNDO"

            fecha_hora_normalizada = (
                instante.isoformat(
                    timespec="microseconds"
                )
            )

        elif hora_original.count(":") == 2:

            precision = "SEGUNDO"

            fecha_hora_normalizada = (
                instante.isoformat(
                    timespec="seconds"
                )
            )

        else:

            precision = "MINUTO"

            fecha_hora_normalizada = (
                instante.isoformat(
                    timespec="minutes"
                )
            )

    return {
        "estado": (
            "FECHA_HORA_VALIDADA"
            if not incidencias
            else "FECHA_HORA_RECHAZADA"
        ),
        "valida": not incidencias,
        "hoja_excel": captura.get("hoja_excel"),
        "fila_excel": captura.get("fila_excel"),
        "codigo_planta": captura.get("codigo_planta"),
        "fecha_hora_normalizada": fecha_hora_normalizada,
        "origen_temporal": origen,
        "precision_temporal": precision,
        "zona_horaria": None,
        "valores_originales": {
            "fecha": fecha,
            "hora": hora,
            "fecha_hora": combinada
        },
        "incidencias": incidencias,
        "listo_para_importar": False,
        "datos_guardados": False
    }


# Validación ambiental preliminar.
# Las unidades deberán confirmarse con el dispositivo real.

import math


PATRON_NUMERO_AMBIENTAL = re.compile(
    r"[+-]?[0-9]+(?:[.,][0-9]+)?"
)


def _interpretar_numero_ambiental(valor):
    """Interpreta números sin inferir unidades ni miles."""

    if isinstance(valor, bool):

        raise ValueError(
            "Los booleanos no son mediciones ambientales."
        )

    if isinstance(valor, (int, float)):

        numero = float(valor)

    elif isinstance(valor, str):

        if not PATRON_NUMERO_AMBIENTAL.fullmatch(valor):

            raise ValueError(
                "Formato numérico no reconocido."
            )

        # Tres cifras tras un separador pueden representar
        # decimales o una agrupación de miles.
        if "." in valor or "," in valor:

            partes = re.split(r"[.,]", valor)

            if (
                len(partes[1]) == 3
                and partes[0].lstrip("+-") != "0"
            ):

                raise ValueError(
                    "Separador decimal potencialmente ambiguo."
                )

        numero = float(
            valor.replace(",", ".")
        )

    else:

        raise ValueError(
            "Tipo de medición ambiental no reconocido."
        )

    if not math.isfinite(numero):

        raise ValueError(
            "La medición debe ser un número finito."
        )

    return numero



def _representar_valor_original(valor):
    """Representa valores no finitos sin perder su significado."""

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
            _representar_valor_original(elemento)
            for elemento in valor
        ]

    if isinstance(valor, dict):

        return {
            clave: _representar_valor_original(elemento)
            for clave, elemento in valor.items()
        }

    return valor


def validar_datos_ambientales_captura(captura):
    """Valida mediciones ambientales sin sustituir datos."""

    if not isinstance(captura, dict):

        raise ValueError(
            "La captura debe ser un diccionario."
        )

    temperatura = captura.get(
        "temperatura_ambiental"
    )

    humedad = captura.get(
        "humedad_ambiental"
    )

    incidencias = []

    def registrar(nivel, codigo, campo, mensaje):

        incidencias.append({
            "nivel": nivel,
            "codigo": codigo,
            "campo": campo,
            "mensaje": mensaje,
            "hoja_excel": captura.get("hoja_excel"),
            "fila_excel": captura.get("fila_excel"),
            "codigo_planta": captura.get("codigo_planta")
        })

    temperatura_validada = None
    humedad_validada = None

    if _valor_ausente(temperatura):

        registrar(
            "ADVERTENCIA",
            "TEMPERATURA_AMBIENTAL_AUSENTE",
            "temperatura_ambiental",
            "La captura no contiene temperatura ambiental."
        )

    else:

        try:

            numero = _interpretar_numero_ambiental(
                temperatura
            )

            if numero < -273.15:

                registrar(
                    "ERROR",
                    "TEMPERATURA_AMBIENTAL_FUERA_RANGO",
                    "temperatura_ambiental",
                    "Temperatura inferior al cero absoluto."
                )

            else:

                temperatura_validada = numero

        except (ValueError, OverflowError):

            registrar(
                "ERROR",
                "TEMPERATURA_AMBIENTAL_INVALIDA",
                "temperatura_ambiental",
                "La temperatura no es un número válido."
            )

    if _valor_ausente(humedad):

        registrar(
            "ADVERTENCIA",
            "HUMEDAD_AMBIENTAL_AUSENTE",
            "humedad_ambiental",
            "La captura no contiene humedad ambiental."
        )

    else:

        try:

            numero = _interpretar_numero_ambiental(
                humedad
            )

            if not 0 <= numero <= 100:

                registrar(
                    "ERROR",
                    "HUMEDAD_AMBIENTAL_FUERA_RANGO",
                    "humedad_ambiental",
                    "La humedad relativa debe estar entre 0 y 100 %."
                )

            else:

                humedad_validada = numero

        except (ValueError, OverflowError):

            registrar(
                "ERROR",
                "HUMEDAD_AMBIENTAL_INVALIDA",
                "humedad_ambiental",
                "La humedad no es un número válido."
            )

    errores = sum(
        i["nivel"] == "ERROR"
        for i in incidencias
    )

    advertencias = sum(
        i["nivel"] == "ADVERTENCIA"
        for i in incidencias
    )

    if errores:

        estado = "DATOS_AMBIENTALES_RECHAZADOS"

    elif advertencias:

        estado = "DATOS_AMBIENTALES_INCOMPLETOS"

    else:

        estado = "DATOS_AMBIENTALES_VALIDADOS"

    return {
        "estado": estado,
        "valida": errores == 0,
        "datos_completos": (
            temperatura_validada is not None
            and humedad_validada is not None
        ),
        "requiere_revision": bool(incidencias),
        "hoja_excel": captura.get("hoja_excel"),
        "fila_excel": captura.get("fila_excel"),
        "codigo_planta": captura.get("codigo_planta"),
        "temperatura_ambiental": temperatura_validada,
        "humedad_ambiental": humedad_validada,
        "unidades_provisionales": {
            "temperatura_ambiental": "°C",
            "humedad_ambiental": "%"
        },
        "unidades_confirmadas": False,
        "valores_originales": {
            "temperatura_ambiental": (
                _representar_valor_original(temperatura)
            ),
            "humedad_ambiental": (
                _representar_valor_original(humedad)
            )
        },
        "incidencias": incidencias,
        "resumen": {
            "errores": errores,
            "advertencias": advertencias
        },
        "listo_para_importar": False,
        "datos_guardados": False
    }
