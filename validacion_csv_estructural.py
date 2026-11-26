"""Validación de CSV estructural de plantas de FenologIA."""

import pandas as pd
import numpy as np


def validar_csv_estructural(datos):
    obligatorias = [
        "id", "cuartel", "variedad", "fila", "planta"
    ]

    opcionales = ["lat", "lon"]

    faltantes = [
        c for c in obligatorias
        if c not in datos.columns
    ]

    if faltantes:
        raise ValueError(
            "Faltan columnas: " + ", ".join(faltantes)
        )

    if datos.empty:
        raise ValueError("El CSV está vacío.")

    datos = datos.copy()

    adicionales = [
        c for c in datos.columns
        if c not in obligatorias + opcionales
    ]

    if adicionales:
        raise ValueError(
            "El CSV estructural no admite estas columnas: "
            + ", ".join(adicionales)
        )

    for columna in ["id", "cuartel", "variedad"]:
        valores = datos[columna].astype("string").str.strip()

        if valores.isna().any() or valores.eq("").any():
            raise ValueError(
                f"Existen valores vacíos en {columna}."
            )

        datos[columna] = valores.astype(str)

    for columna in ["fila", "planta"]:
        valores = pd.to_numeric(
            datos[columna], errors="raise"
        )

        if (
            valores.isna().any()
            or not np.isfinite(valores).all()
            or (valores <= 0).any()
            or (valores % 1 != 0).any()
            or (valores >= 2**63).any()
        ):
            raise ValueError(
                f"{columna} debe contener enteros positivos."
            )

        datos[columna] = valores.astype("int64")

    for columna in opcionales:
        if columna not in datos.columns:
            datos[columna] = np.nan

        datos[columna] = pd.to_numeric(
            datos[columna].replace(
                r"^\s*$", np.nan, regex=True
            ),
            errors="raise"
        )

    if (datos["lat"].isna() != datos["lon"].isna()).any():
        raise ValueError(
            "Latitud y longitud deben estar ambas "
            "completas o ambas vacías."
        )

    for columna, minimo, maximo in [
        ("lat", -90, 90),
        ("lon", -180, 180)
    ]:
        valores = datos[columna].dropna()

        if (
            not np.isfinite(valores).all()
            or not valores.between(minimo, maximo).all()
        ):
            raise ValueError(
                f"Coordenadas inválidas: {columna}."
            )

    if datos["id"].duplicated().any():
        raise ValueError(
            "Existen códigos de planta duplicados."
        )

    if datos.duplicated(
        subset=["cuartel", "fila", "planta"]
    ).any():
        raise ValueError(
            "Existen posiciones estructurales duplicadas."
        )

    return datos[obligatorias + opcionales].copy()
