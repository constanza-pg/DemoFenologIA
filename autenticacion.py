import hashlib
import os
import hmac
import secrets
import uuid
import re

from database import conectar


ITERACIONES = 310_000


def generar_hash(password):
    salt = secrets.token_hex(16)

    clave = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        ITERACIONES
    ).hex()

    return f"pbkdf2_sha256${ITERACIONES}${salt}${clave}"


def verificar_hash(password, password_hash):
    try:
        algoritmo, iteraciones, salt, clave_guardada = password_hash.split("$")

        if algoritmo != "pbkdf2_sha256":
            return False

        clave = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iteraciones)
        ).hex()

        return hmac.compare_digest(clave, clave_guardada)

    except (ValueError, TypeError):
        return False




def crear_usuario(usuario_actual, nombre, email, password):
    """Crea una cuenta secundaria dentro de la viña del administrador."""

    nombre = nombre.strip()
    email = email.strip().lower()

    if not nombre:
        raise ValueError("Debes ingresar el nombre del usuario.")

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("El correo electrónico no es válido.")

    if not isinstance(password, str) or len(password) < 10:
        raise ValueError(
            "La contraseña debe tener al menos 10 caracteres."
        )

    if not isinstance(usuario_actual, dict):
        raise ValueError("Sesión de usuario no válida.")

    usuario_id_admin = usuario_actual.get("usuario_id")

    if not usuario_id_admin:
        raise ValueError("No se pudo identificar al administrador.")

    with conectar() as conexion:

        administrador = conexion.execute("""
            SELECT vina_id, rol, activo
            FROM usuarios
            WHERE usuario_id = ?
        """, (usuario_id_admin,)).fetchone()

        if administrador is None:
            raise ValueError("El administrador no existe.")

        vina_id = administrador[0]
        rol = administrador[1]
        activo = administrador[2]

        if rol != "administrador" or activo != 1:
            raise ValueError(
                "No tienes permisos para crear usuarios."
            )

        existente = conexion.execute("""
            SELECT usuario_id
            FROM usuarios
            WHERE email = ?
        """, (email,)).fetchone()

        if existente:
            raise ValueError("Este correo ya está registrado.")

        nuevo_usuario_id = str(uuid.uuid4())
        password_hash = generar_hash(password)

        conexion.execute("""
            INSERT INTO usuarios (
                usuario_id,
                vina_id,
                nombre,
                email,
                password_hash,
                rol,
                activo
            )
            VALUES (?, ?, ?, ?, ?, 'usuario', 1)
        """, (
            nuevo_usuario_id,
            vina_id,
            nombre,
            email,
            password_hash
        ))

    return nuevo_usuario_id


def verificar_usuario(email, password):
    email = email.strip().lower()

    with conectar() as conexion:
        usuario = conexion.execute(
            """
            SELECT
                usuario_id,
                vina_id,
                nombre,
                email,
                password_hash,
                rol,
                activo
            FROM usuarios
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

    if usuario is None:
        return None

    if usuario[6] != 1:
        return None

    if not verificar_hash(password, usuario[4]):
        return None


    if usuario[5] == "investigador":
        with conectar() as conexion:
            perfil = conexion.execute(
                "SELECT estado FROM perfiles_investigadores "
                "WHERE usuario_id = ?",
                (usuario[0],)
            ).fetchone()

        if perfil is None or perfil[0] != "aprobado":
            return None

    return {
        "usuario_id": usuario[0],
        "vina_id": usuario[1],
        "nombre": usuario[2],
        "email": usuario[3],
        "rol": usuario[5]
    }


def registrar_vina_administrador(
    nombre_vina,
    nombre_administrador,
    email,
    password,
    confirmar_password,
    *,
    codigo_invitacion=""
):
    """
    Registra una nueva viña y su primer administrador.

    Ambas operaciones se realizan en una única transacción.
    """

    codigo_servidor = os.environ.get(
        "FENOLOGIA_CODIGO_REGISTRO", ""
    )

    if (
        len(codigo_servidor) < 24
        or not isinstance(codigo_invitacion, str)
        or not hmac.compare_digest(
            codigo_servidor.encode("utf-8"),
            codigo_invitacion.encode("utf-8")
        )
    ):
        raise ValueError(
            "Código de invitación incorrecto "
            "o registro no disponible."
        )


    if not isinstance(nombre_vina, str):
        raise ValueError("El nombre de la viña no es válido.")

    if not isinstance(nombre_administrador, str):
        raise ValueError("El nombre del administrador no es válido.")

    if not isinstance(email, str):
        raise ValueError("El correo electrónico no es válido.")

    nombre_vina = nombre_vina.strip()
    nombre_administrador = nombre_administrador.strip()
    email = email.strip().lower()

    if not nombre_vina:
        raise ValueError("Debes ingresar el nombre de la viña.")

    if not nombre_administrador:
        raise ValueError(
            "Debes ingresar el nombre del administrador."
        )

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("El correo electrónico no es válido.")

    if not isinstance(password, str) or len(password) < 10:
        raise ValueError(
            "La contraseña debe tener al menos 10 caracteres."
        )

    if password != confirmar_password:
        raise ValueError("Las contraseñas no coinciden.")

    vina_id = str(uuid.uuid4())
    usuario_id = str(uuid.uuid4())
    password_hash = generar_hash(password)

    with conectar() as conexion:

        existente = conexion.execute("""
            SELECT usuario_id
            FROM usuarios
            WHERE email = ?
        """, (email,)).fetchone()

        if existente:
            raise ValueError("Este correo ya está registrado.")

        conexion.execute("""
            INSERT INTO vinas (
                id,
                nombre,
                ubicacion,
                entorno
            )
            VALUES (?, ?, ?, 'operacional')
        """, (
            vina_id,
            nombre_vina,
            "Por definir"
        ))

        conexion.execute("""
            INSERT INTO usuarios (
                usuario_id,
                vina_id,
                nombre,
                email,
                password_hash,
                rol,
                activo
            )
            VALUES (?, ?, ?, ?, ?, 'administrador', 1)
        """, (
            usuario_id,
            vina_id,
            nombre_administrador,
            email,
            password_hash
        ))

    return {
        "vina_id": vina_id,
        "usuario_id": usuario_id
    }

def consultar_usuario_activo(usuario_id):
    """
    Consulta el estado vigente de un usuario autenticado.

    Devuelve sus datos actuales si la cuenta sigue activa.
    Devuelve None si no existe o está desactivada.
    No modifica la base de datos.
    """

    if not usuario_id:
        return None

    with conectar() as conexion:
        usuario = conexion.execute(
            """
            SELECT
                usuario_id,
                vina_id,
                nombre,
                email,
                rol
            FROM usuarios
            WHERE usuario_id = ?
              AND activo = 1
            """,
            (usuario_id,)
        ).fetchone()

    if usuario is None:
        return None


    if usuario[4] == "investigador":
        with conectar() as conexion:
            perfil = conexion.execute(
                "SELECT estado FROM perfiles_investigadores "
                "WHERE usuario_id = ?",
                (usuario[0],)
            ).fetchone()

        if perfil is None or perfil[0] != "aprobado":
            return None

    return {
        "usuario_id": usuario[0],
        "vina_id": usuario[1],
        "nombre": usuario[2],
        "email": usuario[3],
        "rol": usuario[4]
    }



def registrar_investigador(
    nombre,
    email,
    institucion,
    area_investigacion,
    finalidad,
    password,
    confirmar_password
):
    """Registra una solicitud de investigador pendiente."""

    nombre = nombre.strip()
    email = email.strip().lower()
    institucion = institucion.strip()
    area_investigacion = area_investigacion.strip()
    finalidad = finalidad.strip()

    if not all([
        nombre,
        institucion,
        area_investigacion,
        finalidad
    ]):
        raise ValueError(
            "Debes completar todos los campos."
        )

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError(
            "El correo electronico no es valido."
        )

    if len(password) < 10:
        raise ValueError(
            "La contrasena debe tener al menos 10 caracteres."
        )

    if password != confirmar_password:
        raise ValueError(
            "Las contrasenas no coinciden."
        )

    usuario_id = str(uuid.uuid4())
    password_hash = generar_hash(password)

    with conectar() as conexion:

        existente = conexion.execute("""
            SELECT usuario_id
            FROM usuarios
            WHERE email = ?
        """, (email,)).fetchone()

        if existente:
            raise ValueError(
                "Este correo ya esta registrado."
            )

        conexion.execute("""
            INSERT INTO usuarios (
                usuario_id,
                vina_id,
                nombre,
                email,
                password_hash,
                rol,
                activo
            )
            VALUES (?, NULL, ?, ?, ?, 'investigador', 0)
        """, (
            usuario_id,
            nombre,
            email,
            password_hash
        ))

        conexion.execute("""
            INSERT INTO perfiles_investigadores (
                usuario_id,
                institucion,
                area_investigacion,
                finalidad,
                estado
            )
            VALUES (?, ?, ?, ?, 'pendiente')
        """, (
            usuario_id,
            institucion,
            area_investigacion,
            finalidad
        ))

    return usuario_id

