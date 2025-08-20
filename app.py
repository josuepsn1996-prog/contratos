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
        # Usa el texto extraído directamente
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

    # --- SEGUNDA PASADA (Prompts estrictos para máxima precisión) ---

    st.markdown("## 🔎 Revisión IA enfocada en elementos críticos:")

    # Montos
    prompt_montos = (
        "Del siguiente texto de contrato, extrae TODOS los montos, cantidades monetarias y formas de pago, tal como aparecen (no infieras, solo copia textualmente). "
        "Incluye conceptos como anticipo, pagos, total de contrato, retenciones, penalizaciones, garantías y cualquier cifra monetaria relevante. "
        "Escribe exactamente como aparece, incluyendo separadores, comas, decimales, signos de moneda, etc. "
        "NO transformes ni resumas, solo copia lo que ves. "
        "Lista cada monto y su contexto."
        "\n\nTexto:\n" + full_text
    )
    response_montos = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de montos, cantidades y su contexto, copiados textualmente."},
            {"role": "user", "content": prompt_montos}
        ],
        max_tokens=1024,
    )
    st.markdown("### 💰 Montos y cantidades:")
    st.markdown(response_montos.choices[0].message.content)

    # Porcentajes
    prompt_porcentajes = (
        "Del siguiente texto de contrato, extrae todos los porcentajes que aparezcan, incluyendo símbolos %, fracciones o proporciones relacionadas con anticipos, penalizaciones, garantías, retenciones y pagos. "
        "Escribe exactamente lo que aparece en el texto, SIN transformar a decimales ni modificar el formato original. "
        "Si aparece '15%' y después entre paréntesis 'quince por ciento', escribe todo así: '15% (quince por ciento)'. "
        "No realices conversiones, ni infieras, ni resumas. Copia literalmente el formato, los errores y las palabras. Lista cada porcentaje y su contexto."
        "\n\nTexto:\n" + full_text
    )
    response_porcentajes = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de porcentajes encontrados y su contexto, exactamente como aparecen."},
            {"role": "user", "content": prompt_porcentajes}
        ],
        max_tokens=1024,
    )
    st.markdown("### 📊 Porcentajes:")
    st.markdown(response_porcentajes.choices[0].message.content)

    # Plazos
    prompt_plazos = (
        "Del siguiente texto de contrato, extrae todas las fechas, plazos, periodos, vigencias y tiempos de ejecución o cumplimiento, tal como aparecen (fecha de inicio, fin, duración, periodos de entrega, etc.). "
        "Copia exactamente como aparece, sin transformar ni resumir. Lista cada plazo con su contexto."
        "\n\nTexto:\n" + full_text
    )
    response_plazos = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de plazos, fechas y periodos encontrados, copiados textualmente."},
            {"role": "user", "content": prompt_plazos}
        ],
        max_tokens=1024,
    )
    st.markdown("### ⏳ Plazos y fechas:")
    st.markdown(response_plazos.choices[0].message.content)

    # Sanciones / penalizaciones
    prompt_sanciones = (
        "Del siguiente texto de contrato, extrae todas las sanciones, penalizaciones, multas o consecuencias por incumplimiento que mencione el texto, con su contexto y condiciones (por ejemplo: montos, porcentajes, plazos asociados). "
        "Copia los textos tal cual aparecen, sin resumir ni transformar."
        "\n\nTexto:\n" + full_text
    )
    response_sanciones = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de sanciones, penalizaciones y sus condiciones, copiados textualmente."},
            {"role": "user", "content": prompt_sanciones}
        ],
        max_tokens=1024,
    )
    st.markdown("### ⚠️ Sanciones y penalizaciones:")
    st.markdown(response_sanciones.choices[0].message.content)

    # Garantías
    prompt_garantias = (
        "Del siguiente texto de contrato, extrae todas las garantías, fianzas y pólizas mencionadas (de cumplimiento, de anticipo, de vicios ocultos, de calidad, etc.), "
        "especificando el monto o porcentaje y las condiciones. Copia el texto tal como aparece, sin resumir ni modificar."
        "\n\nTexto:\n" + full_text
    )
    response_garantias = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de garantías y fianzas encontradas, copiados textualmente y con sus condiciones."},
            {"role": "user", "content": prompt_garantias}
        ],
        max_tokens=1024,
    )
    st.markdown("### 🛡️ Garantías y fianzas:")
    st.markdown(response_garantias.choices[0].message.content)

    # Firmas
    prompt_firmas = (
        "Del siguiente texto de contrato, extrae únicamente los nombres de todas las personas que aparecen como firmantes, representantes legales o testigos. "
        "No infieras ni omitas nombres. Copia los nombres tal como aparecen y agrúpalos por parte o función (ejemplo: representante de la entidad, representante del contratista, testigos, etc.)."
        "\n\nTexto:\n" + full_text
    )
    response_firmas = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de nombres de firmantes y su función, copiados exactamente como aparecen."},
            {"role": "user", "content": prompt_firmas}
        ],
        max_tokens=1024,
    )
    st.markdown("### ✍️ Firmas y firmantes:")
    st.markdown(response_firmas.choices[0].message.content)

    # Modificaciones
    prompt_modificaciones = (
        "Del siguiente texto de contrato, extrae todas las referencias a modificaciones, ampliaciones, reducciones, ajustes de monto, cambio de plazos, "
        "procedimientos para modificar el contrato, requisitos para modificaciones y condiciones bajo las cuales es posible modificar cualquier parte del contrato. "
        "Copia el texto tal como aparece y da el mayor contexto posible. No transformes ni resumas, solo copia lo que ves."
        "\n\nTexto:\n" + full_text
    )
    response_modificaciones = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres experto en contratos. Devuelve solo la lista de modificaciones y sus condiciones, copiados textualmente."},
            {"role": "user", "content": prompt_modificaciones}
        ],
        max_tokens=1024,
    )
    st.markdown("### ✏️ Modificaciones al contrato:")
    st.markdown(response_modificaciones.choices[0].message.content)

    # Descarga del análisis completo
    resultado_completo = (
        "# Lista general consolidada\n" + resultado +
        "\n\n# Montos\n" + response_montos.choices[0].message.content +
        "\n\n# Porcentajes\n" + response_porcentajes.choices[0].message.content +
        "\n\n# Plazos y fechas\n" + response_plazos.choices[0].message.content +
        "\n\n# Sanciones y penalizaciones\n" + response_sanciones.choices[0].message.content +
        "\n\n# Garantías y fianzas\n" + response_garantias.choices[0].message.content +
        "\n\n# Firmas y firmantes\n" + response_firmas.choices[0].message.content +
        "\n\n# Modificaciones al contrato\n" + response_modificaciones.choices[0].message.content
    )
    st.download_button(
        "Descargar todo el análisis (Markdown)",
        data=resultado_completo,
        file_name="analisis_contrato_publico.md",
        mime="text/markdown"
    )
else:
    st.info("Sube un PDF y tu clave de OpenAI para comenzar.")
