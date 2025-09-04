import streamlit as st
import openai
import base64
import tempfile
import fitz  # PyMuPDF

st.set_page_config(page_title="IA Contratos Públicos OCR", page_icon="📄")
st.title("📄 Análisis Inteligente de Contratos de la Administración Pública")

st.markdown("""
Carga tu contrato público (PDF, escaneado o digital).  
La IA extrae y consolida los **elementos legales más importantes** del contrato, en formato estandarizado y comparativo para todos los casos.

**Necesitas tu clave de API de [OpenAI](https://platform.openai.com/api-keys)**
""")

st.warning(
    "⚠️ Esta app funciona con contratos PDF digitales (texto seleccionable) o escaneados (imagen). "
    "Si el PDF es digital, el análisis será mucho más rápido y barato. "
    "La extracción de cifras y porcentajes es textual, sin modificar el formato, para máxima precisión."
)

api_key = st.text_input("Introduce tu clave OpenAI API", type="password")
uploaded_file = st.file_uploader("Sube tu contrato en PDF", type=["pdf"])

if uploaded_file and api_key:
    openai.api_key = api_key

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    st.info("Detectando tipo de PDF...")

    doc = fitz.open(tmp_path)
    is_digital = True
    digital_texts = []
    for page in doc:
        page_text = page.get_text("text")
        digital_texts.append(page_text)
        if len(page_text.strip()) < 30:
            is_digital = False

    st.success(f"Tipo de PDF detectado: {'Digital (texto seleccionable)' if is_digital else 'Escaneado (imagen)'}")

    all_texts = []
    progress_bar = st.progress(0)

    if is_digital:
        st.info("Extrayendo texto directamente (rápido y barato)...")
        for i, page_text in enumerate(digital_texts):
            st.write(f"Procesando página {i + 1} de {len(doc)} (digital)...")
            all_texts.append(page_text)
            progress_bar.progress((i+1)/len(doc))
    else:
        st.info("Convirtiendo páginas a imagen y usando IA Vision para OCR...")
        for i, page in enumerate(doc):
            st.write(f"Procesando página {i + 1} de {len(doc)} (imagen)...")
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            messages = [
                {"role": "system", "content": "Eres un experto en contratos públicos y OCR legal."},
                {"role": "user", "content": [
                    {"type": "text", "text": (
                        "Lee la imagen adjunta de un contrato, extrae todo el texto útil y, si detectas información de partes, objeto, monto, plazo, garantías, "
                        "obligaciones, penalizaciones, modificaciones, normatividad aplicable, resolución de controversias, firmas o anexos, indícalo claramente. "
                        "No agregues explicaciones, solo texto estructurado."
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

    st.info("Consolidando elementos legales con IA...")

    # Junta todos los textos y consolida
    full_text = "\n\n".join(all_texts)

    prompt_final = (
        "Eres un analista legal automatizado experto en contratos públicos. "
        "A continuación tienes el texto relevante extraído de todas las páginas de un contrato de la administración pública mexicana. "
        "Debes estructurar y presentar SIEMPRE la siguiente lista de elementos legales, usando EXCLUSIVAMENTE los títulos y el ORDEN proporcionado abajo, con el siguiente formato: "
        "Numera los campos del 1 al 13, cada título va en NEGRITAS (por ejemplo **Partes:**), seguido exactamente por el dato correspondiente. "
        "Si algún elemento no existe en el contrato o no aparece explícitamente, escribe SOLO la leyenda 'NO LOCALIZADO' en ese campo (sin sinónimos, sin frases tipo 'no se encontró', 'no aplica', 'no especificado', etc). "
        "NO fusiones campos, NO repitas campos, NO agregues ejemplos, NO cambies el nombre ni el orden de los títulos, NO hagas explicaciones, NO incluyas resumen final ni comentarios. "
        "No mezcles información de diferentes campos; si hay varios datos, sepáralos por punto y seguido. "
        "No pongas cargos en Firmas, solo los nombres. No incluyas definiciones. "
        "Escribe los montos y cifras exactamente como aparezcan, no los transformes ni los resumas. "
        "Aquí el formato OBLIGATORIO, así debe salir SIEMPRE, con los mismos títulos y formato:\n\n"
        "1. **Partes:** [dato]\n"
        "2. **Objeto:** [dato]\n"
        "3. **Monto:** [dato]\n"
        "4. **Plazo:** [dato]\n"
        "5. **Garantías:** [dato]\n"
        "6. **Obligaciones del Proveedor:** [dato]\n"
        "7. **Supervisión:** [dato]\n"
        "8. **Penalizaciones:** [dato]\n"
        "9. **Modificaciones:** [dato]\n"
        "10. **Normatividad Aplicable:** [dato]\n"
        "11. **Resolución de Controversias:** [dato]\n"
        "12. **Firmas:** [dato]\n"
        "13. **Anexos:** [dato]\n\n"
        "Ejemplo de respuesta:\n"
        "1. **Partes:** La Secretaría de Finanzas y Administración del Estado de Durango y la empresa Maquinaria y Edificaciones Doble G, S.A. de C.V. representada por C. Felipe de Jesús García Avendaño y C. Jonathan Moncada Galaviz.\n"
        "2. **Objeto:** Servicio de fumigaciones para diferentes dependencias.\n"
        "3. **Monto:** $48,368,544.21 después de impuestos.\n"
        "4. **Plazo:** Del 14 de junio de 2025 al 31 de diciembre de 2025.\n"
        "5. **Garantías:** Fianza por el 10% del importe total del contrato.\n"
        "6. **Obligaciones del Proveedor:** Cumplir con el servicio en tiempo y forma.\n"
        "7. **Supervisión:** Dirección de Servicios Generales de la Subsecretaría de Administración.\n"
        "8. **Penalizaciones:** Hasta 300 UMA's más IVA por día de atraso.\n"
        "9. **Modificaciones:** Permitidas mediante acuerdo escrito entre las partes, hasta un 15% del total.\n"
        "10. **Normatividad Aplicable:** Ley de Adquisiciones, Arrendamientos y Servicios del Estado de Durango.\n"
        "11. **Resolución de Controversias:** Tribunales locales del Estado de Durango.\n"
        "12. **Firmas:** Pedro Josué Herrera Parra. Óscar Manuel Vázquez Pacheco. Felipe de Jesús García Avendaño. Jonathan Moncada Galaviz.\n"
        "13. **Anexos:** Anexo 1.\n\n"
        "Responde SOLO con la lista numerada exactamente en ese formato. Aquí está el texto:\n\n"
        + full_text
    )

    response_final = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres un experto en contratos públicos. Devuelve la lista estructurada y consolidada, sin duplicados, sin campos extra y siguiendo EXACTAMENTE los campos y el orden indicados."},
            {"role": "user", "content": prompt_final}
        ],
        max_tokens=4096,
    )
    resultado = response_final.choices[0].message.content

    st.success("¡Análisis general completado!")
    st.markdown("### Lista consolidada de elementos legales (análisis general):")
    st.markdown(resultado)

    st.download_button(
        "Descargar análisis general (Markdown)",
        data=resultado,
        file_name="elementos_legales_contrato.md",
        mime="text/markdown"
    )
else:
    st.info("Sube un PDF y tu clave de OpenAI para comenzar.")
