import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import os
import re
from datetime import datetime, timedelta
from itertools import islice
import csv
import pandas as pd

sitemap_urls = [
    "https://www.ugr.es/sitemap.xml?page=8",
    "https://www.ugr.es/sitemap.xml?page=9",
    "https://www.ugr.es/sitemap.xml?page=10",
    "https://www.ugr.es/sitemap.xml?page=11"
]

BASE_PATH = "BibliografiasUGR"
ULTIMA_EJECUCION_PATH = os.path.join(BASE_PATH, "ultima_ejecucion.txt")
CODIGO_REGEX = re.compile(r"\b\d{7,8}[A-Z]?\b")
FECHA_HOY = datetime.now().strftime("%Y-%m-%d")
CAMBIADAS_COMPLETAMENTE_PATH = os.path.join(BASE_PATH, f"Asignaturas_cambiadas_por_completo_{FECHA_HOY}.txt")
FACULTADES_DESCONOCIDAS_PATH = os.path.join(BASE_PATH, f"Facultades_no_encontradas_{FECHA_HOY}.txt")
MAPEO_PATH = os.path.join(BASE_PATH, "mapeo_asignaturas.csv")
GRADOS_ALIAS_PATH = os.path.join(BASE_PATH, "grados_alias.csv")

asignaturas_por_cambio = {
    "100%": [],
    "80-99%": [],
    "50-79%": []
}

urls_facultad_desconocida = []

mapeo_manual = {}
if os.path.exists(MAPEO_PATH):
    df = pd.read_csv(MAPEO_PATH)
    for _, row in df.iterrows():
        clave = (row["grado"].strip(), row["asignatura"].strip())
        mapeo_manual[clave] = row["facultad"].strip()
else:
    with open(MAPEO_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["grado", "asignatura", "facultad"])

grados_alias = {}
if os.path.exists(GRADOS_ALIAS_PATH):
    df_alias = pd.read_csv(GRADOS_ALIAS_PATH)
    for _, row in df_alias.iterrows():
        grados_alias[row["grado_slug"].strip()] = row["grado_normalizado"].strip()

def slug(texto):
    return re.sub(r"[^\w\-]", "-", texto.strip().replace(" ", "-")).strip("-")

def comprobar_fecha_ejecucion():
    if os.path.exists(ULTIMA_EJECUCION_PATH):
        with open(ULTIMA_EJECUCION_PATH, "r", encoding="utf-8") as f:
            try:
                ultima_fecha = datetime.strptime(f.read().strip(), "%Y-%m-%d")
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

def batch(iterable, n):
    it = iter(iterable)
    while True:
        b = list(islice(it, n))
        if not b:
            break
        yield b

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

def obtener_fecha_archivo(ruta):
    if os.path.exists(ruta):
        timestamp = os.path.getmtime(ruta)
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    return "¿?"

def comparar_bibliografias(antigua, nueva, fecha_antigua, fecha_nueva):
    set_antigua = set(sorted(antigua))
    set_nueva = set(sorted(nueva))
    añadidos = list(set_nueva - set_antigua)
    eliminados = list(set_antigua - set_nueva)
    total_union = len(set_antigua | set_nueva)
    diferencias = len(set_antigua ^ set_nueva)
    porcentaje_cambio = diferencias / total_union if total_union else 0

    resumen = [
        f"📅 Comparativa entre: {fecha_antigua} (antiguo) y {fecha_nueva} (nuevo)",
        f"📊 Porcentaje estimado de cambio: {int(porcentaje_cambio * 100)}% [{'█' * int(porcentaje_cambio * 10)}{'░' * (10 - int(porcentaje_cambio * 10))}]",
        f"Total en antigua: {len(set_antigua)}",
        f"Total en nueva: {len(set_nueva)}",
        f"Recursos añadidos ({len(añadidos)}):"
    ] + [f"• {r}" for r in sorted(añadidos)] + [
        f"\nRecursos eliminados ({len(eliminados)}):"
    ] + [f"• {r}" for r in sorted(eliminados)]

    return "\n".join(resumen), porcentaje_cambio

async def extraer_urls_de_sitemap(session, sitemap_url):
    print(f"🔎 Leyendo sitemap: {sitemap_url}")
    async with session.get(sitemap_url) as resp:
        texto = await resp.text()
    soup = BeautifulSoup(texto, "lxml-xml")
    return [loc.text.strip() for loc in soup.find_all("loc") if es_url_valida(loc.text.strip())]

async def obtener_facultad(session, base_url, grado, asignatura):
    try:
        async with session.get(base_url, timeout=10) as resp:
            if resp.status != 200:
                raise Exception("HTTP error")
            html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        for fila in soup.find_all("tr"):
            if "centro" in fila.get_text(strip=True).lower():
                td = fila.find("td")
                if td:
                    facultad = td.get_text(strip=True)
                    if facultad:
                        return slug(facultad)
        print(f"❓ No se encontró facultad para: {base_url}")
    except Exception as e:
        print(f"⚠️ No se pudo extraer facultad de {base_url}: {e}")

    clave = (grado.strip(), asignatura.strip())
    if clave in mapeo_manual:
        return slug(mapeo_manual[clave])
    urls_facultad_desconocida.append(base_url)
    return "Facultad-Desconocida"

async def registrar_mapeo(grado, asignatura, facultad):
    clave = (grado.strip(), asignatura.strip())
    if clave not in mapeo_manual:
        with open(MAPEO_PATH, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([grado.strip(), asignatura.strip(), facultad.strip()])
        mapeo_manual[clave] = facultad.strip()

async def procesar_url(session, base_url):
    url = construir_url_guia_docente(base_url)
    print(f"📘 Procesando: {url}")
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()

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
        grado_slug = grados_alias.get(grado_slug, grado_slug)

        facultad_slug = await obtener_facultad(session, base_url, grado_slug, nombre_asignatura)
        await registrar_mapeo(grado_slug, nombre_asignatura, facultad_slug)

        carpeta_tipo = os.path.join(BASE_PATH, tipo)
        carpeta_nuevas = os.path.join(carpeta_tipo, "Nuevas", grado_slug)
        carpeta_antiguas = os.path.join(carpeta_tipo, "Antiguas", grado_slug)
        carpeta_comparativas = os.path.join(carpeta_tipo, "Comparativas", grado_slug)

        os.makedirs(carpeta_nuevas, exist_ok=True)
        os.makedirs(carpeta_antiguas, exist_ok=True)
        os.makedirs(carpeta_comparativas, exist_ok=True)

        nombre_archivo = f"{nombre_limpio}.txt"
        ruta_nueva = os.path.join(carpeta_nuevas, nombre_archivo)
        ruta_antigua = os.path.join(carpeta_antiguas, nombre_archivo)
        ruta_comparativa = os.path.join(carpeta_comparativas, nombre_archivo)

        if os.path.exists(ruta_nueva):
            os.makedirs(os.path.dirname(ruta_antigua), exist_ok=True)
            os.replace(ruta_nueva, ruta_antigua)

        with open(ruta_nueva, "w", encoding="utf-8") as f:
            for entrada in bibliografia:
                f.write(entrada + "\n")

        if os.path.exists(ruta_antigua):
            with open(ruta_antigua, "r", encoding="utf-8") as f:
                antigua = [line.strip() for line in f.readlines()]
            fecha_antigua = obtener_fecha_archivo(ruta_antigua)
            fecha_nueva = obtener_fecha_archivo(ruta_nueva)
            comparativa, porcentaje_cambio = comparar_bibliografias(antigua, bibliografia, fecha_antigua, fecha_nueva)

            with open(ruta_comparativa, "w", encoding="utf-8") as f:
                f.write(comparativa)

            if porcentaje_cambio >= 1.0:
                asignaturas_por_cambio["100%"].append(nombre_asignatura)
            elif porcentaje_cambio >= 0.80:
                asignaturas_por_cambio["80-99%"].append(nombre_asignatura)
            elif porcentaje_cambio >= 0.50:
                asignaturas_por_cambio["50-79%"].append(nombre_asignatura)

        return ruta_nueva

    except Exception as e:
        print(f"⚠️ Error procesando {url}: {e}")
        return None


async def guardar_asignaturas_cambiadas():
    if any(asignaturas_por_cambio.values()):
        with open(CAMBIADAS_COMPLETAMENTE_PATH, "w", encoding="utf-8") as f:
            for clave, titulo in [
                ("100%", "📘 Asignaturas con CAMBIO DEL 100%"),
                ("80-99%", "📙 Asignaturas con CAMBIO del 80–99%"),
                ("50-79%", "📒 Asignaturas con CAMBIO del 50–79%")
            ]:
                if asignaturas_por_cambio[clave]:
                    f.write(titulo + "\n")
                    for nombre in sorted(asignaturas_por_cambio[clave]):
                        f.write(f"{nombre}\n")
                    f.write("\n")

    if urls_facultad_desconocida:
        with open(FACULTADES_DESCONOCIDAS_PATH, "w", encoding="utf-8") as f:
            f.write("🔍 URLs con facultad no detectada:\n\n")
            for url in sorted(urls_facultad_desconocida):
                f.write(url + "\n")

async def main(callback=None):
    if not comprobar_fecha_ejecucion():
        return

    async with aiohttp.ClientSession() as session:
        todas_las_urls = []
        for sitemap_url in sitemap_urls:
            urls = await extraer_urls_de_sitemap(session, sitemap_url)
            todas_las_urls.extend(urls)

        print(f"🔗 Total de URLs a procesar: {len(todas_las_urls)}")

        batch_size = 100
        procesadas = 0
        total = len(todas_las_urls)

        for i, grupo in enumerate(batch(todas_las_urls, batch_size)):
            print(f"🚀 Lote {i+1} con {len(grupo)} URLs")
            tareas = [procesar_url(session, url) for url in grupo]
            await asyncio.gather(*tareas)
            procesadas += len(grupo)
            if callback:
                callback(int(procesadas / total * 100), f"Lote {i+1}")

        registrar_fecha_ejecucion()
        await guardar_asignaturas_cambiadas()

        return {
            "tipo": "GRADOS",
            "total_cambiadas": sum(len(v) for v in asignaturas_por_cambio.values()),
            "cambios": asignaturas_por_cambio
        }

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        raise RuntimeError("❌ Error al ejecutar 'extraer_bibliografia_toda_ugr.py': " + str(e))
