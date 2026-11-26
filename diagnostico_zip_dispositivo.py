"""Diagnóstico preliminar de fotografías y capturas."""

REGLAS_FOTOGRAFIAS = {
    "FOTOGRAFIA_PROPUESTA": (
        "INFORMACION",
        "Fotografía localizada.",
        "Confirmar que corresponde a la captura."
    ),
    "SIN_FOTOGRAFIA": (
        "ADVERTENCIA",
        "La captura declara que no tiene fotografía. "
        "Se requiere autorización excepcional.",
        "Revisar la causa de la ausencia fotográfica "
        "y autorizar expresamente la conservación "
        "de los datos ambientales, cuando esté "
        "disponible esa opción."
    ),
    "VINCULACION_PENDIENTE": (
        "ADVERTENCIA",
        "La captura declara una fotografía sin identificarla.",
        "Identificar la fotografía mediante información "
        "verificable. No utilizar el orden de los archivos "
        "como único criterio de vinculación."
    ),
    "INFORMACION_INSUFICIENTE": (
        "ADVERTENCIA",
        "No se informó si existe una fotografía.",
        "Revisar los campos originales del Excel."
    ),
    "FOTOGRAFIA_AMBIGUA": (
        "ERROR",
        "Existen varias fotografías con el nombre indicado.",
        "Identificar la ruta correcta."
    ),
    "FOTOGRAFIA_NO_ENCONTRADA": (
        "ERROR",
        "La fotografía declarada no existe en el ZIP.",
        "Revisar el nombre o incorporar el archivo faltante."
    ),
    "CONFLICTO_INDICADOR_REFERENCIA": (
        "ERROR",
        "El indicador contradice la referencia fotográfica.",
        "Revisar el indicador y el nombre de archivo."
    ),
    "INDICADOR_INVALIDO": (
        "ERROR",
        "El indicador de fotografía no es reconocido.",
        "Revisar el valor original."
    ),
    "REFERENCIA_INVALIDA": (
        "ERROR",
        "La referencia fotográfica no es válida.",
        "Revisar el nombre, extensión o ruta del archivo."
    )
}


def generar_diagnostico_fotografias(evaluacion):
    """Genera incidencias sin autorizar una importación."""

    if evaluacion.get("estado") != "EVALUACION_COMPLETADA":

        raise ValueError(
            "Se requiere una evaluación conjunta completa."
        )

    incidencias = []

    def agregar(nivel, codigo, mensaje, recomendacion, **datos):

        incidencias.append({
            "nivel": nivel,
            "codigo": codigo,
            "mensaje": mensaje,
            "recomendacion": recomendacion,
            **datos
        })

    registros = evaluacion["evaluaciones"]

    if not registros:

        agregar(
            "ERROR",
            "SIN_CAPTURAS",
            "No existen capturas para importar.",
            "Revisar la selección de registros del Excel."
        )

    for registro in registros:

        estado = registro["estado"]

        if estado not in REGLAS_FOTOGRAFIAS:

            raise ValueError(
                "Estado de evaluación desconocido: " + estado
            )

        nivel, mensaje, recomendacion = (
            REGLAS_FOTOGRAFIAS[estado]
        )

        agregar(
            nivel,
            estado,
            mensaje,
            recomendacion,
            hoja_excel=registro["hoja_excel"],
            fila_excel=registro["fila_excel"],
            codigo_planta=registro["codigo_planta"],
            referencia=registro["referencia_original"]
        )

    for compartida in evaluacion["referencias_compartidas"]:

        agregar(
            "ERROR",
            "FOTOGRAFIA_COMPARTIDA",
            "Varias capturas hacen referencia inequívoca "
            "a la misma fotografía.",
            "Revisar las filas indicadas y corregir las "
            "referencias utilizando información verificable. "
            "No asignar fotografías por suposición.",
            ruta=compartida["ruta"],
            capturas=[
                dict(captura)
                for captura in compartida["capturas"]
            ]
        )

    for solapamiento in evaluacion.get(
        "solapamientos_potenciales", []
    ):

        agregar(
            "ERROR",
            "SOLAPAMIENTO_POTENCIAL",
            "Una fotografía aparece entre las posibles "
            "coincidencias de varias capturas.",
            "Resolver las referencias ambiguas mediante "
            "rutas completas y comprobar su procedencia. "
            "No confirmar vinculaciones por suposición.",
            ruta=solapamiento["ruta"],
            capturas=[
                dict(captura)
                for captura in solapamiento["capturas"]
            ]
        )

    for ruta in evaluacion["fotografias_sin_referencia"]:

        agregar(
            "ADVERTENCIA",
            "FOTOGRAFIA_SIN_REFERENCIA",
            "No se encontró una referencia para esta fotografía.",
            "Comprobar su procedencia antes de vincularla. "
            "No asignarla automáticamente a una captura.",
            ruta=ruta
        )

    orden = {
        "ERROR": 0,
        "ADVERTENCIA": 1,
        "INFORMACION": 2
    }

    incidencias.sort(
        key=lambda incidencia: orden[incidencia["nivel"]]
    )

    conteo = {
        nivel: sum(
            incidencia["nivel"] == nivel
            for incidencia in incidencias
        )
        for nivel in orden
    }

    return {
        "estado": "DIAGNOSTICO_COMPLETADO",
        "checksum_zip": evaluacion.get("checksum_zip"),
        "resumen": {
            "cantidad_capturas": len(registros),
            "errores": conteo["ERROR"],
            "advertencias": conteo["ADVERTENCIA"],
            "informaciones": conteo["INFORMACION"],
            "total_incidencias": len(incidencias),
            "capturas_requieren_autorizacion_excepcional": sum(
                registro["estado"] == "SIN_FOTOGRAFIA"
                for registro in registros
            )
        },
        "incidencias": incidencias,
        "requiere_autorizacion_excepcional": any(
            registro["estado"] == "SIN_FOTOGRAFIA"
            for registro in registros
        ),
        "autorizacion_excepcional_confirmada": False,
        "tiene_errores": conteo["ERROR"] > 0,
        "requiere_revision": (
            conteo["ERROR"] > 0
            or conteo["ADVERTENCIA"] > 0
            or any(
                registro["requiere_revision"]
                for registro in registros
            )
        ),
        "listo_para_importar": False,
        "datos_guardados": False
    }



def generar_diagnostico_ampliado(evaluacion, indice):
    """Amplía el diagnóstico sin confirmar vinculaciones."""

    if indice.get("indice_completado") is not True:

        raise ValueError(
            "Se requiere un índice validado."
        )

    checksum = indice.get("checksum_zip")

    if not checksum or checksum != evaluacion.get("checksum_zip"):

        raise ValueError(
            "La evaluación y el índice deben corresponder al mismo ZIP."
        )

    resultado = generar_diagnostico_fotografias(
        evaluacion
    )

    incidencias = resultado["incidencias"]

    def agregar(nivel, codigo, mensaje, recomendacion, **datos):

        incidencias.append({
            "nivel": nivel,
            "codigo": codigo,
            "mensaje": mensaje,
            "recomendacion": recomendacion,
            **datos
        })

    for nombre, rutas in sorted(
        indice["nombres_repetidos"].items()
    ):

        agregar(
            "ADVERTENCIA",
            "NOMBRE_FOTOGRAFIA_REPETIDO",
            "Existen fotografías con el mismo nombre.",
            "Utilizar rutas completas para diferenciarlas.",
            nombre=nombre,
            rutas=sorted(rutas)
        )

    for hash_foto, rutas in sorted(
        indice["contenidos_repetidos"].items()
    ):

        agregar(
            "ADVERTENCIA",
            "CONTENIDO_FOTOGRAFICO_REPETIDO",
            "Varias fotografías tienen contenido idéntico.",
            "Revisar si son copias o registros intencionales.",
            checksum_fotografia=hash_foto,
            rutas=sorted(rutas)
        )

    propuestas = {}
    ambiguas = {}

    for registro in evaluacion["evaluaciones"]:

        identificador = {
            "hoja_excel": registro["hoja_excel"],
            "fila_excel": registro["fila_excel"],
            "codigo_planta": registro["codigo_planta"]
        }

        fotografia = registro["fotografia_propuesta"]

        if fotografia is not None:

            propuestas.setdefault(
                fotografia["ruta"], []
            ).append(identificador)

        if registro["estado"] == "FOTOGRAFIA_AMBIGUA":

            for ruta in registro["busqueda"]["coincidencias"]:

                ambiguas.setdefault(
                    ruta, []
                ).append(identificador)

    # Los solapamientos se diagnostican ahora
    # en generar_diagnostico_fotografias.

    orden = {
        "ERROR": 0,
        "ADVERTENCIA": 1,
        "INFORMACION": 2
    }

    incidencias.sort(
        key=lambda i: orden[i["nivel"]]
    )

    conteo = {
        nivel: sum(
            i["nivel"] == nivel
            for i in incidencias
        )
        for nivel in orden
    }

    resultado["resumen"].update({
        "errores": conteo["ERROR"],
        "advertencias": conteo["ADVERTENCIA"],
        "informaciones": conteo["INFORMACION"],
        "total_incidencias": len(incidencias)
    })

    resultado["tiene_errores"] = (
        conteo["ERROR"] > 0
    )

    resultado["requiere_revision"] = (
        resultado["requiere_revision"]
        or conteo["ERROR"] > 0
        or conteo["ADVERTENCIA"] > 0
    )

    resultado["diagnostico_ampliado"] = True

    resultado["listo_para_importar"] = False
    resultado["datos_guardados"] = False

    return resultado
