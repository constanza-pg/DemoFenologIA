# FenologIA v1.0

Plataforma de monitoreo vitícola, seguimiento fenológico,
gestión de información agronómica y análisis experimental
de fotografías mediante inteligencia artificial.

## 1. Objetivo

Centralizar la información de cada viñedo, facilitando
el seguimiento individual de plantas, la interpretación
de indicadores agronómicos y la comparación temporal
de mediciones, fotografías y condiciones ambientales.

## 2. Funcionalidades

### Inicio
- Presentación de FenologIA.
- Acceso a recursos de aprendizaje y tutoriales.

### Diagnóstico
- Resumen del estado del viñedo.
- Indicadores agronómicos configurables.
- Alertas según umbrales definidos por el administrador.
- Comparación por cuartel y variedad.
- Identificación de plantas con indicadores fuera de rango.
- Diferenciación entre indicadores evaluados y no evaluables.

### Monitoreo
- Visualización geográfica de cuarteles y plantas.
- Filtros por cuartel, variedad e identificador.
- Consulta individual e histórica de mediciones.
- Visualización del claro monitoreado.
- Consulta de fotografías asociadas a las plantas.
- Carga de mediciones mediante archivos XLSX.
- Importación de capturas del dispositivo mediante ZIP.

### Meteorología
- Integración con Open-Meteo.
- Condiciones meteorológicas actuales.
- Pronóstico meteorológico.
- Historial de temperatura, humedad, precipitación,
  radiación solar y viento.
- Comparación entre periodos meteorológicos.

La información de Open-Meteo corresponde a estimaciones
meteorológicas de referencia. No sustituye las mediciones
directas realizadas por el dispositivo en el viñedo.

### Fotografías e IA
- Galería de fotografías por viñedo y planta.
- Consulta de fotografías del dispositivo.
- Detección experimental de racimos mediante YOLO-World.
- Selección y corrección manual de regiones de interés.
- Segmentación mediante SAM 2.
- Análisis de distribución de colores mediante HSV.
- Registro e historial de resultados.

### Mi viña
- Configuración general del viñedo.
- Registro de ubicación geográfica.
- Gestión de estructura vitícola.
- Configuración de claros monitoreados.
- Administración de usuarios.
- Configuración de indicadores agronómicos.
- Autorización para uso agregado de datos en investigación.

## 3. Perfiles de usuario

### Administrador
Gestiona su propio viñedo, usuarios, estructura,
mediciones, indicadores y autorizaciones.

### Usuario
Consulta la información de su viñedo y utiliza
las funciones de monitoreo y carga autorizadas.
No puede registrar estructuras vitícolas ni administrar
usuarios o modificar indicadores de alerta.

### Investigador
Perfil independiente sujeto a aprobación.
Dispone de una interfaz de consulta de información
agregada para fines de investigación.

La publicación y exportación de datos de investigación
permanecen deshabilitadas en esta versión hasta completar
la validación de privacidad correspondiente.

Los datos de prueba no forman parte del repositorio
de investigación.

## 4. Arquitectura

FenologIA utiliza una arquitectura modular basada en:

- Python y Streamlit para la aplicación web.
- SQLite para almacenamiento persistente.
- Pandas y NumPy para procesamiento de información.
- Plotly para visualización de datos.
- Folium para representación geográfica.
- Open-Meteo para información meteorológica.
- PyTorch, Ultralytics y OpenCV para análisis de imágenes.
- OpenPyXL para procesamiento de archivos Excel.

La plataforma separa la autenticación, el almacenamiento,
la interfaz, el procesamiento de imágenes, la meteorología
y la importación de datos en módulos especializados.

## 5. Organización del proyecto

    FenologIA_v1.0/
    |
    |-- app.py
    |-- database.py
    |-- autenticacion.py
    |-- configuracion_indicadores.py
    |-- meteorologia_local.py
    |-- analizador.py
    |-- analizador_fenologia.py
    |-- interfaz_fenologia.py
    |-- interfaz_investigacion.py
    |-- investigacion.py
    |-- importador_zip_dispositivo.py
    |-- motor_importacion_zip_dispositivo.py
    |-- gestionar_vinas.py
    |-- gestionar_investigadores.py
    |-- modulos/
    |-- servicios/
    |-- modelos/
    |-- weights/
    |-- data/
    |-- tutoriales/
    |-- requirements.txt
    |-- README.md

Existen módulos adicionales de validación, visualización,
procesamiento y vinculación de datos.

## 6. Instalación

Se recomienda Python 3.11, Git y un entorno virtual.

En macOS:

    python3.11 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    python -m pip check

Los modelos de inteligencia artificial deben encontrarse
en las rutas correspondientes:

    modelos/sam2_t.pt
    modelos/yolov8s-worldv2.pt
    weights/clip/ViT-B-32.pt

El manifiesto de modelos registra sus archivos y hashes
de integridad. Los pesos no se incluyen en GitHub.

## 7. Ejecución

Desde la carpeta principal:

    source .venv/bin/activate
    export SSL_CERT_FILE="$(python -m certifi)"
    python -m streamlit run app.py --server.port 8501

Abrir:

    http://localhost:8501

La base de datos predeterminada es data/vina.db.

Puede seleccionarse una base alternativa mediante
la variable de entorno VINA_DB_PATH.

Ejemplo:

    VINA_DB_PATH="$PWD/data/vina_pruebas.db" python -m streamlit run app.py

La base alternativa debe prepararse previamente
para el entorno de pruebas correspondiente.

## 8. Integración con el dispositivo

La plataforma admite la importación de archivos ZIP
generados según el formato compatible con el dispositivo.

El proceso contempla:

- Identificación del dispositivo.
- Validación de pertenencia al viñedo.
- Identificación de plantas.
- Lectura de mediciones ambientales.
- Vinculación de fotografías.
- Validación de fechas y estructura.
- Detección de duplicados.
- Comparación con el historial existente.
- Almacenamiento de capturas validadas.

La transferencia no requiere conectividad celular.

La validación del software de importación no equivale
a una certificación del funcionamiento físico del robot.

## 9. Seguridad y privacidad

- Autenticación mediante contraseñas protegidas con
  PBKDF2-SHA256.
- Control de acceso por roles y pertenencia al viñedo.
- Validación de permisos en operaciones del backend.
- Separación de datos de prueba y operacionales.
- Autorización de uso de información para investigación.
- Registro de auditoría de consultas de investigación.
- Protección de archivos privados mediante .gitignore.
- Verificación de integridad y claves foráneas en SQLite.
- Respaldos antes de modificaciones relevantes.

No deben publicarse bases de datos privadas, fotografías
de usuarios, credenciales ni archivos de configuración
sensibles.

## 10. Inteligencia artificial

YOLO-World proporciona propuestas de detección de racimos.
SAM 2 permite segmentar las regiones seleccionadas.
El procesamiento HSV estima la distribución de colores
dentro de las regiones segmentadas.

Los resultados son experimentales y pueden verse afectados
por iluminación, sombras, oclusiones, calidad fotográfica
y selección de las regiones de interés.

Los porcentajes de color no constituyen por sí solos
una determinación validada de madurez o etapa fenológica.

Se recomienda revisar manualmente cada resultado.

## 11. Tutoriales

La carpeta tutoriales contiene los recursos audiovisuales
utilizados por el centro de aprendizaje.

Consultar tutoriales/README.md para conocer los nombres
esperados y el estado de disponibilidad de los recursos.

## 12. Estado de la version

Version: 1.0
Fecha de consolidacion: noviembre de 2026
Estado: prototipo funcional academico.

La plataforma ha sido sometida a pruebas funcionales,
de integridad, autenticacion y permisos.

La validacion agronomica de los modelos, el testeo integral
del dispositivo fisico, la privacidad de publicaciones
de investigacion y la certificacion para produccion
comercial permanecen pendientes.
