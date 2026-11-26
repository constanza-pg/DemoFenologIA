"""Preparación de plantas y mediciones para el mapa de FenologIA."""

import pandas as pd

from distribucion_provisional import distribuir_plantas


COLUMNAS_ESTRUCTURA = [
    "id", "plant_internal_id", "cuartel",
    "variedad", "fila", "planta", "lat", "lon"
]


def preparar_estructura_mapa(
    plantas,
    latitud_vina,
    longitud_vina,
    esp_fila=2.4,
    esp_planta=1.2
):
    """Calcula posiciones visuales para todas las plantas."""

    estructura = plantas[COLUMNAS_ESTRUCTURA].copy()

    if estructura.empty:
        estructura["lat_mapa"] = estructura["lat"]
        estructura["lon_mapa"] = estructura["lon"]
        estructura["posicion_provisional"] = False
        return estructura

    if estructura["id"].duplicated().any():
        raise ValueError("Existen códigos de planta duplicados.")

    return distribuir_plantas(
        estructura,
        latitud_vina=latitud_vina,
        longitud_vina=longitud_vina,
        esp_fila=esp_fila,
        esp_planta=esp_planta
    )


def preparar_datos_fecha(
    estructura,
    mediciones,
    fecha=None,
    parametros=None
):
    """Mantiene todas las plantas, tengan o no mediciones."""

    resultado = estructura.copy()

    parametros = list(parametros or [])

    reservadas = set(COLUMNAS_ESTRUCTURA) | {
        "fecha", "lat_mapa", "lon_mapa",
        "posicion_provisional", "tiene_medicion"
    }

    if reservadas.intersection(parametros):
        raise ValueError("Parámetros estructurales no permitidos.")

    if (
        fecha is None
        or mediciones.empty
        or "fecha" not in mediciones.columns
    ):
        resultado["tiene_medicion"] = False

        for parametro in parametros:
            resultado[parametro] = float("nan")

        return resultado.set_index("id")

    actuales = mediciones[
        mediciones["fecha"] == fecha
    ].copy()

    if actuales["id"].duplicated().any():
        raise ValueError(
            "Existen mediciones duplicadas para esta fecha."
        )

    disponibles = [
        p for p in parametros
        if p in actuales.columns
    ]

    actuales = actuales[
        ["id"] + disponibles
    ].copy()

    actuales["tiene_medicion"] = True

    resultado = resultado.merge(
        actuales,
        on="id",
        how="left",
        validate="one_to_one"
    )

    resultado["tiene_medicion"] = (
        resultado["tiene_medicion"].eq(True)
    )

    for parametro in parametros:
        if parametro not in resultado.columns:
            resultado[parametro] = float("nan")

    return resultado.set_index("id")



def preparar_ultimos_registros(
    estructura,
    mediciones,
    parametros=None
):
    """Selecciona la última medición real de cada planta."""

    resultado = estructura.copy()
    parametros = list(parametros or [])

    reservadas = set(COLUMNAS_ESTRUCTURA) | {
        "fecha", "fecha_medicion", "lat_mapa",
        "lon_mapa", "posicion_provisional",
        "tiene_medicion"
    }

    if reservadas.intersection(parametros):
        raise ValueError(
            "Parámetros estructurales no permitidos."
        )

    if resultado["id"].duplicated().any():
        raise ValueError("Existen plantas duplicadas.")

    if mediciones.empty or "fecha" not in mediciones.columns:

        resultado["tiene_medicion"] = False
        resultado["fecha_medicion"] = None

        for parametro in parametros:
            resultado[parametro] = float("nan")

        return resultado.set_index("id")

    actuales = mediciones.copy()

    actuales["_fecha_orden"] = pd.to_datetime(
        actuales["fecha"],
        errors="raise"
    )

    if actuales["_fecha_orden"].isna().any():
        raise ValueError("Existen mediciones sin fecha válida.")

    if actuales.duplicated(
        subset=["id", "_fecha_orden"]
    ).any():
        raise ValueError(
            "Existen mediciones duplicadas por planta y fecha."
        )

    actuales = (
        actuales
        .sort_values("_fecha_orden")
        .drop_duplicates(subset=["id"], keep="last")
    )

    disponibles = [
        p for p in parametros
        if p in actuales.columns
    ]

    actuales = actuales[
        ["id", "fecha"] + disponibles
    ].copy()

    actuales = actuales.rename(
        columns={"fecha": "fecha_medicion"}
    )

    actuales["tiene_medicion"] = True

    resultado = resultado.merge(
        actuales,
        on="id",
        how="left",
        validate="one_to_one"
    )

    resultado["tiene_medicion"] = (
        resultado["tiene_medicion"].eq(True)
    )

    for parametro in parametros:
        if parametro not in resultado.columns:
            resultado[parametro] = float("nan")

    return resultado.set_index("id")
