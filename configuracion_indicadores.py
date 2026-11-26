
import math
from contextlib import closing

from database import (
    conectar,
    verificar_administrador_vina,
    verificar_permiso_mediciones
)


INDICADORES = {
    "ndvi": "NDVI (vigor)",
    "hum": "Humedad de suelo",
    "psi": "Potencial hídrico",
    "brix": "Grados Brix",
    "rend": "Rendimiento estimado"
}


def inicializar_configuracion_indicadores():

    with closing(conectar()) as conexion:
        with conexion:
            conexion.execute("""
                CREATE TABLE IF NOT EXISTS configuracion_indicadores (
                    vina_id TEXT NOT NULL,
                    parametro TEXT NOT NULL
                        CHECK (parametro IN (
                            'ndvi', 'hum', 'psi', 'brix', 'rend'
                        )),
                    variedad TEXT NOT NULL DEFAULT '',
                    etapa_fenologica TEXT NOT NULL DEFAULT '',
                    valor_minimo REAL,
                    valor_maximo REAL,
                    alerta_activa INTEGER NOT NULL DEFAULT 0
                        CHECK (alerta_activa IN (0, 1)),
                    actualizado_por TEXT NOT NULL,
                    fecha_actualizacion TEXT
                        DEFAULT CURRENT_TIMESTAMP,

                    PRIMARY KEY (
                        vina_id,
                        parametro,
                        variedad,
                        etapa_fenologica
                    ),

                    CHECK (
                        valor_minimo IS NULL
                        OR valor_maximo IS NULL
                        OR valor_minimo <= valor_maximo
                    ),

                    CHECK (
                        alerta_activa = 0
                        OR valor_minimo IS NOT NULL
                        OR valor_maximo IS NOT NULL
                    ),

                    CHECK (
                        etapa_fenologica = ''
                        OR variedad <> ''
                    ),

                    FOREIGN KEY (vina_id)
                        REFERENCES vinas(id),

                    FOREIGN KEY (actualizado_por)
                        REFERENCES usuarios(usuario_id)
                )
            """)


def consultar_configuracion_indicadores(usuario_id, vina_id):

    with closing(conectar()) as conexion:

        verificar_permiso_mediciones(
            conexion, usuario_id, vina_id
        )

        conexion.row_factory = __import__("sqlite3").Row

        filas = conexion.execute("""
            SELECT *
            FROM configuracion_indicadores
            WHERE vina_id = ?
            ORDER BY variedad, etapa_fenologica, parametro
        """, (vina_id,)).fetchall()

        return [dict(fila) for fila in filas]


def guardar_configuracion_indicador(
    usuario_id,
    vina_id,
    parametro,
    valor_minimo=None,
    valor_maximo=None,
    alerta_activa=False,
    variedad="",
    etapa_fenologica=""
):

    if parametro not in INDICADORES:
        raise ValueError("Indicador no reconocido.")

    variedad = str(variedad or "").strip()
    etapa_fenologica = str(etapa_fenologica or "").strip()

    if etapa_fenologica and not variedad:
        raise ValueError(
            "Debes seleccionar una variedad."
        )

    def validar_valor(valor):

        if valor is None or valor == "":
            return None

        numero = float(valor)

        if not math.isfinite(numero):
            raise ValueError("El valor debe ser finito.")

        return numero

    minimo = validar_valor(valor_minimo)
    maximo = validar_valor(valor_maximo)

    if minimo is not None and maximo is not None:
        if minimo > maximo:
            raise ValueError(
                "El mínimo no puede superar al máximo."
            )

    if alerta_activa and minimo is None and maximo is None:
        raise ValueError(
            "Debes definir al menos un límite."
        )

    with closing(conectar()) as conexion:
        with conexion:

            conexion.execute("BEGIN IMMEDIATE")

            verificar_administrador_vina(
                conexion, usuario_id, vina_id
            )

            conexion.execute("""
                INSERT INTO configuracion_indicadores (
                    vina_id,
                    parametro,
                    variedad,
                    etapa_fenologica,
                    valor_minimo,
                    valor_maximo,
                    alerta_activa,
                    actualizado_por
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT (
                    vina_id,
                    parametro,
                    variedad,
                    etapa_fenologica
                )

                DO UPDATE SET
                    valor_minimo = excluded.valor_minimo,
                    valor_maximo = excluded.valor_maximo,
                    alerta_activa = excluded.alerta_activa,
                    actualizado_por = excluded.actualizado_por,
                    fecha_actualizacion = CURRENT_TIMESTAMP

            """, (
                vina_id,
                parametro,
                variedad,
                etapa_fenologica,
                minimo,
                maximo,
                int(bool(alerta_activa)),
                usuario_id
            ))
