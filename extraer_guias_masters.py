import os
import re
import time
import shutil
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from webdriver_manager.chrome import ChromeDriverManager  # ✅ Nuevo
from selenium.webdriver.chrome.service import Service  # al inicio del script

BASE_URL = "https://masteres.ugr.es/ramas"
BASE_PATH = "BibliografiasUGR/master-doctorados"
HEADLESS = True

def asegurar_estructura_directorios():
    for subcarpeta in ["Nuevas", "Antiguas", "Comparativas"]:
        ruta = os.path.join(BASE_PATH, subcarpeta)
        os.makedirs(ruta, exist_ok=True)

def configurar_driver():
    chrome_options = Options()
    if HEADLESS:
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())  # ✅ Corrección
    return webdriver.Chrome(service=service, options=chrome_options)


def obtener_enlaces_masteres(driver):
    driver.get(BASE_URL)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
    soup = BeautifulSoup(driver.page_source, "html.parser")
    enlaces = []
    for a in soup.select("table a"):
        href = a.get("href")
        if href and href.startswith("http"):
            enlaces.append((a.text.strip(), href.strip()))
    return enlaces

def obtener_enlaces_guias(driver, url_master):
    plan_estudios_url = urljoin(url_master + "/", "docencia/plan-estudios")
    driver.get(plan_estudios_url)
    time.sleep(2)

    try:
        driver.execute_script("let popup = document.getElementById('sliding-popup'); if (popup) popup.remove();")
    except:
        pass

    try:
        desplegables = driver.find_elements(By.CSS_SELECTOR, ".ui-accordion-header")
        for elem in desplegables:
            driver.execute_script("arguments[0].scrollIntoView();", elem)
            elem.click()
            time.sleep(0.5)
    except Exception as e:
        print(f"❌ No se pudo expandir módulos en {plan_estudios_url}: {e}")
        return []

    print(f"🔗 Accediendo a página de plan de estudios: {plan_estudios_url}")
    soup = BeautifulSoup(driver.page_source, "html.parser")
    enlaces_guias = []

    for fila in soup.select("table.materias tbody tr"):
        columnas = fila.find_all("td")
        if len(columnas) >= 6:
            asignatura = columnas[0].get_text(strip=True)
            enlace_tag = columnas[5].find("a")
            if enlace_tag and enlace_tag.get("href"):
                url_guia = urljoin(plan_estudios_url, enlace_tag["href"].strip())
                enlaces_guias.append((asignatura, url_guia))
                print(f"🧭 Enlace detectado a guía docente: {url_guia}")

    return enlaces_guias

def extraer_identificador_asignatura(html):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1", class_="page-title")
    if h1:
        titulo = h1.get_text(strip=True)
        titulo = re.sub(r'[\\/*?:"<>|]', "", titulo).replace(" ", "_")
        return titulo
    return None

def extraer_bibliografia(html):
    soup = BeautifulSoup(html, "html.parser")
    bibliografia = []
    for h3 in soup.find_all("h3"):
        texto = h3.get_text(strip=True)
        if "Metodología docente" in texto or "Enlaces recomendados" in texto:
            break
        if "Bibliografía fundamental" in texto or "Bibliografía complementaria" in texto:
            div = h3.find_next_sibling(lambda tag: tag.name == "div")
            if div:
                for elem in div.descendants:
                    if elem.name in ["p", "li"] and elem.get_text(strip=True):
                        bibliografia.append(elem.get_text(strip=True))
    return bibliografia

def generar_nombre_archivo(titulo):
    return f"{titulo}.txt"

def guardar_bibliografia(titulo, bibliografia):
    nombre_archivo = generar_nombre_archivo(titulo)
    ruta_nueva = os.path.join(BASE_PATH, "Nuevas", nombre_archivo)
    ruta_antigua = os.path.join(BASE_PATH, "Antiguas", nombre_archivo)
    ruta_comparativa = os.path.join(BASE_PATH, "Comparativas", nombre_archivo)

    os.makedirs(os.path.dirname(ruta_nueva), exist_ok=True)
    os.makedirs(os.path.dirname(ruta_antigua), exist_ok=True)
    os.makedirs(os.path.dirname(ruta_comparativa), exist_ok=True)

    with open(ruta_nueva, "w", encoding="utf-8") as f:
        for linea in bibliografia:
            f.write(linea + "\n")

    if os.path.exists(ruta_antigua):
        with open(ruta_antigua, "r", encoding="utf-8") as f:
            antigua = [line.strip() for line in f.readlines()]
        añadidos = list(set(bibliografia) - set(antigua))
        eliminados = list(set(antigua) - set(bibliografia))
        resumen = (
            [f"Total en antigua: {len(antigua)}", f"Total en nueva: {len(bibliografia)}",
             f"Recursos añadidos ({len(añadidos)}):"] + añadidos +
            [f"\nRecursos eliminados ({len(eliminados)}):"] + eliminados
        )
        with open(ruta_comparativa, "w", encoding="utf-8") as f:
            f.write("\n".join(resumen))

def mover_nuevas_a_antiguas():
    carpeta_nuevas = os.path.join(BASE_PATH, "Nuevas")
    carpeta_antiguas = os.path.join(BASE_PATH, "Antiguas")

    if not os.path.exists(carpeta_nuevas):
        return

    archivos = os.listdir(carpeta_nuevas)
    if archivos:
        os.makedirs(carpeta_antiguas, exist_ok=True)
        for archivo in archivos:
            origen = os.path.join(carpeta_nuevas, archivo)
            destino = os.path.join(carpeta_antiguas, archivo)
            if os.path.exists(origen):
                try:
                    shutil.move(origen, destino)
                except Exception as e:
                    print(f"❌ No se pudo mover {archivo}: {e}")
            else:
                print(f"⚠️ Archivo no encontrado: {archivo}")
        print("📦 Archivos válidos de 'Nuevas' trasladados a 'Antiguas'.")


def crear_sesion_con_reintentos():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

def main():
    asegurar_estructura_directorios()
    mover_nuevas_a_antiguas()
    session = crear_sesion_con_reintentos()
    driver_masteres = configurar_driver()
    try:
        enlaces_masteres = obtener_enlaces_masteres(driver_masteres)
    finally:
        driver_masteres.quit()

    for master_name, url_master in enlaces_masteres:
        print(f"🔍 Procesando máster: {master_name} ({url_master})")
        driver = configurar_driver()
        try:
            enlaces_guias = obtener_enlaces_guias(driver, url_master)
            for asignatura, url_guia in enlaces_guias:
                print(f"   📘 Procesando guía: {asignatura} → {url_guia}")
                try:
                    res = session.get(url_guia, timeout=20)
                    res.raise_for_status()
                    bib = extraer_bibliografia(res.text)
                    titulo = extraer_identificador_asignatura(res.text)
                    if bib and titulo:
                        guardar_bibliografia(titulo, bib)
                    else:
                        print(f"   ⚠️ No se guarda guía por falta de bibliografía o título en {url_guia}")
                except Exception as e:
                    print(f"   ❌ Error al procesar guía {url_guia}: {e}")
        except Exception as e:
            print(f"   ❌ Error en máster {master_name}: {e}")
        finally:
            driver.quit()

if __name__ == "__main__":
    main()
