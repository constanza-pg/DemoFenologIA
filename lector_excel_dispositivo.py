"""Lectura segura del Excel generado por el dispositivo."""

import io
import zipfile

from defusedxml import ElementTree as XML
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError

from validador_zip_dispositivo import (
    _validar_excel_interno,
    _leer_entrada_controlada,
    MAX_ARCHIVO
)


# Límites preventivos y ajustables.
MAX_PROFUNDIDAD_XML = 100
MAX_ELEMENTOS_XML = 2000000
MAX_DOCUMENTOS_XML = 1000


def validar_documento_xml(contenido, nombre):
    """Valida un documento XML mediante lectura incremental."""

    profundidad = 0
    profundidad_maxima = 0
    elementos = 0
    pila = []

    try:

        eventos = XML.iterparse(
            io.BytesIO(contenido),
            events=("start", "end"),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True
        )

        for evento, elemento in eventos:

            if evento == "start":

                pila.append(elemento)

                profundidad += 1
                elementos += 1

                profundidad_maxima = max(
                    profundidad_maxima,
                    profundidad
                )

                if profundidad > MAX_PROFUNDIDAD_XML:
                    raise ValueError(
                        f"Anidamiento XML excesivo: {nombre}"
                    )

                if elementos > MAX_ELEMENTOS_XML:
                    raise ValueError(
                        f"Demasiados elementos XML: {nombre}"
                    )

                etiqueta = elemento.tag.rsplit(
                    "}", 1
                )[-1]

                if etiqueta == "Relationship":

                    modo = elemento.attrib.get(
                        "TargetMode", ""
                    )

                    if modo.strip().casefold() == "external":

                        raise ValueError(
                            f"Referencia externa no permitida: "
                            f"{nombre}"
                        )

            else:

                pila.pop()

                elemento.clear()

                if pila:
                    pila[-1].remove(elemento)

                profundidad -= 1

    except (
        DefusedXmlException,
        ParseError
    ) as error:

        raise ValueError(
            f"Documento XML inválido o inseguro: {nombre}"
        ) from error

    return {
        "nombre": nombre,
        "elementos": elementos,
        "profundidad_maxima": profundidad_maxima
    }


def validar_xml_excel(contenido):
    """Valida los documentos XML internos de un XLSX."""

    if not isinstance(contenido, bytes):
        raise ValueError(
            "El Excel debe recibirse como bytes."
        )

    if not contenido:
        raise ValueError("El Excel está vacío.")

    if len(contenido) > MAX_ARCHIVO:
        raise ValueError(
            "El Excel supera el tamaño permitido."
        )

    estructura = _validar_excel_interno(contenido)

    documentos = []

    with zipfile.ZipFile(
        io.BytesIO(contenido), "r"
    ) as z:

        entradas = [
            entrada
            for entrada in z.infolist()
            if not entrada.is_dir()
            and entrada.filename.lower().endswith(
                (".xml", ".rels", ".vml")
            )
        ]

        if len(entradas) > MAX_DOCUMENTOS_XML:

            raise ValueError(
                "El Excel contiene demasiados documentos XML."
            )

        total_elementos = 0

        for entrada in entradas:

            datos = _leer_entrada_controlada(
                z,
                entrada,
                MAX_ARCHIVO,
                conservar=True
            )

            detalle = validar_documento_xml(
                datos,
                entrada.filename
            )

            total_elementos += detalle["elementos"]

            if total_elementos > MAX_ELEMENTOS_XML:
                raise ValueError(
                    "El Excel contiene demasiados "
                    "elementos XML acumulados."
                )

            documentos.append(detalle)

            del datos

    return {
        "xml_validado": True,
        "estructura": estructura,
        "cantidad_documentos": len(documentos),
        "total_elementos": total_elementos,
        "documentos": documentos
    }



# Límites preliminares de lectura.
MAX_HOJAS_EXCEL = 20
MAX_FILAS_EXCEL = 50000
MAX_COLUMNAS_EXCEL = 100
MAX_CELDAS_EXCEL = 1000000
MAX_FILAS_PREVIA = 20


def _serializar_celda(celda):
    """Representa una celda sin interpretar su significado."""

    from datetime import datetime, date, time, timedelta

    valor = celda.value

    if valor is None:
        return None

    if celda.data_type == "f":
        raise ValueError(
            "El Excel contiene fórmulas no permitidas."
        )

    if isinstance(valor, bool):
        tipo = "booleano"

    elif isinstance(valor, datetime):
        tipo = "fecha_hora"
        valor = valor.isoformat()

    elif isinstance(valor, date):
        tipo = "fecha"
        valor = valor.isoformat()

    elif isinstance(valor, time):
        tipo = "hora"
        valor = valor.isoformat()

    elif isinstance(valor, timedelta):
        tipo = "duracion"
        valor = str(valor)

    elif isinstance(valor, (int, float)):
        tipo = "numero"

    elif celda.data_type == "e":
        tipo = "error_excel"
        valor = str(valor)

    else:
        tipo = "texto"
        valor = str(valor)

    return {
        "valor": valor,
        "tipo": tipo
    }


def inspeccionar_hojas_excel(contenido, lectura_completa=False):
    """Inspecciona hojas y opcionalmente conserva todas sus filas."""

    if not isinstance(lectura_completa, bool):
        raise ValueError(
            "La modalidad de lectura debe ser booleana."
        )

    from openpyxl import load_workbook

    validacion = validar_xml_excel(contenido)

    coordenadas = validar_coordenadas_excel(
        contenido
    )

    libro = load_workbook(
        io.BytesIO(contenido),
        read_only=True,
        data_only=False,
        keep_links=False
    )

    resultado = {
        "validacion_xml": validacion,
        "validacion_coordenadas": coordenadas,
        "cantidad_hojas": 0,
        "hojas": []
    }

    total_celdas = 0

    try:

        if len(libro.sheetnames) > MAX_HOJAS_EXCEL:
            raise ValueError(
                "El Excel contiene demasiadas hojas."
            )

        for hoja in libro.worksheets:

            # Revisar las dimensiones declaradas.
            if (
                hoja.max_row is not None
                and hoja.max_row > MAX_FILAS_EXCEL
            ):
                raise ValueError(
                    f"Demasiadas filas: {hoja.title}"
                )

            if (
                hoja.max_column is not None
                and hoja.max_column > MAX_COLUMNAS_EXCEL
            ):
                raise ValueError(
                    f"Demasiadas columnas: {hoja.title}"
                )

            # No confiar únicamente en las dimensiones
            # declaradas por el archivo.
            hoja.reset_dimensions()

            filas_con_datos = 0
            ultima_fila = 0
            ultima_columna = 0
            celdas_con_datos = 0
            vista_previa = []
            filas_completas = (
                [] if lectura_completa else None
            )
            tipos = set()

            for numero_fila, fila in enumerate(
                hoja.iter_rows(),
                start=1
            ):

                if numero_fila > MAX_FILAS_EXCEL:
                    raise ValueError(
                        f"Límite de filas excedido: "
                        f"{hoja.title}"
                    )

                if len(fila) > MAX_COLUMNAS_EXCEL:
                    raise ValueError(
                        f"Límite de columnas excedido: "
                        f"{hoja.title}"
                    )

                total_celdas += len(fila)

                if total_celdas > MAX_CELDAS_EXCEL:
                    raise ValueError(
                        "Demasiadas celdas para procesar."
                    )

                valores = []

                for numero_columna, celda in enumerate(
                    fila,
                    start=1
                ):

                    dato = _serializar_celda(celda)

                    if dato is None:
                        continue

                    celdas_con_datos += 1

                    ultima_columna = max(
                        ultima_columna,
                        numero_columna
                    )

                    tipos.add(dato["tipo"])

                    valores.append({
                        "columna": numero_columna,
                        **dato
                    })

                if valores:

                    filas_con_datos += 1
                    ultima_fila = numero_fila

                    registro_fila = {
                        "fila": numero_fila,
                        "celdas": valores
                    }

                    if len(vista_previa) < MAX_FILAS_PREVIA:

                        vista_previa.append(registro_fila)

                    if lectura_completa:

                        filas_completas.append(registro_fila)

            resultado["hojas"].append({
                "nombre": hoja.title,
                "visibilidad": hoja.sheet_state,
                "filas_con_datos": filas_con_datos,
                "ultima_fila_con_datos": ultima_fila,
                "ultima_columna_con_datos": ultima_columna,
                "celdas_con_datos": celdas_con_datos,
                "vacia": celdas_con_datos == 0,
                "tipos_detectados": sorted(tipos),
                "vista_previa": vista_previa
            })

            if lectura_completa:

                if len(filas_completas) != filas_con_datos:
                    raise ValueError(
                        "Lectura completa inconsistente."
                    )

                resultado["hojas"][-1][
                    "filas_completas"
                ] = filas_completas

        resultado["cantidad_hojas"] = len(
            resultado["hojas"]
        )

        resultado["celdas_procesadas"] = total_celdas

        if lectura_completa:
            resultado["lectura_completa"] = True

    finally:

        libro.close()

    return resultado



def _interpretar_coordenada_excel(referencia):
    """Interpreta una coordenada Excel con límites seguros."""

    import re

    coincidencia = re.fullmatch(
        r"([A-Z]{1,3})([1-9][0-9]{0,6})",
        referencia
    )

    if coincidencia is None:
        raise ValueError(
            f"Coordenada Excel inválida: {referencia}"
        )

    letras, numero = coincidencia.groups()

    fila = int(numero)
    columna = 0

    for letra in letras:

        columna = (
            columna * 26
            + ord(letra)
            - ord("A")
            + 1
        )

    if fila > MAX_FILAS_EXCEL:
        raise ValueError(
            "Coordenada supera el límite de filas."
        )

    if columna > MAX_COLUMNAS_EXCEL:
        raise ValueError(
            "Coordenada supera el límite de columnas."
        )

    return fila, columna


def validar_coordenadas_excel(contenido):
    """Comprueba coordenadas antes de abrir las hojas."""

    import posixpath

    ns = (
        "{http://schemas.openxmlformats.org/"
        "spreadsheetml/2006/main}"
    )

    ns_rel = (
        "{http://schemas.openxmlformats.org/"
        "package/2006/relationships}"
    )

    ns_id = (
        "{http://schemas.openxmlformats.org/"
        "officeDocument/2006/relationships}"
    )

    detalles = []
    total_celdas = 0
    total_rectangular = 0

    with zipfile.ZipFile(
        io.BytesIO(contenido), "r"
    ) as z:

        def leer_xml(nombre):

            entrada = z.getinfo(nombre)

            datos = _leer_entrada_controlada(
                z,
                entrada,
                MAX_ARCHIVO,
                conservar=True
            )

            return XML.fromstring(
                datos,
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True
            )

        libro = leer_xml("xl/workbook.xml")

        relaciones = leer_xml(
            "xl/_rels/workbook.xml.rels"
        )

        destinos = {}

        for relacion in relaciones:

            if relacion.tag != ns_rel + "Relationship":
                continue

            identificador = relacion.attrib.get("Id")

            if not identificador or identificador in destinos:
                raise ValueError(
                    "Relación XLSX inválida o duplicada."
                )

            destinos[identificador] = relacion

        hojas = libro.findall(
            ns + "sheets/" + ns + "sheet"
        )

        if not hojas:
            raise ValueError(
                "El Excel no contiene hojas compatibles."
            )

        if len(hojas) > MAX_HOJAS_EXCEL:
            raise ValueError(
                "El Excel contiene demasiadas hojas."
            )

        rutas_utilizadas = set()

        for hoja in hojas:

            identificador = hoja.attrib.get(
                ns_id + "id"
            )

            relacion = destinos.get(identificador)

            if relacion is None:
                raise ValueError(
                    "Hoja sin relación interna válida."
                )

            if not relacion.attrib.get(
                "Type", ""
            ).endswith("/worksheet"):

                raise ValueError(
                    "Tipo de hoja Excel no compatible."
                )

            destino = relacion.attrib.get(
                "Target", ""
            )

            if (
                not destino
                or chr(92) in destino
                or ":" in destino
                or ".." in destino.split("/")
            ):
                raise ValueError(
                    "Destino de hoja inseguro."
                )

            if destino.startswith("/"):

                ruta = destino.lstrip("/")

            else:

                ruta = posixpath.normpath(
                    posixpath.join("xl", destino)
                )

            if (
                not ruta.startswith("xl/worksheets/")
                or not ruta.endswith(".xml")
                or ruta not in z.namelist()
                or ruta in rutas_utilizadas
            ):
                raise ValueError(
                    "Ruta de hoja Excel inválida."
                )

            rutas_utilizadas.add(ruta)

            entrada = z.getinfo(ruta)

            fila_anterior = 0
            fila_actual = None
            columna_anterior = 0

            max_fila = 0
            max_columna = 0
            cantidad = 0

            pila = []

            with z.open(entrada, "r") as origen:

                eventos = XML.iterparse(
                    origen,
                    events=("start", "end"),
                    forbid_dtd=True,
                    forbid_entities=True,
                    forbid_external=True
                )

                for evento, elemento in eventos:

                    etiqueta = elemento.tag

                    if evento == "start":

                        pila.append(elemento)

                        if etiqueta == ns + "dimension":

                            referencia = elemento.attrib.get(
                                "ref", ""
                            )

                            extremos = referencia.split(":")

                            if len(extremos) not in (1, 2):
                                raise ValueError(
                                    "Dimensión Excel inválida."
                                )

                            for extremo in extremos:

                                _interpretar_coordenada_excel(
                                    extremo
                                )

                        elif etiqueta == ns + "row":

                            numero = elemento.attrib.get(
                                "r", ""
                            )

                            if (
                                not numero.isascii()
                                or not numero.isdigit()
                                or len(numero) > 7
                            ):
                                raise ValueError(
                                    "Número de fila inválido."
                                )

                            fila_actual = int(numero)

                            if (
                                fila_actual <= fila_anterior
                                or fila_actual > MAX_FILAS_EXCEL
                            ):
                                raise ValueError(
                                    "Fila duplicada, desordenada "
                                    "o fuera de límites."
                                )

                            fila_anterior = fila_actual
                            columna_anterior = 0

                            max_fila = max(
                                max_fila,
                                fila_actual
                            )

                        elif etiqueta == ns + "c":

                            referencia = elemento.attrib.get(
                                "r", ""
                            )

                            fila, columna = (
                                _interpretar_coordenada_excel(
                                    referencia
                                )
                            )

                            if fila != fila_actual:
                                raise ValueError(
                                    "Celda fuera de su fila."
                                )

                            if columna <= columna_anterior:
                                raise ValueError(
                                    "Celda duplicada o desordenada."
                                )

                            columna_anterior = columna

                            max_columna = max(
                                max_columna,
                                columna
                            )

                            cantidad += 1
                            total_celdas += 1

                            if total_celdas > MAX_CELDAS_EXCEL:
                                raise ValueError(
                                    "Demasiadas celdas XML."
                                )

                        elif etiqueta == ns + "f":

                            raise ValueError(
                                "El Excel contiene fórmulas "
                                "no permitidas."
                            )

                    else:

                        if etiqueta == ns + "row":
                            fila_actual = None

                        pila.pop()
                        elemento.clear()

                        if pila:
                            pila[-1].remove(elemento)

            total_rectangular += (
                max_fila * max_columna
            )

            if total_rectangular > MAX_CELDAS_EXCEL:

                raise ValueError(
                    "Dimensiones acumuladas excesivas."
                )

            detalles.append({
                "hoja": hoja.attrib.get("name"),
                "ruta": ruta,
                "filas": max_fila,
                "columnas": max_columna,
                "celdas_xml": cantidad
            })

    return {
        "coordenadas_validadas": True,
        "cantidad_hojas": len(detalles),
        "total_celdas_xml": total_celdas,
        "total_rectangular": total_rectangular,
        "hojas": detalles
    }
