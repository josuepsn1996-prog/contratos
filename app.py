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

    full_text = "\n\n".join(all_texts)

    prompt_final = (
        "Eres un analista legal experto en contratos públicos. "
        "Tienes el texto extraído de un contrato de la administración pública mexicana. "
        "Debes presentar SIEMPRE la siguiente lista numerada, usando EXCLUSIVAMENTE los títulos y el ORDEN proporcionado, en formato claro, formal, homogéneo y fácil de comparar, así:\n\n"
        "1. **Partes:** Enumera cada parte con nombre oficial, nombre completo y cargo de cada firmante. Agrupa por parte (por ejemplo: 'Por la Secretaría: ...; Por la empresa: ...').\n"
        "2. **Objeto:** Describe todos los servicios, bienes u obras exactos del contrato, uno por renglón, sin resumir.\n"
        "3. **Monto:** Presenta así, SIEMPRE, cada línea aparte, con separador de miles y MXN:\n"
        "   - Monto antes de IVA: $##,###,###.## MXN\n"
        "   - IVA: $##,###,###.## MXN\n"
        "   - Monto total: $##,###,###.## MXN\n"
        "   Si alguno falta, pon 'NO LOCALIZADO' en esa línea. No uses otros formatos ni redacciones. No incluyas decimales innecesarios.\n"
        "4. **Plazo:** Expresa en formato: 'Inicio: [fecha]. Fin: [fecha]. Vigencia: [periodo].'\n"
        "5. **Garantías:** Lista tipo, porcentaje y condiciones de cada garantía; una por renglón, usando el formato: 'Tipo: [tipo]. Porcentaje: [% o monto]. Condiciones: [condiciones].'\n"
        "6. **Obligaciones del Proveedor:** Lista TODAS las obligaciones específicas, una por renglón, literal del contrato. No uses frases generales. No resumas ni combines en un solo párrafo.\n"
        "7. **Supervisión:** Indica la(s) persona(s), área(s) o dependencia(s) responsables. Un dato por renglón.\n"
        "8. **Penalizaciones:** Lista cada penalización, con monto/porcentaje y condición, una por renglón. Luego agrega la línea 'Penalización máxima: [dato]'. Si no está, pon 'NO LOCALIZADO'.\n"
        "9. **Modificaciones:** Indica el procedimiento, máximo permitido (% o monto), plazos y fundamento legal literal.\n"
        "10. **Normatividad Aplicable:** Lista todas las leyes, reglamentos, normas oficiales mexicanas y códigos citados en el contrato, cada uno en una línea, sin abreviar ni resumir.\n"
        "11. **Resolución de Controversias:** Si NO hay procedimiento específico, inicia la línea con 'NO LOCALIZADO.' y después copia cualquier mención a jurisdicción/tribunal.\n"
        "12. **Firmas:** Agrupa firmantes por parte, cada firmante en línea aparte con nombre completo y cargo literal. Ejemplo: 'Por la Secretaría: Nombre, Cargo.'\n"
        "13. **Anexos:** Para cada anexo, pon el número, nombre y descripción literal. Si sólo hay nombre, pon 'sin descripción'.\n"
        "Usa negritas solo en títulos. Presenta todas las listas, montos y campos en líneas separadas, nunca pegados ni mezclados. No escribas explicaciones, resúmenes, comentarios ni fusiones. El formato debe ser siempre igual para todos los contratos.\n\n"
        "Aquí está el texto del contrato:\n\n"
        + full_text
    )

    response_final = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres un experto en contratos públicos. Devuelve la lista estructurada, sin campos extra y siguiendo EXACTAMENTE los campos, formato, y nivel de detalle indicados."},
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
