
"""Motor integrado de diagnóstico previo a la importación ZIP."""

import io
import hashlib
import zipfile

from validador_zip_dispositivo import (
    validar_contenido_zip_dispositivo,
    _leer_entrada_controlada,
    MAX_ARCHIVO
)

from lector_excel_dispositivo import (
    inspeccionar_hojas_excel
)

from normalizador_capturas_dispositivo import (
    normalizar_capturas_excel
)

from validador_pertenencia_dispositivo import (
    validar_usuario_dispositivo,
    validar_planta_captura
)

from validador_capturas_dispositivo import (
    validar_datos_ambientales_captura
)

from temporalidad_historica_dispositivo import (
    preparar_metadatos_temporales
)

from vinculador_fotografias_dispositivo import (
    construir_indice_fotografias,
    evaluar_conjunto_capturas
)

from diagnostico_zip_dispositivo import (
    generar_diagnostico_ampliado
)

from detector_historial_dispositivo import (
    detectar_zip_previamente_importado
)

from detector_duplicados_dispositivo import (
    detectar_coincidencias_internas,
    MAX_CAPTURAS_COMPARACION
)

from comparador_historial_dispositivo import (
    comparar_lote_con_historial
)


def diagnosticar_importacion_zip(
    conexion,
    contenido,
    nombre_hoja,
    fila_encabezado,
    asignaciones,
    usuario_id,
    vina_id,
    device_id
):
    """Diagnostica una hoja completa sin guardar información."""

    resultado = {
        "estado": "DIAGNOSTICO_ZIP_RECHAZADO",
        "diagnostico_completo": False,
        "checksum_zip": None,
        "vina_id": None,
        "device_id": None,
        "cantidad_capturas": 0,
        "capturas": [],
        "incidencias": [],
        "resumen": {},
        "requiere_revision": True,
        "recuperacion_transaccional_pendiente": False,
        "savepoint_pendiente": None,
        "apto_para_confirmacion": False,
        "listo_para_importar": False,
        "datos_guardados": False
    }

    def rechazar(codigo, mensaje):
        resultado["incidencias"].append({
            "nivel": "ERROR",
            "codigo": codigo,
            "mensaje": mensaje
        })
        return resultado

    contexto = validar_usuario_dispositivo(
        conexion, usuario_id, vina_id, device_id
    )

    if contexto["valida"] is not True:
        resultado["incidencias"].extend(
            contexto["incidencias"]
        )
        return rechazar(
            "CONTEXTO_NO_AUTORIZADO",
            "Usuario o dispositivo no autorizado."
        )

    resultado["vina_id"] = contexto["vina_id"]
    resultado["device_id"] = contexto["device_id"]

    validacion = validar_contenido_zip_dispositivo(
        contenido
    )

    checksum = hashlib.sha256(contenido).hexdigest()

    if (
        validacion.get("contenido_validado") is not True
        or validacion.get("checksum") != checksum
    ):
        return rechazar(
            "ZIP_NO_VERIFICADO",
            "No se pudo verificar el contenido ZIP."
        )

    resultado["checksum_zip"] = checksum

    historial_zip = detectar_zip_previamente_importado(
        conexion, checksum, usuario_id, vina_id, device_id
    )

    resultado["historial_zip"] = historial_zip

    if (
        historial_zip["consulta_completada"] is not True
        or historial_zip["bloqueo_reimportacion"] is not False
    ):
        resultado["incidencias"].extend(
            historial_zip["incidencias"]
        )
        return rechazar(
            "IMPORTACION_BLOQUEADA",
            "El ZIP ya fue importado o su historial no es verificable."
        )

    with zipfile.ZipFile(io.BytesIO(contenido), "r") as z:

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

    normalizacion = normalizar_capturas_excel(
        lectura,
        nombre_hoja,
        fila_encabezado,
        asignaciones
    )

    capturas = normalizacion["capturas"]

    resultado["cantidad_capturas"] = len(capturas)

    if not capturas or len(capturas) > MAX_CAPTURAS_COMPARACION:
        return rechazar(
            "CANTIDAD_CAPTURAS_INVALIDA",
            "Cantidad de capturas fuera del límite permitido."
        )

    indice = construir_indice_fotografias(validacion)

    fotografias = evaluar_conjunto_capturas(
        capturas, indice
    )

    diagnostico_fotos = generar_diagnostico_ampliado(
        fotografias, indice
    )

    resultado["diagnostico_fotografico"] = diagnostico_fotos
    resultado["evaluacion_fotografica"] = fotografias

    resultado["incidencias"].extend(
        diagnostico_fotos["incidencias"]
    )

    if (
        diagnostico_fotos.get("estado")
        != "DIAGNOSTICO_COMPLETADO"
        or diagnostico_fotos.get("checksum_zip") != checksum
    ):
        return rechazar(
            "DIAGNOSTICO_FOTOGRAFICO_INCOMPLETO",
            "No pudo completarse la evaluación fotográfica."
        )

    errores_capturas = 0

    for captura in capturas:

        pertenencia = validar_planta_captura(
            conexion,
            captura,
            usuario_id,
            vina_id,
            device_id
        )

        temporalidad = preparar_metadatos_temporales(
            captura
        )

        ambiental = validar_datos_ambientales_captura(
            captura
        )

        valida = all(
            r.get("valida") is True
            for r in (
                pertenencia,
                temporalidad,
                ambiental
            )
        )

        errores_capturas += int(not valida)

        for evaluacion in (
            pertenencia,
            temporalidad,
            ambiental
        ):
            resultado["incidencias"].extend(
                evaluacion.get("incidencias", [])
            )

        resultado["capturas"].append({
            "captura_original": captura,
            "pertenencia": pertenencia,
            "temporalidad": temporalidad,
            "ambiental": ambiental,
            "valida": valida
        })

    if errores_capturas:
        return rechazar(
            "CAPTURAS_INVALIDAS",
            f"{errores_capturas} capturas requieren corrección."
        )

    internas = detectar_coincidencias_internas(
        conexion,
        capturas,
        usuario_id,
        vina_id,
        device_id
    )

    resultado["coincidencias_internas"] = internas

    resultado["incidencias"].extend(
        internas["incidencias_globales"]
    )

    if (
        internas["diagnostico_completo"] is not True
        or internas["resumen"]["capturas_excluidas"] != 0
    ):
        return rechazar(
            "DIAGNOSTICO_INTERNO_INCOMPLETO",
            "No fue posible comparar todas las capturas."
        )

    historicas = comparar_lote_con_historial(
        conexion,
        capturas,
        usuario_id,
        vina_id,
        device_id
    )

    resultado["coincidencias_historicas"] = historicas

    resultado["incidencias"].extend(
        historicas["incidencias"]
    )

    resultado["recuperacion_transaccional_pendiente"] = (
        historicas["recuperacion_transaccional_pendiente"]
    )

    resultado["savepoint_pendiente"] = (
        historicas["savepoint_pendiente"]
    )

    if (
        historicas["diagnostico_completo"] is not True
        or historicas["recuperacion_transaccional_pendiente"]
        is not False
    ):
        return rechazar(
            "DIAGNOSTICO_HISTORICO_INCOMPLETO",
            "No pudo verificarse el historial completo."
        )

    cantidad_internas = internas["resumen"][
        "pares_con_coincidencia"
    ]

    cantidad_historicas = historicas[
        "cantidad_coincidencias"
    ]

    errores = sum(
        i.get("nivel") == "ERROR"
        for i in resultado["incidencias"]
    )

    advertencias = sum(
        i.get("nivel") == "ADVERTENCIA"
        for i in resultado["incidencias"]
    )

    revision_fotos = any(
        e.get("estado") not in (
            "FOTOGRAFIA_PROPUESTA",
            "SIN_FOTOGRAFIA"
        )
        or e.get("requiere_autorizacion_excepcional")
        or e.get("referencia_compartida")
        or e.get("solapamiento_potencial")
        or bool(e.get("advertencias"))
        for e in fotografias["evaluaciones"]
    ) or any(
        i.get("nivel") != "INFORMACION"
        or i.get("codigo") != "FOTOGRAFIA_PROPUESTA"
        for i in diagnostico_fotos["incidencias"]
        if i.get("nivel") != "INFORMACION"
    )

    bloqueado = bool(
        errores
        or cantidad_internas
        or cantidad_historicas
        or revision_fotos
        or diagnostico_fotos["tiene_errores"]
    )

    resultado["resumen"] = {
        "cantidad_capturas": len(capturas),
        "capturas_validas": len(capturas),
        "capturas_invalidas": errores_capturas,
        "cantidad_fotografias": validacion["cantidad_fotografias"],
        "coincidencias_internas": cantidad_internas,
        "coincidencias_historicas": cantidad_historicas,
        "errores": errores,
        "advertencias": advertencias
    }

    resultado.update({
        "estado": "DIAGNOSTICO_ZIP_COMPLETADO",
        "diagnostico_completo": True,
        "requiere_revision": bool(
            bloqueado or advertencias
        ),
        "apto_para_confirmacion": not bloqueado
    })

    return resultado
