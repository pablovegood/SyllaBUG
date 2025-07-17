import webview
import traceback
import asyncio

try:
    from extraer_guias_masters import main as main_masters
except Exception as e:
    def main_masters(callback=None):
        raise RuntimeError("❌ Error al importar 'extraer_guias_masters.py': " + str(e))

try:
    from extraer_bibliografia_toda_ugr import main as main_grados
except Exception as e:
    def main_grados(callback=None):
        raise RuntimeError("❌ Error al importar 'extraer_bibliografia_toda_ugr.py': " + str(e))


class API:
    def __init__(self):
        self._ventana = None  # ✅ nombre cambiado para evitar conflicto con pywebview internamente

    def lanzar(self, tipo):
        try:
            log = f"🚀 Iniciando extracción de bibliografías ({tipo})...\n"
            self.emitir_progreso(0, "Inicio")

            if tipo.upper() == "GRADOS":
                resultado = self.main_con_progreso(main_grados)
            elif tipo.upper() == "MÁSTERS":
                resultado = self.main_con_progreso(main_masters)
            else:
                return {"log": log + "❌ Tipo no reconocido."}

            log += "✅ Proceso completado con éxito.\n"

            if resultado and isinstance(resultado, dict):
                log += self.formatear_resumen(resultado)
            else:
                log += "⚠️ No se devolvió información estructurada.\n"
            return {"log": log}
        except Exception as e:
            return {"log": f"❌ Error: {e}\n{traceback.format_exc()}"}

    def main_con_progreso(self, funcion_objetivo):
        if asyncio.iscoroutinefunction(funcion_objetivo):
            return asyncio.run(funcion_objetivo(callback=self.emitir_progreso))
        else:
            return funcion_objetivo(callback=self.emitir_progreso)

    def emitir_progreso(self, porcentaje, estado=""):
        if self._ventana:
            js_code = f'actualizarProgreso({porcentaje}, "{estado}");'
            self._ventana.evaluate_js(js_code)

    def formatear_resumen(self, data):
        tipo = data.get("tipo", "DESCONOCIDO")
        total = data.get("total_cambiadas", 0)
        cambios = data.get("cambios", {})
        texto = f"\n📂 Resultado para {tipo}:\n📌 Total de asignaturas con cambios: {total}\n"

        for grupo in ["100%", "80-99%", "50-79%"]:
            items = sorted(cambios.get(grupo, []))
            if items:
                texto += f"\n🔸 {grupo} de cambio ({len(items)} asignaturas):\n"
                for asignatura in items:
                    texto += f"   • {asignatura}\n"
        texto += "\n--------------------------\n"
        return texto


if __name__ == '__main__':
    api = API()
    ventana = webview.create_window(
        "SyllaBUG: Comparador de Guías Docentes",
        html=open("template.html", encoding="utf-8").read(),
        js_api=api,
        width=950,
        height=600,
        min_size=(800, 500)
    )
    api._ventana = ventana  # ✅ Se asigna sin conflicto
    webview.start()
