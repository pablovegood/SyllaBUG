import pandas as pd
import re
import sys
import os
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By


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


def obtener_reading_list_id(codigo):
    df = pd.read_excel("MapeadoCodigos.xlsx")
    df.columns = df.iloc[0]
    df = df.drop(0)
    df = df[df["Reading List Id"] != "-99"]
    resultado = df[df["Course Code"] == codigo]
    return resultado["Reading List Id"].values[0] if not resultado.empty else None


def extraer_bibliografia(html):
    soup = BeautifulSoup(html, "html.parser")
    bibliografia = []

    secciones = {
        "fundamental": "Bibliografía fundamental",
        "complementaria": "Bibliografía complementaria"
    }

    for tipo, encabezado in secciones.items():
        h3 = soup.find("h3", string=re.compile(encabezado, re.IGNORECASE))
        if h3:
            div = h3.find_next_sibling("div")
            if div:
                lis = div.find_all("li")
                for li in lis:
                    texto = li.get_text(separator=" ", strip=True)
                    if texto:
                        bibliografia.append(f"[{tipo.upper()}] {texto}")
            else:
                print(f"⚠️ No se encontró el div siguiente a <h3> {encabezado}")
        else:
            print(f"⚠️ No se encontró sección con <h3> {encabezado}")

    return bibliografia


def guardar_bibliografia(bibliografia, titulo):
    nombre_archivo = f"{titulo}_BIBLIOGRAFIA.txt".replace(" ", "_")
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        f.write("📚 Bibliografía:\n")
        for item in bibliografia:
            f.write(f" - {item}\n")
    print(f"✅ Archivo guardado como: {nombre_archivo}")


def esperar_y_extraer_html_completo(driver, max_scrolls=30):
    print("⏳ Haciendo scroll para cargar todos los recursos...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    scrolls = 0

    while scrolls < max_scrolls:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
        scrolls += 1

    print("✅ Scroll completo. Capturando HTML final...")
    return driver.page_source


def extraer_recursos_leganto_bs4(html):
    soup = BeautifulSoup(html, "html.parser")
    contenedores = soup.select("div.item-detail-brief.pipe-line.flex-1.citation-author.ng-star-inserted")
    titulos = soup.select("span[class*=aut-citation-header-title]")

    recursos = []
    for i in range(min(len(titulos), len(contenedores))):
        titulo = titulos[i].get_text(strip=True)
        detalle = contenedores[i].get_text(" ", strip=True)
        recursos.append(f"{titulo}\n    ↳ {detalle}")
    print(f"📦 Recursos encontrados: {len(recursos)}")
    return recursos


def guardar_recursos_leganto(recursos, titulo):
    nombre_archivo = f"{titulo}_RECURSOS_LEGANTO.txt".replace(" ", "_")
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        f.write("📘 Recursos extraídos desde Leganto:\n\n")
        for idx, r in enumerate(recursos, start=1):
            f.write(f"{idx}. {r}\n\n")
    print(f"✅ Recursos Leganto guardados en: {nombre_archivo}")


def descargar_leganto_y_extraer(reading_list_id):
    url = f"https://cbua-ugr.alma.exlibrisgroup.com/leganto/nui/lists/{reading_list_id}"
    login_url = "https://cbua-ugr.alma.exlibrisgroup.com/leganto/login?auth=SAML"

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    try:
        print(f"🔐 Abriendo navegador para iniciar sesión...")
        driver.get(login_url)
        input("🔓 Inicia sesión y pulsa ENTER...")

        print(f"🌐 Accediendo a la lista: {url}")
        driver.get(url)
        time.sleep(3)

        html_leganto = esperar_y_extraer_html_completo(driver)
        recursos = extraer_recursos_leganto_bs4(html_leganto)
        guardar_recursos_leganto(recursos, f"leganto_{reading_list_id}")

    finally:
        driver.quit()


def obtener_leganto_desde_guia(url_guia):
    html = descargar_html(url_guia)
    if not html:
        return

    codigo = extraer_codigo_asignatura(html)
    if not codigo:
        print("❌ No se encontró ningún código de asignatura.")
        return

    print(f"📘 Código de asignatura: {codigo}")

    bibliografia = extraer_bibliografia(html)
    if bibliografia:
        guardar_bibliografia(bibliografia, f"guia_{codigo}")
    else:
        print("⚠️ No se encontró bibliografía en la guía docente.")

    reading_list_id = obtener_reading_list_id(codigo)
    if not reading_list_id:
        print("❌ No se encontró el código en el Excel.")
        return

    print(f"🔗 ID de Leganto: {reading_list_id}")
    descargar_leganto_y_extraer(reading_list_id)


# ----------- EJECUCIÓN ------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ Uso: python script.py <url_guia_docente>")
        sys.exit(1)

    url_guia = sys.argv[1]
    if not os.path.exists("MapeadoCodigos.xlsx"):
        print("❌ No se encuentra el archivo 'MapeadoCodigos.xlsx' en el directorio.")
        sys.exit(1)

    obtener_leganto_desde_guia(url_guia)
