from flask import Flask, render_template, request
import pandas as pd
import os
import re

# Explicitar carpetas de plantillas/estáticos
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
    """
    Devuelve [(nombre_archivo, porcentaje, contenido)] ordenado desc por porcentaje.
    Si no se encuentra el indicador, se usa 0.
    """
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


def nombre_amigable_carpeta(slug: str) -> str:
    """
    Convierte nombres de carpeta tipo 'grado-ciencias-politicas-administracion'
    en 'Grado Ciencias Políticas Administración' (con acentos comunes).
    """
    base = os.path.splitext(slug)[0]
    base = base.replace("_", " ").replace("-", " ").replace("–", " ")
    base = re.sub(r"\s+", " ", base).strip().lower()

    # Acentos frecuentes en nombres de titulaciones
    accent_map = {
        "grado": "Grado",
        "arqueologia": "Arqueología",
        "psicologia": "Psicología",
        "sociologia": "Sociología",
        "biologia": "Biología",
        "geologia": "Geología",
        "filologia": "Filología",
        "tecnologia": "Tecnología",
        "economia": "Economía",
        "economicas": "Económicas",
        "administracion": "Administración",
        "direccion": "Dirección",
        "comunicacion": "Comunicación",
        "educacion": "Educación",
        "traduccion": "Traducción",
        "interpretacion": "Interpretación",
        "matematicas": "Matemáticas",
        "fisica": "Física",
        "quimica": "Química",
        "informatica": "Informática",
        "musica": "Música",
        "politicas": "Políticas",
        "ingenieria": "Ingeniería",
        "farmacia": "Farmacia",
        "historia": "Historia",
        "derecho": "Derecho",
        "ciencias": "Ciencias",
        "arte": "Arte",
        "bellas": "Bellas",
        "artes": "Artes",
        "traduccion e interpretacion": "Traducción e Interpretación",
    }

    preps = {"de", "del", "la", "las", "el", "los", "y", "e", "o", "u", "en", "por", "para", "con", "a"}

    palabras = base.split(" ")
    bonito = []
    i = 0
    while i < len(palabras):
        # Uniones frecuentes (trigramas/bigramas)
        if i + 2 < len(palabras):
            tri = " ".join(palabras[i:i+3])
            if tri in accent_map:
                bonito.append(accent_map[tri])
                i += 3
                continue
        if i + 1 < len(palabras):
            bi = " ".join(palabras[i:i+2])
            if bi in accent_map:
                bonito.append(accent_map[bi])
                i += 2
                continue

        p = palabras[i]
        if p in accent_map:
            bonito.append(accent_map[p])
        elif i > 0 and p in preps:
            bonito.append(p)  # preposiciones minúsculas
        else:
            bonito.append(p.capitalize())
        i += 1

    if bonito and bonito[0].lower() == "grado":
        bonito[0] = "Grado"

    return " ".join(bonito)


# ---------- Parseo del título de archivo: limpia 'Guía Docente' y '(pdf)' y extrae código ----------
CODIGO_RE = re.compile(r"\b\d{7}\b|\b\d{5}[a-z]\d\b", re.IGNORECASE)

def parsear_titulo_y_codigo(nombre_archivo: str):
    """
    'Guia Docente Pensamiento Árabe Contemporáneo (pdf) 27911e1.txt'
      -> titulo='Pensamiento Árabe Contemporáneo', codigo='27911e1'
    """
    base = os.path.splitext(nombre_archivo)[0]

    # Normalizar separadores
    base = base.replace("_", " ").replace("–", " ").replace("-", " ")
    base = re.sub(r"\s+", " ", base).strip()

    # Quitar 'Guía Docente' / 'Guia Docente' (con o sin tilde) al inicio
    base = re.sub(r"^(gu[ií]a\s+docente)\s*", "", base, flags=re.IGNORECASE)

    # Quitar cualquier '(pdf)' en el nombre
    base = re.sub(r"\(pdf\)", "", base, flags=re.IGNORECASE).strip()

    # Buscar código (7 dígitos o 5 dígitos + letra + dígito)
    codigo = ""
    cods = list(CODIGO_RE.finditer(base))
    if cods:
        codigo = cods[-1].group(0)  # último match
        base = (base[:cods[-1].start()] + base[cods[-1].end():]).strip()

    # Compactar espacios y capitalizar suave respetando preps
    base = re.sub(r"\s+", " ", base).strip()
    preps = {"de", "del", "la", "las", "el", "los", "y", "e", "o", "u", "en", "por", "para", "con", "a"}
    palabras = base.split(" ")
    palabras_fmt = [
        (p.capitalize() if (i == 0 or p.lower() not in preps) else p.lower())
        for i, p in enumerate(palabras) if p
    ]
    titulo = " ".join(palabras_fmt)

    return titulo, codigo


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
                    # Título bonito del grado
                    titulo_grado = nombre_amigable_carpeta(carpeta)
                    secciones.append(f"<h2>{titulo_grado}</h2>")

                    archivos = sorted(os.listdir(ruta))
                    archivos_ordenados = extraer_porcentaje_y_ordenar(archivos, ruta)
                    for archivo, porcentaje, contenido_txt in archivos_ordenados:
                        titulo, codigo = parsear_titulo_y_codigo(archivo)
                        izquierda = f"{titulo} ({codigo})" if codigo else titulo

                        secciones.append(
                            f"""
<details class="cmp">
  <summary class="toc">
    <span class="cmp-left">{izquierda}</span>
    <span class="toc-leader" aria-hidden="true"></span>
    <span class="cmp-pct">{porcentaje}%</span>
  </summary>
  <pre>{contenido_txt}</pre>
</details>
""".strip()
                        )
                else:
                    secciones.append(f"<p class='no-resultados'>❌ No se encontró la carpeta: {carpeta}</p>")

            contenido = "\n".join(secciones)
            feedback = f"✅ Se han cargado {len(nombres_carpetas)} grado(s)."

        elif seleccion:
            mensaje = f"📚 Has seleccionado: {seleccion}"
            grados_filtrados = df[
                df['Biblioteca'].fillna('').str.split(r'\s*\+\s*').apply(lambda bibl_list: seleccion in bibl_list)
            ]

    return render_template(
        "index.html",
        bibliotecas=bibliotecas,
        mensaje=mensaje,
        feedback=feedback,
        seleccion=seleccion,
        grados=grados_filtrados,
        contenido=contenido
    )


def normalizar_nombre(url):
    """Slug consistente desde la URL del grado para localizar carpeta."""
    return (
        url.strip()
        .split("/")[-1]
        .lower()
        .replace("_", "-")
        .replace("–", "-")
        .replace(" ", "-")
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
