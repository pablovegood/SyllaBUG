import tkinter as tk
from tkinter import scrolledtext
from threading import Thread
import traceback

try:
    from extraer_guias_masters import main as main_masters
except Exception as e:
    def main_masters():
        raise RuntimeError("❌ Error al importar 'extraer_guias_masters.py': " + str(e))

try:
    from extraer_bibliografia_toda_ugr import main as main_grados
except Exception as e:
    def main_grados():
        raise RuntimeError("❌ Error al importar 'extraer_bibliografia_toda_ugr.py': " + str(e))


def lanzar_scraper(tipo):
    grados_btn.config(state="disabled")
    masters_btn.config(state="disabled")
    salida.insert(tk.END, f"\n🚀 Iniciando extracción de bibliografías ({tipo})...\n")
    salida.see(tk.END)

    if tipo == "GRADOS":
        Thread(target=wrapper, args=(main_grados,)).start()
    elif tipo == "MÁSTERS":
        Thread(target=wrapper, args=(main_masters,)).start()


def wrapper(func):
    try:
        resultado = func()
        salida.insert(tk.END, "✅ Proceso completado con éxito.\n")

        if resultado and isinstance(resultado, dict):
            mostrar_resumen_en_terminal(resultado)
        else:
            salida.insert(tk.END, "⚠️ No se devolvió información estructurada.\n")

    except Exception as e:
        salida.insert(tk.END, f"❌ Error detectado: {e}\n")
        salida.insert(tk.END, traceback.format_exc())
    finally:
        salida.see(tk.END)
        grados_btn.config(state="normal")
        masters_btn.config(state="normal")


def mostrar_resumen_en_terminal(data):
    tipo = data.get("tipo", "DESCONOCIDO")
    total = data.get("total_cambiadas", 0)
    cambios = data.get("cambios", {})

    salida.insert(tk.END, f"\n📂 Resultado para {tipo}:\n")
    salida.insert(tk.END, f"📌 Total de asignaturas con cambios: {total}\n")

    for grupo in ["100%", "80-99%", "50-79%"]:
        items = sorted(cambios.get(grupo, []))
        if items:
            salida.insert(tk.END, f"\n🔸 {grupo} de cambio ({len(items)} asignaturas):\n")
            for asignatura in items:
                salida.insert(tk.END, f"   • {asignatura}\n")

    salida.insert(tk.END, "\n--------------------------\n")
    salida.see(tk.END)


# Interfaz
root = tk.Tk()
root.title("UGR Bibliografía Scraper")
root.geometry("900x550")

frame_botones = tk.Frame(root)
frame_botones.pack(pady=10)

grados_btn = tk.Button(frame_botones, text="GRADOS", font=("Arial", 12), width=20,
                       command=lambda: lanzar_scraper("GRADOS"))
grados_btn.grid(row=0, column=0, padx=20)

masters_btn = tk.Button(frame_botones, text="MÁSTERS", font=("Arial", 12), width=20,
                        command=lambda: lanzar_scraper("MÁSTERS"))
masters_btn.grid(row=0, column=1, padx=20)

salida = scrolledtext.ScrolledText(root, wrap=tk.WORD, font=("Courier", 10), width=110, height=28)
salida.pack(padx=10, pady=10)

root.mainloop()
