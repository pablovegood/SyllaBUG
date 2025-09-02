from flask import Flask, render_template, request
import pandas as pd
import os
import re

app = Flask(__name__, template_folder="templates", static_folder="static")

BASE_PATH = os.path.join("BibliografiasUGR", "grados", "Comparativas")

bibliotecas = [
    "B. Filosofía y Letras A", "B. Informática y Telecom.",
    "B. Melilla", "B. PTS", "B. Políticas y Sociolog.", "B. Politécnica",
    "B. Psicología y Letras B", "B. S. Jerónimo", "B. Traductores e Intérpretes",
    "B. Arquitectura", "B. Bellas Artes", "B. Ceuta",
    "B. Ciencias", "B. Colegio Máximo", "B. Deporte", "B. Derecho",
    "B. Económicas y Empres.", "B. Educación", "B. Farmacia"
]

df = pd.read_excel("Grados_UGR_Centros.xlsx")
df.columns = df.columns.str.strip()

def extraer_porcentaje_y_ordenar(archivos, ruta):
    archivos_con_porcentaje = []
    for archivo in archivos:
        if archivo.endswith(".txt"):
            ruta_completa = os.path.join(ruta, archivo)
            with open(ruta_completa, "r", encoding="utf-8", errors="ignore") as f:
                contenido = f.read()
            match = re.search(r"Porcentaje estimado de cambio: (\d+)%", contenido)
            porcentaje = int(match.group(1)) if match else 0
            archivos_con_porcentaje.append((archivo, porcentaje, contenido))
    return sorted(archivos_con_porcentaje, key=lambda x: x[1], reverse=True)

@app.route("/", methods=["GET", "POST"])
def index():
    mensaje = ""
    feedback = ""
    contenido = ""
    grados_filtrados = pd.DataFrame()
    seleccion = ""

    if request.method == "POST":
        seleccion = request.form.get("biblioteca")
        accion = request.form.get("accion")

        if accion == "confirmar_grados":
            urls = request.form.getlist("grados_seleccionados")
            nombres_carpetas = [normalizar_nombre(url) for url in urls]

            secciones = []
            for carpeta in nombres_carpetas:
                ruta = os.path.join(BASE_PATH, carpeta)
                if os.path.exists(ruta):
                    secciones.append(f"<h2>{carpeta}</h2>")
                    archivos = sorted(os.listdir(ruta))
                    archivos_ordenados = extraer_porcentaje_y_ordenar(archivos, ruta)
                    for archivo, porcentaje, contenido_txt in archivos_ordenados:
                        secciones.append(f"<h4>{archivo}</h4><pre>{contenido_txt}</pre><hr>")
                else:
                    secciones.append(f"<p>❌ No se encontró la carpeta: {carpeta}</p>")

            contenido = "\n".join(secciones)
            feedback = f"✅ Se han cargado {len(nombres_carpetas)} grado(s)."

        elif seleccion:
            mensaje = f"📚 Ha seleccionado: {seleccion}"
            grados_filtrados = df[
                df['Biblioteca'].fillna('').str.split(r'\s*\+\s*').apply(lambda bibl_list: seleccion in bibl_list)
            ]

    return render_template("index.html", bibliotecas=bibliotecas, mensaje=mensaje, feedback=feedback,
                           seleccion=seleccion, grados=grados_filtrados, contenido=contenido)

def normalizar_nombre(url):
    return url.strip().split("/")[-1].lower().replace("_", "-").replace("–", "-").replace(" ", "-")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
