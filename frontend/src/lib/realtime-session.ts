/**
 * Conversa por voz contínua sobre os documentos, via WebRTC.
 *
 * O resto do app faz um turno por vez: grava um áudio, sobe, transcreve,
 * recupera, gera, sintetiza, toca um MP3. Aqui o modelo fala e escuta ao mesmo
 * tempo, e quando precisa de um fato dos documentos ele CHAMA a busca no meio
 * da frase — a pessoa interrompe, pede pra repetir, muda de assunto e volta, e
 * a conversa continua.
 *
 * O áudio NÃO passa pelo nosso backend. Proxiar mídia em tempo real numa VPS de
 * 2 vCPU seria o gargalo, e o WebRTC já resolve jitter, perda de pacote e eco.
 * O backend entra só onde precisa mandar: cunhar a credencial efêmera (a chave
 * real da OpenAI nunca chega ao navegador) e executar a busca, para que quem
 * decide o que é relevante continue sendo o grader do servidor.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const CALLS_URL = "https://api.openai.com/v1/realtime/calls";

export type EstadoRealtime = "parado" | "conectando" | "ouvindo" | "buscando" | "falando";

export type FalaNaConversa = {
  id: string;
  quem: "pessoa" | "agente";
  texto: string;
};

type Callbacks = {
  onEstado?: (estado: EstadoRealtime) => void;
  onFala?: (fala: FalaNaConversa) => void;
  /** Cada busca que o modelo disparou — é o que a UI mostra como prova de RAG. */
  onBusca?: (pergunta: string, trechos: number) => void;
  onErro?: (mensagem: string) => void;
};

export class RealtimeSession {
  private pc: RTCPeerConnection | null = null;
  private dc: RTCDataChannel | null = null;
  private stream: MediaStream | null = null;
  private audio: HTMLAudioElement | null = null;
  private readonly sessionId: string;
  private readonly cb: Callbacks;

  constructor(sessionId: string, cb: Callbacks = {}) {
    this.sessionId = sessionId;
    this.cb = cb;
  }

  async conectar(): Promise<void> {
    this.cb.onEstado?.("conectando");

    // 1. Credencial efêmera. O backend cunha já amarrada às instruções e à
    //    tool; o navegador nunca vê a chave real.
    const r = await fetch(
      `${API_BASE_URL}/api/realtime/session?session_id=${encodeURIComponent(this.sessionId)}`,
      { method: "POST" },
    );
    if (!r.ok) {
      const e = await r.json().catch(() => ({ detail: "Realtime is unavailable" }));
      throw new Error(e.detail ?? "Realtime is unavailable");
    }
    const { client_secret } = (await r.json()) as { client_secret: string };

    // 2. Microfone. Sem echoCancellation o modelo escuta a própria voz pelo
    //    alto-falante e se interrompe sozinho num loop.
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });

    const pc = new RTCPeerConnection();
    this.pc = pc;

    this.audio = new Audio();
    this.audio.autoplay = true;
    pc.ontrack = (ev) => {
      if (this.audio) this.audio.srcObject = ev.streams[0];
    };
    this.stream.getTracks().forEach((t) => pc.addTrack(t, this.stream!));

    // 3. Data channel: tudo que não é áudio (transcrições, chamadas de tool).
    const dc = pc.createDataChannel("oai-events");
    this.dc = dc;
    dc.addEventListener("message", (ev) => {
      void this.aoEvento(JSON.parse(ev.data));
    });

    // 4. Troca de SDP direto com a OpenAI, autenticada pela credencial efêmera.
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const resp = await fetch(CALLS_URL, {
      method: "POST",
      body: offer.sdp,
      headers: {
        Authorization: `Bearer ${client_secret}`,
        "Content-Type": "application/sdp",
      },
    });
    if (!resp.ok) throw new Error("Could not open the voice connection");
    await pc.setRemoteDescription({ type: "answer", sdp: await resp.text() });

    this.cb.onEstado?.("ouvindo");
  }

  private async aoEvento(ev: Record<string, unknown>): Promise<void> {
    const tipo = ev.type as string;

    // Fala da pessoa, já transcrita pelo próprio modelo.
    if (tipo === "conversation.item.input_audio_transcription.completed") {
      const texto = String(ev.transcript ?? "").trim();
      if (texto) {
        this.cb.onFala?.({ id: String(ev.item_id ?? Date.now()), quem: "pessoa", texto });
      }
      return;
    }

    if (tipo === "response.output_audio_transcript.done") {
      const texto = String(ev.transcript ?? "").trim();
      if (texto) {
        this.cb.onFala?.({ id: String(ev.item_id ?? Date.now()), quem: "agente", texto });
      }
      return;
    }

    if (tipo === "output_audio_buffer.started") return this.cb.onEstado?.("falando");
    if (tipo === "output_audio_buffer.stopped") return this.cb.onEstado?.("ouvindo");

    if (tipo === "error") {
      this.cb.onErro?.(String((ev.error as Record<string, unknown>)?.message ?? "Realtime error"));
      return;
    }

    // O modelo pediu a busca. Chega dentro do response.done concluído.
    if (tipo === "response.done") {
      const saidas = ((ev.response as Record<string, unknown>)?.output ?? []) as Array<
        Record<string, unknown>
      >;
      for (const item of saidas) {
        if (item.type === "function_call" && item.name === "buscar_nos_documentos") {
          await this.executarBusca(String(item.call_id), String(item.arguments ?? "{}"));
        }
      }
    }
  }

  private async executarBusca(callId: string, argumentosJson: string): Promise<void> {
    this.cb.onEstado?.("buscando");
    let pergunta = "";
    let saida: unknown;
    try {
      pergunta = String(JSON.parse(argumentosJson)?.pergunta ?? "");
      const r = await fetch(
        `${API_BASE_URL}/api/realtime/tool/buscar?session_id=${encodeURIComponent(this.sessionId)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pergunta }),
        },
      );
      saida = r.ok
        ? await r.json()
        : { trechos: [], baixa_confianca: true, erro: "search failed" };
    } catch {
      // Erro da busca vira RESULTADO, não exceção: o modelo precisa poder
      // dizer que não conseguiu, e um tool call sem resposta trava o turno.
      saida = { trechos: [], baixa_confianca: true, erro: "search failed" };
    }

    const trechos = (saida as { trechos?: unknown[] })?.trechos?.length ?? 0;
    this.cb.onBusca?.(pergunta, trechos);

    this.enviar({
      type: "conversation.item.create",
      item: { type: "function_call_output", call_id: callId, output: JSON.stringify(saida) },
    });
    this.enviar({ type: "response.create" });
    this.cb.onEstado?.("falando");
  }

  private enviar(payload: unknown): void {
    if (this.dc?.readyState === "open") this.dc.send(JSON.stringify(payload));
  }

  desconectar(): void {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.dc?.close();
    this.pc?.close();
    if (this.audio) this.audio.srcObject = null;
    this.stream = null;
    this.dc = null;
    this.pc = null;
    this.audio = null;
    this.cb.onEstado?.("parado");
  }
}
