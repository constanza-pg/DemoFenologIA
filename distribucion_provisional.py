"""Distribución visual provisional de plantas sin GPS.

No escribe en SQLite ni modifica las coordenadas originales.
Las posiciones generadas son esquemáticas, no mediciones GPS.
"""

import math

import pandas as pd


def distribuir_plantas(
    datos,
    latitud_vina,
    longitud_vina,
    esp_fila=2.4,
    esp_planta=1.2,
    separacion_cuarteles=20.0,
):
    """Devuelve una copia con lat_mapa, lon_mapa y posicion_provisional."""

    resultado = datos.copy()

    resultado["lat_mapa"] = pd.to_numeric(
        resultado["lat"], errors="coerce"
    )
    resultado["lon_mapa"] = pd.to_numeric(
        resultado["lon"], errors="coerce"
    )

    resultado["posicion_provisional"] = False

    if resultado.empty:
        return resultado

    sin_gps = (
        resultado["lat_mapa"].isna()
        & resultado["lon_mapa"].isna()
    )

    if not sin_gps.any():
        return resultado

    if latitud_vina is None or longitud_vina is None:
        return resultado

    latitud_vina = float(latitud_vina)
    longitud_vina = float(longitud_vina)

    if not (
        math.isfinite(latitud_vina)
        and math.isfinite(longitud_vina)
        and -90 <= latitud_vina <= 90
        and -180 <= longitud_vina <= 180
    ):
        raise ValueError("Ubicación de viña inválida.")

    if esp_fila <= 0 or esp_planta <= 0:
        raise ValueError("Las separaciones deben ser positivas.")

    if separacion_cuarteles < 0:
        raise ValueError("Separación de cuarteles inválida.")

    if abs(latitud_vina) >= 89:
        raise ValueError(
            "La ubicación está demasiado cerca de un polo."
        )

    pendientes = resultado.loc[sin_gps].copy()

    pendientes["_cuartel"] = (
        pendientes["cuartel"].fillna("Sin cuartel").astype(str)
    )

    pendientes["_fila"] = pd.to_numeric(
        pendientes["fila"], errors="coerce"
    )

    pendientes["_planta"] = pd.to_numeric(
        pendientes["planta"], errors="coerce"
    )

    # Cada planta mantiene una sola posición en todas sus fechas.
    identificadores = (
        pendientes.sort_values(
            ["_cuartel", "_fila", "_planta", "id"],
            kind="stable",
            na_position="last",
        )
        .drop_duplicates("id")
    )

    desplazamiento_x = 0.0
    posiciones = {}

    for cuartel in sorted(identificadores["_cuartel"].unique()):
        grupo = identificadores[
            identificadores["_cuartel"] == cuartel
        ].copy()

        filas = sorted(
            grupo["_fila"].dropna().unique()
        )

        numeros_fila = {
            numero: indice
            for indice, numero in enumerate(filas)
        }

        ancho_maximo = 0.0

        for numero_fila, plantas_fila in grupo.groupby(
            "_fila", dropna=False, sort=False
        ):
            plantas_fila = plantas_fila.sort_values(
                ["_planta", "id"],
                kind="stable",
                na_position="last",
            )

            indice_fila = numeros_fila.get(
                numero_fila, len(filas)
            )

            # Conservar los números conocidos y asignar
            # posiciones libres a los faltantes o repetidos.
            numeros = plantas_fila["_planta"]

            columnas = []
            ocupadas = set()

            for numero in numeros:
                if (
                    pd.notna(numero)
                    and numero >= 1
                    and numero % 1 == 0
                    and int(numero) - 1 not in ocupadas
                ):
                    columna = int(numero) - 1
                    ocupadas.add(columna)
                    columnas.append(columna)
                else:
                    columnas.append(None)

            siguiente_libre = 0

            for indice, columna in enumerate(columnas):
                if columna is not None:
                    continue

                while siguiente_libre in ocupadas:
                    siguiente_libre += 1

                columnas[indice] = siguiente_libre
                ocupadas.add(siguiente_libre)
                siguiente_libre += 1

            for (_, planta_datos), columna in zip(
                plantas_fila.iterrows(), columnas
            ):
                x = desplazamiento_x + columna * esp_planta
                y = indice_fila * esp_fila

                posiciones[planta_datos["id"]] = (x, y)
                ancho_maximo = max(
                    ancho_maximo, columna * esp_planta
                )

        desplazamiento_x += (
            ancho_maximo + separacion_cuarteles + esp_planta
        )

    metros_por_grado_lon = (
        111320 * math.cos(math.radians(latitud_vina))
    )

    # Comprobar que el conjunto provisional no coincida
    # con plantas que tienen coordenadas GPS reales.
    con_gps = resultado.loc[
        resultado["lat_mapa"].notna()
        & resultado["lon_mapa"].notna()
    ]

    posiciones_reales = [
        (
            (float(fila["lon_mapa"]) - longitud_vina)
            * metros_por_grado_lon,
            (latitud_vina - float(fila["lat_mapa"]))
            * 111320,
        )
        for _, fila in con_gps.iterrows()
    ]

    posiciones_unicas = list(set(posiciones.values()))

    desplazamiento_seguridad = 0.0
    distancia_seguridad = 0.6
    paso_desplazamiento = esp_planta

    if posiciones_reales and posiciones_unicas:
        for intento in range(10000):
            existe_conflicto = any(
                math.hypot(
                    x + desplazamiento_seguridad - xr,
                    y - yr,
                ) < distancia_seguridad
                for x, y in posiciones_unicas
                for xr, yr in posiciones_reales
            )

            if not existe_conflicto:
                break

            desplazamiento_seguridad += paso_desplazamiento
        else:
            raise ValueError(
                "No se encontró una distribución provisional "
                "sin superposiciones."
            )

    for indice in resultado.index[sin_gps]:
        identificador = resultado.at[indice, "id"]
        if identificador not in posiciones:
            continue

        x, y = posiciones[identificador]
        x += desplazamiento_seguridad

        resultado.at[indice, "lat_mapa"] = (
            latitud_vina - y / 111320
        )
        resultado.at[indice, "lon_mapa"] = (
            longitud_vina + x / metros_por_grado_lon
        )
        resultado.at[indice, "posicion_provisional"] = True

    return resultado
