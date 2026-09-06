# A camada de voz sai daqui e vai para o BrainHub

> **06/09/2026.** Este projeto vai ser **aposentado como card de portfólio**. A engenharia de
> voz dele está certa e vai ser preservada: ela migra para o `group-documents` (BrainHub).
> Este documento é o inventário exato do que migra, o que muda no caminho, e por quê.
>
> Análise que originou a decisão: `pgtech/docs/26-voz-sobre-documentos-e-o-que-o-provedor-ja-faz.md`

---

## 1. Por que, em três parágrafos

**O código está certo.** A conversa ao vivo aqui é WebRTC de verdade contra a Realtime API,
fala a fala, com `gpt-realtime-2.1`. O áudio não passa pelo backend, a credencial é efêmera e
cunhada no servidor, a busca roda do lado do servidor com o mesmo grader do `/query`, o teto
diário é consumido antes de cunhar, e busca vazia volta como resposta válida em vez de erro.
Isso é o padrão de 2026 e não precisa de refatoração.

**O produto é que não existe.** Qualquer pessoa sobe um PDF no Claude, no ChatGPT ou no
Gemini, pergunta por voz, ouve a resposta e continua a conversa. Não há uma linha da
comparação onde este projeto ganhe, e há linhas onde o provedor ganha (multimodal, memória
entre sessões). Um avaliador técnico faz essa conta em quinze segundos.

**O que diferencia não é a voz, é o acervo.** Acervo grande de verdade, isolamento entre
inquilinos, o caminho até a resposta, fontes que se contradizem, recorte no tempo. Cinco
dessas seis coisas **já estão construídas no BrainHub**. Então a voz vai para lá, e não o
contrário: lá estão 94 testes, a fila durável, o isolamento por usuário e a tabela
`decisions`. Aqui são 10 testes e nenhum acervo.

---

## 2. O que migra, arquivo por arquivo

| Origem | Linhas | Destino | Muda? |
|---|---:|---|---|
| `backend/routers/realtime.py` | 200 | `backend/app/api/routes/realtime.py` | sim, §3 |
| `frontend/src/lib/realtime-session.ts` | 194 | `frontend/lib/realtime-session.ts` | quase nada, §4 |
| `frontend/src/components/live-voice.tsx` | 131 | `frontend/components/chat/LiveVoice.tsx` | sim, §4 |
| `backend/models/schemas.py`: `RealtimeSessionResponse`, `RealtimeToolRequest`, `RealtimeTrecho`, `RealtimeToolResponse` | ~35 | schemas do BrainHub | só o `Trecho` |
| `backend/config.py`: `enable_realtime`, `realtime_model`, `realtime_voice`, `daily_realtime_limit` | 4 | `app/config/settings.py` | não |

**Total: cerca de 560 linhas**, das quais a maior parte migra sem alteração.

### O que NÃO migra, e é de propósito

O pipeline de turno único (`/query`, `/query/stream`, TTS por sentença, o player de Web Audio,
o `MediaRecorder`). O BrainHub já tem chat por texto com SSE. O caminho gravar-subir-transcrever
é a arquitetura de 2024 que a conversa ao vivo substitui, e levá-lo junto seria carregar duas
gerações para dentro de um projeto que hoje tem uma só.

---

## 3. O que muda no backend ao migrar

O broker daqui foi escrito para um visitante anônimo com `session_id` em `localStorage`. O
BrainHub tem usuário com JWT. As quatro diferenças:

| Aqui | No BrainHub |
|---|---|
| `session_id` como query param, validado contra `SessionStore` | `user_id = await require_user(request)`, o dependency de JWT que já existe |
| `_retrieve_and_grade(session_id=...)` | `retrieve_documents(question, user_id=..., as_of=..., top_k=...)`, que **já exige `user_id`** e **já aceita `as_of`** |
| `daily_budget.consume("realtime", limit)` | `metering.consumir("realtime", settings.daily_realtime_limit)`, mesmíssimo formato dos tetos de `chat` e `ingest` que já existem |
| a tool devolve trechos e sai | a tool devolve trechos **e grava uma linha em `decisions`**, que é o ponto inteiro da migração |

### 🔑 A mudança que justifica tudo

Aqui, `POST /api/realtime/tool/buscar` devolve os trechos e acabou. No BrainHub ele passa a
escrever na tabela `decisions`, do mesmo jeito que `POST /chat` já faz: variantes de query,
trechos com score, o que o grader aprovou, se o rerank rodou, se caiu na rede de baixa
confiança, `conflict`, `as_of` e `latency_ms`.

**Consequência:** a trilha de decisão passa a ser escrita **enquanto a pessoa fala**. Isso é
o momento de demo que nenhum chat de provedor consegue encenar, porque eles são caixa-preta
por projeto. Um chat de provedor te dá a resposta. Este te dá a resposta e o caminho até ela,
ao vivo.

### As instruções do agente mudam também

O `INSTRUCOES` daqui manda o modelo responder só a partir dos documentos e dizer quando não
está lá. No BrainHub ele ganha duas obrigações a mais, que são o que o acervo permite e o
provedor não:

- quando a checagem de conflito devolver divergência, **dizer em voz alta** que duas fontes
  respondem diferente, nomeando as duas;
- quando a pessoa perguntar sobre uma data, usar `as_of` e dizer qual recorte usou.

---

## 4. O que muda no frontend

`realtime-session.ts` migra quase intacto: `RTCPeerConnection`, `getUserMedia`,
`createDataChannel("oai-events")`, o tratamento de `function_call` e o `function_call_output`
seguido de `response.create` continuam iguais. Muda só a URL da tool e o header de
autorização, que passa a levar o JWT.

`live-voice.tsx` vira um componente ao lado do chat, e não uma página. E ganha o painel de
trilha: enquanto a pessoa fala, o painel se preenche com o que a tool gravou.

### ⚠️ CSP: a armadilha que já derrubou isto uma vez

O commit `21e3642` deste repo registra que **o botão de conversa ao vivo falhava para 100% dos
visitantes** porque a CSP do frontend não listava `api.openai.com` em `connect-src`, e o WebRTC
troca o SDP direto com a OpenAI.

**Verificado em 06/09:** a CSP do BrainHub hoje é `connect-src 'self' https: wss:`, que já
cobre. **Não há mudança a fazer**, mas se alguém apertar essa CSP no futuro sem lembrar disto,
a conversa ao vivo morre em silêncio e sem erro visível no servidor. Deixe esta nota junto da
regra.

---

## 5. O que fazer com este repositório depois

1. **Não apagar.** O histórico documenta a construção da camada de voz, e o `docs/26` do
   `pgtech` cita este código como a implementação de referência.
2. **Sai da grade do portfólio** (proposta de mudança ao **D-040**, decisão do Pedro).
3. **Antes de migrar, subir o rerank** de `rerank-v3.5` para `rerank-v4.0-fast`, que é o que o
   BrainHub já usa. Meia hora, e evita levar a defasagem junto.
4. O container `voicerag-*` na VPS só pode ser derrubado **depois** que o card sair do
   portfólio no ar. Demo morta custa mais que demo ausente, e hoje o card ainda aponta para cá.

---

## 6. Ordem de execução

```
1. subir rerank para v4.0-fast aqui                            ~30min
2. migrar realtime.py -> app/api/routes/realtime.py            ~1 dia
   com require_user, retrieve_documents e a escrita em decisions
3. migrar realtime-session.ts + LiveVoice.tsx                  ~1 dia
4. painel de trilha ao lado da conversa                        ~1 dia
5. semear o acervo de demo, com contradicao plantada           ~4h
6. reescrever o card do portfolio e aposentar o do Voice RAG   ~2h
7. so entao derrubar os containers voicerag-*
```
