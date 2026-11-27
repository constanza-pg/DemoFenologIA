

import pandas as pd
import plotly.express as px
import streamlit as st

from database import conectar

from investigacion import (
    consultar_datos_investigacion,
    verificar_investigador,
    MIN_VINAS,
    MIN_PLANTAS
)

VARIABLES = {
    "NDVI": "NDVI",
    "Humedad": "Humedad (%)",
    "Potencial_hidrico": "Potencial hídrico (MPa)",
    "Brix": "Grados Brix (°Bx)",
    "Rendimiento": "Rendimiento (kg/planta)",
    "Temperatura_ambiental": "Temperatura ambiental (°C)",
    "Humedad_ambiental": "Humedad ambiental (%)",
    "Porcentaje_verde": "Superficie verde del racimo (%)",
    "Porcentaje_morado": "Superficie morada del racimo (%)"
}

SECCIONES = [
    "Inicio",
    "Explorador",
    "Comparativas",
    "Meteorología",
    "Descargas",
    "Mi perfil"
]


def navegar_investigacion(destino):
    st.session_state["nav_investigacion"] = destino



def mostrar_filtros(datos, prefijo):

    columnas = st.columns(4)
    resultado = datos.copy()

    campos = {
        "Region": "Región",
        "Variedad": "Variedad",
        "Temporada": "Temporada",
        "Periodo": "Período"
    }

    for columna, (campo, etiqueta) in zip(
        columnas, campos.items()
    ):

        with columna:

            opciones = sorted(
                datos[campo].dropna().unique().tolist()
            )

            seleccion = st.multiselect(
                etiqueta,
                opciones,
                key=f"{prefijo}_{campo}"
            )

            if seleccion:
                resultado = resultado[
                    resultado[campo].isin(seleccion)
                ]

    return resultado



def mostrar_aviso_privacidad():

    st.caption(
        "Repositorio de información vitivinícola agregada. "
        "Solo podrán publicarse datos de viñedos autorizados "
        "con procedencia validada."
    )

    st.caption(
        f"Cada grupo requiere al menos {MIN_VINAS} "
        f"viñedos y {MIN_PLANTAS} plantas."
    )

    st.caption(
        "Los resultados corresponden a promedios "
        "equilibrados por viñedo. Los datos de prueba "
        "no forman parte del repositorio."
    )

    st.caption(
        "Los resultados de inteligencia artificial "
        "corresponden a estimaciones experimentales."
    )


def mostrar_inicio(datos):

    from estilos_fenologia import mostrar_titulo_inicio

    mostrar_titulo_inicio(
        "Investigación vitivinícola",
        "Explora información técnica para el estudio "
        "de la viticultura y la evolución fenológica."
    )

    columnas = st.columns(3)

    for columna, titulo, campo in zip(
        columnas,
        [
            "Variedades disponibles",
            "Regiones disponibles",
            "Períodos disponibles"
        ],
        ["Variedad", "Region", "Periodo"]
    ):

        with columna:
            with st.container(border=True):
                st.metric(
                    titulo,
                    datos[campo].nunique()
                )

    st.markdown("### Accesos rápidos")

    accesos = [
        (
            "Explorador",
            "Explorar datos",
            "Consulta las variables disponibles.",
            ":material/database:"
        ),
        (
            "Comparativas",
            "Comparar variedades",
            "Estudia tendencias y diferencias.",
            ":material/monitoring:"
        ),
        (
            "Meteorología",
            "Variables ambientales",
            "Relaciona el ambiente con la viticultura.",
            ":material/cloud:"
        ),
        (
            "Descargas",
            "Exportar información",
            "Obtén datos para tus investigaciones.",
            ":material/download:"
        )
    ]

    for inicio in (0, 2):

        columnas = st.columns(2, gap="medium")

        for columna, acceso in zip(
            columnas,
            accesos[inicio:inicio+2]
        ):

            destino, titulo, descripcion, icono = acceso

            with columna:
                with st.container(border=True):

                    st.markdown(f"### {titulo}")
                    st.caption(descripcion)

                    st.button(
                        "Abrir sección",
                        key=f"investigacion_acceso_{destino}",
                        width="stretch",
                        type="primary",
                        on_click=navegar_investigacion,
                        args=(destino,)
                    )

    mostrar_aviso_privacidad()

    if datos.empty:
        st.warning(
            "Todavía no hay grupos de datos que cumplan "
            "los requisitos de publicación."
        )



def mostrar_explorador(datos):

    st.title("Explorador de datos")

    st.caption(
        "Consulta información agrupada por región, "
        "variedad, temporada y período."
    )

    with st.container(border=True):

        filtrados = mostrar_filtros(
            datos, "explorador"
        )

        variables = st.multiselect(
            "Variables de interés",
            list(VARIABLES),
            default=list(VARIABLES)[:5],
            format_func=lambda v: VARIABLES[v]
        )

        st.metric(
            "Grupos disponibles",
            len(filtrados)
        )

        if filtrados.empty:
            mostrar_aviso_privacidad()
            return

        columnas = [
            "Region", "Variedad",
            "Temporada", "Periodo",
            *variables, "Origen"
        ]

        tabla = filtrados[columnas].rename(
            columns=VARIABLES
        )

        st.dataframe(
            tabla,
            hide_index=True,
            width="stretch"
        )


def mostrar_comparativas(datos):

    st.title("Análisis comparativo")

    st.caption(
        "Compara la evolución temporal de las "
        "variables vitícolas disponibles."
    )

    with st.container(border=True):

        filtrados = mostrar_filtros(
            datos, "comparativas"
        )

        variable = st.selectbox(
            "Variable de análisis",
            list(VARIABLES),
            format_func=lambda v: VARIABLES[v]
        )

        filtrados = filtrados.dropna(
            subset=[variable]
        ).copy()

        if filtrados.empty:
            mostrar_aviso_privacidad()
            return

        filtrados["Grupo"] = (
            filtrados["Variedad"] + " · " +
            filtrados["Region"]
        )

        filtrados = filtrados.sort_values(
            "Periodo"
        )

        figura = px.line(
            filtrados,
            x="Periodo",
            y=variable,
            color="Grupo",
            markers=True,
            labels={
                variable: VARIABLES[variable],
                "Periodo": "Período"
            },
            color_discrete_sequence=[
                "#322345",
                "#84C55D",
                "#9875B8",
                "#568C40",
                "#C99BC8"
            ]
        )

        figura.update_layout(
            legend_title_text="Variedad y región",
            margin=dict(l=15, r=15, t=20, b=15)
        )

        st.plotly_chart(
            figura,
            width="stretch"
        )

        st.caption(
            "Valores agrupados por región, variedad y período. "
            "Interpretar considerando la cobertura de los datos."
        )



def mostrar_meteorologia(datos):

    st.title("Meteorología e investigación")

    st.caption(
        "Explora las relaciones entre las condiciones "
        "ambientales y las variables vitícolas."
    )

    with st.container(border=True):

        filtrados = mostrar_filtros(
            datos, "meteorologia"
        )

        if filtrados.empty:
            mostrar_aviso_privacidad()
            return

        filtrados = filtrados.copy()

        filtrados["Grupo"] = (
            filtrados["Region"] + " · " +
            filtrados["Variedad"]
        )

        filtrados = filtrados.sort_values("Periodo")

        tab_temp, tab_hum, tab_rel = st.tabs([
            "Temperatura",
            "Humedad ambiental",
            "Relaciones entre variables"
        ])

        for pestana, variable in [
            (tab_temp, "Temperatura_ambiental"),
            (tab_hum, "Humedad_ambiental")
        ]:

            with pestana:

                figura = px.line(
                    filtrados,
                    x="Periodo",
                    y=variable,
                    color="Grupo",
                    markers=True,
                    labels=VARIABLES
                )

                st.plotly_chart(
                    figura,
                    width="stretch",
                    key=f"meteo_{variable}"
                )

        with tab_rel:

            col1, col2 = st.columns(2)

            with col1:

                eje_x = st.selectbox(
                    "Variable ambiental",
                    [
                        "Temperatura_ambiental",
                        "Humedad_ambiental"
                    ],
                    format_func=lambda v: VARIABLES[v]
                )

            with col2:

                eje_y = st.selectbox(
                    "Variable vitícola",
                    [
                        "NDVI",
                        "Humedad",
                        "Potencial_hidrico",
                        "Brix",
                        "Rendimiento",
                        "Porcentaje_verde",
                        "Porcentaje_morado"
                    ],
                    format_func=lambda v: VARIABLES[v]
                )

            validos = filtrados.dropna(
                subset=[eje_x, eje_y]
            )

            if validos.empty:

                st.info(
                    "No hay valores disponibles "
                    "para esta selección."
                )

            else:

                figura = px.scatter(
                    validos,
                    x=eje_x,
                    y=eje_y,
                    color="Variedad",
                    hover_data=["Region", "Periodo"],
                    labels=VARIABLES
                )

                st.plotly_chart(
                    figura,
                    width="stretch"
                )

                st.caption(
                    "Relaciones estadísticas entre datos "
                    "agrupados. No permiten establecer "
                    "causalidad ni conclusiones agronómicas."
                )



def mostrar_descargas(datos):

    st.title("Descargas de investigación")

    st.caption(
        "Exportación de información técnica agrupada "
        "para investigaciones vitivinícolas."
    )

    with st.container(border=True):

        filtrados = mostrar_filtros(
            datos, "descargas"
        )

        st.multiselect(
            "Variables para exportar",
            list(VARIABLES),
            default=list(VARIABLES),
            format_func=lambda v: VARIABLES[v]
        )

        st.metric(
            "Grupos disponibles",
            len(filtrados)
        )

        st.info(
            "Las descargas estarán disponibles cuando "
            "existan datos autorizados y se complete "
            "la validación del repositorio."
        )

        col_csv, col_excel = st.columns(2)

        with col_csv:
            st.button(
                "Descargar CSV",
                disabled=True,
                width="stretch"
            )

        with col_excel:
            st.button(
                "Descargar Excel",
                disabled=True,
                width="stretch"
            )


def mostrar_perfil(usuario):

    st.title("Mi perfil")

    with conectar() as conexion:

        verificar_investigador(
            conexion,
            usuario["usuario_id"]
        )

        perfil = conexion.execute("""
            SELECT institucion,
                   area_investigacion,
                   finalidad,
                   estado
            FROM perfiles_investigadores
            WHERE usuario_id = ?
        """, (usuario["usuario_id"],)).fetchone()

    with st.container(border=True):

        st.markdown("### Información personal")

        st.write("**Nombre:**", usuario["nombre"])
        st.write("**Correo:**", usuario["email"])

        st.divider()

        st.markdown("### Información de investigación")

        st.write("**Institución:**", perfil[0])
        st.write("**Área:**", perfil[1])
        st.write("**Finalidad:**", perfil[2])

        st.success("Cuenta de investigador aprobada.")

    with st.container(border=True):

        st.markdown("### Compromiso de privacidad")

        st.write(
            "La información disponible está destinada "
            "exclusivamente a fines de investigación. "
            "No debe utilizarse para identificar "
            "viñedos participantes."
        )


def mostrar_interfaz_investigacion(usuario):

    with conectar() as conexion:
        verificar_investigador(
            conexion,
            usuario["usuario_id"]
        )


    from estilos_fenologia import mostrar_cabecera_fenologia

    if st.session_state.get(
        "nav_investigacion"
    ) not in SECCIONES:

        st.session_state["nav_investigacion"] = "Inicio"

    actual = st.session_state["nav_investigacion"]

    mostrar_cabecera_fenologia(
        [(seccion, seccion) for seccion in SECCIONES],
        SECCIONES.index(actual),
        navegar_investigacion
    )


    st.session_state.pop(
        "modo_demo_investigacion", None
    )

    try:

        datos = consultar_datos_investigacion(
            usuario["usuario_id"]
        )

    except PermissionError:

        st.error(
            "No tienes acceso al repositorio de investigacion."
        )

        return

    except Exception:

        st.error(
            "No fue posible consultar el repositorio. "
            "Intenta nuevamente mas tarde."
        )

        return

    if actual == "Inicio":
        mostrar_inicio(datos)

    elif actual == "Explorador":
        mostrar_explorador(datos)

    elif actual == "Comparativas":
        mostrar_comparativas(datos)

    elif actual == "Meteorología":
        mostrar_meteorologia(datos)

    elif actual == "Descargas":
        mostrar_descargas(datos)

    elif actual == "Mi perfil":
        mostrar_perfil(usuario)

