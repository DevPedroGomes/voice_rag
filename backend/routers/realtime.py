"""Conversa por voz contínua — o RAG vira uma tool, não o meio do pipeline.

O resto do app é a arquitetura correta de 2024: grava um áudio, sobe, transcreve,
recupera, gera, sintetiza, devolve um MP3. Funciona, e é um turno de cada vez.

Aqui o desenho é outro:

    áudio contínuo ⟷ gpt-realtime ⟷ tool: buscar_nos_documentos()

O modelo fala e escuta ao mesmo tempo, e quando precisa de um fato dos
documentos ele CHAMA a busca no meio da frase. O ganho não é só latência: a
pessoa interrompe, pede pra repetir, muda de assunto e volta, e a conversa
continua — porque não existe mais "um turno" a ser concluído.

O pipeline de retrieval não muda em nada. Hybrid + rerank + grade continuam
sendo os mesmos de `/query`; muda quem os chama e quando.

Por que o navegador fala direto com a OpenAI (e não passa áudio por aqui):
proxiar mídia em tempo real numa KVM de 2 vCPU seria o gargalo, e o WebRTC já
resolve jitter, perda de pacote e eco. O backend entra só onde precisa mandar —
cunhar a credencial efêmera e executar a busca — e a chave real nunca sai daqui.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException

from config import get_settings
from models.schemas import RealtimeSessionResponse, RealtimeToolRequest, RealtimeToolResponse
from routers.query import _retrieve_and_grade
from services import daily_budget
from services.embedding_service import EmbeddingService, get_embedding_service
from services.session_service import SessionStore, get_session_store
from services.vector_service import VectorService, get_vector_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/realtime", tags=["realtime"])

CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"

FERRAMENTA_BUSCA = {
    "type": "function",
    "name": "buscar_nos_documentos",
    "description": (
        "Search the documents this person uploaded and return the passages that "
        "answer their question. Call this whenever the answer depends on what is "
        "in their files — do not answer from memory. Rephrase what they said into "
        "a clear search question; spoken language is terse and the documents are "
        "not."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pergunta": {
                "type": "string",
                "description": "The question to search for, as a full sentence.",
            }
        },
        "required": ["pergunta"],
        "additionalProperties": False,
    },
}

INSTRUCOES = """\
You are a voice assistant that answers strictly from the documents this person \
uploaded. You are speaking out loud — there is no screen.

Language: answer in the language the person speaks to you. If they switch, switch \
with them, without commenting on it.

Before answering anything about the documents, call buscar_nos_documentos. Never \
answer from memory, and never guess a number, name or date that did not come back \
from the search.

When the search comes back empty, say plainly that it is not in the documents. Do \
not fill the gap.

You are being heard, not read. Two or three sentences. No lists, no markdown, no \
headings, no citation markers — if the source matters, name the file out loud. \
Being interrupted is normal: stop talking and listen.
"""


@router.post("/session", response_model=RealtimeSessionResponse)
async def criar_sessao_realtime(
    session_id: str,
    session_store: SessionStore = Depends(get_session_store),
):
    """Cunha uma credencial efêmera para o navegador abrir o WebRTC.

    A chave real da OpenAI nunca chega ao cliente: o que sai daqui é um
    `ek_...` de vida curta, já amarrado a estas instruções e a esta tool. Um
    visitante não consegue reconfigurar a sessão para outra coisa.
    """
    settings = get_settings()

    if not settings.enable_realtime:
        raise HTTPException(status_code=503, detail="Realtime voice is disabled")
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="Realtime voice is not configured")

    sessao = await session_store.get(session_id)
    if sessao is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    if not sessao.is_ready:
        raise HTTPException(status_code=400, detail="No documents uploaded yet")

    # Teto diário consumido ANTES de cunhar. Uma conversa realtime é aberta:
    # sem isto, um visitante segura a linha e gasta o dia inteiro sozinho.
    permitido, _ = await daily_budget.consume("realtime", settings.daily_realtime_limit)
    if not permitido:
        raise HTTPException(
            status_code=503,
            detail="Daily limit for this demo reached. It resets at midnight UTC.",
            headers={"Retry-After": str(daily_budget.seconds_until_utc_midnight())},
        )

    corpo = {
        "session": {
            "type": "realtime",
            "model": settings.realtime_model,
            "instructions": INSTRUCOES,
            "audio": {"output": {"voice": settings.realtime_voice}},
            "tools": [FERRAMENTA_BUSCA],
            "tool_choice": "auto",
        }
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                CLIENT_SECRETS_URL,
                json=corpo,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            )
            r.raise_for_status()
            dados = r.json()
    except httpx.HTTPError as e:
        logger.warning("realtime: falha ao cunhar credencial: %s", e)
        raise HTTPException(status_code=503, detail="Realtime voice is unavailable") from e

    return RealtimeSessionResponse(
        client_secret=dados["value"],
        expires_at=dados["expires_at"],
        model=settings.realtime_model,
    )


@router.post("/tool/buscar", response_model=RealtimeToolResponse)
async def executar_busca(
    session_id: str,
    body: RealtimeToolRequest,
    session_store: SessionStore = Depends(get_session_store),
    vector_service: VectorService = Depends(get_vector_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """Executa a tool que o modelo chamou, com o MESMO pipeline do /query.

    O navegador recebe o `function_call` pelo data channel e bate aqui; a
    resposta volta para o modelo como `function_call_output`. Deliberadamente
    não é o navegador que decide o que é relevante — quem filtra continua sendo
    o grader, do lado do servidor.
    """
    settings = get_settings()

    sessao = await session_store.get(session_id)
    if sessao is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    try:
        trechos, baixa_confianca = await _retrieve_and_grade(
            session_id=session_id,
            query=body.pergunta,
            settings=settings,
            vector_service=vector_service,
            embedding_service=embedding_service,
        )
    except HTTPException as e:
        # 404 do retrieval significa "nada sobreviveu ao grader". Para o modelo
        # isso e uma resposta valida — e a diferenca entre ele dizer "nao esta
        # nos documentos" e inventar. Nunca vira erro.
        if e.status_code == 404:
            return RealtimeToolResponse(trechos=[], baixa_confianca=True)
        raise

    return RealtimeToolResponse(
        trechos=[
            {
                "texto": t.get("content", ""),
                "arquivo": t.get("file_name", ""),
                "pagina": t.get("page_number"),
            }
            for t in trechos
        ],
        baixa_confianca=baixa_confianca,
    )
