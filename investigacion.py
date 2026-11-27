import uuid
import json
import math


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




VARIABLES_REPOSITORIO = {
    "NDVI": ("ndvi", 3),
    "Humedad": ("hum", 2),
    "Potencial_hidrico": ("psi", 3),
    "Brix": ("brix", 2),
    "Rendimiento": ("rend", 2),
    "Temperatura_ambiental": (
        "temperatura_ambiental", 2
    ),
    "Humedad_ambiental": (
        "humedad_ambiental", 2
    ),
    "Porcentaje_verde": (
        "porcentaje_verde", 2
    ),
    "Porcentaje_morado": (
        "porcentaje_morado", 2
    )
}

REGIONES_PUBLICABLES = {
    "Arica y Parinacota",
    "Tarapacá",
    "Antofagasta",
    "Atacama",
    "Coquimbo",
    "Valparaíso",
    "Metropolitana",
    "Metropolitana de Santiago",
    "O’Higgins",
    "O'Higgins",
    "Libertador General Bernardo O'Higgins",
    "Maule",
    "Ñuble",
    "Biobío",
    "La Araucanía",
    "Los Ríos",
    "Los Lagos",
    "Aysén",
    "Magallanes"
}

VARIEDADES_PUBLICABLES = {
    "Cabernet Sauvignon",
    "Cabernet Franc",
    "Carménère",
    "Merlot",
    "Syrah",
    "Sauvignon Blanc",
    "Chardonnay",
    "Pinot Noir",
    "Malbec",
    "País",
    "Cinsault",
    "Carignan",
    "Moscatel",
    "Semillón",
    "Riesling",
    "Viognier",
    "Petit Verdot",
    "Tempranillo",
    "Grenache",
    "Garnacha"
}


PUBLICACION_HABILITADA = False


def consultar_datos_investigacion(usuario_id):

    columnas = [
        "Region",
        "Variedad",
        "Periodo",
        "Temporada",
        *VARIABLES_REPOSITORIO,
        "Origen"
    ]

    with conectar() as conexion:

        conexion.execute("BEGIN IMMEDIATE")

        verificar_investigador(
            conexion, usuario_id
        )

        if not PUBLICACION_HABILITADA:

            return pd.DataFrame(columns=columnas)

        datos = pd.read_sql_query("""
            WITH elegibles AS (

                SELECT
                    p.id AS planta,
                    p.vina_id AS vina,
                    TRIM(p.variedad) AS variedad,
                    TRIM(v.region) AS region

                FROM plantas p

                JOIN vinas v
                    ON v.id = p.vina_id

                JOIN autorizaciones_investigacion a
                    ON a.vina_id = v.id

                WHERE v.entorno = 'operacional'
                  AND a.autorizado = 1

            ),

            fuentes AS (

                SELECT
                    e.*,
                    strftime(
                        '%Y-%m', m.fecha_hora
                    ) AS periodo,
                    'viticola' AS fuente,

                    CASE
                        WHEN json_valid(m.datos_json)
                        THEN m.datos_json
                        ELSE '{}'
                    END AS valores

                FROM mediciones m

                JOIN elegibles e
                    ON e.planta = m.plant_id

                WHERE m.procedencia = 'real'

                UNION ALL

                SELECT
                    e.*,
                    strftime(
                        '%Y-%m', c.fecha_hora
                    ),
                    'ambiental',

                    json_object(
                        'temperatura_ambiental',
                        c.temperatura_ambiental,
                        'humedad_ambiental',
                        c.humedad_ambiental
                    )

                FROM capturas_dispositivo c

                JOIN elegibles e
                    ON e.planta = c.plant_id

                JOIN dispositivos d
                    ON d.device_id = c.device_id
                   AND d.vina_id = e.vina

                JOIN importaciones_dispositivo imp
                    ON imp.importacion_id = c.importacion_id
                   AND imp.vina_id = e.vina
                   AND imp.device_id = c.device_id

                WHERE c.procedencia = 'real'

                UNION ALL

                SELECT
                    e.*,
                    strftime(
                        '%Y-%m', i.fecha_hora
                    ),
                    'ia',

                    json_object(
                        'porcentaje_verde',
                        ai.porcentaje_verde,
                        'porcentaje_morado',
                        ai.porcentaje_morado
                    )

                FROM analisis_imagenes ai

                JOIN vista_imagenes_origen i
                    ON i.image_id = ai.image_id

                JOIN elegibles e
                    ON e.planta = i.plant_id
                   AND e.vina = i.vina_id

                LEFT JOIN mediciones m
                    ON m.measurement_id = i.measurement_id

                LEFT JOIN capturas_dispositivo c
                    ON c.captura_id = i.captura_id

                WHERE ai.procedencia = 'real'
                  AND COALESCE(
                      m.procedencia,
                      c.procedencia
                  ) = 'real'

                  AND ai.modelo = 'FenologIA - SAM 2'

                  AND ai.analisis_id = (

                      SELECT ultimo.analisis_id

                      FROM analisis_imagenes ultimo

                      WHERE ultimo.image_id = ai.image_id

                      ORDER BY
                          ultimo.fecha_analisis DESC,
                          ultimo.analisis_id DESC

                      LIMIT 1
                  )

            )

            SELECT
                f.planta,
                f.vina,
                f.variedad,
                f.region,
                f.periodo,
                f.fuente,
                j.key AS variable,
                j.value AS valor

            FROM fuentes f, json_each(f.valores) j

            WHERE f.periodo IS NOT NULL
              AND j.type IN ('integer', 'real')

        """, conexion)

        datos = datos[
            datos["region"].isin(REGIONES_PUBLICABLES)
            & datos["variedad"].isin(VARIEDADES_PUBLICABLES)
        ].copy()

        datos["region"] = datos["region"].replace({
            "Metropolitana de Santiago": "Metropolitana",
            "O’Higgins": "O'Higgins",
            "Libertador General Bernardo O'Higgins":
                "O'Higgins"
        })

        datos["valor"] = pd.to_numeric(
            datos["valor"], errors="coerce"
        )

        datos = datos.loc[
            datos["valor"].map(math.isfinite).astype(bool)
        ].copy()

        fuentes_variables = {
            "viticola": {
                "ndvi", "hum", "psi", "brix", "rend"
            },
            "ambiental": {
                "temperatura_ambiental",
                "humedad_ambiental"
            },
            "ia": {
                "porcentaje_verde",
                "porcentaje_morado"
            }
        }

        datos = datos[
            [
                variable in fuentes_variables.get(
                    fuente, set()
                )
                for fuente, variable in zip(
                    datos["fuente"],
                    datos["variable"]
                )
            ]
        ] if not datos.empty else datos

        limites = {
            "ndvi": (-1, 1),
            "hum": (0, 100),
            "humedad_ambiental": (0, 100),
            "porcentaje_verde": (0, 100),
            "porcentaje_morado": (0, 100),
            "brix": (0, 100),
            "rend": (0, float("inf"))
        }

        for variable, (minimo, maximo) in limites.items():

            datos = datos[
                (datos["variable"] != variable)
                | datos["valor"].between(minimo, maximo)
            ]

        resultados = []

        for claves, grupo in datos.groupby(
            ["region", "variedad", "periodo"]
        ):

            region, variedad, periodo = claves

            fila = {
                "Region": region,
                "Variedad": variedad,
                "Periodo": periodo,
                "Origen": "Datos operacionales agregados"
            }

            anio, mes = map(int, periodo.split("-"))

            inicio = anio if mes >= 7 else anio - 1

            fila["Temporada"] = (
                f"{inicio}-{inicio + 1}"
            )

            disponibles = 0

            for nombre, configuracion in (
                VARIABLES_REPOSITORIO.items()
            ):

                variable, decimales = configuracion

                seleccion = grupo[
                    grupo["variable"] == variable
                ]

                plantas = seleccion.groupby(
                    ["vina", "planta"]
                )["valor"].mean().reset_index()

                # Evitar contribuciones de vinas
                # representadas por una sola planta.
                conteos = plantas.groupby("vina").size()

                vinas_validas = conteos[
                    conteos >= 3
                ].index

                plantas = plantas[
                    plantas["vina"].isin(vinas_validas)
                ]

                fila[nombre] = None

                if (
                    plantas["vina"].nunique() < MIN_VINAS
                    or plantas["planta"].nunique() < MIN_PLANTAS
                ):
                    continue

                promedio_vinas = plantas.groupby(
                    "vina"
                )["valor"].mean()

                fila[nombre] = round(
                    float(promedio_vinas.mean()),
                    decimales
                )

                disponibles += 1

            if disponibles:
                resultados.append(fila)

        resultado = pd.DataFrame(
            resultados,
            columns=columnas
        )

        for variable in VARIABLES_REPOSITORIO:

            resultado[variable] = pd.to_numeric(
                resultado[variable],
                errors="coerce"
            )

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
                ],
                "metodo": "promedio_equilibrado_por_vina"
            }),
            len(resultado)
        ))

    return resultado



# Mantener deshabilitada la exportacion publica
# hasta completar la revision de privacidad.
EXPORTACIONES_HABILITADAS = False


def preparar_exportacion_investigacion(
    usuario_id,
    formato,
    filtros=None,
    variables=None
):

    import io

    if not EXPORTACIONES_HABILITADAS:
        raise PermissionError(
            "Exportaciones pendientes de validacion."
        )

    if formato not in ("csv", "xlsx"):
        raise ValueError("Formato no permitido.")

    filtros = filtros or {}

    campos = [
        "Region",
        "Variedad",
        "Temporada",
        "Periodo"
    ]

    if not set(filtros).issubset(campos):
        raise ValueError("Filtro no permitido.")

    if variables is None:
        variables = list(VARIABLES_REPOSITORIO)

    variables = list(dict.fromkeys(variables))

    if not variables:
        raise ValueError("Seleccione alguna variable.")

    if not set(variables).issubset(
        VARIABLES_REPOSITORIO
    ):
        raise ValueError("Variable no permitida.")

    datos = consultar_datos_investigacion(
        usuario_id
    )

    for campo, valores in filtros.items():

        if valores:

            datos = datos.loc[
                datos[campo].isin(valores)
            ]

    datos = datos.dropna(
        subset=variables,
        how="all"
    )

    datos = datos[
        campos + variables + ["Origen"]
    ].copy()

    if datos.empty:
        raise ValueError(
            "No existen datos publicables "
            "para esta seleccion."
        )

    if formato == "csv":

        contenido = datos.to_csv(
            index=False
        ).encode("utf-8-sig")

    else:

        memoria = io.BytesIO()

        with pd.ExcelWriter(
            memoria,
            engine="openpyxl"
        ) as writer:

            datos.to_excel(
                writer,
                sheet_name="Datos agregados",
                index=False
            )

            metodologia = pd.DataFrame({
                "Concepto": [
                    "Procedencia",
                    "Agrupacion",
                    "Metodo",
                    "Minimo de vinas",
                    "Minimo de plantas",
                    "Minimo por vina",
                    "Temporada",
                    "Inteligencia artificial",
                    "Valores vacios"
                ],
                "Descripcion": [
                    "Vinas operacionales autorizadas",
                    "Region, variedad y mes",
                    "Promedio equilibrado por vina",
                    MIN_VINAS,
                    MIN_PLANTAS,
                    3,
                    "Julio a junio",
                    "Estimaciones experimentales",
                    "Dato no disponible o no publicable"
                ]
            })

            metodologia.to_excel(
                writer,
                sheet_name="Metodologia",
                index=False
            )

        contenido = memoria.getvalue()

    with conectar() as conexion:

        conexion.execute("BEGIN IMMEDIATE")

        verificar_investigador(
            conexion, usuario_id
        )

        conexion.execute("""
            INSERT INTO auditoria_investigacion (
                auditoria_id,
                usuario_id,
                accion,
                filtros_json,
                cantidad_registros
            )
            VALUES (?, ?, 'exportacion', ?, ?)
        """, (
            str(uuid.uuid4()),
            usuario_id,
            json.dumps({
                "formato": formato,
                "filtros": filtros,
                "variables": variables,
                "evento": "archivo_preparado"
            }, ensure_ascii=False),
            len(datos)
        ))

    return contenido

