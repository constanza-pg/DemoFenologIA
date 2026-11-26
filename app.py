"""
Prototipo de plataforma para visualizar parámetros de plantas georreferenciadas de una viña.

Ejecutar:  streamlit run app.py

Estructura del archivo:
  1. CONFIGURACIÓN  -> lo que más se edita (parámetros, cuarteles, fechas, alertas, fondos de mapa)
  2. DATOS          -> datos de ejemplo o lectura de un CSV subido
  3. INTERFAZ       -> barra derecha (capas, filtros, fecha, ficha) y mapa
"""

from lectura_fotografica import (
    obtener_ruta_fotografia_segura,
    obtener_ruta_resultado_ia_segura
)

from pathlib import Path
import uuid
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from distribucion_provisional import distribuir_plantas
from mapa_estructural import (
    preparar_estructura_mapa,
    preparar_datos_fecha,
    preparar_ultimos_registros
)
from validacion_csv_estructural import validar_csv_estructural
from database import (
    importar_csv_estructural,
    consultar_plantas_registradas
)
from modulos.ui.monitoreo_vina import render_monitoreo_vina
from modulos.ui.galeria_ia import render_galeria_ia
import json
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import ssl
import certifi

from database import (
    inicializar_bd,
    actualizar_esquema_capturas_dispositivo,
    actualizar_esquema_imagenes_dispositivo,
    actualizar_vista_imagenes_origen,
    guardar_plantas,
    guardar_mediciones,
    consultar_datos,
    importar_xlsx_mediciones_seguro,
    actualizar_esquema_transferencias,
    actualizar_esquema_multi_vina,
    registrar_imagen,
    consultar_imagenes_por_planta,
    consultar_todas_las_imagenes,
    guardar_analisis_imagen,
    consultar_analisis_por_imagen,
    conectar,
    consultar_vina,
    actualizar_ubicacion_vina,
    consultar_estaciones_cercanas,
    consultar_mediciones_meteorologicas,
    consultar_mediciones_dmc_precipitacion,
    consultar_mediciones_dmc_re1034,
    actualizar_esquema_claros,
    guardar_claro_monitoreado,
    consultar_claro_monitoreado,
)

from interfaz_fenologia import (
    mostrar_editor_fenologia,
    mostrar_resultados_fenologia
)

from autenticacion import verificar_usuario, crear_usuario, registrar_vina_administrador, consultar_usuario_activo

inicializar_bd()
from database import inicializar_investigacion
inicializar_investigacion()

from configuracion_indicadores import (
    inicializar_configuracion_indicadores
)

inicializar_configuracion_indicadores()

actualizar_esquema_transferencias()

actualizar_esquema_multi_vina()

actualizar_esquema_claros()

actualizar_esquema_capturas_dispositivo()

actualizar_esquema_imagenes_dispositivo()

actualizar_vista_imagenes_origen()

# =====================================================================
# 1. CONFIGURACIÓN
# =====================================================================
NOMBRE_VINA = "FenologIA"
LAT0, LON0 = -34.65, -71.38          # esquina noroeste del campo (cámbiala por la real)
ESP_FILA, ESP_PLANTA = 2.4, 1.2      # metros entre filas y entre plantas

# Cuarteles de ejemplo: posición (x, y) y tamaño en metros.
# "variedades" = lista de (última fila hasta donde llega esa variedad, nombre).
CUARTELES = {
    "A": dict(x=0,   y=0,  ancho=110, alto=72, variedades=[(20, "Cabernet Sauvignon"), (30, "Merlot")]),
    "B": dict(x=124, y=0,  ancho=110, alto=72, variedades=[(22, "Carménère"), (30, "Cabernet Franc")]),
    "C": dict(x=0,   y=88, ancho=110, alto=72, variedades=[(30, "Syrah")]),
    "D": dict(x=124, y=88, ancho=110, alto=72, variedades=[(18, "Sauvignon Blanc"), (30, "Chardonnay")]),
}

FECHAS = ["2025-03-18", "2025-09-15", "2025-12-10", "2026-02-12", "2026-03-18", "2026-10-12"]

# Parámetros (capas). La clave es el nombre de la columna en los datos.
PARAMETROS = {
    "ndvi": dict(nombre="NDVI (vigor)",        unidad="",          rango=(0.35, 0.88), archivo="ndvi_dron.tif",        dec=2),
    "hum":  dict(nombre="Humedad de suelo",    unidad="%",         rango=(12, 34),     archivo="sensores_suelo.csv",   dec=1),
    "psi":  dict(nombre="Potencial hídrico",   unidad="MPa",       rango=(-1.6, -0.4), archivo="camara_presion.csv",   dec=2),
    "brix": dict(nombre="Grados Brix",         unidad="°Bx",       rango=(18, 25.5),   archivo="muestreo_madurez.xlsx", dec=1),
    "rend": dict(nombre="Rendimiento estimado", unidad="kg/planta", rango=(1.2, 4.6),   archivo="conteo_racimos.csv",  dec=1),
}

# Alertas: parámetro -> (operador, umbral). Se muestran en la ficha de la planta.
ALERTAS = {"ndvi": ("<", 0.50), "psi": ("<", -1.30)}

# Variación estacional de ejemplo (solo para generar datos falsos), una por fecha.
ESTACIONAL = {
    "ndvi": [.02, -.20, -.05, .10, .04, -.08],
    "hum":  [.05, -.10, -.20, -.05, 0, .10],
    "psi":  [-.05, .05, -.15, -.10, -.12, .10],
    "brix": [.15, -.30, -.25, -.10, .15, -.28],
    "rend": [.04, -.15, -.05, .08, .02, -.10],
}

# Fondos de mapa. El satélite necesita internet (teselas de Esri; revisa sus términos de uso).
FONDOS = {
    "Satélite": dict(style="white-bg", layers=[dict(
        below="traces", sourcetype="raster", sourceattribution="Esri, Maxar, Earthstar Geographics",
        source=["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
        maxzoom=19)]),
    "Mapa de calles": dict(style="open-street-map", layers=[]),
}

# Columnas que NO son parámetros cuando se sube un CSV propio.
COLUMNAS_BASE = ["id", "fecha", "lat", "lon", "cuartel", "variedad", "fila", "planta"]


# =====================================================================
# 2. DATOS
# =====================================================================
@st.cache_data
def generar_datos(semilla: int = 11) -> pd.DataFrame:
    """Datos de ejemplo: una fila por planta y fecha."""
    rng = np.random.default_rng(semilla)
    bloques = []
    for cid, c in CUARTELES.items():
        nf, npl = int(c["alto"] // ESP_FILA), int(c["ancho"] // ESP_PLANTA)
        f, i = np.meshgrid(np.arange(nf), np.arange(npl), indexing="ij")
        f, i = f.ravel(), i.ravel()
        variedad = [next(v for limite, v in c["variedades"] if r + 1 <= limite) for r in f]
        bloques.append(pd.DataFrame(dict(cuartel=cid, variedad=variedad, fila=f + 1, planta=i + 1,
                                         x=c["x"] + 1 + i * ESP_PLANTA, y=c["y"] + 1 + f * ESP_FILA)))
    pl = pd.concat(bloques, ignore_index=True)
    pl["id"] = pl.cuartel + "-F" + pl.fila.astype(str).str.zfill(2) + "-P" + pl.planta.astype(str).str.zfill(3)
    pl["lat"] = LAT0 - pl.y / 111320
    pl["lon"] = LON0 + pl.x / (111320 * np.cos(np.radians(LAT0)))

    tablas = []
    for d, fecha in enumerate(FECHAS):
        t = pl.drop(columns=["x", "y"]).copy()
        t["fecha"] = fecha
        for p, (k, P) in enumerate(PARAMETROS.items()):
            base = .5 + .28 * np.sin(pl.x / 41 + p * .5) + .22 * np.cos(pl.y / 33 - p * .4) + .12 * np.sin((pl.x + pl.y) / 15 + p * .3)
            v = base * .9 + rng.normal(0, .06, len(pl)) + ESTACIONAL[k][d] + .1 * np.sin(pl.x / 23 + pl.y / 31 + d * 1.7 + p)
            a, b = P["rango"]
            t[k] = a + np.clip(v, 0, 1) * (b - a)
        tablas.append(t)
    return pd.concat(tablas, ignore_index=True)


def leer_csv(archivo) -> pd.DataFrame:
    """CSV propio. Obligatorias: id, fecha. Opcionales: lat, lon, cuartel, variedad, fila, planta.
    Todas las demás columnas numéricas se tratan como parámetros (capas)."""
    df = pd.read_csv(archivo)
    faltan = [c for c in ["id", "fecha"] if c not in df.columns]
    if faltan:
        st.error(f"Al CSV le faltan las columnas: {', '.join(faltan)}")
        st.stop()
    df["fecha"] = df["fecha"].astype(str)
    for c in ["cuartel", "variedad"]:
        if c not in df.columns:
            df[c] = "Sin dato"
    return df


def info(k: str) -> dict:
    """Metadatos de un parámetro; si viene de un CSV propio y no está en PARAMETROS, se infiere."""
    return PARAMETROS.get(k, dict(nombre=k, unidad="", archivo="archivo subido", dec=2))


def fmt(v, k) -> str:
    P = info(k)
    return f"{v:.{P['dec']}f}".replace(".", ",") + (f" {P['unidad']}" if P["unidad"] else "")




# =====================================================================
# 3. INTERFAZ
# =====================================================================
st.set_page_config(page_title=f"{NOMBRE_VINA} · Monitoreo vitícola", layout="wide")




st.markdown("""
<style>

:root {
    --fenologia-morado: #322345;
    --fenologia-verde: #84C55D;
    --fenologia-borde: #E4E7E2;
}

.stApp {
    background-color: #FFFFFF;
}

.block-container {
    max-width: 1500px !important;
    margin-left: auto !important;
    margin-right: auto !important;
    padding-top: 1.2rem !important;
    padding-bottom: 2rem !important;
}

.fenologia-logo {
    color: #000000 !important;
    font-weight: 700 !important;
    letter-spacing: -0.04em;
}

.fenologia-logo span {
    color: #322345 !important;
}

h1 {
    font-size: 2rem !important;
    font-weight: 650 !important;
    letter-spacing: -0.025em;
}

h2 {
    font-size: 1.45rem !important;
    font-weight: 600 !important;
}

h3 {
    font-size: 1.15rem !important;
    font-weight: 600 !important;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px !important;
    border-color: #E4E7E2 !important;
}

[data-testid="stMetric"] {
    background-color: #F6F7F5;
    border-radius: 10px;
    padding: 14px;
}

[data-testid="stMetricValue"] {
    color: #322345;
    font-size: 1.65rem !important;
    font-weight: 600;
}

[data-testid="stMetricLabel"] {
    font-weight: 500;
}

button[kind="primary"]:not(:disabled),
button[kind="primaryFormSubmit"]:not(:disabled) {
    background-color: #322345 !important;
    border-color: #322345 !important;
    color: #FFFFFF !important;
    border-radius: 8px !important;
    box-shadow: none !important;
}

button[kind="primary"]:not(:disabled):hover,
button[kind="primaryFormSubmit"]:not(:disabled):hover {
    background-color: #49365E !important;
    border-color: #49365E !important;
}

[data-testid="stTabs"] [role="tab"] {
    font-weight: 500;
    padding-left: 14px;
    padding-right: 14px;
}

[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #322345 !important;
    font-weight: 650 !important;
    border-bottom: 3px solid #84C55D !important;
}

[data-baseweb="tab-highlight"] {
    background-color: #84C55D !important;
}

[data-testid="stExpander"] details {
    border-radius: 10px !important;
    border-color: #E4E7E2 !important;
}

[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
}

[data-testid="stImage"] img {
    border-radius: 8px;
}

div.st-key-dm18_separador {
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}

@media (max-width: 768px) {
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    h1 {
        font-size: 1.65rem !important;
    }
}

</style>
""", unsafe_allow_html=True)



# =========================================================
# INICIO DE SESIÓN
# =========================================================

if "usuario" not in st.session_state:
    st.session_state["usuario"] = None

if st.session_state["usuario"] is None:

    import os

    registro_habilitado = False

    st.markdown("""
    <style>
    [data-testid="stSidebar"] {
        display: none;
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    .block-container {
        max-width: 760px !important;
        margin: 0 auto !important;
        width: 100% !important;
        padding-top: 4vh !important;
        padding-bottom: 3rem;
    }

    .fenologia-logo {
        text-align: center;
        font-size: clamp(3rem, 7vw, 5rem);
        font-weight: 750;
        letter-spacing: -2px;
        margin-bottom: 0.3rem;
        color: #000000;
    }

    .fenologia-logo span {
        color: #322345;
    }

    div[data-testid="stForm"] {
        border: none;
        padding: 0;
    }

    div.stButton > button,
    div[data-testid="stFormSubmitButton"] button {
        background-color: #322345;
        color: white;
        border-color: #322345;
        border-radius: 10px;
    }

    div.stButton > button:hover,
    div[data-testid="stFormSubmitButton"] button:hover {
        background-color: #49345F;
        color: white;
        border-color: #49345F;
    }

    div[data-testid="stRadio"] {
        display: flex;
        justify-content: center;
    }

    div[data-testid="stRadio"] input {
        accent-color: #322345;
    }

    div[data-testid="stRadio"] {
        display: flex !important;
        justify-content: center !important;
    }

    div[data-testid="stRadio"] [role="radiogroup"] {
        justify-content: center !important;
        gap: 1rem !important;
        flex-wrap: wrap !important;
    }

    div[data-testid="stRadio"] label {
        padding: 0.5rem;
    }

    div[data-testid="stFormSubmitButton"] button {
        min-height: 2.8rem;
    }

</style>
    """, unsafe_allow_html=True)

    st.markdown(
        '<div class="fenologia-logo">Fenolog<span>IA</span></div>',
        unsafe_allow_html=True
    )


    st.markdown(
        "<p style='text-align:center;color:#777;'>"
        "Monitoreo e investigación vitivinícola"
        "</p>",
        unsafe_allow_html=True
    )


    st.markdown("""
    <style>

    .st-key-perfiles_acceso {
        max-width: 560px;
        margin: 0 auto;
    }

    .st-key-perfiles_acceso div.stButton > button {
        background-color: #FFFFFF !important;
        color: #322345 !important;
        border: 1.5px solid #DDD9E2 !important;
        border-radius: 14px !important;
        min-height: 60px !important;
        width: 100% !important;
        padding: 8px 10px !important;
        transition: all 0.2s ease;
    }

    .st-key-perfiles_acceso div.stButton > button:hover {
        background-color: #F4F8EF !important;
        border-color: #84C55D !important;
        color: #322345 !important;
    }

    .st-key-perfiles_acceso div.stButton > button[kind="primary"] {
        background-color: #F0F7E9 !important;
        border: 2px solid #84C55D !important;
        color: #322345 !important;
    }

    .st-key-perfiles_acceso button p {
        text-align: center !important;
        font-size: 0.95rem !important;
        line-height: 1.6 !important;
    }

    .st-key-opcion_acceso {
        width: 100%;
        margin: 0 auto;
    }

    .st-key-opcion_acceso [role="radiogroup"] {
        width: 100%;
        justify-content: center !important;
        gap: 1.5rem !important;
    }

    </style>
    """, unsafe_allow_html=True)

    if "tipo_acceso_fenologia" not in st.session_state:
        st.session_state["tipo_acceso_fenologia"] = (
            "Gestión vitícola"
        )

    def seleccionar_perfil_acceso(perfil):
        st.session_state["tipo_acceso_fenologia"] = perfil

    st.markdown(
        "<p style='text-align:center;"
        "font-weight:600;color:#322345;"
        "margin-top:12px;margin-bottom:4px;'>"
        "Selecciona tu perfil</p>",
        unsafe_allow_html=True
    )

    tipo_acceso = st.session_state[
        "tipo_acceso_fenologia"
    ]

    with st.container(key="perfiles_acceso"):

        col_viticola, col_investigacion = st.columns(
            2, gap="medium"
        )

        with col_viticola:

            st.button(
                "Gestión vitícola",
                icon=":material/agriculture:",
                key="seleccionar_perfil_viticola",
                type=(
                    "primary"
                    if tipo_acceso == "Gestión vitícola"
                    else "secondary"
                ),
                width="stretch",
                on_click=seleccionar_perfil_acceso,
                args=("Gestión vitícola",)
            )

        with col_investigacion:

            st.button(
                "Investigación vitivinícola",
                icon=":material/science:",
                key="seleccionar_perfil_investigacion",
                type=(
                    "primary"
                    if tipo_acceso == "Investigación vitivinícola"
                    else "secondary"
                ),
                width="stretch",
                on_click=seleccionar_perfil_acceso,
                args=("Investigación vitivinícola",)
            )

    st.markdown(
        "<div style='height:12px;'></div>",
        unsafe_allow_html=True
    )

    opcion_acceso = st.radio(
        "Acceso a FenologIA",
        ["Iniciar sesión", "Crear cuenta"],
        horizontal=True,
        label_visibility="collapsed",
        key="opcion_acceso"
    )

    if opcion_acceso == "Iniciar sesión":

        with st.form("formulario_login"):

            email = st.text_input(
                "Correo electrónico"
            )

            password = st.text_input(
                "Contraseña",
                type="password"
            )

            ingresar = st.form_submit_button(
                "🍇 Ingresar",
                use_container_width=True
            )

            if ingresar:
                try:
                    usuario = verificar_usuario(email, password)

                    if usuario:
                        es_investigador = (
                            usuario["rol"] == "investigador"
                        )

                        acceso_investigacion = (
                            tipo_acceso ==
                            "Investigación vitivinícola"
                        )

                        if es_investigador != acceso_investigacion:
                            st.error(
                                "Selecciona el tipo de acceso "
                                "correspondiente a tu cuenta."
                            )
                        else:
                            st.session_state.clear()
                            st.session_state["usuario"] = usuario
                            st.rerun()
                    else:
                        st.error(
                            "Correo o contraseña incorrectos."
                        )

                except Exception:
                    st.error(
                        "No se pudo iniciar sesión. "
                        "Inténtalo nuevamente."
                    )


    elif tipo_acceso == "Investigación vitivinícola":

        from autenticacion import registrar_investigador

        with st.container(border=True):

            st.subheader("Solicitud de acceso")

            st.caption(
                "Completa tus antecedentes académicos o "
                "profesionales para solicitar acceso."
            )

            with st.form("registro_investigador"):

                col_a_0, col_b_0 = st.columns(2)
                with col_a_0:
                    nombre = st.text_input("Nombre completo")
                with col_b_0:
                    email = st.text_input("Correo electrónico")

                col_a_1, col_b_1 = st.columns(2)
                with col_a_1:
                    institucion = st.text_input(
                        "Institución u organización"
                    )
                with col_b_1:
                    area = st.text_input(
                        "Área de investigación"
                    )

                finalidad = st.text_area(
                    "Finalidad de la investigación",
                    placeholder=(
                        "Describe brevemente el uso "
                        "que darás a los datos."
                    )
                )

                col_a_2, col_b_2 = st.columns(2)
                with col_a_2:
                    password = st.text_input(
                        "Contraseña",
                        type="password",
                        help="Mínimo 10 caracteres."
                    )
                with col_b_2:
                    confirmar = st.text_input(
                        "Confirmar contraseña",
                        type="password"
                    )

                aceptar = st.checkbox(
                    "Me comprometo a utilizar los datos "
                    "exclusivamente con fines de investigación "
                    "y a respetar la privacidad de los viñedos."
                )

                enviar = st.form_submit_button(
                    "Enviar solicitud",
                    use_container_width=True
                )

                if enviar:

                    if not aceptar:
                        st.warning(
                            "Debes aceptar el compromiso de uso."
                        )

                    else:
                        try:
                            registrar_investigador(
                                nombre,
                                email,
                                institucion,
                                area,
                                finalidad,
                                password,
                                confirmar
                            )

                            st.success(
                                "Solicitud registrada correctamente. "
                                "Tu cuenta quedará pendiente "
                                "de aprobación."
                            )

                        except ValueError as e:
                            st.error(str(e))

                        except Exception:
                            st.error(
                                "No se pudo registrar la solicitud."
                            )

    elif registro_habilitado:

        with st.form("formulario_registro_vina"):

            nombre_vina = st.text_input(
                "Nombre de la viña"
            )

            nombre_administrador = st.text_input(
                "Nombre del administrador"
            )

            email_registro = st.text_input(
                "Correo electrónico"
            )

            password_registro = st.text_input(
                "Contraseña",
                type="password",
                help="Debe contener al menos 10 caracteres."
            )

            confirmar_password = st.text_input(
                "Confirmar contraseña",
                type="password"
            )

            registrar = st.form_submit_button(
                "🍇 Crear cuenta",
                use_container_width=True
            )

            if registrar:
                try:
                    registrar_vina_administrador(
                        nombre_vina,
                        nombre_administrador,
                        email_registro,
                        password_registro,
                        confirmar_password
                    )

                    st.success(
                        "Tu viña y cuenta administradora "
                        "se registraron correctamente. "
                        "Ahora puedes iniciar sesión."
                    )

                except ValueError as e:
                    st.error(str(e))

                except Exception:
                    st.error(
                        "No se pudo completar el registro. "
                        "Inténtalo nuevamente."
                    )

    else:
        st.info(
            "La creación de cuentas estará disponible "
            "cuando finalicemos las pruebas de seguridad."
        )

    st.stop()

# Validar el estado vigente de la cuenta en cada ejecución
usuario_sesion = st.session_state["usuario"]

usuario_vigente = consultar_usuario_activo(
    usuario_sesion.get("usuario_id")
)

if usuario_vigente is None:
    st.session_state.clear()
    st.warning(
        "Tu sesión ha finalizado porque tu cuenta "
        "ya no está activa. Contacta al administrador."
    )
    st.stop()

# Evitar conservar selecciones de otra viña o rol
if (
    usuario_sesion.get("vina_id") != usuario_vigente["vina_id"]
    or usuario_sesion.get("rol") != usuario_vigente["rol"]
):
    st.session_state.clear()

st.session_state["usuario"] = usuario_vigente

# Datos actualizados del usuario autenticado
usuario_actual = st.session_state["usuario"]


# Separacion de perfiles de investigacion y gestion viticola.
if usuario_actual["rol"] == "investigador":

    from interfaz_investigacion import (
        mostrar_interfaz_investigacion
    )

    mostrar_interfaz_investigacion(usuario_actual)

    st.stop()

VINA_ID_ACTUAL = usuario_actual["vina_id"]
NOMBRE_USUARIO = usuario_actual["nombre"]

vina_actual = consultar_vina(VINA_ID_ACTUAL)

if vina_actual is not None:
    NOMBRE_VINA = vina_actual[1]

st.markdown("<style>.block-container{padding-top:1.2rem}</style>", unsafe_allow_html=True)

# =========================================================
# NAVEGACIÓN PRINCIPAL
# =========================================================

SECCIONES = [
    "FenologIA",
    "Resumen y diagnóstico inteligente",
    "Mapa y monitoreo de plantas",
    "Meteorología y precipitaciones",
    "Fotografías y análisis IA",
    "Configuración de mi viña",
]

opciones_superiores = [
    ("FenologIA", "Inicio"),
    ("Resumen y diagnóstico inteligente", "Diagnóstico"),
    ("Mapa y monitoreo de plantas", "Monitoreo"),
    ("Meteorología y precipitaciones", "Meteorología"),
    ("Fotografías y análisis IA", "Fotografías e IA"),
    ("Configuración de mi viña", "Mi viña"),
]

if st.session_state.get("navegacion_principal") not in SECCIONES:
    st.session_state["navegacion_principal"] = "FenologIA"

def navegar_fenologia(destino):
    st.session_state["navegacion_principal"] = destino

indice_activo = SECCIONES.index(
    st.session_state["navegacion_principal"]
)


from estilos_fenologia import mostrar_cabecera_fenologia

mostrar_cabecera_fenologia(
    opciones_superiores,
    indice_activo,
    navegar_fenologia
)

seccion_actual = st.session_state["navegacion_principal"]

# Se conservan temporalmente los controles existentes.
with st.sidebar:
    st.caption(f"Sesión: {NOMBRE_USUARIO}")

    if st.button("Cerrar sesión"):
        st.session_state.clear()
        st.rerun()


    if usuario_actual["rol"] == "administrador":

        from vista_previa_csv import preparar_vista_previa_csv
        from database import importar_csv_conservador
        import hashlib

        st.subheader("Importación de plantas y mediciones")

        st.caption(
            "La importación conserva los registros existentes "
            "y agrega únicamente plantas y mediciones nuevas."
        )

        subido = st.file_uploader(
            "Seleccionar archivo CSV",
            type=["csv"],
            key="cargador_csv_plantas"
        )

        if subido is not None:

            try:
                contenido_csv = subido.getvalue()
                identificador_csv = hashlib.sha256(
                    contenido_csv
                ).hexdigest()

                datos_entrada = leer_csv(subido)

                vista = preparar_vista_previa_csv(
                    datos_entrada,
                    VINA_ID_ACTUAL,
                    usuario_actual["usuario_id"]
                )

                resumen = vista["resumen"]
                discrepancias = vista["discrepancias"]

                st.markdown("#### Vista previa")

                col1, col2, col3, col4 = st.columns(4)

                col1.metric(
                    "Plantas nuevas",
                    resumen["plantas_nuevas"]
                )

                col2.metric(
                    "Plantas existentes",
                    resumen["plantas_existentes"]
                )

                col3.metric(
                    "Mediciones nuevas",
                    resumen["mediciones_nuevas"]
                )

                col4.metric(
                    "Mediciones existentes",
                    resumen["mediciones_existentes"]
                )

                st.dataframe(
                    vista["datos_validados"].head(20),
                    use_container_width=True
                )

                if not discrepancias.empty:

                    st.warning(
                        f"Se detectaron {len(discrepancias)} "
                        "discrepancias estructurales. "
                        "Las plantas existentes no serán modificadas."
                    )

                    st.dataframe(
                        discrepancias,
                        use_container_width=True
                    )

                st.info(
                    "Los registros existentes serán omitidos. "
                    "La importación solo incorporará información nueva."
                )

                confirmacion = st.checkbox(
                    "Confirmo que revisé el archivo y autorizo "
                    "la importación conservadora.",
                    key=f"confirmar_csv_{identificador_csv}"
                )

                if st.button(
                    "Importar registros nuevos",
                    key="ejecutar_importacion_conservadora",
                    disabled=not confirmacion
                ):

                    resultado = importar_csv_conservador(
                        vista["datos_validados"],
                        VINA_ID_ACTUAL,
                        usuario_actual["usuario_id"]
                    )

                    st.success(
                        "Importación finalizada correctamente."
                    )

                    st.write(
                        "Plantas creadas:",
                        resultado["plantas_creadas"]
                    )

                    st.write(
                        "Plantas omitidas:",
                        resultado["plantas_omitidas"]
                    )

                    st.write(
                        "Mediciones creadas:",
                        resultado["mediciones_creadas"]
                    )

                    st.write(
                        "Mediciones omitidas:",
                        resultado["mediciones_omitidas"]
                    )

            except (ValueError, PermissionError) as error:
                st.error(str(error))

            except Exception as error:
                st.error(
                    "No fue posible completar la operación: "
                    f"{error}"
                )

    # Si no hay CSV, recuperar solamente los datos de esta viña
    datos = consultar_datos(VINA_ID_ACTUAL)

    if seccion_actual == "Mapa y monitoreo de plantas":

        st.header("Mapa")

        fondo = st.radio(
            "Fondo",
            list(FONDOS)
        )

        busca = st.text_input(
            "Buscar planta por ID",
            placeholder="Ej: A-F05-P020"
        ).strip()

    else:
        fondo = list(FONDOS)[0]
        busca = ""

# Pantalla inicial de la viña autenticada
if seccion_actual == "FenologIA":

    from estilos_fenologia import mostrar_titulo_inicio

    mostrar_titulo_inicio(
        NOMBRE_VINA,
        "Monitoreo y gestión vitícola"
    )

    accesos = [
        (
            "Monitoreo de plantas",
            "Explora el mapa y consulta tus plantas.",
            "Explorar mapa",
            "Mapa y monitoreo de plantas"
        ),
        (
            "Diagnóstico",
            "Consulta indicadores y alertas de tu viña.",
            "Ver diagnóstico",
            "Resumen y diagnóstico inteligente"
        ),
        (
            "Fotografías e IA",
            "Consulta fotografías y resultados de análisis.",
            "Abrir galería",
            "Fotografías y análisis IA"
        ),
        (
            "Meteorología",
            "Consulta las condiciones meteorológicas.",
            "Ver meteorología",
            "Meteorología y precipitaciones"
        ),
    ]

    for fila in range(0, len(accesos), 2):

        columnas = st.columns(2, gap="medium")

        for indice, acceso in enumerate(
            accesos[fila:fila + 2]
        ):

            titulo, descripcion, boton, destino = acceso

            with columnas[indice]:

                with st.container(border=True):

                    st.markdown(f"### {titulo}")
                    st.caption(descripcion)

                    st.button(
                        boton,
                        key=f"inicio_acceso_{fila + indice}",
                        type="primary",
                        use_container_width=True,
                        on_click=navegar_fenologia,
                        args=(destino,)
                    )

    with st.container(border=True):
        st.markdown("### Actualizar información")

        col_xlsx, col_zip = st.columns(2)

        with col_xlsx:

            if st.button(
                "Cargar xlsx fenologia",
                key="inicio_cargar_xlsx",
                type="primary",
                use_container_width=True
            ):
                st.session_state["fenologia_acceso_carga"] = "xlsx"
                navegar_fenologia("Mapa y monitoreo de plantas")
                st.rerun()

        with col_zip:

            if st.button(
                "Importar ZIP del dispositivo",
                key="inicio_cargar_zip",
                type="primary",
                use_container_width=True
            ):
                st.session_state["fenologia_acceso_carga"] = "zip"
                navegar_fenologia("Mapa y monitoreo de plantas")
                st.rerun()


    with st.container(border=True):

        st.markdown("### Tutoriales y presentación")

        st.caption(
            "Conoce FenologIA y aprende a utilizar "
            "cada sección de la plataforma."
        )

        @st.dialog("Centro de ayuda FenologIA", width="large")
        def abrir_centro_ayuda():

            st.markdown("### Bienvenido a FenologIA")

            st.write(
                "Plataforma de monitoreo vitícola que integra "
                "información de plantas, meteorología, "
                "fotografías e inteligencia artificial."
            )

            recursos = Path(__file__).resolve().parent / "tutoriales"

            st.markdown("### Presentación de la plataforma")

            presentacion = recursos / "presentacion.pdf"

            if presentacion.is_file():
                st.download_button(
                    "Descargar presentación",
                    data=presentacion.read_bytes(),
                    file_name="Presentacion_FenologIA.pdf",
                    mime="application/pdf",
                    key="descargar_presentacion_fenologia"
                )
            else:
                st.caption("Presentación próximamente disponible.")

            st.divider()
            st.markdown("### Videotutoriales")

            secciones = [
                (
                    "Diagnóstico",
                    "Interpreta los indicadores y alertas de tu viña.",
                    "02_diagnostico.mp4"
                ),
                (
                    "Mapa y monitoreo",
                    "Consulta plantas e importa nuevas mediciones.",
                    "03_monitoreo.mp4"
                ),
                (
                    "Meteorología",
                    "Consulta condiciones actuales, historial y pronóstico.",
                    "04_meteorologia.mp4"
                ),
                (
                    "Fotografías e IA",
                    "Revisa fotografías y realiza análisis de racimos.",
                    "05_fotografias_ia.mp4"
                ),
                (
                    "Mi viña",
                    "Configura y administra la información de tu viña.",
                    "06_mi_vina.mp4"
                )
            ]

            for titulo, descripcion, nombre in secciones:

                with st.container(border=True):

                    st.markdown(f"**{titulo}**")
                    st.caption(descripcion)

                    video = recursos / nombre

                    if video.is_file():
                        st.video(str(video))
                    else:
                        st.caption("Videotutorial próximamente disponible.")

            if st.button(
                "Cerrar ventana",
                key="cerrar_centro_ayuda"
            ):
                st.rerun()

        if st.button(
            "Ver tutoriales y presentación",
            key="inicio_centro_ayuda",
            icon=":material/school:",
            type="primary",
            width="stretch"
        ):
            abrir_centro_ayuda()

    st.stop()


# =========================================================
# DATOS GEOGRÁFICOS DE LA VIÑA ACTUAL
# =========================================================

vina_actual = consultar_vina(VINA_ID_ACTUAL)

if vina_actual is not None:
    nombre_vina_actual = vina_actual[1]
    ubicacion_guardada = vina_actual[2]
    latitud_guardada = vina_actual[3]
    longitud_guardada = vina_actual[4]
else:
    nombre_vina_actual = NOMBRE_VINA
    ubicacion_guardada = None
    latitud_guardada = None
    longitud_guardada = None

# Coordenadas exclusivas para visualización.
# Se calculan después de recuperar la ubicación de la viña.
# No se guardan en SQLite.
if not datos.empty:
    datos = distribuir_plantas(
        datos,
        latitud_vina=latitud_guardada,
        longitud_vina=longitud_guardada,
        esp_fila=ESP_FILA,
        esp_planta=ESP_PLANTA,
    )

mostrar_configuracion = (
    seccion_actual == "Configuración de mi viña"
)

if mostrar_configuracion:

    st.title("Mi viña")

    st.caption(
        f"{nombre_vina_actual} · Configuración y administración"
    )

    opciones_configuracion = [
        "Información general",
        "Claro monitoreado",
        "Configuración de indicadores",
        "Plantillas"
    ]

    if usuario_actual["rol"] == "administrador":
        opciones_configuracion.append("Usuarios")

    pestanas_configuracion = st.tabs(
        opciones_configuracion
    )

    with pestanas_configuracion[0]:
        # =========================================================
        # UBICACIÓN GEOGRÁFICA DE LA VIÑA
        # =========================================================

        vina_actual = consultar_vina(VINA_ID_ACTUAL)

        if vina_actual is not None:

            nombre_vina_actual = vina_actual[1]
            ubicacion_guardada = vina_actual[2]
            latitud_guardada = vina_actual[3]
            longitud_guardada = vina_actual[4]

            from regiones_chile import (
                obtener_regiones,
                obtener_comunas
            )

            from database import consultar_ubicacion_detallada

            import math

            detalle = consultar_ubicacion_detallada(
                VINA_ID_ACTUAL
            )

            prefijo = f"geo_{VINA_ID_ACTUAL}_"

            configurada = (
                latitud_guardada is not None
                and longitud_guardada is not None
            )

            es_admin = usuario_actual["rol"] == "administrador"

            st.subheader("Ubicación de mi viña")

            st.caption(
                "Define la ubicación exacta del predio para "
                "personalizar el mapa y las consultas a Open-Meteo."
            )

            if configurada:

                st.success("Ubicación geográfica registrada.")

                c1, c2 = st.columns(2)

                c1.metric(
                    "Latitud",
                    f"{latitud_guardada:.6f}"
                )

                c2.metric(
                    "Longitud",
                    f"{longitud_guardada:.6f}"
                )

                st.write(
                    "**Región:**",
                    detalle["region"] or "Pendiente de completar"
                )

                st.write(
                    "**Comuna:**",
                    detalle["comuna"] or "Pendiente de completar"
                )

                st.write(
                    "**Dirección:**",
                    detalle["direccion"] or ubicacion_guardada
                )

            puede_configurar = (
                es_admin and not configurada
            )

            if configurada:

                st.caption(
                    "Ubicación definitiva registrada. "
                    "No se permite modificarla."
                )

            clave_lat = prefijo + "lat"
            clave_lon = prefijo + "lon"
            clave_version = prefijo + "version"

            st.session_state.setdefault(
                clave_lat, latitud_guardada
            )

            st.session_state.setdefault(
                clave_lon, longitud_guardada
            )

            st.session_state.setdefault(
                clave_version, 0
            )

            if puede_configurar:

                st.markdown("#### Datos geográficos")

                st.text_input(
                    "País",
                    value="Chile",
                    disabled=True,
                    key=prefijo + "pais"
                )

                regiones = obtener_regiones()

                region = st.selectbox(
                    "Región",
                    regiones,
                    index=(
                        regiones.index(detalle["region"])
                        if detalle["region"] in regiones
                        else None
                    ),
                    placeholder="Selecciona una región",
                    key=prefijo + "region"
                )

                comunas = obtener_comunas(region)

                comuna = st.selectbox(
                    "Comuna",
                    comunas,
                    index=(
                        comunas.index(detalle["comuna"])
                        if detalle["comuna"] in comunas
                        else None
                    ),
                    placeholder="Selecciona una comuna",
                    disabled=not region,
                    key=prefijo + "comuna_" + str(region)
                )

                direccion = st.text_input(
                    "Dirección exacta o referencia del predio",
                    value=detalle["direccion"] or "",
                    placeholder="Camino, parcela, kilómetro o sector",
                    key=prefijo + "direccion"
                )

                consulta = ", ".join(
                    parte for parte in [
                        direccion, comuna, region, "Chile"
                    ] if parte
                )

                if st.button(
                    "Buscar ubicación en el mapa",
                    key=prefijo + "buscar",
                    disabled=not (
                        region and comuna and direccion.strip()
                    )
                ):

                    try:

                        geolocalizador = Nominatim(
                            user_agent="FenologIA_geolocalizacion",
                            ssl_context=ssl.create_default_context(
                                cafile=certifi.where()
                            )
                        )

                        with st.spinner("Buscando ubicación..."):

                            resultado = geolocalizador.geocode(
                                consulta,
                                timeout=15,
                                country_codes="cl"
                            )

                        if resultado:

                            st.session_state[clave_lat] = float(
                                resultado.latitude
                            )

                            st.session_state[clave_lon] = float(
                                resultado.longitude
                            )

                            st.session_state[clave_version] += 1

                            st.success(
                                "Ubicación encontrada. "
                                "Verifica el marcador en el mapa."
                            )

                        else:

                            st.warning(
                                "No encontramos la dirección exacta. "
                                "Puedes marcar el predio en el mapa "
                                "o ingresar sus coordenadas GPS."
                            )

                    except Exception:

                        st.warning(
                            "La búsqueda no está disponible. "
                            "Puedes utilizar el mapa o las coordenadas."
                        )

                with st.expander(
                    "Ingresar coordenadas GPS (opcional)"
                ):

                    c1, c2 = st.columns(2)

                    lat_manual = c1.text_input(
                        "Latitud",
                        placeholder="-34.650000",
                        key=prefijo + "lat_manual"
                    )

                    lon_manual = c2.text_input(
                        "Longitud",
                        placeholder="-71.380000",
                        key=prefijo + "lon_manual"
                    )

                    if st.button(
                        "Aplicar coordenadas",
                        key=prefijo + "aplicar_gps"
                    ):

                        try:

                            lat = float(
                                lat_manual.replace(",", ".")
                            )

                            lon = float(
                                lon_manual.replace(",", ".")
                            )

                            if not (
                                math.isfinite(lat)
                                and math.isfinite(lon)
                                and -90 <= lat <= 90
                                and -180 <= lon <= 180
                            ):

                                raise ValueError()

                            st.session_state[clave_lat] = lat
                            st.session_state[clave_lon] = lon
                            st.session_state[clave_version] += 1

                            st.success("Coordenadas aplicadas.")

                        except ValueError:

                            st.error(
                                "Ingresa coordenadas GPS válidas."
                            )

            lat_actual = (
                st.session_state[clave_lat]
                if puede_configurar
                else latitud_guardada
            )

            lon_actual = (
                st.session_state[clave_lon]
                if puede_configurar
                else longitud_guardada
            )

            hay_coordenadas = (
                lat_actual is not None
                and lon_actual is not None
            )

            centro = (
                [lat_actual, lon_actual]
                if hay_coordenadas
                else [-35.7, -71.5]
            )

            st.markdown("#### Ubicación en el mapa")

            if puede_configurar:

                st.caption(
                    "Haz clic sobre el mapa para ajustar "
                    "la ubicación exacta del viñedo."
                )

            mapa_ubicacion = folium.Map(
                location=centro,
                zoom_start=16 if hay_coordenadas else 5,
                tiles=None,
                control_scale=True
            )

            folium.TileLayer(
                tiles=(
                    "https://server.arcgisonline.com/ArcGIS/rest/"
                    "services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                ),
                attr="Esri World Imagery",
                name="Satélite",
                overlay=False
            ).add_to(mapa_ubicacion)

            folium.TileLayer(
                "OpenStreetMap",
                name="Mapa de calles"
            ).add_to(mapa_ubicacion)

            folium.LayerControl().add_to(mapa_ubicacion)

            if hay_coordenadas:

                folium.Marker(
                    [lat_actual, lon_actual],
                    tooltip="Ubicación de la viña",
                    icon=folium.Icon(
                        color="green",
                        icon="leaf"
                    )
                ).add_to(mapa_ubicacion)

            resultado_mapa = st_folium(
                mapa_ubicacion,
                width=900,
                height=500,
                returned_objects=(
                    ["last_clicked"]
                    if puede_configurar else []
                ),
                key=(
                    prefijo + "mapa_" +
                    str(st.session_state[clave_version])
                )
            )

            if puede_configurar and resultado_mapa:

                clic = resultado_mapa.get("last_clicked")

                if clic:

                    nueva_lat = round(float(clic["lat"]), 7)
                    nueva_lon = round(float(clic["lng"]), 7)

                    if (nueva_lat, nueva_lon) != (
                        lat_actual, lon_actual
                    ):

                        st.session_state[clave_lat] = nueva_lat
                        st.session_state[clave_lon] = nueva_lon
                        st.session_state[clave_version] += 1

                        st.rerun()

            if hay_coordenadas:

                st.caption(
                    f"Coordenadas seleccionadas: "
                    f"{lat_actual:.6f}, {lon_actual:.6f}"
                )

            if puede_configurar:

                listo = bool(
                    region
                    and comuna
                    and direccion.strip()
                    and hay_coordenadas
                )

                confirmado = st.checkbox(
                    "Confirmo que el marcador corresponde "
                    "a la ubicación exacta de mi viña.",
                    key=(
                        prefijo + "confirmar_" +
                        str(st.session_state[clave_version]) +
                        "_" + consulta
                    ),
                    disabled=not listo
                )

                if st.button(
                    "Guardar ubicación de mi viña",
                    type="primary",
                    disabled=not (listo and confirmado),
                    key=prefijo + "guardar"
                ):

                    try:

                        actualizar_ubicacion_vina(
                            VINA_ID_ACTUAL,
                            consulta,
                            lat_actual,
                            lon_actual,
                            usuario_id=usuario_actual["usuario_id"],
                            region=region,
                            comuna=comuna,
                            direccion=direccion,
                            permitir_modificacion=False
                        )

                        st.session_state[clave_lat] = lat_actual
                        st.session_state[clave_lon] = lon_actual

                        st.success(
                            "Ubicación guardada correctamente."
                        )

                        st.rerun()

                    except Exception as e:

                        st.error(
                            f"No se pudo guardar la ubicación: {e}"
                        )

            elif not configurada:

                st.info(
                    "El administrador debe registrar "
                    "la ubicación de esta viña."
                )

        # =========================================================
        # INFORMACIÓN METEOROLÓGICA
        # =========================================================


        st.divider()

        st.markdown("### Información meteorológica")

        st.caption(
            "Consulta las condiciones meteorológicas, los registros "
            "históricos y los informes de precipitación."
        )

        st.button(
            "Consultar meteorología",
            key="mi_vina_ir_meteorologia",
            type="primary",
            on_click=navegar_fenologia,
            args=("Meteorología y precipitaciones",)
        )



        if usuario_actual["rol"] == "administrador":

            from investigacion import mostrar_autorizacion

            st.divider()

            mostrar_autorizacion(
                usuario_actual["usuario_id"],
                VINA_ID_ACTUAL
            )

    with pestanas_configuracion[1]:


        st.subheader("Claro monitoreado")

        st.caption(
            "Cada cuartel puede tener un claro monitoreado "
            "compuesto por exactamente seis plantas."
        )

        with conectar() as conexion:
            cuarteles_claro = [
                fila[0]
                for fila in conexion.execute("""
                    SELECT DISTINCT cuartel
                    FROM plantas
                    WHERE vina_id = ?
                      AND cuartel IS NOT NULL
                    ORDER BY cuartel
                """, (VINA_ID_ACTUAL,)).fetchall()
            ]

        if not cuarteles_claro:
            st.info(
                "Esta viña todavía no tiene plantas registradas."
            )

        else:
            cuartel_claro = st.selectbox(
                "Selecciona el cuartel",
                cuarteles_claro,
                key=f"df283_cuartel_{VINA_ID_ACTUAL}"
            )

            configuracion_actual = consultar_claro_monitoreado(
                VINA_ID_ACTUAL,
                cuartel_claro
            )

            with conectar() as conexion:
                plantas_disponibles = conexion.execute("""
                    SELECT id, codigo_planta, fila,
                           numero_planta, variedad
                    FROM plantas
                    WHERE vina_id = ?
                      AND cuartel = ?
                    ORDER BY fila, numero_planta, codigo_planta
                """, (
                    VINA_ID_ACTUAL,
                    cuartel_claro
                )).fetchall()

            etiquetas_plantas = {
                planta[0]: (
                    f"{planta[1]} — Fila {planta[2]}, "
                    f"Planta {planta[3]} — {planta[4]}"
                )
                for planta in plantas_disponibles
            }

            ids_disponibles = list(etiquetas_plantas)

            es_admin_claro = (
                usuario_actual["rol"] == "administrador"
            )

            if configuracion_actual:
                st.success(
                    "Este cuartel tiene un claro monitoreado "
                    "configurado."
                )

                for planta in configuracion_actual:
                    st.write(
                        f"**Posición {planta[0]}:** "
                        f"{planta[2]}"
                    )

            else:
                st.info(
                    "Este cuartel todavía no tiene un "
                    "claro monitoreado configurado."
                )

            if es_admin_claro:

                if len(ids_disponibles) < 6:
                    st.warning(
                        "Se necesitan al menos seis plantas "
                        "registradas para configurar el claro."
                    )

                else:
                    st.markdown(
                        "#### Seleccionar las seis plantas"
                    )

                    st.caption(
                        "Selecciona las plantas reales que "
                        "monitoreará el dispositivo. "
                        "No se asignan automáticamente."
                    )

                    with st.form(
                        key=(
                            f"df283_configuracion_claro_"
                            f"{VINA_ID_ACTUAL}_{cuartel_claro}"
                        )
                    ):

                        seleccion_claro = []

                        for posicion in range(1, 7):

                            valor_actual = None

                            if configuracion_actual:
                                valor_actual = (
                                    configuracion_actual[
                                        posicion - 1
                                    ][1]
                                )

                            opciones = [None] + ids_disponibles

                            indice_actual = (
                                opciones.index(valor_actual)
                                if valor_actual in opciones
                                else 0
                            )

                            elegido = st.selectbox(
                                f"Planta {posicion}",
                                opciones,
                                index=indice_actual,
                                format_func=lambda identificador: (
                                    etiquetas_plantas.get(
                                        identificador,
                                        "Seleccionar planta"
                                    )
                                    if identificador is not None
                                    else "Seleccionar planta"
                                ),
                                key=(
                                    f"df283_planta_"
                                    f"{VINA_ID_ACTUAL}_"
                                    f"{cuartel_claro}_"
                                    f"{posicion}"
                                )
                            )

                            seleccion_claro.append(elegido)

                        guardar_claro = st.form_submit_button(
                            "Guardar claro monitoreado"
                        )

                    if guardar_claro:

                        if any(
                            identificador is None
                            for identificador in seleccion_claro
                        ):
                            st.warning(
                                "Debes seleccionar las seis plantas."
                            )

                        elif len(set(seleccion_claro)) != 6:
                            st.warning(
                                "Las seis plantas deben ser distintas."
                            )

                        else:
                            try:
                                guardar_claro_monitoreado(
                                    VINA_ID_ACTUAL,
                                    cuartel_claro,
                                    seleccion_claro,
                                    usuario_actual["usuario_id"]
                                )

                                st.success(
                                    "Claro monitoreado guardado "
                                    "correctamente."
                                )

                                st.rerun()

                            except (ValueError, PermissionError) as e:
                                st.error(str(e))

                            except Exception:
                                st.error(
                                    "No fue posible guardar el claro. "
                                    "Revisa la configuración."
                                )

            else:
                st.caption(
                    "Solo el administrador de esta viña "
                    "puede configurar o modificar el claro."
                )

    with pestanas_configuracion[2]:

        st.subheader("Configuración de indicadores")

        st.caption(
            "Define los rangos de referencia y los "
            "criterios de alerta de tu viña."
        )

        from interfaz_indicadores import (
            mostrar_configuracion_indicadores
        )

        mostrar_configuracion_indicadores(
            usuario_actual,
            VINA_ID_ACTUAL
        )

    with pestanas_configuracion[3]:

        st.subheader("Plantillas de archivos")
        st.caption("Descarga los formatos para importar información.")

        plantillas_disponibles = [
            (
                "Mediciones fenológicas",
                "Mediciones por planta y fecha.",
                "plantillas/FenologIA_Plantilla_Mediciones.xlsx",
                "Descargar XLSX fenologia",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "dm42_descargar_xlsx_fenologia"
            )
        ]

        if usuario_actual["rol"] == "administrador":
            plantillas_disponibles.extend([
                (
                    "Registro individual",
                    "Registro de plantas específicas.",
                    "plantillas_prueba/plantilla_registro_individual.csv",
                    "Descargar CSV individual",
                    "text/csv",
                    "dm38_descargar_individual"
                ),
                (
                    "Generación automática",
                    "Registro de cuarteles y filas.",
                    "plantillas_prueba/plantilla_generacion_automatica.csv",
                    "Descargar CSV automático",
                    "text/csv",
                    "dm38_descargar_automatica"
                )
            ])

        columnas_plantillas = st.columns(3)

        for columna, plantilla in zip(
            columnas_plantillas,
            plantillas_disponibles
        ):
            titulo, descripcion, ruta, etiqueta, mime, clave = plantilla

            with columna:
                with st.container(border=True):
                    st.markdown(f"### {titulo}")
                    st.caption(descripcion)

                    ruta_plantilla = Path(ruta)

                    if ruta_plantilla.is_file():
                        st.download_button(
                            etiqueta,
                            icon=":material/download:",
                            data=ruta_plantilla.read_bytes(),
                            file_name=ruta_plantilla.name,
                            mime=mime,
                            key=clave,
                            type="primary",
                            use_container_width=True
                        )
                    else:
                        st.warning("Plantilla no disponible.")


    if usuario_actual["rol"] == "administrador":
        with pestanas_configuracion[4]:
            if usuario_actual["rol"] == "administrador":
                st.subheader("Usuarios y permisos")

                st.markdown("#### Crear nuevo usuario")

                with st.form("dm31_crear_usuario"):
                    nuevo_nombre = st.text_input(
                        "Nombre del usuario"
                    )
                    nuevo_email = st.text_input(
                        "Correo electrónico"
                    )
                    nueva_password = st.text_input(
                        "Contraseña inicial",
                        type="password"
                    )

                    crear = st.form_submit_button(
                        "Crear usuario"
                    )

                    if crear:
                        try:
                            crear_usuario(
                                usuario_actual,
                                nuevo_nombre,
                                nuevo_email,
                                nueva_password
                            )
                            st.success(
                                "Usuario creado correctamente."
                            )
                        except ValueError as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(
                                f"No se pudo crear el usuario: {e}"
                            )

                st.markdown("#### Usuarios registrados")

                from database import conectar

                with conectar() as conexion:
                    usuarios_vina = conexion.execute("""
                        SELECT nombre, email, rol, activo,
                               fecha_registro
                        FROM usuarios
                        WHERE vina_id = ?
                        ORDER BY fecha_registro DESC
                    """, (VINA_ID_ACTUAL,)).fetchall()

                if usuarios_vina:
                    tabla_usuarios = pd.DataFrame(
                        [
                            {
                                "Nombre": u[0],
                                "Correo": u[1],
                                "Rol": u[2],
                                "Estado": (
                                    "Activo" if u[3] else "Inactivo"
                                ),
                                "Fecha de registro": u[4]
                            }
                            for u in usuarios_vina
                        ]
                    )

                    st.dataframe(
                        tabla_usuarios,
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info(
                        "No hay usuarios registrados en esta viña."
                    )


# =========================================================

if seccion_actual == "Meteorología y precipitaciones":

    st.title("Meteorología")

    st.caption(
        "Información meteorológica para las coordenadas "
        "registradas de tu viña."
    )

    from meteorologia_local import (
        mostrar_meteorologia_local,
        mostrar_condiciones_actuales,
        mostrar_pronostico_local
    )

    if latitud_guardada is None or longitud_guardada is None:

        st.info(
            "Registra la ubicación geográfica de tu viña "
            "para consultar la información meteorológica."
        )

    else:

        lat_meteo = float(latitud_guardada)
        lon_meteo = float(longitud_guardada)

        st.caption(
            f"Ubicación: {lat_meteo:.5f}, {lon_meteo:.5f} "
            "· Fuente: Open-Meteo"
        )

        tab_actual, tab_historial, tab_pronostico = st.tabs([
            "Condiciones actuales",
            "Historial meteorológico",
            "Pronóstico meteorológico"
        ])

        with tab_actual:

            mostrar_condiciones_actuales(
                lat_meteo, lon_meteo
            )

        with tab_historial:

            mostrar_meteorologia_local(
                VINA_ID_ACTUAL
            )

        with tab_pronostico:

            mostrar_pronostico_local(
                lat_meteo, lon_meteo
            )

        st.divider()

        st.caption(
            "Fuente meteorológica externa: Open-Meteo. "
            "Los datos corresponden a estimaciones de "
            "modelos meteorológicos y no a mediciones "
            "directas realizadas dentro de la viña. "
            "Las mediciones del dispositivo FenologIA "
            "constituyen una fuente complementaria."
        )



if seccion_actual == "Mapa y monitoreo de plantas":

    plantas_registradas = consultar_plantas_registradas(
        VINA_ID_ACTUAL
    )

    estructura_mapa = preparar_estructura_mapa(
        plantas_registradas,
        latitud_vina=latitud_guardada,
        longitud_vina=longitud_guardada,
        esp_fila=ESP_FILA,
        esp_planta=ESP_PLANTA
    )

    st.sidebar.success(
        f"{len(plantas_registradas)} plantas registradas."
    )

    columnas_excluidas = set(COLUMNAS_BASE) | {
        "plant_internal_id",
        "lat_mapa",
        "lon_mapa",
        "posicion_provisional",
        "tiene_medicion"
    }

    params = [
        c for c in datos.columns
        if c not in columnas_excluidas
        and pd.api.types.is_numeric_dtype(datos[c])
    ]

    fechas = (
        sorted(datos["fecha"].dropna().unique())
        if "fecha" in datos.columns else []
    )

    st.title("Monitoreo de plantas")

    panel_cargas = st.container()
    panel_visualizacion = st.container()

# DM.24: ventana modal CSV con selección y vista previa
@st.dialog("🍇 Cargar CSV plantas", width="large")
def ventana_csv_plantas():

    if usuario_actual["rol"] != "administrador":
        st.error(
            "Solo el administrador de la viña puede importar plantas."
        )
        return

    st.caption(
        "Registra la estructura de tu viña sin necesidad "
        "de incorporar mediciones fenológicas."
    )

    st.markdown(
        "**Columnas obligatorias:** id, cuartel, variedad, fila, planta."
    )

    st.caption(
        "Columnas opcionales: lat y lon. "
        "Si no dispones de GPS, deja ambas vacías."
    )

    archivo_csv = st.file_uploader(
        "Seleccionar archivo CSV",
        type=["csv"],
        key="csv_estructural_archivo"
    )

    if archivo_csv is not None:

        try:
            archivo_csv.seek(0)

            datos_csv = pd.read_csv(
                archivo_csv,
                sep=None,
                engine="python",
                encoding="utf-8-sig",
                dtype={
                    "id": "string",
                    "cuartel": "string",
                    "variedad": "string"
                }
            )

            datos_csv = validar_csv_estructural(datos_csv)

            existentes = consultar_plantas_registradas(
                VINA_ID_ACTUAL
            )

            mascara_existentes = datos_csv["id"].isin(
                existentes["id"]
            )

            nuevas = datos_csv.loc[
                ~mascara_existentes
            ].copy()

            cantidad_nuevas = len(nuevas)
            cantidad_existentes = int(
                mascara_existentes.sum()
            )

            st.markdown("#### Vista previa")

            col1, col2, col3 = st.columns(3)

            col1.metric("Plantas nuevas", cantidad_nuevas)
            col2.metric("Existentes", cantidad_existentes)
            col3.metric(
                "Nuevas sin GPS",
                int(nuevas["lat"].isna().sum())
            )

            vista = datos_csv.copy()

            vista["Estado"] = np.where(
                mascara_existentes,
                "Existente",
                "Nueva"
            )

            st.dataframe(
                vista.head(100),
                use_container_width=True,
                hide_index=True
            )

            if len(vista) > 100:
                st.caption("Se muestran las primeras 100 plantas.")

            ocupadas = {
                (str(r.cuartel), int(r.fila), int(r.planta)):
                str(r.id)
                for r in existentes.itertuples(index=False)
            }

            conflictos = []

            for r in nuevas.itertuples(index=False):
                posicion = (
                    str(r.cuartel),
                    int(r.fila),
                    int(r.planta)
                )

                if posicion in ocupadas:
                    conflictos.append({
                        "Planta nueva": r.id,
                        "Posición ocupada por": ocupadas[posicion]
                    })

            if conflictos:
                st.error(
                    "Existen posiciones ocupadas. "
                    "Corrige el CSV antes de importarlo."
                )
                st.dataframe(
                    pd.DataFrame(conflictos),
                    hide_index=True
                )

            st.info(
                "Las plantas existentes no se modificarán. "
                "No se crearán mediciones. "
                "Las posiciones provisionales serán "
                "exclusivamente visuales."
            )

            puede_guardar = (
                cantidad_nuevas > 0 and not conflictos
            )

            confirmar = st.checkbox(
                "Confirmo el registro de las plantas nuevas.",
                key="csv_estructural_confirmar",
                disabled=not puede_guardar
            )

            if st.button(
                "Guardar plantas nuevas",
                type="primary",
                key="csv_estructural_guardar",
                disabled=not (puede_guardar and confirmar),
                use_container_width=True
            ):

                resultado = importar_csv_estructural(
                    datos_csv,
                    VINA_ID_ACTUAL,
                    usuario_actual["usuario_id"]
                )

                st.session_state["csv_estructural_resultado"] = (
                    VINA_ID_ACTUAL,
                    resultado
                )

                st.rerun()

        except Exception as error:
            st.error(f"No se pudo importar el CSV: {error}")

    if st.button(
        "Cerrar ventana",
        key="csv_estructural_cerrar"
    ):
        st.rerun()


# DM.26: ventana de archivos ZIP del dispositivo

def obtener_identidad_sesion_zip(usuario):
    """Identifica al usuario, su viña y su rol."""

    if not isinstance(usuario, dict):
        return None

    identidad = (
        usuario.get("usuario_id"),
        usuario.get("vina_id"),
        usuario.get("rol")
    )

    if not all(
        isinstance(valor, str) and valor.strip()
        for valor in identidad
    ):
        return None

    if identidad[2] not in ("administrador", "usuario"):
        return None

    return identidad


def limpiar_estados_zip_dispositivo(conservar=()):
    """Elimina exclusivamente estados del diálogo ZIP."""

    claves_exactas = (
        "dm26_archivo_zip",
        "dm26_cerrar_zip",
        "dm26_checksum_inspeccion",
        "dm26_confirmacion_asignaciones",
        "dm26_error_inspeccion",
        "dm26_importar_capturas",
        "dm26_inspeccionar_zip",
        "dm26_resultado_inspeccion",
        "dm26_identidad_zip"
    )

    prefijos = (
        "dm26_asignacion_columna_",
        "dm26_confirmar_columnas_",
        "dm26_encabezado_candidato_",
        "dm26_filtro_diagnostico_",
        "dm26_fotografia_vista_previa_",
        "dm26_hoja_vista_previa_",
        "dm26_restablecer_asignaciones_",
        "dm26_revision_asignaciones_",
        "dm26_visualizar_fotografia_"
    )

    for clave in list(st.session_state.keys()):

        if clave in conservar:
            continue

        if (
            clave in claves_exactas
            or (
                isinstance(clave, str)
                and clave.startswith(prefijos)
            )
        ):
            st.session_state.pop(clave, None)


def cerrar_dialogo_zip_dispositivo():
    """Elimina los estados temporales al cerrar el ZIP."""

    limpiar_estados_zip_dispositivo()


def reiniciar_inspeccion_zip_dispositivo():
    """Invalida resultados y selecciones anteriores."""

    limpiar_estados_zip_dispositivo(
        conservar=(
            "dm26_identidad_zip",
            "dm26_archivo_zip",
            "dm26_inspeccionar_zip",
            "dm26_cerrar_zip"
        )
    )


def validar_identidad_sesion_zip(identidad_apertura):
    """Comprueba la identidad vigente antes de inspeccionar."""

    identidad_sesion = obtener_identidad_sesion_zip(
        st.session_state.get("usuario")
    )

    if (
        identidad_apertura is None
        or identidad_sesion != identidad_apertura
        or st.session_state.get("dm26_identidad_zip")
        != identidad_apertura
    ):
        raise PermissionError(
            "La sesión de inspección ya no es válida."
        )

    usuario_vigente_zip = consultar_usuario_activo(
        identidad_apertura[0]
    )

    identidad_vigente = obtener_identidad_sesion_zip(
        usuario_vigente_zip
    )

    if identidad_vigente != identidad_apertura:
        raise PermissionError(
            "La cuenta o sus permisos han cambiado."
        )

    return identidad_vigente


@st.dialog(
    "📦 Cargar ZIP dispositivo",
    width="large",
    on_dismiss=cerrar_dialogo_zip_dispositivo
)
def ventana_zip_dispositivo(identidad_apertura):

    if "dm26_identidad_zip" not in st.session_state:

        cerrar_dialogo_zip_dispositivo()
        st.rerun(scope="app")

    try:

        identidad_zip = validar_identidad_sesion_zip(
            identidad_apertura
        )

    except PermissionError:

        limpiar_estados_zip_dispositivo()

        st.warning(
            "La sesión de inspección ha finalizado. "
            "Cierra esta ventana y vuelve a ingresar."
        )

        st.stop()

    except Exception:

        limpiar_estados_zip_dispositivo()

        st.error(
            "No fue posible verificar tu sesión. "
            "Cierra esta ventana e inténtalo nuevamente."
        )

        st.stop()


    import hashlib

    from inspector_zip_dispositivo import (
        inspeccionar_zip_completo
    )

    st.caption(
        "Selecciona un archivo ZIP generado "
        "por el dispositivo FenologIA."
    )

    st.info(
        "La inspección permite revisar el contenido "
        "del archivo antes de importar información. "
        "Solo se guardarán datos después de validar y confirmar la importación."
    )

    archivo = st.file_uploader(
        "Seleccionar archivo ZIP",
        type=["zip"],
        key="dm26_archivo_zip",
        on_change=reiniciar_inspeccion_zip_dispositivo
    )

    clave_resultado = "dm26_resultado_inspeccion"
    clave_checksum = "dm26_checksum_inspeccion"
    clave_error = "dm26_error_inspeccion"

    def limpiar_inspeccion():

        reiniciar_inspeccion_zip_dispositivo()

    if archivo is None:

        limpiar_inspeccion()

    else:

        contenido = archivo.getvalue()

        checksum_actual = hashlib.sha256(
            contenido
        ).hexdigest()

        if st.session_state.get(
            clave_checksum
        ) != checksum_actual:

            limpiar_inspeccion()

        st.caption(
            f"Archivo: {archivo.name} · "
            f"{len(contenido) / (1024 ** 2):.2f} MB"
        )

        if st.session_state.get(clave_checksum) != checksum_actual:

            limpiar_inspeccion()

            st.session_state[
                clave_checksum
            ] = checksum_actual

            try:

                with st.spinner(
                    "Validando e inspeccionando el archivo..."
                ):

                    resultado = inspeccionar_zip_completo(
                        contenido
                    )

                    if resultado.get("estado") != (
                        "INSPECCION_COMPLETADA"
                    ):
                        raise ValueError(
                            "La inspección no pudo completarse."
                        )

                    if resultado.get("datos_guardados") is not False:
                        raise ValueError(
                            "Estado inesperado de la inspección."
                        )

                    st.session_state[
                        clave_resultado
                    ] = resultado

            except ValueError as error:

                st.session_state[
                    clave_error
                ] = str(error)

            except Exception:

                st.session_state[
                    clave_error
                ] = (
                    "No fue posible completar la inspección. "
                    "Revisa el archivo e inténtalo nuevamente."
                )

        error = st.session_state.get(
            clave_error
        )

        if error:

            st.error(error)

        resultado = st.session_state.get(
            clave_resultado
        )

        if resultado is not None:

            # La confirmación solo es válida para la
            # selección mostrada en esta ejecución.
            firma_visible = None

            resumen = resultado["resumen"]

            st.success(
                "Inspección preliminar completada."
            )

            st.markdown("#### Resumen del archivo")

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Hojas Excel",
                resumen["cantidad_hojas"]
            )

            col2.metric(
                "Fotografías",
                resumen["cantidad_fotografias"]
            )

            col3.metric(
                "Advertencias",
                resumen["cantidad_advertencias"]
            )

            st.caption(
                f"Archivo Excel: {resumen['archivo_excel']}"
            )

            (
                pestana_datos_zip,
                pestana_fotografias_zip,
                pestana_diagnostico_zip
            ) = st.tabs([
                "📊 Datos",
                "📷 Fotografías",
                "📋 Diagnóstico"
            ])

            with pestana_datos_zip:

                st.divider()

                st.markdown("#### Datos del Excel")

                import pandas as pd

                hojas = resultado["excel"]["hojas"]

                if not hojas:

                    st.warning(
                        "No se encontraron hojas disponibles."
                    )

                else:

                    nombres_hojas = [
                        hoja["nombre"]
                        for hoja in hojas
                    ]

                    hoja_elegida = st.selectbox(
                        "Seleccionar hoja del Excel",
                        options=nombres_hojas,
                        key=(
                            "dm26_hoja_vista_previa_"
                            + checksum_actual
                        )
                    )

                    hoja = next(
                        h for h in hojas
                        if h["nombre"] == hoja_elegida
                    )

                    c1, c2, c3 = st.columns(3)

                    c1.metric(
                        "Filas con datos",
                        hoja["filas_con_datos"]
                    )

                    c2.metric(
                        "Última columna",
                        hoja["ultima_columna_con_datos"]
                    )

                    c3.metric(
                        "Celdas con datos",
                        hoja["celdas_con_datos"]
                    )

                    if hoja["visibilidad"] != "visible":

                        st.warning(
                            "Esta hoja está oculta "
                            "en el archivo Excel original."
                        )

                    if hoja["vacia"]:

                        st.info(
                            "La hoja seleccionada no contiene datos."
                        )

                    else:

                        vista_previa = hoja["vista_previa"]

                        registros = []

                        for fila in vista_previa:

                            registro = {
                                "Fila Excel": fila["fila"]
                            }

                            for celda in fila["celdas"]:

                                posicion = celda["columna"]

                                registro[
                                    f"Columna {posicion}"
                                ] = celda["valor"]

                            registros.append(registro)

                        tabla = pd.DataFrame(
                            registros,
                            dtype=object
                        )

                        columnas = sorted(
                            [
                                columna
                                for columna in tabla.columns
                                if columna != "Fila Excel"
                            ],
                            key=lambda nombre: int(
                                nombre.split()[-1]
                            )
                        )

                        if not tabla.empty:

                            tabla = tabla[
                                ["Fila Excel"] + columnas
                            ]

                            st.markdown(
                                "**Vista previa del contenido**"
                            )

                            st.dataframe(
                                tabla,
                                hide_index=True,
                                use_container_width=True
                            )

                            st.caption(
                                f"Mostrando {len(vista_previa)} "
                                f"de {hoja['filas_con_datos']} "
                                "filas con información. "
                                "Se conservan las posiciones "
                                "originales del Excel."
                            )

                        else:

                            st.info(
                                "No hay filas disponibles "
                                "para la vista previa."
                            )

                    st.divider()

                    st.markdown(
                        "#### Reconocimiento de encabezados"
                    )

                    etiquetas_campos = {
                        "codigo_planta": "Código de planta",
                        "fecha": "Fecha",
                        "hora": "Hora",
                        "fecha_hora": "Fecha y hora",
                        "temperatura_ambiental": "Temperatura ambiental",
                        "humedad_ambiental": "Humedad ambiental",
                        "tiene_fotografia": "Indicador de fotografía",
                        "archivo_fotografia": "Nombre de fotografía",
                        "device_id": "Identificador del dispositivo",
                        "latitud": "Latitud",
                        "longitud": "Longitud"
                    }

                    etiquetas_estados = {
                        "RECONOCIDO": "Reconocido",
                        "AMBIGUO": "Requiere revisión",
                        "CONFLICTO": "Asignación en conflicto",
                        "DESCONOCIDO": "No reconocido",
                        "VACIO": "Sin encabezado"
                    }

                    hojas_encabezados = (
                        resultado["encabezados"]["hojas"]
                    )

                    encabezados_hoja = next(
                        (
                            h for h in hojas_encabezados
                            if h["nombre"] == hoja_elegida
                        ),
                        None
                    )

                    candidatos = (
                        encabezados_hoja["candidatos"]
                        if encabezados_hoja
                        else []
                    )

                    if not candidatos:

                        st.warning(
                            "No se detectaron encabezados candidatos "
                            "en la vista previa de esta hoja. "
                            "Será necesario revisar su estructura "
                            "manualmente."
                        )

                    else:

                        opciones = {
                            candidato["fila"]: candidato
                            for candidato in candidatos
                        }

                        fila_elegida = st.selectbox(
                            "Fila de encabezados candidata",
                            options=list(opciones),
                            format_func=lambda fila: (
                                f"Fila {fila} — "
                                f"Puntuación: "
                                f"{opciones[fila]['puntuacion']}"
                            ),
                            key=(
                                "dm26_encabezado_candidato_"
                                + checksum_actual
                                + "_"
                                + hoja_elegida
                            )
                        )

                        candidato = opciones[fila_elegida]

                        e1, e2, e3 = st.columns(3)

                        e1.metric(
                            "Reconocidas",
                            candidato["reconocidas"]
                        )

                        e2.metric(
                            "Ambiguas",
                            candidato["ambiguas"]
                        )

                        e3.metric(
                            "Conflictos",
                            candidato["conflictos"]
                        )

                        filas_encabezados = []

                        for columna in candidato["columnas"]:

                            campo = columna.get(
                                "campo_sugerido"
                            )

                            posibles = columna.get(
                                "candidatos", []
                            )

                            filas_encabezados.append({
                                "Columna Excel": columna["columna"],
                                "Encabezado original": str(
                                    columna.get("original") or ""
                                ),
                                "Campo sugerido": (
                                    etiquetas_campos.get(
                                        campo, campo
                                    )
                                    if campo
                                    else "Sin asignar"
                                ),
                                "Estado": etiquetas_estados.get(
                                    columna["estado"],
                                    columna["estado"]
                                ),
                                "Posibles campos": ", ".join(
                                    etiquetas_campos.get(c, c)
                                    for c in posibles
                                )
                            })

                        if filas_encabezados:

                            st.dataframe(
                                pd.DataFrame(filas_encabezados),
                                hide_index=True,
                                use_container_width=True
                            )

                        st.caption(
                            "La puntuación permite ordenar "
                            "los encabezados candidatos. "
                            "No representa un porcentaje "
                            "de confianza."
                        )

                        st.divider()

                        st.markdown(
                            "#### Asignación manual de columnas"
                        )

                        st.caption(
                            "Revisa las sugerencias y selecciona "
                            "el significado de cada columna."
                        )

                        opciones_campos = [
                            ""
                        ] + list(etiquetas_campos)

                        contexto_asignacion = hashlib.sha256(
                            repr((
                                checksum_actual,
                                hoja_elegida,
                                fila_elegida
                            )).encode("utf-8")
                        ).hexdigest()

                        prefijo_asignacion = (
                            "dm26_asignacion_columna_"
                            + contexto_asignacion
                            + "_"
                        )

                        columnas_candidatas = {
                            columna["columna"]: columna
                            for columna in candidato["columnas"]
                        }

                        posiciones = set(columnas_candidatas)

                        for fila in hoja["vista_previa"]:

                            if fila["fila"] > fila_elegida:

                                posiciones.update(
                                    celda["columna"]
                                    for celda in fila["celdas"]
                                )

                        columnas_asignables = []

                        for posicion in sorted(posiciones):

                            columna = columnas_candidatas.get(
                                posicion,
                                {
                                    "columna": posicion,
                                    "original": "",
                                    "estado": "VACIO",
                                    "campo_sugerido": None
                                }
                            )

                            columnas_asignables.append(columna)

                        sugerencias_iniciales = {}

                        for columna in columnas_asignables:

                            posicion = columna["columna"]

                            sugerencia = columna.get(
                                "campo_sugerido"
                            )

                            if (
                                columna["estado"] == "RECONOCIDO"
                                and sugerencia in etiquetas_campos
                            ):

                                sugerencias_iniciales[posicion] = (
                                    sugerencia
                                )

                            else:

                                sugerencias_iniciales[posicion] = ""

                        def restablecer_asignaciones():

                            for posicion, sugerencia in (
                                sugerencias_iniciales.items()
                            ):

                                clave = (
                                    prefijo_asignacion
                                    + str(posicion)
                                )

                                st.session_state[clave] = sugerencia

                        st.button(
                            "Restablecer sugerencias",
                            key=(
                                "dm26_restablecer_asignaciones_"
                                + contexto_asignacion
                            ),
                            on_click=restablecer_asignaciones
                        )

                        asignaciones = {}

                        for columna in columnas_asignables:

                            posicion = columna["columna"]

                            encabezado = columna.get("original")

                            if encabezado is None or encabezado == "":

                                encabezado = "Sin encabezado"

                            clave = (
                                prefijo_asignacion
                                + str(posicion)
                            )

                            if clave not in st.session_state:

                                st.session_state[clave] = (
                                    sugerencias_iniciales[posicion]
                                )

                            campo_elegido = st.selectbox(
                                f"Columna {posicion} — {encabezado}",
                                options=opciones_campos,
                                format_func=lambda campo: (
                                    etiquetas_campos.get(
                                        campo,
                                        "Sin asignar"
                                    )
                                ),
                                key=clave
                            )

                            asignaciones[posicion] = campo_elegido

                        campos_asignados = [
                            campo
                            for campo in asignaciones.values()
                            if campo
                        ]

                        duplicados = sorted({
                            campo
                            for campo in campos_asignados
                            if campos_asignados.count(campo) > 1
                        })

                        cantidad_asignadas = len(
                            campos_asignados
                        )

                        cantidad_sin_asignar = (
                            len(asignaciones)
                            - cantidad_asignadas
                        )

                        a1, a2, a3 = st.columns(3)

                        a1.metric(
                            "Asignadas",
                            cantidad_asignadas
                        )

                        a2.metric(
                            "Sin asignar",
                            cantidad_sin_asignar
                        )

                        a3.metric(
                            "Campos duplicados",
                            len(duplicados)
                        )

                        if duplicados:

                            for campo in duplicados:

                                posiciones_duplicadas = [
                                    str(posicion)
                                    for posicion, valor in (
                                        asignaciones.items()
                                    )
                                    if valor == campo
                                ]

                                st.error(
                                    f"{etiquetas_campos[campo]} "
                                    "está asignado a las columnas "
                                    + ", ".join(
                                        posiciones_duplicadas
                                    )
                                    + "."
                                )

                        elif cantidad_asignadas:

                            st.success(
                                "No se detectaron asignaciones "
                                "duplicadas."
                            )

                        else:

                            st.warning(
                                "Todavía no hay columnas asignadas."
                            )

                        st.caption(
                            "La temperatura y humedad ambiental "
                            "son diferentes de las mediciones "
                            "agronómicas del suelo."
                        )

                        st.divider()

                        st.markdown(
                            "#### Validación y confirmación"
                        )

                        errores_asignacion = []
                        advertencias_asignacion = []

                        campos = set(campos_asignados)

                        if not campos:

                            errores_asignacion.append(
                                "Debes asignar al menos una columna."
                            )

                        if duplicados:

                            errores_asignacion.append(
                                "Debes corregir los campos duplicados."
                            )

                        if "codigo_planta" not in campos:

                            errores_asignacion.append(
                                "Debes identificar la columna "
                                "del código de planta."
                            )

                        if (
                            "fecha_hora" in campos
                            and (
                                "fecha" in campos
                                or "hora" in campos
                            )
                        ):

                            errores_asignacion.append(
                                "Existe una asignación temporal "
                                "ambigua: fecha y hora combinadas "
                                "junto con campos separados."
                            )

                        if "fecha_hora" not in campos:

                            if "fecha" not in campos:

                                advertencias_asignacion.append(
                                    "No se ha asignado una fecha."
                                )

                            if "hora" not in campos:

                                advertencias_asignacion.append(
                                    "No se ha asignado una hora."
                                )

                        if "temperatura_ambiental" not in campos:

                            advertencias_asignacion.append(
                                "No se ha asignado la temperatura "
                                "ambiental."
                            )

                        if "humedad_ambiental" not in campos:

                            advertencias_asignacion.append(
                                "No se ha asignado la humedad "
                                "ambiental."
                            )

                        if (
                            resumen["cantidad_fotografias"] > 0
                            and "archivo_fotografia" not in campos
                        ):

                            advertencias_asignacion.append(
                                "El ZIP contiene fotografías, pero "
                                "no se ha asignado una columna "
                                "con sus nombres. La vinculación "
                                "requerirá revisión adicional."
                            )

                        if (
                            ("latitud" in campos)
                            != ("longitud" in campos)
                        ):

                            advertencias_asignacion.append(
                                "Las coordenadas geográficas "
                                "están incompletas."
                            )

                        for mensaje in errores_asignacion:

                            st.error(mensaje)

                        for mensaje in advertencias_asignacion:

                            st.warning(mensaje)

                        if not errores_asignacion:

                            st.success(
                                "Las asignaciones pueden "
                                "confirmarse preliminarmente."
                            )

                        firma_asignaciones = hashlib.sha256(
                            repr((
                                identidad_zip,
                                checksum_actual,
                                hoja_elegida,
                                fila_elegida,
                                sorted(asignaciones.items())
                            )).encode("utf-8")
                        ).hexdigest()

                        firma_visible = firma_asignaciones

                        clave_confirmacion = (
                            "dm26_confirmacion_asignaciones"
                        )

                        clave_revision = (
                            "dm26_revision_asignaciones_"
                            + firma_asignaciones
                        )

                        confirmacion = st.session_state.get(
                            clave_confirmacion
                        )

                        if confirmacion is not None:

                            if (
                                confirmacion.get("firma")
                                != firma_asignaciones
                                or confirmacion.get("identidad_zip")
                                != identidad_zip
                                or errores_asignacion
                            ):

                                st.session_state.pop(
                                    clave_confirmacion,
                                    None
                                )

                                confirmacion = None

                        revisado = st.checkbox(
                            "He revisado el significado de "
                            "las columnas seleccionadas.",
                            key=clave_revision,
                            disabled=bool(errores_asignacion)
                        )

                        if not revisado:

                            st.session_state.pop(
                                clave_confirmacion,
                                None
                            )

                            confirmacion = None

                        if st.button(
                            "Confirmar asignaciones",
                            key=(
                                "dm26_confirmar_columnas_"
                                + firma_asignaciones
                            ),
                            disabled=(
                                bool(errores_asignacion)
                                or not revisado
                                or confirmacion is not None
                            ),
                            use_container_width=True
                        ):

                            confirmacion = {
                                "identidad_zip": identidad_zip,
                                "checksum_zip": checksum_actual,
                                "hoja": hoja_elegida,
                                "fila_encabezado": fila_elegida,
                                "asignaciones": dict(asignaciones),
                                "firma": firma_asignaciones,
                                "advertencias": list(
                                    advertencias_asignacion
                                ),
                                "confirmacion_preliminar": True,
                                "listo_para_importar": False,
                                "datos_guardados": False
                            }

                            st.session_state[
                                clave_confirmacion
                            ] = confirmacion

                        if confirmacion is not None:

                            st.success(
                                "Asignaciones confirmadas "
                                "preliminarmente."
                            )

                            st.caption(
                                f"Hoja: {hoja_elegida} | "
                                f"Encabezado: fila {fila_elegida} | "
                                f"Columnas asignadas: "
                                f"{cantidad_asignadas}"
                            )

                            st.info(
                                "La confirmación corresponde "
                                "únicamente a la estructura "
                                "seleccionada. Todavía falta "
                                "validar las capturas y sus "
                                "fotografías."
                            )

                        else:

                            st.info(
                                "La configuración todavía no "
                                "ha sido confirmada."
                            )

                    st.caption(
                        "Los encabezados y tipos de mediciones "
                        "todavía no han sido confirmados."
                    )

                confirmacion_actual = st.session_state.get(
                    "dm26_confirmacion_asignaciones"
                )

                if confirmacion_actual is not None:

                    if (
                        firma_visible is None
                        or confirmacion_actual.get("firma")
                        != firma_visible
                    ):

                        st.session_state.pop(
                            "dm26_confirmacion_asignaciones",
                            None
                        )


            with pestana_fotografias_zip:
                st.divider()

                st.markdown(
                    "#### Fotografías del dispositivo"
                )

                import io
                import zipfile

                from PIL import Image

                from validador_zip_dispositivo import (
                    _leer_entrada_controlada,
                    MAX_ARCHIVO
                )

                informacion_zip = resultado["zip"]

                fotografias = informacion_zip[
                    "detalle_fotografias"
                ]

                contenido_validado = (
                    informacion_zip.get(
                        "contenido_validado"
                    ) is True
                )

                f1, f2 = st.columns(2)

                f1.metric(
                    "Fotografías encontradas",
                    len(fotografias)
                )

                f2.metric(
                    "Integridad del contenido",
                    "Validada" if contenido_validado
                    else "Pendiente"
                )

                if not contenido_validado:

                    st.error(
                        "El contenido fotográfico no ha "
                        "superado la validación."
                    )

                elif not fotografias:

                    st.info(
                        "El ZIP no contiene fotografías."
                    )

                else:

                    rutas_fotografias = {
                        foto["nombre"]: foto
                        for foto in fotografias
                    }

                    if len(rutas_fotografias) != len(
                        fotografias
                    ):

                        st.error(
                            "Se encontraron rutas "
                            "fotográficas duplicadas."
                        )

                    else:

                        ruta_elegida = st.selectbox(
                            "Seleccionar fotografía",
                            options=list(rutas_fotografias),
                            key=(
                                "dm26_fotografia_vista_previa_"
                                + checksum_actual
                            )
                        )

                        foto = rutas_fotografias[
                            ruta_elegida
                        ]

                        m1, m2, m3 = st.columns(3)

                        m1.metric(
                            "Ancho",
                            f"{foto['ancho']} px"
                        )

                        m2.metric(
                            "Alto",
                            f"{foto['alto']} px"
                        )

                        m3.metric(
                            "Tamaño",
                            f"{foto['bytes'] / 1024:.1f} KB"
                        )

                        st.caption(
                            f"Ruta dentro del ZIP: "
                            f"{ruta_elegida}"
                        )

                        clave_visualizacion = (
                            "dm26_visualizar_fotografia_"
                            + hashlib.sha256(
                                repr((
                                    checksum_actual,
                                    ruta_elegida
                                )).encode("utf-8")
                            ).hexdigest()
                        )

                        mostrar_foto = st.checkbox(
                            "Mostrar vista previa",
                            key=clave_visualizacion
                        )

                        if mostrar_foto:

                            try:

                                if (
                                    resumen["checksum_zip"]
                                    != checksum_actual
                                ):

                                    raise ValueError(
                                        "El archivo ZIP cambió "
                                        "desde su inspección."
                                    )

                                with zipfile.ZipFile(
                                    io.BytesIO(contenido)
                                ) as zip_fotos:

                                    entrada = zip_fotos.getinfo(
                                        ruta_elegida
                                    )

                                    contenido_foto = (
                                        _leer_entrada_controlada(
                                            zip_fotos,
                                            entrada,
                                            MAX_ARCHIVO,
                                            conservar=True
                                        )
                                    )

                                if len(contenido_foto) != (
                                    foto["bytes"]
                                ):

                                    raise ValueError(
                                        "El tamaño de la "
                                        "fotografía no coincide."
                                    )

                                hash_foto = hashlib.sha256(
                                    contenido_foto
                                ).hexdigest()

                                if hash_foto != foto["checksum"]:

                                    raise ValueError(
                                        "La integridad de la "
                                        "fotografía no coincide."
                                    )

                                with Image.open(
                                    io.BytesIO(contenido_foto)
                                ) as imagen:

                                    if imagen.format != "JPEG":

                                        raise ValueError(
                                            "Formato fotográfico "
                                            "no autorizado."
                                        )

                                    if imagen.size != (
                                        foto["ancho"],
                                        foto["alto"]
                                    ):

                                        raise ValueError(
                                            "Las dimensiones "
                                            "no coinciden."
                                        )

                                    imagen.thumbnail(
                                        (1200, 1200)
                                    )

                                    vista_foto = imagen.convert(
                                        "RGB"
                                    )

                                st.image(
                                    vista_foto,
                                    caption=foto["nombre"],
                                    use_container_width=True
                                )

                                st.caption(
                                    "Vista previa reducida. "
                                    "La fotografía original "
                                    "no ha sido modificada."
                                )

                            except ValueError as error:

                                st.error(str(error))

                            except Exception:

                                st.error(
                                    "No fue posible mostrar "
                                    "la fotografía seleccionada."
                                )

                        st.info(
                            "La fotografía ha sido inspeccionada, "
                            "pero todavía no está vinculada "
                            "a una captura ni a una planta."
                        )

                st.divider()

                st.markdown(
                    "#### Vinculación de capturas y fotografías"
                )

                from vinculador_fotografias_dispositivo import (
                    construir_indice_fotografias,
                    evaluar_conjunto_capturas
                )

                confirmacion_vinculacion = (
                    st.session_state.get(
                        "dm26_confirmacion_asignaciones"
                    )
                )

                evaluacion_fotografias = None
                capturas_preliminares = []

                if (
                    confirmacion_vinculacion is None
                    or confirmacion_vinculacion.get("identidad_zip")
                    != identidad_zip
                    or firma_visible is None
                    or confirmacion_vinculacion.get("firma")
                    != firma_visible
                    or confirmacion_vinculacion.get("checksum_zip")
                    != checksum_actual
                    or confirmacion_vinculacion.get(
                        "confirmacion_preliminar"
                    ) is not True
                ):

                    st.info(
                        "Confirma primero las asignaciones "
                        "de las columnas del Excel."
                    )

                elif not contenido_validado:

                    st.error(
                        "El contenido del ZIP no ha "
                        "superado la validación."
                    )

                else:

                    try:

                        hoja_confirmada = next(
                            h for h in resultado["excel"]["hojas"]
                            if h["nombre"]
                            == confirmacion_vinculacion["hoja"]
                        )

                        fila_encabezado = (
                            confirmacion_vinculacion[
                                "fila_encabezado"
                            ]
                        )

                        mapa_columnas = {
                            campo: posicion
                            for posicion, campo in (
                                confirmacion_vinculacion[
                                    "asignaciones"
                                ].items()
                            )
                            if campo
                        }

                        if "codigo_planta" not in mapa_columnas:

                            raise ValueError(
                                "No se ha identificado "
                                "el código de planta."
                            )

                        for fila in (
                            hoja_confirmada["vista_previa"]
                        ):

                            if fila["fila"] <= fila_encabezado:

                                continue

                            valores = {
                                celda["columna"]: celda["valor"]
                                for celda in fila["celdas"]
                            }

                            def obtener_campo(campo):

                                posicion = mapa_columnas.get(
                                    campo
                                )

                                if posicion is None:

                                    return None

                                return valores.get(posicion)

                            codigo_planta = obtener_campo(
                                "codigo_planta"
                            )

                            captura = {
                                "hoja_excel": (
                                    hoja_confirmada["nombre"]
                                ),
                                "fila_excel": fila["fila"],
                                "codigo_planta": codigo_planta,
                                "fecha_hora": obtener_campo(
                                    "fecha_hora"
                                ),
                                "fecha": obtener_campo("fecha"),
                                "hora": obtener_campo("hora"),
                                "temperatura_ambiental": (
                                    obtener_campo(
                                        "temperatura_ambiental"
                                    )
                                ),
                                "humedad_ambiental": (
                                    obtener_campo(
                                        "humedad_ambiental"
                                    )
                                ),
                                "tiene_fotografia": (
                                    obtener_campo(
                                        "tiene_fotografia"
                                    )
                                ),
                                "archivo_fotografia": (
                                    obtener_campo(
                                        "archivo_fotografia"
                                    )
                                )
                            }

                            capturas_preliminares.append(
                                captura
                            )

                        st.warning(
                            "Evaluación preliminar basada "
                            "exclusivamente en las filas "
                            "disponibles en la vista previa. "
                            "No constituye una validación "
                            "completa del archivo Excel."
                        )

                        if not capturas_preliminares:

                            st.info(
                                "No hay filas posteriores "
                                "al encabezado seleccionado "
                                "en la vista previa."
                            )

                        else:

                            indice_fotografias = (
                                construir_indice_fotografias(
                                    informacion_zip
                                )
                            )

                            evaluacion_fotografias = (
                                evaluar_conjunto_capturas(
                                    capturas_preliminares,
                                    indice_fotografias
                                )
                            )

                            if evaluacion_fotografias.get(
                                "datos_guardados"
                            ) is not False:

                                raise ValueError(
                                    "Estado inesperado "
                                    "de la evaluación."
                                )

                            resumen_vinculacion = (
                                evaluacion_fotografias["resumen"]
                            )

                            v1, v2 = st.columns(2)

                            v1.metric(
                                "Filas evaluadas",
                                resumen_vinculacion[
                                    "cantidad_capturas"
                                ]
                            )

                            v2.metric(
                                "Capturas con propuesta",
                                resumen_vinculacion[
                                    "capturas_con_propuesta"
                                ]
                            )

                            v3, v4 = st.columns(2)

                            v3.metric(
                                "Capturas sin fotografía",
                                resumen_vinculacion[
                                    "capturas_sin_fotografia"
                                ]
                            )

                            v4.metric(
                                "Requieren revisión",
                                resumen_vinculacion[
                                    "capturas_requieren_revision"
                                ]
                            )

                            etiquetas_vinculacion = {
                                "FOTOGRAFIA_PROPUESTA": (
                                    "Fotografía propuesta"
                                ),
                                "SIN_FOTOGRAFIA": (
                                    "Sin fotografía"
                                ),
                                "VINCULACION_PENDIENTE": (
                                    "Vinculación pendiente"
                                ),
                                "INFORMACION_INSUFICIENTE": (
                                    "Información insuficiente"
                                ),
                                "FOTOGRAFIA_AMBIGUA": (
                                    "Coincidencia ambigua"
                                ),
                                "FOTOGRAFIA_NO_ENCONTRADA": (
                                    "Fotografía no encontrada"
                                ),
                                "INDICADOR_INVALIDO": (
                                    "Indicador inválido"
                                ),
                                "CONFLICTO_INDICADOR_REFERENCIA": (
                                    "Conflicto entre indicador "
                                    "y referencia"
                                ),
                                "REFERENCIA_INVALIDA": (
                                    "Referencia inválida"
                                )
                            }

                            registros_vinculacion = []

                            for evaluacion in (
                                evaluacion_fotografias[
                                    "evaluaciones"
                                ]
                            ):

                                propuesta = (
                                    evaluacion.get(
                                        "fotografia_propuesta"
                                    ) or {}
                                )

                                estado = evaluacion["estado"]

                                registros_vinculacion.append({
                                    "Fila Excel": (
                                        evaluacion["fila_excel"]
                                    ),
                                    "Código de planta": str(
                                        evaluacion.get(
                                            "codigo_planta"
                                        )
                                        if evaluacion.get(
                                            "codigo_planta"
                                        ) is not None
                                        else "Sin identificar"
                                    ),
                                    "Referencia original": str(
                                        evaluacion.get(
                                            "referencia_original"
                                        )
                                        if evaluacion.get(
                                            "referencia_original"
                                        ) is not None
                                        else ""
                                    ),
                                    "Fotografía propuesta": (
                                        propuesta.get("ruta", "")
                                    ),
                                    "Estado": (
                                        etiquetas_vinculacion.get(
                                            estado, estado
                                        )
                                    ),
                                    "Referencia compartida": (
                                        "Sí"
                                        if evaluacion.get(
                                            "referencia_compartida"
                                        )
                                        else "No"
                                    ),
                                    "Requiere revisión": (
                                        "Sí"
                                        if evaluacion[
                                            "requiere_revision"
                                        ]
                                        else "No"
                                    )
                                })

                            st.dataframe(
                                pd.DataFrame(
                                    registros_vinculacion
                                ),
                                hide_index=True,
                                use_container_width=True
                            )

                            st.caption(
                                "Las coincidencias son "
                                "propuestas preliminares. "
                                "No se ha comprobado todavía "
                                "la existencia de las plantas "
                                "en la viña ni la validez "
                                "de las mediciones."
                            )

                            st.info(
                                "Las fotografías no han sido "
                                "vinculadas definitivamente "
                                "ni guardadas."
                            )

                    except ValueError as error:

                        evaluacion_fotografias = None
                        st.error(str(error))

                    except Exception:

                        evaluacion_fotografias = None

                        st.error(
                            "No fue posible completar "
                            "la evaluación preliminar "
                            "de las vinculaciones."
                        )


            with pestana_diagnostico_zip:
                st.divider()

                st.markdown(
                    "#### Diagnóstico del archivo ZIP"
                )

                from diagnostico_zip_dispositivo import (
                    generar_diagnostico_ampliado
                )

                advertencias_inspector = (
                    resultado.get("advertencias", [])
                )

                st.markdown(
                    "**Advertencias de la inspección inicial**"
                )

                if advertencias_inspector:

                    st.warning(
                        f"Se encontraron "
                        f"{len(advertencias_inspector)} "
                        "advertencias durante la inspección."
                    )

                    with st.expander(
                        "Ver advertencias del inspector"
                    ):

                        for advertencia in (
                            advertencias_inspector
                        ):

                            if isinstance(advertencia, dict):

                                st.text(
                                    str(
                                        advertencia.get(
                                            "codigo",
                                            "Advertencia"
                                        )
                                    )
                                )

                                st.text(
                                    str(
                                        advertencia.get(
                                            "mensaje",
                                            advertencia
                                        )
                                    )
                                )

                            else:

                                st.text(str(advertencia))

                else:

                    st.success(
                        "La inspección inicial no reportó "
                        "advertencias."
                    )

                st.markdown(
                    "**Diagnóstico de vinculaciones**"
                )

                diagnostico_fotografico = None

                if evaluacion_fotografias is None:

                    st.info(
                        "El diagnóstico fotográfico requiere "
                        "una evaluación preliminar de las "
                        "capturas del Excel."
                    )

                else:

                    try:

                        diagnostico_fotografico = (
                            generar_diagnostico_ampliado(
                                evaluacion_fotografias,
                                indice_fotografias
                            )
                        )

                        if diagnostico_fotografico.get(
                            "estado"
                        ) != "DIAGNOSTICO_COMPLETADO":

                            raise ValueError(
                                "El diagnóstico no se completó."
                            )

                        if diagnostico_fotografico.get(
                            "checksum_zip"
                        ) != checksum_actual:

                            raise ValueError(
                                "El diagnóstico corresponde "
                                "a otro archivo ZIP."
                            )

                        if diagnostico_fotografico.get(
                            "datos_guardados"
                        ) is not False:

                            raise ValueError(
                                "Estado inesperado del diagnóstico."
                            )

                        resumen_diagnostico = (
                            diagnostico_fotografico["resumen"]
                        )

                        d1, d2, d3 = st.columns(3)

                        d1.metric(
                            "Errores",
                            resumen_diagnostico["errores"]
                        )

                        d2.metric(
                            "Advertencias",
                            resumen_diagnostico["advertencias"]
                        )

                        d3.metric(
                            "Informaciones",
                            resumen_diagnostico["informaciones"]
                        )

                        if diagnostico_fotografico[
                            "tiene_errores"
                        ]:

                            st.error(
                                "Se encontraron inconsistencias "
                                "que requieren corrección."
                            )

                        elif diagnostico_fotografico[
                            "requiere_revision"
                        ]:

                            st.warning(
                                "El contenido requiere "
                                "revisión adicional."
                            )

                        else:

                            st.success(
                                "No se detectaron errores ni "
                                "revisiones pendientes en "
                                "las filas evaluadas."
                            )

                        etiquetas_niveles = {
                            "TODAS": "Todas las incidencias",
                            "ERROR": "Errores",
                            "ADVERTENCIA": "Advertencias",
                            "INFORMACION": "Información"
                        }

                        nivel_elegido = st.selectbox(
                            "Filtrar incidencias",
                            options=list(etiquetas_niveles),
                            format_func=lambda nivel: (
                                etiquetas_niveles[nivel]
                            ),
                            key=(
                                "dm26_filtro_diagnostico_"
                                + firma_visible
                            )
                        )

                        incidencias = (
                            diagnostico_fotografico[
                                "incidencias"
                            ]
                        )

                        incidencias_filtradas = [
                            incidencia
                            for incidencia in incidencias
                            if (
                                nivel_elegido == "TODAS"
                                or incidencia["nivel"]
                                == nivel_elegido
                            )
                        ]

                        st.caption(
                            f"Incidencias seleccionadas: "
                            f"{len(incidencias_filtradas)} "
                            f"de {len(incidencias)}."
                        )

                        if not incidencias_filtradas:

                            st.info(
                                "No hay incidencias "
                                "para el filtro seleccionado."
                            )

                        else:

                            registros_diagnostico = []

                            for incidencia in (
                                incidencias_filtradas
                            ):

                                registros_diagnostico.append({
                                    "Nivel": (
                                        etiquetas_niveles.get(
                                            incidencia["nivel"],
                                            incidencia["nivel"]
                                        )
                                    ),
                                    "Código": incidencia.get(
                                        "codigo", ""
                                    ),
                                    "Hoja Excel": incidencia.get(
                                        "hoja_excel", ""
                                    ),
                                    "Fila Excel": incidencia.get(
                                        "fila_excel"
                                    ),
                                    "Planta": str(
                                        incidencia.get(
                                            "codigo_planta"
                                        ) or ""
                                    ),
                                    "Referencia": str(
                                        incidencia.get(
                                            "referencia"
                                        ) or ""
                                    ),
                                    "Ruta fotográfica": str(
                                        incidencia.get(
                                            "ruta"
                                        ) or ""
                                    ),
                                    "Descripción": str(
                                        incidencia.get(
                                            "mensaje", ""
                                        )
                                    ),
                                    "Recomendación": str(
                                        incidencia.get(
                                            "recomendacion", ""
                                        )
                                    )
                                })

                            st.dataframe(
                                pd.DataFrame(
                                    registros_diagnostico
                                ),
                                hide_index=True,
                                use_container_width=True
                            )

                            st.markdown(
                                "**Detalle de incidencias**"
                            )

                            limite_detalle = 30

                            for numero, incidencia in enumerate(
                                incidencias_filtradas[
                                    :limite_detalle
                                ],
                                start=1
                            ):

                                nivel = incidencia["nivel"]

                                icono = {
                                    "ERROR": "🔴",
                                    "ADVERTENCIA": "🟠",
                                    "INFORMACION": "🔵"
                                }.get(nivel, "⚪")

                                titulo = (
                                    f"{icono} {numero}. "
                                    f"{incidencia['codigo']}"
                                )

                                with st.expander(titulo):

                                    st.text(
                                        str(
                                            incidencia.get(
                                                "mensaje", ""
                                            )
                                        )
                                    )

                                    if incidencia.get(
                                        "fila_excel"
                                    ) is not None:

                                        st.text(
                                            f"Fila Excel: "
                                            f"{incidencia['fila_excel']}"
                                        )

                                    if incidencia.get(
                                        "codigo_planta"
                                    ) is not None:

                                        st.text(
                                            f"Planta: "
                                            f"{incidencia['codigo_planta']}"
                                        )

                                    if incidencia.get("ruta"):

                                        st.text(
                                            str(incidencia["ruta"])
                                        )

                                    st.markdown(
                                        "**Recomendación**"
                                    )

                                    st.text(
                                        str(
                                            incidencia.get(
                                                "recomendacion", ""
                                            )
                                        )
                                    )

                            if len(incidencias_filtradas) > (
                                limite_detalle
                            ):

                                st.caption(
                                    "Se muestran las primeras "
                                    "30 incidencias en detalle. "
                                    "La tabla contiene todas "
                                    "las incidencias del filtro."
                                )

                        st.warning(
                            "Este diagnóstico se basa únicamente "
                            "en las filas disponibles en la "
                            "vista previa de la hoja seleccionada. "
                            "Una fotografía sin referencia en "
                            "esta muestra podría estar vinculada "
                            "a otras filas u hojas del Excel."
                        )

                        st.caption(
                            "No se han validado todas las "
                            "capturas, la pertenencia de las "
                            "plantas ni los valores ambientales."
                        )

                    except ValueError as error:

                        diagnostico_fotografico = None
                        st.error(str(error))

                    except Exception:

                        diagnostico_fotografico = None

                        st.error(
                            "No fue posible completar "
                            "el diagnóstico preliminar."
                        )


            st.divider()
            st.markdown("#### Validación e importación definitiva")

            from contextlib import closing
            from motor_importacion_zip_dispositivo import (
                diagnosticar_importacion_zip
            )
            from importador_zip_dispositivo import (
                importar_zip_dispositivo
            )
            from database import (
                verificar_permiso_mediciones
            )

            confirmacion_final = st.session_state.get(
                "dm26_confirmacion_asignaciones"
            )

            if (
                confirmacion_final is None
                or firma_visible is None
                or confirmacion_final.get("firma") != firma_visible
                or confirmacion_final.get("identidad_zip") != identidad_zip
                or confirmacion_final.get("checksum_zip") != checksum_actual
                or confirmacion_final.get("confirmacion_preliminar") is not True
            ):

                st.info(
                    "Confirma primero las asignaciones del Excel."
                )

            else:

                try:

                    usuario_id_zip, vina_id_zip, _ = (
                        validar_identidad_sesion_zip(
                            identidad_apertura
                        )
                    )

                    with closing(conectar()) as con_zip:

                        con_zip.execute("PRAGMA query_only = ON")

                        verificar_permiso_mediciones(
                            con_zip,
                            usuario_id_zip,
                            vina_id_zip
                        )

                        dispositivos_zip = [
                            fila[0]
                            for fila in con_zip.execute(
                                """
                                SELECT device_id
                                FROM dispositivos
                                WHERE vina_id = ?
                                ORDER BY device_id
                                """,
                                (vina_id_zip,)
                            ).fetchall()
                        ]

                    if not dispositivos_zip:

                        st.warning(
                            "Esta viña no tiene dispositivos registrados."
                        )

                    else:

                        device_id_zip = st.selectbox(
                            "Dispositivo de origen",
                            options=dispositivos_zip,
                            index=None,
                            placeholder="Seleccionar dispositivo",
                            key=(
                                "dm26_revision_asignaciones_dispositivo_"
                                + firma_visible
                            )
                        )

                        if device_id_zip is not None:

                            firma_diagnostico = hashlib.sha256(
                                repr((
                                    identidad_zip,
                                    checksum_actual,
                                    firma_visible,
                                    device_id_zip
                                )).encode("utf-8")
                            ).hexdigest()

                            clave_diagnostico = (
                                "dm26_revision_asignaciones_diagnostico_"
                                + firma_diagnostico
                            )

                            for clave in list(st.session_state):

                                if (
                                    isinstance(clave, str)
                                    and clave.startswith(
                                        "dm26_revision_asignaciones_diagnostico_"
                                    )
                                    and clave != clave_diagnostico
                                ):
                                    st.session_state.pop(clave, None)

                            if st.button(
                                "Validar ZIP completo",
                                key=(
                                    "dm26_confirmar_columnas_validar_"
                                    + firma_diagnostico
                                ),
                                type="primary",
                                use_container_width=True
                            ):

                                st.session_state.pop(
                                    clave_diagnostico, None
                                )

                                validar_identidad_sesion_zip(
                                    identidad_apertura
                                )

                                with st.spinner(
                                    "Validando todas las capturas "
                                    "y comparando con el historial..."
                                ):

                                    with closing(conectar()) as con_zip:

                                        con_zip.execute(
                                            "PRAGMA query_only = ON"
                                        )

                                        diagnostico_final = (
                                            diagnosticar_importacion_zip(
                                                con_zip,
                                                contenido,
                                                confirmacion_final["hoja"],
                                                confirmacion_final["fila_encabezado"],
                                                confirmacion_final["asignaciones"],
                                                usuario_id_zip,
                                                vina_id_zip,
                                                device_id_zip
                                            )
                                        )

                                resumen_final = diagnostico_final.get(
                                    "resumen", {}
                                )

                                st.session_state[clave_diagnostico] = {
                                    "estado": diagnostico_final["estado"],
                                    "completo": diagnostico_final[
                                        "diagnostico_completo"
                                    ],
                                    "apto": diagnostico_final[
                                        "apto_para_confirmacion"
                                    ],
                                    "recuperacion_pendiente": (
                                        diagnostico_final[
                                            "recuperacion_transaccional_pendiente"
                                        ]
                                    ),
                                    "cantidad_capturas": (
                                        diagnostico_final["cantidad_capturas"]
                                    ),
                                    "resumen": resumen_final,
                                    "incidencias": (
                                        diagnostico_final["incidencias"][:200]
                                    ),
                                    "total_incidencias": len(
                                        diagnostico_final["incidencias"]
                                    ),
                                    "historicas": [
                                        {
                                            "Planta": c.get("codigo_planta"),
                                            "Fila": c.get("fila_excel"),
                                            "Tipo": c.get("codigo"),
                                            "Fecha nueva": c.get(
                                                "fecha_hora_nueva"
                                            ),
                                            "Fecha histórica": c.get(
                                                "fecha_hora_historica"
                                            )
                                        }
                                        for c in diagnostico_final.get(
                                            "coincidencias_historicas", {}
                                        ).get("coincidencias", [])[:100]
                                    ]
                                }

                                del diagnostico_final

                            diagnostico_visible = st.session_state.get(
                                clave_diagnostico
                            )

                            if diagnostico_visible is not None:

                                resumen_final = diagnostico_visible[
                                    "resumen"
                                ]

                                c1, c2, c3 = st.columns(3)

                                c1.metric(
                                    "Capturas",
                                    diagnostico_visible["cantidad_capturas"]
                                )

                                c2.metric(
                                    "Coincidencias internas",
                                    resumen_final.get(
                                        "coincidencias_internas", "—"
                                    )
                                )

                                c3.metric(
                                    "Coincidencias históricas",
                                    resumen_final.get(
                                        "coincidencias_historicas", "—"
                                    )
                                )

                                if diagnostico_visible["incidencias"]:

                                    with st.expander(
                                        "Ver incidencias del diagnóstico"
                                    ):

                                        st.dataframe(
                                            pd.DataFrame(
                                                diagnostico_visible["incidencias"]
                                            ),
                                            hide_index=True,
                                            use_container_width=True
                                        )

                                        st.caption(
                                            "Se muestran hasta 200 incidencias "
                                            "de un total de "
                                            + str(
                                                diagnostico_visible[
                                                    "total_incidencias"
                                                ]
                                            )
                                        )

                                if diagnostico_visible["historicas"]:

                                    with st.expander(
                                        "Ver coincidencias históricas"
                                    ):

                                        st.dataframe(
                                            pd.DataFrame(
                                                diagnostico_visible["historicas"]
                                            ),
                                            hide_index=True,
                                            use_container_width=True
                                        )

                                        st.caption(
                                            "Se muestran hasta 100 coincidencias."
                                        )

                                apto = (
                                    diagnostico_visible["completo"] is True
                                    and diagnostico_visible["apto"] is True
                                    and diagnostico_visible[
                                        "recuperacion_pendiente"
                                    ] is False
                                )

                                if not apto:

                                    st.error(
                                        "Importación bloqueada. Revisa "
                                        "las incidencias antes de continuar."
                                    )

                                else:

                                    st.success(
                                        "El diagnóstico permite continuar."
                                    )

                                    unidades = st.checkbox(
                                        "Confirmo que la temperatura está "
                                        "en °C y la humedad relativa en %.",
                                        key=(
                                            "dm26_revision_asignaciones_unidades_"
                                            + firma_diagnostico
                                        )
                                    )

                                    confirmar_guardado = st.checkbox(
                                        "He revisado el diagnóstico y autorizo "
                                        "guardar las capturas y fotografías.",
                                        key=(
                                            "dm26_revision_asignaciones_guardado_"
                                            + firma_diagnostico
                                        )
                                    )

                                    if st.button(
                                        "Importar capturas",
                                        key="dm26_importar_capturas",
                                        type="primary",
                                        disabled=not (
                                            unidades and confirmar_guardado
                                        ),
                                        use_container_width=True
                                    ):

                                        st.session_state.pop(
                                            clave_diagnostico, None
                                        )

                                        validar_identidad_sesion_zip(
                                            identidad_apertura
                                        )

                                        with st.spinner(
                                            "Verificando y guardando el ZIP..."
                                        ):

                                            importacion_final = (
                                                importar_zip_dispositivo(
                                                    contenido,
                                                    archivo.name,
                                                    confirmacion_final["hoja"],
                                                    confirmacion_final["fila_encabezado"],
                                                    confirmacion_final["asignaciones"],
                                                    usuario_id_zip,
                                                    vina_id_zip,
                                                    device_id_zip,
                                                    confirmacion=confirmar_guardado,
                                                    unidades_confirmadas=unidades
                                                )
                                            )

                                        st.success(
                                            "Importación completada: "
                                            + str(
                                                importacion_final[
                                                    "cantidad_capturas"
                                                ]
                                            )
                                            + " capturas y "
                                            + str(
                                                importacion_final[
                                                    "cantidad_fotografias"
                                                ]
                                            )
                                            + " fotografías guardadas."
                                        )

                                        st.caption(
                                            "Identificador de importación: "
                                            + importacion_final["importacion_id"]
                                        )

                except PermissionError:

                    st.error(
                        "La sesión o los permisos ya no son válidos."
                    )

                except ValueError as error:

                    st.error(str(error))

                except Exception as error:

                    import logging

                    logging.getLogger(__name__).exception(
                        "Error durante el flujo experimental ZIP"
                    )

                    st.error(
                        "No fue posible completar la operación. "
                        "Revisa la terminal antes de volver a importar. "
                        f"Tipo de error: {type(error).__name__}."
                    )

    st.button(
        "Cerrar ventana",
        key="dm26_cerrar_zip",
        on_click=cerrar_dialogo_zip_dispositivo
    )


# DM.26: ventana de mediciones fenológicas Excel
@st.dialog("📊 Cargar xlsx fenologia", width="large")
def ventana_xlsx_fenologia():

    st.markdown("""
    <style>
    .st-key-dm49_guardar_mediciones button:not(:disabled) {
        background-color: #322345 !important;
        border-color: #322345 !important;
        color: #FFFFFF !important;
    }

    .st-key-dm49_guardar_mediciones button:not(:disabled) p {
        color: #FFFFFF !important;
    }

    .st-key-dm49_guardar_mediciones button:not(:disabled):hover {
        background-color: #49365E !important;
        border-color: #49365E !important;
    }

    .st-key-dm49_guardar_mediciones button:disabled {
        background-color: #E5E7EB !important;
        border-color: #D1D5DB !important;
        color: #9CA3AF !important;
        cursor: not-allowed !important;
    }

    .st-key-dm49_guardar_mediciones button:disabled p {
        color: #9CA3AF !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.caption(
        "Selecciona el archivo Excel de mediciones fenológicas."
    )

    archivo = st.file_uploader(
        "Seleccionar archivo XLSX",
        type=["xlsx"],
        key="dm26_archivo_xlsx"
    )

    if archivo is not None:
        st.success(f"Archivo seleccionado: {archivo.name}")

        try:
            from io import BytesIO

            datos_xlsx = pd.read_excel(
                BytesIO(archivo.getvalue()),
                sheet_name="Mediciones",
                dtype={"id": "string"},
                engine="openpyxl"
            )

            columnas_esperadas = [
                "id", "fecha", "ndvi", "hum",
                "psi", "brix", "rend"
            ]

            faltantes = [
                columna
                for columna in columnas_esperadas
                if columna not in datos_xlsx.columns
            ]

            if faltantes:
                st.error(
                    "Faltan columnas obligatorias: "
                    + ", ".join(faltantes)
                )

            elif list(datos_xlsx.columns) != columnas_esperadas:
                st.error(
                    "Las columnas y su orden deben coincidir "
                    "con la plantilla FenologIA."
                )

            elif datos_xlsx.empty:
                st.warning(
                    "La hoja Mediciones está vacía. "
                    "Completa al menos una fila."
                )

            else:
                st.success(
                    "Hoja Mediciones leída correctamente."
                )

                st.metric(
                    "Registros encontrados",
                    len(datos_xlsx)
                )

                st.markdown("#### Vista previa")

                st.dataframe(
                    datos_xlsx.head(10),
                    use_container_width=True,
                    hide_index=True
                )

                # DM.44.3: validación preliminar XLSX
                import math
                from datetime import date, datetime

                errores_xlsx = []
                claves_vistas = set()
                variables_xlsx = [
                    "ndvi", "hum", "psi", "brix", "rend"
                ]

                for indice, registro in datos_xlsx.iterrows():
                    numero_fila = indice + 2

                    codigo = registro["id"]
                    fecha = registro["fecha"]

                    if pd.isna(codigo) or not str(codigo).strip():
                        errores_xlsx.append(
                            f"Fila {numero_fila}: identificador vacío."
                        )
                        codigo_normalizado = None
                    else:
                        codigo_normalizado = str(codigo).strip()

                    fecha_normalizada = None

                    if not pd.isna(fecha):
                        try:
                            if isinstance(fecha, (datetime, date)):
                                fecha_normalizada = fecha.strftime(
                                    "%Y-%m-%d"
                                )
                            else:
                                fecha_normalizada = datetime.strptime(
                                    str(fecha).strip(),
                                    "%Y-%m-%d"
                                ).strftime("%Y-%m-%d")
                        except (ValueError, TypeError):
                            pass

                    if fecha_normalizada is None:
                        errores_xlsx.append(
                            f"Fila {numero_fila}: fecha inválida."
                        )

                    if codigo_normalizado and fecha_normalizada:
                        clave = (
                            codigo_normalizado,
                            fecha_normalizada
                        )

                        if clave in claves_vistas:
                            errores_xlsx.append(
                                f"Fila {numero_fila}: "
                                "planta y fecha duplicadas."
                            )

                        claves_vistas.add(clave)

                    if all(
                        pd.isna(registro[v])
                        for v in variables_xlsx
                    ):
                        errores_xlsx.append(
                            f"Fila {numero_fila}: debe existir "
                            "al menos una medición válida."
                        )

                    for variable in variables_xlsx:
                        valor = registro[variable]

                        if pd.isna(valor):
                            continue

                        try:
                            numero = float(valor)
                            if not math.isfinite(numero):
                                raise ValueError()
                        except (ValueError, TypeError):
                            errores_xlsx.append(
                                f"Fila {numero_fila}: "
                                f"valor inválido en {variable}."
                            )

                st.markdown("#### Validación preliminar")

                if errores_xlsx:
                    st.error(
                        f"Se encontraron {len(errores_xlsx)} "
                        "problemas en el archivo."
                    )

                    for error_xlsx in errores_xlsx[:30]:
                        st.warning(error_xlsx)

                    if len(errores_xlsx) > 30:
                        st.caption(
                            "Se muestran los primeros 30 problemas."
                        )

                else:
                    st.success(
                        "Validación preliminar superada: "
                        "identificadores, fechas, valores "
                        "numéricos y duplicados."
                    )

                    # DM.45.3: consulta conservadora de SQLite
                    resumen_xlsx = []
                    estados_xlsx = {
                        "MEDICIÓN NUEVA": 0,
                        "MEDICIÓN EXISTENTE": 0,
                        "CONFLICTO DE VALORES": 0,
                        "PLANTA NO ENCONTRADA": 0
                    }

                    try:
                        with conectar() as conexion:
                            for _, registro in datos_xlsx.iterrows():
                                codigo_planta = str(
                                    registro["id"]
                                ).strip()

                                fecha_valor = registro["fecha"]

                                if isinstance(
                                    fecha_valor, (datetime, date)
                                ):
                                    fecha_xlsx = fecha_valor.strftime(
                                        "%Y-%m-%d"
                                    )
                                else:
                                    fecha_xlsx = datetime.strptime(
                                        str(fecha_valor).strip(),
                                        "%Y-%m-%d"
                                    ).strftime("%Y-%m-%d")

                                planta_bd = conexion.execute("""
                                    SELECT id
                                    FROM plantas
                                    WHERE vina_id = ?
                                      AND codigo_planta = ?
                                """, (
                                    VINA_ID_ACTUAL,
                                    codigo_planta
                                )).fetchone()

                                if planta_bd is None:
                                    estado = "PLANTA NO ENCONTRADA"
                                else:
                                    medicion_bd = conexion.execute("""
                                        SELECT datos_json
                                        FROM mediciones
                                        WHERE plant_id = ?
                                          AND fecha_hora = ?
                                        LIMIT 1
                                    """, (
                                        planta_bd[0],
                                        fecha_xlsx
                                    )).fetchone()

                                    if medicion_bd is None:
                                        estado = "MEDICIÓN NUEVA"
                                    else:
                                        import json

                                        existentes = json.loads(
                                            medicion_bd[0] or "{}"
                                        )

                                        valores = {
                                            v: (
                                                None
                                                if pd.isna(registro[v])
                                                else float(registro[v])
                                            )
                                            for v in variables_xlsx
                                        }

                                        if not isinstance(existentes, dict):
                                            estado = "CONFLICTO DE VALORES"
                                        elif any(
                                            existentes.get(v) != valor
                                            for v, valor in valores.items()
                                        ):
                                            estado = "CONFLICTO DE VALORES"
                                        else:
                                            estado = "MEDICIÓN EXISTENTE"

                                estados_xlsx[estado] += 1

                                resumen_xlsx.append({
                                    "Planta": codigo_planta,
                                    "Fecha": fecha_xlsx,
                                    "Estado": estado
                                })

                        st.markdown(
                            "#### Verificación de plantas y mediciones"
                        )

                        (
                            col_nuevas,
                            col_existentes,
                            col_faltantes,
                            col_conflictos
                        ) = st.columns(4)

                        col_nuevas.metric(
                            "Nuevas",
                            estados_xlsx["MEDICIÓN NUEVA"]
                        )

                        col_existentes.metric(
                            "Existentes",
                            estados_xlsx["MEDICIÓN EXISTENTE"]
                        )

                        col_faltantes.metric(
                            "Plantas no encontradas",
                            estados_xlsx["PLANTA NO ENCONTRADA"]
                        )

                        col_conflictos.metric(
                            "Conflictos",
                            estados_xlsx["CONFLICTO DE VALORES"]
                        )

                        st.dataframe(
                            pd.DataFrame(resumen_xlsx),
                            use_container_width=True,
                            hide_index=True
                        )

                        # DM.49.3: confirmación previa a la importación
                        st.markdown("#### Confirmación de importación")

                        puede_importar_xlsx = (
                            estados_xlsx["PLANTA NO ENCONTRADA"] == 0
                            and estados_xlsx["CONFLICTO DE VALORES"] == 0
                            and estados_xlsx["MEDICIÓN NUEVA"] > 0
                        )

                        if estados_xlsx["PLANTA NO ENCONTRADA"] > 0:
                            st.error(
                                "No se puede importar este archivo "
                                "porque contiene plantas que no existen "
                                "en la viña seleccionada."
                            )

                        elif estados_xlsx["CONFLICTO DE VALORES"] > 0:
                            st.error(
                                "El archivo contiene mediciones con "
                                "valores diferentes para plantas y "
                                "fechas ya registradas. "
                                "No se sobrescribirán datos existentes."
                            )

                        elif estados_xlsx["MEDICIÓN NUEVA"] == 0:
                            st.info(
                                "No hay mediciones nuevas para importar. "
                                "Los registros existentes se conservarán."
                            )

                        else:
                            st.success(
                                f"Hay {estados_xlsx['MEDICIÓN NUEVA']} "
                                "mediciones nuevas disponibles "
                                "para importar."
                            )

                        confirmacion_xlsx = st.checkbox(
                            "Confirmo que revisé los datos y deseo "
                            "importar únicamente las mediciones nuevas.",
                            key="dm49_confirmar_importacion",
                            disabled=not puede_importar_xlsx
                        )

                        if st.button(
                            "Guardar mediciones nuevas",
                            key="dm49_guardar_mediciones",
                            disabled=not (
                                puede_importar_xlsx
                                and confirmacion_xlsx
                            ),
                            use_container_width=True
                        ):
                            resultado = importar_xlsx_mediciones_seguro(
                                datos_xlsx,
                                VINA_ID_ACTUAL,
                                usuario_actual["usuario_id"]
                            )

                            st.session_state[
                                "resultado_importacion_xlsx"
                            ] = (VINA_ID_ACTUAL, resultado)

                            st.rerun()

                    except Exception as error_bd:
                        st.error(
                            "No se pudo verificar el archivo "
                            f"contra la base de datos: {error_bd}"
                        )

                st.caption(
                    "Las mediciones anteriores se conservarán. "
                    "Los registros nuevos se incorporarán "
                    "al historial de cada planta."
                )

        except Exception as error:
            st.error(
                "No se pudo leer la hoja Mediciones "
                f"del archivo Excel: {error}"
            )

    if st.button("Cerrar ventana", key="dm26_cerrar_xlsx"):
        st.rerun()


# DM.23.2: fin de la definición de la ventana modal

resultado_xlsx_guardado = st.session_state.pop(
    "resultado_importacion_xlsx", None
)

if resultado_xlsx_guardado is not None:
    vina_resultado, resultado = resultado_xlsx_guardado

    if vina_resultado == VINA_ID_ACTUAL:
        st.success(
            f"{resultado['mediciones_creadas']} "
            "mediciones registradas. "
            f"{resultado['mediciones_omitidas']} "
            "mediciones existentes conservadas."
        )


if seccion_actual == "Mapa y monitoreo de plantas":
    with panel_cargas:

        acceso_carga = st.session_state.pop(
            "fenologia_acceso_carga", None
        )

        es_admin = usuario_actual["rol"] == "administrador"

        columnas_carga = st.columns(
            3 if es_admin else 2,
            gap="small"
        )

        with columnas_carga[0]:

            if st.button(
                "Cargar xlsx fenologia",
                key="dm5_xlsx_fenologia",
                type="primary",
                use_container_width=True
            ) or acceso_carga == "xlsx":
                ventana_xlsx_fenologia()

        with columnas_carga[1]:

            if st.button(
                "Importar ZIP",
                key="dm5_zip_dispositivo",
                type="primary",
                use_container_width=True
            ) or acceso_carga == "zip":
                limpiar_estados_zip_dispositivo()

                identidad_apertura_zip = (
                    obtener_identidad_sesion_zip(
                        st.session_state.get("usuario")
                    )
                )

                st.session_state["dm26_identidad_zip"] = (
                    identidad_apertura_zip
                )

                ventana_zip_dispositivo(
                    identidad_apertura_zip
                )

        if es_admin:

            with columnas_carga[2]:

                if st.button(
                    "Registrar plantas",
                    key="dm5_csv_plantas",
                    use_container_width=True
                ):
                    ventana_csv_plantas()

        resultado_csv = st.session_state.pop(
            "csv_estructural_resultado", None
        )

        if resultado_csv and resultado_csv[0] == VINA_ID_ACTUAL:

            resultado = resultado_csv[1]

            st.success(
                f"{resultado['plantas_creadas']} plantas registradas. "
                f"{resultado['plantas_omitidas']} existentes conservadas."
            )

    st.divider()

    # Contenedores asociados al panel derecho
    filtros_col = panel_visualizacion.container()
    mapa_col = panel_visualizacion.container()

    # La ficha de planta permanece debajo de las columnas.
    der = st.container()

    # ---- Filtros compactos del mapa
    with filtros_col:

        hay_mediciones = bool(fechas and params)

        col_param, col_modo = st.columns(
            2, gap="medium"
        )

        with col_param:

            if hay_mediciones:

                param = st.selectbox(
                    "Indicador",
                    params,
                    format_func=lambda k: info(k)["nombre"],
                    key="selector_parametro_mapa"
                )

            else:

                param = None
                st.caption("Sin indicadores registrados.")

        with col_modo:

            modo_mediciones = st.selectbox(
                "Mediciones",
                [
                    "Último registro por planta",
                    "Fecha específica"
                ],
                key=f"modo_mediciones_{VINA_ID_ACTUAL}"
            )

        modo_ultimo = (
            modo_mediciones == "Último registro por planta"
        )

        fecha = None
        fecha2 = None
        comparar = False

        col_cuartel, col_variedad = st.columns(
            2, gap="medium"
        )

        with col_cuartel:

            sel_cuartel = st.multiselect(
                "Cuartel",
                sorted(estructura_mapa["cuartel"].unique()),
                placeholder="Todos los cuarteles",
                key=f"filtro_cuartel_{VINA_ID_ACTUAL}"
            )

        with col_variedad:

            sel_variedad = st.multiselect(
                "Variedad",
                sorted(estructura_mapa["variedad"].unique()),
                placeholder="Todas las variedades",
                key=f"filtro_variedad_{VINA_ID_ACTUAL}"
            )

        if modo_ultimo:

            if fechas:

                ultima_fecha_registrada = max(
                    pd.Timestamp(f).date()
                    for f in fechas
                )

                st.caption(
                    "Última medición registrada: "
                    f"{ultima_fecha_registrada:%d/%m/%Y}. "
                    "Cada planta muestra su registro más reciente."
                )

            else:

                st.caption("Sin mediciones registradas.")

        elif fechas:

            fechas_calendario = {
                pd.Timestamp(f).date(): f
                for f in fechas
            }

            col_fecha, col_comparacion = st.columns(2)

            with col_fecha:

                fecha_elegida = st.date_input(
                    "Fecha de lectura",
                    value=max(fechas_calendario),
                    min_value=min(fechas_calendario),
                    max_value=max(fechas_calendario),
                    format="DD/MM/YYYY",
                    key=f"calendario_lectura_{VINA_ID_ACTUAL}"
                )

                fecha = fechas_calendario.get(
                    fecha_elegida,
                    fecha_elegida.isoformat()
                )

                if fecha_elegida not in fechas_calendario:

                    st.warning(
                        "No existen mediciones para esta fecha."
                    )

            with col_comparacion:

                if hay_mediciones and len(fechas_calendario) >= 2:

                    comparar = st.checkbox(
                        "Comparar con otra fecha",
                        key=f"comparar_mapa_{VINA_ID_ACTUAL}"
                    )

                    if comparar:

                        fechas_alternativas = [
                            f for f in fechas_calendario
                            if f != fecha_elegida
                        ]

                        fechas_previas = [
                            f for f in fechas_alternativas
                            if f < fecha_elegida
                        ]

                        fecha_comparacion_default = (
                            max(fechas_previas)
                            if fechas_previas
                            else min(fechas_alternativas)
                        )

                        fecha_comparacion = st.date_input(
                            "Fecha de comparación",
                            value=fecha_comparacion_default,
                            min_value=min(fechas_calendario),
                            max_value=max(fechas_calendario),
                            format="DD/MM/YYYY",
                            key=f"calendario_comparacion_{VINA_ID_ACTUAL}"
                        )

                        if fecha_comparacion == fecha_elegida:

                            st.warning(
                                "Selecciona una fecha diferente."
                            )

                            comparar = False

                        elif (
                            fecha_comparacion not in fechas_calendario
                            or fecha_elegida not in fechas_calendario
                        ):

                            st.warning(
                                "Ambas fechas deben tener mediciones."
                            )

                            comparar = False

                        else:

                            fecha2 = fechas_calendario[
                                fecha_comparacion
                            ]

        else:

            st.caption("Sin mediciones registradas.")

    # ---- Todas las plantas registradas
    if modo_ultimo:
        act = preparar_ultimos_registros(
            estructura_mapa,
            datos,
            parametros=params
        )
    else:
        act = preparar_datos_fecha(
            estructura_mapa,
            datos,
            fecha=fecha,
            parametros=params
        )

        act["fecha_medicion"] = fecha
        act.loc[
            ~act["tiene_medicion"],
            "fecha_medicion"
        ] = None

    act["fecha_visible"] = (
        act["fecha_medicion"]
        .fillna("Sin medición")
        .astype(str)
    )

    if comparar:
        anterior = preparar_datos_fecha(
            estructura_mapa,
            datos,
            fecha=fecha2,
            parametros=params
        )
        act["delta"] = act[param] - anterior[param]

    visible = pd.Series(True, index=act.index)

    if sel_cuartel:
        visible &= act["cuartel"].isin(sel_cuartel)

    if sel_variedad:
        visible &= act["variedad"].isin(sel_variedad)

    dentro = act.loc[visible]
    fuera = act.loc[~visible]

    # ---- Planta seleccionada: clic en el mapa o búsqueda por ID

    clics = [
        p for p in (
            (st.session_state.get("mapa") or {})
            .get("selection", {})
            .get("points", [])
        )
        if p.get("customdata")
    ]

    # Si se busca una planta por ID, guardar su selección
    if busca in act.index:
        st.session_state["planta_seleccionada"] = busca

    # Si se hace clic en otra planta del mapa, actualizar la selección
    elif clics:
        st.session_state["planta_seleccionada"] = clics[0]["customdata"][0]

    # Recuperar la última planta seleccionada
    pid = st.session_state.get("planta_seleccionada")

    if pid not in act.index:
        pid = None

    plant_internal_id = (
        act.loc[pid, "plant_internal_id"]
        if pid is not None else None
    )

    # ---- Mapa
    with mapa_col:
        P = (
            info(param)
            if param is not None
            else {"nombre": "Sin mediciones", "unidad": ""}
        )

        columna_color = "delta" if comparar else param

        if columna_color is not None:
            valores = pd.to_numeric(
                dentro[columna_color],
                errors="coerce"
            )
            mascara_valores = valores.notna() & np.isfinite(valores)
        else:
            mascara_valores = pd.Series(
                False, index=dentro.index
            )

        con_valores = dentro.loc[mascara_valores]
        sin_valores = dentro.loc[~mascara_valores]

        fig = go.Figure()

        fig.add_trace(go.Scattermap(
            lat=fuera["lat_mapa"],
            lon=fuera["lon_mapa"],
            mode="markers",
            hoverinfo="skip",
            marker=dict(
                size=5,
                color="rgba(220,222,210,.35)"
            ),
            showlegend=False
        ))

        if not sin_valores.empty:
            fig.add_trace(go.Scattermap(
                lat=sin_valores["lat_mapa"],
                lon=sin_valores["lon_mapa"],
                mode="markers",
                name="Sin datos disponibles",
                showlegend=True,
                customdata=sin_valores.reset_index()[
                    ["id", "cuartel", "variedad", "fecha_visible"]
                ].values,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "%{customdata[2]}<br>"
                    "Medición: %{customdata[3]}<br>"
                    "Sin datos disponibles<extra></extra>"
                ),
                marker=dict(
                    size=7,
                    color="#92979e",
                    opacity=.9
                )
            ))

        if not con_valores.empty:
            fig.add_trace(go.Scattermap(
                lat=con_valores["lat_mapa"],
                lon=con_valores["lon_mapa"],
                mode="markers",
                showlegend=False,
                customdata=con_valores.reset_index()[
                    ["id", "cuartel", "variedad", "fecha_visible"]
                ].values,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "%{customdata[2]}<br>"
                    "Medición: %{customdata[3]}<br>"
                    + P["nombre"]
                    + ": %{marker.color:.2f}<extra></extra>"
                ),
                marker=dict(
                    size=7,
                    color=con_valores[columna_color],
                    opacity=.95,
                    colorscale="RdYlGn" if comparar else "Viridis",
                    cmid=0 if comparar else None,
                    showscale=True,
                    colorbar=dict(
                        title=(
                            ("Cambio en " if comparar else "")
                            + P["nombre"]
                            + (f" ({P['unidad']})" if P["unidad"] else "")
                        ),
                        orientation="h",
                        y=-0.02,
                        thickness=12,
                        len=.6
                    )
                )
            ))

        if pid:
            s = act.loc[pid]
            fig.add_trace(go.Scattermap(lat=[s["lat_mapa"]], lon=[s["lon_mapa"]], mode="markers", hoverinfo="skip",
                                        marker=dict(size=17, color="white", opacity=.9), showlegend=False))
        # Centrado seguro utilizando coordenadas válidas.
        coordenadas_validas = act[
            ["lat_mapa", "lon_mapa"]
        ].dropna()

        planta_buscada = (
            act.loc[busca]
            if busca in act.index
            else None
        )

        if (
            planta_buscada is not None
            and pd.notna(planta_buscada["lat_mapa"])
            and pd.notna(planta_buscada["lon_mapa"])
        ):
            centro = planta_buscada[
                ["lat_mapa", "lon_mapa"]
            ]

        elif not coordenadas_validas.empty:
            centro = coordenadas_validas.mean()

        elif (
            latitud_guardada is not None
            and longitud_guardada is not None
        ):
            centro = pd.Series({
                "lat_mapa": latitud_guardada,
                "lon_mapa": longitud_guardada,
            })

        else:
            # Centro técnico de respaldo para el mapa vacío.
            # No se asigna a ninguna planta ni se guarda.
            centro = pd.Series({
                "lat_mapa": LAT0,
                "lon_mapa": LON0,
            })

        if coordenadas_validas.empty:
            st.warning(
                "No existen plantas con coordenadas disponibles "
                "en el mapa. Si faltan coordenadas, registra la ubicación de la "
                "viña para visualizar las posiciones provisionales."
            )
        F = FONDOS[fondo]
        fig.update_layout(height=720, margin=dict(l=0, r=0, t=0, b=0), uirevision=busca or "fijo",
                        map=dict(style=F["style"], layers=F["layers"], center=dict(lat=centro["lat_mapa"], lon=centro["lon_mapa"]),
                                zoom=19 if busca in act.index else 17.6))
        st.plotly_chart(fig, key="mapa", on_select="rerun", selection_mode="points", width="stretch",
                        config={"scrollZoom": True, "displaylogo": False})
        # Información sobre ubicaciones provisionales.
        cantidad_provisionales = int(
            dentro["posicion_provisional"].sum()
        )

        if cantidad_provisionales > 0:
            st.info(
                f"📍 {cantidad_provisionales} plantas visibles "
                "tienen una ubicación provisional calculada. "
                "Estas posiciones son referenciales y "
                "no corresponden a coordenadas GPS medidas."
            )

        titulo = (
            f"{fecha} frente a {fecha2}"
            if comparar
            else (
                "Último registro por planta"
                if modo_ultimo
                else (fecha or "Mapa estructural")
            )
        )

        st.caption(
            f"{len(con_valores)} plantas con valores disponibles · "
            f"{len(sin_valores)} sin datos disponibles"
        )
        st.caption(f"{NOMBRE_VINA} · {titulo} · {len(dentro):,} de {len(act):,} plantas visibles".replace(",", "."))

    # ---- Ficha de la planta (barra derecha)
    # ---- Resumen dinámico de cuartel y variedad
    st.divider()
    st.subheader("Resumen de la selección")

    descripcion = []
    if sel_cuartel:
        descripcion.append("Cuartel: " + ", ".join(map(str, sel_cuartel)))
    if sel_variedad:
        descripcion.append("Variedad: " + ", ".join(map(str, sel_variedad)))

    st.caption(
        " · ".join(descripcion) if descripcion
        else "Todas las plantas de la viña"
    )
    st.caption(
        "Últimas mediciones individuales disponibles"
        if modo_ultimo
        else (
            f"Fecha de medición: {fecha}"
            if fecha is not None
            else "Sin fecha de medición registrada"
        )
    )

    resumen_plantas = dentro.copy()

    total_seleccion = len(resumen_plantas)

    medidas = resumen_plantas.loc[
        resumen_plantas["tiene_medicion"]
    ]

    total_medidas = len(medidas)
    total_sin_mediciones = total_seleccion - total_medidas

    if modo_ultimo and not medidas.empty:
        fechas_individuales = medidas["fecha_medicion"].dropna()

        if not fechas_individuales.empty:
            st.caption(
                f"Período de las mediciones mostradas: "
                f"{fechas_individuales.min()} a "
                f"{fechas_individuales.max()}. "
                "Los indicadores pueden combinar fechas distintas."
            )

    met1, met2, met3 = st.columns(3)

    met1.metric("Plantas seleccionadas", total_seleccion)
    met2.metric("Con mediciones", total_medidas)
    met3.metric("Sin mediciones", total_sin_mediciones)

    if total_seleccion == 0:
        st.info(
            "No hay plantas para los filtros seleccionados."
        )

    elif total_medidas == 0:
        st.info(
            "Las plantas seleccionadas todavía no tienen historial."
            if modo_ultimo
            else (
                "Las plantas están registradas, pero todavía "
                "no tienen mediciones para la fecha seleccionada."
            )
        )

    else:
        alerta_por_planta = pd.Series(
            False, index=medidas.index
        )

        evaluables = pd.Series(
            False, index=medidas.index
        )

        for parametro_alerta, (operador, umbral) in ALERTAS.items():

            if parametro_alerta not in medidas.columns:
                continue

            valores_alerta = pd.to_numeric(
                medidas[parametro_alerta],
                errors="coerce"
            )

            validos = (
                valores_alerta.notna()
                & np.isfinite(valores_alerta)
            )

            evaluables |= validos

            if operador == "<":
                alerta_por_planta |= (
                    validos & (valores_alerta < umbral)
                )
            elif operador == ">":
                alerta_por_planta |= (
                    validos & (valores_alerta > umbral)
                )

        total_evaluables = int(evaluables.sum())
        total_alertadas = int(alerta_por_planta.sum())

        porcentaje_alertas = (
            100 * total_alertadas / total_evaluables
            if total_evaluables else None
        )

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Plantas evaluables",
            total_evaluables
        )

        col2.metric(
            "Plantas con alertas",
            total_alertadas if total_evaluables else "Sin datos"
        )

        col3.metric(
            "Porcentaje con alertas",
            f"{porcentaje_alertas:.1f}%"
            if porcentaje_alertas is not None
            else "Sin datos"
        )

        st.caption(
            "Las alertas se calculan únicamente sobre plantas "
            "con valores válidos para los umbrales configurados."
        )

        promedios = []

        for parametro_resumen in PARAMETROS:

            if parametro_resumen not in medidas.columns:
                continue

            valores = pd.to_numeric(
                medidas[parametro_resumen],
                errors="coerce"
            )

            valores = valores[
                valores.notna() & np.isfinite(valores)
            ]

            if valores.empty:
                continue

            promedios.append({
                "Indicador": info(parametro_resumen)["nombre"],
                "Promedio": round(
                    float(valores.mean()),
                    info(parametro_resumen)["dec"]
                ),
                "Unidad": info(parametro_resumen)["unidad"]
            })

        if promedios:
            st.markdown(
                "**Promedios de los parámetros disponibles**"
            )

            st.dataframe(
                pd.DataFrame(promedios),
                use_container_width=True,
                hide_index=True
            )

        st.caption(
            "Este resumen no constituye por sí solo "
            "un diagnóstico agronómico definitivo."
        )

    with der:

        if param is not None and not con_valores.empty:

            columna_promedio = "delta" if comparar else param

            m = con_valores[columna_promedio].mean()

            st.caption(
                ("Cambio promedio: " if comparar
                 else "Promedio de las visibles: ")
                + fmt(m, param)
            )

        st.divider()
        if not pid:
            st.write("Haz zoom en el mapa y haz clic en una planta para ver su ficha, o búscala por ID en la barra izquierda.")
        else:
            s = act.loc[pid]
            st.subheader(pid)

            fecha_planta = (
                str(s["fecha_medicion"])
                if s["tiene_medicion"]
                and pd.notna(s["fecha_medicion"])
                else None
            )

            st.caption(
                f"Fecha de medición: {fecha_planta}"
                if fecha_planta
                else "Sin medición disponible"
            )

            st.caption(
                f"Cuartel {s['cuartel']} · {s['variedad']} · "
                f"Fila {s['fila']} · Planta {s['planta']}"
            )

            if pd.notna(s["lat"]) and pd.notna(s["lon"]):

                st.caption(
                    f"GPS: {s['lat']:.6f}, {s['lon']:.6f}"
                )

            elif s["posicion_provisional"]:

                st.caption(
                    f"Ubicación provisional: "
                    f"{s['lat_mapa']:.6f}, {s['lon_mapa']:.6f}"
                )

            else:
                st.caption("Sin coordenadas disponibles")

            if not s["tiene_medicion"]:

                st.info(
                    "Planta registrada sin historial de mediciones."
                    if modo_ultimo
                    else (
                        "Planta registrada sin mediciones "
                        "para la fecha seleccionada."
                    )
                )

            else:

                alertas = []
                parametros_evaluados = 0

                for k, (op, u) in ALERTAS.items():

                    if k not in params:
                        continue

                    valor = pd.to_numeric(
                        s[k], errors="coerce"
                    )

                    if pd.isna(valor) or not np.isfinite(valor):
                        continue

                    parametros_evaluados += 1

                    if (
                        (op == "<" and valor < u)
                        or (op == ">" and valor > u)
                    ):
                        alertas.append(
                            f"{info(k)['nombre']} {op} {u}"
                        )

                if alertas:
                    st.warning(
                        "Atención: " + "; ".join(alertas)
                    )

                elif parametros_evaluados == 0:
                    st.info(
                        "Sin datos suficientes para evaluar alertas."
                    )

                else:
                    st.success(
                        "Sin alertas en los parámetros evaluados."
                    )

            ant = anterior.loc[pid] if comparar else None

            plantas_claro_ficha = consultar_claro_monitoreado(
                VINA_ID_ACTUAL,
                s["cuartel"]
            ) or []

            pertenece_al_claro = any(
                str(planta[1]) == str(plant_internal_id)
                for planta in plantas_claro_ficha
            )

            etiquetas_ficha = [
                "Mediciones",
                "Evolución",
                "Fotografías e IA"
            ]

            if pertenece_al_claro:
                etiquetas_ficha.append("Registro dispositivo")

            pestanas_ficha = st.tabs(etiquetas_ficha)

            tab_mediciones = pestanas_ficha[0]
            tab_evolucion = pestanas_ficha[1]
            tab_fotografias = pestanas_ficha[2]

            with tab_mediciones:

                if not s["tiene_medicion"] or not params:

                    st.info(
                        "No hay mediciones fenológicas "
                        "disponibles para esta planta y fecha."
                    )

                else:

                    st.markdown("**Mediciones de la planta**")

                    columnas_mediciones = st.columns(
                        3, gap="medium"
                    )

                    for i, k in enumerate(params):

                        valor = s[k]

                        disponible = (
                            pd.notna(valor)
                            and np.isfinite(valor)
                        )

                        cambio = None

                        if (
                            comparar
                            and disponible
                            and pd.notna(ant[k])
                            and np.isfinite(ant[k])
                        ):
                            cambio = fmt(valor - ant[k], k)

                        with columnas_mediciones[i % 3]:

                            st.metric(
                                info(k)["nombre"],
                                fmt(valor, k)
                                if disponible else "Sin datos",
                                cambio
                            )

            with tab_evolucion:

                if (
                    param is None
                    or datos.empty
                    or not datos.loc[
                        datos["id"] == pid, param
                    ].notna().any()
                ):
                    st.info(
                        "Todavía no existe un historial "
                        "para este parámetro y planta."
                    )

                else:
                    # Historial de la capa activa: planta vs promedio del cuartel
                    hist = datos[datos["id"] == pid].set_index("fecha")[param]
                    prom = datos[datos["cuartel"] == s["cuartel"]].groupby("fecha")[param].mean()
                    g = px.line(pd.DataFrame({"Esta planta": hist, "Promedio del cuartel": prom}).reset_index(),
                                x="fecha", y=["Esta planta", "Promedio del cuartel"], markers=True,
                                title=f"Historial de {P['nombre']}")
                    g.update_traces(selector=dict(name="Promedio del cuartel"), line_dash="dash")
                    g.update_layout(height=260, margin=dict(l=0, r=0, t=40, b=0), legend_title=None, xaxis_title=None,
                                    yaxis_title=P["unidad"] or None, legend=dict(orientation="h", y=-0.25))
                    st.plotly_chart(g, width="stretch")


            if pertenece_al_claro:
                with pestanas_ficha[3]:
                    from database import (
                        consultar_capturas_ambientales,
                        consultar_ambiente_fotografia
                    )

                    st.markdown("### Historial ambiental del dispositivo")

                    st.caption(
                        "Mediciones locales registradas al momento "
                        "de la captura. Independientes de las "
                        "estimaciones meteorológicas de Open-Meteo."
                    )

                    try:

                        capturas_ambientales = consultar_capturas_ambientales(
                            plant_internal_id,
                            VINA_ID_ACTUAL,
                            usuario_actual["usuario_id"]
                        )

                    except PermissionError:

                        capturas_ambientales = []
                        st.error("No tienes autorización para consultar estos datos.")

                    else:

                        if not capturas_ambientales:

                            st.info(
                                "Esta planta todavía no tiene capturas "
                                "ambientales del dispositivo."
                            )

                        else:

                            ultima = capturas_ambientales[0]

                            temperatura = ultima["temperatura_ambiental"]
                            humedad = ultima["humedad_ambiental"]

                            col_temp, col_hum = st.columns(2)

                            col_temp.metric(
                                "Temperatura ambiental",
                                f"{temperatura:.1f} °C".replace(".", ",")
                                if temperatura is not None else "Sin datos"
                            )

                            col_hum.metric(
                                "Humedad relativa",
                                f"{humedad:.1f} %".replace(".", ",")
                                if humedad is not None else "Sin datos"
                            )

                            st.caption(
                                f"Última captura: {ultima['fecha_hora']} · "
                                f"Dispositivo: {ultima['device_id']}"
                            )

                            tabla_ambiental = pd.DataFrame(
                                capturas_ambientales
                            )

                            tabla_ambiental = tabla_ambiental.rename(columns={
                                "fecha_hora": "Fecha y hora",
                                "temperatura_ambiental": "Temperatura (°C)",
                                "humedad_ambiental": "Humedad relativa (%)",
                                "device_id": "Dispositivo",
                                "tiene_fotografia": "Fotografía"
                            })

                            tabla_ambiental["Fotografía"] = (
                                tabla_ambiental["Fotografía"].map({
                                    1: "Sí",
                                    0: "No"
                                })
                            )

                            with st.expander(
                                "Ver historial de capturas ambientales"
                            ):

                                st.caption(
                                    "Selecciona una fila para consultar su fotografía."
                                )

                                seleccion_ambiental = st.dataframe(
                                    tabla_ambiental[[
                                        "Fecha y hora",
                                        "Temperatura (°C)",
                                        "Humedad relativa (%)",
                                        "Dispositivo",
                                        "Fotografía"
                                    ]],
                                    hide_index=True,
                                    use_container_width=True,
                                    on_select="rerun",
                                    selection_mode="single-row",
                                    key=f"historial_ambiental_{VINA_ID_ACTUAL}_{plant_internal_id}"
                                )

                                @st.dialog("Fotografía de la captura", width="large")
                                def mostrar_fotografia_captura(captura):

                                    from contextlib import closing
                                    from database import verificar_permiso_mediciones

                                    try:
                                        with closing(conectar()) as conexion:

                                            conexion.execute("PRAGMA query_only = ON")

                                            verificar_permiso_mediciones(
                                                conexion,
                                                usuario_actual["usuario_id"],
                                                VINA_ID_ACTUAL
                                            )

                                            fotos = conexion.execute("""
                                                SELECT ruta_archivo
                                                FROM vista_imagenes_origen
                                                WHERE captura_id = ?
                                                  AND plant_id = ?
                                                  AND vina_id = ?
                                                  AND origen = 'CAPTURA_DISPOSITIVO'
                                            """, (
                                                captura["captura_id"],
                                                plant_internal_id,
                                                VINA_ID_ACTUAL
                                            )).fetchall()

                                    except PermissionError:
                                        st.error("Consulta no autorizada.")
                                        return

                                    st.caption(
                                        f"Fecha: {captura['fecha_hora']} · "
                                        f"Dispositivo: {captura['device_id']}"
                                    )

                                    if not fotos:
                                        st.warning("No se encontró la fotografía registrada.")

                                    for foto in fotos:

                                        ruta_foto = obtener_ruta_fotografia_segura(foto[0])

                                        if ruta_foto is not None:
                                            st.image(str(ruta_foto), width="stretch")
                                        else:
                                            st.warning("Fotografía no disponible.")

                                    if st.button(
                                        "Cerrar fotografía",
                                        key="cerrar_foto_historial"
                                    ):
                                        st.rerun()

                                filas_seleccionadas = seleccion_ambiental.selection.rows

                                clave_seleccion = (
                                    f"ultima_foto_ambiental_{VINA_ID_ACTUAL}_{plant_internal_id}"
                                )

                                if filas_seleccionadas:

                                    posicion = filas_seleccionadas[0]

                                    if 0 <= posicion < len(capturas_ambientales):

                                        captura_elegida = capturas_ambientales[posicion]

                                        if captura_elegida["tiene_fotografia"] == 1:

                                            if st.session_state.get(clave_seleccion) != (
                                                captura_elegida["captura_id"]
                                            ):

                                                st.session_state[clave_seleccion] = (
                                                    captura_elegida["captura_id"]
                                                )

                                                mostrar_fotografia_captura(captura_elegida)

                                        else:
                                            st.session_state.pop(clave_seleccion, None)
                                            st.caption("Esta captura no tiene fotografía.")

                                else:
                                    st.session_state.pop(clave_seleccion, None)



            with tab_fotografias:
                st.subheader("📸 Historial fotográfico")

                # FORMULARIO PARA SUBIR FOTOGRAFÍAS

                if not s["tiene_medicion"]:

                    st.info(
                        "Para adjuntar una fotografía debes "
                        "registrar primero una medición "
                        "de esta planta."
                    )

                else:
                    with st.form(key=f"form_foto_{pid}_{fecha_planta}"):

                        foto = st.file_uploader(
                            "Seleccionar fotografía de esta planta",
                            type=["jpg", "jpeg", "png"],
                            key=f"foto_{pid}_{fecha_planta}"
                        )

                        guardar = st.form_submit_button("💾 Guardar fotografía")

                        if guardar:

                            if foto is None:
                                st.warning("Primero debes seleccionar una fotografía.")

                            else:
                                with conectar() as conexion:
                                    resultado = conexion.execute("""
                                    SELECT m.measurement_id
                                    FROM mediciones m
                                    JOIN plantas p ON p.id = m.plant_id
                                    WHERE m.plant_id = ?
                                    AND p.vina_id = ?
                                    AND substr(m.fecha_hora, 1, 10) = ?
                                    ORDER BY m.fecha_hora DESC
                                    LIMIT 1
                                """, (plant_internal_id, VINA_ID_ACTUAL, fecha_planta[:10])).fetchone()

                                if resultado is None:
                                    st.error("No se encontró una medición para esta planta y fecha.")

                                else:
                                    from database import (
                                        registrar_fotografia_manual_segura
                                    )

                                    try:

                                        registro_fotografico = (
                                            registrar_fotografia_manual_segura(
                                                measurement_id=resultado[0],
                                                contenido=foto.getvalue(),
                                                nombre_original=foto.name,
                                                vina_id=VINA_ID_ACTUAL,
                                                usuario_id=usuario_actual['usuario_id']
                                            )
                                        )

                                        if (
                                            registro_fotografico.get(
                                                "registro_bd_realizado"
                                            ) is not True
                                            or registro_fotografico.get(
                                                "fotografia_guardada"
                                            ) is not True
                                        ):
                                            raise RuntimeError(
                                                "No se pudo confirmar el registro fotográfico."
                                            )

                                    except PermissionError:

                                        st.error(
                                            "Tu cuenta no está autorizada para "
                                            "adjuntar fotografías a esta medición."
                                        )

                                    except ValueError as error:

                                        st.error(str(error))

                                    except Exception:

                                        st.error(
                                            "No fue posible confirmar el guardado "
                                            "de la fotografía. El registro requiere "
                                            "revisión antes de volver a intentarlo."
                                        )

                                    else:

                                        st.success(
                                            "¡Fotografía guardada correctamente!"
                                        )


                from database import consultar_ambiente_fotografia

                imagenes = consultar_imagenes_por_planta(
                    plant_internal_id,
                    VINA_ID_ACTUAL
                )

                # Fotografías del dispositivo disponibles
                # desde el historial ambiental.
                imagenes = [
                    imagen for imagen in imagenes
                    if imagen[4] is not None
                ]

                if not imagenes:
                    pass

                else:
                    for imagen in imagenes:

                        image_id, ruta_archivo, tipo, fecha_subida, measurement_id, fecha_hora, plant_id = imagen

                        @st.dialog(
                            "Fotografía de la planta",
                            width="large",
                            dismissible=True
                        )
                        def abrir_fotografia_monitoreo(
                            image_id, ruta_archivo, fecha_hora
                        ):

                            if st.button(
                                "Cerrar ventana",
                                key=f"cerrar_monitoreo_{image_id}"
                            ):
                                st.rerun()

                            st.write(f"Fecha de captura: {fecha_hora}")

                            from database import (
                                consultar_ambiente_fotografia
                            )

                            try:

                                ambiente_foto = consultar_ambiente_fotografia(
                                    image_id,
                                    VINA_ID_ACTUAL,
                                    usuario_actual["usuario_id"]
                                )

                            except PermissionError:

                                ambiente_foto = None
                                st.warning("Datos ambientales no autorizados.")

                            if ambiente_foto is not None:

                                st.markdown("**Condiciones ambientales de la captura**")

                                temperatura_foto = ambiente_foto[
                                    "temperatura_ambiental"
                                ]

                                humedad_foto = ambiente_foto[
                                    "humedad_ambiental"
                                ]

                                c_temp, c_hum = st.columns(2)

                                c_temp.metric(
                                    "Temperatura",
                                    f"{temperatura_foto:.1f} °C".replace(".", ",")
                                    if temperatura_foto is not None else "—"
                                )

                                c_hum.metric(
                                    "Humedad relativa",
                                    f"{humedad_foto:.1f} %".replace(".", ",")
                                    if humedad_foto is not None else "—"
                                )

                                st.caption(
                                    "Fuente: dispositivo "
                                    + ambiente_foto["device_id"]
                                )

                            ruta = obtener_ruta_fotografia_segura(ruta_archivo)

                            if ruta is not None:
                                st.image(str(ruta), width=400)

                                mostrar_editor_fenologia(
                                    ruta, image_id, VINA_ID_ACTUAL, "monitoreo"
                                )

                                # HISTORIAL PERMANENTE DE ANÁLISIS
                                st.divider()
                                st.write("**📊 Historial de análisis de esta fotografía**")

                                historial = consultar_analisis_por_imagen(
                                    image_id,
                                    VINA_ID_ACTUAL
                                )

                                if historial:

                                    for registro in historial:

                                        (
                                            analisis_id,
                                            imagen_id,
                                            modelo,
                                            version,
                                            cantidad_racimos,
                                            verde,
                                            envero,
                                            morado,
                                            etapa,
                                            confianza,
                                            resultado_json,
                                            fecha_analisis
                                        ) = registro

                                        st.caption(f"Fecha: {fecha_analisis}")

                                        st.write(f"**Modelo:** {modelo} · Versión: {version}")

                                        if resultado_json:
                                            datos_analisis = json.loads(resultado_json)

                                            if modelo == "FenologIA - SAM 2":
                                                mostrar_resultados_fenologia(datos_analisis, f"historial_monitoreo_{image_id}_{analisis_id}")

                                            elif modelo == "Roboflow":
                                                st.metric(
                                                    "Detecciones de uvas",
                                                    datos_analisis.get("cantidad_detecciones", 0)
                                                )

                                                confianzas = datos_analisis.get(
                                                    "confianzas", []
                                                )

                                                if confianzas:
                                                    st.write(
                                                        f"Confianza máxima: {max(confianzas):.2f}%"
                                                    )
                                                else:
                                                    st.info(
                                                        "No se encontraron detecciones "
                                                        "sobre el umbral configurado."
                                                    )

                                                ruta_diagnostico = datos_analisis.get(
                                                    "imagen_resultado"
                                                )

                                                ruta_diagnostico = (
                                                    obtener_ruta_resultado_ia_segura(
                                                        ruta_diagnostico,
                                                        "roboflow"
                                                    )
                                                )

                                                if ruta_diagnostico is not None:
                                                    st.image(
                                                        str(ruta_diagnostico),
                                                        caption="Detecciones de Roboflow",
                                                        width=400
                                                    )

                                                st.caption(
                                                    datos_analisis.get(
                                                        "advertencia", ""
                                                    )
                                                )

                                            elif modelo == "Segmentación HSV experimental":
                                                col1, col2 = st.columns(2)

                                                col1.metric(
                                                    "Zonas verdes",
                                                    f"{datos_analisis.get('porcentaje_verde', 0)}%"
                                                )

                                                col2.metric(
                                                    "Zonas oscuras",
                                                    f"{datos_analisis.get('porcentaje_zonas_oscuras', 0)}%"
                                                )

                                                st.metric(
                                                    "Otros píxeles",
                                                    f"{datos_analisis.get('porcentaje_otros', 0)}%"
                                                )

                                                st.caption(
                                                    f"Método: {datos_analisis.get('metodo', 'No especificado')}"
                                                )

                                            with st.expander(
                                                "Ver detalles técnicos del análisis"
                                            ):
                                                st.json(datos_analisis)

                                        st.divider()

                                else:
                                    st.info("Esta fotografía todavía no tiene análisis registrados.")

                            else:
                                st.warning(f"No se encontró el archivo: {ruta_archivo}")


                        if st.button(
                            f"Ver fotografía · {fecha_hora}",
                            key=f"abrir_monitoreo_{image_id}",
                            width="stretch"
                        ):
                            abrir_fotografia_monitoreo(
                                image_id, ruta_archivo, fecha_hora
                            )


# =========================================================
# RESUMEN Y DIAGNÓSTICO INTELIGENTE
# =========================================================

if seccion_actual == "Resumen y diagnóstico inteligente":

    st.title("Diagnóstico de mi viña")

    st.caption(
        f"Estado general de {NOMBRE_VINA}"
    )

    datos_resumen = consultar_datos(VINA_ID_ACTUAL)

    if datos_resumen.empty:

        st.info(
            "Esta viña todavía no tiene mediciones de plantas "
            "registradas. Cuando incorpores datos, aquí aparecerá "
            "el resumen y diagnóstico."
        )

    else:

        # -----------------------------------------------------
        # ÚLTIMA FECHA Y MEDICIONES ACTUALES
        # -----------------------------------------------------

        fecha_ultima = datos_resumen["fecha"].max()

        datos_actuales = (
            datos_resumen
            .sort_values("fecha")
            .drop_duplicates(subset=["id"], keep="last")
            .copy()
        )

        fecha_mas_antigua = datos_actuales["fecha"].min()

        plantas_registradas_resumen = (
            consultar_plantas_registradas(VINA_ID_ACTUAL)
        )

        total_registradas = len(plantas_registradas_resumen)

        total_sin_historial = (
            total_registradas
            - datos_actuales["id"].nunique()
        )

        total_plantas = datos_actuales["id"].nunique()

        total_mediciones = len(datos_resumen)

        total_cuarteles = (
            datos_actuales["cuartel"].nunique()
            if "cuartel" in datos_actuales.columns
            else 0
        )

        total_variedades = (
            datos_actuales["variedad"].nunique()
            if "variedad" in datos_actuales.columns
            else 0
        )

        st.caption(
            f"Último registro: {fecha_ultima} · "
            "Diagnóstico basado en la última medición de cada planta."
        )

        alertas_detectadas = []

        for parametro, (operador, umbral) in ALERTAS.items():

            if parametro not in datos_actuales.columns:
                continue

            valores = pd.to_numeric(
                datos_actuales[parametro],
                errors="coerce"
            )

            if operador == "<":
                condicion = valores < umbral
            elif operador == ">":
                condicion = valores > umbral
            else:
                continue

            plantas_alertadas = datos_actuales[
                condicion.fillna(False)
            ]

            for _, planta in plantas_alertadas.iterrows():

                alertas_detectadas.append({
                    "Código de planta": planta["id"],
                    "Cuartel": planta.get("cuartel"),
                    "Variedad": planta.get("variedad"),
                    "Parámetro": info(parametro)["nombre"],
                    "Valor registrado": valores.loc[
                        planta.name
                    ],
                    "Umbral": f"{operador} {umbral}"
                })

        total_plantas_alertadas = (
            len(
                set(
                    alerta["Código de planta"]
                    for alerta in alertas_detectadas
                )
            )
        )

        st.subheader("Estado general")

        col1, col2, col3 = st.columns(3)

        with col1:
            with st.container(border=True):
                st.metric(
                    "Plantas monitoreadas",
                    f"{total_plantas:,}".replace(",", ".")
                )

        with col2:
            with st.container(border=True):
                st.metric(
                    "Cobertura de monitoreo",
                    f"{100 * total_plantas / total_registradas:.1f}%"
                    if total_registradas else "Sin datos"
                )

        with col3:
            with st.container(border=True):
                st.metric(
                    "Plantas con alertas",
                    f"{total_plantas_alertadas:,}".replace(",", ".")
                )

        st.divider()

        st.subheader("Alertas por cuartel")

        if alertas_detectadas:

            st.warning(
                "Se detectaron valores fuera de los umbrales "
                "de atención configurados."
            )

            tabla_alertas = pd.DataFrame(
                alertas_detectadas
            )

            # -------------------------------------------------
            # RESUMEN POR CUARTEL
            # -------------------------------------------------



            resumen_cuarteles = (
                datos_actuales.groupby("cuartel")["id"]
                .nunique()
                .reset_index(name="Plantas medidas")
                .rename(columns={"cuartel": "Cuartel"})
            )

            plantas_alertadas_cuartel = (
                tabla_alertas.groupby("Cuartel")[
                    "Código de planta"
                ]
                .nunique()
                .reset_index(name="Plantas con alertas")
            )

            resumen_cuarteles = resumen_cuarteles.merge(
                plantas_alertadas_cuartel,
                on="Cuartel",
                how="left"
            )

            resumen_cuarteles["Plantas con alertas"] = (
                resumen_cuarteles["Plantas con alertas"]
                .fillna(0)
                .astype(int)
            )

            resumen_cuarteles["% con alertas"] = (
                resumen_cuarteles["Plantas con alertas"]
                / resumen_cuarteles["Plantas medidas"]
                * 100
            ).round(1)

            st.dataframe(
                resumen_cuarteles.sort_values(
                    "% con alertas",
                    ascending=False
                ),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "% con alertas": st.column_config.ProgressColumn(
                        "% con alertas",
                        help="Porcentaje de plantas con al menos una alerta en el cuartel.",
                        format="%.1f %%",
                        min_value=0,
                        max_value=100
                    )
                }
            )

            # -------------------------------------------------
            # DETALLE DE PLANTAS ALERTADAS
            # -------------------------------------------------

            with st.expander(
                "Consultar detalle de plantas alertadas"
            ):

                st.dataframe(
                    tabla_alertas,
                    use_container_width=True,
                    hide_index=True
                )

        else:

            st.success(
                "No se detectaron valores fuera de los umbrales "
                "configurados en la última medición."
            )


        # -----------------------------------------------------
        # RESUMEN METEOROLÓGICO
        # -----------------------------------------------------


        st.divider()

        st.subheader("Indicadores vitícolas")

        columnas_base = {
            "id",
            "plant_internal_id",
            "cuartel",
            "variedad",
            "fila",
            "planta",
            "lat",
            "lon",
            "fecha"
        }

        parametros_disponibles = [
            columna
            for columna in datos_actuales.columns
            if columna not in columnas_base
            and pd.api.types.is_numeric_dtype(
                datos_actuales[columna]
            )
        ]

        if parametros_disponibles:

            columnas_metricas = st.columns(
                min(len(parametros_disponibles), 3)
            )

            for i, parametro in enumerate(
                parametros_disponibles
            ):

                valores = pd.to_numeric(
                    datos_actuales[parametro],
                    errors="coerce"
                ).dropna()

                if not valores.empty:

                    with columnas_metricas[
                        i % len(columnas_metricas)
                    ]:

                        configuracion = info(parametro)
                        promedio = valores.mean()

                        valor_formateado = (
                            f"{promedio:.{configuracion['dec']}f}"
                            .replace(".", ",")
                        )

                        if configuracion["unidad"]:
                            valor_formateado += f" {configuracion['unidad']}"

                        with st.container(border=True):
                            st.metric(
                                configuracion["nombre"],
                                valor_formateado
                            )

        else:

            st.info(
                "No hay parámetros numéricos disponibles "
                "en la última medición."
            )

        st.caption(
            "Promedios de las últimas mediciones disponibles "
            "de cada planta."
        )

        st.divider()

        # -----------------------------------------------------
        # ALERTAS SEGÚN UMBRALES CONFIGURADOS
        # -----------------------------------------------------

        with st.expander("Contexto meteorológico"):

            st.caption(
                "Información modelada por coordenadas "
                "de la viña · Fuente: Open-Meteo."
            )

            if latitud_guardada is None or longitud_guardada is None:

                st.info(
                    "Registra la ubicación de tu viña "
                    "para incorporar información meteorológica."
                )

            else:

                from meteorologia_local import (
                    obtener_pronostico_local,
                    obtener_historial_local,
                    formato_valor_meteo,
                    descripcion_tiempo
                )

                lat = float(latitud_guardada)
                lon = float(longitud_guardada)

                try:

                    datos = obtener_pronostico_local(lat, lon)
                    actual = datos["current"]

                    st.markdown("**Condiciones actuales**")

                    st.caption(
                        f"{descripcion_tiempo(actual.get('weather_code'))}"
                        f" · {actual.get('time', '')}"
                    )

                    columnas = st.columns(3)

                    variables = [
                        ("Temperatura", "temperature_2m", "°C"),
                        ("Humedad relativa", "relative_humidity_2m", "%"),
                        ("Viento", "wind_speed_10m", "km/h")
                    ]

                    for columna, (nombre, clave, unidad) in zip(
                        columnas, variables
                    ):

                        columna.metric(
                            nombre,
                            formato_valor_meteo(
                                actual.get(clave), unidad
                            )
                        )

                except Exception:

                    st.warning(
                        "Las condiciones actuales no están "
                        "disponibles temporalmente."
                    )

                st.divider()

                try:

                    historial = obtener_historial_local(
                        lat, lon, 30
                    )

                    st.markdown("**Contexto meteorológico histórico**")

                    st.caption(
                        f"Período: {historial.fecha.min():%d-%m-%Y}"
                        f" al {historial.fecha.max():%d-%m-%Y}"
                    )

                    columnas = st.columns(3)

                    valores = [
                        (
                            "Temperatura máxima media",
                            historial.temperatura_max.mean(),
                            "°C"
                        ),
                        (
                            "Humedad relativa media",
                            historial.humedad_relativa.mean(),
                            "%"
                        ),
                        (
                            "Precipitación acumulada",
                            historial.precipitacion.sum(min_count=1),
                            "mm"
                        )
                    ]

                    for columna, (nombre, valor, unidad) in zip(
                        columnas, valores
                    ):

                        columna.metric(
                            nombre,
                            formato_valor_meteo(valor, unidad)
                        )

                    if historial.precipitacion.notna().sum() < 30:

                        st.warning(
                            "El acumulado de precipitación es parcial."
                        )

                except Exception:

                    st.warning(
                        "El historial meteorológico no está "
                        "disponible temporalmente."
                    )

                st.caption(
                    "Los datos de Open-Meteo son referenciales. "
                    "Las mediciones directas del dispositivo "
                    "deben interpretarse por separado."
                )


        with st.expander("Detalles del monitoreo e interpretación"):

            col1, col2, col3 = st.columns(3)

            col1.metric("Plantas registradas", total_registradas)
            col2.metric("Plantas sin historial", total_sin_historial)
            col3.metric("Cuarteles", total_cuarteles)

            col4, col5 = st.columns(2)

            col4.metric("Variedades", total_variedades)
            col5.metric("Registros históricos", total_mediciones)

            st.caption(
                f"Período considerado: "
                f"{fecha_mas_antigua} a {fecha_ultima}."
            )

            distribucion_fechas = (
                datos_actuales["fecha"]
                .value_counts()
                .sort_index(ascending=False)
                .rename_axis("Fecha de medición")
                .reset_index(name="Cantidad de plantas")
            )

            st.markdown("**Antigüedad de las mediciones**")

            st.dataframe(
                distribucion_fechas,
                hide_index=True,
                use_container_width=True
            )

            st.caption(
                "Las mediciones pueden corresponder a fechas "
                "diferentes. Considera su antigüedad antes de "
                "interpretar los resultados."
            )

            st.info(
                "Las alertas se basan en los umbrales configurados. "
                "Son señales para revisión y no constituyen por "
                "sí solas un diagnóstico agronómico definitivo."
            )



# =========================================================
# GALERÍA GENERAL DE FOTOGRAFÍAS Y ANÁLISIS IA
# =========================================================

if seccion_actual == "Fotografías y análisis IA":

    st.title("Fotografías e IA")

    st.caption(
        f"Galería fotográfica de {NOMBRE_VINA}"
    )

    # DF.2.9 - Navegación por claros monitoreados
    modo_galeria = st.radio(
        "Consultar fotografías",
        ["Claro monitoreado", "Todas las fotografías"],
        horizontal=True,
        key=f"df29_modo_{VINA_ID_ACTUAL}"
    )

    imagenes = consultar_todas_las_imagenes(
        VINA_ID_ACTUAL
    )

    if modo_galeria == "Claro monitoreado":

        with conectar() as conexion:
            cuarteles_galeria = [
                fila[0]
                for fila in conexion.execute(
                    """
                    SELECT DISTINCT cuartel
                    FROM plantas
                    WHERE vina_id = ?
                      AND cuartel IS NOT NULL
                    ORDER BY cuartel
                    """,
                    (VINA_ID_ACTUAL,)
                ).fetchall()
            ]

        if cuarteles_galeria:

            cuartel_galeria = st.selectbox(
                "Cuartel",
                cuarteles_galeria,
                key=f"df29_cuartel_{VINA_ID_ACTUAL}"
            )

            plantas_claro = consultar_claro_monitoreado(
                VINA_ID_ACTUAL,
                cuartel_galeria
            )

            if plantas_claro:

                st.caption(
                    f"Claro monitoreado · {len(plantas_claro)} plantas configuradas"
                )

                opciones_plantas = {
                    planta[1]: (
                        f"Posición {planta[0]} · "
                        f"{planta[2]}"
                    )
                    for planta in plantas_claro
                }

                planta_seleccionada = st.selectbox(
                    "Planta del claro",
                    list(opciones_plantas),
                    format_func=lambda identificador:
                        opciones_plantas[identificador],
                    key=(
                        f"df29_planta_"
                        f"{VINA_ID_ACTUAL}_{cuartel_galeria}"
                    )
                )

                imagenes = [
                    imagen
                    for imagen in imagenes
                    if imagen[6] == planta_seleccionada
                ]

                st.markdown(
                    f"#### 🌱 {opciones_plantas[planta_seleccionada]}"
                )

                st.caption(
                    f"Cuartel {cuartel_galeria} · "
                    f"{len(imagenes)} fotografía(s) de esta planta"
                )

                if not imagenes:
                    st.info(
                        "Esta planta del claro todavía no tiene "
                        "fotografías registradas. Puedes consultar "
                        "las imágenes históricas de la viña desde "
                        "'Todas las fotografías'."
                    )

            else:

                st.info(
                    "Este cuartel todavía no tiene un claro "
                    "monitoreado configurado."
                )
                imagenes = []

        else:

            st.info(
                "Esta viña todavía no tiene cuarteles registrados."
            )
            imagenes = []

    if modo_galeria == "Todas las fotografías" and imagenes:

        col_cuartel, col_planta, col_fecha = st.columns(3)

        cuarteles = sorted({
            str(imagen[7])
            for imagen in imagenes
            if imagen[7] is not None
        })

        with col_cuartel:

            filtro_cuartel = st.selectbox(
                "Cuartel",
                ["Todos"] + cuarteles,
                key=f"galeria_filtro_cuartel_{VINA_ID_ACTUAL}"
            )

        if filtro_cuartel != "Todos":

            imagenes = [
                imagen for imagen in imagenes
                if str(imagen[7]) == filtro_cuartel
            ]

        plantas = sorted({
            str(imagen[6])
            for imagen in imagenes
            if imagen[6] is not None
        })

        with col_planta:

            filtro_planta = st.selectbox(
                "Planta",
                ["Todas"] + plantas,
                key=f"galeria_filtro_planta_{VINA_ID_ACTUAL}"
            )

        if filtro_planta != "Todas":

            imagenes = [
                imagen for imagen in imagenes
                if str(imagen[6]) == filtro_planta
            ]

        fechas_galeria = sorted({
            str(imagen[5])[:10]
            for imagen in imagenes
            if imagen[5] is not None
        }, reverse=True)

        with col_fecha:

            filtro_fecha = st.selectbox(
                "Fecha",
                ["Todas"] + fechas_galeria,
                key=f"galeria_filtro_fecha_{VINA_ID_ACTUAL}"
            )

        if filtro_fecha != "Todas":

            imagenes = [
                imagen for imagen in imagenes
                if str(imagen[5])[:10] == filtro_fecha
            ]

    if not imagenes:

        if modo_galeria == "Todas las fotografías":
            st.info(
                "No hay fotografías disponibles para esta consulta. "
                "Puedes cambiar los filtros o agregar fotografías "
                "desde la ficha de una planta en Monitoreo."
            )

    else:

        st.write(
            f"**{len(imagenes)} fotografías registradas**"
        )

        columnas = st.columns(3)

        for i, imagen in enumerate(imagenes):

            (
                image_id,
                ruta_archivo,
                tipo,
                fecha_subida,
                measurement_id,
                fecha_hora,
                plant_id,
                cuartel,
                variedad,
                fila,
                numero_planta
            ) = imagen

            with columnas[i % 3]:

                titulo_foto = (
                    f"Cuartel {cuartel or 'Sin información'} · "
                    f"Fila {fila if fila is not None else '-'} · "
                    f"Planta {numero_planta if numero_planta is not None else '-'}"
                )

                with st.container(border=True):

                    ruta = obtener_ruta_fotografia_segura(ruta_archivo)

                    st.markdown(f"**{titulo_foto}**")
                    st.caption(variedad or "Variedad sin información")
                    st.caption(f"Fecha: {fecha_hora}")

                    from PIL import Image, ImageOps

                    fondo = Image.new("RGB", (480, 270), "#F0EDF3")

                    if ruta is not None:
                        try:
                            with Image.open(ruta) as original:
                                miniatura = ImageOps.contain(
                                    original.convert("RGB"),
                                    (480, 270)
                                )

                            fondo.paste(
                                miniatura,
                                (
                                    (480-miniatura.width)//2,
                                    (270-miniatura.height)//2
                                )
                            )

                        except Exception:
                            pass

                    st.image(fondo, width="stretch")

                    @st.dialog(
                        "Fotografía y análisis IA",
                        width="large",
                        dismissible=True
                    )
                    def abrir_fotografia_galeria(
                        image_id, ruta_archivo, titulo_foto,
                        variedad, fecha_hora
                    ):

                        if st.button(
                            "Cerrar ventana",
                            key=f"cerrar_galeria_{image_id}"
                        ):
                            st.rerun()

                        ruta = obtener_ruta_fotografia_segura(ruta_archivo)

                        st.markdown(f"**{titulo_foto}**")

                        st.caption(
                            variedad or "Variedad sin información"
                        )

                        st.caption(f"Fecha: {fecha_hora}")

                        from database import (
                            consultar_ambiente_fotografia
                        )

                        try:

                            ambiente_foto = consultar_ambiente_fotografia(
                                image_id,
                                VINA_ID_ACTUAL,
                                usuario_actual["usuario_id"]
                            )

                        except PermissionError:

                            ambiente_foto = None
                            st.warning("Datos ambientales no autorizados.")

                        if ambiente_foto is not None:
                            with st.expander("Condiciones ambientales"):



                                temperatura_foto = ambiente_foto[
                                    "temperatura_ambiental"
                                ]

                                humedad_foto = ambiente_foto[
                                    "humedad_ambiental"
                                ]

                                c_temp, c_hum = st.columns(2)

                                c_temp.metric(
                                    "Temperatura",
                                    f"{temperatura_foto:.1f} °C".replace(".", ",")
                                    if temperatura_foto is not None else "—"
                                )

                                c_hum.metric(
                                    "Humedad relativa",
                                    f"{humedad_foto:.1f} %".replace(".", ",")
                                    if humedad_foto is not None else "—"
                                )

                                st.caption(
                                    "Fuente: dispositivo "
                                    + ambiente_foto["device_id"]
                                )

                        if ruta is not None:

                            st.image(str(ruta), width=500)

                            mostrar_editor_fenologia(
                                ruta, image_id, VINA_ID_ACTUAL, "galeria"
                            )

                            historial = consultar_analisis_por_imagen(
                                image_id,
                                VINA_ID_ACTUAL
                            )

                            if historial:

                                with st.expander(
                                    "Resultados e historial de IA"
                                ):

                                    for registro in historial:

                                        (
                                            analisis_id,
                                            imagen_id,
                                            modelo,
                                            version,
                                            cantidad_racimos,
                                            verde,
                                            envero,
                                            morado,
                                            etapa,
                                            confianza,
                                            resultado_json,
                                            fecha_analisis
                                        ) = registro

                                        st.caption(
                                            f"Análisis del {fecha_analisis}"
                                        )

                                        st.write(
                                            f"**Modelo:** {modelo} · Versión: {version}"
                                        )

                                        if resultado_json:

                                            datos_analisis = json.loads(
                                                resultado_json
                                            )

                                            if modelo == "FenologIA - SAM 2":
                                                mostrar_resultados_fenologia(datos_analisis, f"historial_galeria_{image_id}_{analisis_id}")

                                            elif modelo == "Roboflow":

                                                st.metric(
                                                    "Detecciones de uvas",
                                                    datos_analisis.get(
                                                        "cantidad_detecciones", 0
                                                    )
                                                )

                                                confianzas = datos_analisis.get(
                                                    "confianzas", []
                                                )

                                                if confianzas:
                                                    st.caption(
                                                        f"Confianza máxima: {max(confianzas):.2f}%"
                                                    )
                                                else:
                                                    st.info(
                                                        "No se encontraron detecciones "
                                                        "sobre el umbral configurado."
                                                    )

                                                ruta_diagnostico = datos_analisis.get(
                                                    "imagen_resultado"
                                                )

                                                ruta_diagnostico = (
                                                    obtener_ruta_resultado_ia_segura(
                                                        ruta_diagnostico,
                                                        "roboflow"
                                                    )
                                                )

                                                if ruta_diagnostico is not None:
                                                    st.image(
                                                        str(ruta_diagnostico),
                                                        caption="Detecciones de Roboflow",
                                                        width="stretch"
                                                    )

                                                st.caption(
                                                    datos_analisis.get(
                                                        "advertencia", ""
                                                    )
                                                )

                                            elif modelo == "Segmentación HSV experimental":

                                                st.write(
                                                    f"Zonas verdes: "
                                                    f"{datos_analisis.get('porcentaje_verde', 0)}%"
                                                )

                                                st.write(
                                                    f"Zonas oscuras: "
                                                    f"{datos_analisis.get('porcentaje_zonas_oscuras', 0)}%"
                                                )

                                            with st.expander(
                                                "Ver detalles técnicos"
                                            ):
                                                st.json(datos_analisis)

                                        st.divider()

                        else:

                            st.warning(
                                f"No se encontró el archivo: {ruta_archivo}"
                            )


                    if st.button(
                        "Ver fotografía y análisis",
        type="primary",
        icon=":material/open_in_new:",
                        key=f"abrir_galeria_{image_id}",
                        width="stretch"
                    ):
                        abrir_fotografia_galeria(
                            image_id, ruta_archivo, titulo_foto,
                            variedad, fecha_hora
                        )
