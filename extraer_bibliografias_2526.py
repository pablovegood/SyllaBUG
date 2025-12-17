import aiohttp
import asyncio
from bs4 import BeautifulSoup, Tag
from urllib.parse import urlparse, urljoin
import os
import re
import pandas as pd
from itertools import islice

''' A continuación se muestran los enlaces que redirigen a distintas páginas dentro de https://www.ugr.es/sitemap,
en concreto de la 8 a la 11 que son las páginas donde se encuentran los enlaces de las páginas de las diferentes 
asignaturas de los grados de la UGR, es posible que si el sitemap crece en el futuro, se tengan que añadir más líneas
de código indicando https://www.ugr.es/sitemap.xml?page=12 ... https://www.ugr.es/sitemap.xml?page=n según corresponda'''
sitemap_urls = [
    "https://www.ugr.es/sitemap.xml?page=8",
    "https://www.ugr.es/sitemap.xml?page=9",
    "https://www.ugr.es/sitemap.xml?page=10",
    "https://www.ugr.es/sitemap.xml?page=11",
    # "https://www.ugr.es/sitemap.xml?page=12",
]

''' Esta sección del código viene a indicar en que directorios (carpetas) dentro de la estructura del proyecto se 
 guardarán las bibliografías de las guías docentes: hay que tener cuidado con  GRADOS_PATH, ya que si no se modifican
 los nombres de un años para otro, '''
BASE_PATH = "BibliografiasUGR"
GRADOS_PATH = os.path.join(BASE_PATH, "grados", "2026-2027")
MAPEO_PATH = os.path.join(BASE_PATH, "mapeo_asignaturas.csv")
GRADOS_ALIAS_PATH = os.path.join(BASE_PATH, "grados_alias.csv")

# -------- Carga de mapeos opcionales --------
mapeo_manual = {}
if os.path.exists(MAPEO_PATH):
    df = pd.read_csv(MAPEO_PATH)
    for _, row in df.iterrows():
        clave = (row["grado"].strip(), row["asignatura"].strip())
        mapeo_manual[clave] = row["facultad"].strip()

grados_alias = {}
if os.path.exists(GRADOS_ALIAS_PATH):
    df_alias = pd.read_csv(GRADOS_ALIAS_PATH)
    for _, row in df_alias.iterrows():
        grados_alias[row["grado_slug"].strip()] = row["grado_normalizado"].strip()

# -------- Cache prefijos por grado --------
# Guardará, para cada grado, los 3 primeros CARACTERES del código de asignatura (p. ej., "2TC", "turismo-238", "205")
grado_prefijos = {}

# -------- Utilidades generales --------
def slug(texto: str) -> str:
    return re.sub(r"[^\w\-]", "-", texto.strip().replace(" ", "-")).strip("-")

def es_url_valida(url: str) -> bool:
    return (
        url.startswith("https://www.ugr.es/estudiantes/grados/")
        or url.startswith("https://grados.ugr.es/")
    )

def construir_url_guia_docente(url: str) -> str:
    u = url.rstrip("/")
    return u if u.endswith("/guia-docente") else (u + "/guia-docente")

def batch(iterable, n):
    it = iter(iterable)
    while True:
        b = list(islice(it, n))
        if not b:
            break
        yield b

# --- EXTRACCIÓN DE CÓDIGO (robusta) ---
# 1) Entre paréntesis: capta alfanuméricos de 5-12 chars: 2TC1113, 20511F2, 23811B1, etc.
COD_RE_STRICT = re.compile(r"\(([A-Za-z0-9]{5,12})\)")
# 2) Cerca de 'pdf' por si el ( ) está roto: "... 2TC1113 ) pdf"
COD_NEAR_PDF = re.compile(r"([A-Za-z0-9]{5,12})\s*\)*\s*pdf", re.IGNORECASE)

def extraer_codigo_asignatura(nombre_asignatura: str, html: str | None = None) -> str:
    m = COD_RE_STRICT.search(nombre_asignatura or "")
    if m:
        return m.group(1)

    m2 = COD_NEAR_PDF.search(nombre_asignatura or "")
    if m2:
        return m2.group(1)

    if html:
        m3 = COD_RE_STRICT.search(html)
        if m3:
            return m3.group(1)
        m4 = COD_NEAR_PDF.search(html)
        if m4:
            return m4.group(1)

    return "SIN_CODIGO"

def prefijo_grado_desde_codigo(cod: str) -> str:
    """
    Devuelve los 3 primeros CARACTERES del código de la asignatura.
    Si no hay código, usa '000' como marcador temporal.
    """
    if not cod or cod == "SIN_CODIGO":
        return "000"
    return cod[:3]

def limpiar_titulo_para_nombre(nombre: str) -> str:
    """
    - Quita 'Guía docente de ' o 'Guía docente ' al principio.
    - Quita '(pdf)' o 'pdf' residuales.
    - Quita el código entre paréntesis del título.
    - Conserva acentos y mayúsculas/minúsculas del texto original.
    """
    s = nombre or ""
    s = re.sub(r"(?i)^gu[ií]a\s+docente(?:\s+de)?\s+", "Guia_docente_", s.strip())
    s = re.sub(r"\s*\(([A-Za-z0-9]{5,12})\)\s*", " ", s)  # quita el código entre paréntesis
    s = re.sub(r"\s*\(?\s*pdf\s*\)?\s*", " ", s, flags=re.IGNORECASE)  # quita (pdf)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def generar_nombre_archivo(nombre_asignatura: str, codigo: str) -> str:
    """
    Devuelve un nombre tipo:
      Guia_docente_Circuitos_y_Sistemas_Electrónicos_para_Aplicaciones_Biomédicas_20511F2.txt
    Sin '(pdf)' y conservando el título legible.
    """
    base = limpiar_titulo_para_nombre(nombre_asignatura)
    # Eliminar caracteres no válidos en sistemas de ficheros y convertir espacios en '_'
    base = re.sub(r"[\\/*?\"<>|]", "", base).replace(" ", "_")
    if codigo and codigo != "SIN_CODIGO":
        return f"{base}_{codigo}.txt"
    else:
        return f"{base}_SIN_CODIGO.txt"

def grado_slug_desde_url(u: str) -> str:
    p = urlparse(u)
    parts = [s for s in p.path.strip("/").split("/") if s]

    slug_candidato = "grado-desconocido"
    if p.netloc == "www.ugr.es":
        if len(parts) >= 3 and parts[0] == "estudiantes" and parts[1] == "grados":
            slug_candidato = parts[2]
    elif p.netloc == "grados.ugr.es":
        if len(parts) >= 1:
            slug_candidato = parts[0]
    else:
        for seg in parts:
            if seg not in {"estudiantes", "grados", "docencia", "plan-estudios", "guia-docente"}:
                slug_candidato = seg
                break

    return grados_alias.get(slug_candidato, slug_candidato)

# -------- Filtros de cabeceras y limpieza --------
HEADINGS_PATTERNS = [
    r'^\s*bibliograf[ií]a\s+fundamental\s*:?\s*$',
    r'^\s*bibliograf[ií]a\s+complementaria\s*:?\s*$',
    r'^\s*bibliograf[ií]a\s*:?\s*$',
    r'^\s*otras\s+referencias\s*:?\s*$',
    r'^\s*enlaces\s+recomendados\s*:?\s*$',
    r'^\s*metodolog[ií]a\s+docente\s*:?\s*$',
]

def es_cabecera_biblio(linea: str) -> bool:
    t = re.sub(r'\s+', ' ', linea or '').strip().lower()
    return any(re.match(p, t, flags=re.IGNORECASE) for p in HEADINGS_PATTERNS)

def limpia_bullet_y_espacios(s: str) -> str:
    s = re.sub(r'^[\s•\-\u2013\u2014]+', '', s or '')
    s = re.sub(r'\s+', ' ', s).strip()
    return s

# -------- Extracción robusta de bibliografía --------
INI_ITEM = re.compile(r'^\s*[•\-\u2013\u2014]\s*')

def _p_text_parts(p: Tag):
    parts, buf = [], []
    for node in p.children:
        if isinstance(node, Tag) and node.name in ('br', 'hr'):
            s = ''.join(buf).strip()
            if s:
                parts.append(s)
            buf = []
        else:
            buf.append(node.get_text(strip=False) if isinstance(node, Tag) else str(node))
    s = ''.join(buf).strip()
    if s:
        parts.append(s)
    return parts

def extraer_bibliografia_desde_html(html: str):
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    resultados = []

    def add_item(txt: str):
        t = limpia_bullet_y_espacios(txt)
        if t and not es_cabecera_biblio(t):
            resultados.append(t)

    headers = []
    for hdr in soup.find_all(["h2", "h3"]):
        t = hdr.get_text(" ", strip=True)
        if re.search(r"\bBibliograf[ií]a\b", t, re.IGNORECASE):
            headers.append(hdr)

    STOP_RE = re.compile(r"(Metodolog[ií]a docente|Enlaces recomendados|Webgraf[ií]a)", re.IGNORECASE)

    for hdr in headers:
        for el in hdr.next_elements:
            if el is hdr:
                continue
            if isinstance(el, Tag) and el.name in ("h2", "h3"):
                break
            if isinstance(el, Tag):
                txt_all = el.get_text(" ", strip=True)[:200]
                if STOP_RE.search(txt_all or ""):
                    break
                if el.name in ("ul", "ol"):
                    for li in el.find_all("li"):
                        add_item(li.get_text(" ", strip=True))
                    continue
                if el.get("role") == "list":
                    for li in el.find_all(attrs={"role": "listitem"}):
                        add_item(li.get_text(" ", strip=True))
                    continue
                if el.name == "p":
                    for piece in _p_text_parts(el):
                        piece = piece.strip()
                        if piece and not es_cabecera_biblio(piece):
                            add_item(piece)

    limpio, vistos = [], set()
    for it in resultados:
        it2 = it.replace(" ,", ",").strip()
        if it2 and it2 not in vistos and not es_cabecera_biblio(it2):
            limpio.append(it2)
            vistos.add(it2)
    return limpio

# -------- Resolución robusta de /guia-docente --------
async def resolver_guia_docente_url(session: aiohttp.ClientSession, base_url: str) -> str | None:
    if base_url.rstrip("/").endswith("/guia-docente"):
        return base_url.rstrip("/")

    candidata = construir_url_guia_docente(base_url)
    try:
        async with session.get(candidata, timeout=30) as resp:
            if resp.status == 200:
                final = str(resp.url)
                if final.rstrip("/").endswith("/guia-docente"):
                    return final.rstrip("/")
    except Exception:
        pass

    try:
        async with session.get(base_url, timeout=30) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()
    except Exception:
        return None

    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True).lower()
        if "guia-docente" in href or "guía docente" in text or "guia docente" in text:
            destino = urljoin(base_url, href)
            try:
                async with session.get(destino, timeout=30) as resp2:
                    if resp2.status == 200:
                        return str(resp2.url).rstrip("/")
            except Exception:
                continue

    return None

# -------- Descarga y procesado --------
async def extraer_urls_de_sitemap(session, sitemap_url):
    print(f"🔎 Leyendo sitemap: {sitemap_url}")
    async with session.get(sitemap_url, timeout=30) as resp:
        texto = await resp.text()
    soup = BeautifulSoup(texto, "lxml-xml")
    return [loc.text.strip() for loc in soup.find_all("loc") if es_url_valida(loc.text.strip())]

async def procesar_url(session, base_url):
    guia_url = await resolver_guia_docente_url(session, base_url)
    if not guia_url:
        print(f"⛔ No se pudo resolver guía docente desde: {base_url}")
        return

    print(f"📘 Procesando guía: {guia_url}")
    try:
        async with session.get(guia_url, timeout=30) as resp:
            if resp.status != 200:
                print(f"⚠️ Guía no accesible ({resp.status}): {guia_url}")
                return
            html = await resp.text()

        bibliografia = extraer_bibliografia_desde_html(html)
        if not bibliografia:
            print(f"⚠️ Sin bibliografía (o no detectada): {guia_url}")
            return

        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        nombre_asignatura = h1.get_text(strip=True) if h1 else "Guia docente"

        # Código robusto (del título y, si hace falta, del HTML)
        codigo = extraer_codigo_asignatura(nombre_asignatura, html)

        # Nombre de archivo sin '(pdf)' y conservando el formato del título
        nombre_archivo = generar_nombre_archivo(nombre_asignatura, codigo)

        # Carpeta destino: grado + prefijo de 3 CARACTERES
        grado_slug = grado_slug_desde_url(guia_url)

        if grado_slug not in grado_prefijos or grado_prefijos[grado_slug] == "000":
            nuevo_prefijo = prefijo_grado_desde_codigo(codigo)
            if nuevo_prefijo != "000" or grado_slug not in grado_prefijos:
                grado_prefijos[grado_slug] = nuevo_prefijo

        prefijo = grado_prefijos.get(grado_slug, "000")
        carpeta_grado_con_prefijo = f"{grado_slug}-{prefijo}"
        carpeta_destino = os.path.join(GRADOS_PATH, carpeta_grado_con_prefijo)
        os.makedirs(carpeta_destino, exist_ok=True)

        ruta_archivo = os.path.join(carpeta_destino, nombre_archivo)

        with open(ruta_archivo, "w", encoding="utf-8") as f:
            f.write(f"{guia_url}\n\n")
            f.write(f"{nombre_asignatura}\n\n")  # conserva el título original
            for entrada in bibliografia:
                if entrada and not es_cabecera_biblio(entrada):
                    f.write(entrada + "\n")

        print(f"✅ Guardado: {ruta_archivo}")

    except Exception as e:
        print(f"⚠️ Error procesando {guia_url}: {e}")

async def main():
    os.makedirs(GRADOS_PATH, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        todas_las_urls = []
        for sitemap_url in sitemap_urls:
            urls = await extraer_urls_de_sitemap(session, sitemap_url)
            todas_las_urls.extend(urls)

        print(f"🔗 Total de URLs a procesar: {len(todas_las_urls)}")
        batch_size = 100

        for i, grupo in enumerate(batch(todas_las_urls, batch_size)):
            print(f"🚀 Lote {i+1} con {len(grupo)} URLs")
            tareas = [procesar_url(session, url) for url in grupo]
            await asyncio.gather(*tareas)

if __name__ == "__main__":
    asyncio.run(main())
