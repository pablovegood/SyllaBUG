from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time

def descargar_html_tras_click_en_lista(
    url,
    texto_objetivo="DESARROLLO BASADO EN AGENTES (E. ING. SOFTWARE)",
    salida="html_lista_detallada.html"
):
    options = Options()
    options.headless = False
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    try:
        print(f"🌐 Abriendo navegador en: {url}")
        driver.get(url)

        print("🔐 Espera manualmente a iniciar sesión (tienes hasta 5 min)...")
        WebDriverWait(driver, 300).until(
            lambda d: "login" not in d.current_url
        )

        print("✅ Login completado. Buscando la lista...")
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.TAG_NAME, "h2"))
        )

        # Buscar el título de la lista y hacer clic
        titulos = driver.find_elements(By.TAG_NAME, "h2")
        encontrado = False
        for titulo in titulos:
            if texto_objetivo.strip().lower() in titulo.text.strip().lower():
                print(f"🖱️ Haciendo clic en: {titulo.text.strip()}")
                driver.execute_script("arguments[0].click();", titulo)
                encontrado = True
                break

        if not encontrado:
            raise Exception(f"No se encontró el título '{texto_objetivo}'")

        # Esperar a que cargue la nueva página
        time.sleep(5)

        # Guardar HTML formateado
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        html_pretty = soup.prettify()

        with open(salida, "w", encoding="utf-8") as f:
            f.write(html_pretty)

        print(f"📄 HTML guardado como '{salida}'")

    except Exception as e:
        print(f"❌ Error: {e}")

    finally:
        driver.quit()

# Llama a la función con la URL de Leganto
descargar_html_tras_click_en_lista(
    url="https://cbua-ugr.alma.exlibrisgroup.com/leganto/login?institute=34CBUA_UGR&auth=SAML",
    texto_objetivo="DESARROLLO BASADO EN AGENTES (E. ING. SOFTWARE)",
    salida="desarrollo_basado_en_agentes.html"
)
