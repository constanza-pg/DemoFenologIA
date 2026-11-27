
import argparse
from database import conectar


def listar_vinas():

    with conectar() as con:

        filas = con.execute("""
            SELECT id, nombre, entorno
            FROM vinas
            ORDER BY id
        """).fetchall()

        for fila in filas:
            print(" | ".join(str(v) for v in fila))


def habilitar_vina(vina_id):

    with conectar() as con:

        con.execute("BEGIN IMMEDIATE")

        vina = con.execute("""
            SELECT nombre, entorno
            FROM vinas
            WHERE id = ?
        """, (vina_id,)).fetchone()

        if vina is None:
            raise ValueError("La vina no existe.")

        if vina[1] == "prueba":
            raise ValueError(
                "Una vina de prueba no puede convertirse "
                "en operacional. Registre una nueva vina."
            )

        if vina[1] == "operacional":
            print("La vina ya es operacional.")
            return

        con.execute("""
            UPDATE vinas
            SET entorno = 'operacional'
            WHERE id = ?
            AND entorno = 'sin_verificar'
        """, (vina_id,))

        print("OK: vina operacional habilitada:", vina[0])


def main():

    parser = argparse.ArgumentParser(
        description="Administracion tecnica de FenologIA"
    )

    parser.add_argument(
        "accion",
        choices=["listar", "habilitar"]
    )

    parser.add_argument(
        "vina_id",
        nargs="?"
    )

    parser.add_argument(
        "--confirmar-real",
        action="store_true"
    )

    args = parser.parse_args()

    if args.accion == "listar":
        listar_vinas()

    elif args.accion == "habilitar":

        if not args.vina_id:
            parser.error("Debe indicar el ID de la vina.")

        if not args.confirmar_real:
            parser.error(
                "Debe confirmar que corresponde "
                "a una vina real mediante --confirmar-real."
            )

        habilitar_vina(args.vina_id)


if __name__ == "__main__":
    main()
