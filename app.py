import streamlit as st
import openai
import base64
import tempfile
import fitz  # PyMuPDF

st.set_page_config(page_title="IA Contratos Públicos OCR", page_icon="📄")
st.title("📄 Análisis Inteligente de Contratos de la Administración Pública")

st.markdown("""
Carga tu contrato público (PDF, escaneado o digital).  
La IA extrae y consolida los **elementos legales más importantes** del contrato, y realiza una segunda revisión enfocada en los datos críticos para mayor precisión.

**Necesitas tu clave de API de [OpenAI](https://platform.openai.com/api-keys)**
""")

st.warning("⚠️ Esta app funciona con contratos PDF digitales o escaneados (imagen). El análisis detallado puede tardar y consumir créditos de tu API Key.")

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
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
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

    # Mostrar texto extraído de cada página (opcional)
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

    # --- PASADA ENFOCADA: elementos críticos ---
    st.markdown("## 🔎 Revisión IA enfocada en elementos críticos:")

    # Montos
    prompt_montos = (
        "Del siguiente texto de contrato, extrae TODOS los montos, cantidades monetarias y formas de pago, tal como aparecen (no infieras, solo copia textualmente). Incluye conceptos como anticipo, pagos, total de contrato, retenciones, penalizaciones, garantías y cualquier cifra monetaria relevante. Lista cada monto y su contexto."
        "\n\nTexto:\n" + full_text
    )
    response_montos = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de montos, cantidades y su contexto."},
            {"role": "user", "content": prompt_montos}
        ],
        max_tokens=1024,
    )
    st.markdown("### 💰 Montos y cantidades:")
    st.markdown(response_montos.choices[0].message.content)

    # Porcentajes
    prompt_porcentajes = (
        "Del siguiente texto de contrato, extrae todos los porcentajes que aparezcan, incluyendo los símbolos %, fracciones o proporciones relacionadas con anticipos, penalizaciones, garantías, retenciones y pagos. Copia los valores exactamente como aparecen en el texto, sin modificar formato ni unidad. Lista cada porcentaje y su contexto."
        "\n\nTexto:\n" + full_text
    )
    response_porcentajes = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de porcentajes encontrados y su contexto."},
            {"role": "user", "content": prompt_porcentajes}
        ],
        max_tokens=1024,
    )
    st.markdown("### 📊 Porcentajes:")
    st.markdown(response_porcentajes.choices[0].message.content)

    # Plazos
    prompt_plazos = (
        "Del siguiente texto de contrato, extrae todas las fechas, plazos, periodos, vigencias y tiempos de ejecución o cumplimiento, tal como aparecen (fecha de inicio, fin, duración, periodos de entrega, etc.). Lista cada plazo con su contexto."
        "\n\nTexto:\n" + full_text
    )
    response_plazos = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de plazos, fechas y periodos encontrados, con su contexto."},
            {"role": "user", "content": prompt_plazos}
        ],
        max_tokens=1024,
    )
    st.markdown("### ⏳ Plazos y fechas:")
    st.markdown(response_plazos.choices[0].message.content)

    # Sanciones / penalizaciones
    prompt_sanciones = (
        "Del siguiente texto de contrato, extrae todas las sanciones, penalizaciones, multas o consecuencias por incumplimiento que mencione el texto, con su contexto y condiciones (por ejemplo: montos, porcentajes, plazos asociados). Copia los textos tal cual aparecen."
        "\n\nTexto:\n" + full_text
    )
    response_sanciones = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de sanciones, penalizaciones y sus condiciones."},
            {"role": "user", "content": prompt_sanciones}
        ],
        max_tokens=1024,
    )
    st.markdown("### ⚠️ Sanciones y penalizaciones:")
    st.markdown(response_sanciones.choices[0].message.content)

    # Garantías
    prompt_garantias = (
        "Del siguiente texto de contrato, extrae todas las garantías, fianzas y pólizas mencionadas (de cumplimiento, de anticipo, de vicios ocultos, de calidad, etc.), especificando el monto o porcentaje y las condiciones. Copia el texto tal como aparece."
        "\n\nTexto:\n" + full_text
    )
    response_garantias = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de garantías y fianzas encontradas, con sus condiciones."},
            {"role": "user", "content": prompt_garantias}
        ],
        max_tokens=1024,
    )
    st.markdown("### 🛡️ Garantías y fianzas:")
    st.markdown(response_garantias.choices[0].message.content)

    # Firmas
    prompt_firmas = (
        "Del siguiente texto de contrato, extrae únicamente los nombres de todas las personas que aparecen como firmantes, representantes legales o testigos. No infieras ni omitas nombres. Copia los nombres tal como aparecen y agrúpalos por parte o función (ejemplo: representante de la entidad, representante del contratista, testigos, etc.)."
        "\n\nTexto:\n" + full_text
    )
    response_firmas = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de nombres de firmantes y su función."},
            {"role": "user", "content": prompt_firmas}
        ],
        max_tokens=1024,
    )
    st.markdown("### ✍️ Firmas y firmantes:")
    st.markdown(response_firmas.choices[0].message.content)

    # Descarga del análisis completo
    resultado_completo = (
        "# Lista general consolidada\n" + resultado +
        "\n\n# Montos\n" + response_montos.choices[0].message.content +
        "\n\n# Porcentajes\n" + response_porcentajes.choices[0].message.content +
        "\n\n# Plazos y fechas\n" + response_plazos.choices[0].message.content +
        "\n\n# Sanciones y penalizaciones\n" + response_sanciones.choices[0].message.content +
        "\n\n# Garantías y fianzas\n" + response_garantias.choices[0].message.content +
        "\n\n# Firmas y firmantes\n" + response_firmas.choices[0].message.content
    )
    st.download_button(
        "Descargar todo el análisis (Markdown)",
        data=resultado_completo,
        file_name="analisis_contrato_publico.md",
        mime="text/markdown"
    )
else:
    st.info("Sube un PDF y tu clave de OpenAI para comenzar.")
