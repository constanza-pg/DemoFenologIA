
import uuid
import json

import pandas as pd
import streamlit as st

from database import (
    conectar,
    verificar_administrador_vina
)


MIN_VINAS = 3
MIN_PLANTAS = 10


def verificar_investigador(conexion, usuario_id):

    usuario = conexion.execute("""
        SELECT u.usuario_id
        FROM usuarios u
        JOIN perfiles_investigadores p
          ON p.usuario_id = u.usuario_id
        WHERE u.usuario_id = ?
          AND u.rol = 'investigador'
          AND u.vina_id IS NULL
          AND u.activo = 1
          AND p.estado = 'aprobado'
    """, (usuario_id,)).fetchone()

    if usuario is None:
        raise PermissionError(
            "No tienes acceso al repositorio de investigacion."
        )


def consultar_autorizacion(usuario_id, vina_id):

    with conectar() as conexion:

        verificar_administrador_vina(
            conexion, usuario_id, vina_id
        )

        fila = conexion.execute("""
            SELECT autorizado
            FROM autorizaciones_investigacion
            WHERE vina_id = ?
        """, (vina_id,)).fetchone()

    return bool(fila and fila[0])


def guardar_autorizacion(
    usuario_id,
    vina_id,
    autorizado
):

    with conectar() as conexion:

        conexion.execute("BEGIN IMMEDIATE")

        verificar_administrador_vina(
            conexion, usuario_id, vina_id
        )

        codigo = "INV-" + uuid.uuid4().hex.upper()

        conexion.execute("""
            INSERT INTO autorizaciones_investigacion (
                vina_id,
                autorizado,
                codigo_publico,
                autorizado_por
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(vina_id) DO UPDATE SET
                autorizado = excluded.autorizado,
                autorizado_por = excluded.autorizado_por,
                fecha_actualizacion = CURRENT_TIMESTAMP
        """, (
            vina_id,
            int(bool(autorizado)),
            codigo,
            usuario_id
        ))


def mostrar_autorizacion(usuario_id, vina_id):

    autorizado = consultar_autorizacion(
        usuario_id, vina_id
    )

    with st.container(border=True):

        st.markdown(
            "### Participación en investigación vitivinícola"
        )

        st.write(
            "Contribuye al desarrollo de investigaciones "
            "vitivinícolas compartiendo información "
            "técnica de tu viñedo."
        )

        if autorizado:
            st.success("Participación autorizada.")
        else:
            st.info("Participación no autorizada.")

        st.markdown("**Protección de tu información**")

        st.caption(
            "No se compartirán nombres de viñas, "
            "direcciones, coordenadas exactas, usuarios, "
            "identificadores de plantas ni fotografías originales."
        )

        st.caption(
            "Los resultados se entregarán agrupados y "
            "sujetos a criterios mínimos de privacidad."
        )

        with st.expander("Información que podrá compartirse"):

            st.write(
                "- Variedades de uva.\n"
                "- Región geográfica general.\n"
                "- Mediciones vitícolas.\n"
                "- Temperatura y humedad ambiental.\n"
                "- Resultados técnicos de inteligencia artificial."
            )

        with st.form(
            f"autorizacion_investigacion_{vina_id}"
        ):

            aceptar = st.checkbox(
                "Autorizo compartir información técnica "
                "desidentificada de mi viñedo con fines "
                "de investigación.",
                value=autorizado
            )

            guardar = st.form_submit_button(
                "Guardar preferencias",
                type="primary",
                use_container_width=True
            )

            if guardar:

                guardar_autorizacion(
                    usuario_id,
                    vina_id,
                    aceptar
                )

                st.rerun()

        st.caption(
            "Puedes retirar tu autorización en cualquier "
            "momento. Esto impedirá nuevas consultas, "
            "pero no recuperará archivos descargados anteriormente."
        )


def consultar_datos_investigacion(usuario_id):

    with conectar() as conexion:

        conexion.execute("BEGIN IMMEDIATE")

        verificar_investigador(
            conexion, usuario_id
        )

        datos = pd.read_sql_query("""
            WITH base AS (

                SELECT
                    p.id AS planta_interna,
                    p.vina_id AS vina_interna,
                    p.variedad,
                    COALESCE(
                        NULLIF(TRIM(v.region), ''),
                        'Sin region registrada'
                    ) AS region,
                    strftime(
                        '%Y-%m', m.fecha_hora
                    ) AS periodo,

                    CASE
                        WHEN json_valid(m.datos_json)
                        THEN m.datos_json
                        ELSE '{}'
                    END AS valores

                FROM mediciones m

                JOIN plantas p
                  ON p.id = m.plant_id

                JOIN vinas v
                  ON v.id = p.vina_id

                JOIN autorizaciones_investigacion a
                  ON a.vina_id = p.vina_id
                 AND a.autorizado = 1

                WHERE p.variedad IS NOT NULL

            ),

            normalizado AS (

                SELECT
                    planta_interna,
                    vina_interna,
                    variedad,
                    region,
                    periodo,

                    CASE WHEN json_type(valores, '$.ndvi')
                        IN ('integer', 'real')
                        THEN json_extract(valores, '$.ndvi')
                    END AS ndvi,

                    CASE WHEN json_type(valores, '$.hum')
                        IN ('integer', 'real')
                        THEN json_extract(valores, '$.hum')
                    END AS hum,

                    CASE WHEN json_type(valores, '$.psi')
                        IN ('integer', 'real')
                        THEN json_extract(valores, '$.psi')
                    END AS psi,

                    CASE WHEN json_type(valores, '$.brix')
                        IN ('integer', 'real')
                        THEN json_extract(valores, '$.brix')
                    END AS brix,

                    CASE WHEN json_type(valores, '$.rend')
                        IN ('integer', 'real')
                        THEN json_extract(valores, '$.rend')
                    END AS rend

                FROM base

                WHERE periodo IS NOT NULL

            )

            SELECT
                region AS Region,
                variedad AS Variedad,
                periodo AS Periodo,

                COUNT(*) AS Mediciones,

                CASE WHEN
                    COUNT(DISTINCT CASE WHEN ndvi IS NOT NULL
                        THEN vina_interna END) >= ?
                    AND COUNT(DISTINCT CASE WHEN ndvi IS NOT NULL
                        THEN planta_interna END) >= ?
                    THEN ROUND(AVG(ndvi), 3)
                END AS NDVI,

                CASE WHEN
                    COUNT(DISTINCT CASE WHEN hum IS NOT NULL
                        THEN vina_interna END) >= ?
                    AND COUNT(DISTINCT CASE WHEN hum IS NOT NULL
                        THEN planta_interna END) >= ?
                    THEN ROUND(AVG(hum), 2)
                END AS Humedad,

                CASE WHEN
                    COUNT(DISTINCT CASE WHEN psi IS NOT NULL
                        THEN vina_interna END) >= ?
                    AND COUNT(DISTINCT CASE WHEN psi IS NOT NULL
                        THEN planta_interna END) >= ?
                    THEN ROUND(AVG(psi), 3)
                END AS Potencial_hidrico,

                CASE WHEN
                    COUNT(DISTINCT CASE WHEN brix IS NOT NULL
                        THEN vina_interna END) >= ?
                    AND COUNT(DISTINCT CASE WHEN brix IS NOT NULL
                        THEN planta_interna END) >= ?
                    THEN ROUND(AVG(brix), 2)
                END AS Brix,

                CASE WHEN
                    COUNT(DISTINCT CASE WHEN rend IS NOT NULL
                        THEN vina_interna END) >= ?
                    AND COUNT(DISTINCT CASE WHEN rend IS NOT NULL
                        THEN planta_interna END) >= ?
                    THEN ROUND(AVG(rend), 2)
                END AS Rendimiento

            FROM normalizado

            GROUP BY region, variedad, periodo

            HAVING COUNT(DISTINCT vina_interna) >= ?
               AND COUNT(DISTINCT planta_interna) >= ?

            ORDER BY periodo, region, variedad

        """, conexion, params=(
            (MIN_VINAS, MIN_PLANTAS) * 6
        ))

        conexion.execute("""
            INSERT INTO auditoria_investigacion (
                auditoria_id,
                usuario_id,
                accion,
                filtros_json,
                cantidad_registros
            )
            VALUES (?, ?, 'consulta', ?, ?)
        """, (
            str(uuid.uuid4()),
            usuario_id,
            json.dumps({
                "agrupacion": [
                    "region", "variedad", "mes"
                ]
            }),
            len(datos)
        ))

    return datos
