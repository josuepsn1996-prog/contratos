import streamlit as st
import openai
import base64
import tempfile
import fitz  # PyMuPDF
from PIL import Image
import os

st.set_page_config(page_title="IA Contratos Públicos OCR", page_icon="📄")
st.title("📄 Análisis de Contratos de la Administración Pública con GPT-4o Vision")

st.markdown("""
Sube cualquier contrato de la administración pública (PDF, aunque sea escaneado como imagen).  
La IA extrae texto, identifica y **consolida los elementos legales más importantes** (partes, objeto, monto, plazo, garantías, penalizaciones, etc.).

**Necesitas tu clave de API de [OpenAI](https://platform.openai.com/api-keys)** (solo se usa localmente, nunca se almacena).
""")

st.warning("⚠️ Esta app funciona con contratos PDF, sean digitales o escaneados. El procesamiento de escaneos puede ser más lento y consumir más créditos de tu API Key.")

api_key = st.text_input("Introduce tu clave OpenAI API", type="password")
uploaded_file = st.file_uploader("Sube tu contrato en PDF", type=["pdf"])

if uploaded_file and api_key:
    openai.api_key = api_key

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    st.info("Convirtiendo páginas del PDF a imágenes...")

    doc = fitz.open(tmp_path)
    all_texts = []

    progress_bar = st.progress(0)
    for i, page in enumerate(doc):
        st.write(f"Procesando página {i + 1} de {len(doc)}...")

        # Convierte la página a PNG (¡no requiere dependencias del sistema!)
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")

        img_base64 = base64.b64encode(img_bytes).decode('utf-8')

        # Llama a Vision: extrae TODO el texto relevante
        messages = [
            {"role": "system", "content": "Eres un experto en contratos públicos y OCR legal."},
            {"role": "user", "content": [
                {"type": "text", "text": "Lee la imagen adjunta de un contrato, extrae todo el texto útil y, si detectas información de partes, objeto, monto, plazo, garantías, obligaciones, penalizaciones, modificaciones, normatividad aplicable, resolución de controversias, firmas o anexos, indícalo claramente. No agregues explicaciones, solo texto estructurado."},
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

    st.success("¡OCR completado en todas las páginas!")

    # Muestra (opcionalmente) el texto extraído de cada página:
    with st.expander("Ver texto extraído de cada página"):
        for idx, txt in enumerate(all_texts):
            st.markdown(f"**Página {idx+1}:**\n\n{txt}\n---")

    st.info("Consolidando todos los elementos legales con IA...")

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

    st.success("¡Lista consolidada generada!")
    st.markdown("### Elementos legales consolidados:")
    st.markdown(resultado)

    st.download_button(
        "Descargar resultado (Markdown)",
        data=resultado,
        file_name="elementos_legales_contrato.md",
        mime="text/markdown"
    )

else:
    st.info("Sube un PDF y tu clave de OpenAI para comenzar.")
