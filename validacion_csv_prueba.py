import pandas as pd
import numpy as np

def validar_csv(datos):
    obligatorias = ["id", "fecha"]

    faltantes = [c for c in obligatorias if c not in datos.columns]
    if faltantes:
        raise ValueError("Faltan columnas: " + ", ".join(faltantes))

    if datos.empty:
        raise ValueError("El CSV está vacío.")

    datos = datos.copy()

    codigos = datos["id"].astype("string").str.strip()
    if codigos.isna().any() or codigos.eq("").any():
        raise ValueError("Existen códigos de planta vacíos.")
    datos["id"] = codigos.astype(str)

    fechas = datos["fecha"].astype("string").str.strip()
    formato = fechas.str.fullmatch(r"\d{4}-\d{2}-\d{2}").fillna(False)
    if not formato.all():
        raise ValueError("Formato de fecha inválido.")

    try:
        fechas = pd.to_datetime(fechas, format="%Y-%m-%d", errors="raise")
    except (ValueError, TypeError) as error:
        raise ValueError("Existen fechas inválidas.") from error

    datos["fecha"] = fechas.dt.strftime("%Y-%m-%d")

    # Coordenadas GPS opcionales: ambas presentes o ambas ausentes.
    for columna in ("lat", "lon"):
        if columna not in datos.columns:
            datos[columna] = np.nan

        datos[columna] = pd.to_numeric(
            datos[columna].replace(r"^\\s*$", np.nan, regex=True),
            errors="raise"
        )

    lat = datos["lat"]
    lon = datos["lon"]

    if (lat.isna() != lon.isna()).any():
        raise ValueError(
            "Cada planta debe tener latitud y longitud "
            "completas, o ambas vacías."
        )

    for columna, minimo, maximo in [
        ("lat", -90, 90),
        ("lon", -180, 180)
    ]:
        valores = datos[columna].dropna()

        if (
            not np.isfinite(valores.to_numpy(dtype=float)).all()
            or not valores.between(minimo, maximo).all()
        ):
            raise ValueError(
                f"Coordenadas inválidas: {columna}"
            )

    base = {"id", "fecha", "lat", "lon",
            "cuartel", "variedad", "fila", "planta"}

    for columna in datos.columns:
        if columna not in base and pd.api.types.is_numeric_dtype(datos[columna]):
            if np.isinf(datos[columna].to_numpy(dtype=float)).any():
                raise ValueError(f"Valores infinitos: {columna}")

    if datos.duplicated(subset=["id", "fecha"]).any():
        raise ValueError("Hay mediciones duplicadas.")


    # CONTRADICCIONES ESTRUCTURALES
    # Una planta debe conservar una estructura consistente
    # entre las distintas fechas del mismo CSV.

    campos_estructura = [
        "cuartel", "variedad", "fila",
        "planta", "lat", "lon"
    ]

    def valores_validos(serie):
        resultado = []

        for valor in serie:
            if pd.isna(valor):
                continue

            if isinstance(valor, str):
                valor = valor.strip()

                if valor.lower() in ("", "sin dato"):
                    continue

            resultado.append(valor)

        return resultado

    for codigo_planta, grupo in datos.groupby(
        "id", sort=False
    ):

        for campo in campos_estructura:

            if campo not in grupo.columns:
                continue

            valores = valores_validos(grupo[campo])

            if len(valores) < 2:
                continue

            referencia = valores[0]

            for valor in valores[1:]:

                if campo in ("lat", "lon"):
                    diferente = (
                        abs(
                            float(valor)
                            - float(referencia)
                        ) > 0.000001
                    )

                elif campo in ("fila", "planta"):
                    try:
                        diferente = (
                            float(valor)
                            != float(referencia)
                        )
                    except (ValueError, TypeError):
                        diferente = (
                            str(valor).strip()
                            != str(referencia).strip()
                        )

                else:
                    diferente = (
                        str(valor).strip()
                        != str(referencia).strip()
                    )

                if diferente:
                    raise ValueError(
                        "Contradicción estructural en "
                        f"la planta '{codigo_planta}', "
                        f"campo '{campo}'. "
                        "El CSV contiene valores "
                        "diferentes para una misma planta."
                    )

    return datos
