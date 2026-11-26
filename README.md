# FenologIA

Plataforma inteligente de monitoreo fenológico y ambiental
para viñedos.

## Descripción

FenologIA es un prototipo académico orientado al monitoreo
individual de plantas, la visualización geoespacial de
mediciones y el análisis de información vitícola.

## Funcionalidades actuales

- Mapa interactivo de plantas y cuarteles.
- Monitoreo individual e histórico de plantas.
- Visualización de indicadores vitícolas.
- Resumen y diagnóstico mediante alertas.
- Registro de viñas, usuarios y dispositivos.
- Gestión de permisos de usuario y administrador.
- Importación de archivos CSV, XLSX y ZIP.
- Historial de capturas ambientales.
- Galería fotográfica y análisis mediante IA.
- Integración de información meteorológica.

## Tecnologías

- Python
- Streamlit
- SQLite
- Pandas y NumPy
- Plotly
- Folium
- Inteligencia artificial y visión computacional

## Instalación

Se recomienda utilizar Python 3.11.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Generar datos de demostración

```bash
python inicializar_demo.py
```

El script solicita crear una contraseña y genera:

- 10.920 plantas ficticias.
- 65.520 mediciones.
- 4 cuarteles.
- 6 fechas de monitoreo.

Usuario de demostración: demo@example.com

## Ejecutar la plataforma

```bash
python -m streamlit run app.py
```

Abrir http://localhost:8501 en el navegador.

## Estado del proyecto

Prototipo académico funcional en desarrollo.

Los datos de demostración son sintéticos y no corresponden
a mediciones reales de un viñedo.

Las funcionalidades de inteligencia artificial pueden
requerir dependencias, modelos y credenciales adicionales.
La demostración no incluye históricos meteorológicos,
fotografías originales ni datos de dispositivos físicos.

Por seguridad, el repositorio no incluye bases de datos
privadas, contraseñas ni claves API.

## Proyecto

FenologIA busca integrar tecnologías de monitoreo,
visualización e inteligencia artificial como herramientas
de apoyo a la gestión vitícola.
