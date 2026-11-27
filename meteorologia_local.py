
import requests
import pandas as pd
import streamlit as st
import certifi
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@st.cache_data(ttl=21600, show_spinner=False)
def obtener_historial_local(latitud, longitud, dias=90):

    hoy = datetime.now(
        ZoneInfo("America/Santiago")
    ).date()

    fin = hoy - timedelta(days=7)
    inicio = fin - timedelta(days=dias - 1)

    variables = {
        "temperature_2m_min": "temperatura_min",
        "temperature_2m_max": "temperatura_max",
        "relative_humidity_2m_mean": "humedad_relativa",
        "precipitation_sum": "precipitacion",
        "shortwave_radiation_sum": "radiacion_solar",
        "wind_speed_10m_mean": "velocidad_viento"
    }

    respuesta = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": latitud,
            "longitude": longitud,
            "start_date": inicio.isoformat(),
            "end_date": fin.isoformat(),
            "daily": ",".join(variables),
            "timezone": "auto",
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm"
        },
        timeout=25,
        verify=certifi.where()
    )

    respuesta.raise_for_status()

    datos = respuesta.json()

    if datos.get("error") or not datos.get("daily"):
        raise ValueError(
            "La fuente no entregó datos meteorológicos."
        )

    df = pd.DataFrame(datos["daily"])

    df = df.rename(
        columns={"time": "fecha", **variables}
    )

    df["fecha"] = pd.to_datetime(
        df["fecha"], errors="coerce"
    )

    df = df.dropna(subset=["fecha"])
    df = df.drop_duplicates("fecha")
    df = df.sort_values("fecha")

    for variable in variables.values():
        df[variable] = pd.to_numeric(
            df[variable], errors="coerce"
        )

    if df.empty or not df[
        list(variables.values())
    ].notna().any().any():
        raise ValueError(
            "No existen mediciones disponibles."
        )

    return df


def mostrar_meteorologia_local(vina_id, *, usuario_id):

    import database
    import plotly.express as px

    with database.conectar() as con:
        con.execute("BEGIN")
        database.verificar_permiso_mediciones(
            con, usuario_id, vina_id
        )
        ubicacion = con.execute("""
            SELECT latitud, longitud
            FROM vinas
            WHERE id = ?
        """, (vina_id,)).fetchone()

    if (
        ubicacion is None
        or ubicacion[0] is None
        or ubicacion[1] is None
    ):
        st.info(
            "Registra la ubicación de tu viña "
            "para consultar su meteorología."
        )
        return

    st.subheader("Meteorología por ubicación")

    st.caption(
        "Estimaciones meteorológicas históricas "
        "por coordenadas. Fuente: Open-Meteo. "
        "No corresponden a mediciones directas "
        "de una estación ni del dispositivo."
    )

    periodo = st.selectbox(
        "Período de consulta",
        [30, 90, 180, 365],
        index=1,
        format_func=lambda n: f"Últimos {n} días",
        key="periodo_meteo_local"
    )

    try:
        with st.spinner("Consultando meteorología..."):
            df = obtener_historial_local(
                float(ubicacion[0]),
                float(ubicacion[1]),
                periodo
            )

    except Exception:
        st.warning(
            "La fuente meteorológica no está disponible "
            "temporalmente. Intenta nuevamente más tarde."
        )
        return

    st.caption(
        f"Período disponible: "
        f"{df.fecha.min():%d-%m-%Y} al "
        f"{df.fecha.max():%d-%m-%Y}. "
        f"{len(df)} días de registros."
    )

    st.caption(
        "El historial termina siete días antes "
        "de la fecha actual para considerar "
        "el retraso de publicación."
    )

    indicadores = [
        (
            "Temperatura máxima media",
            df.temperatura_max.mean(),
            "°C"
        ),
        (
            "Humedad media",
            df.humedad_relativa.mean(),
            "%"
        ),
        (
            "Precipitación acumulada",
            df.precipitacion.sum(min_count=1),
            "mm"
        )
    ]

    columnas = st.columns(3)

    for col, (nombre, valor, unidad) in zip(
        columnas, indicadores
    ):
        col.metric(
            nombre,
            f"{valor:.1f} {unidad}"
            if pd.notna(valor)
            else "Sin datos"
        )

    if df.precipitacion.isna().any():
        st.warning(
            "El acumulado de precipitación es parcial: "
            "existen días sin información."
        )

    graficos = [
        (
            "Temperatura",
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
            "MJ/m²/día"
        ),
        (
            "Velocidad del viento",
            ["velocidad_viento"],
            "km/h"
        )
    ]

    for i in range(0, len(graficos), 2):

        columnas = st.columns(2)

        for col, (titulo, variables, unidad) in zip(
            columnas, graficos[i:i+2]
        ):
            with col:

                if titulo == "Precipitación":
                    fig = px.bar(
                        df,
                        x="fecha",
                        y=variables[0],
                        color_discrete_sequence=["#322345"]
                    )
                else:
                    fig = px.line(
                        df,
                        x="fecha",
                        y=variables,
                        color_discrete_sequence=[
                            "#322345", "#84C55D"
                        ]
                    )

                fig.update_layout(
                    title=titulo,
                    template="plotly_white",
                    height=300,
                    xaxis_title="Fecha",
                    yaxis_title=unidad,
                    legend_title_text="",
                    margin=dict(l=15,r=15,t=45,b=15)
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    key=f"meteo_local_{i}_{titulo}"
                )

    with st.expander("Disponibilidad de los datos"):

        cobertura = {
            variable: round(
                df[variable].notna().sum()
                / periodo * 100, 1
            )
            for variable in [
                "temperatura_min",
                "temperatura_max",
                "humedad_relativa",
                "precipitacion",
                "radiacion_solar",
                "velocidad_viento"
            ]
        }

        st.dataframe(
            pd.DataFrame(
                cobertura.items(),
                columns=["Variable", "Cobertura (%)"]
            ),
            hide_index=True,
            use_container_width=True
        )

        st.caption(
            "Los datos faltantes no se sustituyen por cero. "
            "Las estimaciones pueden diferir de las "
            "condiciones reales del viñedo."
        )




# ==========================================================
# OPEN-METEO: CONDICIONES ACTUALES Y PRONÓSTICO
# ==========================================================

@st.cache_data(ttl=1800, show_spinner=False)
def obtener_pronostico_local(latitud, longitud):

    actuales = [
        "temperature_2m",
        "relative_humidity_2m",
        "apparent_temperature",
        "precipitation",
        "weather_code",
        "cloud_cover",
        "wind_speed_10m",
        "wind_gusts_10m"
    ]

    diarias = [
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "precipitation_probability_max",
        "wind_speed_10m_max",
        "wind_gusts_10m_max",
        "shortwave_radiation_sum",
        "et0_fao_evapotranspiration",
        "sunrise",
        "sunset"
    ]

    horarias = [
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "precipitation_probability",
        "vapour_pressure_deficit",
        "wind_speed_10m"
    ]

    respuesta = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitud,
            "longitude": longitud,
            "current": ",".join(actuales),
            "daily": ",".join(diarias),
            "hourly": ",".join(horarias),
            "timezone": "auto",
            "forecast_days": 7,
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm"
        },
        timeout=25,
        verify=certifi.where()
    )

    respuesta.raise_for_status()
    datos = respuesta.json()

    if datos.get("error") or not datos.get("current"):
        raise ValueError(
            "No se recibió información meteorológica válida."
        )

    return datos


def descripcion_tiempo(codigo):

    if codigo == 0:
        return "Despejado"
    if codigo == 1:
        return "Mayormente despejado"
    if codigo == 2:
        return "Parcialmente nublado"
    if codigo == 3:
        return "Nublado"
    if codigo in (45, 48):
        return "Niebla"
    if codigo in (51, 53, 55, 56, 57):
        return "Llovizna"
    if codigo in (61, 63, 65, 66, 67):
        return "Lluvia"
    if codigo in (71, 73, 75, 77, 85, 86):
        return "Nieve"
    if codigo in (80, 81, 82):
        return "Chubascos"
    if codigo in (95, 96, 99):
        return "Tormenta"

    return "Condición no disponible"


def formato_valor_meteo(valor, unidad):

    if valor is None or pd.isna(valor):
        return "Sin datos"

    return f"{float(valor):.1f} {unidad}"


def mostrar_condiciones_actuales(latitud, longitud):

    import plotly.express as px

    st.subheader("Condiciones meteorológicas actuales")

    try:

        datos = obtener_pronostico_local(
            latitud, longitud
        )

        actual = datos["current"]

        st.caption(
            "Fuente: Open-Meteo · Datos modelados · "
            f"Hora de referencia: {actual.get('time', '')} · "
            f"{datos.get('timezone', '')}"
        )

        st.markdown(
            "### " + descripcion_tiempo(
                actual.get("weather_code")
            )
        )

        variables = [
            ("Temperatura", "temperature_2m", "°C"),
            ("Humedad relativa", "relative_humidity_2m", "%"),
            ("Precipitación", "precipitation", "mm"),
            ("Sensación térmica", "apparent_temperature", "°C"),
            ("Viento", "wind_speed_10m", "km/h"),
            ("Ráfagas", "wind_gusts_10m", "km/h"),
            ("Nubosidad", "cloud_cover", "%")
        ]

        columnas = st.columns(3)

        for i, (nombre, variable, unidad) in enumerate(variables):

            columnas[i % 3].metric(
                nombre,
                formato_valor_meteo(
                    actual.get(variable), unidad
                )
            )

        st.divider()

        st.subheader("Evolución durante el día")

        df = pd.DataFrame(datos["hourly"])

        df["time"] = pd.to_datetime(df["time"])

        fecha_actual = pd.Timestamp(actual["time"]).date()

        df = df[df["time"].dt.date == fecha_actual]

        graficos = [
            ("temperature_2m", "Temperatura", "°C"),
            ("relative_humidity_2m", "Humedad relativa", "%"),
            ("vapour_pressure_deficit", "Déficit de presión de vapor", "kPa"),
            ("precipitation", "Precipitación horaria", "mm")
        ]

        for variable, nombre, unidad in graficos:

            if variable == "precipitation":

                fig = px.bar(
                    df, x="time", y=variable,
                    title=nombre
                )

                fig.update_traces(marker_color="#322345")

            else:

                fig = px.line(
                    df, x="time", y=variable,
                    title=nombre
                )

                fig.update_traces(line_color="#84C55D")

            fig.update_layout(
                template="plotly_white",
                height=280,
                xaxis_title="Hora",
                yaxis_title=unidad
            )

            st.plotly_chart(
                fig,
                width="stretch",
                key=f"actual_openmeteo_{variable}"
            )

        st.caption(
            "La evolución diaria combina estimaciones "
            "modeladas y pronósticos. No corresponde "
            "a mediciones directas del dispositivo."
        )

    except Exception as e:

        st.warning(
            f"No se pudo consultar Open-Meteo: {e}"
        )


def mostrar_pronostico_local(latitud, longitud):

    import plotly.express as px

    st.subheader("Pronóstico de los próximos 7 días")

    try:

        datos = obtener_pronostico_local(
            latitud, longitud
        )

        df = pd.DataFrame(datos["daily"])

        df["time"] = pd.to_datetime(df["time"])

        st.caption(
            "Fuente: Open-Meteo · Pronóstico meteorológico "
            "sujeto a incertidumbre y actualizaciones."
        )

        tabla = pd.DataFrame({
            "Fecha": df["time"].dt.strftime("%d-%m-%Y"),
            "Condición": df["weather_code"].apply(
                descripcion_tiempo
            ),
            "Mínima (°C)": df["temperature_2m_min"],
            "Máxima (°C)": df["temperature_2m_max"],
            "Lluvia (mm)": df["precipitation_sum"],
            "Prob. lluvia (%)":
                df["precipitation_probability_max"],
            "Viento máx. (km/h)": df["wind_speed_10m_max"],
            "Radiación (MJ/m²)": df["shortwave_radiation_sum"],
            "ET0 (mm)": df["et0_fao_evapotranspiration"]
        })

        st.dataframe(
            tabla,
            hide_index=True,
            width="stretch"
        )

        fig = px.line(
            df,
            x="time",
            y=["temperature_2m_min", "temperature_2m_max"],
            markers=True,
            title="Temperaturas previstas",
            color_discrete_sequence=["#322345", "#84C55D"]
        )

        fig.for_each_trace(
            lambda traza: traza.update(
                name={
                    "temperature_2m_min": "Mínima",
                    "temperature_2m_max": "Máxima"
                }.get(traza.name, traza.name)
            )
        )

        fig.update_layout(
            template="plotly_white",
            height=320,
            xaxis_title="Fecha",
            yaxis_title="Temperatura (°C)",
            legend_title_text=""
        )

        st.plotly_chart(
            fig,
            width="stretch",
            key="pronostico_openmeteo_temperatura"
        )

        variables = [
            ("precipitation_sum", "Precipitación prevista", "mm"),
            ("precipitation_probability_max", "Probabilidad de lluvia", "%"),
            ("wind_speed_10m_max", "Viento máximo", "km/h"),
            ("shortwave_radiation_sum", "Radiación solar", "MJ/m²"),
            ("et0_fao_evapotranspiration", "Evapotranspiración de referencia", "mm")
        ]

        for variable, nombre, unidad in variables:

            fig = px.bar(
                df,
                x="time",
                y=variable,
                title=nombre
            )

            fig.update_traces(marker_color="#84C55D")

            fig.update_layout(
                template="plotly_white",
                height=280,
                xaxis_title="Fecha",
                yaxis_title=unidad
            )

            st.plotly_chart(
                fig,
                width="stretch",
                key=f"pronostico_openmeteo_{variable}"
            )

        st.info(
            "La evapotranspiración de referencia (ET0) "
            "permite contextualizar la demanda atmosférica "
            "de agua, pero no equivale directamente a "
            "las necesidades de riego del viñedo."
        )

    except Exception as e:

        st.warning(
            f"No se pudo obtener el pronóstico: {e}"
        )



# ==========================================================
# COMPARACION METEOROLOGICA POR FECHAS
# ==========================================================

@st.cache_data(ttl=21600, show_spinner=False)
def obtener_meteorologia_por_fechas(
    latitud,
    longitud,
    fecha_inicio,
    fecha_fin
):

    import math

    latitud = float(latitud)
    longitud = float(longitud)

    if not (
        math.isfinite(latitud)
        and math.isfinite(longitud)
        and -90 <= latitud <= 90
        and -180 <= longitud <= 180
    ):
        raise ValueError("Coordenadas invalidas.")

    inicio = pd.Timestamp(fecha_inicio).date()
    fin = pd.Timestamp(fecha_fin).date()

    hoy = datetime.now(
        ZoneInfo("America/Santiago")
    ).date()

    ultima_fecha = hoy - timedelta(days=7)

    if inicio > fin:
        raise ValueError(
            "La fecha inicial debe ser anterior o igual a la final."
        )

    if fin > ultima_fecha:
        raise ValueError(
            "La fecha seleccionada supera el limite historico."
        )

    cantidad_dias = (fin - inicio).days + 1

    if cantidad_dias > 366:
        raise ValueError(
            "Cada periodo puede tener hasta 366 dias."
        )

    variables = {
        "temperature_2m_min": "temperatura_min",
        "temperature_2m_max": "temperatura_max",
        "relative_humidity_2m_mean": "humedad_relativa",
        "precipitation_sum": "precipitacion",
        "shortwave_radiation_sum": "radiacion_solar",
        "wind_speed_10m_mean": "velocidad_viento"
    }

    respuesta = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": latitud,
            "longitude": longitud,
            "start_date": inicio.isoformat(),
            "end_date": fin.isoformat(),
            "daily": ",".join(variables),
            "timezone": "auto",
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm"
        },
        timeout=25,
        verify=certifi.where()
    )

    respuesta.raise_for_status()

    datos = respuesta.json()

    if datos.get("error") or not datos.get("daily"):
        raise ValueError(
            "No se recibieron datos meteorologicos."
        )

    df = pd.DataFrame(datos["daily"])

    df = df.rename(
        columns={"time": "fecha", **variables}
    )

    df["fecha"] = pd.to_datetime(
        df["fecha"], errors="coerce"
    ).dt.normalize()

    df = (
        df.dropna(subset=["fecha"])
        .drop_duplicates("fecha")
        .set_index("fecha")
        .sort_index()
    )

    for variable in variables.values():

        if variable not in df.columns:
            df[variable] = float("nan")

        df[variable] = pd.to_numeric(
            df[variable],
            errors="coerce"
        ).replace(
            [float("inf"), float("-inf")],
            float("nan")
        )

    # Conservar todos los dias solicitados,
    # incluso aquellos sin informacion.
    calendario = pd.date_range(
        inicio,
        fin,
        freq="D",
        name="fecha"
    )

    df = df.reindex(calendario)

    if not df[
        list(variables.values())
    ].notna().any().any():

        raise ValueError(
            "No existen datos para el periodo seleccionado."
        )

    return df.reset_index()

