"""
Vista previa de importación conservadora de FenologIA.

No modifica la base de datos.
"""

from validacion_csv_prueba import validar_csv
from database import (
    conectar,
    verificar_administrador_vina,
    diagnosticar_discrepancias_csv,
)


def preparar_vista_previa_csv(datos, vina_id, usuario_id):
    """
    Calcula cuántas plantas y mediciones son nuevas
    y cuántas ya existen en la viña.
    """

    datos = validar_csv(datos)

    resumen = {
        "plantas_nuevas": 0,
        "plantas_existentes": 0,
        "mediciones_nuevas": 0,
        "mediciones_existentes": 0,
    }

    with conectar() as conexion:

        verificar_administrador_vina(
            conexion,
            usuario_id,
            vina_id
        )

        plantas = conexion.execute("""
            SELECT id, codigo_planta
            FROM plantas
            WHERE vina_id = ?
        """, (vina_id,)).fetchall()

        mapa_plantas = {
            codigo: planta_id
            for planta_id, codigo in plantas
        }

        codigos_csv = datos["id"].drop_duplicates()

        for codigo in codigos_csv:
            if codigo in mapa_plantas:
                resumen["plantas_existentes"] += 1
            else:
                resumen["plantas_nuevas"] += 1

        mediciones_existentes = set(
            conexion.execute("""
                SELECT m.plant_id, m.fecha_hora
                FROM mediciones m
                JOIN plantas p ON p.id = m.plant_id
                WHERE p.vina_id = ?
            """, (vina_id,)).fetchall()
        )

        for _, fila in datos.iterrows():

            codigo = fila["id"]
            fecha = fila["fecha"]

            planta_id = mapa_plantas.get(codigo)

            if (
                planta_id is not None
                and (planta_id, fecha) in mediciones_existentes
            ):
                resumen["mediciones_existentes"] += 1
            else:
                resumen["mediciones_nuevas"] += 1

    discrepancias = diagnosticar_discrepancias_csv(
        datos,
        vina_id,
        usuario_id
    )

    return {
        "resumen": resumen,
        "discrepancias": discrepancias,
        "datos_validados": datos
    }
