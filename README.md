# SyllaBUG: Comparador de Guías Docentes (UGR)

SyllaBUG es una herramienta de control de versiones de bibliografías de guías docentes de la Universidad de Granada (UGR). Su objetivo es detectar cambios en la bibliografía de una asignatura entre el curso académico anterior y el actual para facilitar tareas de revisión y actualización.

## FUENTES DE DATOS
----------------
La herramienta trabaja con dos fuentes principales:

1) Guías firmadas en PDF (años anteriores)
   - Se descargan desde el portal de “guías docentes firmadas”.
   - Ejemplo: https://grados.ugr.es/sites/grados/default/public/guias-firmadas/2024-2025/2421117.pdf

2) Guías docentes en HTML (año actual)
   - Se extraen desde las páginas web oficiales de las guías.
   - Ejemplo: https://derecho.ugr.es/docencia/grados/graduadoa-derecho/derechos-humanosigualdad-y-sistemas-proteccion/11/guia-docente

## ¿QUÉ HACE EL PROYECTO?
---------------------
1) Extracción de bibliografías del año anterior (PDF)
   - Descarga las guías firmadas y extrae el bloque de bibliografía aplicando filtros para reducir “ruido” típico del PDF (cabeceras, secciones no relevantes, etc.).

2) Extracción de bibliografías del año actual (HTML)
   - Localiza/normaliza la URL de “.../guia-docente” y extrae bibliografía (fundamental/complementaria) desde el HTML de forma más fiable.

3) Comparación de bibliografías entre cursos y generación de informes
   - Para cada asignatura (por código), genera una salida con:
     * Recursos eliminados
     * Recursos añadidos
     * Recursos sin cambios
     * Un porcentaje estimado de cambio
   - La comparación intenta ser robusta ante pequeñas variaciones (ediciones, años, editoriales, etc.) usando normalización y similitud de texto (fuzzy matching).

## INTERFAZ WEB
----------------------
El repositorio incluye una pequeña app web (Flask) para visualizar comparativas de forma cómoda, filtrando por biblioteca y grados (a partir de un Excel de mapeo) y mostrando las comparativas ordenadas por número de cambios.

El programa se encuentra desplegado en la nube con Render y se puede consultar en el siguiente enlace: https://syllabug.onrender.com/

## ESTRUCTURA DE SALIDA 
------------------------------
Las bibliografías y comparativas se guardan en una estructura tipo:

- BibliografiasUGR/grados/<curso>/...              (TXT por asignatura)
- BibliografiasUGR/grados/Comparativas/<grado>/... (comparativas generadas)


## SCRIPTS PRINCIPALES
-------------------
- extraer_bibiografias_2425.py : extracción desde PDFs firmados (año anterior)
- extraer_bibliografias_2526.py: extracción desde HTML (año actual)
- comparar.py                  : genera comparativas (añadidos/eliminados/iguales) y métricas
- app.py                       : interfaz web Flask para explorar resultados
