import streamlit as st

def render_monitoreo_vina(context: dict):
    # traer dependencias desde context
    globals_ref = context.get("globals_ref", {})
    # Esto permite acceder a nombres como pd, np, px, go, uuid, fmt, info, etc. si están en app.py
    st_local = context["st"]
    st_local.subheader("Monitoreo de la viña")

    # --- IMPORTANTE ---
    # Aquí pegaremos el bloque completo que hoy está en app.py bajo:
    # if seccion_actual == "Monitoreo de la viña":
    #
    # Para hacerlo bien, usaremos context['pd'], context['np'], etc.
