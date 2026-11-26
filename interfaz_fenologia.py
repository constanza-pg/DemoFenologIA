import json
import uuid
import threading

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from PIL import Image, ImageDraw
from streamlit_image_coordinates import (
    streamlit_image_coordinates
)

from analizador_fenologia import (
    COLORES,
    detectar_candidatos,
    segmentar_racimos,
    analizar_colores
)

from analizador import (
    preparar_carpeta_ia_experimental
)

from lectura_fotografica import (
    obtener_ruta_resultado_ia_segura
)

from database import guardar_analisis_imagen

MODELO = "FenologIA - SAM 2"
VERSION = "1.0 experimental"

BLOQUEO_IA = threading.RLock()

NOMBRES = {
    "verde": "Verde",
    "verde_amarillento": "Verde amarillento",
    "rosado_rojizo": "Rosado / rojizo",
    "morado_claro": "Morado claro",
    "morado": "Morado",
    "morado_oscuro": "Morado oscuro",
    "marron": "Marron",
    "otras_areas": "Otras areas"
}


def mostrar_resultados_fenologia(datos, clave):

    a, b, c = st.columns(3)

    a.metric(
        "Racimos",
        datos["cantidad_racimos"]
    )

    b.metric(
        "Morado total",
        f"{datos['porcentaje_morado_total']:.2f}%"
    )

    c.metric(
        "Superficie fotografica",
        f"{datos['superficie_segmentada']:.2f}%"
    )

    valores = datos["colores"]

    fig = go.Figure(go.Pie(
        labels=[NOMBRES[k] for k in COLORES],
        values=[valores[k] for k in COLORES],
        marker=dict(
            colors=list(COLORES.values())
        ),
        hole=0.58,
        sort=False,
        textinfo="percent"
    ))

    fig.update_layout(
        height=320,
        margin=dict(l=5, r=5, t=10, b=10),
        legend=dict(orientation="h"),
        showlegend=True
    )

    st.plotly_chart(fig, width="stretch", key=f"{clave}_grafico")

    tabla = pd.DataFrame([
        {
            "Color": NOMBRES[k],
            "Porcentaje (%)": valores[k]
        }
        for k in COLORES
    ])

    st.dataframe(
        tabla,
        hide_index=True,
        width="stretch"
    )

    if valores["otras_areas"] >= 20:
        st.warning(
            "Existe una proporcion importante de "
            "pixeles sin clasificacion cromatica. "
            "Revise sombras, iluminacion y mascaras."
        )

    if datos.get("detalle_racimos"):

        st.write("**Distribucion por racimo**")

        filas = []

        for racimo in datos["detalle_racimos"]:

            fila = {
                "Racimo": racimo["racimo"]
            }

            for k in COLORES:
                fila[NOMBRES[k]] = racimo["colores"][k]

            filas.append(fila)

        st.dataframe(
            pd.DataFrame(filas),
            hide_index=True,
            width="stretch"
        )

    imagen = datos.get("imagen_resultado")

    if isinstance(imagen, Image.Image):
        st.image(
            imagen,
            caption="Segmentacion y distribucion cromatica"
        )

    elif isinstance(imagen, str):

        ruta = obtener_ruta_resultado_ia_segura(
            imagen, "yolo"
        )

        if ruta is not None:
            st.image(
                str(ruta),
                caption="Analisis cromatico registrado"
            )

    st.caption(datos.get("advertencia", ""))


def mostrar_editor_fenologia(
    ruta, image_id, vina_id, origen
):

    usuario = st.session_state.get("usuario", {})

    prefijo = (
        f"fenologia_{usuario.get('usuario_id')}_"
        f"{vina_id}_{image_id}_{origen}"
    )

    if not st.toggle(
        "Analizar fotografia con IA",
        key=prefijo + "_abrir"
    ):
        return

    clave = prefijo + "_estado"

    if clave not in st.session_state:

        st.session_state[clave] = {
            "cajas": [],
            "punto": None,
            "ultimo_click": None,
            "revision": 0,
            "resultado": None,
            "mascaras": [],
            "guardado": False
        }

    estado = st.session_state[clave]

    def invalidar():
        estado["resultado"] = None
        estado["mascaras"] = []
        estado["guardado"] = False
        estado["revision"] += 1

    with Image.open(ruta) as original:
        imagen = original.convert("RGB")

    ancho, alto = imagen.size

    st.caption(
        "Detecte candidatos automaticamente o marque "
        "dos esquinas opuestas de cada racimo."
    )

    if st.button(
        "Detectar automaticamente",
        key=prefijo + "_auto"
    ):

        try:
            with st.spinner("Buscando racimos..."):
                with BLOQUEO_IA:
                    candidatos = detectar_candidatos(ruta)

            estado["cajas"] = [
                c["caja"] for c in candidatos
            ]

            estado["punto"] = None
            estado["ultimo_click"] = None

            invalidar()

            if not candidatos:
                st.info(
                    "Sin candidatos. Seleccione "
                    "los racimos manualmente."
                )
            else:
                st.warning(
                    "Candidatos experimentales. "
                    "Revise y corrija las selecciones."
                )

        except Exception as e:
            st.warning(
                "Deteccion automatica no disponible. "
                "Puede continuar manualmente."
            )

    visual = imagen.copy()
    dibujo = ImageDraw.Draw(visual)

    for i, caja in enumerate(
        estado["cajas"], 1
    ):
        dibujo.rectangle(
            caja,
            outline="#84C55D",
            width=3
        )

        dibujo.text(
            (caja[0], caja[1]),
            f"R{i}",
            fill="white",
            stroke_width=2,
            stroke_fill="#322345"
        )

    if estado["punto"] is not None:

        x, y = estado["punto"]

        dibujo.ellipse(
            (x-5, y-5, x+5, y+5),
            fill="#84C55D"
        )

    escala = min(1.0, 500 / ancho)

    dimensiones = (
        max(1, round(ancho * escala)),
        max(1, round(alto * escala))
    )

    visual = visual.resize(
        dimensiones,
        Image.Resampling.LANCZOS
    )

    click = streamlit_image_coordinates(
        visual,
        key=(
            prefijo + "_imagen_" +
            str(estado["revision"])
        )
    )

    if click and click != estado["ultimo_click"]:

        estado["ultimo_click"] = dict(click)

        cw = click.get("width") or dimensiones[0]
        ch = click.get("height") or dimensiones[1]

        x = max(0, min(
            ancho-1, click["x"] * ancho / cw
        ))

        y = max(0, min(
            alto-1, click["y"] * alto / ch
        ))

        if estado["punto"] is None:
            estado["punto"] = (x, y)

        else:
            px, py = estado["punto"]

            caja = [
                min(px, x), min(py, y),
                max(px, x), max(py, y)
            ]

            if (
                caja[2]-caja[0] >= 5
                and caja[3]-caja[1] >= 5
            ):
                estado["cajas"].append(caja)

            estado["punto"] = None

        invalidar()
        st.rerun(scope="fragment")

    if estado["punto"] is not None:
        st.info("Marque la esquina opuesta.")

    st.write(
        f"**Racimos seleccionados: "
        f"{len(estado['cajas'])}**"
    )

    c1, c2 = st.columns(2)

    if c1.button(
        "Deshacer",
        key=prefijo + "_deshacer"
    ):

        if estado["punto"] is not None:
            estado["punto"] = None

        elif estado["cajas"]:
            estado["cajas"].pop()

        invalidar()
        st.rerun(scope="fragment")

    if c2.button(
        "Limpiar seleccion",
        key=prefijo + "_limpiar"
    ):
        estado["cajas"] = []
        estado["punto"] = None

        invalidar()
        st.rerun(scope="fragment")

    if estado["cajas"]:

        eliminar = st.selectbox(
            "Eliminar una seleccion incorrecta",
            options=[0] + list(
                range(1, len(estado["cajas"])+1)
            ),
            format_func=lambda x: (
                "Seleccionar racimo"
                if x == 0 else f"Racimo {x}"
            ),
            key=(
                prefijo + "_eliminar_opcion_" +
                str(estado["revision"])
            )
        )

        if st.button(
            "Eliminar racimo seleccionado",
            key=prefijo + "_eliminar",
            disabled=eliminar == 0
        ):
            estado["cajas"].pop(eliminar-1)

            invalidar()
            st.rerun(scope="fragment")

    if st.button(
        "Segmentar y analizar colores",
        key=prefijo + "_analizar",
        type="primary",
        disabled=(
            not estado["cajas"]
            or estado["punto"] is not None
        )
    ):

        invalidar()

        try:
            with st.spinner(
                "Segmentando racimos con SAM 2..."
            ):
                with BLOQUEO_IA:

                    mascaras = segmentar_racimos(
                        ruta, estado["cajas"]
                    )

                    if not mascaras:
                        raise ValueError(
                            "No se generaron mascaras."
                        )

                    estado["mascaras"] = mascaras

                    estado["resultado"] = (
                        analizar_colores(
                            ruta, mascaras
                        )
                    )

            if len(mascaras) != len(estado["cajas"]):
                st.warning(
                    "No todas las selecciones "
                    "produjeron mascaras."
                )

        except Exception as e:
            st.error(f"No se pudo analizar: {e}")

    resultado = estado["resultado"]

    if resultado is None:
        return

    st.divider()

    st.write("**Revision del analisis**")

    mostrar_resultados_fenologia(resultado, prefijo + "_revision")

    confirmado = st.checkbox(
        "He revisado las mascaras y confirmo "
        "que corresponden a los racimos visibles.",
        key=(
            prefijo + "_confirmar_" +
            str(estado["revision"])
        )
    )

    if estado["guardado"]:
        st.success("Analisis guardado.")
        return

    if st.button(
        "Guardar analisis",
        key=prefijo + "_guardar",
        disabled=not confirmado
    ):

        archivo = None

        try:

            carpeta = (
                preparar_carpeta_ia_experimental(
                    "yolo"
                )
            )

            archivo = carpeta / (
                f"fenologia_{uuid.uuid4().hex}.png"
            )

            with archivo.open("xb") as f:
                resultado["imagen_resultado"].save(
                    f, format="PNG"
                )

            if obtener_ruta_resultado_ia_segura(
                str(archivo), "yolo"
            ) is None:
                raise ValueError(
                    "Ruta de resultado no valida."
                )

            datos = dict(resultado)

            datos["imagen_resultado"] = str(archivo)
            datos["modelo"] = MODELO
            datos["version_modelo"] = VERSION
            datos["cajas"] = estado["cajas"]
            datos["revision_usuario"] = True

            guardar_analisis_imagen(
                image_id=image_id,
                modelo=MODELO,
                version_modelo=VERSION,
                cantidad_racimos=datos[
                    "cantidad_racimos"
                ],
                porcentaje_verde=datos[
                    "colores"
                ]["verde"],
                porcentaje_envero=None,
                porcentaje_morado=datos[
                    "porcentaje_morado_total"
                ],
                etapa_fenologica=None,
                confianza=None,
                resultado_json=json.dumps(
                    datos,
                    ensure_ascii=False
                ),
                vina_id=vina_id
            )

            estado["guardado"] = True

            st.success(
                "Analisis guardado correctamente."
            )

        except Exception as e:

            st.error(
                f"No se pudo guardar: {e}"
            )
