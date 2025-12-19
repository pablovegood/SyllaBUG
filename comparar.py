""" El propósito de este programa es comparar las guias docentes del año anterior con las del actual. Pero, ¿por qué?
Con el propósito de facilitar y agilizar el trabajo al personal de biblioteca de la UGR en la tarea de actualizar
la bibliografía de las guías docentes de TOOODAS las asignaturas (que cuenten con bibliografía, es decir, TFG o
prácticas de empresa no son tenidas en cuenta) en Leganto (se intenta asumir que el año pasado fueron actualizadas
todas, aunque en realidad no tendría porque ser así).
"""

import os
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
import textwrap
from concurrent.futures import ProcessPoolExecutor, as_completed

""" Este fragmento de código indica DÓNDE se guardarán los archivos que muestren las diferencias entre las guías del 
año actual y las del año pasado (eliminadas, añadidas, sin cambios), actualmente se está indicando que las comparativas 
se guarden en BibliografiasUGR/grados/Comparativas y dentro se guardarán los directorios de los grados.
BASE_OLD = os.path.join(BASE_DIR, "2024-2025") y BASE_NEW = os.path.join(BASE_DIR, "2025-2026") indican de donde se 
deben extraer las bibliografías antiguas y las nuevas respectivamente. Si se quieren cambiar las comparativas para el 
año actual, basta con poner el año anterior en old (2027-2028) y en new el actual (2028-2029)"""
BASE_DIR = os.path.join("BibliografiasUGR", "grados")
BASE_OLD = os.path.join(BASE_DIR, "2024-2025")
BASE_NEW = os.path.join(BASE_DIR, "2025-2026")
COMPARATIVAS_BASE = os.path.join(BASE_DIR, "Comparativas")
os.makedirs(COMPARATIVAS_BASE, exist_ok=True)

# Esta línea de código configura el paralelismo del código para poder acelerar el proceso de extraer las comparativas
MAX_WORKERS = max(2, (os.cpu_count() or 4) - 1)  # ajusta a tu máquina

# Indica el ancho del justificado
JUSTIFY_WIDTH = 100

# ====== Normalización / utilidades ======
PUNCT_END = r"[.;:,·•]+$"
PUBLISHERS_CITIES = (
    "editorial|ediciones?|ed\\.?|piramide|paraninfo|ariel|deusto|thomson|"
    "garceta|sanz|torres|pearson|mcgraw|hill|anaya|oxford|elsevier|"
    "granada|madrid|barcelona|sevilla|valencia"
)
GUIDE_HEADER_RE = re.compile(r"^\s*gu[ií]a docente\b", re.IGNORECASE)

def _norm(s: str) -> str:
    return quitar_acentos(s).lower().strip()

def strip_bullets_and_punct(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^(\+|-|=|~)?\s*•?\s*", "", s)
    s = re.sub(PUNCT_END, "", s).strip()
    s = re.sub(r"\s{2,}", " ", s)
    return s

def quitar_acentos(s: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize("NFD", s) if not unicodedata.combining(ch))

def slugify_nombre(s: str, use_underscores=True) -> str:
    if not s:
        return "desconocido"
    s = quitar_acentos(s)
    s = re.sub(r'[\\/*?:"<>|]', "", s).strip()
    if use_underscores:
        s = re.sub(r"\s+", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
    else:
        s = s.lower()
        s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "desconocido"

def normalizar_nombre(texto: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', texto.lower()) if unicodedata.category(c) != 'Mn')

def remove_urls_years_editions_raw(s: str) -> str:
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"\b(1[89]\d{2}|20\d{2}|21\d{2})\b", " ", s)
    s = re.sub(r"\b\d{1,2}\s*(?:ª|a|\.ª)?\s*(?:ed\.?|edicion|edición)\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(?:segunda|tercera|cuarta|quinta)\s+(?:edicion|edición)\b", " ", s, flags=re.IGNORECASE)
    return s

def normalize_for_match(s: str) -> str:
    s = strip_bullets_and_punct(s)
    s = normalizar_nombre(s)
    s = remove_urls_years_editions_raw(s)
    s = re.sub(fr"\b({PUBLISHERS_CITIES})\b", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    tokens = s.split(); tokens.sort()
    return " ".join(tokens)

def normalize_without_years_editions(s: str) -> str:
    s = strip_bullets_and_punct(s)
    s = normalizar_nombre(s)
    s = remove_urls_years_editions_raw(s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    tokens = s.split(); tokens.sort()
    return " ".join(tokens)

def normalize_without_publishers(s: str) -> str:
    s = strip_bullets_and_punct(s)
    s = normalizar_nombre(s)
    s = remove_urls_years_editions_raw(s)
    s = re.sub(fr"\b({PUBLISHERS_CITIES})\b", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    tokens = s.split(); tokens.sort()
    return " ".join(tokens)

def years_anywhere(s: str) -> set[str]:
    return set(re.findall(r"\b(1[89]\d{2}|20\d{2}|21\d{2})\b", s))

def has_year(s: str) -> bool:
    return bool(years_anywhere(s))

def pick_longer_with_year(a: str, b: str) -> str:
    ay, by = has_year(a), has_year(b)
    if ay and not by: return a
    if by and not ay: return b
    if ay and by: return a if len(a) >= len(b) else b
    return a if len(a) >= len(b) else b

def ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def tokens(s: str) -> set:
    return set(s.split())

def token_coverage_equal(a: str, b: str, threshold: float = 0.9) -> bool:
    a_norm = normalize_without_publishers(a)
    b_norm = normalize_without_publishers(b)
    ta, tb = tokens(a_norm), tokens(b_norm)
    if not ta or not tb:
        return False
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    inter = len(short & long_)
    coverage = inter / max(len(short), 1)
    return coverage >= threshold

def best_match(item: str, candidates: set, threshold: float = 0.86):
    best_cand, best_score = None, 0.0
    a = normalize_for_match(item)
    for cand in candidates:
        b = normalize_for_match(cand)
        score = SequenceMatcher(None, a, b).ratio()
        if score > best_score:
            best_score, best_cand = score, cand
    return (best_cand, best_score) if best_score >= threshold else (None, 0.0)

# ====== Lectura robusta de recursos desde TXT ======
BULLET_PREFIX_RE = re.compile(
    r"^[\s]*("
    r"[\u2022\u2023\u25E6\u2043\u2219\-\–\—\*•]"
    r"|(?:\(?\d{1,3}[.)])"
    r")\s*"
)
SECTION_HEADER_RE = re.compile(
    r"^(?:❌|📚|🔁|✅|📊|Recursos eliminados|Recursos sin cambios|Misma obra|"
    r"Recursos añadidos|Porcentaje estimado|Comparativa de bibliografía|🆚)\b",
    re.IGNORECASE
)
SEPARATOR_RE = re.compile(r"^[-=]{5,}$")

def _probable_entry(s: str) -> bool:
    if len(s) < 8: return False
    has_letters = re.search(r"[A-Za-zÁÉÍÓÚÜáéíóúüñÑ]", s) is not None
    has_punct = re.search(r"[.,;:()]", s) is not None
    has_year = re.search(r"\b(1[89]\d{2}|20\d{2}|21\d{2})\b", s) is not None
    has_isbn = re.search(r"\b(?:ISBN|ISSN|DOI)\b", s, re.IGNORECASE) is not None
    return (has_letters and has_punct) or has_year or has_isbn

def leer_recursos_txt(ruta: str) -> set:
    """
    Lee recursos desde .txt de forma robusta:
    - Quita cualquier viñeta/guion/numeración al inicio.
    - Ignora cabeceras/separadores si los hubiera.
    - Ignora la primera línea si es una URL (2024-2025 y 2025-2026).
    - Ignora encabezados tipo 'Guía docente ...' y un caso concreto.
    """
    if not os.path.exists(ruta):
        return set()
    recursos = set()
    with open(ruta, "r", encoding="utf-8") as f:
        lineas = [ln.rstrip("\n") for ln in f]

    # Omitir primera línea si es URL
    if lineas and re.match(r"^\s*https?://", lineas[0], flags=re.IGNORECASE):
        lineas = lineas[1:]
    # Omitir cabecera si no parece entrada
    if lineas and (SECTION_HEADER_RE.search(lineas[0]) or not _probable_entry(lineas[0])):
        lineas = lineas[1:]

    SKIP_EXACT_NORMS = {
        _norm("Guía docente de Análisis y Control de Costes (43311B1)"),
    }

    for raw in lineas:
        s = raw.strip()
        if not s: continue
        if SEPARATOR_RE.match(s): continue
        if SECTION_HEADER_RE.match(s): continue
        s_norm = _norm(s)
        if GUIDE_HEADER_RE.match(s) or s_norm in SKIP_EXACT_NORMS:
            continue
        s = BULLET_PREFIX_RE.sub("", s).strip()
        s = strip_bullets_and_punct(s)
        if not s: continue
        if _probable_entry(s) or len(s) >= 12:
            recursos.add(s)
    return recursos

# ====== Extra: justificación y separación de recursos ======
def justify_line(line: str, width: int) -> str:
    words = line.split()
    if not words: return ""
    if len(words) == 1: return words[0]
    text_len = sum(len(w) for w in words)
    total_spaces = width - text_len
    if total_spaces <= len(words) - 1:
        return " ".join(words)
    gaps = len(words) - 1
    base = total_spaces // gaps
    extra = total_spaces % gaps
    parts = []
    for i, w in enumerate(words[:-1]):
        pads = 1 + base + (1 if i < extra else 0)
        parts.append(w + " " * pads)
    parts.append(words[-1])
    return "".join(parts)

def justify_text(text: str, width: int) -> str:
    if not text: return ""
    wrapped = textwrap.wrap(text, width=width)
    if not wrapped: return ""
    lines = []
    for i, ln in enumerate(wrapped):
        lines.append(ln if i == len(wrapped) - 1 else justify_line(ln, width))
    return "\n".join(lines)

def format_entry(s: str) -> str:
    return justify_text(s, JUSTIFY_WIDTH)

# ====== Extraer nombre/código de asignatura ======
def split_name_and_code_from_filename(filename: str) -> tuple[str, str | None]:
    base = os.path.splitext(os.path.basename(filename))[0]
    matches = list(re.finditer(r"[A-Za-z0-9]{3,}", base))
    if not matches:
        return base.strip(), None
    last = matches[-1]
    code = last.group(0)
    name = (base[:last.start()] + base[last.end():]).strip()
    name = re.sub(r"[\s\-_()]+$", "", name)
    name = re.sub(r"^[\s\-_()]+", "", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return (name or base).strip(), code

def degree_code3_from_subject_code(subj_code: str) -> str:
    return subj_code[:3] if subj_code and len(subj_code) >= 3 else "000"

# ====== Extraer nombre de grado y código desde carpeta ======
def split_degree_name_and_code_from_folder(folder_name: str) -> tuple[str, str]:
    raw = folder_name.strip()
    parts = re.split(r"[-_]", raw)
    if parts and re.fullmatch(r"[A-Za-z0-9]{3,}", parts[-1]):
        cod3 = parts[-1][:3]
        nombre = re.sub(r"[-_]*" + re.escape(parts[-1]) + r"$", "", raw).strip("-_")
        if nombre.startswith("grado-"):
            nombre = nombre[6:]
        nombre = nombre or raw
        return nombre, cod3
    name = raw[6:] if raw.startswith("grado-") else raw
    return name or "desconocido", "000"

# ====== Indexado por año ======
def index_year_folder(root: str) -> dict[str, tuple[str, str, str]]:
    idx = {}
    if not os.path.isdir(root): return idx
    for sub in os.listdir(root):
        subdir = os.path.join(root, sub)
        if not os.path.isdir(subdir): continue
        grado_nombre, _ = split_degree_name_and_code_from_folder(os.path.basename(subdir))
        for fn in os.listdir(subdir):
            if not fn.endswith(".txt"): continue
            nombre_asig, codigo = split_name_and_code_from_filename(fn)
            if not codigo: continue
            idx[codigo] = (os.path.join(subdir, fn), nombre_asig, grado_nombre)
    return idx

# ====== Comparación ======
def comparar_sets(recursos_2024: set, recursos_2025: set):
    set_2024 = set(recursos_2024)
    set_2025 = set(recursos_2025)

    iguales = set_2024 & set_2025
    set_2024 -= iguales
    set_2025 -= iguales

    emp_24 = set()
    emp_25 = set()
    changed_old = []
    changed_new = []

    for r24 in list(set_2024):
        cand, score = best_match(r24, set_2025, threshold=0.86)
        if not cand:
            for c in set_2025:
                if ratio(normalize_without_publishers(r24), normalize_without_publishers(c)) >= 0.92:
                    cand, score = c, 0.92
                    break
        if not cand:
            for c in set_2025:
                if token_coverage_equal(r24, c, threshold=0.9):
                    cand, score = c, 0.91
                    break
        if not cand:
            continue

        core1 = normalize_without_years_editions(r24)
        core2 = normalize_without_years_editions(cand)
        core_eq = (ratio(core1, core2) >= 0.90) or token_coverage_equal(r24, cand, threshold=0.9)
        if core_eq:
            y_old = years_anywhere(r24)
            y_new = years_anywhere(cand)
            if y_old and y_new and y_old != y_new:
                changed_old.append(r24)
                changed_new.append(cand)
                emp_24.add(r24); emp_25.add(cand)
            else:
                iguales.add(pick_longer_with_year(r24, cand))
                emp_24.add(r24); emp_25.add(cand)
        else:
            iguales.add(cand)
            emp_24.add(r24); emp_25.add(cand)

    restantes_eliminados = sorted(set_2024 - emp_24)
    restantes_anadidos = sorted(set_2025 - emp_25)
    eliminados = sorted(restantes_eliminados + changed_old)
    anadidos = sorted(restantes_anadidos + changed_new)
    comunes = sorted(iguales)

    total_actual = max(len(recursos_2025), 1)
    porcentaje = min((len(eliminados) + len(anadidos)) / total_actual, 1.0)
    return eliminados, comunes, anadidos, porcentaje

""" Como se puede apreciar en esta función, se crea el path para almacenar el archivo de la comparativa, para ello, se 
 usa la kebab-case (también llamada slug, por una babosa) y se pasa el nombre del grado primero (Educacion Infantil -->
 educacion-infantil) seguido por el código del grado  (son 3 digitos alfanuméricos y todos los ccódigos de las 
 asignaturas de ese grado empezaran por ese código)"""
def build_comparativa_path(dest_root: str, nombre_grado: str, grado_code3: str, nombre_asignatura: str, subj_code: str) -> str:
    grado_dirname = f"{slugify_nombre(nombre_grado, use_underscores=False)}_{grado_code3}"
    asig_filename = f"{slugify_nombre(nombre_asignatura, use_underscores=True)}_{subj_code}.txt"
    return os.path.join(dest_root, grado_dirname, asig_filename)


""" Si se quisiera modificar el formato o los elementos que se muestran en los archivos generados de comparativa, ahora
es el momento para hacerlo, ya que escribir_comparativa hace precisamente eso"""
def escribir_comparativa(dest_root: str, nombre_grado: str, grado_code3: str, nombre_asignatura: str, subj_code: str,
                         eliminados: list[str], comunes: list[str], anadidos: list[str], porcentaje: float):
    grado_dirname = f"{slugify_nombre(nombre_grado, use_underscores=False)}_{grado_code3}"
    asig_filename = f"{slugify_nombre(nombre_asignatura, use_underscores=True)}_{subj_code}.txt"
    grado_path = os.path.join(dest_root, grado_dirname)
    os.makedirs(grado_path, exist_ok=True)
    out_path = os.path.join(grado_path, asig_filename)

    """ Función usada por escribir_bibliografía escribe en el archivo f (file) los elementos pasados como parámetro de 
    items, si no está vacío recorre los elementos y los va imprimiendo (uno por línea) """
    def _print_list(f, items):
        if items:
            for r in items:
                f.write(format_entry(r) + "\n\n")
        else:
            f.write("No hay elementos.\n\n")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"{nombre_asignatura} ({subj_code})\n")
        f.write(f"Grado: {nombre_grado} ({grado_code3})\n")
        f.write("\n\n")

        f.write(f"❌ Recursos eliminados ({len(eliminados)}):\n")
        f.write("\n")
        _print_list(f, eliminados)

        f.write(f"📚 Recursos sin cambios ({len(comunes)}):\n")
        f.write("\n")
        _print_list(f, comunes)

        f.write(f"✅ Recursos añadidos ({len(anadidos)}):\n")
        f.write("\n")
        _print_list(f, anadidos)

        porcentaje_limitado = min(max(porcentaje, 0.0), 1.0)
        f.write("📊 Porcentaje estimado de cambio: ")
        f.write(f"{int(porcentaje_limitado * 100)}% ")
        f.write(f"[{'█' * int(porcentaje_limitado * 10)}{'░' * (10 - int(porcentaje_limitado * 10))}]\n")

# ====== Indexado con nombres ======
def index_year_folder_with_names(root: str) -> dict[str, tuple[str, str, str]]:
    return index_year_folder(root)

# ====== Worker multiproceso ======
def worker_compare_and_write(job):
    """
    job: (subj_code, ruta24, ruta25, nombre_asig, nombre_grado, grado_code3, out_path_base)
    Devuelve (subj_code, n24, n25, n_comunes, n_add, n_del, written_bool, out_path)
    """
    (subj_code, ruta24, ruta25, nombre_asig, nombre_grado, grado_code3, out_base) = job

    # Saltar si ya existe (doble salvaguarda)
    out_path = build_comparativa_path(out_base, nombre_grado, grado_code3, nombre_asig, subj_code)
    if os.path.exists(out_path):
        return (subj_code, 0, 0, 0, 0, 0, False, out_path)

    rec24 = leer_recursos_txt(ruta24)
    rec25 = leer_recursos_txt(ruta25)
    eliminados, comunes, anadidos, pct = comparar_sets(rec24, rec25)
    escribir_comparativa(out_base, nombre_grado, grado_code3, nombre_asig, subj_code, eliminados, comunes, anadidos, pct)

    return (subj_code, len(rec24), len(rec25), len(comunes), len(anadidos), len(eliminados), True, out_path)

# ====== Recorrido principal ======
def main():
    print("📁 Indexando 2024-2025…")
    idx24 = index_year_folder_with_names(BASE_OLD)
    print(f" → {len(idx24)} asignaturas indexadas")

    print("📁 Indexando 2025-2026…")
    idx25 = index_year_folder_with_names(BASE_NEW)
    print(f" → {len(idx25)} asignaturas indexadas")

    codigos_comunes = sorted(set(idx24.keys()) & set(idx25.keys()))
    print(f"🔗 Códigos comunes: {len(codigos_comunes)}")

    # Construir trabajos y filtrar los que ya existen
    jobs = []
    already = 0
    for subj_code in codigos_comunes:
        ruta24, asig24, grado24 = idx24[subj_code]
        ruta25, asig25, grado25 = idx25[subj_code]
        nombre_asig = asig25 if asig25 else asig24
        nombre_grado = grado25 if grado25 else grado24
        grado_code3 = degree_code3_from_subject_code(subj_code)

        out_path = build_comparativa_path(COMPARATIVAS_BASE, nombre_grado, grado_code3, nombre_asig, subj_code)
        if os.path.exists(out_path):
            already += 1
            continue

        jobs.append((subj_code, ruta24, ruta25, nombre_asig, nombre_grado, grado_code3, COMPARATIVAS_BASE))

    print(f"🚀 Tareas a generar: {len(jobs)} (ya existentes: {already})")

    generadas = 0
    if jobs:
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = [ex.submit(worker_compare_and_write, job) for job in jobs]
            for fut in as_completed(futures):
                try:
                    subj_code, n24, n25, ncom, nadd, ndel, wrote, outp = fut.result()
                    if wrote:
                        generadas += 1
                        print(f"✔ {subj_code}: 2024={n24} | 2025={n25} | comunes={ncom} | +{nadd} | -{ndel}")
                    else:
                        print(f"⏭ {subj_code}: ya existía → {outp}")
                except Exception as e:
                    print(f"❗ Error en tarea: {e}")

    # Resumen global
    resumen_path = os.path.join(COMPARATIVAS_BASE, f"Resumen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    with open(resumen_path, "w", encoding="utf-8") as f:
        f.write("📘 Resumen de comparativas (por código):\n")
        f.write("=" * 40 + "\n")
        f.write(f"Total asignaturas con código común: {len(codigos_comunes)}\n")
        f.write(f"Comparativas generadas en esta ejecución: {generadas}\n")
        f.write(f"Comparativas ya existentes (omitidas): {already}\n")

if __name__ == "__main__":
    main()
