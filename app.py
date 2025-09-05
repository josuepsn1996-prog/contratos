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
        "Tu tarea es rellenar la siguiente ficha, con cada campo EXACTAMENTE como se indica. No expliques, no agregues comentarios, no resumas ni fusiones campos. "
        "No cambies el formato ni los títulos. Usa únicamente la información explícita del texto. Si algo no aparece o está incompleto, escribe 'NO LOCALIZADO'. "
        "La ficha debe ser homogénea y cada campo fácil de comparar entre contratos. Usa solo texto plano, sin listas, viñetas ni puntos y seguido innecesarios."
        "\n\n== FICHA ESTANDARIZADA DE CONTRATO DE ADMINISTRACIÓN PÚBLICA ==\n\n"
        "1. **Partes:**\n"
        "Por la Secretaría: Nombre completo(s) y cargo(s) exactos de todos los firmantes de la dependencia pública. "
        "Por el Proveedor: Nombre completo(s), cargo(s) y denominación de la empresa o persona física de todos los firmantes del proveedor. "
        "No agregues redacción extra ni resumas, sólo nombres y cargos separados por punto y coma."
        "\n\n2. **Objeto:**\n"
        "Describe de forma literal todos los servicios, bienes u obras específicos que se enlistan como objeto del contrato, uno por renglón. "
        "No resumas, no combines, no interpretes, sólo transcribe textualmente todo lo que se considere objeto."
        "\n\n3. **Monto:**\n"
        "Monto antes de IVA: $[número con separador de miles, 2 decimales] MXN. "
        "IVA: $[número con separador de miles, 2 decimales] MXN. "
        "Monto total: $[número con separador de miles, 2 decimales] MXN. "
        "Si alguno de estos datos no aparece, pon 'NO LOCALIZADO'."
        "\n\n4. **Plazo:**\n"
        "Inicio: [fecha literal]. Fin: [fecha literal]. Vigencia: [periodo o plazo]. "
        "No combines fechas en un solo renglón, pon cada una donde corresponde. Si falta algún dato, pon 'NO LOCALIZADO'."
        "\n\n5. **Garantías:**\n"
        "Tipo: [tipo de garantía, por ejemplo, Cumplimiento o Anticipo]. Porcentaje: [% literal]. Condiciones: [condiciones textuales]. "
        "Si hay varias garantías, cada una en renglón aparte. Si falta algo, pon 'NO LOCALIZADO'."
        "\n\n6. **Obligaciones del Proveedor:**\n"
        "Cada obligación literal, una por renglón, sin resumir ni combinar. No agregues frases generales, sólo lo que aparece explícito en el contrato."
        "\n\n7. **Supervisión:**\n"
        "Nombre o cargo de la(s) persona(s), área(s) o dependencia(s) responsables. Un responsable por renglón. No resumas."
        "\n\n8. **Penalizaciones:**\n"
        "Cada penalización, monto y condición literal en renglón aparte. Al final, pon 'Penalización máxima: [dato textual]'. Si no está, pon 'NO LOCALIZADO'."
        "\n\n9. **Modificaciones:**\n"
        "Procedimiento, límite máximo permitido (% o monto), plazos y fundamento legal, cada elemento en renglón aparte. Si falta algún dato, pon 'NO LOCALIZADO'."
        "\n\n10. **Normatividad Aplicable:**\n"
        "Todas las leyes, reglamentos, códigos y normas oficiales mencionadas, cada una en renglón aparte, con nombre completo tal cual. No resumas ni combines."
        "\n\n11. **Resolución de Controversias:**\n"
        "Procedimiento específico para resolver controversias, literal. Si NO existe, inicia con 'NO LOCALIZADO.' y luego agrega cualquier mención a tribunal o jurisdicción, tal cual aparezca."
        "\n\n12. **Firmas:**\n"
        "Por la Secretaría: Nombre completo(s) y cargo(s) de todos los firmantes. Por el Proveedor: Nombre completo(s), cargo(s) y denominación de la empresa/persona física. Igual que el campo Partes. Sin redacción extra."
        "\n\n13. **Anexos:**\n"
        "Para cada anexo, pon el número, nombre literal y breve descripción. Si sólo aparece el nombre, pon 'sin descripción'."
        "\n\n14. **No localizado:**\n"
        "Como experto en contratos públicos, menciona brevemente cualquier dato importante, campo o requisito legal del contrato que NO aparezca en la ficha anterior (por ejemplo: falta de garantías, falta de desglose de montos, ausencia de procedimiento de modificación, omisión de firmas obligatorias, etc). Un posible vacío legal por línea. Si todo está, escribe 'Ninguno.'"
        "\n\n15. **Áreas de mejora:**\n"
        "Como experto en contratos públicos, señala cualquier parte, redacción o campo que, aunque exista, sea ambiguo, subjetivo, genérico, poco claro, interpretable o pueda dar pie a controversias en la ejecución del contrato. Cada área de mejora por renglón. Si no hay, escribe 'Ninguna.'"
        "\n\nRecuerda: NO EXPLIQUES ni comentes fuera de los campos anteriores, sólo llena la ficha en ese formato. El resultado debe ser siempre igual en orden, formato y nivel de detalle."
        "\n\nAquí está el texto del contrato:\n\n"
        + full_text
    )

    response_final = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres un experto en contratos públicos. Devuelve la ficha estructurada, sin campos extra y siguiendo EXACTAMENTE los campos, formato y nivel de detalle indicados."},
            {"role": "user", "content": prompt_final}
        ],
        max_tokens=4096,
    )
    resultado = response_final.choices[0].message.content

    st.success("¡Análisis general completado!")
    st.markdown("### Ficha estandarizada de contrato de administración pública:")
    st.markdown(resultado)

    st.download_button(
        "Descargar ficha (Markdown)",
        data=resultado,
        file_name="ficha_contrato_publico.md",
        mime="text/markdown"
    )
else:
    st.info("Sube un PDF y tu clave de OpenAI para comenzar.")
