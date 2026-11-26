
import argparse

from database import conectar


def listar_solicitudes():

    with conectar() as conexion:

        solicitudes = conexion.execute("""
            SELECT u.nombre, u.email,
                   p.institucion,
                   p.area_investigacion,
                   p.finalidad,
                   p.estado
            FROM perfiles_investigadores p
            JOIN usuarios u
              ON u.usuario_id = p.usuario_id
            WHERE u.rol = 'investigador'
            ORDER BY p.fecha_solicitud DESC
        """).fetchall()

    if not solicitudes:
        print("No hay solicitudes registradas.")
        return

    for nombre, email, institucion, area, finalidad, estado in solicitudes:

        print("-" * 50)
        print("Nombre:", nombre)
        print("Correo:", email)
        print("Institucion:", institucion)
        print("Area:", area)
        print("Finalidad:", finalidad)
        print("Estado:", estado)


def cambiar_estado(email, estado):

    email = email.strip().lower()

    with conectar() as conexion:

        usuario = conexion.execute("""
            SELECT u.usuario_id
            FROM usuarios u
            JOIN perfiles_investigadores p
              ON p.usuario_id = u.usuario_id
            WHERE u.email = ?
              AND u.rol = 'investigador'
        """, (email,)).fetchone()

        if usuario is None:
            raise ValueError("Investigador no encontrado.")

        usuario_id = usuario[0]

        conexion.execute("""
            UPDATE perfiles_investigadores
            SET estado = ?,
                fecha_aprobacion = CASE
                    WHEN ? = 'aprobado'
                    THEN CURRENT_TIMESTAMP
                    ELSE fecha_aprobacion
                END
            WHERE usuario_id = ?
        """, (estado, estado, usuario_id))

        conexion.execute("""
            UPDATE usuarios
            SET activo = ?
            WHERE usuario_id = ?
              AND rol = 'investigador'
        """, (
            int(estado == "aprobado"),
            usuario_id
        ))

    print("OK: estado actualizado a", estado)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Gestion local de investigadores FenologIA"
    )

    parser.add_argument(
        "accion",
        choices=[
            "listar",
            "aprobar",
            "rechazar",
            "suspender"
        ]
    )

    parser.add_argument("email", nargs="?")

    args = parser.parse_args()

    if args.accion == "listar":
        listar_solicitudes()

    else:
        if not args.email:
            parser.error("Debes indicar el correo.")

        estados = {
            "aprobar": "aprobado",
            "rechazar": "rechazado",
            "suspender": "suspendido"
        }

        cambiar_estado(
            args.email,
            estados[args.accion]
        )
