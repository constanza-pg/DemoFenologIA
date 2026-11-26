from pathlib import Path
import os
import ast
import uuid
from getpass import getpass

BASE = Path(__file__).resolve().parent
RUTA_DB = BASE / "data" / "vina.db"

if RUTA_DB.exists():
    raise SystemExit(
        "Ya existe una base de datos. No se modificará."
    )

os.environ["VINA_DB_PATH"] = str(RUTA_DB)

import numpy as np
import pandas as pd
import database
from autenticacion import generar_hash

password = getpass("Crea una contraseña para la demo: ")

if len(password) < 10:
    raise SystemExit("Utiliza al menos 10 caracteres.")

if password != getpass("Confirma la contraseña: "):
    raise SystemExit("Las contraseñas no coinciden.")

# Recuperar la configuración y el generador existente
# sin ejecutar la interfaz de Streamlit.

arbol = ast.parse(
    (BASE / "app.py").read_text(encoding="utf-8")
)

nombres = {
    "LAT0", "LON0", "ESP_FILA", "ESP_PLANTA",
    "CUARTELES", "FECHAS", "PARAMETROS", "ESTACIONAL"
}

nodos = []

for nodo in arbol.body:
    if isinstance(nodo, (ast.Assign, ast.AnnAssign)):
        destinos = (
            nodo.targets
            if isinstance(nodo, ast.Assign)
            else [nodo.target]
        )

        variables = {
            elemento.id
            for destino in destinos
            for elemento in ast.walk(destino)
            if isinstance(elemento, ast.Name)
        }

        if variables & nombres:
            nodos.append(nodo)

    elif isinstance(nodo, ast.FunctionDef):
        if nodo.name == "generar_datos":
            nodo.decorator_list = []
            nodos.append(nodo)

contexto = {"np": np, "pd": pd}

exec(
    compile(
        ast.Module(body=nodos, type_ignores=[]),
        "generador_demo",
        "exec"
    ),
    contexto
)

faltantes = nombres - contexto.keys()

if faltantes:
    raise RuntimeError(
        f"Variables faltantes: {sorted(faltantes)}"
    )

datos = contexto["generar_datos"]()

database.inicializar_bd()
database.actualizar_esquema_transferencias()
database.actualizar_esquema_multi_vina()
database.actualizar_esquema_claros()
database.actualizar_esquema_capturas_dispositivo()
database.actualizar_esquema_imagenes_dispositivo()
database.actualizar_vista_imagenes_origen()

usuario_id = str(uuid.uuid4())

with database.conectar() as conexion:
    conexion.execute("""
        UPDATE vinas
        SET nombre = ?, ubicacion = ?,
            latitud = ?, longitud = ?
        WHERE id = ?
    """, (
        "Viña demostrativa FenologIA",
        "Ubicación de demostración",
        contexto["LAT0"],
        contexto["LON0"],
        "VINA001"
    ))

    conexion.execute("""
        INSERT INTO usuarios (
            usuario_id, vina_id, nombre,
            email, password_hash, rol, activo
        )
        VALUES (?, ?, ?, ?, ?, 'administrador', 1)
    """, (
        usuario_id,
        "VINA001",
        "Administrador demo",
        "demo@example.com",
        generar_hash(password)
    ))

plantas = database.guardar_plantas(
    datos, "VINA001", usuario_id
)

mediciones = database.guardar_mediciones(
    datos, "VINA001"
)

database.registrar_dispositivos_iniciales()

print("\n===== DEMOSTRACIÓN GENERADA =====")
print("Plantas:", plantas)
print("Mediciones:", mediciones)
print("Usuario: demo@example.com")
print("Base de datos:", RUTA_DB)
print("Proyecto original: SIN CAMBIOS")
