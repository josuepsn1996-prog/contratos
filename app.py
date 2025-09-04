import streamlit as st
import openai
import base64
import tempfile
import fitz  # PyMuPDF
import re
import json
import pandas as pd

st.set_page_config(page_title="Ficha de Contrato Público", page_icon="📄")
st.title("📄 Ficha Institucional de Contrato de la Administración Pública")

st.markdown("""
Carga tu contrato público (PDF, escaneado o digital).  
La IA presenta los **elementos legales más importantes** del contrato en una ficha profesional y sistematizada.
""")

def limpiar_json_gpt(texto):
    # Extrae solo el bloque JSON entre llaves
    match = re.search(r'\{.*\}', texto, re.DOTALL)
    if match:
        bloque = match.group(0)
        # Quita saltos de línea dentro de los strings (entre comillas dobles)
        bloque = re.sub(r'"\s*\n\s*', '"', bloque)
        # Quita saltos de línea fuera de los valores
        bloque = re.sub(r'\n+', '\n', bloque)
        # Quita comas después del último elemento en listas/diccionarios
        bloque = re.sub(r',\s*([\]\}])', r'\1', bloque)
        # Corrige comillas simples si GPT las puso
        bloque = bloque.replace("'", '"')
        # Borra doble coma accidental
        bloque = bloque.replace(",,", ",")
        return bloque
    else:
        return texto

api_key = st.text_input("Introduce tu clave OpenAI API", type="password")
uploaded_file = st.file_uploader("Sube tu contrato en PDF", type=["pdf"])

if uploaded_file and api_key:
    openai.api_key = api_key

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    st.info("Procesando archivo...")

    doc = fitz.open(tmp_path)
    is_digital = True
    digital_texts = []
    for page in doc:
        page_text = page.get_text("text")
        digital_texts.append(page_text)
        if len(page_text.strip()) < 30:
            is_digital = False

    all_texts = []
    progress_bar = st.progress(0)
    if is_digital:
        for i, page_text in enumerate(digital_texts):
            all_texts.append(page_text)
            progress_bar.progress((i+1)/len(doc))
    else:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            messages = [
                {"role": "system", "content": "Eres un experto en contratos públicos y OCR legal."},
                {"role": "user", "content": [
                    {"type": "text", "text": (
                        "Lee la imagen adjunta de un contrato, extrae todo el texto útil para estructurar una ficha institucional."
                    )},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                ]}
            ]
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=2048,
            )
            page_text = response.choices[0].message.content
            all_texts.append(page_text)
            progress_bar.progress((i+1)/len(doc))

    st.success("¡Extracción completada!")

    with st.expander("Ver texto extraído de cada página"):
        for idx, txt in enumerate(all_texts):
            st.markdown(f"**Página {idx+1}:**\n\n{txt}\n---")

    st.info("Generando ficha resumen con IA...")

    # FICHA RESUMEN JSON (prompt mejorado)
    full_text = "\n\n".join(all_texts)
    prompt_ficha = (
        "A continuación tienes el texto relevante extraído de todas las páginas de un contrato de la administración pública mexicana. "
        "Estructura una FICHA RESUMEN del contrato en formato JSON, usando estos campos (rellena todos los posibles, si no está alguno, usa 'No localizado'): "
        "{"
        '"partes": [lista de todas las partes], '
        '"objeto": "", '
        '"monto_sin_iva": "", '
        '"iva": "", '
        '"monto_total": "", '
        '"plazo_inicio": "", '
        '"plazo_fin": "", '
        '"plazo_descripcion": "", '
        '"garantias": "", '
        '"obligaciones_proveedor": "", '
        '"supervision": "", '
        '"penalizaciones": "", '
        '"modificaciones": "", '
        '"normatividad_aplicable": "", '
        '"resolucion_controversias": "", '
        '"firmas": [lista de firmantes], '
        '"anexos": "" '
        "}. "
        "Devuelve el JSON en una sola línea (sin saltos de línea dentro de los valores o listas) y asegúrate de que sea válido para Python/JSON. "
        "NO generes texto adicional fuera del JSON. Aquí está el texto:\n\n"
        + full_text
    )
    response_ficha = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos públicos y sistematización de información legal."},
            {"role": "user", "content": prompt_ficha}
        ],
        max_tokens=2048,
    )
    ficha_json = response_ficha.choices[0].message.content
    ficha_json_limpio = limpiar_json_gpt(ficha_json)
    try:
        ficha = json.loads(ficha_json_limpio)
    except Exception as e:
        st.error("No se pudo procesar el JSON de la ficha. Copia manualmente (puedes corregir los saltos de línea o comillas):")
        st.code(ficha_json_limpio, language="json")
        ficha = None

    if ficha:
        st.markdown("## 🗂️ Ficha institucional del contrato:")

        def fmt(val):
            if isinstance(val, list):
                return "\n".join(f"- {v}" for v in val if v.strip())
            return val if val.strip() else "No localizado"

        cols = {
            "partes": "Partes",
            "objeto": "Objeto del Contrato",
            "monto_sin_iva": "Monto sin IVA",
            "iva": "IVA",
            "monto_total": "Monto Total",
            "plazo_inicio": "Fecha de Inicio",
            "plazo_fin": "Fecha de Término",
            "plazo_descripcion": "Descripción de Plazo",
            "garantias": "Garantías",
            "obligaciones_proveedor": "Obligaciones del Proveedor",
            "supervision": "Supervisión",
            "penalizaciones": "Penalizaciones",
            "modificaciones": "Modificaciones",
            "normatividad_aplicable": "Normatividad Aplicable",
            "resolucion_controversias": "Resolución de Controversias",
            "firmas": "Firmas",
            "anexos": "Anexos"
        }

        df = pd.DataFrame([
            [cols.get(k, k), fmt(ficha.get(k, "No localizado"))]
            for k in cols
        ], columns=["Elemento", "Valor"])
        st.table(df)

        st.download_button(
            "Descargar ficha resumen (Excel)",
            data=df.to_csv(index=False, encoding="utf-8-sig"),
            file_name="ficha_contrato_publico.csv",
            mime="text/csv"
        )
    else:
        st.text_area("Ficha extraída (copia manualmente si lo requieres)", ficha_json_limpio, height=400)
else:
    st.info("Sube un PDF y tu clave de OpenAI para comenzar.")
