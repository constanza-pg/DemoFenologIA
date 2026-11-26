# FenologIA

### Plataforma inteligente de monitoreo e investigación vitivinícola

FenologIA es un prototipo académico orientado al monitoreo
individual de plantas, la visualización geoespacial y el
análisis de información vitícola mediante inteligencia artificial.

## Objetivo

Centralizar información vitícola, ambiental y fotográfica
para facilitar el seguimiento de los viñedos y apoyar
la toma de decisiones.

## Perfiles de acceso

### Gestión vitícola

- Administración independiente de cada viña.
- Gestión de usuarios y permisos.
- Registro de plantas y estructura del viñedo.
- Consulta e incorporación de mediciones.
- Monitoreo individual e histórico.

### Investigación vitivinícola

- Registro y aprobación de investigadores.
- Exploración de información agrupada.
- Filtros por región, variedad y período.
- Comparación de indicadores.
- Exportación de datos sintéticos en CSV y XLSX.
- Autorizaciones de participación de viñas.

El perfil investigador utiliza actualmente datos sintéticos.
El acceso a información real requiere validaciones adicionales
de privacidad y seguridad.

## Funcionalidades de la plataforma

### Inicio

- Accesos rápidos a las herramientas.
- Centro de ayuda, presentación y videotutoriales.

### Diagnóstico

- Resumen de indicadores vitícolas.
- Identificación de alertas por planta.
- Gráficos y contexto meteorológico.
- Apoyo a la toma de decisiones.

### Mapa y monitoreo

- Mapa interactivo de plantas y cuarteles.
- Filtros por fecha, variedad y cuartel.
- Consulta individual e histórica de plantas.
- Fotografías asociadas.
- Importación de mediciones mediante XLSX.

### Meteorología

- Integración con Open-Meteo.
- Condiciones meteorológicas actuales.
- Historial y pronóstico meteorológico.
- Información referencial según coordenadas.

### Fotografías e inteligencia artificial

- Galería fotográfica.
- Detección asistida mediante YOLO-World.
- Segmentación de racimos mediante SAM 2.
- Selección y corrección manual de racimos.
- Clasificación experimental de colores.
- Historial de resultados.

### Mi viña

- Información general y ubicación geográfica.
- Configuración del claro monitoreado.
- Configuración de indicadores.
- Plantillas de importación.
- Administración de usuarios.
- Autorizaciones de investigación.

La integración de los indicadores personalizados
con el sistema de alertas se encuentra en desarrollo.

## Integración con dispositivos

- Importación de archivos ZIP.
- Validación de dispositivos y archivos.
- Registro de temperatura y humedad ambiental.
- Asociación de fotografías con plantas.
- Historial de capturas.
- Detección de registros duplicados.

## Tecnologías

- Python y Streamlit.
- SQLite.
- Pandas y NumPy.
- Plotly y Folium.
- Geopy y Open-Meteo.
- OpenCV y Pillow.
- PyTorch y Torchvision.
- YOLO-World y SAM 2.

## Instalación

Se recomienda utilizar Python 3.11 y Git.

```bash
git clone https://github.com/constanza-pg/DemoFenologIA.git
cd DemoFenologIA
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Generar datos de demostración

```bash
python inicializar_demo.py
```

El generador está diseñado para crear:

- 10.920 plantas ficticias.
- 65.520 mediciones sintéticas.
- 4 cuarteles.
- 6 fechas de monitoreo.

Usuario de demostración: demo@example.com

La contraseña se establece localmente durante
la inicialización.

## Ejecutar FenologIA

```bash
python -m streamlit run app.py
```

Abrir http://localhost:8501 en el navegador.

Las funciones meteorológicas, la geocodificación
y los fondos cartográficos requieren internet.

## Arquitectura del proyecto

| Módulo | Responsabilidad |
|---|---|
| app.py | Interfaz principal |
| database.py | Base de datos |
| autenticacion.py | Autenticación y permisos |
| estilos_fenologia.py | Diseño visual |
| meteorologia_local.py | Integración Open-Meteo |
| analizador_fenologia.py | Análisis de racimos |
| interfaz_fenologia.py | Editor de fotografías |
| investigacion.py | Consultas y autorizaciones |
| interfaz_investigacion.py | Perfil investigador |
| datos_demo_investigacion.py | Datos sintéticos |
| configuracion_indicadores.py | Criterios de alerta |
| interfaz_indicadores.py | Configuración de indicadores |
| regiones_chile.py | Catálogo territorial |
| inicializar_demo.py | Generador de demostración |

## Modelos de inteligencia artificial

- sam2_t.pt
- yolov8s-worldv2.pt

Los pesos deben obtenerse mediante Ultralytics.
No se incluyen en el repositorio.

## Seguridad y privacidad

- Contraseñas protegidas mediante PBKDF2-SHA256.
- Separación de información por viña.
- Control de acceso según roles.
- Autorizaciones para investigación.
- Validación de permisos administrativos.

## Estado del proyecto

Prototipo académico en desarrollo.

Aspectos pendientes:

- Integración de indicadores personalizados con alertas.
- Validación agronómica de los análisis de IA.
- Validación de privacidad para investigación.
- Incorporación de videotutoriales.
- Preparación para producción.

Los datos de demostración son sintéticos.
La información meteorológica es referencial.
FenologIA no sustituye la evaluación profesional en terreno.
