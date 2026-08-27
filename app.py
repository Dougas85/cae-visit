import os
import base64
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from supabase import create_client, Client

app = Flask(__name__)

# Configuração Segura: Lê as chaves do ambiente (Vercel ou .env)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Inicializa o cliente Supabase se as variáveis estiverem configuradas
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print9f"Erro ao inializar o cloiente Supabase: {e}")
    else:
        print("Aviso: SUPABASE_URL ou SUPABASE_KEY não foram encontradas nas variáveis de ambiente.")

# Mapeamento dos nomes dos campos para os rótulos de exibição
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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/salvar", methods=["POST"])
def salvar():
    try:
        dados = request.get_json() or {}

        coordenador = dados.get("coordenador", "").strip()
        unidade_id = dados.get("unidade_id")
        clima = dados.get("clima")
        latitude = dados.get("latitude")
        longitude = dados.get("longitude")
        precisao = dados.get("precisao")
        foto_base64 = dados.get("foto_base64")  # Imagem capturada em Data URL

        # Validações básicas
        if not coordenador or not unidade_id or not latitude or not longitude:
            return jsonify({
                "status": "erro",
                "mensagem": "Preencha todos os campos obrigatórios e garanta que o GPS esteja ativo."
            }), 400

        respostas_brutas = dados.get("respostas", {})
        foto_url = None

        # 1. Processamento e Upload da Foto para o Supabase Storage (se enviado)
        if supabase and foto_base64 and "," in foto_base64:
            try:
                header, encoded = foto_base64.split(",", 1)
                conteudo_imagem = base64.b64decode(encoded)

                nome_arquivo = f"visita_u{unidade_id}_{uuid.uuid4().hex[:8]}.jpg"
                caminho_storage = f"fotos_unidades/{nome_arquivo}"

                # Upload para o Bucket 'evidencias-visitas'
                supabase.storage.from_("evidencias-visitas").upload(
                    path=caminho_storage,
                    file=conteudo_imagem,
                    file_options={"content-type": "image/jpeg"}
                )

                # Obter URL Pública
                foto_url = supabase.storage.from_("evidencias-visitas").get_public_url(caminho_storage)
            except Exception as e:
                print(f"Erro ao salvar foto no Storage: {str(e)}")

        # 2. Montagem do Payload para a Tabela 'relatorios_visita'
        payload_banco = {
            "coordenador_nome": coordenador,
            "unidade_id": int(unidade_id),
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

        # 3. Gravação no PostgreSQL via Supabase API
        if supabase:
            resposta_db = supabase.table("relatorios_visita").insert(payload_banco).execute()
            relatorio_id = resposta_db.data[0]["id"] if resposta_db.data else None
        else:
            relatorio_id = "Modo Local (Sem Supabase Conectado)"

        return jsonify({
            "status": "sucesso",
            "mensagem": "Relatório de visita registrado com sucesso!",
            "relatorio_id": relatorio_id,
            "foto_url": foto_url
        }), 200

    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"Erro interno no servidor: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
