import os
import base64
import uuid
import io
import requests
from flask import Flask, render_template, request, jsonify, send_file
from supabase import create_client, Client

# Importações do ReportLab para PDF Nativo
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.units import inch

app = Flask(__name__)

# Configuração do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Erro ao inicializar o cliente Supabase: {e}")

# Mapeamento mantido para formatação de relatórios/e-mails
ITENS_LABELS = {
    "item_organizada": "1. A unidade está organizada?",
    "item_limpa": "2. A unidade está limpa?",
    "item_efetivo": "3. A unidade está com o efetivo previsto?",
    "item_residuo_mesa": "4. Há resíduo de mesa simples?",
    "item_objetos_sem_inducao": "5. Existem objetos sem indução?",
    "item_sro_saida": "6. O lado previsto para saída no SROWEB saiu para entrega?",
    "item_gestor_qualidade": "7. O gestor acompanha os resultados de qualidade?",
    "item_registros_normativos": "8. Os registros nos sistemas estão conforme os normativos?",
    "item_sd_pratica": "9. O SD está implantado na prática conforme o previsto?",
    "item_acompanhamento_processos": "10. Os gestores acompanham os processos internos?"
}

def obter_nome_localizacao(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
        headers = {'User-Agent': 'RelatorioVisitaApp/1.0'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            dados = response.json().get('address', {})
            cidade = dados.get('city') or dados.get('town') or dados.get('municipality') or 'Cidade N/D'
            bairro = dados.get('suburb') or dados.get('neighbourhood') or ''
            uf = dados.get('state_code') or ''
            
            local = f"{bairro}, {cidade}" if bairro else cidade
            return f"{local} - {uf}" if uf else local
    except Exception as e:
        print(f"Erro na conversão de GPS: {e}")
    return "Localização não identificada"


def gerar_pdf_bytes(dados_relatorio):
    """Gera o arquivo PDF em memória RAM utilizando ReportLab."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, textColor=colors.HexColor('#0F172A'), spaceAfter=4)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#64748B'), spaceAfter=15)
    section_style = ParagraphStyle('SectionStyle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#0284C7'), spaceBefore=12, spaceAfter=6)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#1E293B'))
    
    elements = []

    # Cabeçalho
    elements.append(Paragraph("Relatório de Inspeção Técnica", title_style))
    elements.append(Paragraph("Sistema Qualidade & Operações", subtitle_style))

    # Tabela de Identificação
    data_id = [
        [
            Paragraph("<b>Coordenador:</b>", normal_style), Paragraph(dados_relatorio.get('coordenador', ''), normal_style),
            Paragraph("<b>Data/Hora:</b>", normal_style), Paragraph(dados_relatorio.get('data_hora', ''), normal_style)
        ],
        [
            Paragraph("<b>Unidade:</b>", normal_style), Paragraph(dados_relatorio.get('unidade_id', ''), normal_style),
            Paragraph("<b>Localização:</b>", normal_style), Paragraph(dados_relatorio.get('localizacao', ''), normal_style)
        ],
        [
            Paragraph("<b>Clima Percebido:</b>", normal_style), Paragraph(dados_relatorio.get('clima', ''), normal_style),
            Paragraph("", normal_style), Paragraph("", normal_style)
        ]
    ]
    
    t_id = Table(data_id, colWidths=[1.1*inch, 2.5*inch, 1.1*inch, 2.5*inch])
    t_id.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t_id)

    # Checklist
    elements.append(Paragraph("Checklist de Conformidade", section_style))
    
    respostas = dados_relatorio.get('respostas', {})
    data_chk = []
    
    for key, label in ITENS_LABELS.items():
        resp = respostas.get(key, 'N/A')
        cor_resp = '#059669' if resp == 'Sim' else '#DC2626'
        
        p_label = Paragraph(f"<b>{label}</b>", normal_style)
        p_val = Paragraph(f"<font color='{cor_resp}'><b>{resp}</b></font>", ParagraphStyle('Val', parent=normal_style, alignment=1))
        data_chk.append([p_label, p_val])

    t_chk = Table(data_chk, colWidths=[6.2*inch, 1.0*inch])
    t_chk.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    elements.append(t_chk)

    # Foto da Evidência
    foto_bytes = dados_relatorio.get('foto_bytes')
    if foto_bytes:
        elements.append(Paragraph("Evidência Fotográfica", section_style))
        try:
            img_stream = io.BytesIO(foto_bytes)
            img = RLImage(img_stream, width=4.5*inch, height=3.0*inch)
            elements.append(Spacer(1, 5))
            elements.append(img)
        except Exception as e:
            print(f"Erro ao incluir foto no PDF: {e}")

    doc.build(elements)
    buffer.seek(0)
    return buffer


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/salvar", methods=["POST"])
def salvar():
    try:
        dados = request.get_json() or {}

        coordenador = dados.get("coordenador", "").strip()
        unidade_id = str(dados.get("unidade_id", "")).strip()
        clima = dados.get("clima")
        latitude = dados.get("latitude")
        longitude = dados.get("longitude")
        precisao = dados.get("precisao")
        foto_base64 = dados.get("foto_base64")

        if not coordenador or not unidade_id or not latitude or not longitude:
            return jsonify({
                "status": "erro",
                "mensagem": "Preencha todos os campos obrigatórios e garanta que o GPS esteja ativo."
            }), 400

        # Converte GPS para nome de localização
        localizacao_texto = obter_nome_localizacao(latitude, longitude)
        respostas_brutas = dados.get("respostas", {})

        foto_url = None
        conteudo_imagem = None

        # Processamento da Foto
        if foto_base64 and "," in foto_base64:
            try:
                header, encoded = foto_base64.split(",", 1)
                conteudo_imagem = base64.b64decode(encoded)

                if supabase:
                    unidade_slug = "".join(c for c in unidade_id if c.isalnum())
                    nome_arquivo = f"visita_{unidade_slug}_{uuid.uuid4().hex[:8]}.jpg"
                    caminho_storage = f"fotos_unidades/{nome_arquivo}"

                    supabase.storage.from_("evidencias-visitas").upload(
                        path=caminho_storage,
                        file=conteudo_imagem,
                        file_options={"content-type": "image/jpeg"}
                    )
                    foto_url = supabase.storage.from_("evidencias-visitas").get_public_url(caminho_storage)
            except Exception as e:
                print(f"Erro ao processar foto: {str(e)}")

        # Salva no Banco Supabase
        payload_banco = {
            "coordenador_nome": coordenador,
            "unidade_id": unidade_id,
            "clima_organizacional": clima,
            "latitude_capturada": float(latitude),
            "longitude_capturada": float(longitude),
            "precisao_gps_metros": float(precisao) if precisao else 0.0,
            "foto_url": foto_url or "",
            "unidade_organizada": respostas_brutas.get("item_organizada") == "Sim",
            "unidade_limpa": respostas_brutas.get("item_limpa") == "Sim",
            "efetivo_previsto": respostas_brutas.get("item_efetivo") == "Sim",
            "residuo_mesa_simples": respostas_brutas.get("item_residuo_mesa") == "Sim",
            "objetos_sem_inducao": respostas_brutas.get("item_objetos_sem_inducao") == "Sim",
            "lado_saida_sroweb": respostas_brutas.get("item_sro_saida") == "Sim",
            "gestor_acompanha_qualidade": respostas_brutas.get("item_gestor_qualidade") == "Sim",
            "registros_normativos": respostas_brutas.get("item_registros_normativos") == "Sim",
            "sd_implantado_pratica": respostas_brutas.get("item_sd_pratica") == "Sim",
            "gestores_acompanham_processos": respostas_brutas.get("item_acompanhamento_processos") == "Sim"
        }

        if supabase:
            supabase.table("relatorios_visita").insert(payload_banco).execute()

        # Dados estruturados para o PDF
        from datetime import datetime
        dados_pdf = {
            "coordenador": coordenador,
            "unidade_id": unidade_id,
            "clima": clima,
            "localizacao": localizacao_texto,
            "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "respostas": respostas_brutas,
            "foto_bytes": conteudo_imagem
        }

        # Gera o PDF em memória RAM e envia como Download nativo
        pdf_io = gerar_pdf_bytes(dados_pdf)
        unidade_slug = "".join(c for c in unidade_id if c.isalnum())

        return send_file(
            pdf_io,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"Relatorio_{unidade_slug}.pdf"
        )

    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"Erro interno no servidor: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
