from flask import Flask, render_template, request
import pandas as pd
import os
import re
from urllib.parse import urlparse

# Explicitar carpetas de plantillas/estáticos
app = Flask(__name__, template_folder="templates", static_folder="static")

BASE_PATH = os.path.join("BibliografiasUGR", "grados", "Comparativas")

bibliotecas = [
    "B. Filosofía y Letras A", "B. Informática y Telecom.",
    "B. Melilla", "B. PTS", "B. Políticas y Sociolog.", "B. Politécnica",
    "B. Filosofía y Letras B", "B. S. Jerónimo", "B. Traductores e Intérpretes",
    "B. Arquitectura", "B. Bellas Artes", "B. Ceuta",
    "B. Ciencias", "B. Colegio Máximo", "B. Deporte", "B. Derecho",
    "B. Económicas y Empres.", "B. Educación", "B. Farmacia"
]

# ---- Carga segura del Excel (no romper en Render si falta el archivo o el engine) ----
_DF_PATH = "Grados_UGR_Centros.xlsx"
def _cargar_df():
    if not os.path.exists(_DF_PATH):
        return pd.DataFrame()
    try:
        # requiere openpyxl en requirements.txt
        df_ = pd.read_excel(_DF_PATH, engine="openpyxl")
    except Exception:
        # último recurso: intenta sin engine (por si el entorno ya decide uno)
        try:
            df_ = pd.read_excel(_DF_PATH)
        except Exception:
            return pd.DataFrame()
    df_.columns = df_.columns.str.strip()
    return df_

df = _cargar_df()

def extraer_porcentaje_y_ordenar(archivos, ruta):
    archivos_con_porcentaje = []
    for archivo in archivos:
        if archivo.endswith(".txt"):
            ruta_completa = os.path.join(ruta, archivo)
            try:
                with open(ruta_completa, "r", encoding="utf-8", errors="ignore") as f:
                    contenido = f.read()
            except Exception:
                contenido = ""
            match = re.search(r"Porcentaje estimado de cambio: (\d+)%", contenido)
            porcentaje = int(match.group(1)) if match else 0
            archivos_con_porcentaje.append((archivo, porcentaje, contenido))
    return sorted(archivos_con_porcentaje, key=lambda x: x[1], reverse=True)

def nombre_amigable_carpeta(slug: str) -> str:
    base = os.path.splitext(slug)[0]
    base = re.sub(r"[_-]\d{3,}$", "", base)
    base = base.replace("_", " ").replace("-", " ").replace("–", " ")
    base = re.sub(r"\s+", " ", base).strip().lower()
    accent_map = {
        "grado": "Grado", "arqueologia": "Arqueología", "psicologia": "Psicología",
        "sociologia": "Sociología", "biologia": "Biología", "geologia": "Geología",
        "filologia": "Filología", "tecnologia": "Tecnología", "economia": "Economía",
        "economicas": "Económicas", "administracion": "Administración", "direccion": "Dirección",
        "comunicacion": "Comunicación", "educacion": "Educación", "traduccion": "Traducción",
        "interpretacion": "Interpretación", "matematicas": "Matemáticas", "fisica": "Física",
        "quimica": "Química", "informatica": "Informática", "musica": "Música",
        "politicas": "Políticas", "ingenieria": "Ingeniería", "farmacia": "Farmacia",
        "historia": "Historia", "derecho": "Derecho", "ciencias": "Ciencias",
        "arte": "Arte", "bellas": "Bellas", "artes": "Artes",
        "traduccion e interpretacion": "Traducción e Interpretación",
    }
    preps = {"de","del","la","las","el","los","y","e","o","u","en","por","para","con","a"}
    palabras = base.split(" ")
    bonito, i = [], 0
    while i < len(palabras):
        if i + 2 < len(palabras):
            tri = " ".join(palabras[i:i+3])
            if tri in accent_map:
                bonito.append(accent_map[tri]); i += 3; continue
        if i + 1 < len(palabras):
            bi = " ".join(palabras[i:i+2])
            if bi in accent_map:
                bonito.append(accent_map[bi]); i += 2; continue
        p = palabras[i]
        if p in accent_map:
            bonito.append(accent_map[p])
        elif i > 0 and p in preps:
            bonito.append(p)
        else:
            bonito.append(p.capitalize())
        i += 1
    if bonito and bonito[0].lower() == "grado":
        bonito[0] = "Grado"
    return " ".join(bonito)

def parsear_titulo_y_codigo(nombre_archivo: str):
    base = os.path.splitext(nombre_archivo)[0]
    code_pat = r"[A-Za-z0-9]{5,}"
    m_suf = re.search(rf"[_-]({code_pat})$", base)
    codigo = ""
    if m_suf and any(ch.isdigit() for ch in m_suf.group(1)):
        codigo = m_suf.group(1)
        base = base[:m_suf.start()]
    base = base.replace("_", " ").replace("–", " ").replace("-", " ")
    base = re.sub(r"\s+", " ", base).strip()
    base = re.sub(r"^(gu[ií]a\s+docente|guia\s+docente|guia_docente)\s*", "", base, flags=re.IGNORECASE)
    base = re.sub(r"\(pdf\)", "", base, flags=re.IGNORECASE).strip()
    if not codigo:
        for m in re.finditer(code_pat, base):
            bloque = m.group(0)
            if any(ch.isdigit() for ch in bloque):
                codigo = bloque
                base = (base[:m.start()] + base[m.end():]).strip()
                break
    preps = {"de","del","la","las","el","los","y","e","o","u","en","por","para","con","a"}
    palabras = [p for p in base.split(" ") if p]
    palabras_fmt = [(p.capitalize() if (i == 0 or p.lower() not in preps) else p.lower())
                    for i, p in enumerate(palabras)]
    titulo = " ".join(palabras_fmt)
    return titulo, codigo

STOP_SEGMENTS = {
    "docencia","plan-estudios","guia-docente","presentacion","informacion",
    "movilidad","practicas","profesorado","itinerarios","salidas-profesionales",
    "acceso","admision","matricula",
    "ramas","ramas-de-conocimiento","centros","facultades","escuelas",
    "grado","grados","doble-grado","grado-en","doble-grado-en"
}

def _dirs_en_comparativas():
    try:
        return [d for d in os.listdir(BASE_PATH) if os.path.isdir(os.path.join(BASE_PATH, d))]
    except FileNotFoundError:
        return []

def _clean_segment(seg: str) -> str:
    s = seg.lower().strip()
    s = re.sub(r"^(doble-grado(-en)?|grado(-en)?)\-", "", s)
    s = re.sub(r"[-_]\d{3,}$", "", s)
    s = s.replace("–", "-")
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s

def _match_slug_en_dirs(slug_base: str, dirs: list[str]) -> str | None:
    if not slug_base:
        return None
    s = slug_base.strip().lower()
    s = re.sub(r"[-_]\d{3,}$", "", s)
    hy = s.replace("_", "-")
    us = s.replace("-", "_")
    candidates = [
        d for d in dirs
        if d == s or d == hy or d == us
        or d.startswith(hy + "_") or d.startswith(us + "_")
        or d.startswith("grado-" + hy + "_") or d.startswith("grado_" + us + "_")
    ]
    if not candidates:
        norm = re.sub(r"[-_]+", "", s)
        for d in dirs:
            if re.sub(r"[-_]+", "", d).startswith(norm):
                candidates.append(d)
    if not candidates:
        return None
    with_code = [d for d in candidates if re.search(r"[_-]\d{3,}$", d)]
    return sorted(with_code or candidates)[0]

def resolver_carpeta(entrada: str) -> str:
    s = (entrada or "").strip()
    dirs = _dirs_en_comparativas()
    if not s or not dirs:
        return s
    if s in dirs:
        return s
    if "://" in s:
        path = urlparse(s).path
        segs = [t for t in path.split("/") if t]
        for seg in reversed(segs):
            raw = seg.lower()
            if raw in STOP_SEGMENTS or raw.isdigit():
                continue
            base = _clean_segment(raw)
            if not base or base in STOP_SEGMENTS:
                continue
            found = _match_slug_en_dirs(base, dirs)
            if found:
                return found
        return _clean_segment(segs[-1]) if segs else s
    bonito_key = s.lower()
    for d in dirs:
        if nombre_amigable_carpeta(d).lower() == bonito_key:
            return d
    found = _match_slug_en_dirs(s, dirs)
    return found or s

def _detectar_columna_entrada(df_: pd.DataFrame) -> str | None:
    candidates = ["URL", "Url", "Enlace", "Link", "Slug", "Carpeta", "Grado URL"]
    for c in candidates:
        if c in df_.columns:
            return c
    for c in ["Grado", "Título", "Titulo", "Nombre", "Nombre Grado"]:
        if c in df_.columns:
            return c
    return None

def _extraer_codigo_desde_entrada(valor: str) -> str:
    carpeta = resolver_carpeta(valor)
    m = re.search(r"(\d{3,})$", carpeta or "")
    return m.group(1) if m else ""

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
            entradas = request.form.getlist("grados_seleccionados")
            nombres_carpetas = [resolver_carpeta(x) for x in entradas]

            secciones = []
            for carpeta in nombres_carpetas:
                ruta = os.path.join(BASE_PATH, carpeta)
                if os.path.exists(ruta):
                    titulo_grado = nombre_amigable_carpeta(carpeta)
                    secciones.append(f"<h2>{titulo_grado}</h2>")
                    try:
                        archivos = sorted(os.listdir(ruta))
                    except Exception:
                        archivos = []
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
            if not df.empty and "Biblioteca" in df.columns:
                grados_filtrados = df[
                    df['Biblioteca'].fillna('').str.split(r'\s*\+\s*').apply(lambda bibl_list: seleccion in bibl_list)
                ].copy()
                col_entrada = _detectar_columna_entrada(grados_filtrados)
                if col_entrada:
                    grados_filtrados["CÓDIGO"] = grados_filtrados[col_entrada].apply(_extraer_codigo_desde_entrada)
                else:
                    grados_filtrados["CÓDIGO"] = ""
            else:
                grados_filtrados = pd.DataFrame()

    return render_template(
        "index.html",
        bibliotecas=bibliotecas,
        mensaje=mensaje,
        feedback=feedback,
        seleccion=seleccion,
        grados=grados_filtrados,
        contenido=contenido
    )

if __name__ == "__main__":
    # Render: usar 0.0.0.0 y PORT del entorno
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)
