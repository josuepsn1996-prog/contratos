import streamlit as st
import openai
import base64
import pandas as pd
from io import StringIO
import tempfile
import fitz  # PyMuPDF
from PIL import Image
import os
import re

st.set_page_config(page_title="IA para Análisis de Contratos Públicos", page_icon="📄")
st.title("📄 Análisis Inteligente de Contratos de la Administración Pública")

st.markdown("""
Carga tu contrato (PDF) y obtén una **lista estructurada** de los elementos legales más importantes: partes, objeto, monto, plazo, garantías, obligaciones, penalizaciones, anexos y más.

*Necesitas tu clave de API de [OpenAI](https://platform.openai.com/api-keys) (nunca la compartas, solo cópiala aquí temporalmente para usar la app).*
""")

api_key = st.text_input("Introduce tu clave OpenAI API", type="password")
uploaded_file = st.file_uploader("Sube tu contrato en PDF", type=["pdf"])

if uploaded_file and api_key:
    openai.api_key = api_key

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    st.info("Extrayendo texto de tu PDF con PyMuPDF...")

    doc = fitz.open(tmp_path)
    all_texts = []

    for i, page in enumerate(doc):
        st.write(f"Procesando página {i + 1} de {len(doc)}...")
        text = page.get_text("text")
        # Si la página está vacía (escaneada), podrías aquí insertar OCR (opcional, no incluido para mantener simple)
        all_texts.append(text if text.strip() else "")

    st.success("¡Extracción de texto completada!")
    st.markdown("### Analizando elementos legales...")

    # Une todo el texto (o podrías dividir en bloques si son demasiadas páginas/límites de tokens)
    full_text = "\n\n".join(all_texts)

    # Si el contrato es MUY largo, divídelo en bloques (para evitar límite de tokens)
    max_words = 6000
    words = full_text.split()
    blocks = [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)] if len(words) > max_words else [full_text]
    block_results = []

    for idx, block in enumerate(blocks):
        prompt = (
            "A partir del siguiente texto extraído de un contrato de la administración pública mexicana, "
            "identifica y extrae una LISTA ESTRUCTURADA de todos los ELEMENTOS IMPORTANTES del contrato. "
            "Incluye tanto los elementos básicos (partes, objeto, monto, plazo, garantías, obligaciones, supervisión, penalizaciones, modificaciones, normatividad aplicable, resolución de controversias, firmas y anexos) "
            "como los elementos adicionales relevantes según sea de obra pública o proveedor de servicios. "
            "Para cada elemento, indica:\n"
            "- El nombre del elemento (ej: Partes, Objeto, Monto, etc.)\n"
            "- El contenido extraído del contrato, o 'NO LOCALIZADO' si no está presente.\n"
            "Responde solo con la lista estructurada. Aquí está el texto:\n\n"
            + block
        )

        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Eres un experto en análisis de contratos públicos y estructuración de información legal."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4096,
        )
        block_results.append(response.choices[0].message.content)

    # Consolidación (segunda pasada para que solo salga un elemento único por campo)
    st.info("Consolidando información...")
    resultados_juntos = "\n\n".join(block_results)
    prompt_consolidar = (
        "A continuación tienes varias listas de elementos importantes extraídos de diferentes bloques de un mismo contrato de la administración pública. "
        "Unifica los elementos repetidos y crea una sola lista consolidada, en la que cada elemento (ej: Monto, Partes, Objeto, etc.) aparezca solo una vez, "
        "con el contenido más completo que se haya encontrado. Si un elemento tiene información parcial en distintos bloques, fusiónala de forma coherente. "
        "Si algún elemento no está presente en ninguno, indícalo como 'NO LOCALIZADO'.\n\n"
        "=== Listas extraídas de bloques ===\n\n"
        + resultados_juntos
    )

    response_final = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres un experto en contratos públicos. Unifica y consolida los elementos sin repetir."},
            {"role": "user", "content": prompt_consolidar}
        ],
        max_tokens=4096,
    )

    st.success("¡Análisis completado!")
    st.markdown("### Lista consolidada de elementos importantes:")
    st.markdown(response_final.choices[0].message.content)
else:
    st.info("Sube un PDF y tu clave de OpenAI para comenzar.")

