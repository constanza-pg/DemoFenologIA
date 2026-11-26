
import streamlit as st

from contextlib import closing
from database import conectar, verificar_permiso_mediciones

from configuracion_indicadores import (
    consultar_configuracion_indicadores,
    guardar_configuracion_indicador
)


INDICADORES_UI = {
    "ndvi": ("NDVI (vigor)", "Indice"),
    "hum": ("Humedad de suelo", "%"),
    "psi": ("Potencial hídrico", "MPa"),
    "brix": ("Grados Brix", "°Bx"),
    "rend": ("Rendimiento estimado", "kg/planta")
}


def mostrar_configuracion_indicadores(usuario, vina_id):

    usuario_id = usuario["usuario_id"]
    es_admin = usuario["rol"] == "administrador"

    configuraciones = consultar_configuracion_indicadores(
        usuario_id, vina_id
    )

    with closing(conectar()) as conexion:

        verificar_permiso_mediciones(
            conexion, usuario_id, vina_id
        )

        variedades = [
            fila[0]
            for fila in conexion.execute("""
                SELECT DISTINCT variedad
                FROM plantas
                WHERE vina_id = ?
                  AND variedad IS NOT NULL
                  AND TRIM(variedad) <> ''
                ORDER BY variedad
            """, (vina_id,))
        ]

    alcance = st.radio(
        "Aplicar configuración a",
        ["Toda la viña", "Variedad específica"],
        horizontal=True,
        key="indicadores_alcance"
    )

    variedad = ""

    if alcance == "Variedad específica":

        if not variedades:
            st.info("Todavía no hay variedades registradas.")
            return

        variedad = st.selectbox(
            "Selecciona la variedad",
            variedades,
            key="indicadores_variedad"
        )

    criterios = {
        (c["parametro"], c["variedad"]): c
        for c in configuraciones
        if not c["etapa_fenologica"]
    }

    if not es_admin:
        st.info(
            "Solo el administrador puede modificar "
            "los criterios de alerta."
        )

    st.caption(
        "Puedes definir un límite mínimo, máximo o ambos. "
        "Deja vacío un límite si no deseas establecerlo."
    )

    st.info(
        "Los criterios guardados todavía no se aplican "
        "a Diagnóstico y Monitoreo. "
        "La integración se encuentra en preparación."
    )

    for parametro, (nombre, unidad) in INDICADORES_UI.items():

        criterio = criterios.get((parametro, variedad))
        origen = "Configuración propia"

        if criterio is None and variedad:
            criterio = criterios.get((parametro, ""))
            origen = "Configuración general heredada"

        if criterio is None:
            criterio = {}
            origen = "Sin configuración"

        clave = f"indicador_{vina_id}_{parametro}_{variedad}"

        with st.container(border=True):

            st.markdown(f"**{nombre}**")
            st.caption(f"Unidad: {unidad} · {origen}")

            minimo = criterio.get("valor_minimo")
            maximo = criterio.get("valor_maximo")

            with st.form(clave):

                activa = st.checkbox(
                    "Activar alerta",
                    value=bool(criterio.get("alerta_activa", 0)),
                    disabled=not es_admin
                )

                c1, c2 = st.columns(2)

                with c1:
                    minimo_nuevo = st.number_input(
                        "Valor mínimo",
                        value=minimo,
                        step=0.01,
                        format="%.2f",
                        disabled=not es_admin
                    )

                with c2:
                    maximo_nuevo = st.number_input(
                        "Valor máximo",
                        value=maximo,
                        step=0.01,
                        format="%.2f",
                        disabled=not es_admin
                    )

                guardar = st.form_submit_button(
                    "Guardar indicador",
                    disabled=not es_admin
                )

            if guardar:

                try:
                    guardar_configuracion_indicador(
                        usuario_id=usuario_id,
                        vina_id=vina_id,
                        parametro=parametro,
                        valor_minimo=minimo_nuevo,
                        valor_maximo=maximo_nuevo,
                        alerta_activa=activa,
                        variedad=variedad
                    )

                    st.success("Configuración guardada.")

                except (ValueError, PermissionError) as error:
                    st.error(str(error))
