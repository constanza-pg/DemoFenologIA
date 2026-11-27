
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


def _preparar_configuracion_indicador(
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

        if valor is None:
            return None

        if isinstance(valor, str):
            valor = valor.strip().replace(",", ".")
            if not valor:
                return None

        try:
            numero = float(valor)
        except (ValueError, TypeError):
            raise ValueError(
                f"{parametro}: ingresa un valor numerico valido."
            )

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


    return (
        vina_id, parametro, variedad,
        etapa_fenologica, minimo, maximo,
        int(bool(alerta_activa)), usuario_id
    )



def _escribir_configuracion_indicador(conexion, registro):
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

    """, registro)



def guardar_configuracion_indicadores(
    usuario_id, vina_id, indicadores, variedad=""
):
    registros = [
        _preparar_configuracion_indicador(
            usuario_id=usuario_id,
            vina_id=vina_id,
            variedad=variedad,
            **indicador
        )
        for indicador in indicadores
    ]

    if not registros:
        raise ValueError("No hay indicadores para guardar.")

    with closing(conectar()) as conexion:
        with conexion:
            conexion.execute("BEGIN IMMEDIATE")

            verificar_administrador_vina(
                conexion, usuario_id, vina_id
            )

            for registro in registros:
                _escribir_configuracion_indicador(
                    conexion, registro
                )


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
    guardar_configuracion_indicadores(
        usuario_id,
        vina_id,
        [{
            "parametro": parametro,
            "valor_minimo": valor_minimo,
            "valor_maximo": valor_maximo,
            "alerta_activa": alerta_activa,
            "etapa_fenologica": etapa_fenologica
        }],
        variedad=variedad
    )


def preparar_criterios_alerta(configuraciones):
    return {
        (c["parametro"], c["variedad"]): c
        for c in configuraciones
        if not c.get("etapa_fenologica")
    }


def evaluar_indicadores_planta(planta, criterios):

    variedad_original = planta.get("variedad")

    variedad = (
        str(variedad_original).strip()
        if variedad_original is not None
        else ""
    )

    alertas = []
    evaluados = 0
    activos = 0

    for parametro in INDICADORES:

        criterio = criterios.get(
            (parametro, variedad)
        )

        if criterio is None:
            criterio = criterios.get(
                (parametro, "")
            )

        if not criterio or not criterio.get("alerta_activa"):
            continue

        minimo = criterio.get("valor_minimo")
        maximo = criterio.get("valor_maximo")

        if minimo is None and maximo is None:
            continue

        activos += 1

        try:
            valor = float(planta.get(parametro))
        except (TypeError, ValueError, OverflowError):
            continue

        if not math.isfinite(valor):
            continue

        evaluados += 1

        if minimo is not None and valor < minimo:

            alertas.append({
                "parametro": parametro,
                "valor": valor,
                "operador": "<",
                "umbral": minimo
            })

        elif maximo is not None and valor > maximo:

            alertas.append({
                "parametro": parametro,
                "valor": valor,
                "operador": ">",
                "umbral": maximo
            })

    return {
        "alertas": alertas,
        "evaluados": evaluados,
        "activos": activos
    }


def evaluar_indicadores_dataframe(datos, criterios):

    import pandas as pd

    resultados = [
        evaluar_indicadores_planta(planta, criterios)
        for planta in datos.to_dict("records")
    ]

    alertadas = pd.Series(
        [bool(r["alertas"]) for r in resultados],
        index=datos.index,
        dtype=bool
    )

    evaluables = pd.Series(
        [r["evaluados"] > 0 for r in resultados],
        index=datos.index,
        dtype=bool
    )

    return alertadas, evaluables, resultados
