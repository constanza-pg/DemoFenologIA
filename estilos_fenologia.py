
import html
import streamlit as st


def mostrar_cabecera_fenologia(
    opciones_superiores,
    indice_activo,
    navegar
):

    st.markdown("""
    <style>
    .fenologia-logo {
        font-weight: 750;
        color: #242424;
    }

    .fenologia-logo span {
        color: #8265A3;
    }

    .block-container {
        padding-top: 1.2rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <style>
    .block-container {{
        padding-top: 0.8rem !important;
    }}

    div[class*="st-key-nav_superior_"] button {{
        min-height: 2.6rem !important;
        border: 1px solid transparent !important;
        border-radius: 8px !important;
        background: transparent !important;
        color: inherit !important;
        box-shadow: none !important;
        font-weight: 500 !important;
    }}

    div[class*="st-key-nav_superior_"] button:hover {{
        background: #EDF5E8 !important;
        color: #322345 !important;
    }}

    div.st-key-nav_superior_{indice_activo} button {{
        background: #84C55D !important;
        color: #17210F !important;
        font-weight: 650 !important;
    }}

    div[data-testid="stButton"] button[kind="primary"] {{
        background-color: #322345 !important;
        border-color: #322345 !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
        box-shadow: none !important;
    }}

    div[data-testid="stButton"] button[kind="primary"]:hover {{
        background-color: #49365E !important;
        border-color: #49365E !important;
    }}

    </style>
    """, unsafe_allow_html=True)

    col_sesion, col_salir = st.columns([5, 1])

    with col_sesion:
        st.markdown(
            '<div class="fenologia-logo" style="font-size:1.8rem;">'
            'Fenolog<span>IA</span></div>',
            unsafe_allow_html=True
        )

    with col_salir:
        if st.button(
            "Cerrar sesión",
            key="fenologia_cerrar_sesion_visible",
            use_container_width=True
        ):
            st.session_state.clear()
            st.rerun()


    columnas_nav = st.columns(
        [0.45, 0.85, 1.15, 1.15, 1.25, 1.45, 0.9, 0.45],
        gap="small"
    )

    for indice, (seccion, etiqueta) in enumerate(opciones_superiores):
        with columnas_nav[indice + 1]:
            st.button(
                etiqueta,
                key=f"nav_superior_{indice}",
                use_container_width=True,
                type="secondary",
                on_click=navegar,
                args=(seccion,)
            )

    st.markdown("""
    <style>
    [data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }

    .block-container {
        max-width: 1500px !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }

    div.st-key-dm18_separador {
        margin-top: -0.5rem !important;
        margin-bottom: -0.5rem !important;
    }

    div.st-key-dm18_separador hr {
        margin: 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    with st.container(key="dm18_separador"):
        st.markdown(
            '<div style="border-top:1px solid #E0E0E0;"></div>',
            unsafe_allow_html=True
        )


def mostrar_titulo_inicio(titulo, subtitulo):

    st.markdown("""
    <style>
    .fenologia-inicio-titulo {
        font-size: 2rem;
        font-weight: 650;
        margin-bottom: 0.2rem;
    }

    .fenologia-inicio-subtitulo {
        color: #777777;
        font-size: 1rem;
        margin-bottom: 1.5rem;
    }
    </style>
    """, unsafe_allow_html=True)

    titulo = html.escape(str(titulo))
    subtitulo = html.escape(str(subtitulo))

    st.markdown(
        f'<div class="fenologia-inicio-titulo">'
        f'{titulo}</div>'
        f'<div class="fenologia-inicio-subtitulo">'
        f'{subtitulo}</div>',
        unsafe_allow_html=True
    )
