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

from analizador import analizar_uvas_roboflow

from autenticacion import verificar_usuario, crear_usuario, registrar_vina_administrador, consultar_usuario_activo

inicializar_bd()

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


def seleccionar_estacion_con_historial(vina_id):
    """
    Identifica por separado:
    - La estación geográficamente más cercana.
    - La estación más cercana que cumple criterios mínimos
      de disponibilidad para análisis meteorológico.

    No modifica la base de datos.
    """

    try:
        estaciones = consultar_estaciones_cercanas(vina_id)
    except ValueError as error:
        if "coordenadas" in str(error).lower():
            return None
        raise

    if not estaciones:
        return None

    variables = [
        "temperatura_min",
        "temperatura_max",
        "humedad_relativa",
        "precipitacion",
        "radiacion_solar",
        "velocidad_viento"
    ]

    minimo_dias = 30
    minimo_variables = 3
    cobertura_minima = 80.0
    radio_maximo_km = 30.0

    with conectar() as conexion:
        resumenes = conexion.execute("""
            SELECT estacion_id, COUNT(*)
            FROM mediciones_meteorologicas
            GROUP BY estacion_id
        """).fetchall()

    resumen_por_estacion = {
        fila[0]: fila[1]
        for fila in resumenes
    }

    estacion_seleccionada = None
    registros_seleccionados = []
    fecha_ultima_seleccionada = None
    dias_desde_seleccionada = None
    cobertura_seleccionada = {}
    diagnostico = []

    hoy = pd.Timestamp.now().normalize()

    # Las estaciones se revisan desde la más cercana.
    for indice, estacion in enumerate(estaciones):

        estacion_id = estacion["estacion_id"]
        cantidad = resumen_por_estacion.get(estacion_id, 0)

        estado = "No apta para análisis"
        motivo = ""
        dias_distintos = 0
        cobertura = {}

        if cantidad == 0:
            motivo = "Sin historial meteorológico general."

        else:
            registros = consultar_mediciones_meteorologicas(
                estacion_id
            )

            if not registros:
                motivo = "No fue posible recuperar sus registros."

            else:
                df = pd.DataFrame(registros)

                df["fecha"] = pd.to_datetime(
                    df["fecha"],
                    errors="coerce"
                )

                df = df.dropna(subset=["fecha"])
                df = df.sort_values("fecha")

                # Se considera un solo registro por día.
                df["dia"] = df["fecha"].dt.normalize()
                df = df.drop_duplicates(
                    subset=["dia"],
                    keep="last"
                )

                dias_distintos = len(df)

                if dias_distintos == 0:
                    motivo = "No contiene fechas válidas."

                else:
                    for variable in variables:
                        valores = pd.to_numeric(
                            df[variable],
                            errors="coerce"
                        )

                        porcentaje = (
                            valores.notna().sum()
                            / dias_distintos
                        ) * 100

                        cobertura[variable] = round(
                            porcentaje, 1
                        )

                    variables_suficientes = [
                        variable
                        for variable, porcentaje
                        in cobertura.items()
                        if porcentaje >= cobertura_minima
                    ]

                    if dias_distintos < minimo_dias:
                        motivo = (
                            f"Historial insuficiente: "
                            f"{dias_distintos} días; "
                            f"se requieren al menos {minimo_dias}."
                        )

                    elif len(variables_suficientes) < minimo_variables:
                        motivo = (
                            f"Cobertura insuficiente: solo "
                            f"{len(variables_suficientes)} variables "
                            f"alcanzan el {cobertura_minima:.0f}%."
                        )

                    else:
                        if estacion["distancia_km"] > radio_maximo_km:
                            estado = "Fuera del radio de análisis"
                            motivo = (
                                f"Tiene historial suficiente, pero está a "
                                f"{estacion['distancia_km']:.2f} km. "
                                f"El radio máximo configurado es "
                                f"{radio_maximo_km:.0f} km."
                            )
                        else:
                            estado = "Apta para análisis"
                            motivo = (
                                "Cumple los criterios mínimos de "
                                "disponibilidad, cobertura y distancia."
                            )

                        if (
                            estacion_seleccionada is None
                            and estacion['distancia_km'] <= radio_maximo_km
                        ):
                            estacion_seleccionada = estacion
                            registros_seleccionados = (
                                df.drop(columns=["dia"])
                                .to_dict("records")
                            )
                            fecha_ultima_seleccionada = (
                                df["fecha"].max()
                            )
                            dias_desde_seleccionada = (
                                hoy
                                - fecha_ultima_seleccionada.normalize()
                            ).days
                            cobertura_seleccionada = cobertura

        # Conservamos el diagnóstico de las cinco estaciones
        # geográficamente más cercanas.
        if indice < 5:
            diagnostico.append({
                "estacion": estacion,
                "estado": estado,
                "motivo": motivo,
                "dias_distintos": dias_distintos,
                "cobertura": cobertura
            })

    estacion_mas_cercana = estaciones[0]

    return {
        "estacion": estacion_seleccionada,
        "registros": registros_seleccionados,
        "fecha_ultimo_registro": fecha_ultima_seleccionada,
        "dias_desde_ultimo": dias_desde_seleccionada,
        "es_referencia": (
            estacion_seleccionada is not None
            and estacion_seleccionada["estacion_id"]
            != estacion_mas_cercana["estacion_id"]
        ),
        "estacion_mas_cercana": estacion_mas_cercana,
        "diagnostico_estaciones": diagnostico,
        "cobertura_variables": cobertura_seleccionada,
        "criterios_calidad": {
            "minimo_dias": minimo_dias,
            "minimo_variables": minimo_variables,
            "cobertura_minima": cobertura_minima,
            "radio_maximo_km": radio_maximo_km
        }
    }


# =====================================================================
# 3. INTERFAZ
# =====================================================================
st.set_page_config(page_title=f"{NOMBRE_VINA} · Monitoreo vitícola", layout="wide")


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
        max-width: 650px;
        padding-top: 7vh;
        padding-bottom: 3rem;
    }

    .fenologia-logo {
        text-align: center;
        font-size: clamp(3rem, 7vw, 5rem);
        font-weight: 750;
        letter-spacing: -2px;
        margin-bottom: 2rem;
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
    </style>
    """, unsafe_allow_html=True)

    st.markdown(
        '<div class="fenologia-logo">Fenolog<span>IA</span></div>',
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
    "Resumen y diagnóstico inteligente",
    "Mapa y monitoreo de plantas",
    "Meteorología y precipitaciones",
    "Fotografías y análisis IA",
    "Configuración de mi viña",
]

# DM.16: compactar espacio de navegación
st.markdown("""
<style>
/* Contenedor de la navegación */
div.st-key-dm16_navegacion {
    margin-bottom: 0 !important;
    padding-bottom: 0 !important;
}

/* Reducir espacios internos de las columnas */
div.st-key-dm16_navegacion
[data-testid="stHorizontalBlock"] {
    margin-bottom: 0 !important;
    padding-bottom: 0 !important;
}

/* Mantener los botones completos */
div.st-key-dm16_navegacion button {
    border-radius: 10px !important;
    overflow: visible !important;
}
</style>
""", unsafe_allow_html=True)

# DM.12: navegación compacta y pestaña activa sólida
st.markdown("""
<style>
/* Reducir el espacio superior general */
.block-container {
    padding-top: 0.5rem !important;
}

/* Botones de navegación */
div[class*="st-key-nav_superior_"] button {
    min-height: 2.15rem !important;
    height: 2.15rem !important;
    border-radius: 10px !important;
    box-shadow: none !important;
}

/* Reducir el espacio vertical del separador */
div[data-testid="stDivider"] {
    margin-top: 0 !important;
    margin-bottom: 0.25rem !important;
}
</style>
""", unsafe_allow_html=True)

# Navegación superior de FenologIA

SECCIONES = ["FenologIA"] + SECCIONES

if "navegacion_principal" not in st.session_state:
    st.session_state["navegacion_principal"] = "FenologIA"

indice_activo = next(
    (
        i for i, (seccion, _) in enumerate([
            ("FenologIA", "FenologIA"),
            ("Resumen y diagnóstico inteligente", ""),
            ("Mapa y monitoreo de plantas", ""),
            ("Meteorología y precipitaciones", ""),
            ("Fotografías y análisis IA", ""),
        ])
        if st.session_state["navegacion_principal"] == seccion
    ),
    -1
)

st.markdown(f"""
<style>
/* Botones de la barra de navegación */
div[data-testid="stButton"] button[kind="secondary"] {{
    border: none;
    border-radius: 9px;
    background: transparent;
    color: #222222;
}}

div[data-testid="stButton"] button[kind="secondary"]:hover {{
    background-color: #EDF5E8;
    color: #222222;
}}


/* Estado activo de la navegación de FenologIA */

div.st-key-nav_superior_0
button[kind="secondary"] {{
    background-color: transparent;
    border: none;
    color: #222222;
}}

div.st-key-nav_superior_1
button[kind="secondary"] {{
    background-color: transparent;
    border: none;
    color: #222222;
}}

div.st-key-nav_superior_2
button[kind="secondary"] {{
    background-color: transparent;
    border: none;
    color: #222222;
}}

div.st-key-nav_superior_3
button[kind="secondary"] {{
    background-color: transparent;
    border: none;
    color: #222222;
}}

div.st-key-nav_superior_4
button[kind="secondary"] {{
    background-color: transparent;
    border: none;
    color: #222222;
}}

/* Pestaña activa: rectángulo verde completo */

div.st-key-nav_superior_{indice_activo} button[kind="secondary"] {{
    background: #84C55D !important;
    background-color: #84C55D !important;
    border: 1px solid #84C55D !important;
    border-radius: 10px !important;
    color: #17210F !important;
    font-weight: 650;
}}

/* El botón de usuario se destaca cuando Configuración está activa */
/* Botones principales morados */
div[data-testid="stButton"] button[kind="primary"] {{
    background-color: #322345;
    border-color: #322345;
    color: white;
    border-radius: 10px;
}}

div[data-testid="stButton"] button[kind="primary"]:hover {{
    background-color: #49345F;
    border-color: #49345F;
    color: white;
}}
</style>
""", unsafe_allow_html=True)

opciones_superiores = [
    ("FenologIA", "FenologIA"),
    ("Resumen y diagnóstico inteligente", "Resumen y diagnóstico"),
    ("Mapa y monitoreo de plantas", "Mapa y monitoreo"),
    ("Meteorología y precipitaciones", "Meteorología y precipitaciones"),
    ("Fotografías y análisis IA", "Fotografías y análisis"),
]

# DM.16: navegación en contenedor identificable
contenedor_nav = st.container(key="dm16_navegacion")

with contenedor_nav:
    columnas_nav = st.columns(
        [1.2, 1.8, 1.5, 2.2, 1.7, 0.55],
        gap="small"
    )

for indice, (seccion, etiqueta) in enumerate(opciones_superiores):

    with columnas_nav[indice]:

        activa = (
            st.session_state["navegacion_principal"] == seccion
        )

        if st.button(
            etiqueta,
            key=f"nav_superior_{indice}",
            use_container_width=True,
            type="secondary"
        ):
            st.session_state["navegacion_principal"] = seccion
            st.rerun()

with columnas_nav[-1]:
    if st.button(
        "👤",
        key="nav_configuracion",
        use_container_width=True,
        help="Configuración de mi viña"
    ):
        st.session_state["navegacion_principal"] = (
            "Configuración de mi viña"
        )
        st.rerun()

seccion_actual = st.session_state["navegacion_principal"]

if seccion_actual == "Configuración de mi viña":
    st.markdown("""
    <style>
    div.st-key-nav_configuracion button {
        background-color: #84C55D !important;
        border-color: #84C55D !important;
        color: #17210F !important;
    }
    </style>
    """, unsafe_allow_html=True)



# DM.7: ocultar visualmente la barra lateral
st.markdown("""
<style>
    [data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }

    [data-testid="stAppViewContainer"] > .main {
        margin-left: 0 !important;
    }

    .block-container {
        max-width: 100% !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stDivider"]) {
    margin-top: 0 !important;
}
</style>
""", unsafe_allow_html=True)

# DM.18: separador compacto bajo la navegación
st.markdown("""
<style>
div.st-key-dm16_navegacion {
    margin-bottom: 0 !important;
}

div.st-key-dm18_separador {
    margin-top: -2.5rem !important;
    margin-bottom: 0 !important;
}
</style>
""", unsafe_allow_html=True)

with st.container(key="dm18_separador"):
    st.markdown(
        '<div style="border-top:1px solid #E0E0E0; width:100%;"></div>',
        unsafe_allow_html=True
    )

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
    st.markdown("""
    <style>
    [data-testid="stSidebar"] {
        display: none;
    }
    </style>
    """, unsafe_allow_html=True)

    st.write("")
    st.write("")

    st.markdown(
        f"<h1 style='text-align:center; color:#000000;'>"
        f"Viña «{__import__('html').escape(str(NOMBRE_VINA))}»"
        f"</h1>",
        unsafe_allow_html=True
    )

    izquierda, centro, derecha = st.columns([1, 1, 1])

    with centro:
        if st.button(
            "🍇 Ir a diagnóstico",
            key="boton_ir_diagnostico",
            use_container_width=True,
            type="primary"
        ):
            st.session_state["navegacion_principal"] = (
                "Resumen y diagnóstico inteligente"
            )
            st.rerun()

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

    # DM.30: estructura inicial de Mi perfil
    panel_plantillas, panel_perfil = st.columns(
        [0.7, 3.3],
        gap="medium"
    )

    with panel_plantillas:
        st.markdown("### Plantillas de archivos")

        st.caption(
            "Aquí estarán disponibles las plantillas "
            "para importar datos a FenologIA."
        )

        # DM.38: plantillas estructurales descargables
        plantilla_individual = Path(
            "plantillas_prueba/plantilla_registro_individual.csv"
        )
        plantilla_automatica = Path(
            "plantillas_prueba/plantilla_generacion_automatica.csv"
        )

        st.markdown("**Registro individual de plantas**")
        st.caption("CSV para registrar plantas específicas.")

        if plantilla_individual.is_file():
            st.download_button(
                "Descargar CSV individual",
                icon=":material/download:",
                data=plantilla_individual.read_bytes(),
                file_name="plantilla_registro_individual.csv",
                mime="text/csv",
                key="dm38_descargar_individual",
                use_container_width=True
            )
        else:
            st.warning("Plantilla individual no disponible.")

        st.markdown("**Generación automática de plantas**")
        st.caption("CSV para registrar cuarteles y filas.")

        if plantilla_automatica.is_file():
            st.download_button(
                "Descargar CSV automático",
                icon=":material/download:",
                data=plantilla_automatica.read_bytes(),
                file_name="plantilla_generacion_automatica.csv",
                mime="text/csv",
                key="dm38_descargar_automatica",
                use_container_width=True
            )
        else:
            st.warning("Plantilla automática no disponible.")

        st.markdown("**Mediciones fenológicas**")
        st.caption(
            "XLSX para registrar las cinco variables "
            "de monitoreo por planta y fecha."
        )

        plantilla_fenologia = Path(
            "plantillas/FenologIA_Plantilla_Mediciones.xlsx"
        )

        if plantilla_fenologia.is_file():
            st.download_button(
                "Descargar XLSX fenologia",
                icon=":material/download:",
                data=plantilla_fenologia.read_bytes(),
                file_name="FenologIA_Plantilla_Mediciones.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                key="dm42_descargar_xlsx_fenologia",
                use_container_width=True
            )
        else:
            st.warning(
                "Plantilla de mediciones no disponible."
            )

    with panel_perfil:
        if usuario_actual["rol"] == "administrador":
            with st.expander("👥 Administrar usuarios"):

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

    # Los apartados actuales permanecen temporalmente
    # en su posición original hasta validar el diseño.


    # =========================================================
    # DF.2.8.3: CONFIGURACIÓN DEL CLARO MONITOREADO
    # =========================================================

    with panel_perfil:

        st.divider()

        with st.expander(
            "🌱 Configuración del claro monitoreado",
            expanded=False
        ):

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

    with panel_perfil:
        # =========================================================
        # UBICACIÓN GEOGRÁFICA DE LA VIÑA
        # =========================================================

        vina_actual = consultar_vina(VINA_ID_ACTUAL)

        if vina_actual is not None:

            nombre_vina_actual = vina_actual[1]
            ubicacion_guardada = vina_actual[2]
            latitud_guardada = vina_actual[3]
            longitud_guardada = vina_actual[4]

            # Determinar si la ubicación ya fue registrada
            ubicacion_configurada = (
                latitud_guardada is not None
                and longitud_guardada is not None
            )

            clave_lat = f"ubicacion_lat_{VINA_ID_ACTUAL}"
            clave_lon = f"ubicacion_lon_{VINA_ID_ACTUAL}"
            clave_nombre = f"ubicacion_nombre_{VINA_ID_ACTUAL}"

            # Inicializar coordenadas solo una vez por viña
            if clave_lat not in st.session_state:
                st.session_state[clave_lat] = latitud_guardada

            if clave_lon not in st.session_state:
                st.session_state[clave_lon] = longitud_guardada

            if clave_nombre not in st.session_state:
                st.session_state[clave_nombre] = (
                    ubicacion_guardada or "Por definir"
                )

            st.header("Ubicación de mi viña")
            st.caption(
                f"Configuración geográfica de {nombre_vina_actual}"
            )

            es_admin = usuario_actual["rol"] == "administrador"

            # Solo permitir configurar si todavía no existe ubicación
            puede_configurar = es_admin and not ubicacion_configurada

            if puede_configurar:

                with st.form("buscar_ubicacion_vina"):
                    consulta_lugar = st.text_input(
                        "Busca la localidad o dirección de tu viña",
                        placeholder="Ej: Santa Cruz, Región de O'Higgins, Chile"
                    )

                    buscar = st.form_submit_button("Buscar ubicación")

                if buscar:
                    if not consulta_lugar.strip():
                        st.warning("Escribe una localidad o dirección.")
                    else:
                        try:
                            geolocalizador = Nominatim(
                                user_agent="plataforma_monitoreo_viticola",
                                ssl_context=ssl.create_default_context(
                                    cafile=certifi.where()
                                )
                            )

                            resultado = geolocalizador.geocode(
                                consulta_lugar,
                                timeout=10,
                                country_codes="cl"
                            )

                            if resultado:
                                st.session_state[clave_lat] = float(
                                    resultado.latitude
                                )
                                st.session_state[clave_lon] = float(
                                    resultado.longitude
                                )
                                st.session_state[clave_nombre] = (
                                    resultado.address
                                )
                                st.rerun()
                            else:
                                st.warning(
                                    "No encontramos ese lugar. "
                                    "Prueba con otra dirección o localidad."
                                )

                        except Exception as e:
                            st.error(
                                f"No se pudo buscar la ubicación: {e}"
                            )

            lat_actual = st.session_state[clave_lat]
            lon_actual = st.session_state[clave_lon]

            if lat_actual is not None and lon_actual is not None:
                centro_mapa = [lat_actual, lon_actual]
                zoom_mapa = 15
            else:
                centro_mapa = [-35.7, -71.5]
                zoom_mapa = 5

            mapa_ubicacion = folium.Map(
                location=centro_mapa,
                zoom_start=zoom_mapa,
                control_scale=True
            )

            if lat_actual is not None and lon_actual is not None:
                folium.Marker(
                    [lat_actual, lon_actual],
                    tooltip="Ubicación de la viña",
                    popup=st.session_state[clave_nombre],
                    icon=folium.Icon(color="green", icon="leaf")
                ).add_to(mapa_ubicacion)

            if puede_configurar:
                st.caption(
                    "Haz clic sobre el mapa para marcar la ubicación "
                    "exacta del predio."
                )
            elif ubicacion_configurada:
                st.caption(
                    "Ubicación definitiva registrada. "
                    "El mapa está disponible solo para consulta."
                )
            else:
                st.caption(
                    "El administrador todavía no ha definido "
                    "la ubicación de esta viña."
                )

            resultado_mapa = st_folium(
                mapa_ubicacion,
                width=900,
                height=450,
                returned_objects=(
                    ["last_clicked"] if puede_configurar else []
                ),
                key=f"mapa_ubicacion_{VINA_ID_ACTUAL}"
            )

            if puede_configurar and resultado_mapa:
                clic = resultado_mapa.get("last_clicked")

                if clic:
                    nueva_lat = round(float(clic["lat"]), 7)
                    nueva_lon = round(float(clic["lng"]), 7)

                    clic_anterior = st.session_state.get(
                        f"ultimo_clic_{VINA_ID_ACTUAL}"
                    )

                    nuevo_clic = (nueva_lat, nueva_lon)

                    if nuevo_clic != clic_anterior:
                        st.session_state[f"ultimo_clic_{VINA_ID_ACTUAL}"] = nuevo_clic

                        st.session_state[clave_lat] = nueva_lat
                        st.session_state[clave_lon] = nueva_lon
                        st.session_state[clave_nombre] = (
                            "Ubicación seleccionada en el mapa"
                        )

                        st.rerun()

            if lat_actual is not None and lon_actual is not None:
                st.write(f"**Ubicación:** {st.session_state[clave_nombre]}")
                st.write(f"**Latitud:** {lat_actual:.6f}")
                st.write(f"**Longitud:** {lon_actual:.6f}")

            if puede_configurar:

                if st.button(
                    "Guardar ubicación",
                    key=f"guardar_ubicacion_{VINA_ID_ACTUAL}_{round(lat_actual or 0, 5)}_{round(lon_actual or 0, 5)}"
                ):
                    try:
                        actualizar_ubicacion_vina(
                            VINA_ID_ACTUAL,
                            st.session_state[clave_nombre],
                            st.session_state[clave_lat],
                            st.session_state[clave_lon]
                        )

                        st.success(
                            "¡Ubicación de la viña guardada correctamente!"
                        )
                        st.rerun()

                    except Exception as e:
                        st.error(
                            f"No se pudo guardar la ubicación: {e}"
                        )

        # =========================================================

        # =========================================================
        # ESTACIÓN METEOROLÓGICA RECOMENDADA
        # =========================================================

        st.divider()
        st.subheader("Estación meteorológica asociada")

        if latitud_guardada is not None and longitud_guardada is not None:

            try:
                estaciones_cercanas = consultar_estaciones_cercanas(
                    VINA_ID_ACTUAL
                )

                if estaciones_cercanas:
                    estacion_recomendada = estaciones_cercanas[0]

                    st.success("Estación más cercana encontrada")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.metric(
                            "Estación",
                            estacion_recomendada["nombre"]
                        )

                        st.write(
                            "**Institución:**",
                            estacion_recomendada["institucion"]
                        )

                    with col2:
                        st.metric(
                            "Distancia a la viña",
                            f'{estacion_recomendada["distancia_km"]} km'
                        )

                        st.write(
                            "**Fuente:**",
                            estacion_recomendada["fuente_datos"]
                        )

                    st.caption(
                        "Estación recomendada según distancia geográfica. "
                        "La selección definitiva requiere validar su "
                        "actividad y disponibilidad de datos."
                    )

                else:
                    st.warning(
                        "No hay estaciones meteorológicas registradas "
                        "para esta ubicación."
                    )

            except Exception as e:
                st.warning(
                    f"No se pudo consultar las estaciones: {e}"
                )

        else:
            st.info(
                "Registra la ubicación de tu viña para buscar "
                "automáticamente las estaciones meteorológicas cercanas."
            )

    # =========================================================


# =========================================================
# PANEL DE INFORMACIÓN METEOROLÓGICA
# =========================================================

if seccion_actual == "Meteorología y precipitaciones":

    st.divider()
    st.header("Monitoreo meteorológico")

    if latitud_guardada is not None and longitud_guardada is not None:

        try:
            seleccion_meteo = seleccionar_estacion_con_historial(
                VINA_ID_ACTUAL
            )

            if seleccion_meteo:

                estacion_datos = seleccion_meteo["estacion"]
                datos_meteo = seleccion_meteo["registros"]
                datos_referencia = seleccion_meteo["es_referencia"]
                estacion_principal = seleccion_meteo["estacion_mas_cercana"]

                if datos_meteo:

                    col_cercana, col_historial = st.columns(2)

                    with col_cercana:
                        with st.container(border=True):
                            st.caption("ESTACIÓN MÁS CERCANA")
                            st.write(
                                f"**{estacion_principal['nombre']}**"
                            )
                            st.caption(
                                f"Distancia a la viña: "
                                f"{estacion_principal['distancia_km']} km"
                            )

                    with col_historial:
                        with st.container(border=True):
                            st.caption("ESTACIÓN PARA ANÁLISIS HISTÓRICO")
                            st.write(
                                f"**{estacion_datos['nombre']}**"
                            )
                            st.caption(
                                f"Distancia a la viña: "
                                f"{estacion_datos['distancia_km']} km"
                            )

                    df_meteo = pd.DataFrame(datos_meteo)
                    df_meteo["fecha"] = pd.to_datetime(
                        df_meteo["fecha"]
                    )
                    df_meteo = df_meteo.sort_values("fecha")

                    fecha_ultimo_registro = seleccion_meteo[
                        "fecha_ultimo_registro"
                    ]
                    dias_desde_ultimo = seleccion_meteo[
                        "dias_desde_ultimo"
                    ]

                    st.caption(
                        f"Último registro meteorológico: "
                        f"{fecha_ultimo_registro.date()} · "
                        f"Antigüedad: {dias_desde_ultimo} días"
                    )

                    if dias_desde_ultimo > 7:
                        st.warning(
                            "Los registros meteorológicos disponibles "
                            "están desactualizados. Se muestran como "
                            "referencia histórica y no representan "
                            "condiciones actuales."
                        )
                    elif dias_desde_ultimo < 0:
                        st.warning(
                            "La fecha del último registro es posterior "
                            "a la fecha actual. Conviene revisar la fuente."
                        )

                    if datos_referencia:
                        st.warning(
                            f"No hay registros históricos de "
                            f"{estacion_principal['nombre']}. "
                            f"Se muestran datos de referencia de "
                            f"{estacion_datos['nombre']}, a "
                            f"{estacion_datos['distancia_km']} km. "
                            "No representan mediciones directas de la viña."
                        )
                    else:
                        st.success(
                            "Historial meteorológico de la estación principal."
                        )

                    st.caption(
                        f"Fuente: {df_meteo.iloc[0]['fuente_datos']} · "
                        f"Período: "
                        f"{df_meteo['fecha'].min().date()} al "
                        f"{df_meteo['fecha'].max().date()} · "
                        f"{len(df_meteo)} registros"
                    )

                    col1, col2 = st.columns(2)

                    with col1:
                        fig_temp = px.line(
                            df_meteo,
                            x="fecha",
                            y=["temperatura_min", "temperatura_max"],
                            title="Temperaturas mínimas y máximas (°C)",
                            labels={
                                "fecha": "Fecha",
                                "value": "Temperatura (°C)",
                                "variable": "Medición"
                            }
                        )
                        st.plotly_chart(
                            fig_temp,
                            width="stretch"
                        )

                    with col2:
                        fig_hum = px.line(
                            df_meteo,
                            x="fecha",
                            y="humedad_relativa",
                            title="Humedad relativa (%)",
                            labels={
                                "fecha": "Fecha",
                                "humedad_relativa": "Humedad (%)"
                            }
                        )
                        st.plotly_chart(
                            fig_hum,
                            width="stretch"
                        )

                    col3, col4 = st.columns(2)

                    with col3:
                        fig_prec = px.bar(
                            df_meteo,
                            x="fecha",
                            y="precipitacion",
                            title="Precipitaciones (mm)",
                            labels={
                                "fecha": "Fecha",
                                "precipitacion": "Precipitación (mm)"
                            }
                        )
                        st.plotly_chart(
                            fig_prec,
                            width="stretch"
                        )

                    with col4:
                        fig_viento = px.line(
                            df_meteo,
                            x="fecha",
                            y="velocidad_viento",
                            title="Velocidad del viento (km/h)",
                            labels={
                                "fecha": "Fecha",
                                "velocidad_viento": "Velocidad (km/h)"
                            }
                        )
                        st.plotly_chart(
                            fig_viento,
                            width="stretch"
                        )

                    fig_rad = px.line(
                        df_meteo,
                        x="fecha",
                        y="radiacion_solar",
                        title="Radiación solar (MJ/m²)",
                        labels={
                            "fecha": "Fecha",
                            "radiacion_solar": "Radiación (MJ/m²)"
                        }
                    )
                    st.plotly_chart(
                        fig_rad,
                        width="stretch"
                    )

                else:
                    st.info(
                        "No hay una estación cercana que cumpla los "
                        "criterios mínimos para análisis meteorológico."
                    )

                    if estacion_principal:
                        st.write(
                            f"**Estación geográficamente más cercana:** "
                            f"{estacion_principal['nombre']} · "
                            f"{estacion_principal['distancia_km']} km"
                        )

                    for item in seleccion_meteo["diagnostico_estaciones"]:
                        st.caption(
                            f"{item['estacion']['nombre']}: "
                            f"{item['estado']} — {item['motivo']}"
                        )

            else:
                st.info(
                    "No se encontraron estaciones cercanas con "
                    "historial meteorológico general disponible."
                )

        except Exception as e:
            st.error(
                f"No se pudo cargar el panel meteorológico: {e}"
            )

    else:
        st.info(
            "Registra la ubicación de tu viña para consultar "
            "la información meteorológica."
        )

# =========================================================

# =========================================================
# PRECIPITACIÓN DMC
# =========================================================

if seccion_actual == "Meteorología y precipitaciones":

    st.divider()
    st.header("Precipitación - Dirección Meteorológica de Chile")

    if latitud_guardada is not None and longitud_guardada is not None:

        try:
            estaciones_dmc = consultar_estaciones_cercanas(
                VINA_ID_ACTUAL
            )

            estacion_dmc = None
            acumulados_dmc = []

            # Buscar la estación DMC más cercana con informes guardados.
            for estacion in estaciones_dmc:

                if estacion["fuente_datos"] != "DMC":
                    continue

                registros = consultar_mediciones_dmc_precipitacion(
                    estacion["estacion_id"],
                    tipo_registro="acumulado"
                )

                if registros:
                    fecha_mas_reciente = max(
                        registro["fecha_informe"]
                        for registro in registros
                    )

                    acumulados_dmc = [
                        registro
                        for registro in registros
                        if registro["fecha_informe"] == fecha_mas_reciente
                    ]

                    estacion_dmc = estacion
                    break

            if estacion_dmc is None:

                st.info(
                    "Todavía no hay informes de precipitación DMC "
                    "guardados para las estaciones disponibles."
                )

            else:

                fecha_informe = max(
                    registro["fecha_informe"]
                    for registro in acumulados_dmc
                )

                st.write(
                    f"**Estación de referencia:** "
                    f"{estacion_dmc['nombre']}"
                )

                st.caption(
                    f"Fuente: DMC · "
                    f"Distancia a la viña: "
                    f"{estacion_dmc['distancia_km']} km · "
                    f"Fecha del informe: {fecha_informe}"
                )

                if estacion_dmc["distancia_km"] > 30:
                    st.warning(
                        "Referencia meteorológica regional. "
                        f"Esta estación está a "
                        f"{estacion_dmc['distancia_km']:.2f} km "
                        "de la viña, fuera del radio de referencia "
                        "local de 30 km. Sus precipitaciones "
                        "corresponden a la estación y no deben "
                        "interpretarse como mediciones de la viña."
                    )

                dias_antiguedad = (
                    pd.Timestamp.now().date()
                    - pd.to_datetime(fecha_informe).date()
                ).days

                if dias_antiguedad > 7:
                    st.warning(
                        f"El informe tiene {dias_antiguedad} días "
                        "de antigüedad. Estos datos son históricos "
                        "y no representan la precipitación actual."
                    )

                else:
                    st.info(
                        "Informe reciente disponible. "
                        "Los valores corresponden al período "
                        "informado por la DMC."
                    )

                # Mostrar acumulados informados por la DMC.
                acumulados_por_periodo = {
                    registro["periodo"]: registro
                    for registro in acumulados_dmc
                }

                col1, col2, col3 = st.columns(3)

                for columna, periodo, etiqueta in [
                    (col1, "Hoy", "Acumulado Hoy"),
                    (col2, "Ayer", "Acumulado Ayer"),
                    (col3, "Hoy + Ayer", "Total Hoy + Ayer")
                ]:

                    registro = acumulados_por_periodo.get(periodo)

                    if registro is None:
                        valor = "No disponible"

                    elif (
                        registro["estado"] == "numerico"
                        and registro["precipitacion_mm"] is not None
                    ):
                        valor = (
                            f"{registro['precipitacion_mm']:.1f} mm"
                        )

                    elif registro["estado"] == "s/p":
                        valor = "s/p"

                    else:
                        valor = "No disponible"

                    columna.metric(etiqueta, valor)

                # Consultar el detalle horario del mismo informe.
                horarios_dmc = consultar_mediciones_dmc_precipitacion(
                    estacion_dmc["estacion_id"],
                    fecha_inicio=fecha_informe,
                    fecha_fin=fecha_informe,
                    tipo_registro="horario"
                )

                if horarios_dmc:

                    filas_horarias = []

                    for registro in horarios_dmc:

                        if (
                            registro["estado"] == "numerico"
                            and registro["precipitacion_mm"] is not None
                        ):
                            valor = (
                                f"{registro['precipitacion_mm']:.1f} mm"
                            )
                        elif registro["estado"] == "s/p":
                            valor = "s/p"
                        else:
                            valor = "No disponible"

                        filas_horarias.append({
                            "Período": registro["periodo"],
                            "Inicio UTC": registro["inicio_utc"],
                            "Término UTC": registro["termino_utc"],
                            "Precipitación": valor,
                            "Estado": registro["estado"],
                            "Observaciones": registro["observaciones"]
                        })

                    df_dmc = pd.DataFrame(filas_horarias)

                    with st.expander(
                        "Ver detalle horario de precipitación",
                        expanded=False
                    ):
                        st.dataframe(
                            df_dmc,
                            hide_index=True,
                            width="stretch"
                        )

                        st.caption(
                            "Los intervalos horarios están expresados en UTC. "
                            "s/p indica que el informe señala ausencia de "
                            "precipitación; no disponible indica que no "
                            "se pudo obtener un valor numérico."
                        )

                else:
                    st.info(
                        "Este informe no tiene registros horarios "
                        "disponibles."
                    )

        except Exception as e:
            st.warning(
                f"No se pudo cargar la información de precipitación DMC: {e}"
            )

    else:
        st.info(
            "Registra la ubicación de tu viña para consultar "
            "informes DMC de estaciones cercanas."
        )


# =========================================================
# PRECIPITACIÓN ACUMULADA DMC - RE1034
# =========================================================

if seccion_actual == "Meteorología y precipitaciones":

    st.divider()
    st.subheader("Precipitación acumulada - DMC (RE1034)")

    st.caption(
        "Informe de precipitaciones acumuladas en ventanas móviles "
        "de 24 a 144 horas y total anual. Estos valores no representan "
        "precipitaciones diarias independientes."
    )

    if latitud_guardada is not None and longitud_guardada is not None:

        try:
            estaciones_re1034 = consultar_estaciones_cercanas(
                VINA_ID_ACTUAL
            )

            estacion_re1034 = None
            registros_re1034 = []

            # Buscar la estación DMC más cercana con datos RE1034.
            for estacion in estaciones_re1034:

                if estacion["fuente_datos"] != "DMC":
                    continue

                registros = consultar_mediciones_dmc_re1034(
                    estacion["estacion_id"]
                )

                if not registros:
                    continue

                fecha_mas_reciente = max(
                    registro["fecha_informe"]
                    for registro in registros
                )

                registros_recientes = [
                    registro
                    for registro in registros
                    if registro["fecha_informe"] == fecha_mas_reciente
                ]

                estacion_re1034 = estacion
                registros_re1034 = registros_recientes
                break

            if estacion_re1034 is None:

                st.info(
                    "Todavía no hay informes RE1034 disponibles "
                    "para las estaciones DMC cercanas."
                )

            else:

                fecha_informe_re1034 = max(
                    registro["fecha_informe"]
                    for registro in registros_re1034
                )

                st.write(
                    f"**Estación de referencia:** "
                    f"{estacion_re1034['nombre']}"
                )

                st.caption(
                    f"Fuente: DMC · "
                    f"Distancia a la viña: "
                    f"{estacion_re1034['distancia_km']} km · "
                    f"Fecha del informe: {fecha_informe_re1034}"
                )

                if estacion_re1034["distancia_km"] > 30:
                    st.warning(
                        "Referencia meteorológica regional. "
                        f"Esta estación está a "
                        f"{estacion_re1034['distancia_km']:.2f} km "
                        "de la viña, fuera del radio de referencia "
                        "local de 30 km. Sus precipitaciones "
                        "corresponden a la estación y no deben "
                        "interpretarse como mediciones de la viña."
                    )

                dias_antiguedad_re1034 = (
                    pd.Timestamp.now().date()
                    - pd.to_datetime(
                        fecha_informe_re1034
                    ).date()
                ).days

                if dias_antiguedad_re1034 > 7:
                    st.warning(
                        f"El informe RE1034 tiene "
                        f"{dias_antiguedad_re1034} días "
                        "de antigüedad. Estos datos son "
                        "históricos y no representan "
                        "la precipitación actual."
                    )
                elif dias_antiguedad_re1034 < 0:
                    st.warning(
                        "La fecha del informe RE1034 es "
                        "posterior a la fecha actual. "
                        "Conviene revisar la fuente."
                    )

                registros_por_periodo = {
                    registro["periodo"]: registro
                    for registro in registros_re1034
                }

                periodos_re1034 = [
                    ("24Hrs", "Últimas 24 horas"),
                    ("48Hrs", "Últimas 48 horas"),
                    ("72Hrs", "Últimas 72 horas"),
                    ("96Hrs", "Últimas 96 horas"),
                    ("120Hrs", "Últimas 120 horas"),
                    ("144Hrs", "Últimas 144 horas")
                ]

                def mostrar_valor_re1034(registro):

                    if registro is None:
                        return "No disponible"

                    if (
                        registro["estado"] == "numerico"
                        and registro["precipitacion_mm"] is not None
                    ):
                        return (
                            f"{registro['precipitacion_mm']:.1f} mm"
                        )

                    if registro["estado"] == "s/p":
                        return "s/p"

                    if registro["estado"] == "no_reconocido":
                        return "No reconocido"

                    return "No disponible"

                # Mostrar los seis acumulados móviles en dos filas.
                for inicio in (0, 3):

                    grupo = periodos_re1034[inicio:inicio + 3]
                    columnas = st.columns(3)

                    for columna, (periodo, etiqueta) in zip(
                        columnas,
                        grupo
                    ):

                        registro = registros_por_periodo.get(periodo)

                        columna.metric(
                            etiqueta,
                            mostrar_valor_re1034(registro)
                        )

                        if registro and registro["fecha_referencia"]:
                            fecha_referencia = pd.to_datetime(
                                registro["fecha_referencia"]
                            ).strftime("%d-%m-%Y")

                            columna.caption(
                                f"Fecha de referencia: {fecha_referencia}"
                            )

                # Mostrar el total anual en una fila independiente.
                registro_anual = registros_por_periodo.get(
                    "total_anual"
                )

                st.divider()
                st.markdown("**Precipitación total anual informada**")

                columna_anual, _ = st.columns([1, 3])

                columna_anual.metric(
                    "Total anual",
                    mostrar_valor_re1034(registro_anual)
                )

                st.caption(
                    "s/p indica que la DMC no publicó una observación. "
                    "No se interpreta como 0 mm. Las ventanas de 24, "
                    "48, 72, 96, 120 y 144 horas son acumulados "
                    "móviles y no deben sumarse entre sí."
                )

        except Exception as e:
            st.warning(
                f"No se pudo cargar el informe DMC RE1034: {e}"
            )

    else:
        st.info(
            "Registra la ubicación de tu viña para consultar "
            "informes RE1034 de estaciones cercanas."
        )



# =========================================================

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

    # DM.5: distribución visual de Mapa y monitoreo
    panel_cargas, panel_visualizacion = st.columns(
        [0.7, 3.3],
        gap="medium"
    )

    # DM.14: alineación exacta del panel de importaciones
    st.markdown("""
    <style>
    div.st-key-dm5_zip_dispositivo,
    div.st-key-dm5_xlsx_fenologia,
    div.st-key-dm5_csv_plantas {
        margin-left: 0 !important;
        padding-left: 0 !important;
    }

    div.st-key-dm5_zip_dispositivo button,
    div.st-key-dm5_xlsx_fenologia button,
    div.st-key-dm5_csv_plantas button {
        width: 100% !important;
        justify-content: flex-start !important;
        text-align: left !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
        margin-left: 0 !important;
        border: none !important;
        background: transparent !important;
    }

    div.st-key-dm5_zip_dispositivo button p,
    div.st-key-dm5_xlsx_fenologia button p,
    div.st-key-dm5_csv_plantas button p {
        text-align: left !important;
        margin-left: 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)

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

        if st.button(
            "Inspeccionar archivo ZIP",
            key="dm26_inspeccionar_zip",
            type="primary",
            use_container_width=True
        ):

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
        background-color: #793DB5 !important;
        border-color: #793DB5 !important;
        color: #FFFFFF !important;
    }

    .st-key-dm49_guardar_mediciones button:not(:disabled) p {
        color: #FFFFFF !important;
    }

    .st-key-dm49_guardar_mediciones button:not(:disabled):hover {
        background-color: #65309B !important;
        border-color: #65309B !important;
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
        st.markdown("### Importar datos")

        if st.button(
            "📦 Cargar ZIP dispositivo",
            key="dm5_zip_dispositivo",
            use_container_width=True
        ):
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

        if st.button(
            "📊 Cargar xlsx fenologia",
            key="dm5_xlsx_fenologia",
            use_container_width=True
        ):
            ventana_xlsx_fenologia()

        if usuario_actual["rol"] == "administrador":

            if st.button(
                "🍇 Cargar CSV plantas",
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

    # Contenedores asociados al panel derecho
    filtros_col = panel_visualizacion.container()
    mapa_col = panel_visualizacion.container()

    # La ficha de planta permanece debajo de las columnas.
    der = st.container()

    # ---- Filtros compactos del mapa
    with filtros_col:
        st.subheader("Visualización de plantas")

        modo_mediciones = st.radio(
            "Modalidad de visualización",
            ["Último registro por planta", "Fecha específica"],
            horizontal=True,
            key=f"modo_mediciones_{VINA_ID_ACTUAL}"
        )

        modo_ultimo = (
            modo_mediciones == "Último registro por planta"
        )

        if modo_ultimo:
            st.caption(
                "Cada planta muestra su última medición disponible. "
                "Las fechas pueden ser diferentes entre plantas."
            )

        col_param, col_fecha, col_comparar = st.columns(
            [1.5, 1.2, 1.3],
            gap="medium"
        )

        hay_mediciones = bool(fechas and params)

        with col_param:
            if hay_mediciones:
                param = st.selectbox(
                    "Parámetro",
                    params,
                    format_func=lambda k: f"{info(k)['nombre']}  ·  {info(k)['archivo']}",
                    key="selector_parametro_mapa"
                )
            else:
                param = None
                st.caption("Sin parámetros registrados")

        with col_fecha:
            if modo_ultimo:
                fecha = None

                if fechas:
                    ultima_fecha_registrada = max(
                        pd.Timestamp(f).date()
                        for f in fechas
                    )

                    st.date_input(
                        "Última medición individual",
                        value=ultima_fecha_registrada,
                        format="DD/MM/YYYY",
                        disabled=True,
                        key=(
                            f"ultima_medicion_informativa_"
                            f"{VINA_ID_ACTUAL}_"
                            f"{ultima_fecha_registrada.isoformat()}"
                        ),
                        help=(
                            "Fecha más reciente registrada en la viña. "
                            "Cada planta conserva la fecha real "
                            "de su última medición."
                        )
                    )

                else:
                    st.text_input(
                        "Última medición individual",
                        value="Sin mediciones registradas",
                        disabled=True,
                        key=f"sin_ultima_medicion_{VINA_ID_ACTUAL}"
                    )

            elif fechas:
                fechas_calendario = {
                    pd.Timestamp(f).date(): f
                    for f in fechas
                }

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
            else:
                fecha = None
                st.caption("Sin mediciones registradas")

        with col_comparar:
            comparar = st.checkbox(
                "Comparar con otra fecha",
                disabled=(
                    modo_ultimo
                    or not hay_mediciones
                    or len(fechas) < 2
                )
            )

            comparar = (
                comparar and not modo_ultimo
                and hay_mediciones and len(fechas) >= 2
            )

            fecha2 = None

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
                        "Selecciona una fecha diferente "
                        "a la fecha de lectura."
                    )

                    comparar = False

                elif (
                    fecha_comparacion
                    not in fechas_calendario
                    or fecha_elegida
                    not in fechas_calendario
                ):

                    st.warning(
                        "Ambas fechas deben tener mediciones "
                        "para realizar la comparación."
                    )

                    comparar = False

                else:

                    fecha2 = fechas_calendario[
                        fecha_comparacion
                    ]

        col_cuartel, col_variedad = st.columns(
            2,
            gap="medium"
        )

        with col_cuartel:
            sel_cuartel = st.multiselect(
                "Cuartel",
                sorted(estructura_mapa["cuartel"].unique())
            )

        with col_variedad:
            sel_variedad = st.multiselect(
                "Variedad",
                sorted(estructura_mapa["variedad"].unique())
            )

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

            tab_mediciones, tab_evolucion, tab_fotografias = st.tabs(
                ["📊 Mediciones", "📈 Evolución", "📸 Fotografías e IA"]
            )

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


                from database import (
                    consultar_capturas_ambientales,
                    consultar_ambiente_fotografia
                )

                st.divider()
                st.markdown("### 🌡️ Historial ambiental del dispositivo")

                st.caption(
                    "Mediciones locales registradas al momento "
                    "de la captura. Independientes de las "
                    "estaciones meteorológicas externas."
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

                st.divider()

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

                        with st.expander(
                            f"Fotografía · {fecha_hora}",
                            expanded=False
                        ):
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

                                analizar = st.button(
                                    "🧠 Analizar fotografía",
                                    key=f"analizar_{image_id}"
                                )

                                if analizar:
                                    try:
                                        with st.spinner("Analizando fotografía..."):

                                            resultado = analizar_uvas_roboflow(str(ruta))

                                            guardar_analisis_imagen(
                                                image_id=image_id,
                                                modelo=resultado["modelo"],
                                                version_modelo=resultado["version_modelo"],
                                                cantidad_racimos=None,
                                                porcentaje_verde=None,
                                                porcentaje_envero=None,
                                                porcentaje_morado=None,
                                                etapa_fenologica=None,
                                                confianza=max(resultado["confianzas"], default=None),
                                                resultado_json=json.dumps(
                                                resultado,
                                                ensure_ascii=False,
                                                default=str
                                            ),
                                            vina_id=VINA_ID_ACTUAL
                                            )

                                        st.success("¡Análisis realizado y guardado correctamente!")

                                    except Exception as e:
                                        st.error(f"No se pudo analizar la fotografía: {e}")

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

                                            if modelo == "Roboflow":
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


# =========================================================
# RESUMEN Y DIAGNÓSTICO INTELIGENTE
# =========================================================

if seccion_actual == "Resumen y diagnóstico inteligente":

    st.title("🍇 Resumen y diagnóstico inteligente")

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
            f"Última fecha registrada: {fecha_ultima}"
        )

        st.info(
            "Este diagnóstico utiliza la última medición "
            "disponible de cada planta. Los registros pueden "
            "corresponder a fechas diferentes."
        )

        st.caption(
            f"Período de las mediciones consideradas: "
            f"{fecha_mas_antigua} a {fecha_ultima}."
        )

        distribucion_fechas = (
            datos_actuales["fecha"]
            .value_counts()
            .sort_index(ascending=False)
            .rename_axis("Fecha de medición")
            .reset_index(name="Cantidad de plantas")
        )

        with st.expander("Antigüedad de las mediciones"):
            st.dataframe(
                distribucion_fechas,
                hide_index=True,
                use_container_width=True
            )

        # -----------------------------------------------------
        # INDICADORES GENERALES
        # -----------------------------------------------------

        st.subheader("Estado general de la viña")

        cobertura1, cobertura2, cobertura3 = st.columns(3)

        cobertura1.metric(
            "Plantas registradas",
            total_registradas
        )

        cobertura2.metric(
            "Plantas sin historial",
            total_sin_historial
        )

        cobertura3.metric(
            "Cobertura de monitoreo",
            f"{100 * total_plantas / total_registradas:.1f}%"
            if total_registradas else "Sin datos"
        )

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            with st.container(border=True):
                st.metric(
                    "Plantas medidas",
                    f"{total_plantas:,}".replace(",", ".")
                )

        with col2:
            with st.container(border=True):
                st.metric(
                    "Cuarteles",
                    total_cuarteles
                )

        with col3:
            with st.container(border=True):
                st.metric(
                    "Variedades",
                    total_variedades
                )

        with col4:
            with st.container(border=True):
                st.metric(
                    "Registros históricos",
                    f"{total_mediciones:,}".replace(",", ".")
                )

        st.divider()

        # -----------------------------------------------------
        # PARÁMETROS DISPONIBLES
        # -----------------------------------------------------

        st.subheader("Indicadores de los últimos registros")

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
            "Los valores corresponden al promedio de las plantas "
            "considerando el último registro disponible "
            "de cada planta, aunque las fechas sean diferentes."
        )

        st.divider()

        # -----------------------------------------------------
        # ALERTAS SEGÚN UMBRALES CONFIGURADOS
        # -----------------------------------------------------

        st.subheader("Alertas de plantas")

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

        with st.container(border=True):
            st.metric(
                "Plantas con al menos una alerta",
                f"{total_plantas_alertadas:,}".replace(",", ".")
            )

        if alertas_detectadas:

            st.warning(
                "Se detectaron valores que superan los umbrales "
                "de atención configurados."
            )

            tabla_alertas = pd.DataFrame(
                alertas_detectadas
            )

            # -------------------------------------------------
            # RESUMEN POR CUARTEL
            # -------------------------------------------------

            st.subheader("Distribución de alertas por cuartel")

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
                resumen_cuarteles,
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

        st.subheader("🌦️ Condiciones meteorológicas")

        st.info(
            "Las estaciones meteorológicas proporcionan datos "
            "externos de referencia para contextualizar las "
            "condiciones de la viña. El dispositivo de monitoreo "
            "incorporará mediciones directas de temperatura y "
            "humedad durante cada captura de datos. Ambas fuentes "
            "son complementarias y deben interpretarse por separado."
        )

        if latitud_guardada is not None and longitud_guardada is not None:

            try:
                seleccion_resumen = seleccionar_estacion_con_historial(
                    VINA_ID_ACTUAL
                )

                if seleccion_resumen and seleccion_resumen["registros"]:

                    estacion_datos = seleccion_resumen["estacion"]
                    datos_meteo_resumen = seleccion_resumen["registros"]
                    datos_referencia = seleccion_resumen["es_referencia"]
                    dias_desde_ultimo = seleccion_resumen[
                        "dias_desde_ultimo"
                    ]

                    df_resumen_meteo = pd.DataFrame(
                        datos_meteo_resumen
                    )

                    df_resumen_meteo["fecha"] = pd.to_datetime(
                        df_resumen_meteo["fecha"]
                    )

                    df_resumen_meteo = (
                        df_resumen_meteo.sort_values("fecha")
                    )

                    ultimo_registro = df_resumen_meteo.iloc[-1]

                    estacion_cercana = seleccion_resumen["estacion_mas_cercana"]

                    col_cercana, col_historial = st.columns(2)

                    with col_cercana:
                        with st.container(border=True):
                            st.caption("ESTACIÓN MÁS CERCANA")
                            st.write(
                                f"**{estacion_cercana['nombre']}**"
                            )
                            st.caption(
                                f"Distancia a la viña: "
                                f"{estacion_cercana['distancia_km']} km"
                            )

                    with col_historial:
                        with st.container(border=True):
                            st.caption("ESTACIÓN PARA ANÁLISIS HISTÓRICO")
                            st.write(
                                f"**{estacion_datos['nombre']}**"
                            )
                            st.caption(
                                f"Distancia a la viña: "
                                f"{estacion_datos['distancia_km']} km"
                            )

                    if datos_referencia:
                        st.warning(
                            f"No hay registros de la estación más cercana. "
                            f"Se utilizan datos de referencia de "
                            f"{estacion_datos['nombre']}, ubicada a "
                            f"{estacion_datos['distancia_km']} km. "
                            "No representan mediciones directas de la viña."
                        )
                    else:
                        st.success(
                            "Datos de la estación meteorológica más cercana "
                            "con historial disponible."
                        )

                    st.caption(
                        f"Último registro disponible: "
                        f"{ultimo_registro['fecha'].date()} · "
                        f"Antigüedad: {dias_desde_ultimo} días · "
                        f"Fuente: {ultimo_registro['fuente_datos']}"
                    )

                    if dias_desde_ultimo > 7:
                        st.warning(
                            "Los datos disponibles son antiguos y deben "
                            "interpretarse como información histórica, "
                            "no como condiciones meteorológicas actuales."
                        )
                    elif dias_desde_ultimo < 0:
                        st.warning(
                            "La fecha del último registro es posterior "
                            "a la fecha actual. Conviene revisar la fuente."
                        )

                    def formato_meteo(valor, unidad):
                        numero = pd.to_numeric(
                            pd.Series([valor]),
                            errors="coerce"
                        ).iloc[0]

                        if pd.isna(numero):
                            return "Sin dato"

                        return f"{numero:.1f} {unidad}"

                    col1, col2, col3, col4 = st.columns(4)

                    col1.metric(
                        "Temperatura mínima",
                        formato_meteo(
                            ultimo_registro["temperatura_min"], "°C"
                        )
                    )

                    col2.metric(
                        "Temperatura máxima",
                        formato_meteo(
                            ultimo_registro["temperatura_max"], "°C"
                        )
                    )

                    col3.metric(
                        "Humedad relativa",
                        formato_meteo(
                            ultimo_registro["humedad_relativa"], "%"
                        )
                    )

                    col4.metric(
                        "Precipitación",
                        formato_meteo(
                            ultimo_registro["precipitacion"], "mm"
                        )
                    )

                else:
                    st.info(
                        "No hay una estación con historial suficiente "
                        "para mostrar indicadores meteorológicos."
                    )

                    if seleccion_resumen:
                        estacion_cercana = seleccion_resumen["estacion_mas_cercana"]
                        st.write(
                            f"**Estación más cercana:** "
                            f"{estacion_cercana['nombre']} · "
                            f"{estacion_cercana['distancia_km']} km"
                        )

                        for item in seleccion_resumen["diagnostico_estaciones"]:
                            st.caption(
                                f"{item['estacion']['nombre']}: "
                                f"{item['estado']} — {item['motivo']}"
                            )
                    else:
                        st.info(
                            "No hay estaciones registradas para las "
                            "coordenadas de esta viña."
                        )

            except Exception as e:
                st.warning(
                    f"No se pudo cargar el resumen meteorológico: {e}"
                )

        else:
            st.info(
                "Registra la ubicación geográfica de tu viña "
                "para incorporar información meteorológica."
            )

        st.divider()

        # -----------------------------------------------------
        # ACLARACIÓN SOBRE LOS RESULTADOS
        # -----------------------------------------------------

        st.subheader("¿Cómo interpretar este resumen?")

        st.info(
            "Los indicadores se calculan con las mediciones "
            "más recientes de cada planta, que pueden "
            "corresponder a fechas diferentes. "
            "La antigüedad de los registros debe considerarse "
            "antes de interpretar los resultados. "
            "Las alertas utilizan los umbrales definidos en "
            "la configuración de la plataforma. "
            "Representan señales para revisión y no constituyen "
            "por sí solas un diagnóstico agronómico definitivo."
        )

# =========================================================
# GALERÍA GENERAL DE FOTOGRAFÍAS Y ANÁLISIS IA
# =========================================================

if seccion_actual == "Fotografías y análisis IA":

    st.title("📸 Fotografías y análisis IA")

    st.caption(
        f"Galería fotográfica de {NOMBRE_VINA}"
    )

    # DF.2.9 - Navegación por claros monitoreados
    modo_galeria = st.radio(
        "Modo de consulta",
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

                st.success(
                    "Claro monitoreado: seis plantas configuradas."
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

    if not imagenes:

        if modo_galeria == "Todas las fotografías":
            st.info(
                "Esta viña todavía no tiene fotografías registradas. "
                "Puedes comenzar agregándolas desde la ficha de cada planta "
                "en Monitoreo de la viña."
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

                with st.expander(titulo_foto, expanded=False):

                    ruta = obtener_ruta_fotografia_segura(ruta_archivo)

                    st.markdown(
                        f"**Cuartel {cuartel or 'Sin información'} · "
                        f"Planta {numero_planta if numero_planta is not None else '-'}**"
                    )

                    st.caption(
                        f"{variedad or 'Variedad sin información'} · "
                        f"Fila {fila if fila is not None else '-'}"
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

                    if ruta is not None:

                        from PIL import Image, ImageOps

                        with Image.open(ruta) as imagen_original:
                            miniatura = ImageOps.fit(
                                imagen_original.convert("RGB"),
                                (320, 240),
                                method=Image.Resampling.LANCZOS,
                                centering=(0.5, 0.5)
                            )

                        st.image(
                            miniatura,
                            width="stretch"
                        )

                        if st.button(
                            "🧠 Analizar fotografía",
                            key=f"analizar_galeria_{image_id}"
                        ):

                            try:

                                with st.spinner(
                                    "Analizando fotografía..."
                                ):

                                    resultado = analizar_uvas_roboflow(
                                        str(ruta)
                                    )

                                    guardar_analisis_imagen(
                                        image_id=image_id,
                                        modelo=resultado["modelo"],
                                        version_modelo=resultado["version_modelo"],
                                        cantidad_racimos=None,
                                        porcentaje_verde=None,
                                        porcentaje_envero=None,
                                        porcentaje_morado=None,
                                        etapa_fenologica=None,
                                        confianza=max(resultado["confianzas"], default=None),
                                        resultado_json=json.dumps(
                                            resultado,
                                            ensure_ascii=False,
                                            default=str
                                        ),
                                        vina_id=VINA_ID_ACTUAL
                                    )

                                st.success(
                                    "Análisis realizado y guardado."
                                )

                            except Exception as e:

                                st.error(
                                    f"No se pudo analizar la fotografía: {e}"
                                )

                        historial = consultar_analisis_por_imagen(
                            image_id,
                            VINA_ID_ACTUAL
                        )

                        if historial:

                            with st.expander(
                                "📊 Ver historial de análisis"
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

                                        if modelo == "Roboflow":

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