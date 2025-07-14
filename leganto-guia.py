import pandas as pd
import re
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# 1. Descargar el HTML de la guía docente
def descargar_html(url):
    try:
        print(f"🌐 Descargando: {url}")
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Error al descargar la página: {e}")
        return None

# 2. Extraer el código de asignatura desde el <h1> con paréntesis
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

# 3. Leer Excel con códigos y devolver Reading List ID
def obtener_reading_list_id(codigo, excel_path):
    df = pd.read_excel(excel_path)
    df.columns = df.iloc[0]
    df = df.drop(0)
    df = df[df["Reading List Id"] != "-99"]
    resultado = df[df["Course Code"] == codigo]
    return resultado["Reading List Id"].values[0] if not resultado.empty else None

# 4. Automatizar exportación del PDF con Selenium
def obtener_pdf_leganto(reading_list_id):
    login_url = "https://cbua-ugr.alma.exlibrisgroup.com/leganto/login?auth=SAML"
    list_url = f"https://cbua-ugr.alma.exlibrisgroup.com/leganto/nui/lists/{reading_list_id}"

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    try:
        print("🔐 Inicia sesión manualmente y pulsa ENTER...")
        driver.get(login_url)
        input("✅ Pulsa ENTER cuando hayas iniciado sesión correctamente...")

        print(f"➡️ Accediendo a la lista: {list_url}")
        driver.get(list_url)
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(4)

        print("⚙️ Abriendo el menú de configuración...")
        menu_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Lista']"))
        )
        menu_btn.click()
        time.sleep(1)

        print("📄 Haciendo clic en 'Exportar lista'...")
        exportar_lista = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'Exportar lista')]"))
        )
        exportar_lista.click()
        time.sleep(1)

        print("📤 Haciendo clic en botón final 'Exportar'...")
        boton_exportar = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "lg-dialog-ok"))
        )
        boton_exportar.click()

        print("⏳ Esperando redirección al PDF...")
        time.sleep(6)

        url_pdf = driver.current_url
        print(f"📎 PDF generado en: {url_pdf}")

        cookies = {c['name']: c['value'] for c in driver.get_cookies()}
        response = requests.get(url_pdf, cookies=cookies)
        response.raise_for_status()

        pdf_name = f"leganto_{reading_list_id}.pdf"
        with open(pdf_name, "wb") as f:
            f.write(response.content)
        print(f"✅ PDF guardado como: {pdf_name}")
        return pdf_name

    except TimeoutException as e:
        print(f"❌ Timeout esperando elemento: {e}")
    except Exception as e:
        print(f"❌ Error en el proceso: {e}")
    finally:
        driver.quit()

# 5. Función principal
def obtener_leganto_desde_guia(url_guia, excel_path):
    html = descargar_html(url_guia)
    if not html:
        return

    codigo = extraer_codigo_asignatura(html)
    if not codigo:
        print("❌ No se encontró el código de asignatura.")
        return

    print(f"📘 Código de asignatura: {codigo}")
    reading_list_id = obtener_reading_list_id(codigo, excel_path)
    if not reading_list_id:
        print("❌ Código no encontrado en el Excel.")
        return

    print(f"🔗 Reading List ID: {reading_list_id}")
    pdf_path = obtener_pdf_leganto(reading_list_id)
    if pdf_path:
        print(f"📄 PDF descargado correctamente: {pdf_path}")
    else:
        print("❌ No se pudo descargar el PDF.")

# ✅ EJECUCIÓN
if __name__ == "__main__":
    url_guia = "https://www.ugr.es/estudiantes/grados/grado-historia/historia-mujeres/guia-docente"
    excel_path = "MapeadoCodigos.xlsx"
    obtener_leganto_desde_guia(url_guia, excel_path)
