import streamlit as st
import openai
import base64
import tempfile
import fitz  # PyMuPDF

st.set_page_config(page_title="IA Contratos Públicos OCR", page_icon="📄")
st.title("📄 Análisis Inteligente de Contratos de la Administración Pública")

st.markdown("""
Carga tu contrato público (PDF, escaneado o digital).  
La IA extrae y consolida los **elementos legales más importantes** del contrato, con un flujo **más rápido para PDFs digitales**.

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
        # Si una página tiene muy poco texto, es probable que sea imagen escaneada
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
        "A continuación tienes el texto relevante extraído de todas las páginas de un contrato de la administración pública mexicana. "
        "Unifica y estructura en una sola lista los ELEMENTOS MÁS IMPORTANTES del contrato (partes, objeto, monto, plazo, garantías, obligaciones, supervisión, penalizaciones, modificaciones, normatividad aplicable, resolución de controversias, firmas y anexos). "
        "Si algún elemento aparece disperso o repetido, fusiónalo en uno solo, lo más completo posible. Si falta, indícalo como 'NO LOCALIZADO'. "
        "Responde SOLO con la lista estructurada en markdown, para fácil lectura o copia. Aquí está el texto:\n\n"
        + full_text
    )
    response_final = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres un experto en contratos públicos. Devuelve la lista estructurada y consolidada, sin duplicados."},
            {"role": "user", "content": prompt_final}
        ],
        max_tokens=4096,
    )
    resultado = response_final.choices[0].message.content

    st.success("¡Análisis general completado!")
    st.markdown("### Lista consolidada de elementos legales (análisis general):")
    st.markdown(resultado)

    # Descarga solo del análisis general
    st.download_button(
        "Descargar análisis general (Markdown)",
        data=resultado,
        file_name="elementos_legales_contrato.md",
        mime="text/markdown"
    )
else:
    st.info("Sube un PDF y tu clave de OpenAI para comenzar.")
