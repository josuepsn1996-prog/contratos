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

    # PROMPT ULTRA-DETALLADO
    prompt_final = (
        "Eres un analista legal experto en contratos públicos. "
        "A continuación tienes el texto relevante extraído de todas las páginas de un contrato de la administración pública mexicana. "
        "Debes presentar SIEMPRE la siguiente lista numerada, usando EXCLUSIVAMENTE los títulos y el ORDEN proporcionado, y el formato indicado: "
        "Numera del 1 al 13. Cada título va en NEGRITAS (por ejemplo **Partes:**), seguido exactamente por el dato correspondiente. "
        "Si un elemento no existe explícitamente, escribe SOLO la leyenda 'NO LOCALIZADO' (sin sinónimos ni explicaciones). "
        "No fusiones campos, no repitas campos, no agregues ejemplos, no cambies el nombre ni el orden, no incluyas resumen final, no comentes. "
        "En cada campo, sigue estas instrucciones para máxima uniformidad:\n\n"
        "1. **Partes:** Enumera a todas las partes del contrato, indicando nombre completo y el puesto/cargo de cada firmante de cada parte. Ejemplo: 'La Secretaría de Finanzas y Administración del Estado de Durango, representada por el L.E.P. Pedro Josué Herrera Parra, Subsecretario de Administración; y la empresa Maquinaria y Edificaciones Doble G, S.A. de C.V., representada por C. Felipe de Jesús García Avendaño, Administrador Único; y C. Jonathan Moncada Galaviz, Persona Física.'\n"
        "2. **Objeto:** Describe el objeto del contrato de la forma más específica posible, incluyendo si aplica el tipo de servicio, suministro u obra. No resumas.\n"
        "3. **Monto:** Desglosa SIEMPRE (si está disponible) en tres líneas: 'Monto antes de IVA: [dato]', 'IVA: [dato]', 'Monto total: [dato]'. Si solo hay uno, indícalo como 'NO LOCALIZADO' en las otras líneas.\n"
        "4. **Plazo:** Especifica claramente la vigencia, fechas de inicio y fin, y cualquier otra condición temporal. Si hay plazos parciales, desglósalos.\n"
        "5. **Garantías:** Indica tipo, porcentaje, monto y condiciones de todas las garantías requeridas. No resumas.\n"
        "6. **Obligaciones del Proveedor:** Lista todas las obligaciones explícitas del proveedor, sin resumir en frases generales, incluyendo entregas, reportes, equipamiento, personal, requisitos técnicos, etc. Una obligación por punto y seguido.\n"
        "7. **Supervisión:** Señala exactamente qué persona, área o dependencia es responsable de la supervisión. Si hay varias, sepáralas.\n"
        "8. **Penalizaciones:** Señala todas las penalizaciones, incluyendo monto, porcentaje, UMA's, condiciones y PENALIZACIÓN MÁXIMA. Si no está indicada, escribe 'NO LOCALIZADO' para penalización máxima.\n"
        "9. **Modificaciones:** Indica el procedimiento para modificaciones (por ejemplo, máximo permitido, requisitos, plazos, autorización, fundamento legal específico).\n"
        "10. **Normatividad Aplicable:** Lista TODA la normatividad mencionada (leyes, reglamentos, códigos) tal como aparece en el texto. Separa cada norma por punto y seguido. No resumas ni inventes normas no presentes.\n"
        "11. **Resolución de Controversias:** Especifica el procedimiento y autoridad para la resolución de controversias, y si no hay procedimiento específico, escribe 'NO LOCALIZADO' y después lo que sí esté disponible (por ejemplo: sólo menciona tribunal, pero no procedimientos). Ejemplo: 'NO LOCALIZADO. Sólo se indica jurisdicción de Tribunales Locales del Estado de Durango.'\n"
        "12. **Firmas:** Enumera el nombre completo y puesto/cargo de cada firmante, agrupando por parte contratante. Ejemplo: 'Por la Secretaría de Finanzas y Administración: L.E.P. Pedro Josué Herrera Parra, Subsecretario de Administración; Ing. Óscar Manuel Vázquez Pacheco, Director de Servicios Generales. Por la empresa: C. Felipe de Jesús García Avendaño, Administrador Único; C. Jonathan Moncada Galaviz, Persona Física.'\n"
        "13. **Anexos:** Enumera cada anexo por nombre y una breve descripción (por ejemplo: 'Anexo 1: Propuesta técnico-económica aceptada; Anexo 2: Detalle técnico del servicio de fumigación, etc.'). Si sólo aparece el nombre, escríbelo tal cual.\n\n"
        "Recuerda: Sigue exactamente este formato y nivel de detalle. Si algún campo no tiene información suficiente, pon 'NO LOCALIZADO' sólo en esa línea.\n\n"
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
