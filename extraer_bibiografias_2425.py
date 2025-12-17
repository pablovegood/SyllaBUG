# El propósito de este programa es el de extraer las guías docentes de todas las asignaturas de la UGR que dispongan
# de una para el año 2024-2025. Este programa tiene sus fallos al extraer los contenidos de PDFs con texto plano, a
# diferencia de las páginas de las guias docentes en HTML para el año actual. Es por ello que el uso de este pograma
# está pensado para ser finito, ya que a partri de ahora se usará el program destinado para extraer las guías
# ddocentes del año actual, ya que el eresultado será mucho más fidedigno y será más complicado que haya errores e
# incongruencias.
#
# Si, por el motivo que sea, se deseara extraer las guias docentes de años anteriores a 2024-2025, será tan sencillo
# como realizar una serie de modificaciones en el programa siguiente que explicaré a continuación.
#
# 1. Querremos almacenar las guias docentes dentro de BibliografíasUGR/grados/2024-2025 para ello bastará con sustituir
# la siguiente línea:
# BASE_PATH = os.path.join("BibliografiasUGR", "grados", "2024-2025")
# por esta otra
# BASE_PATH = os.path.join("BibliografiasUGR", "grados", "2023-2024")
# o según el año que queráis, en este caso esta puesta para las guias docentes del curso académico 2023-2024, pero se
# podría poner el de 2022-2023, etc. Están disponibles hasta el año 2021/2022

import os
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import pdfplumber
import re
import unicodedata
from urllib.parse import urlparse, urljoin
from aiohttp import (
    ClientError, ClientPayloadError, ClientConnectorError,
    ClientSession, ClientTimeout
)
from aiohttp.http_exceptions import ContentLengthError
import ssl

BASE_PATH = os.path.join("BibliografiasUGR", "grados", "2024-2025")
URL_BASE_GRADOS = "https://grados.ugr.es/informacion/guias-docentes-firmadas"
MAX_CONCURRENT = 5
RETRIES = 3

semaforo = asyncio.Semaphore(MAX_CONCURRENT)

# -------------------------
# Utils: slug para carpetas
# -------------------------
SPANISH_STOPWORDS = {
    "a","al","del","de","la","el","los","las","lo","un","una","unos","unas",
    "y","e","o","u","con","sin","por","para","en","sobre","entre","hacia","desde",
    "segun","según","ante","bajo","tras","durante","mediante","hasta",
    # comunes en nombres de grado
    "grado","doble","mencion","mención","itinerario","en"
}

def quitar_acentos(s: str) -> str:
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))

def slugify_nombre_grado(nombre: str) -> str:
    if not nombre:
        return "grado-desconocido"
    s = quitar_acentos(nombre).lower()
    s = s.replace("&", " y ").replace("/", " ").replace("+", " ")
    tokens = re.findall(r"[a-z0-9]+", s)
    tokens = [t for t in tokens if t not in SPANISH_STOPWORDS]
    slug = "-".join(tokens)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if not slug:
        slug = "desconocido"
    return "grado-" + slug

# --- Prefijo de grado (3 primeros caracteres del código de asignatura) ---
def codigo_desde_pdf_url(url_pdf: str) -> str:
    path = urlparse(url_pdf).path
    base = os.path.basename(path)
    if base.lower().endswith(".pdf"):
        base = base[:-4]
    return base.strip()

def prefijo_grado_desde_codigo(cod: str) -> str:
    if not cod:
        return "000"
    return cod[:3]

def prefijo_grado_desde_lista_pdfs(pdfs: list[tuple[str, str]]) -> str:
    for _, url_pdf in pdfs:
        cod = codigo_desde_pdf_url(url_pdf)
        if len(cod) >= 3 and re.match(r"^[A-Za-z0-9]", cod):
            return prefijo_grado_desde_codigo(cod)
    return "000"

# ------------------------------------------------
# Extracción de bibliografía con filtros reforzados
# ------------------------------------------------
def extraer_bibliografia_desde_pdf(ruta_pdf: str):
    raw_lines = []

    patron_ini = re.compile(r"\bbibliograf[ií]a\b", re.IGNORECASE)
    patron_fin = re.compile(
        r"(enlaces recomendados|información adicional|evaluación|"
        r"metodolog[ií]a docente|programa de contenidos te[oó]ricos y pr[aá]cticos)",
        re.IGNORECASE,
    )

    basura_keywords = [
        "adanarg", "dadisrevinu", ":)1(", "amrif", ":fic", "firmado electrónicamente",
        "código seguro de verificación", "sede.ugr.es", "guías curso", "docentes 2024",
        "https://", "http://", "firma", "cif", "verifirma", "guía docente", "verificarse en",
        "resultados de aprendizaje", "objetivos", "contenido", "contenidos", "teórico", "práctico",
        "competencias generales", "competencias específicas", "competencias", "competencia",
        "capacidad", "trabajo en equipo", "autónomo", "razonamiento crítico", "motivación por la calidad",
        "conciencia crítica", "ética", "dimensión ética", "valores y principios",
        "f2008181q"
    ]

    patron_cabecera_cod = re.compile(r"^(cg|ce|md|ct)\d{2}(\b|[-:])", re.IGNORECASE)
    patron_cabecera_ev  = re.compile(r"^ev-(?:[a-z]+\d{1,2}|\d{2})(\b|[-:])", re.IGNORECASE)
    patron_token_ev     = re.compile(r"\bev-(?:[a-z]+\d{1,2}|\d{2})\b", re.IGNORECASE)
    patron_objetivo_num = re.compile(r"^[\u2022\-\–·\s]*(?:0?\d{1,2}[.)])\s")
    patron_docencia_head = re.compile(
        r"^(actividad física|identificaci[oó]n|prevenci[oó]n|riesgos|objetivos|"
        r"resultados|competencias|metodolog[ií]a|temario|unidades?|bloque|evaluaci[oó]n)\b",
        re.IGNORECASE
    )
    patron_ciudad_editor = re.compile(
        r"^[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÜÀ-ÿ'’\- ]+(?:,\s*[A-Z]{2})?\s*:\s*[\wÁÉÍÓÚÜÀ-ÿ'’&.,\- ]+\.?$"
    )

    def es_basura(linea: str) -> bool:
        linea_stripped = linea.strip()
        linea_low = linea_stripped.lower()
        head = re.sub(r"^[\u2022\-\–·]+\s*", "", linea_stripped).strip()

        if len(linea_low) < 5:
            return True
        if any(kw in linea_low for kw in basura_keywords):
            return True
        if patron_objetivo_num.match(linea_stripped):
            return True
        if patron_docencia_head.match(head):
            return True
        if re.match(r"\d+\s*/\s*\d+", linea_low):
            return True
        if re.match(r"^[A-Z]{1}\d{6,}[A-Z]?$", linea_stripped, re.IGNORECASE):
            return True
        if re.match(r"^CE\d{1,2}(\s*-.*)?$", head, re.IGNORECASE):
            return True
        if re.match(r"^MD\d{2}\s*-", head, re.IGNORECASE):
            return True
        if patron_cabecera_cod.match(head):
            return True
        if patron_cabecera_ev.match(head):
            return True
        return False

    def parece_bibliografia(linea: str) -> bool:
        if not linea or len(linea) < 20:
            return False
        if not re.search(r"[.,;:()]", linea):
            return False
        if len(re.findall(r"\w{4,}", linea)) < 2:
            return False
        if all(ch.isupper() or ch.isspace() for ch in linea) and len(linea) > 20:
            return False
        has_year = re.search(r"\b(19|20)\d{2}\b", linea) is not None
        has_isbn_doi = re.search(r"\b(?:ISBN|ISSN|DOI)\b", linea, re.IGNORECASE) is not None
        has_publisher = re.search(
            r"\b(editorial|edici[oó]n|ed\.|press|springer|elsevier|pearson|wiley|sage|routledge|"
            r"mcgraw|human kinetics|gra[oó]|pir[aá]mide|oxford|cambridge|who|world health organization|"
            r"college of|association|committee|universidad|university|ministerio)\b",
            linea, re.IGNORECASE
        ) is not None
        has_author_initials = re.search(
            r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+,\s*[A-ZÁÉÍÓÚÑ](?:\.[A-ZÁÉÍÓÚÑ]\.)?\b", linea
        ) is not None
        return has_year or has_isbn_doi or has_publisher or has_author_initials

    guardar = False

    with pdfplumber.open(ruta_pdf) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto:
                continue
            for linea in texto.splitlines():
                clean = linea.strip()
                if patron_ini.search(clean):
                    guardar = True
                    continue
                elif patron_fin.search(clean):
                    if guardar:
                        guardar = False
                        break

                if guardar and not es_basura(clean):
                    clean = patron_token_ev.sub(" ", clean)
                    basura_interna = ["adanarG", "dadisrevinU", "amriF", ":)1(", ":FIC", "F2008181Q"]
                    for palabra in basura_interna:
                        clean = re.sub(rf"[\s,;:()\-\u00A0]*{re.escape(palabra)}[\s,;:()\-\u00A0]*", " ", clean)
                    clean = re.sub(r"\s{2,}", " ", clean).strip()
                    if clean:
                        raw_lines.append(clean)

    combinadas = []
    i = 0
    while i < len(raw_lines):
        actual = raw_lines[i]
        while i + 1 < len(raw_lines):
            siguiente = raw_lines[i + 1].strip()
            actual_final = actual.rstrip()[-1:]
            unir = False
            if (not actual_final) or (actual_final not in ('.', ':', ';')):
                unir = True
            if re.match(r"^[a-z(\u2022\-–·]", siguiente):
                unir = True
            if patron_ciudad_editor.match(siguiente):
                unir = True
            if unir:
                actual += " " + siguiente.lstrip("\u2022-–· ")
                i += 1
            else:
                break
        combinadas.append(actual.strip())
        i += 1

    bibliografia = []
    basura_interna_final = ["adanarG", "dadisrevinU", "amriF", ":)1(", ":FIC", "F2008181Q"]
    for linea in combinadas:
        linea = re.sub(r"\bev-(?:[a-z]+\d{1,2}|\d{2})\b", " ", linea, flags=re.IGNORECASE)
        for palabra in basura_interna_final:
            linea = re.sub(rf"[\s,;:()\-\u00A0]*{re.escape(palabra)}[\s,;:()\-\u00A0]*", " ", linea)
        linea = re.sub(r"\s{2,}", " ", linea).strip()
        if parece_bibliografia(linea):
            if not linea.startswith("\u2022"):
                linea = "\u2022 " + linea
            bibliografia.append(linea)

    return bibliografia

# ----------------------------
# Scraping de grados y PDFs
# ----------------------------
async def obtener_lista_grados(session: ClientSession):
    print("\U0001f50e Obteniendo lista de grados de 2024/2025...")
    async with session.get(URL_BASE_GRADOS) as resp:
        html = await resp.text()
    soup = BeautifulSoup(html, "html.parser")
    seccion = soup.find("h2", string=re.compile("Grados impartidos.*2024 / 2025"))
    lista = []
    if seccion:
        ul = seccion.find_next_sibling("ul")
        if ul:
            for li in ul.find_all("li"):
                enlace = li.find("a")
                if enlace:
                    nombre = enlace.text.strip()
                    url = enlace["href"]
                    url = urljoin(URL_BASE_GRADOS, url)
                    lista.append((nombre, url))
    return lista

async def obtener_pdfs_asignaturas(session: ClientSession, url_grado: str):
    async with session.get(url_grado) as resp:
        html = await resp.text()
    soup = BeautifulSoup(html, "html.parser")
    enlaces = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower():
            enlaces.append((a.text.strip(), urljoin(url_grado, href)))
    return enlaces

# ----------------------------
# Helpers de nombre de archivo
# ----------------------------
def quitar_marca_pdf(titulo: str) -> str:
    """
    Elimina '(pdf)' o variantes en cualquier parte del texto y 'pdf' suelto al final.
    """
    s = re.sub(r"\(\s*pdf\s*\)", " ", titulo or "", flags=re.IGNORECASE)
    s = re.sub(r"\bpdf\b\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s

# ------------------------------------------------------
# Guardado: carpetas 'grado-<slug>-<prefijo3>'
# ------------------------------------------------------
async def descargar_y_extraer(session: ClientSession, url_pdf: str, nombre_asignatura: str, carpeta_destino: str):
    codigo = codigo_desde_pdf_url(url_pdf)

    os.makedirs(carpeta_destino, exist_ok=True)

    # Limpia '(pdf)' del nombre visible
    nombre_asignatura = quitar_marca_pdf(nombre_asignatura)

    nombre_limpio = re.sub(r'[\\/*?:"<>|]', "", nombre_asignatura)
    nombre_limpio = quitar_acentos(nombre_limpio)
    nombre_limpio = re.sub(r"\s+", "_", nombre_limpio).strip("_")
    nombre_limpio = re.sub(r"_+", "_", nombre_limpio)

    salida_path = os.path.join(carpeta_destino, f"Guia_docente_{nombre_limpio}_{codigo}.txt")

    if os.path.exists(salida_path):
        print(f"⏩ Ya existe, se omite: {salida_path}")
        return

    for intento in range(RETRIES):
        try:
            async with semaforo:
                async with session.get(url_pdf) as resp:
                    if resp.status != 200:
                        raise ClientError(f"HTTP {resp.status}")
                    pdf_bytes = await resp.read()

            os.makedirs("temp_pdfs", exist_ok=True)
            temp_path = os.path.join("temp_pdfs", f"{codigo or 'SIN_CODIGO'}.pdf")
            with open(temp_path, "wb") as f:
                f.write(pdf_bytes)

            bibliografia = extraer_bibliografia_desde_pdf(temp_path)
            if bibliografia:
                with open(salida_path, "w", encoding="utf-8") as f:
                    for linea in bibliografia:
                        f.write(linea + "\n")
                print(f"✅ Guardada bibliografía: {salida_path}")
            else:
                print(f"⚠️ No se encontró bibliografía en {codigo or 'SIN_CODIGO'}.pdf")
            os.remove(temp_path)
            return

        except (ClientPayloadError, ContentLengthError, ClientConnectorError,
                ConnectionResetError, ssl.SSLError, asyncio.TimeoutError) as e:
            print(f"⚠️ Error intento {intento+1}/{RETRIES} en {codigo or 'SIN_CODIGO'}: {e}")
            await asyncio.sleep(2 ** intento)
        except Exception as e:
            print(f"❌ Error inesperado en {codigo or 'SIN_CODIGO'}: {e}")
            return

    print(f"⛔ Fallo permanente al procesar {codigo or 'SIN_CODIGO'} tras {RETRIES} intentos")

# ----------------------------
# Entry point
# ----------------------------
async def main():
    timeout = ClientTimeout(total=180)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, ssl=False)

    async with ClientSession(timeout=timeout, connector=connector) as session:
        grados = await obtener_lista_grados(session)
        print(f"🎓 Se encontraron {len(grados)} grados.")
        for nombre_grado, url in grados:
            carpeta_slug = slugify_nombre_grado(nombre_grado)

            # Obtener PDFs y fijar el prefijo del grado una sola vez
            pdfs = await obtener_pdfs_asignaturas(session, url)
            prefijo = prefijo_grado_desde_lista_pdfs(pdfs)  # '2TC', 'turismo-238', '205' o '000'

            carpeta_destino = os.path.join(BASE_PATH, f"{carpeta_slug}-{prefijo}")
            print(f"\n📘 Procesando grado: {nombre_grado}")
            print(f"   ➤ Carpeta: {os.path.basename(carpeta_destino)}")
            print(f"   ➤ {len(pdfs)} PDFs encontrados")

            tareas = [
                descargar_y_extraer(session, pdf_url, nombre_asig, carpeta_destino)
                for nombre_asig, pdf_url in pdfs
            ]
            await asyncio.gather(*tareas)

if __name__ == "__main__":
    asyncio.run(main())
