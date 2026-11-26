
import numpy as np
import pandas as pd


def generar_datos_demo():

    rng = np.random.default_rng(2026)

    regiones = [
        "Valparaíso",
        "Metropolitana",
        "O'Higgins",
        "Maule"
    ]

    variedades = [
        "Cabernet Sauvignon",
        "Carménère",
        "Merlot",
        "Syrah",
        "Chardonnay",
        "Sauvignon Blanc"
    ]

    registros = []

    for temporada in (2024, 2025):

        periodos = pd.period_range(
            f"{temporada}-09",
            f"{temporada + 1}-03",
            freq="M"
        )

        for r, region in enumerate(regiones):

            for v, variedad in enumerate(variedades):

                for mes, periodo in enumerate(periodos):

                    avance = mes / 6

                    temperatura = (
                        15 + 10 * np.sin(np.pi * avance * 0.8)
                        + r * 0.6 + rng.normal(0, 0.8)
                    )

                    humedad = (
                        76 - 22 * avance
                        + rng.normal(0, 3)
                    )

                    ndvi = (
                        0.40 + 0.40 * np.sin(np.pi * avance * 0.85)
                        + rng.normal(0, 0.025)
                    )

                    brix = (
                        5 + 19 * avance
                        + rng.normal(0, 0.6)
                        if mes >= 3 else None
                    )

                    tinta = variedad not in (
                        "Chardonnay",
                        "Sauvignon Blanc"
                    )

                    morado = (
                        float(np.clip(
                            100 * (avance - 0.45) / 0.55
                            + rng.normal(0, 3),
                            0, 100
                        ))
                        if tinta and mes >= 3 else
                        (0.0 if mes >= 3 else None)
                    )

                    verde = (
                        float(np.clip(
                            100 - morado - 12 * avance,
                            0, 100
                        ))
                        if morado is not None else None
                    )

                    registros.append({

                        "Region": region,
                        "Variedad": variedad,
                        "Periodo": str(periodo),

                        "Temporada": (
                            f"{temporada}-{temporada + 1}"
                        ),

                        "Mediciones": int(
                            rng.integers(60, 180)
                        ),

                        "NDVI": round(
                            float(np.clip(ndvi, 0, 1)), 3
                        ),

                        "Humedad": round(
                            float(np.clip(
                                30 - 12 * avance
                                + rng.normal(0, 2),
                                0, 100
                            )), 2
                        ),

                        "Potencial_hidrico": round(
                            -0.4 - 0.9 * avance
                            + rng.normal(0, 0.08), 3
                        ),

                        "Brix": (
                            round(brix, 2)
                            if brix is not None else None
                        ),

                        "Rendimiento": (
                            round(
                                2.4 + v * 0.15
                                + rng.normal(0, 0.3), 2
                            )
                            if mes == 6 else None
                        ),

                        "Temperatura_ambiental": round(
                            temperatura, 2
                        ),

                        "Humedad_ambiental": round(
                            float(np.clip(humedad, 0, 100)), 2
                        ),

                        "Porcentaje_verde": (
                            round(verde, 2)
                            if verde is not None else None
                        ),

                        "Porcentaje_morado": (
                            round(morado, 2)
                            if morado is not None else None
                        ),

                        "Origen": "SIMULADO"

                    })

    return pd.DataFrame(registros)
