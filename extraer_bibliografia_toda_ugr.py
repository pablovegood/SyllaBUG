import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

# URLs de los sitemaps de UGR
sitemap_urls = [
    "https://www.ugr.es/sitemap.xml?page=8",
    "https://www.ugr.es/sitemap.xml?page=9",
    "https://www.ugr.es/sitemap.xml?page=10",
    "https://www.ugr.es/sitemap.xml?page=11"
]

# Rutas y configuración
BASE_PATH = "BibliografiasUGR"
ULTIMA_EJECUCION_PATH = os.path.join(BASE_PATH, "ultima_ejecucion.txt")
CODIGO_REGEX = re.compile(r"\b\d{7,8}[A-Z]?\b")
FECHA_HOY = datetime.now().strftime("%Y-%m-%d")
CAMBIADAS_COMPLETAMENTE_PATH = os.path.join(BASE_PATH, f"Asignaturas_cambiadas_por_completo_{FECHA_HOY}.txt")

# Estructura para clasificar cambios por porcentaje
asignaturas_por_cambio = {
    "100%": [],
    "80-99%": [],
    "50-79%": []
}


def comprobar_fecha_ejecucion():
    if os.path.exists(ULTIMA_EJECUCION_PATH):
        with open(ULTIMA_EJECUCION_PATH, "r", encoding="utf-8") as f:
            fecha_str = f.read().strip()
            try:
                ultima_fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
                if datetime.now() - ultima_fecha < timedelta(days=7):
                    print("⏳ Ya se ejecutó en la última semana. Abortando ejecución.")
                    return False
            except Exception as e:
                print(f"⚠️ No se pudo interpretar la fecha de última ejecución: {e}")
    return True


def registrar_fecha_ejecucion():
    os.makedirs(BASE_PATH, exist_ok=True)
    with open(ULTIMA_EJECUCION_PATH, "w", encoding="utf-8") as f:
        f.write(FECHA_HOY)


def extraer_urls_de_sitemap(sitemap_url):
    print(f"🔎 Leyendo sitemap: {sitemap_url}")
    r = requests.get(sitemap_url)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "lxml-xml")
    return [loc.text.strip() for loc in soup.find_all("loc")]


def es_url_valida(url):
    return url.startswith("https://www.ugr.es/estudiantes/grados/")


def construir_url_guia_docente(url):
    return url.rstrip("/") + "/guia-docente"


def extraer_bibliografia_desde_html(html):
    soup = BeautifulSoup(html, "html.parser")
    bibliografia = []

    for h3 in soup.find_all("h3"):
        texto_h3 = h3.get_text(strip=True)
        if "Metodología docente" in texto_h3 or "Enlaces recomendados" in texto_h3:
            break

        if "Bibliografía fundamental" in texto_h3 or "Bibliografía complementaria" in texto_h3:
            div_contenido = h3.find_next_sibling(lambda tag: tag.name == "div")
            if div_contenido:
                for elem in div_contenido.descendants:
                    if elem.name in ["p", "li"] and elem.get_text(strip=True):
                        bibliografia.append(elem.get_text(strip=True))

    return bibliografia


def comparar_bibliografias(antigua, nueva):
    antigua_ordenada = sorted(set(antigua))
    nueva_ordenada = sorted(set(nueva))

    set_antigua = set(antigua_ordenada)
    set_nueva = set(nueva_ordenada)

    añadidos = list(set_nueva - set_antigua)
    eliminados = list(set_antigua - set_nueva)

    total_antigua = len(set_antigua)
    interseccion = len(set_antigua & set_nueva)
    porcentaje_cambio = 1.0

    if total_antigua > 0:
        porcentaje_cambio = 1 - (interseccion / total_antigua)

    resumen = []
    if porcentaje_cambio == 1.0:
        resumen.append("📢 La bibliografía fue cambiada por completo.\n")

    resumen += [
        f"Total en antigua: {len(set_antigua)}",
        f"Total en nueva: {len(set_nueva)}",
        f"Recursos añadidos ({len(añadidos)}):"
    ] + sorted(añadidos) + [
        f"\nRecursos eliminados ({len(eliminados)}):"
    ] + sorted(eliminados)

    return "\n".join(resumen), porcentaje_cambio


def procesar_url(base_url):
    url = construir_url_guia_docente(base_url)
    print(f"📘 Procesando: {url}")
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        html = response.text
        bibliografia = extraer_bibliografia_desde_html(html)
        if not bibliografia:
            return None

        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        nombre_asignatura = h1.get_text(strip=True) if h1 else "asignatura"
        nombre_limpio = re.sub(r'[\\/*?:"<>|]', "", nombre_asignatura).replace(" ", "_")[:100]

        tipo = "grados"
        parsed_url = urlparse(base_url)
        parts = parsed_url.path.strip("/").split("/")
        grado_slug = parts[2] if len(parts) >= 4 else "grado-desconocido"

        carpeta_tipo = os.path.join(BASE_PATH, tipo)
        carpeta_nuevas = os.path.join(carpeta_tipo, "Nuevas", grado_slug)
        carpeta_antiguas = os.path.join(carpeta_tipo, "Antiguas", grado_slug)
        carpeta_comparativas = os.path.join(carpeta_tipo, "Comparativas", grado_slug)

        os.makedirs(carpeta_nuevas, exist_ok=True)
        os.makedirs(carpeta_antiguas, exist_ok=True)
        os.makedirs(carpeta_comparativas, exist_ok=True)

        ruta_nueva = os.path.join(carpeta_nuevas, f"{nombre_limpio}.txt")
        ruta_antigua = os.path.join(carpeta_antiguas, f"{nombre_limpio}.txt")
        ruta_comparativa = os.path.join(carpeta_comparativas, f"{nombre_limpio}.txt")

        if os.path.exists(ruta_nueva):
            os.replace(ruta_nueva, ruta_antigua)

        with open(ruta_nueva, "w", encoding="utf-8") as f:
            for entrada in bibliografia:
                f.write(entrada + "\n")

        if os.path.exists(ruta_antigua):
            with open(ruta_antigua, "r", encoding="utf-8") as f:
                antigua = [line.strip() for line in f.readlines()]
            comparativa, porcentaje_cambio = comparar_bibliografias(antigua, bibliografia)

            # Barra visual
            bloques_totales = 10
            bloques_cambio = int(round(porcentaje_cambio * bloques_totales))
            barra = "█" * bloques_cambio + "░" * (bloques_totales - bloques_cambio)
            porcentaje_texto = f"{int(round(porcentaje_cambio * 100))}%"
            encabezado_visual = f"\n📊 Porcentaje estimado de cambio: {porcentaje_texto} [{barra}]\n\n"

            with open(ruta_comparativa, "w", encoding="utf-8") as f:
                f.write(encabezado_visual)
                f.write(comparativa)

            print(f"🔍 Comparativa generada: {ruta_comparativa}")

            if porcentaje_cambio >= 1.0:
                asignaturas_por_cambio["100%"].append(nombre_asignatura)
            elif porcentaje_cambio >= 0.80:
                asignaturas_por_cambio["80-99%"].append(nombre_asignatura)
            elif porcentaje_cambio >= 0.50:
                asignaturas_por_cambio["50-79%"].append(nombre_asignatura)

        else:
            print(f"📥 Primera versión registrada de {nombre_asignatura}")

        print(f"✅ Guardado: {ruta_nueva}")
        return ruta_nueva
    except Exception as e:
        print(f"⚠️ Error procesando {url}: {e}")
        return None


def guardar_asignaturas_cambiadas():
    if any(asignaturas_por_cambio.values()):
        with open(CAMBIADAS_COMPLETAMENTE_PATH, "w", encoding="utf-8") as f:
            if asignaturas_por_cambio["100%"]:
                f.write("📘 Asignaturas con CAMBIO DEL 100%\n")
                for nombre in sorted(asignaturas_por_cambio["100%"]):
                    f.write(f"{nombre}\n")
                f.write("\n")

            if asignaturas_por_cambio["80-99%"]:
                f.write("📙 Asignaturas con CAMBIO del 80–99%\n")
                for nombre in sorted(asignaturas_por_cambio["80-99%"]):
                    f.write(f"{nombre}\n")
                f.write("\n")

            if asignaturas_por_cambio["50-79%"]:
                f.write("📒 Asignaturas con CAMBIO del 50–79%\n")
                for nombre in sorted(asignaturas_por_cambio["50-79%"]):
                    f.write(f"{nombre}\n")


def main():
    if not comprobar_fecha_ejecucion():
        return

    todas_las_urls = []
    for sitemap_url in sitemap_urls:
        urls = extraer_urls_de_sitemap(sitemap_url)
        urls_filtradas = list(filter(es_url_valida, urls))
        todas_las_urls.extend(urls_filtradas)

    print(f"🔗 Total de URLs a procesar: {len(todas_las_urls)}")

    with ThreadPoolExecutor(max_workers=20) as executor:
        resultados = list(executor.map(procesar_url, todas_las_urls))

    resultados_filtrados = [r for r in resultados if r]
    print(f"📚 Bibliografías guardadas: {len(resultados_filtrados)}")

    registrar_fecha_ejecucion()
    guardar_asignaturas_cambiadas()

    return {
        "tipo": "GRADOS",
        "total_cambiadas": sum(len(v) for v in asignaturas_por_cambio.values()),
        "cambios": asignaturas_por_cambio
    }


if __name__ == "__main__":
    main()
