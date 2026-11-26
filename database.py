from contextlib import nullcontext

import sqlite3
import pandas as pd
import json
import os
from pathlib import Path
import uuid


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

DB_PATH = Path(
    os.environ.get("VINA_DB_PATH", str(DATA_DIR / "vina.db"))
)


def conectar():
    DATA_DIR.mkdir(exist_ok=True)

    conexion = sqlite3.connect(DB_PATH)
    conexion.execute("PRAGMA foreign_keys = ON")

    return conexion




def verificar_permiso_mediciones(conexion, usuario_id, vina_id):
    """
    Autoriza la carga de mediciones de plantas existentes.

    Permite administradores y usuarios activos
    pertenecientes a la viña indicada.

    No autoriza registrar ni modificar plantas.
    No modifica la base de datos.
    """

    if not usuario_id or not vina_id:
        raise PermissionError(
            "No se pudo verificar la autorización."
        )

    usuario = conexion.execute("""
        SELECT vina_id, rol, activo
        FROM usuarios
        WHERE usuario_id = ?
    """, (usuario_id,)).fetchone()

    if usuario is None:
        raise PermissionError(
            "El usuario no existe."
        )

    vina_usuario, rol, activo = usuario

    if activo != 1:
        raise PermissionError(
            "La cuenta de usuario no está activa."
        )

    if rol not in ("administrador", "usuario"):
        raise PermissionError(
            "El usuario no tiene un rol autorizado."
        )

    if vina_usuario != vina_id:
        raise PermissionError(
            "No puedes importar mediciones "
            "de otra viña."
        )

    return True


def verificar_administrador_vina(conexion, usuario_id, vina_id):
    """
    Comprueba que un usuario activo sea administrador
    de la viña indicada.

    No modifica la base de datos.
    """

    if not usuario_id or not vina_id:
        raise PermissionError(
            "No se pudo verificar la autorización."
        )

    usuario = conexion.execute("""
        SELECT vina_id, rol, activo
        FROM usuarios
        WHERE usuario_id = ?
    """, (usuario_id,)).fetchone()

    if usuario is None:
        raise PermissionError(
            "El usuario no existe."
        )

    vina_usuario, rol, activo = usuario

    if activo != 1 or rol != "administrador":
        raise PermissionError(
            "No tienes permisos para modificar "
            "la estructura de la viña."
        )

    if vina_usuario != vina_id:
        raise PermissionError(
            "No puedes modificar plantas "
            "de otra viña."
        )

    return True

def inicializar_bd():

    with conectar() as conexion:

        # 1. Viñas registradas en la plataforma
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS vinas (
                id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                ubicacion TEXT,
                fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Plantas pertenecientes a cada viña
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS plantas (
                id TEXT PRIMARY KEY,
                vina_id TEXT NOT NULL,
                cuartel TEXT,
                variedad TEXT,
                fila INTEGER,
                numero_planta INTEGER,
                lat REAL,
                lon REAL,

                FOREIGN KEY (vina_id) REFERENCES vinas(id)
            )
        """)

        # 3. Dispositivos instalados en cada viña
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS dispositivos (
                device_id TEXT PRIMARY KEY,
                vina_id TEXT NOT NULL,
                modelo TEXT,
                fecha_instalacion TEXT,
                ultima_conexion TEXT,

                FOREIGN KEY (vina_id) REFERENCES vinas(id)
            )
        """)

        # 4. Mediciones realizadas
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS mediciones (
                measurement_id TEXT PRIMARY KEY,
                plant_id TEXT NOT NULL,
                device_id TEXT,
                fecha_hora TEXT NOT NULL,
                etapa_fenologica TEXT,
                porcentaje_verde REAL,
                porcentaje_envero REAL,
                porcentaje_morado REAL,
                confianza_modelo REAL,
                version_modelo TEXT,
                datos_json TEXT DEFAULT '{}',

                FOREIGN KEY (plant_id) REFERENCES plantas(id),
                FOREIGN KEY (device_id) REFERENCES dispositivos(device_id)
            )
        """)

        # 5. Fotografías asociadas a las mediciones
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS imagenes (
                image_id TEXT PRIMARY KEY,
                measurement_id TEXT NOT NULL,
                ruta_archivo TEXT NOT NULL,
                tipo_imagen TEXT,
                fecha_subida TEXT,

                FOREIGN KEY (measurement_id)
                    REFERENCES mediciones(measurement_id)
            )
        """)

        # 6. Análisis de inteligencia artificial de las fotografías
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS analisis_imagenes (
                analisis_id TEXT PRIMARY KEY,
                image_id TEXT NOT NULL,

                modelo TEXT,
                version_modelo TEXT,

                cantidad_racimos INTEGER,

                porcentaje_verde REAL,
                porcentaje_envero REAL,
                porcentaje_morado REAL,

                etapa_fenologica TEXT,
                confianza REAL,

                resultado_json TEXT DEFAULT '{}',
                fecha_analisis TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (image_id)
                    REFERENCES imagenes(image_id)
            )
        """)

        # Índice para consultar rápidamente los análisis de cada fotografía
        conexion.execute("""
            CREATE INDEX IF NOT EXISTS idx_analisis_imagenes
            ON analisis_imagenes(image_id)
        """)
        
        # 7. Historial de transferencias de archivos
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS transferencias (
                transferencia_id TEXT PRIMARY KEY,
                image_id TEXT NOT NULL,
                medio TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'PENDIENTE',
                fecha_inicio TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_fin TEXT,
                intentos INTEGER DEFAULT 0,
                mensaje_error TEXT,

                FOREIGN KEY (image_id)
                    REFERENCES imagenes(image_id),

                CHECK (medio IN ('USB', 'WIFI')),
                CHECK (estado IN (
                    'PENDIENTE',
                    'COMPLETADA',
                    'ERROR'
                ))
            )
        """)

        # Registrar nuestra primera viña de prueba
        conexion.execute("""
            INSERT OR IGNORE INTO vinas (id, nombre, ubicacion)
            VALUES (?, ?, ?)
        """, ("VINA001", "Viña de prueba", "Por definir"))


def consultar_tablas():
    with conectar() as conexion:
        resultado = conexion.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
        """).fetchall()

    return [fila[0] for fila in resultado]


def consultar_vinas():
    with conectar() as conexion:
        resultado = conexion.execute("""
            SELECT id, nombre, ubicacion
            FROM vinas
        """).fetchall()

    return resultado


def consultar_vina(vina_id):
    """Consulta los datos de una viña específica."""

    with conectar() as conexion:
        resultado = conexion.execute("""
            SELECT id, nombre, ubicacion, latitud, longitud
            FROM vinas
            WHERE id = ?
        """, (vina_id,)).fetchone()

    return resultado



def actualizar_ubicacion_vina(
    vina_id,
    ubicacion,
    latitud,
    longitud
):
    """Registra la ubicación geográfica inicial de una viña.
    Una vez registrada, no permite modificarla.
    """

    if latitud is None or longitud is None:
        raise ValueError(
            "Debes ingresar latitud y longitud."
        )

    if not -90 <= latitud <= 90:
        raise ValueError("La latitud no es válida.")

    if not -180 <= longitud <= 180:
        raise ValueError("La longitud no es válida.")

    with conectar() as conexion:

        # Verificar que la viña exista
        vina = conexion.execute("""
            SELECT latitud, longitud
            FROM vinas
            WHERE id = ?
        """, (vina_id,)).fetchone()

        if vina is None:
            raise ValueError("La viña indicada no existe.")

        # Impedir modificar una ubicación ya registrada
        if vina[0] is not None or vina[1] is not None:
            raise ValueError(
                "La ubicación de esta viña ya fue registrada "
                "y no se puede modificar."
            )

        # Registrar la ubicación por primera vez
        resultado = conexion.execute("""
            UPDATE vinas
            SET ubicacion = ?,
                latitud = ?,
                longitud = ?
            WHERE id = ?
              AND latitud IS NULL
              AND longitud IS NULL
        """, (
            ubicacion,
            latitud,
            longitud,
            vina_id
        ))

        if resultado.rowcount == 0:
            raise ValueError(
                "No se pudo registrar la ubicación."
            )

def registrar_dispositivos_iniciales():
    """Registra los módulos iniciales sin cambiar su propietario."""

    dispositivos = [
        ("CAM001", "VINA001", "ESP32-CAM + OV2640"),
        ("BASE001", "VINA001", "ESP32-S3 DevKitC-1"),
        ("REP001", "VINA001", "Seeed XIAO ESP32-C3")
    ]

    with conectar() as conexion:
        conexion.executemany("""
            INSERT OR IGNORE INTO dispositivos (
                device_id,
                vina_id,
                modelo
            )
            VALUES (?, ?, ?)
        """, dispositivos)


def consultar_dispositivos(vina_id):
    """Consulta únicamente los dispositivos de una viña."""

    with conectar() as conexion:
        resultado = conexion.execute("""
            SELECT device_id, vina_id, modelo,
                   fecha_instalacion, ultima_conexion
            FROM dispositivos
            WHERE vina_id = ?
            ORDER BY device_id
        """, (vina_id,)).fetchall()

    return resultado


def crear_transferencia(image_id, medio, vina_id):
    """Crea una transferencia verificando la propiedad de la imagen."""

    if medio not in ("USB", "WIFI"):
        raise ValueError("El medio debe ser USB o WIFI")

    transferencia_id = str(uuid.uuid4())

    with conectar() as conexion:
        imagen = conexion.execute("""
            SELECT i.image_id
            FROM vista_imagenes_origen i
            
            WHERE i.image_id = ?
            AND i.vina_id = ?
        """, (image_id, vina_id)).fetchone()

        if imagen is None:
            raise ValueError(
                "La fotografía no pertenece a esta viña."
            )

        conexion.execute("""
            INSERT INTO transferencias (
                transferencia_id,
                image_id,
                medio,
                estado
            )
            VALUES (?, ?, ?, 'PENDIENTE')
        """, (transferencia_id, image_id, medio))

    return transferencia_id


def actualizar_transferencia(
    transferencia_id,
    estado,
    vina_id,
    mensaje_error=None
):
    """Actualiza una transferencia solo si pertenece a la viña."""

    if estado not in ("PENDIENTE", "COMPLETADA", "ERROR"):
        raise ValueError("Estado de transferencia no válido")

    with conectar() as conexion:
        transferencia = conexion.execute("""
            SELECT t.transferencia_id
            FROM transferencias t
            JOIN vista_imagenes_origen i ON t.image_id = i.image_id
            
            WHERE t.transferencia_id = ?
            AND i.vina_id = ?
        """, (transferencia_id, vina_id)).fetchone()

        if transferencia is None:
            raise ValueError(
                "La transferencia no pertenece a esta viña."
            )

        if estado == "PENDIENTE":
            conexion.execute("""
                UPDATE transferencias
                SET estado = ?,
                    fecha_fin = NULL,
                    mensaje_error = ?
                WHERE transferencia_id = ?
            """, (estado, mensaje_error, transferencia_id))
        else:
            conexion.execute("""
                UPDATE transferencias
                SET estado = ?,
                    fecha_fin = CURRENT_TIMESTAMP,
                    mensaje_error = ?
                WHERE transferencia_id = ?
            """, (estado, mensaje_error, transferencia_id))


def consultar_transferencias(vina_id):
    """Consulta únicamente las transferencias de una viña."""

    with conectar() as conexion:
        return conexion.execute("""
            SELECT t.transferencia_id, t.image_id, t.medio,
                   t.estado, t.fecha_inicio, t.fecha_fin,
                   t.intentos, t.mensaje_error
            FROM transferencias t
            JOIN vista_imagenes_origen i ON t.image_id = i.image_id
            
            WHERE i.vina_id = ?
            ORDER BY t.fecha_inicio DESC
        """, (vina_id,)).fetchall()


def guardar_plantas(datos, vina_id, usuario_id, conexion=None):
    """Guarda o actualiza plantas dentro de una viña."""

    columnas = [
        "id", "cuartel", "variedad", "fila",
        "planta", "lat", "lon"
    ]

    plantas = datos.drop_duplicates(subset=["id"])
    cantidad = 0

    with (conectar() if conexion is None else nullcontext(conexion)) as conexion:

        verificar_administrador_vina(
            conexion,
            usuario_id,
            vina_id
        )

        for _, fila in plantas.iterrows():

            codigo = str(fila["id"]).strip()

            if not codigo or codigo == "nan":
                raise ValueError("Una planta tiene un código vacío.")

            valores = {}

            for columna in columnas[1:]:
                valor = fila[columna] if columna in fila.index else None

                if pd.isna(valor):
                    valor = None

                valores[columna] = valor

            existente = conexion.execute("""
                SELECT id
                FROM plantas
                WHERE vina_id = ?
                AND codigo_planta = ?
            """, (vina_id, codigo)).fetchone()

            if existente:
                planta_id = existente[0]

                conexion.execute("""
                    UPDATE plantas
                    SET cuartel = ?,
                        variedad = ?,
                        fila = ?,
                        numero_planta = ?,
                        lat = ?,
                        lon = ?
                    WHERE id = ?
                    AND vina_id = ?
                """, (
                    valores["cuartel"],
                    valores["variedad"],
                    valores["fila"],
                    valores["planta"],
                    valores["lat"],
                    valores["lon"],
                    planta_id,
                    vina_id
                ))

            else:
                planta_id = str(uuid.uuid4())

                conexion.execute("""
                    INSERT INTO plantas (
                        id,
                        vina_id,
                        codigo_planta,
                        cuartel,
                        variedad,
                        fila,
                        numero_planta,
                        lat,
                        lon
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    planta_id,
                    vina_id,
                    codigo,
                    valores["cuartel"],
                    valores["variedad"],
                    valores["fila"],
                    valores["planta"],
                    valores["lat"],
                    valores["lon"]
                ))

            cantidad += 1

    return cantidad


def guardar_mediciones(datos, vina_id="VINA001"):
    """Guarda mediciones asociadas a plantas de una viña."""

    columnas_base = [
        "id", "fecha", "lat", "lon",
        "cuartel", "variedad", "fila", "planta"
    ]

    parametros = [
        columna for columna in datos.columns
        if columna not in columnas_base
        and pd.api.types.is_numeric_dtype(datos[columna])
    ]

    mediciones = datos.drop_duplicates(
        subset=["id", "fecha"],
        keep="last"
    )

    registros = []

    with conectar() as conexion:

        for _, fila in mediciones.iterrows():

            codigo = str(fila["id"]).strip()
            fecha = str(fila["fecha"])

            planta = conexion.execute("""
                SELECT id
                FROM plantas
                WHERE vina_id = ?
                AND codigo_planta = ?
            """, (vina_id, codigo)).fetchone()

            if planta is None:
                raise ValueError(
                    f"No existe la planta {codigo} "
                    f"en la viña {vina_id}."
                )

            planta_id = planta[0]

            measurement_id = f"{planta_id}_{fecha}"

            valores = {}

            for parametro in parametros:
                valor = fila[parametro]

                if pd.isna(valor):
                    valor = None
                else:
                    valor = float(valor)

                valores[parametro] = valor

            datos_json = json.dumps(
                valores,
                ensure_ascii=False
            )

            registros.append((
                measurement_id,
                planta_id,
                fecha,
                datos_json
            ))

        conexion.executemany("""
            INSERT INTO mediciones (
                measurement_id,
                plant_id,
                fecha_hora,
                datos_json
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(measurement_id) DO UPDATE SET
                fecha_hora = excluded.fecha_hora,
                datos_json = excluded.datos_json
        """, registros)

    return len(registros)




def diagnosticar_discrepancias_csv(datos, vina_id, usuario_id):
    """
    Detecta diferencias estructurales entre el CSV
    y las plantas existentes.

    No modifica la base de datos.
    """

    from validacion_csv_prueba import validar_csv

    datos = validar_csv(datos)

    campos = {
        "cuartel": "cuartel",
        "variedad": "variedad",
        "fila": "fila",
        "planta": "numero_planta",
        "lat": "lat",
        "lon": "lon"
    }

    discrepancias = []

    with conectar() as conexion:

        verificar_administrador_vina(
            conexion,
            usuario_id,
            vina_id
        )

        conexion.row_factory = sqlite3.Row

        for codigo, grupo in datos.groupby("id", sort=False):

            existente = conexion.execute("""
                SELECT
                    cuartel,
                    variedad,
                    fila,
                    numero_planta,
                    lat,
                    lon
                FROM plantas
                WHERE vina_id = ?
                  AND codigo_planta = ?
            """, (vina_id, codigo)).fetchone()

            if existente is None:
                continue

            for _, fila_csv in grupo.iterrows():

                for campo_csv, campo_bd in campos.items():

                    if campo_csv not in datos.columns:
                        continue

                    valor_csv = fila_csv[campo_csv]
                    valor_bd = existente[campo_bd]

                    if pd.isna(valor_csv):
                        continue

                    if isinstance(valor_csv, str):
                        valor_csv = valor_csv.strip()

                        if valor_csv.lower() in (
                            "", "sin dato"
                        ):
                            continue

                    if valor_bd is None:
                        diferente = True

                    elif campo_csv in ("lat", "lon"):
                        diferente = (
                            abs(
                                float(valor_csv)
                                - float(valor_bd)
                            ) > 0.000001
                        )

                    elif campo_csv in ("fila", "planta"):
                        diferente = (
                            float(valor_csv)
                            != float(valor_bd)
                        )

                    else:
                        diferente = (
                            str(valor_csv).strip()
                            != str(valor_bd).strip()
                        )

                    if diferente:
                        discrepancias.append({
                            "codigo_planta": codigo,
                            "fecha_csv": fila_csv["fecha"],
                            "campo": campo_csv,
                            "valor_existente": valor_bd,
                            "valor_csv": valor_csv
                        })

    return pd.DataFrame(
        discrepancias,
        columns=[
            "codigo_planta",
            "fecha_csv",
            "campo",
            "valor_existente",
            "valor_csv"
        ]
    )


def importar_csv_conservador(datos, vina_id, usuario_id):
    """
    Importa únicamente plantas y mediciones nuevas.

    No modifica registros existentes.
    Toda la operación utiliza una transacción SQLite.
    """

    from validacion_csv_prueba import validar_csv

    datos = validar_csv(datos)

    columnas_base = {
        "id", "fecha", "lat", "lon",
        "cuartel", "variedad", "fila", "planta"
    }

    parametros = [
        columna
        for columna in datos.columns
        if columna not in columnas_base
        and pd.api.types.is_numeric_dtype(datos[columna])
    ]

    resultado = {
        "plantas_creadas": 0,
        "plantas_omitidas": 0,
        "mediciones_creadas": 0,
        "mediciones_omitidas": 0
    }

    plantas_csv = datos.drop_duplicates(subset=["id"])

    with conectar() as conexion:

        verificar_administrador_vina(
            conexion,
            usuario_id,
            vina_id
        )

        for _, fila in plantas_csv.iterrows():

            codigo = str(fila["id"]).strip()

            existente = conexion.execute("""
                SELECT id
                FROM plantas
                WHERE vina_id = ?
                  AND codigo_planta = ?
            """, (vina_id, codigo)).fetchone()

            if existente is not None:
                resultado["plantas_omitidas"] += 1
                continue

            planta_id = str(uuid.uuid4())

            def valor_opcional(columna):
                valor = fila.get(columna)
                return None if pd.isna(valor) else valor

            conexion.execute("""
                INSERT INTO plantas (
                    id, vina_id, codigo_planta,
                    cuartel, variedad, fila,
                    numero_planta, lat, lon
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                planta_id,
                vina_id,
                codigo,
                valor_opcional("cuartel"),
                valor_opcional("variedad"),
                valor_opcional("fila"),
                valor_opcional("planta"),
                valor_opcional("lat"),
                valor_opcional("lon")
            ))

            resultado["plantas_creadas"] += 1

        for _, fila in datos.iterrows():

            codigo = str(fila["id"]).strip()
            fecha = str(fila["fecha"])

            planta = conexion.execute("""
                SELECT id
                FROM plantas
                WHERE vina_id = ?
                  AND codigo_planta = ?
            """, (vina_id, codigo)).fetchone()

            if planta is None:
                raise ValueError(
                    f"No existe la planta {codigo}."
                )

            planta_id = planta[0]
            measurement_id = f"{planta_id}_{fecha}"

            existente = conexion.execute("""
                SELECT 1
                FROM mediciones
                WHERE measurement_id = ?
                   OR (
                       plant_id = ?
                       AND fecha_hora = ?
                   )
                LIMIT 1
            """, (
                measurement_id,
                planta_id,
                fecha
            )).fetchone()

            if existente is not None:
                resultado["mediciones_omitidas"] += 1
                continue

            valores = {}

            for parametro in parametros:
                valor = fila[parametro]
                valores[parametro] = (
                    None if pd.isna(valor) else float(valor)
                )

            conexion.execute("""
                INSERT INTO mediciones (
                    measurement_id,
                    plant_id,
                    fecha_hora,
                    datos_json
                )
                VALUES (?, ?, ?, ?)
            """, (
                measurement_id,
                planta_id,
                fecha,
                json.dumps(valores, ensure_ascii=False)
            ))

            resultado["mediciones_creadas"] += 1

    return resultado



def importar_xlsx_mediciones_seguro(datos, vina_id, usuario_id):
    """
    Importa mediciones fenológicas de plantas existentes.

    No crea plantas ni sobrescribe mediciones.
    Valida el archivo completo antes de escribir.
    Ejecuta la importación en una transacción SQLite.
    """

    import math
    from datetime import date, datetime

    columnas = [
        "id", "fecha", "ndvi", "hum",
        "psi", "brix", "rend"
    ]

    if not isinstance(datos, pd.DataFrame):
        raise ValueError("Los datos deben ser una tabla.")

    if list(datos.columns) != columnas:
        raise ValueError(
            "Las columnas del XLSX no coinciden "
            "con la plantilla FenologIA."
        )

    if datos.empty:
        raise ValueError(
            "El archivo no contiene mediciones."
        )

    registros = []
    claves = set()

    for indice, fila in enumerate(
        datos.itertuples(index=False, name=None),
        start=2
    ):
        codigo, fecha, *valores_originales = fila

        if pd.isna(codigo) or not str(codigo).strip():
            raise ValueError(
                f"Fila {indice}: identificador vacío."
            )

        codigo = str(codigo).strip()

        if pd.isna(fecha):
            raise ValueError(
                f"Fila {indice}: fecha vacía."
            )

        try:
            if isinstance(fecha, (datetime, date)):
                fecha = fecha.strftime("%Y-%m-%d")
            else:
                fecha = datetime.strptime(
                    str(fecha).strip(),
                    "%Y-%m-%d"
                ).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            raise ValueError(
                f"Fila {indice}: fecha inválida."
            )

        clave = (codigo, fecha)

        if clave in claves:
            raise ValueError(
                f"Fila {indice}: planta y fecha duplicadas."
            )

        claves.add(clave)

        valores = {}

        for variable, valor in zip(
            columnas[2:],
            valores_originales
        ):
            if pd.isna(valor):
                valores[variable] = None
                continue

            try:
                numero = float(valor)

                if not math.isfinite(numero):
                    raise ValueError()

                valores[variable] = numero

            except (ValueError, TypeError):
                raise ValueError(
                    f"Fila {indice}: valor inválido "
                    f"en {variable}."
                )

        if all(valor is None for valor in valores.values()):
            raise ValueError(
                f"Fila {indice}: debe existir al menos "
                "una medición válida."
            )

        registros.append((codigo, fecha, valores))

    resultado = {
        "mediciones_creadas": 0,
        "mediciones_omitidas": 0
    }

    with conectar() as conexion:

        # Iniciar transacción antes de comprobar permisos
        # y existencia de registros.
        conexion.execute("BEGIN IMMEDIATE")

        verificar_permiso_mediciones(
            conexion, usuario_id, vina_id
        )

        preparados = []

        # Validar todas las plantas antes de insertar.
        for codigo, fecha, valores in registros:

            planta = conexion.execute("""
                SELECT id
                FROM plantas
                WHERE vina_id = ?
                  AND codigo_planta = ?
            """, (vina_id, codigo)).fetchone()

            if planta is None:
                raise ValueError(
                    f"La planta {codigo} no existe "
                    f"en la viña seleccionada."
                )

            planta_id = planta[0]

            existente = conexion.execute("""
                SELECT datos_json
                FROM mediciones
                WHERE plant_id = ?
                  AND fecha_hora = ?
                LIMIT 1
            """, (planta_id, fecha)).fetchone()

            if existente:
                try:
                    valores_existentes = json.loads(
                        existente[0] or "{}"
                    )

                    if not isinstance(valores_existentes, dict):
                        raise ValueError()

                except (ValueError, TypeError):
                    raise ValueError(
                        f"No se pudo verificar la medición "
                        f"existente de {codigo} del {fecha}."
                    )

                diferencias = [
                    variable
                    for variable, valor in valores.items()
                    if valores_existentes.get(variable) != valor
                ]

                if diferencias:
                    raise ValueError(
                        f"Conflicto en planta {codigo}, "
                        f"fecha {fecha}. "
                        "Variables diferentes: "
                        + ", ".join(diferencias)
                        + ". No se sobrescribieron mediciones."
                    )

                resultado["mediciones_omitidas"] += 1
                continue

            measurement_id = f"{planta_id}_{fecha}"

            preparados.append((
                measurement_id,
                planta_id,
                fecha,
                json.dumps(valores, ensure_ascii=False)
            ))

        # Insertar únicamente después de validar
        # todas las plantas del archivo.
        for registro in preparados:

            conexion.execute("""
                INSERT INTO mediciones (
                    measurement_id,
                    plant_id,
                    fecha_hora,
                    datos_json
                )
                VALUES (?, ?, ?, ?)
            """, registro)

            resultado["mediciones_creadas"] += 1

    return resultado


def consultar_datos(vina_id="VINA001", fecha=None, plant_id=None):
    """
    Recupera plantas y mediciones de una viña.
    El código visible y el identificador interno se mantienen separados.
    """

    conexion = conectar()

    try:
        consulta = """
            SELECT
                p.codigo_planta AS id,
                p.id AS plant_internal_id,
                p.cuartel,
                p.variedad,
                p.fila,
                p.numero_planta AS planta,
                p.lat,
                p.lon,
                m.fecha_hora AS fecha,
                m.datos_json
            FROM mediciones m
            INNER JOIN plantas p
                ON m.plant_id = p.id
            WHERE p.vina_id = ?
        """

        parametros = [vina_id]

        if fecha is not None:
            consulta += " AND m.fecha_hora = ?"
            parametros.append(str(fecha))

        if plant_id is not None:
            consulta += " AND p.id = ?"
            parametros.append(str(plant_id))

        consulta += " ORDER BY m.fecha_hora, p.codigo_planta"

        resultado = conexion.execute(
            consulta, parametros
        ).fetchall()

        columnas = [
            "id",
            "plant_internal_id",
            "cuartel",
            "variedad",
            "fila",
            "planta",
            "lat",
            "lon",
            "fecha",
            "datos_json"
        ]

        registros = []

        for registro in resultado:
            fila = dict(zip(columnas, registro))

            try:
                mediciones = json.loads(
                    fila.pop("datos_json") or "{}"
                )
            except (json.JSONDecodeError, TypeError):
                mediciones = {}

            fila.update(mediciones)
            registros.append(fila)

        return pd.DataFrame(registros)

    finally:
        conexion.close()


def actualizar_esquema_transferencias():
    """Prepara SQLite para registrar módulos y transferencias."""

    with conectar() as conexion:

        # 0. Agregar coordenadas geográficas a cada viña
        columnas_vinas = [
            fila[1]
            for fila in conexion.execute(
                "PRAGMA table_info(vinas)"
            ).fetchall()
        ]

        if "latitud" not in columnas_vinas:
            conexion.execute("""
                ALTER TABLE vinas
                ADD COLUMN latitud REAL
            """)

        if "longitud" not in columnas_vinas:
            conexion.execute("""
                ALTER TABLE vinas
                ADD COLUMN longitud REAL
            """)

        # Añadir el tipo de módulo a los dispositivos existentes
        tablas = conexion.execute("""
            SELECT name FROM sqlite_master WHERE type = 'table'
        """).fetchall()

        nombres_tablas = [fila[0] for fila in tablas]

        if "dispositivos" in nombres_tablas:
            columnas = [
                fila[1]
                for fila in conexion.execute(
                    "PRAGMA table_info(dispositivos)"
                ).fetchall()
            ]

            if "tipo_modulo" not in columnas:
                conexion.execute("""
                    ALTER TABLE dispositivos
                    ADD COLUMN tipo_modulo TEXT
                """)

        # Registrar las transferencias de archivos
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS transferencias (
                transferencia_id TEXT PRIMARY KEY,
                modulo_origen TEXT NOT NULL,
                modulo_destino TEXT NOT NULL,
                medio TEXT NOT NULL
                    CHECK (medio IN ('USB', 'WIFI')),
                nombre_archivo TEXT NOT NULL,
                fecha_inicio TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_fin TEXT,
                estado TEXT NOT NULL DEFAULT 'PENDIENTE',
                bytes_totales INTEGER,
                bytes_recibidos INTEGER,
                checksum TEXT,
                error TEXT
            )
        """)


def actualizar_esquema_multi_vina():
    """Prepara la base de datos para trabajar con varias viñas."""

    with conectar() as conexion:


        # 0. Agregar coordenadas geográficas a cada viña
        columnas_vinas = [
            fila[1]
            for fila in conexion.execute(
                "PRAGMA table_info(vinas)"
            ).fetchall()
        ]

        if "latitud" not in columnas_vinas:
            conexion.execute("""
                ALTER TABLE vinas
                ADD COLUMN latitud REAL
            """)

        if "longitud" not in columnas_vinas:
            conexion.execute("""
                ALTER TABLE vinas
                ADD COLUMN longitud REAL
            """)

        # 1. Comprobar las columnas actuales de plantas
        columnas = [
            fila[1]
            for fila in conexion.execute(
                "PRAGMA table_info(plantas)"
            ).fetchall()
        ]

        # 2. Agregar codigo_planta si todavía no existe
        if "codigo_planta" not in columnas:

            conexion.execute("""
                ALTER TABLE plantas
                ADD COLUMN codigo_planta TEXT
            """)

            # Conservar los identificadores históricos
            conexion.execute("""
                UPDATE plantas
                SET codigo_planta = id
                WHERE codigo_planta IS NULL
            """)

        # 3. Crear índice único por viña y código de planta
        conexion.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_plantas_vina_codigo
            ON plantas(vina_id, codigo_planta)
        """)

        # 4. Garantizar que exista la tabla de usuarios
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                usuario_id TEXT PRIMARY KEY,
                vina_id TEXT NOT NULL,
                nombre TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL DEFAULT 'administrador'
                    CHECK (rol IN ('administrador', 'usuario')),
                activo INTEGER NOT NULL DEFAULT 1
                    CHECK (activo IN (0, 1)),
                fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (vina_id) REFERENCES vinas(id)
            )
        """)

        conexion.execute("""
            CREATE INDEX IF NOT EXISTS idx_usuarios_vina
            ON usuarios(vina_id)
        """)


        # 5. Catálogo general de estaciones meteorológicas
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS estaciones_meteorologicas (
                estacion_id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                institucion TEXT,
                codigo_externo TEXT,
                latitud REAL NOT NULL,
                longitud REAL NOT NULL,
                altitud REAL,
                activa INTEGER DEFAULT 1,
                variables_json TEXT DEFAULT '{}',
                fuente_datos TEXT,
                fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Índice geográfico básico para consultar estaciones
        conexion.execute("""
            CREATE INDEX IF NOT EXISTS idx_estaciones_coordenadas
            ON estaciones_meteorologicas(latitud, longitud)
        """)

        # 6. Asociar estaciones meteorológicas a cada viña
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS vinas_estaciones (
                asociacion_id TEXT PRIMARY KEY,
                vina_id TEXT NOT NULL,
                estacion_id TEXT NOT NULL,
                distancia_km REAL,
                principal INTEGER DEFAULT 0,
                fecha_asociacion TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (vina_id) REFERENCES vinas(id),
                FOREIGN KEY (estacion_id)
                    REFERENCES estaciones_meteorologicas(estacion_id),

                UNIQUE (vina_id, estacion_id)
            )
        """)

        conexion.execute("""
            CREATE INDEX IF NOT EXISTS idx_vinas_estaciones_vina
            ON vinas_estaciones(vina_id)
        """)

        # 7. Registros meteorológicos diarios por estación
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS mediciones_meteorologicas (
                medicion_id TEXT PRIMARY KEY,
                estacion_id TEXT NOT NULL,
                fecha TEXT NOT NULL,
                temperatura_min REAL,
                temperatura_max REAL,
                humedad_relativa REAL,
                precipitacion REAL,
                radiacion_solar REAL,
                velocidad_viento REAL,
                fuente_datos TEXT,
                fecha_importacion TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (estacion_id)
                    REFERENCES estaciones_meteorologicas(estacion_id),

                UNIQUE (estacion_id, fecha)
            )
        """)

        conexion.execute("""
            CREATE INDEX IF NOT EXISTS idx_mediciones_meteo_fecha
            ON mediciones_meteorologicas(fecha)
        """)

        # 8. Informes de precipitación de la DMC
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS mediciones_dmc_precipitacion (
                registro_id TEXT PRIMARY KEY,
                estacion_id TEXT NOT NULL,
                fecha_informe TEXT NOT NULL,
                inicio_utc TEXT,
                termino_utc TEXT,
                tipo_registro TEXT NOT NULL
                    CHECK (tipo_registro IN ('horario', 'acumulado')),
                periodo TEXT NOT NULL,
                precipitacion_mm REAL,
                estado TEXT NOT NULL,
                observaciones INTEGER,
                fuente_datos TEXT DEFAULT 'DMC',
                fecha_importacion TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (estacion_id)
                    REFERENCES estaciones_meteorologicas(estacion_id),

                UNIQUE (
                    estacion_id,
                    fecha_informe,
                    tipo_registro,
                    periodo
                )
            )
        """)

        conexion.execute("""
            CREATE INDEX IF NOT EXISTS idx_dmc_precipitacion_periodo
            ON mediciones_dmc_precipitacion(
                estacion_id,
                inicio_utc,
                termino_utc
            )
        """)

        # 9. Informes de precipitación acumulada DMC RE1034
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS mediciones_dmc_re1034 (
                registro_id TEXT PRIMARY KEY,
                estacion_id TEXT NOT NULL,
                fecha_informe TEXT NOT NULL,
                periodo TEXT NOT NULL,
                fecha_referencia TEXT,
                precipitacion_mm REAL,
                estado TEXT NOT NULL,
                fuente_datos TEXT DEFAULT 'DMC RE1034',
                fecha_importacion TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (estacion_id)
                    REFERENCES estaciones_meteorologicas(estacion_id),

                UNIQUE (
                    estacion_id,
                    fecha_informe,
                    periodo
                )
            )
        """)

        conexion.execute("""
            CREATE INDEX IF NOT EXISTS idx_dmc_re1034_estacion_fecha
            ON mediciones_dmc_re1034(
                estacion_id,
                fecha_informe
            )
        """)



def registrar_modulo(
    device_id,
    vina_id,
    modelo,
    tipo_modulo
):
    """Registra un módulo sin permitir cambiarlo de viña."""

    tipos_validos = [
        "CAMARA_SENSOR",
        "REPETIDOR",
        "BASE"
    ]

    if tipo_modulo not in tipos_validos:
        raise ValueError("Tipo de módulo no válido.")

    with conectar() as conexion:

        vina = conexion.execute("""
            SELECT id
            FROM vinas
            WHERE id = ?
        """, (vina_id,)).fetchone()

        if vina is None:
            raise ValueError("La viña indicada no existe.")

        dispositivo = conexion.execute("""
            SELECT vina_id
            FROM dispositivos
            WHERE device_id = ?
        """, (device_id,)).fetchone()

        if dispositivo is not None:
            if dispositivo[0] != vina_id:
                raise ValueError(
                    "Este dispositivo ya pertenece a otra viña."
                )

            conexion.execute("""
                UPDATE dispositivos
                SET modelo = ?,
                    tipo_modulo = ?
                WHERE device_id = ?
                AND vina_id = ?
            """, (modelo, tipo_modulo, device_id, vina_id))

        else:
            conexion.execute("""
                INSERT INTO dispositivos (
                    device_id,
                    vina_id,
                    modelo,
                    tipo_modulo
                )
                VALUES (?, ?, ?, ?)
            """, (
                device_id,
                vina_id,
                modelo,
                tipo_modulo
            ))


def registrar_imagen(
    measurement_id,
    ruta_archivo,
    tipo_imagen="ORIGINAL",
    vina_id="VINA001"
):
    """Registra una fotografía verificando la propiedad de la medición."""

    image_id = str(uuid.uuid4())

    with conectar() as conexion:

        medicion = conexion.execute("""
            SELECT m.measurement_id
            FROM mediciones m
            JOIN plantas p ON m.plant_id = p.id
            WHERE m.measurement_id = ?
            AND p.vina_id = ?
        """, (measurement_id, vina_id)).fetchone()

        if medicion is None:
            raise ValueError(
                "La medición no pertenece a la viña indicada."
            )

        conexion.execute("""
            INSERT INTO imagenes (
                image_id,
                measurement_id,
                ruta_archivo,
                tipo_imagen
            )
            VALUES (?, ?, ?, ?)
        """, (
            image_id,
            measurement_id,
            ruta_archivo,
            tipo_imagen
        ))

    return image_id


def consultar_imagenes_por_planta(plant_id, vina_id="VINA001"):
    """Obtiene fotografías de una planta perteneciente a una viña."""

    with conectar() as conexion:

        resultados = conexion.execute("""
            SELECT
                i.image_id,
                i.ruta_archivo,
                i.tipo_imagen,
                i.fecha_subida,
                i.measurement_id,
                i.fecha_hora,
                i.plant_id
            FROM vista_imagenes_origen i
            
            WHERE i.plant_id = ?
            AND i.vina_id = ?
            ORDER BY i.fecha_hora DESC
        """, (plant_id, vina_id)).fetchall()

    return resultados

def consultar_todas_las_imagenes(vina_id="VINA001"):
    """Obtiene todas las fotografías de una viña."""

    with conectar() as conexion:

        resultados = conexion.execute("""
            SELECT
                i.image_id,
                i.ruta_archivo,
                i.tipo_imagen,
                i.fecha_subida,
                i.measurement_id,
                i.fecha_hora,
                i.plant_id,
                i.cuartel,
                i.variedad,
                i.fila,
                i.numero_planta
            FROM vista_imagenes_origen i
            
            WHERE i.vina_id = ?
            ORDER BY i.fecha_hora DESC
        """, (vina_id,)).fetchall()

    return resultados

def guardar_analisis_imagen(
    image_id,
    modelo,
    version_modelo,
    cantidad_racimos,
    porcentaje_verde,
    porcentaje_envero,
    porcentaje_morado,
    etapa_fenologica,
    confianza,
    resultado_json="{}",
    vina_id="VINA001"
):
    """Guarda un análisis verificando la propiedad de la fotografía."""

    analisis_id = str(uuid.uuid4())

    with conectar() as conexion:

        imagen = conexion.execute("""
            SELECT i.image_id
            FROM vista_imagenes_origen i
            
            WHERE i.image_id = ?
            AND i.vina_id = ?
        """, (image_id, vina_id)).fetchone()

        if imagen is None:
            raise ValueError(
                "La fotografía no pertenece a la viña indicada."
            )

        conexion.execute("""
            INSERT INTO analisis_imagenes (
                analisis_id,
                image_id,
                modelo,
                version_modelo,
                cantidad_racimos,
                porcentaje_verde,
                porcentaje_envero,
                porcentaje_morado,
                etapa_fenologica,
                confianza,
                resultado_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            analisis_id,
            image_id,
            modelo,
            version_modelo,
            cantidad_racimos,
            porcentaje_verde,
            porcentaje_envero,
            porcentaje_morado,
            etapa_fenologica,
            confianza,
            resultado_json
        ))

    return analisis_id


def consultar_analisis_por_imagen(image_id, vina_id="VINA001"):
    """Consulta análisis de fotografías pertenecientes a una viña."""

    with conectar() as conexion:

        resultados = conexion.execute("""
            SELECT
                a.analisis_id,
                a.image_id,
                a.modelo,
                a.version_modelo,
                a.cantidad_racimos,
                a.porcentaje_verde,
                a.porcentaje_envero,
                a.porcentaje_morado,
                a.etapa_fenologica,
                a.confianza,
                a.resultado_json,
                a.fecha_analisis
            FROM analisis_imagenes a
            JOIN vista_imagenes_origen i
                ON a.image_id = i.image_id
            
            WHERE a.image_id = ?
            AND i.vina_id = ?
            ORDER BY a.fecha_analisis DESC
        """, (image_id, vina_id)).fetchall()

    return resultados


def consultar_estaciones_cercanas(vina_id):
    """
    Devuelve las estaciones activas ordenadas por distancia
    respecto de las coordenadas de una viña.
    No modifica la base de datos.
    """
    import math

    with conectar() as conexion:
        vina = conexion.execute("""
            SELECT latitud, longitud
            FROM vinas
            WHERE id = ?
        """, (vina_id,)).fetchone()

        if vina is None:
            raise ValueError("La viña indicada no existe.")

        if vina[0] is None or vina[1] is None:
            raise ValueError(
                "La viña todavía no tiene coordenadas registradas."
            )

        estaciones = conexion.execute("""
            SELECT
                estacion_id,
                nombre,
                institucion,
                latitud,
                longitud,
                altitud,
                variables_json,
                fuente_datos
            FROM estaciones_meteorologicas
            WHERE activa = 1
        """).fetchall()

    lat1, lon1 = map(math.radians, vina)
    resultados = []

    for estacion in estaciones:
        lat2 = math.radians(estacion[3])
        lon2 = math.radians(estacion[4])

        diferencia_lat = lat2 - lat1
        diferencia_lon = lon2 - lon1

        a = (
            math.sin(diferencia_lat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2)
            * math.sin(diferencia_lon / 2) ** 2
        )

        distancia = 6371.0088 * 2 * math.asin(
            math.sqrt(a)
        )

        resultados.append({
            "estacion_id": estacion[0],
            "nombre": estacion[1],
            "institucion": estacion[2],
            "distancia_km": round(distancia, 2),
            "altitud": estacion[5],
            "variables_json": estacion[6],
            "fuente_datos": estacion[7]
        })

    resultados.sort(key=lambda x: x["distancia_km"])

    return resultados


def consultar_mediciones_meteorologicas(
    estacion_id,
    fecha_inicio=None,
    fecha_fin=None
):
    """
    Consulta el historial meteorológico de una estación.
    Permite filtrar por fecha inicial y final.
    No modifica la base de datos.
    """

    consulta = """
        SELECT
            fecha,
            temperatura_min,
            temperatura_max,
            humedad_relativa,
            precipitacion,
            radiacion_solar,
            velocidad_viento,
            fuente_datos
        FROM mediciones_meteorologicas
        WHERE estacion_id = ?
    """

    parametros = [estacion_id]

    if fecha_inicio:
        consulta += " AND fecha >= ?"
        parametros.append(fecha_inicio)

    if fecha_fin:
        consulta += " AND fecha <= ?"
        parametros.append(fecha_fin)

    consulta += " ORDER BY fecha ASC"

    with conectar() as conexion:
        resultados = conexion.execute(
            consulta,
            parametros
        ).fetchall()

    return [
        {
            "fecha": fila[0],
            "temperatura_min": fila[1],
            "temperatura_max": fila[2],
            "humedad_relativa": fila[3],
            "precipitacion": fila[4],
            "radiacion_solar": fila[5],
            "velocidad_viento": fila[6],
            "fuente_datos": fila[7]
        }
        for fila in resultados
    ]


def registrar_estacion_meteorologica(
    estacion_id,
    nombre,
    institucion,
    codigo_externo,
    latitud,
    longitud,
    altitud=None,
    fuente_datos="DMC"
):
    """
    Registra una estación meteorológica si todavía no existe.
    No sobrescribe estaciones previamente registradas.
    """

    with conectar() as conexion:
        cursor = conexion.execute("""
            INSERT OR IGNORE INTO estaciones_meteorologicas (
                estacion_id,
                nombre,
                institucion,
                codigo_externo,
                latitud,
                longitud,
                altitud,
                activa,
                fuente_datos
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            estacion_id,
            nombre,
            institucion,
            codigo_externo,
            latitud,
            longitud,
            altitud,
            fuente_datos
        ))

    return cursor.rowcount == 1


def guardar_informe_dmc_precipitacion(informe, estacion_id):
    """
    Guarda las 24 mediciones horarias y los acumulados
    de un informe de precipitación DMC.

    Los intervalos horarios se construyen según las
    etiquetas del informe y sus límites UTC.
    """

    from datetime import datetime, timedelta

    fecha_iso = datetime.strptime(
        informe["fecha_solicitada"],
        "%d-%m-%Y"
    ).strftime("%Y-%m-%d")

    inicio = datetime.fromisoformat(informe["inicio_utc"])
    termino = datetime.fromisoformat(informe["termino_utc"])

    mediciones = informe["precipitacion_horaria"]

    if len(mediciones) != 24:
        raise ValueError(
            "El informe DMC debe contener exactamente 24 horas."
        )

    inicio_esperado = termino - timedelta(
        hours=23,
        minutes=59
    )

    if inicio != inicio_esperado:
        raise ValueError(
            "Los límites UTC del informe no coinciden con "
            "los 24 intervalos horarios esperados."
        )

    registros = []

    # 1. Mediciones horarias
    for i, dato in enumerate(mediciones):

        fin = termino - timedelta(hours=23 - i)
        desde = fin - timedelta(minutes=59)

        hora = str(dato["hora_informe"]).zfill(2)

        if fin.strftime("%H") != hora:
            raise ValueError(
                f"La etiqueta horaria {hora} no coincide "
                "con el intervalo UTC calculado."
            )

        periodo = f"hora_{hora}"

        registro_id = (
            f"{estacion_id}_{fecha_iso}_horario_{periodo}"
        )

        registros.append((
            registro_id,
            estacion_id,
            fecha_iso,
            desde.isoformat(),
            fin.isoformat(),
            "horario",
            periodo,
            dato.get("valor_mm"),
            dato.get("estado", "no_disponible"),
            dato.get("observaciones"),
            "DMC"
        ))

    # 2. Acumulados del informe
    for periodo, dato in informe["acumulados"].items():

        registro_id = (
            f"{estacion_id}_{fecha_iso}_acumulado_{periodo}"
        )

        registros.append((
            registro_id,
            estacion_id,
            fecha_iso,
            None,
            None,
            "acumulado",
            periodo,
            dato.get("valor_mm"),
            dato.get("estado", "no_disponible"),
            dato.get("observaciones"),
            "DMC"
        ))

    # 3. Guardar o actualizar registros sin duplicarlos
    with conectar() as conexion:

        conexion.executemany("""
            INSERT INTO mediciones_dmc_precipitacion (
                registro_id,
                estacion_id,
                fecha_informe,
                inicio_utc,
                termino_utc,
                tipo_registro,
                periodo,
                precipitacion_mm,
                estado,
                observaciones,
                fuente_datos
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT (
                estacion_id,
                fecha_informe,
                tipo_registro,
                periodo
            )
            DO UPDATE SET
                inicio_utc = excluded.inicio_utc,
                termino_utc = excluded.termino_utc,
                precipitacion_mm = excluded.precipitacion_mm,
                estado = excluded.estado,
                observaciones = excluded.observaciones,
                fuente_datos = excluded.fuente_datos,
                fecha_importacion = CURRENT_TIMESTAMP
        """, registros)

    return {
        "estacion_id": estacion_id,
        "fecha": fecha_iso,
        "registros_guardados": len(registros),
        "horarios": len(mediciones),
        "acumulados": len(informe["acumulados"])
    }



def consultar_mediciones_dmc_precipitacion(
    estacion_id,
    fecha_inicio=None,
    fecha_fin=None,
    tipo_registro=None
):
    """
    Consulta precipitaciones DMC por estación,
    rango de fechas y tipo de registro.

    Tipos: horario o acumulado.
    No modifica la base de datos.
    """

    consulta = """
        SELECT
            fecha_informe,
            inicio_utc,
            termino_utc,
            tipo_registro,
            periodo,
            precipitacion_mm,
            estado,
            observaciones,
            fuente_datos
        FROM mediciones_dmc_precipitacion
        WHERE estacion_id = ?
    """

    parametros = [estacion_id]

    if fecha_inicio:
        consulta += " AND fecha_informe >= ?"
        parametros.append(fecha_inicio)

    if fecha_fin:
        consulta += " AND fecha_informe <= ?"
        parametros.append(fecha_fin)

    if tipo_registro:
        if tipo_registro not in ("horario", "acumulado"):
            raise ValueError(
                "El tipo debe ser 'horario' o 'acumulado'."
            )

        consulta += " AND tipo_registro = ?"
        parametros.append(tipo_registro)

    consulta += """
        ORDER BY fecha_informe ASC,
        CASE tipo_registro
            WHEN 'horario' THEN 1
            WHEN 'acumulado' THEN 2
        END,
        inicio_utc ASC,
        periodo ASC
    """

    with conectar() as conexion:
        resultados = conexion.execute(
            consulta,
            parametros
        ).fetchall()

    return [
        {
            "fecha_informe": fila[0],
            "inicio_utc": fila[1],
            "termino_utc": fila[2],
            "tipo_registro": fila[3],
            "periodo": fila[4],
            "precipitacion_mm": fila[5],
            "estado": fila[6],
            "observaciones": fila[7],
            "fuente_datos": fila[8]
        }
        for fila in resultados
    ]


if __name__ == "__main__":
    inicializar_bd()

    print("Base de datos inicializada correctamente.")
    print("Tablas:", consultar_tablas())
    print("Viñas registradas:", consultar_vinas())


def guardar_informe_dmc_re1034(informe, catalogo_estaciones):
    """
    Guarda las estaciones DMC del informe RE1034 y sus siete
    mediciones por estación, utilizando el catálogo RE7001.

    Las estaciones de otros propietarios se excluyen.
    Los registros existentes se actualizan sin duplicarse.
    """

    import math
    from datetime import date

    periodos_esperados = {
        "24Hrs",
        "48Hrs",
        "72Hrs",
        "96Hrs",
        "120Hrs",
        "144Hrs",
        "total_anual"
    }

    estados_validos = {
        "numerico",
        "s/p",
        "no_disponible",
        "no_reconocido"
    }

    fecha_informe = informe.get("fecha_informe")

    try:
        date.fromisoformat(fecha_informe)
    except (TypeError, ValueError):
        raise ValueError("La fecha del informe RE1034 no es válida.")

    estaciones_informe = informe.get("estaciones")

    if not isinstance(estaciones_informe, list) or not estaciones_informe:
        raise ValueError("El informe RE1034 no contiene estaciones.")

    if informe.get("cantidad_estaciones") != len(estaciones_informe):
        raise ValueError(
            "La cantidad declarada de estaciones no coincide "
            "con los registros recibidos."
        )

    codigos_vistos = set()
    estaciones_para_guardar = []
    mediciones_para_guardar = []

    for estacion in estaciones_informe:

        codigo = estacion.get("codigo")

        if not codigo or codigo in codigos_vistos:
            raise ValueError(
                f"Código de estación ausente o duplicado: {codigo}"
            )

        codigos_vistos.add(codigo)

        datos_catalogo = catalogo_estaciones.get(codigo)

        if datos_catalogo is None:
            raise ValueError(
                f"La estación {codigo} no aparece en RE7001."
            )

        propietario = datos_catalogo.get("propietario", "").strip()

        # Excluir estaciones que no pertenecen a la DMC.
        if propietario != "Dirección Meteorológica de Chile":
            continue

        estacion_id = f"DMC_{codigo}"

        registros = estacion.get("registros", [])

        periodos_recibidos = [
            registro.get("periodo")
            for registro in registros
        ]

        if (
            len(registros) != 7
            or set(periodos_recibidos) != periodos_esperados
            or len(set(periodos_recibidos)) != 7
        ):
            raise ValueError(
                f"La estación {codigo} no contiene exactamente "
                "las siete ventanas RE1034 esperadas."
            )

        estaciones_para_guardar.append({
            "estacion_id": estacion_id,
            "nombre": datos_catalogo["nombre"],
            "institucion": propietario,
            "codigo_externo": codigo,
            "latitud": datos_catalogo["latitud"],
            "longitud": datos_catalogo["longitud"],
            "altitud": datos_catalogo["altitud"]
        })

        for registro in registros:

            periodo = registro["periodo"]
            estado = registro.get("estado")
            valor = registro.get("precipitacion_mm")
            fecha_referencia = registro.get("fecha_referencia")

            if estado not in estados_validos:
                raise ValueError(
                    f"Estado no reconocido en estación {codigo}: {estado}"
                )

            if estado == "numerico":

                if (
                    isinstance(valor, bool)
                    or not isinstance(valor, (int, float))
                    or not math.isfinite(valor)
                    or valor < 0
                ):
                    raise ValueError(
                        f"Valor numérico inválido en estación "
                        f"{codigo}, período {periodo}."
                    )

                valor = float(valor)

            elif valor is not None:
                raise ValueError(
                    f"El período {periodo} de la estación {codigo} "
                    "tiene un valor numérico incompatible con su estado."
                )

            if periodo == "total_anual":

                if fecha_referencia is not None:
                    raise ValueError(
                        "El total anual no debe tener fecha de referencia."
                    )

            else:

                try:
                    date.fromisoformat(fecha_referencia)
                except (TypeError, ValueError):
                    raise ValueError(
                        f"Fecha de referencia inválida en "
                        f"estación {codigo}, período {periodo}."
                    )

            registro_id = (
                f"DMC_RE1034_{codigo}_{fecha_informe}_{periodo}"
            )

            mediciones_para_guardar.append((
                registro_id,
                estacion_id,
                fecha_informe,
                periodo,
                fecha_referencia,
                valor,
                estado,
                "DMC RE1034"
            ))

    if not estaciones_para_guardar:
        raise ValueError(
            "No se encontraron estaciones propiedad de la DMC "
            "para guardar."
        )

    # Registrar estaciones y mediciones en una sola transacción.
    estaciones_nuevas = 0

    with conectar() as conexion:

        for estacion in estaciones_para_guardar:

            codigo = estacion["codigo_externo"]
            estacion_id = estacion["estacion_id"]

            existente = conexion.execute("""
                SELECT estacion_id
                FROM estaciones_meteorologicas
                WHERE codigo_externo = ?
            """, (codigo,)).fetchone()

            if existente and existente[0] != estacion_id:
                raise ValueError(
                    f"El código {codigo} ya está asociado a otra "
                    "estación. Se cancela la importación para "
                    "evitar duplicados."
                )

            cursor = conexion.execute("""
                INSERT OR IGNORE INTO estaciones_meteorologicas (
                    estacion_id,
                    nombre,
                    institucion,
                    codigo_externo,
                    latitud,
                    longitud,
                    altitud,
                    activa,
                    fuente_datos
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'DMC')
            """, (
                estacion_id,
                estacion["nombre"],
                estacion["institucion"],
                codigo,
                estacion["latitud"],
                estacion["longitud"],
                estacion["altitud"]
            ))

            estaciones_nuevas += max(cursor.rowcount, 0)

            # Verificar que la estación quedó registrada.
            verificacion = conexion.execute("""
                SELECT codigo_externo
                FROM estaciones_meteorologicas
                WHERE estacion_id = ?
            """, (estacion_id,)).fetchone()

            if not verificacion or verificacion[0] != codigo:
                raise ValueError(
                    f"No se pudo verificar el registro de "
                    f"la estación {codigo}."
                )

        conexion.executemany("""
            INSERT INTO mediciones_dmc_re1034 (
                registro_id,
                estacion_id,
                fecha_informe,
                periodo,
                fecha_referencia,
                precipitacion_mm,
                estado,
                fuente_datos
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT (
                estacion_id,
                fecha_informe,
                periodo
            )
            DO UPDATE SET
                fecha_referencia = excluded.fecha_referencia,
                precipitacion_mm = excluded.precipitacion_mm,
                estado = excluded.estado,
                fuente_datos = excluded.fuente_datos,
                fecha_importacion = CURRENT_TIMESTAMP
        """, mediciones_para_guardar)

    return {
        "fecha_informe": fecha_informe,
        "estaciones_dmc": len(estaciones_para_guardar),
        "estaciones_nuevas": estaciones_nuevas,
        "estaciones_excluidas": (
            len(estaciones_informe) - len(estaciones_para_guardar)
        ),
        "registros_procesados": len(mediciones_para_guardar)
    }


def consultar_mediciones_dmc_re1034(
    estacion_id,
    fecha_inicio=None,
    fecha_fin=None
):
    """
    Consulta mediciones RE1034 de una estación y rango de fechas.
    No modifica la base de datos.
    """

    from datetime import date

    for nombre, valor in (
        ("fecha_inicio", fecha_inicio),
        ("fecha_fin", fecha_fin)
    ):
        if valor is not None:
            try:
                date.fromisoformat(valor)
            except (TypeError, ValueError):
                raise ValueError(f"{nombre} no tiene formato YYYY-MM-DD.")

    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        raise ValueError(
            "La fecha inicial no puede ser posterior a la fecha final."
        )

    consulta = """
        SELECT
            registro_id,
            estacion_id,
            fecha_informe,
            periodo,
            fecha_referencia,
            precipitacion_mm,
            estado,
            fuente_datos,
            fecha_importacion
        FROM mediciones_dmc_re1034
        WHERE estacion_id = ?
    """

    parametros = [estacion_id]

    if fecha_inicio:
        consulta += " AND fecha_informe >= ?"
        parametros.append(fecha_inicio)

    if fecha_fin:
        consulta += " AND fecha_informe <= ?"
        parametros.append(fecha_fin)

    consulta += """
        ORDER BY fecha_informe DESC,
        CASE periodo
            WHEN '24Hrs' THEN 1
            WHEN '48Hrs' THEN 2
            WHEN '72Hrs' THEN 3
            WHEN '96Hrs' THEN 4
            WHEN '120Hrs' THEN 5
            WHEN '144Hrs' THEN 6
            WHEN 'total_anual' THEN 7
        END
    """

    with conectar() as conexion:
        resultados = conexion.execute(
            consulta,
            parametros
        ).fetchall()

    columnas = [
        "registro_id",
        "estacion_id",
        "fecha_informe",
        "periodo",
        "fecha_referencia",
        "precipitacion_mm",
        "estado",
        "fuente_datos",
        "fecha_importacion"
    ]

    return [
        dict(zip(columnas, fila))
        for fila in resultados
    ]


# =========================================================
# CLAROS MONITOREADOS
# =========================================================

def guardar_claro_monitoreado(
    vina_id,
    cuartel,
    plant_ids,
    usuario_id
):
    """
    Configura el único claro monitoreado de un cuartel.

    Solo administradores activos de la viña.
    Exige exactamente seis plantas distintas.
    Guarda toda la configuración en una transacción.
    """

    if not isinstance(vina_id, str) or not vina_id.strip():
        raise ValueError("La viña es obligatoria.")

    if not isinstance(cuartel, str) or not cuartel.strip():
        raise ValueError("El cuartel es obligatorio.")

    if not isinstance(plant_ids, (list, tuple)):
        raise ValueError(
            "Debes seleccionar una lista de seis plantas."
        )

    if len(plant_ids) != 6:
        raise ValueError(
            "El claro debe contener exactamente seis plantas."
        )

    if any(
        not isinstance(plant_id, str) or not plant_id.strip()
        for plant_id in plant_ids
    ):
        raise ValueError(
            "Todos los identificadores deben ser válidos."
        )

    if len(set(plant_ids)) != 6:
        raise ValueError(
            "No puedes repetir plantas dentro del claro."
        )

    with conectar() as conexion:

        conexion.execute("BEGIN IMMEDIATE")

        verificar_administrador_vina(
            conexion,
            usuario_id,
            vina_id
        )

        plantas_validas = conexion.execute("""
            SELECT id
            FROM plantas
            WHERE vina_id = ?
              AND cuartel = ?
              AND id IN (?, ?, ?, ?, ?, ?)
        """, (
            vina_id,
            cuartel,
            *plant_ids
        )).fetchall()

        if len(plantas_validas) != 6:
            raise ValueError(
                "Las seis plantas deben pertenecer "
                "a la viña y al cuartel seleccionados."
            )

        claro = conexion.execute("""
            SELECT claro_id
            FROM claros_monitoreados
            WHERE vina_id = ?
              AND cuartel = ?
        """, (
            vina_id,
            cuartel
        )).fetchone()

        if claro is None:

            cursor = conexion.execute("""
                INSERT INTO claros_monitoreados (
                    vina_id,
                    cuartel
                )
                VALUES (?, ?)
            """, (
                vina_id,
                cuartel
            ))

            claro_id = cursor.lastrowid

        else:

            claro_id = claro[0]

            conexion.execute("""
                DELETE FROM claro_plantas
                WHERE claro_id = ?
            """, (claro_id,))

        for posicion, plant_id in enumerate(
            plant_ids,
            start=1
        ):
            conexion.execute("""
                INSERT INTO claro_plantas (
                    claro_id,
                    posicion,
                    plant_id
                )
                VALUES (?, ?, ?)
            """, (
                claro_id,
                posicion,
                plant_id
            ))

    return claro_id


def consultar_claro_monitoreado(vina_id, cuartel):
    """
    Consulta las plantas del claro de un cuartel.

    Devuelve una lista vacía cuando no existe
    una configuración completa de seis plantas.
    """

    with conectar() as conexion:

        filas = conexion.execute("""
            SELECT
                cp.posicion,
                p.id,
                p.codigo_planta,
                p.cuartel,
                p.variedad,
                p.fila,
                p.numero_planta
            FROM claros_monitoreados c
            JOIN claro_plantas cp
                ON cp.claro_id = c.claro_id
            JOIN plantas p
                ON p.id = cp.plant_id
               AND p.vina_id = c.vina_id
               AND p.cuartel = c.cuartel
            WHERE c.vina_id = ?
              AND c.cuartel = ?
            ORDER BY cp.posicion
        """, (
            vina_id,
            cuartel
        )).fetchall()

    if len(filas) != 6:
        return []

    return filas


def actualizar_esquema_claros():
    """
    Crea las estructuras de claros monitoreados.

    La migración es idempotente y conserva los datos
    existentes. Cada cuartel puede tener un claro
    con hasta seis posiciones configuradas.
    """

    with conectar() as conexion:

        conexion.execute("BEGIN IMMEDIATE")

        conexion.execute("""
            CREATE TABLE IF NOT EXISTS claros_monitoreados (
                claro_id INTEGER PRIMARY KEY AUTOINCREMENT,
                vina_id TEXT NOT NULL,
                cuartel TEXT NOT NULL,
                fecha_configuracion TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(vina_id, cuartel),
                FOREIGN KEY (vina_id) REFERENCES vinas(id)
            )
        """)

        conexion.execute("""
            CREATE TABLE IF NOT EXISTS claro_plantas (
                claro_id INTEGER NOT NULL,
                posicion INTEGER NOT NULL
                    CHECK (posicion BETWEEN 1 AND 6),
                plant_id TEXT NOT NULL,
                PRIMARY KEY (claro_id, posicion),
                UNIQUE(claro_id, plant_id),
                FOREIGN KEY (claro_id)
                    REFERENCES claros_monitoreados(claro_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (plant_id)
                    REFERENCES plantas(id)
            )
        """)

        conexion.execute("""
            CREATE TRIGGER IF NOT EXISTS validar_planta_claro
            BEFORE INSERT ON claro_plantas
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'La planta no pertenece al cuartel y viña del claro'
                )
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM plantas p
                    JOIN claros_monitoreados c
                        ON c.claro_id = NEW.claro_id
                    WHERE p.id = NEW.plant_id
                      AND p.vina_id = c.vina_id
                      AND p.cuartel = c.cuartel
                );
            END
        """)

        conexion.execute("""
            CREATE TRIGGER IF NOT EXISTS validar_actualizacion_planta_claro
            BEFORE UPDATE ON claro_plantas
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'La planta no pertenece al cuartel y viña del claro'
                )
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM plantas p
                    JOIN claros_monitoreados c
                        ON c.claro_id = NEW.claro_id
                    WHERE p.id = NEW.plant_id
                      AND p.vina_id = c.vina_id
                      AND p.cuartel = c.cuartel
                );
            END
        """)

        conexion.execute("""
            CREATE TRIGGER IF NOT EXISTS proteger_planta_claro
            BEFORE UPDATE OF vina_id, cuartel ON plantas
            WHEN EXISTS (
                SELECT 1
                FROM claro_plantas cp
                JOIN claros_monitoreados c
                    ON c.claro_id = cp.claro_id
                WHERE cp.plant_id = OLD.id
                  AND (
                      NEW.vina_id IS NOT c.vina_id
                      OR NEW.cuartel IS NOT c.cuartel
                  )
            )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'No se puede trasladar una planta asignada a un claro'
                );
            END
        """)

        conexion.execute("""
            CREATE TRIGGER IF NOT EXISTS proteger_cuartel_claro
            BEFORE UPDATE OF vina_id, cuartel
            ON claros_monitoreados
            WHEN EXISTS (
                SELECT 1
                FROM claro_plantas
                WHERE claro_id = OLD.claro_id
            )
            AND (
                NEW.vina_id IS NOT OLD.vina_id
                OR NEW.cuartel IS NOT OLD.cuartel
            )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'No se puede trasladar un claro con plantas asignadas'
                );
            END
        """)

        conexion.execute("""
            CREATE TRIGGER IF NOT EXISTS proteger_eliminacion_planta_claro
            BEFORE DELETE ON plantas
            WHEN EXISTS (
                SELECT 1
                FROM claro_plantas
                WHERE plant_id = OLD.id
            )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'No se puede eliminar una planta asignada a un claro'
                );
            END
        """)

        integridad = conexion.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        errores = conexion.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if integridad != "ok" or errores:
            raise RuntimeError(
                "La migración de claros no superó "
                "las comprobaciones de integridad."
            )



def importar_csv_estructural(datos, vina_id, usuario_id):
    """Registra plantas nuevas sin crear mediciones."""

    from validacion_csv_estructural import validar_csv_estructural

    datos = validar_csv_estructural(datos)

    resultado = {
        "plantas_creadas": 0,
        "plantas_omitidas": 0
    }

    with conectar() as conexion:

        conexion.execute("BEGIN IMMEDIATE")

        verificar_administrador_vina(
            conexion,
            usuario_id,
            vina_id
        )

        for _, fila in datos.iterrows():

            codigo = str(fila["id"])

            existente = conexion.execute("""
                SELECT id
                FROM plantas
                WHERE vina_id = ?
                  AND codigo_planta = ?
            """, (vina_id, codigo)).fetchone()

            if existente is not None:
                resultado["plantas_omitidas"] += 1
                continue

            posicion_ocupada = conexion.execute("""
                SELECT codigo_planta
                FROM plantas
                WHERE vina_id = ?
                  AND cuartel = ?
                  AND fila = ?
                  AND numero_planta = ?
            """, (
                vina_id,
                str(fila["cuartel"]),
                int(fila["fila"]),
                int(fila["planta"])
            )).fetchone()

            if posicion_ocupada is not None:
                raise ValueError(
                    f"La posición de {codigo} ya está "
                    f"ocupada por {posicion_ocupada[0]}."
                )

            conexion.execute("""
                INSERT INTO plantas (
                    id, vina_id, codigo_planta,
                    cuartel, variedad, fila,
                    numero_planta, lat, lon
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()),
                vina_id,
                codigo,
                str(fila["cuartel"]),
                str(fila["variedad"]),
                int(fila["fila"]),
                int(fila["planta"]),
                None if pd.isna(fila["lat"])
                else float(fila["lat"]),
                None if pd.isna(fila["lon"])
                else float(fila["lon"])
            ))

            resultado["plantas_creadas"] += 1

    return resultado


def consultar_plantas_registradas(vina_id):
    """Recupera todas las plantas de una viña."""

    conexion = conectar()

    try:
        return pd.read_sql_query("""
            SELECT
                codigo_planta AS id,
                id AS plant_internal_id,
                cuartel,
                variedad,
                fila,
                numero_planta AS planta,
                lat,
                lon
            FROM plantas
            WHERE vina_id = ?
            ORDER BY cuartel, fila, numero_planta,
                     codigo_planta
        """, conexion, params=(vina_id,))

    finally:
        conexion.close()



def actualizar_esquema_capturas_dispositivo():
    """Crea la infraestructura de importaciones ZIP."""

    with conectar() as conexion:

        conexion.execute("BEGIN IMMEDIATE")

        conexion.execute("""
            CREATE TABLE IF NOT EXISTS importaciones_dispositivo (
                importacion_id TEXT PRIMARY KEY,
                vina_id TEXT NOT NULL,
                usuario_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                nombre_archivo TEXT NOT NULL,
                checksum TEXT NOT NULL,
                fecha_importacion TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                cantidad_capturas INTEGER NOT NULL DEFAULT 0
                    CHECK (cantidad_capturas >= 0),
                cantidad_fotografias INTEGER NOT NULL DEFAULT 0
                    CHECK (cantidad_fotografias >= 0),

                FOREIGN KEY (vina_id)
                    REFERENCES vinas(id),

                FOREIGN KEY (usuario_id)
                    REFERENCES usuarios(usuario_id),

                FOREIGN KEY (device_id)
                    REFERENCES dispositivos(device_id),

                UNIQUE (vina_id, checksum)
            )
        """)

        conexion.execute("""
            CREATE TABLE IF NOT EXISTS capturas_dispositivo (
                captura_id TEXT PRIMARY KEY,
                importacion_id TEXT NOT NULL,
                plant_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                fecha_hora TEXT NOT NULL,
                temperatura_ambiental REAL,
                humedad_ambiental REAL
                    CHECK (
                        humedad_ambiental BETWEEN 0 AND 100
                    ),
                tiene_fotografia INTEGER NOT NULL DEFAULT 0
                    CHECK (tiene_fotografia IN (0, 1)),
                datos_json TEXT NOT NULL DEFAULT '{}',
                fecha_importacion TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (importacion_id)
                    REFERENCES importaciones_dispositivo(
                        importacion_id
                    ),

                FOREIGN KEY (plant_id)
                    REFERENCES plantas(id),

                FOREIGN KEY (device_id)
                    REFERENCES dispositivos(device_id)
            )
        """)

        conexion.execute("""
            CREATE INDEX IF NOT EXISTS
                idx_capturas_planta_fecha
            ON capturas_dispositivo(
                plant_id, fecha_hora
            )
        """)

        conexion.execute("""
            CREATE INDEX IF NOT EXISTS
                idx_capturas_dispositivo_fecha
            ON capturas_dispositivo(
                device_id, fecha_hora
            )
        """)

        conexion.execute("""
            CREATE INDEX IF NOT EXISTS
                idx_capturas_importacion
            ON capturas_dispositivo(importacion_id)
        """)

        conexion.execute("""
            CREATE INDEX IF NOT EXISTS
                idx_importaciones_vina_fecha
            ON importaciones_dispositivo(
                vina_id, fecha_importacion
            )
        """)



def actualizar_esquema_imagenes_dispositivo():
    """Permite asociar imágenes a mediciones o capturas."""

    conexion = conectar()

    try:
        columnas = {
            fila[1]: fila
            for fila in conexion.execute(
                "PRAGMA table_info(imagenes)"
            )
        }

        if "captura_id" in columnas:
            if columnas["measurement_id"][3] != 0:
                raise RuntimeError(
                    "La estructura de imágenes es incompatible."
                )

            return False

        if conexion.in_transaction:
            raise RuntimeError(
                "Existe una transacción activa."
            )

        conexion.execute("PRAGMA foreign_keys = OFF")

        conexion.execute("BEGIN IMMEDIATE")

        conexion.execute("""
            CREATE TABLE imagenes_nueva (
                image_id TEXT PRIMARY KEY,
                measurement_id TEXT,
                ruta_archivo TEXT NOT NULL,
                tipo_imagen TEXT,
                fecha_subida TEXT,
                captura_id TEXT,

                FOREIGN KEY (measurement_id)
                    REFERENCES mediciones(measurement_id),

                FOREIGN KEY (captura_id)
                    REFERENCES capturas_dispositivo(captura_id),

                CHECK (
                    (
                        measurement_id IS NOT NULL
                        AND captura_id IS NULL
                    )
                    OR
                    (
                        measurement_id IS NULL
                        AND captura_id IS NOT NULL
                    )
                )
            )
        """)

        conexion.execute("""
            INSERT INTO imagenes_nueva (
                image_id,
                measurement_id,
                ruta_archivo,
                tipo_imagen,
                fecha_subida,
                captura_id
            )
            SELECT
                image_id,
                measurement_id,
                ruta_archivo,
                tipo_imagen,
                fecha_subida,
                NULL
            FROM imagenes
            ORDER BY rowid
        """)

        conexion.execute("DROP TABLE imagenes")

        conexion.execute("""
            ALTER TABLE imagenes_nueva
            RENAME TO imagenes
        """)

        conexion.execute("""
            CREATE INDEX idx_imagenes_medicion
            ON imagenes(measurement_id)
        """)

        conexion.execute("""
            CREATE INDEX idx_imagenes_captura
            ON imagenes(captura_id)
        """)

        errores = conexion.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if errores:
            raise RuntimeError(
                "Se detectaron relaciones inválidas."
            )

        conexion.commit()

        return True

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.execute("PRAGMA foreign_keys = ON")
        conexion.close()



def actualizar_vista_imagenes_origen():
    """Unifica fotografías fenológicas y del dispositivo."""

    with conectar() as conexion:

        conexion.execute("BEGIN IMMEDIATE")

        conexion.execute("""
            DROP VIEW IF EXISTS vista_imagenes_origen
        """)

        conexion.execute("""
            CREATE VIEW vista_imagenes_origen AS

            SELECT
                i.image_id,
                i.ruta_archivo,
                i.tipo_imagen,
                i.fecha_subida,
                i.measurement_id,
                i.captura_id,
                m.fecha_hora,
                p.id AS plant_id,
                p.vina_id,
                p.codigo_planta,
                p.cuartel,
                p.variedad,
                p.fila,
                p.numero_planta,
                'MEDICION_FENOLOGICA' AS origen

            FROM imagenes i

            JOIN mediciones m
                ON i.measurement_id = m.measurement_id

            JOIN plantas p
                ON m.plant_id = p.id

            WHERE i.captura_id IS NULL

            UNION ALL

            SELECT
                i.image_id,
                i.ruta_archivo,
                i.tipo_imagen,
                i.fecha_subida,
                i.measurement_id,
                i.captura_id,
                c.fecha_hora,
                p.id AS plant_id,
                p.vina_id,
                p.codigo_planta,
                p.cuartel,
                p.variedad,
                p.fila,
                p.numero_planta,
                'CAPTURA_DISPOSITIVO' AS origen

            FROM imagenes i

            JOIN capturas_dispositivo c
                ON i.captura_id = c.captura_id

            JOIN plantas p
                ON c.plant_id = p.id

            JOIN importaciones_dispositivo imp
                ON c.importacion_id = imp.importacion_id

            JOIN dispositivos d
                ON c.device_id = d.device_id

            WHERE i.measurement_id IS NULL
              AND p.vina_id = imp.vina_id
              AND p.vina_id = d.vina_id
              AND c.device_id = imp.device_id
        """)



def registrar_imagen_dispositivo(
    captura_id,
    ruta_archivo,
    vina_id,
    usuario_id,
    conexion=None
):
    """Registra una fotografía asociada a una captura."""

    from contextlib import nullcontext

    if not captura_id:
        raise ValueError(
            "Debe indicar una captura válida."
        )

    if not ruta_archivo or not str(ruta_archivo).strip():
        raise ValueError(
            "Debe indicar la ruta de la fotografía."
        )

    image_id = str(uuid.uuid4())

    contexto = (
        conectar()
        if conexion is None
        else nullcontext(conexion)
    )

    with contexto as con:

        if conexion is None:
            con.execute("BEGIN IMMEDIATE")

        verificar_permiso_mediciones(
            con,
            usuario_id,
            vina_id
        )

        captura = con.execute("""
            SELECT
                c.captura_id,
                c.tiene_fotografia

            FROM capturas_dispositivo c

            JOIN plantas p
                ON c.plant_id = p.id

            JOIN importaciones_dispositivo imp
                ON c.importacion_id = imp.importacion_id

            JOIN dispositivos d
                ON c.device_id = d.device_id

            WHERE c.captura_id = ?
              AND p.vina_id = ?
              AND imp.vina_id = ?
              AND d.vina_id = ?
              AND c.device_id = imp.device_id
        """, (
            captura_id,
            vina_id,
            vina_id,
            vina_id
        )).fetchone()

        if captura is None:
            raise ValueError(
                "La captura no existe o no pertenece "
                "a la viña indicada."
            )

        if captura[1] != 1:
            raise ValueError(
                "La captura no declara una fotografía."
            )

        existente = con.execute("""
            SELECT image_id
            FROM imagenes
            WHERE captura_id = ?
              AND ruta_archivo = ?
        """, (
            captura_id,
            str(ruta_archivo)
        )).fetchone()

        if existente is not None:
            raise ValueError(
                "La fotografía ya está registrada "
                "para esta captura."
            )

        con.execute("""
            INSERT INTO imagenes (
                image_id,
                measurement_id,
                captura_id,
                ruta_archivo,
                tipo_imagen,
                fecha_subida
            )
            VALUES (
                ?, NULL, ?, ?, 'ORIGINAL',
                CURRENT_TIMESTAMP
            )
        """, (
            image_id,
            captura_id,
            str(ruta_archivo)
        ))

    return image_id


def registrar_fotografia_manual_segura(
    measurement_id,
    contenido,
    nombre_original,
    vina_id,
    usuario_id
):
    """
    Registra una fotografía manual en el entorno experimental.

    Comprueba permisos, propiedad de la medición,
    contenido fotográfico y almacenamiento protegido.
    """

    from contextlib import closing
    from pathlib import Path
    import hashlib
    import uuid

    from almacenamiento_fotografico import (
        validar_contenido_fotografico,
        validar_carpeta_fotografica,
        guardar_fotografia_protegida
    )

    if not measurement_id:
        raise ValueError(
            "Debe indicar una medición válida."
        )

    if not vina_id or not usuario_id:
        raise PermissionError(
            "No se pudo verificar la autorización."
        )

    validar_contenido_fotografico(
        contenido,
        nombre_original
    )

    fotografia = None
    identidad = None
    image_id = str(uuid.uuid4())

    try:

        with closing(conectar()) as conexion:

            with conexion:

                conexion.execute("BEGIN IMMEDIATE")

                verificar_permiso_mediciones(
                    conexion,
                    usuario_id,
                    vina_id
                )

                medicion = conexion.execute("""
                    SELECT m.measurement_id
                    FROM mediciones m
                    JOIN plantas p
                        ON m.plant_id = p.id
                    WHERE m.measurement_id = ?
                      AND p.vina_id = ?
                """, (
                    measurement_id,
                    vina_id
                )).fetchone()

                if medicion is None:
                    raise ValueError(
                        "La medición no existe o no pertenece "
                        "a la viña indicada."
                    )

                fotografia = guardar_fotografia_protegida(
                    contenido,
                    nombre_original
                )

                ruta = Path(
                    fotografia["ruta_absoluta"]
                )

                carpeta = validar_carpeta_fotografica()

                if (
                    ruta.parent != carpeta
                    or ruta.resolve() != ruta
                    or ruta.is_symlink()
                    or not ruta.is_file()
                    or ruta.stat().st_nlink != 1
                ):
                    raise RuntimeError(
                        "Ruta fotográfica no autorizada."
                    )

                estado = ruta.stat()

                identidad = (
                    estado.st_dev,
                    estado.st_ino
                )

                existente = conexion.execute("""
                    SELECT image_id
                    FROM imagenes
                    WHERE ruta_archivo IN (?, ?)
                """, (
                    fotografia["ruta_relativa"],
                    fotografia["ruta_absoluta"]
                )).fetchone()

                if existente is not None:
                    raise ValueError(
                        "La ruta fotográfica ya está registrada."
                    )

                conexion.execute("""
                    INSERT INTO imagenes (
                        image_id,
                        measurement_id,
                        captura_id,
                        ruta_archivo,
                        tipo_imagen,
                        fecha_subida
                    )
                    VALUES (
                        ?, ?, NULL, ?, 'ORIGINAL',
                        CURRENT_TIMESTAMP
                    )
                """, (
                    image_id,
                    measurement_id,
                    fotografia["ruta_relativa"]
                ))

                registro = conexion.execute("""
                    SELECT
                        measurement_id,
                        captura_id,
                        ruta_archivo
                    FROM imagenes
                    WHERE image_id = ?
                """, (image_id,)).fetchone()

                if (
                    registro is None
                    or tuple(registro) != (
                        measurement_id,
                        None,
                        fotografia["ruta_relativa"]
                    )
                ):
                    raise RuntimeError(
                        "No se pudo verificar el registro."
                    )

    except Exception:

        if fotografia is not None:

            try:

                # Mantener un bloqueo de escritura durante
                # la comprobación y eventual limpieza.

                with closing(conectar()) as revision:

                    with revision:

                        revision.execute("BEGIN IMMEDIATE")

                        registrada = revision.execute("""
                            SELECT image_id
                            FROM imagenes
                            WHERE image_id = ?
                               OR ruta_archivo IN (?, ?)
                        """, (
                            image_id,
                            fotografia["ruta_relativa"],
                            fotografia["ruta_absoluta"]
                        )).fetchone()

                        if registrada is not None:

                            raise RuntimeError(
                                "Existe un registro asociado. "
                                "Se conserva la fotografía."
                            )

                        carpeta = validar_carpeta_fotografica()

                        ruta = Path(
                            fotografia["ruta_absoluta"]
                        )

                        estado = ruta.lstat()

                        if (
                            identidad is None
                            or ruta.parent != carpeta
                            or ruta.resolve() != ruta
                            or ruta.is_symlink()
                            or not ruta.is_file()
                            or estado.st_nlink != 1
                            or (
                                estado.st_dev,
                                estado.st_ino
                            ) != identidad
                            or hashlib.sha256(
                                ruta.read_bytes()
                            ).hexdigest()
                            != fotografia["checksum"]
                        ):
                            raise RuntimeError(
                                "No se pudo verificar la identidad "
                                "de la fotografía para su limpieza."
                            )

                        ruta.unlink()

            except Exception as error_limpieza:

                raise RuntimeError(
                    "El registro requiere revisión manual. "
                    "No se pudo confirmar una limpieza segura."
                ) from error_limpieza

        raise

    return {
        **fotografia,
        "image_id": image_id,
        "measurement_id": measurement_id,
        "vina_id": vina_id,
        "registro_bd_realizado": True
    }


def consultar_capturas_ambientales(
    plant_id, vina_id, usuario_id
):
    """Consulta el historial ambiental de una planta."""

    from contextlib import closing

    with closing(conectar()) as conexion:

        conexion.execute("PRAGMA query_only = ON")

        verificar_permiso_mediciones(
            conexion, usuario_id, vina_id
        )

        filas = conexion.execute("""
            SELECT
                c.captura_id,
                c.fecha_hora,
                c.temperatura_ambiental,
                c.humedad_ambiental,
                c.device_id,
                c.tiene_fotografia
            FROM capturas_dispositivo c
            JOIN plantas p
                ON c.plant_id = p.id
            JOIN importaciones_dispositivo imp
                ON c.importacion_id = imp.importacion_id
            JOIN dispositivos d
                ON c.device_id = d.device_id
            WHERE p.id = ?
              AND p.vina_id = ?
              AND imp.vina_id = p.vina_id
              AND d.vina_id = p.vina_id
              AND imp.device_id = c.device_id
            ORDER BY c.fecha_hora DESC
        """, (plant_id, vina_id)).fetchall()

        columnas = (
            "captura_id",
            "fecha_hora",
            "temperatura_ambiental",
            "humedad_ambiental",
            "device_id",
            "tiene_fotografia"
        )

        return [
            dict(zip(columnas, fila))
            for fila in filas
        ]


def consultar_ambiente_fotografia(
    image_id, vina_id, usuario_id
):
    """Obtiene las condiciones ambientales de una fotografía."""

    from contextlib import closing

    with closing(conectar()) as conexion:

        conexion.execute("PRAGMA query_only = ON")

        verificar_permiso_mediciones(
            conexion, usuario_id, vina_id
        )

        fila = conexion.execute("""
            SELECT
                c.temperatura_ambiental,
                c.humedad_ambiental,
                c.device_id,
                c.fecha_hora
            FROM vista_imagenes_origen i
            JOIN capturas_dispositivo c
                ON i.captura_id = c.captura_id
            WHERE i.image_id = ?
              AND i.vina_id = ?
              AND i.origen = 'CAPTURA_DISPOSITIVO'
        """, (image_id, vina_id)).fetchone()

        if fila is None:
            return None

        return dict(zip((
            "temperatura_ambiental",
            "humedad_ambiental",
            "device_id",
            "fecha_hora"
        ), fila))
