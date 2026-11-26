
"""Importación controlada de paquetes ZIP en la base experimental."""

import hashlib
import io
import json
import uuid
import zipfile

from pathlib import Path, PurePosixPath
from contextlib import closing

from database import (
    conectar,
    registrar_imagen_dispositivo
)

from almacenamiento_fotografico import (
    guardar_fotografia_protegida,
    validar_carpeta_fotografica
)

from motor_importacion_zip_dispositivo import (
    diagnosticar_importacion_zip
)

from validador_zip_dispositivo import (
    validar_contenido_zip_dispositivo,
    _leer_entrada_controlada,
    MAX_ARCHIVO
)

from lector_excel_dispositivo import (
    inspeccionar_hojas_excel
)

from temporalidad_historica_dispositivo import (
    MAX_BYTES_DATOS_JSON
)


def importar_zip_dispositivo(
    contenido,
    nombre_archivo,
    nombre_hoja,
    fila_encabezado,
    asignaciones,
    usuario_id,
    vina_id,
    device_id,
    confirmacion=False,
    unidades_confirmadas=False
):
    """Guarda un ZIP confirmado mediante una transacción controlada."""

    if confirmacion is not True:
        raise PermissionError(
            "Se requiere confirmación explícita de importación."
        )

    if unidades_confirmadas is not True:
        raise ValueError(
            "Debes confirmar las unidades ambientales: °C y %."
        )

    if not isinstance(nombre_archivo, str):
        raise ValueError("Nombre de archivo inválido.")

    nombre_archivo = PurePosixPath(nombre_archivo).name

    if not nombre_archivo.lower().endswith(".zip"):
        raise ValueError("Se requiere un archivo ZIP.")

    checksum = hashlib.sha256(contenido).hexdigest()

    importacion_id = str(uuid.uuid4())

    archivos_creados = []
    cantidad_fotografias = 0
    commit_iniciado = False

    with closing(conectar()) as con:

        try:

            con.execute("BEGIN IMMEDIATE")

            diagnostico = diagnosticar_importacion_zip(
                con,
                contenido,
                nombre_hoja,
                fila_encabezado,
                asignaciones,
                usuario_id,
                vina_id,
                device_id
            )

            if (
                diagnostico.get("diagnostico_completo")
                is not True
                or diagnostico.get("apto_para_confirmacion")
                is not True
                or diagnostico.get("checksum_zip") != checksum
                or diagnostico.get(
                    "recuperacion_transaccional_pendiente"
                ) is not False
            ):
                raise ValueError(
                    "El diagnóstico no permite importar este ZIP."
                )

            validacion = validar_contenido_zip_dispositivo(
                contenido
            )

            if (
                validacion.get("contenido_validado") is not True
                or validacion.get("checksum") != checksum
            ):
                raise ValueError(
                    "El contenido ZIP no pudo verificarse."
                )

            detalles_fotos = {
                f["nombre"]: f
                for f in validacion["detalle_fotografias"]
            }

            evaluaciones = diagnostico[
                "evaluacion_fotografica"
            ]["evaluaciones"]

            fotos_por_fila = {}

            for evaluacion in evaluaciones:

                referencia = (
                    evaluacion["hoja_excel"],
                    evaluacion["fila_excel"]
                )

                if referencia in fotos_por_fila:
                    raise ValueError(
                        "Referencia fotográfica repetida."
                    )

                if (
                    evaluacion.get(
                        "requiere_autorizacion_excepcional"
                    )
                    or evaluacion.get("referencia_compartida")
                    or evaluacion.get("solapamiento_potencial")
                    or bool(evaluacion.get("advertencias"))
                ):
                    raise ValueError(
                        "Existen fotografías pendientes de revisión."
                    )

                estado = evaluacion["estado"]

                if estado not in (
                    "FOTOGRAFIA_PROPUESTA",
                    "SIN_FOTOGRAFIA"
                ):
                    raise ValueError(
                        "Vinculación fotográfica no resuelta."
                    )

                propuesta = evaluacion.get(
                    "fotografia_propuesta"
                )

                if estado == "FOTOGRAFIA_PROPUESTA" and not propuesta:
                    raise ValueError(
                        "Falta la fotografía propuesta."
                    )

                fotos_por_fila[referencia] = (
                    propuesta["ruta"]
                    if propuesta else None
                )

            rutas = [
                r for r in fotos_por_fila.values()
                if r is not None
            ]

            if (
                len(rutas) != len(set(rutas))
                or set(rutas) != set(detalles_fotos)
            ):
                raise ValueError(
                    "Existen fotografías compartidas "
                    "o sin vinculación definitiva."
                )

            registros = diagnostico["capturas"]

            if len(registros) != len(fotos_por_fila):
                raise ValueError(
                    "Cantidad de capturas inconsistente."
                )

            with zipfile.ZipFile(
                io.BytesIO(contenido), "r"
            ) as z:

                excel = _leer_entrada_controlada(
                    z,
                    z.getinfo(validacion["excel"]),
                    MAX_ARCHIVO,
                    conservar=True
                )

                lectura = inspeccionar_hojas_excel(
                    excel,
                    lectura_completa=True
                )

                hojas_con_datos = [
                    h["nombre"]
                    for h in lectura["hojas"]
                    if h["filas_con_datos"] > 0
                ]

                if hojas_con_datos != [nombre_hoja]:
                    raise ValueError(
                        "La importación inicial admite una sola "
                        "hoja con datos por ZIP."
                    )

                con.execute("""
                    INSERT INTO importaciones_dispositivo (
                        importacion_id,
                        vina_id,
                        usuario_id,
                        device_id,
                        nombre_archivo,
                        checksum,
                        cantidad_capturas,
                        cantidad_fotografias
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    importacion_id,
                    vina_id,
                    usuario_id,
                    device_id,
                    nombre_archivo,
                    checksum,
                    len(registros),
                    len(rutas)
                ))

                for registro in registros:

                    original = registro["captura_original"]
                    pertenencia = registro["pertenencia"]
                    temporal = registro["temporalidad"]
                    ambiental = registro["ambiental"]

                    if registro["valida"] is not True:
                        raise ValueError(
                            "Captura no validada."
                        )

                    referencia = (
                        original["hoja_excel"],
                        original["fila_excel"]
                    )

                    ruta_foto = fotos_por_fila[referencia]

                    captura_id = str(uuid.uuid4())

                    datos_json = json.dumps({
                        "version": 1,
                        "temporalidad_v1": (
                            temporal["metadatos_temporales"]
                        ),
                        "captura_original": original,
                        "unidades_ambientales": {
                            "temperatura_ambiental": "°C",
                            "humedad_ambiental": "%"
                        },
                        "unidades_confirmadas": True
                    }, ensure_ascii=False, allow_nan=False)

                    if (
                        len(datos_json.encode("utf-8"))
                        > MAX_BYTES_DATOS_JSON
                    ):
                        raise ValueError(
                            "Los metadatos superan el límite permitido."
                        )

                    con.execute("""
                        INSERT INTO capturas_dispositivo (
                            captura_id,
                            importacion_id,
                            plant_id,
                            device_id,
                            fecha_hora,
                            temperatura_ambiental,
                            humedad_ambiental,
                            tiene_fotografia,
                            datos_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        captura_id,
                        importacion_id,
                        pertenencia["plant_id"],
                        device_id,
                        temporal["fecha_hora"],
                        ambiental["temperatura_ambiental"],
                        ambiental["humedad_ambiental"],
                        int(ruta_foto is not None),
                        datos_json
                    ))

                    if ruta_foto is None:
                        continue

                    detalle = detalles_fotos[ruta_foto]

                    contenido_foto = _leer_entrada_controlada(
                        z,
                        z.getinfo(ruta_foto),
                        MAX_ARCHIVO,
                        conservar=True
                    )

                    if (
                        hashlib.sha256(
                            contenido_foto
                        ).hexdigest() != detalle["checksum"]
                        or len(contenido_foto) != detalle["bytes"]
                    ):
                        raise ValueError(
                            "Integridad fotográfica incorrecta."
                        )

                    foto = guardar_fotografia_protegida(
                        contenido_foto,
                        PurePosixPath(ruta_foto).name
                    )

                    archivo = Path(foto["ruta_absoluta"])
                    estado_archivo = archivo.lstat()

                    archivos_creados.append((
                        archivo,
                        estado_archivo.st_dev,
                        estado_archivo.st_ino
                    ))

                    registrar_imagen_dispositivo(
                        captura_id,
                        foto["ruta_relativa"],
                        vina_id,
                        usuario_id,
                        conexion=con
                    )

                    cantidad_fotografias += 1

            if cantidad_fotografias != len(rutas):
                raise RuntimeError(
                    "Cantidad de fotografías guardadas inconsistente."
                )

            commit_iniciado = True
            con.commit()

        except BaseException as error:

            try:
                con.rollback()

            except BaseException as secundario:
                error.add_note(
                    "No se pudo confirmar el rollback: "
                    + type(secundario).__name__
                )
                raise error

            if commit_iniciado:

                error.add_note(
                    "El resultado del commit requiere verificación. "
                    "Se conservan las fotografías para evitar "
                    "eliminar archivos posiblemente registrados."
                )

                raise

            for archivo, dispositivo, inode in reversed(
                archivos_creados
            ):

                try:

                    carpeta = validar_carpeta_fotografica()
                    estado = archivo.lstat()

                    if (
                        archivo.parent == carpeta
                        and not archivo.is_symlink()
                        and archivo.resolve() == archivo
                        and estado.st_nlink == 1
                        and estado.st_dev == dispositivo
                        and estado.st_ino == inode
                    ):
                        archivo.unlink()

                    else:
                        error.add_note(
                            "Fotografía pendiente de limpieza: "
                            + str(archivo)
                        )

                except Exception:

                    error.add_note(
                        "No se pudo limpiar: " + str(archivo)
                    )

            raise

    return {
        "estado": "IMPORTACION_COMPLETADA",
        "importacion_id": importacion_id,
        "checksum_zip": checksum,
        "vina_id": vina_id,
        "device_id": device_id,
        "cantidad_capturas": len(registros),
        "cantidad_fotografias": cantidad_fotografias,
        "datos_guardados": True
    }
