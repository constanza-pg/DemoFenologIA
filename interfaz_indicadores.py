
import streamlit as st

from contextlib import closing
from database import conectar, verificar_permiso_mediciones

from configuracion_indicadores import (
    consultar_configuracion_indicadores,
    guardar_configuracion_indicadores
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

    st.caption(
        "Los criterios guardados se aplican a Diagnóstico, "
        "Monitoreo y la ficha individual de cada planta. "
        "Los criterios por variedad tienen prioridad sobre "
        "los generales, incluso si están desactivados."
    )

    if not configuraciones:
        st.info(
            "Todavía no hay criterios configurados. "
            "El administrador debe activar algún indicador "
            "para comenzar a evaluar alertas."
        )


    clave_formulario = (
        f"indicadores_{usuario_id}_{vina_id}_{variedad}"
    )

    clave_mensaje = clave_formulario + "_mensaje"

    if st.session_state.pop(clave_mensaje, False):
        st.success("Todos los indicadores fueron guardados.")

    cambios = []

    with st.form(clave_formulario):

        for parametro, (nombre, unidad) in INDICADORES_UI.items():

            criterio = criterios.get((parametro, variedad))
            origen = "Configuración propia"

            if criterio is None and variedad:
                criterio = criterios.get((parametro, ""))
                origen = "Configuración general heredada"

            if criterio is None:
                criterio = {}
                origen = "Sin configuración"

            clave = f"{clave_formulario}_{parametro}"

            with st.container(border=True):

                st.markdown(f"**{nombre}**")
                st.caption(f"Unidad: {unidad} · {origen}")

                activa = st.checkbox(
                    "Usar para alerta",
                    value=bool(criterio.get("alerta_activa", 0)),
                    disabled=not es_admin,
                    key=clave + "_alerta"
                )

                c1, c2 = st.columns(2)

                with c1:
                    minimo = st.number_input(
                        "Valor mínimo",
                        value=criterio.get("valor_minimo"),
                        step=0.01,
                        format="%.2f",
                        disabled=not es_admin,
                        key=clave + "_min"
                    )

                with c2:
                    maximo = st.number_input(
                        "Valor máximo",
                        value=criterio.get("valor_maximo"),
                        step=0.01,
                        format="%.2f",
                        disabled=not es_admin,
                        key=clave + "_max"
                    )

                cambios.append({
                    "parametro": parametro,
                    "valor_minimo": minimo,
                    "valor_maximo": maximo,
                    "alerta_activa": activa
                })

        guardar = st.form_submit_button(
            "Guardar todos los indicadores",
            disabled=not es_admin,
            type="primary",
            use_container_width=True
        )

    if guardar:

        try:
            guardar_configuracion_indicadores(
                usuario_id=usuario_id,
                vina_id=vina_id,
                indicadores=cambios,
                variedad=variedad
            )

            st.session_state[clave_mensaje] = True
            st.rerun()

        except (ValueError, PermissionError) as error:
            st.error(str(error))
