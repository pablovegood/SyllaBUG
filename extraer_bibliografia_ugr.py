import re
import sys
import os
import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
from difflib import SequenceMatcher

def descargar_html(url):
    try:
        print(f"🌐 Descargando: {url}")
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Error al descargar la página: {e}")
        return None

def extraer_codigo_asignatura(html):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1", class_="page-title")
    if h1:
        match = re.search(r"\(([\w\d]+)\)", h1.text)
        if match:
            return match.group(1)
    texto = soup.get_text()
    match = re.search(r"\b\d{5}[A-Z]\d\b", texto)
    return match.group(0) if match else None

def extraer_bibliografia(html):
    soup = BeautifulSoup(html, "html.parser")
    bibliografia = []

    secciones = {
        "fundamental": "Bibliografía fundamental",
        "complementaria": "Bibliografía complementaria"
    }

    stopwords = [
        "enlaces recomendados", "metodología docente",
        "evaluación", "cronograma", "recursos web"
    ]

    for tipo, encabezado in secciones.items():
        h3 = soup.find("h3", string=re.compile(encabezado, re.IGNORECASE))
        if h3:
            for sibling in h3.find_next_siblings():
                if sibling.name and sibling.name.startswith("h"):
                    texto = sibling.get_text(strip=True).lower()
                    if any(stop in texto for stop in stopwords):
                        break  # ⚠️ parar si llegamos a otra sección

                # extraer desde <li> y <p>
                elementos = sibling.find_all(["li", "p"])
                for el in elementos:
                    texto = el.get_text(separator=" ", strip=True)
                    if texto:
                        if ":" in texto:
                            partes = texto.split(":", 1)
                        elif ";" in texto:
                            partes = texto.split(";", 1)
                        elif "." in texto:
                            partes = texto.split(".", 1)
                        else:
                            partes = [None, texto]

                        autor = partes[0].strip() if partes[0] else ""
                        titulo = partes[1].strip() if len(partes) > 1 else partes[0].strip()
                        if titulo:
                            bibliografia.append({
                                "autor": autor,
                                "titulo": titulo
                            })

        else:
            print(f"⚠️ No se encontró sección con <h3> {encabezado}")

    return bibliografia

def extraer_texto_pdf(nombre_pdf):
    try:
        lector = PdfReader(nombre_pdf)
        texto = ""
        for pagina in lector.pages:
            texto += pagina.extract_text() + "\n"
        return texto
    except Exception as e:
        print(f"❌ Error al leer el PDF: {e}")
        return ""

def extraer_titulos_pdf(texto_pdf):
    lineas = texto_pdf.split("\n")
    titulos = []
    siguiente_es_titulo = False

    for linea in lineas:
        l = linea.strip()
        if siguiente_es_titulo and l:
            titulos.append(l)
            siguiente_es_titulo = False
        if "ir al ejemplar" in l.lower() or "ir a la sección" in l.lower():
            siguiente_es_titulo = True

    print(f"✅ Títulos detectados: {len(titulos)}")
    for i, t in enumerate(titulos, 1):
        print(f"{i}. {t}")
    return titulos

def normalizar_titulo_comparacion(texto):
    texto = texto.lower()
    texto = re.sub(r"[.,:;!?()\"\'-]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()

def comparar_por_titulos(guia, pdf_titulos, codigo_asignatura, umbral_fuzzy=0.55):
    guia_map = {
        normalizar_titulo_comparacion(entry["titulo"]): (entry["titulo"], entry["autor"])
        for entry in guia
    }
    pdf_map = {normalizar_titulo_comparacion(t): t for t in pdf_titulos}

    titulos_guia_norm = set(guia_map.keys())
    titulos_pdf_norm = set(pdf_map.keys())

    comunes = titulos_guia_norm & titulos_pdf_norm
    solo_guia = titulos_guia_norm - comunes
    solo_pdf = titulos_pdf_norm - comunes

    fuzzy_matches = []
    for g in sorted(solo_guia):
        for p in sorted(solo_pdf):
            ratio = SequenceMatcher(None, g, p).ratio()
            if ratio >= umbral_fuzzy:
                fuzzy_matches.append((guia_map[g][0], guia_map[g][1], pdf_map[p], round(ratio * 100, 2)))
                break

    matched_guia = set(normalizar_titulo_comparacion(g) for g, _, _, _ in fuzzy_matches)
    matched_pdf = set(normalizar_titulo_comparacion(p) for _, _, p, _ in fuzzy_matches)
    final_solo_guia = [g for g in solo_guia if g not in matched_guia]
    final_solo_pdf = [p for p in solo_pdf if p not in matched_pdf]

    nombre_archivo = f"comparativa_{codigo_asignatura}.txt"
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        f.write("📘 TÍTULOS COINCIDENTES EXACTOS:\n")
        for key in sorted(comunes):
            titulo, autor = guia_map[key]
            f.write(f"   ✅ Autor: {autor} — Título: {titulo}\n")

        f.write("\n🤏 TÍTULOS COINCIDENTES APROXIMADOS (fuzzy):\n")
        for titulo, autor, pdf_title, ratio in fuzzy_matches:
            f.write(f"   🟡 Guía → Autor: {autor} — Título: {titulo}\n")
            f.write(f"      ≈ PDF → Título: {pdf_title}  ({ratio}% parecido)\n\n")

        f.write("\n📗 TÍTULOS SOLO EN LA GUÍA DOCENTE:\n")
        for key in sorted(final_solo_guia):
            titulo, autor = guia_map[key]
            f.write(f"   📙 Autor: {autor} — Título: {titulo}\n")

        f.write("\n📕 TÍTULOS SOLO EN EL PDF DE LEGANTO:\n")
        for key in sorted(final_solo_pdf):
            f.write(f"   📘 Título: {pdf_map[key]}\n")

        f.write("\n📊 RESUMEN:\n")
        total = len(comunes) + len(fuzzy_matches) + len(final_solo_guia) + len(final_solo_pdf)
        coincidencia = round((len(comunes) + len(fuzzy_matches)) / total * 100, 2) if total > 0 else 0.0
        f.write(f"   Coincidencia exacta: {len(comunes)} títulos\n")
        f.write(f"   Coincidencia fuzzy: {len(fuzzy_matches)} títulos\n")
        f.write(f"   Porcentaje de coincidencia total: {coincidencia}%\n")

    print(f"\n✅ Comparativa guardada en: {nombre_archivo}")

# ----------- EJECUCIÓN ------------
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("❌ Uso: python script.py <url_guia_docente> <archivo_pdf>")
        sys.exit(1)

    url_guia = sys.argv[1]
    archivo_pdf = sys.argv[2]

    if not os.path.exists(archivo_pdf):
        print(f"❌ No se encuentra el archivo PDF: {archivo_pdf}")
        sys.exit(1)

    html = descargar_html(url_guia)
    if not html:
        sys.exit(1)

    codigo = extraer_codigo_asignatura(html) or "asignatura"
    print(f"📘 Código de asignatura: {codigo}")

    print("\n🔍 Extrayendo bibliografía de la guía docente...")
    bib_guia = extraer_bibliografia(html)

    print("\n📄 Extrayendo títulos del PDF de Leganto...")
    texto_pdf = extraer_texto_pdf(archivo_pdf)
    titulos_pdf = extraer_titulos_pdf(texto_pdf)

    print("\n🔎 Comparando títulos (exactos y aproximados)...")
    comparar_por_titulos(bib_guia, titulos_pdf, codigo)
