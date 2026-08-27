import os
import base64
import uuid
import requests
from flask import Flask, render_template, request, jsonify
from supabase import create_client, Client

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
    "item_organizada": "A unidade está organizada?",
    "item_limpa": "A unidade está limpa?",
    "item_efetivo": "A unidade está com o efetivo previsto?",
    "item_residuo_mesa": "Há resíduo de mesa simples?",
    "item_objetos_sem_inducao": "Existem objetos sem indução?",
    "item_sro_saida": "O lado previsto para saída no SROWEB saiu para entrega?",
    "item_gestor_qualidade": "O gestor acompanha os resultados de qualidade?",
    "item_registros_normativos": "Os registros nos sistemas estão conforme os normativos?",
    "item_sd_pratica": "O SD está implantado na prática conforme o previsto?",
    "item_acompanhamento_processos": "Os gestores acompanham os processos internos?"
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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/salvar", methods=["POST"])
def salvar():
    try:
        dados = request.get_json() or {}

        coordenador = dados.get("coordenador", "").strip()
        unidade_id = str(dados.get("unidade_id", "")).strip() # Texto
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

        # Monta um resumo legível com base no ITENS_LABELS
        resumo_itens = []
        for chave, rotulo in ITENS_LABELS.items():
            resposta = respostas_brutas.get(chave, "Não informado")
            resumo_itens.append(f"{rotulo}: {resposta}")

        foto_url = None

        # 1. Upload da Foto no Storage
        if supabase and foto_base64 and "," in foto_base64:
            try:
                header, encoded = foto_base64.split(",", 1)
                conteudo_imagem = base64.b64decode(encoded)

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
                print(f"Erro ao salvar foto no Storage: {str(e)}")

        # 2. Payload da Tabela 'relatorios_visita'
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

        # 3. Inserção no Supabase
        if supabase:
            resposta_db = supabase.table("relatorios_visita").insert(payload_banco).execute()
            relatorio_id = resposta_db.data[0]["id"] if resposta_db.data else None
        else:
            relatorio_id = "Modo Local"

        return jsonify({
            "status": "sucesso",
            "mensagem": "Relatório registrado com sucesso!",
            "relatorio_id": relatorio_id,
            "localizacao_nome": localizacao_texto,
            "resumo_detalhado": resumo_itens,
            "foto_url": foto_url,
            "destinatario": "douglas.francisco@correios.com.br"
        }), 200

    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"Erro interno no servidor: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
