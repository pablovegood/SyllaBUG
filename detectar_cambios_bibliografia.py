import os
import sys
import hashlib
import time
from bs4 import BeautifulSoup
from difflib import unified_diff
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def obtener_html_despues_de_login(url):
    chrome_options = Options()
    # Comentamos el modo headless para que puedas ver el navegador
    # chrome_options.add_argument("--headless")

    driver = webdriver.Chrome(options=chrome_options)

    try:
        print(f"🌐 Abriendo navegador para iniciar sesión manual...")
        driver.get(url)

        print("⏳ Esperando a que inicies sesión manualmente...")
        input("✅ Pulsa ENTER cuando hayas iniciado sesión y veas la guía docente cargada.\n")

        html = driver.page_source
        return html
    except Exception as e:
        print(f"❌ Error: {e}")
        return None
    finally:
        driver.quit()

def extraer_bibliografia(html):
    soup = BeautifulSoup(html, 'html.parser')
    bibliografia = []

    for h3 in soup.find_all('h3'):
        if "Bibliografía fundamental" in h3.text or "Bibliografía complementaria" in h3.text:
            titulo = h3.text.strip()
            entradas = []
            siguiente = h3.find_next_sibling()

            while siguiente and siguiente.name in ['ul', 'ol', 'p', 'div']:
                if siguiente.name in ['ul', 'ol']:
                    for li in siguiente.find_all('li'):
                        texto = li.get_text(separator=" ", strip=True)
                        if texto:
                            entradas.append(texto)
                elif siguiente.name == 'p':
                    texto = siguiente.get_text(separator=" ", strip=True)
                    if texto:
                        entradas.append(texto)
                elif siguiente.name == 'div':
                    for li in siguiente.find_all('li'):
                        texto = li.get_text(separator=" ", strip=True)
                        if texto:
                            entradas.append(texto)
                siguiente = siguiente.find_next_sibling()

            bibliografia.append((titulo, entradas))
    return bibliografia

def obtener_nombre_archivo(url):
    return f"bib_{hashlib.md5(url.encode()).hexdigest()}.txt"

def guardar_bibliografia(bib_data, filename):
    with open(filename, "w", encoding="utf-8") as f:
        for titulo, entradas in bib_data:
            f.write(f"== {titulo} ==\n")
            for entrada in entradas:
                f.write(f"{entrada}\n")

def cargar_bibliografia(filename):
    if not os.path.exists(filename):
        return None
    with open(filename, "r", encoding="utf-8") as f:
        return f.readlines()

def main():
    if len(sys.argv) < 2:
        print("Uso: python detectar_cambios_bibliografia_login_manual.py <URL>")
        return

    url = sys.argv[1]

    html = obtener_html_despues_de_login(url)
    if not html:
        return

    bib_actual = extraer_bibliografia(html)
    if not bib_actual:
        print("⚠️ No se encontró bibliografía.")
        return

    filename = obtener_nombre_archivo(url)
    if not os.path.exists(filename):
        print("📦 Guardando bibliografía por primera vez...")
        guardar_bibliografia(bib_actual, filename)
        return

    anterior = cargar_bibliografia(filename)
    nueva = []
    for titulo, entradas in bib_actual:
        nueva.append(f"== {titulo} ==\n")
        nueva.extend(f"{e}\n" for e in entradas)

    if anterior == nueva:
        print("✅ No hay cambios en la bibliografía.")
    else:
        print("\n⚠️  Se detectaron cambios en la bibliografía:\n")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("📄 CAMBIOS DETECTADOS ENTRE VERSIÓN GUARDADA Y VERSIÓN ACTUAL")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        diff = unified_diff(anterior, nueva, fromfile='📂 Anterior', tofile='🆕 Actual', lineterm='')

        for linea in diff:
            if linea.startswith('---') or linea.startswith('+++'):
                print(f"\n{linea}")
            elif linea.startswith('@@'):
                print(f"\n🔄 {linea}")
            elif linea.startswith('+'):
                print(f"🟢 Añadido: {linea[1:].strip()}")
            elif linea.startswith('-'):
                print(f"🔴 Eliminado: {linea[1:].strip()}")
            else:
                print(f"   {linea.strip()}")

        print("\n💾 Actualizando bibliografía guardada...")
        guardar_bibliografia(bib_actual, filename)

if __name__ == "__main__":
    main()
