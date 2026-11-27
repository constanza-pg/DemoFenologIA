
import streamlit as st
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

from meteorologia_local import (
    obtener_meteorologia_por_fechas
)


def mostrar_comparacion_meteorologica(
    vina_id,
    latitud,
    longitud
):

    st.subheader("Comparación meteorológica")

    st.caption(
        "Compara las condiciones meteorológicas de tu viña "
        "entre diferentes fechas o períodos."
    )

    ultima_fecha = datetime.now(
        ZoneInfo("America/Santiago")
    ).date() - timedelta(days=7)

    primera_fecha = date(1940, 1, 1)

    prefijo = f"comparacion_meteo_{vina_id}"

    modalidad = st.radio(
        "Modalidad de comparación",
        ["Comparar fechas", "Comparar períodos"],
        horizontal=True,
        key=f"{prefijo}_modalidad"
    )

    with st.form(f"{prefijo}_formulario_{modalidad}"):

        col1, col2 = st.columns(2)

        if modalidad == "Comparar fechas":

            with col1:

                inicio_a = st.date_input(
                    "Fecha de referencia",
                    value=ultima_fecha - timedelta(days=30),
                    min_value=primera_fecha,
                    max_value=ultima_fecha,
                    key=f"{prefijo}_fecha_a"
                )

            with col2:

                inicio_b = st.date_input(
                    "Fecha de comparación",
                    value=ultima_fecha,
                    min_value=primera_fecha,
                    max_value=ultima_fecha,
                    key=f"{prefijo}_fecha_b"
                )

            fin_a = inicio_a
            fin_b = inicio_b

        else:

            with col1:

                st.markdown("**Período de referencia**")

                inicio_a = st.date_input(
                    "Desde",
                    value=ultima_fecha - timedelta(days=59),
                    min_value=primera_fecha,
                    max_value=ultima_fecha,
                    key=f"{prefijo}_inicio_a"
                )

                fin_a = st.date_input(
                    "Hasta",
                    value=ultima_fecha - timedelta(days=30),
                    min_value=primera_fecha,
                    max_value=ultima_fecha,
                    key=f"{prefijo}_fin_a"
                )

            with col2:

                st.markdown("**Período de comparación**")

                inicio_b = st.date_input(
                    "Desde",
                    value=ultima_fecha - timedelta(days=29),
                    min_value=primera_fecha,
                    max_value=ultima_fecha,
                    key=f"{prefijo}_inicio_b"
                )

                fin_b = st.date_input(
                    "Hasta",
                    value=ultima_fecha,
                    min_value=primera_fecha,
                    max_value=ultima_fecha,
                    key=f"{prefijo}_fin_b"
                )

        comparar = st.form_submit_button(
            "Comparar condiciones meteorológicas",
            type="primary",
            width="stretch"
        )

    st.caption(
        f"Última fecha histórica habilitada: "
        f"{ultima_fecha:%d-%m-%Y}. "
        "Fuente: Open-Meteo."
    )

    clave_resultado = f"{prefijo}_resultado"

    if comparar:

        st.session_state.pop(clave_resultado, None)

        dias_a = (fin_a - inicio_a).days + 1
        dias_b = (fin_b - inicio_b).days + 1

        if dias_a <= 0 or dias_b <= 0:

            st.error(
                "La fecha inicial no puede ser posterior "
                "a la fecha final."
            )
            return

        if dias_a > 366 or dias_b > 366:

            st.error(
                "Cada período puede tener hasta 366 días."
            )
            return

        if dias_a != dias_b:

            st.warning(
                "Ambos períodos deben tener la misma duración "
                "para comparar correctamente sus acumulados."
            )
            return

        if inicio_a == inicio_b and fin_a == fin_b:

            st.warning(
                "Selecciona fechas o períodos diferentes."
            )
            return

        try:

            with st.spinner(
                "Consultando condiciones meteorológicas..."
            ):

                datos_a = obtener_meteorologia_por_fechas(
                    latitud, longitud, inicio_a, fin_a
                )

                datos_b = obtener_meteorologia_por_fechas(
                    latitud, longitud, inicio_b, fin_b
                )

            st.session_state[clave_resultado] = {
                "modalidad": modalidad,
                "coordenadas": (latitud, longitud),
                "inicio_a": inicio_a,
                "fin_a": fin_a,
                "inicio_b": inicio_b,
                "fin_b": fin_b,
                "dias": dias_a,
                "datos_a": datos_a,
                "datos_b": datos_b
            }

        except Exception:

            st.error(
                "No fue posible obtener los datos de ambos "
                "períodos. Revisa las fechas o intenta "
                "nuevamente más tarde."
            )
            return

    resultado = st.session_state.get(clave_resultado)

    if (
        resultado is None
        or resultado["modalidad"] != modalidad
        or resultado["coordenadas"] != (latitud, longitud)
    ):

        st.info(
            "Selecciona las fechas y presiona el botón "
            "para realizar una comparación."
        )
        return

    st.divider()

    st.subheader("Resultados de la comparación")

    st.caption(
        f"Referencia: "
        f"{resultado['inicio_a']:%d-%m-%Y} al "
        f"{resultado['fin_a']:%d-%m-%Y} | "
        f"Comparación: "
        f"{resultado['inicio_b']:%d-%m-%Y} al "
        f"{resultado['fin_b']:%d-%m-%Y}"
    )


    mostrar_resultados_comparacion(resultado)


def mostrar_resultados_comparacion(resultado):

    import pandas as pd
    import plotly.graph_objects as go

    datos_a = resultado["datos_a"]
    datos_b = resultado["datos_b"]

    dias = resultado["dias"]

    es_periodo = (
        resultado["modalidad"] == "Comparar períodos"
    )

    variables = [
        (
            "temperatura_min",
            "Temperatura mínima media" if es_periodo
            else "Temperatura mínima",
            "°C", "media"
        ),
        (
            "temperatura_max",
            "Temperatura máxima media" if es_periodo
            else "Temperatura máxima",
            "°C", "media"
        ),
        (
            "humedad_relativa",
            "Humedad relativa media",
            "%", "media"
        ),
        (
            "precipitacion",
            "Precipitación acumulada" if es_periodo
            else "Precipitación diaria",
            "mm", "suma"
        ),
        (
            "radiacion_solar",
            "Radiación solar acumulada" if es_periodo
            else "Radiación solar diaria",
            "MJ/m²", "suma"
        ),
        (
            "velocidad_viento",
            "Velocidad media del viento",
            "km/h", "media"
        )
    ]

    def calcular_valor(df, variable, operacion):

        serie = pd.to_numeric(
            df[variable], errors="coerce"
        ).replace(
            [float("inf"), float("-inf")],
            float("nan")
        )

        disponibles = int(serie.notna().sum())

        cobertura = disponibles / dias * 100

        # Evitar comparaciones con periodos incompletos.
        if disponibles != dias:
            return None, cobertura

        if operacion == "suma":
            valor = serie.sum(min_count=1)
        else:
            valor = serie.mean()

        return float(valor), cobertura

    def formato(valor, unidad):

        if valor is None or pd.isna(valor):
            return "Sin datos completos"

        return f"{valor:.2f} {unidad}"

    resumen = []

    for variable, nombre, unidad, operacion in variables:

        valor_a, cobertura_a = calcular_valor(
            datos_a, variable, operacion
        )

        valor_b, cobertura_b = calcular_valor(
            datos_b, variable, operacion
        )

        diferencia = (
            valor_b - valor_a
            if valor_a is not None
            and valor_b is not None
            else None
        )

        resumen.append({
            "variable": variable,
            "nombre": nombre,
            "unidad": unidad,
            "referencia": valor_a,
            "comparacion": valor_b,
            "diferencia": diferencia,
            "cobertura_a": cobertura_a,
            "cobertura_b": cobertura_b
        })

    st.caption(
        f"Duración de cada período: {dias} día(s). "
        "Diferencia = comparación menos referencia."
    )

    # Tarjetas principales.
    for inicio in range(0, len(resumen), 3):

        columnas = st.columns(3)

        for col, indicador in zip(
            columnas, resumen[inicio:inicio+3]
        ):

            with col:

                with st.container(border=True):

                    unidad = indicador["unidad"]

                    unidad_delta = (
                        "pp" if unidad == "%" else unidad
                    )

                    diferencia = indicador["diferencia"]

                    delta = (
                        f"{diferencia:+.2f} {unidad_delta}"
                        if diferencia is not None
                        else None
                    )

                    st.metric(
                        indicador["nombre"],
                        formato(
                            indicador["comparacion"],
                            unidad
                        ),
                        delta=delta,
                        delta_color="off"
                    )

                    st.caption(
                        "Referencia: "
                        + formato(
                            indicador["referencia"],
                            unidad
                        )
                    )

    incompletos = [
        r["nombre"] for r in resumen
        if r["diferencia"] is None
    ]

    if incompletos:

        st.warning(
            "No se calculan diferencias para variables "
            "con información incompleta: "
            + ", ".join(incompletos)
        )

    st.divider()

    st.subheader("Gráficos comparativos")

    grupos = [
        (
            "Temperaturas",
            ["temperatura_min", "temperatura_max"],
            "°C"
        ),
        (
            "Humedad relativa",
            ["humedad_relativa"],
            "%"
        ),
        (
            "Precipitación",
            ["precipitacion"],
            "mm"
        ),
        (
            "Radiación solar",
            ["radiacion_solar"],
            "MJ/m²"
        ),
        (
            "Velocidad del viento",
            ["velocidad_viento"],
            "km/h"
        )
    ]

    etiqueta_a = (
        f"{resultado['inicio_a']:%d-%m-%Y}"
        if not es_periodo else "Referencia"
    )

    etiqueta_b = (
        f"{resultado['inicio_b']:%d-%m-%Y}"
        if not es_periodo else "Comparación"
    )

    for i in range(0, len(grupos), 2):

        columnas = st.columns(2)

        for col, (titulo, claves, unidad) in zip(
            columnas, grupos[i:i+2]
        ):

            with col:

                seleccion = [
                    r for r in resumen
                    if r["variable"] in claves
                ]

                nombres = [
                    (
                        "Mínima"
                        if r["variable"] == "temperatura_min"
                        else "Máxima"
                        if r["variable"] == "temperatura_max"
                        else titulo
                    )
                    for r in seleccion
                ]

                fig = go.Figure()

                fig.add_trace(go.Bar(
                    name=etiqueta_a,
                    x=nombres,
                    y=[
                        r["referencia"]
                        for r in seleccion
                    ],
                    marker_color="#322345"
                ))

                fig.add_trace(go.Bar(
                    name=etiqueta_b,
                    x=nombres,
                    y=[
                        r["comparacion"]
                        for r in seleccion
                    ],
                    marker_color="#84C55D"
                ))

                fig.update_layout(
                    title=titulo,
                    template="plotly_white",
                    barmode="group",
                    height=300,
                    yaxis_title=unidad,
                    legend=dict(
                        orientation="h",
                        y=-0.2
                    ),
                    margin=dict(
                        l=20, r=20, t=50, b=65
                    )
                )

                if unidad == "%":
                    fig.update_yaxes(range=[0, 100])

                st.plotly_chart(
                    fig,
                    width="stretch",
                    key=f"comparacion_meteo_grafico_{titulo}"
                )

    # Evolucion diaria para comparacion de periodos.
    if es_periodo and dias > 1:

        st.divider()

        st.subheader("Evolución durante los períodos")

        st.caption(
            "Los períodos se alinean por número de día "
            "para facilitar su comparación."
        )

        opciones = {
            r["nombre"]: r for r in resumen
        }

        seleccion = st.selectbox(
            "Variable meteorológica",
            list(opciones),
            key="variable_evolucion_comparacion_meteo"
        )

        indicador = opciones[seleccion]
        variable = indicador["variable"]

        fig = go.Figure()

        for df, nombre, color in [
            (datos_a, "Referencia", "#322345"),
            (datos_b, "Comparación", "#84C55D")
        ]:

            fig.add_trace(go.Scatter(
                x=list(range(1, dias + 1)),
                y=df[variable],
                name=nombre,
                mode="lines",
                line=dict(color=color, width=2),
                connectgaps=False,
                customdata=df["fecha"].dt.strftime(
                    "%d-%m-%Y"
                ),
                hovertemplate=(
                    "Fecha: %{customdata}<br>"
                    "Valor: %{y:.2f}<extra></extra>"
                )
            ))

        fig.update_layout(
            template="plotly_white",
            height=350,
            xaxis_title="Día del período",
            yaxis_title=indicador["unidad"],
            legend_title_text=""
        )

        st.plotly_chart(
            fig,
            width="stretch",
            key="evolucion_comparacion_meteo"
        )

    with st.expander("Detalle y disponibilidad de datos"):

        tabla = pd.DataFrame([
            {
                "Variable": r["nombre"],
                "Referencia": formato(
                    r["referencia"], r["unidad"]
                ),
                "Comparación": formato(
                    r["comparacion"], r["unidad"]
                ),
                "Cobertura referencia (%)":
                    round(r["cobertura_a"], 1),
                "Cobertura comparación (%)":
                    round(r["cobertura_b"], 1)
            }
            for r in resumen
        ])

        st.dataframe(
            tabla,
            hide_index=True,
            width="stretch"
        )

        st.markdown("**Registros de referencia**")

        st.dataframe(
            datos_a,
            hide_index=True,
            width="stretch"
        )

        st.markdown("**Registros de comparación**")

        st.dataframe(
            datos_b,
            hide_index=True,
            width="stretch"
        )

    st.caption(
        "Fuente: Open-Meteo. Estimaciones meteorológicas "
        "por ubicación. Las diferencias no representan "
        "necesariamente condiciones favorables o "
        "desfavorables para el cultivo."
    )
