"use client";

/**
 * Botão de conversa contínua + o que ela produz.
 *
 * A UI existe para deixar VISÍVEL o que separa isto de "voz colada num RAG":
 * cada `buscar_nos_documentos` que o modelo dispara aparece na linha do tempo,
 * com a pergunta que ele mesmo formulou e quantos trechos voltaram. Sem isso o
 * visitante ouve uma resposta bonita e não tem como saber se ela veio dos
 * documentos dele ou da memória do modelo — que é exatamente a dúvida que esta
 * demo existe para responder.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Square, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  RealtimeSession,
  type EstadoRealtime,
  type FalaNaConversa,
} from "@/lib/realtime-session";

type Item =
  | { tipo: "fala"; id: string; quem: "pessoa" | "agente"; texto: string }
  | { tipo: "busca"; id: string; pergunta: string; trechos: number };

const ROTULO: Record<EstadoRealtime, string> = {
  parado: "Start a conversation",
  conectando: "Connecting…",
  ouvindo: "Listening — just talk",
  buscando: "Searching your documents…",
  falando: "Speaking",
};

export function LiveVoice({ sessionId, pronto }: { sessionId: string; pronto: boolean }) {
  const [estado, setEstado] = useState<EstadoRealtime>("parado");
  const [itens, setItens] = useState<Item[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const sessaoRef = useRef<RealtimeSession | null>(null);
  const fimRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [itens]);

  // Encerrar ao desmontar não é opcional: sem isto o microfone continua aberto
  // e a sessão segue sendo cobrada por minuto depois que a pessoa sai da aba.
  useEffect(() => () => sessaoRef.current?.desconectar(), []);

  const parar = useCallback(() => {
    sessaoRef.current?.desconectar();
    sessaoRef.current = null;
  }, []);

  const começar = useCallback(async () => {
    setErro(null);
    setItens([]);
    const sessao = new RealtimeSession(sessionId, {
      onEstado: setEstado,
      onFala: (f: FalaNaConversa) =>
        setItens((xs) => [...xs, { tipo: "fala", id: f.id, quem: f.quem, texto: f.texto }]),
      onBusca: (pergunta, trechos) =>
        setItens((xs) => [
          ...xs,
          { tipo: "busca", id: `busca-${xs.length}`, pergunta, trechos },
        ]),
      onErro: setErro,
    });
    sessaoRef.current = sessao;
    try {
      await sessao.conectar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Could not start the conversation");
      parar();
    }
  }, [sessionId, parar]);

  const ativo = estado !== "parado";

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Button
          onClick={ativo ? parar : começar}
          disabled={!pronto || estado === "conectando"}
          variant={ativo ? "destructive" : "default"}
        >
          {ativo ? <Square className="mr-2 h-4 w-4" /> : <Mic className="mr-2 h-4 w-4" />}
          {ativo ? "End conversation" : "Talk to your documents"}
        </Button>
        <span className="text-sm text-muted-foreground" aria-live="polite">
          {pronto ? ROTULO[estado] : "Upload a document first"}
        </span>
      </div>

      {erro && <p className="text-sm text-destructive">{erro}</p>}

      {itens.length > 0 && (
        <div className="max-h-80 space-y-2 overflow-y-auto rounded-lg border p-3">
          {itens.map((it) =>
            it.tipo === "busca" ? (
              <div
                key={it.id}
                className="flex items-start gap-2 rounded-md bg-muted/50 px-3 py-2 font-mono text-xs text-muted-foreground"
              >
                <Search className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  searched your documents: “{it.pergunta}” → {it.trechos}{" "}
                  {it.trechos === 1 ? "passage" : "passages"}
                </span>
              </div>
            ) : (
              <div
                key={it.id}
                className={
                  it.quem === "pessoa"
                    ? "ml-auto max-w-[85%] rounded-lg bg-primary/10 px-3 py-2 text-sm"
                    : "max-w-[85%] rounded-lg bg-muted px-3 py-2 text-sm"
                }
              >
                {it.texto}
              </div>
            ),
          )}
          <div ref={fimRef} />
        </div>
      )}
    </div>
  );
}
