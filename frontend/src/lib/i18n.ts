const translations: Record<string, Record<string, string>> = {
  en: {
    'nav.title': 'Voice RAG',
    'nav.queries': 'queries',
    'nav.docsLeft': 'docs left',
    'nav.restart': 'Restart',

    'welcome.title': 'Voice-Powered Document Q&A',
    'welcome.subtitle': 'Upload a PDF, choose a voice, and ask questions — get spoken answers grounded in your documents.',

    'pipeline.label': 'How It Works',
    'pipeline.1.title': 'Upload PDF',
    'pipeline.1.desc': 'Your document is split into semantic chunks using LangChain text splitters.',
    'pipeline.2.title': 'Embed Locally',
    'pipeline.2.desc': 'Each chunk is embedded using FastEmbed (BAAI/bge-small-en-v1.5) — no external API needed.',
    'pipeline.3.title': 'Vector Search',
    'pipeline.3.desc': 'Your question is embedded and matched against stored chunks via pgvector cosine similarity.',
    'pipeline.4.title': 'AI Agent',
    'pipeline.4.desc': 'A Processor Agent (GPT-4.1-mini) synthesizes a grounded answer from the retrieved context.',
    'pipeline.5.title': 'Voice Response',
    'pipeline.5.desc': 'The answer is streamed as speech via GPT-4o-mini-TTS using Server-Sent Events + Web Audio API.',
    'pipeline.footer': 'FastEmbed (local) \u00b7 PostgreSQL + pgvector \u00b7 OpenAI Agents SDK \u00b7 SSE Audio Streaming',

    'step1.title': 'Upload Documents',
    'step1.subtitle.empty': 'PDF files up to 50MB',
    'step1.subtitle.one': '1 document indexed',
    'step1.subtitle.many': '{count} documents indexed',
    'step1.limitReached': 'Document limit reached',

    'step2.title': 'Select Voice',
    'step2.subtitle.locked': 'Choose how the AI responds',

    'step3.title': 'Ask a Question',
    'step3.subtitle.ready': 'Type your question and press Enter',
    'step3.subtitle.locked': 'Complete the steps above first',
    'step3.queryLimit': 'Query limit reached. Restart to create a new session.',

    'toast.uploaded': 'Uploaded {name}',
    'toast.uploadFailed': 'Upload failed',
    'toast.docRemoved': 'Document removed',
    'toast.docRemoveFailed': 'Failed to remove document',
    'toast.queryFailed': 'Query failed',
    'toast.historyFailed': 'Failed to load history',
    'toast.restarted': 'Session restarted',

    'footer': 'Built with Next.js, FastAPI, and OpenAI',
  },
  pt: {
    'nav.title': 'Voice RAG',
    'nav.queries': 'consultas',
    'nav.docsLeft': 'docs restantes',
    'nav.restart': 'Reiniciar',

    'welcome.title': 'Q&A de Documentos por Voz',
    'welcome.subtitle': 'Envie um PDF, escolha uma voz e faca perguntas — receba respostas faladas baseadas nos seus documentos.',

    'pipeline.label': 'Como Funciona',
    'pipeline.1.title': 'Upload do PDF',
    'pipeline.1.desc': 'Seu documento e dividido em chunks semanticos usando LangChain text splitters.',
    'pipeline.2.title': 'Embedding Local',
    'pipeline.2.desc': 'Cada chunk e transformado em embedding usando FastEmbed (BAAI/bge-small-en-v1.5) — sem API externa.',
    'pipeline.3.title': 'Busca Vetorial',
    'pipeline.3.desc': 'Sua pergunta e transformada em embedding e comparada com os chunks armazenados via similaridade cosseno no pgvector.',
    'pipeline.4.title': 'Agente de IA',
    'pipeline.4.desc': 'Um Agente Processador (GPT-4.1-mini) sintetiza uma resposta fundamentada a partir do contexto recuperado.',
    'pipeline.5.title': 'Resposta por Voz',
    'pipeline.5.desc': 'A resposta e transmitida como fala via GPT-4o-mini-TTS usando Server-Sent Events + Web Audio API.',
    'pipeline.footer': 'FastEmbed (local) \u00b7 PostgreSQL + pgvector \u00b7 OpenAI Agents SDK \u00b7 SSE Audio Streaming',

    'step1.title': 'Enviar Documentos',
    'step1.subtitle.empty': 'Arquivos PDF ate 50MB',
    'step1.subtitle.one': '1 documento indexado',
    'step1.subtitle.many': '{count} documentos indexados',
    'step1.limitReached': 'Limite de documentos atingido',

    'step2.title': 'Escolher Voz',
    'step2.subtitle.locked': 'Escolha como a IA responde',

    'step3.title': 'Fazer uma Pergunta',
    'step3.subtitle.ready': 'Digite sua pergunta e pressione Enter',
    'step3.subtitle.locked': 'Complete as etapas acima primeiro',
    'step3.queryLimit': 'Limite de consultas atingido. Reinicie para criar uma nova sessao.',

    'toast.uploaded': '{name} enviado',
    'toast.uploadFailed': 'Falha no upload',
    'toast.docRemoved': 'Documento removido',
    'toast.docRemoveFailed': 'Falha ao remover documento',
    'toast.queryFailed': 'Falha na consulta',
    'toast.historyFailed': 'Falha ao carregar historico',
    'toast.restarted': 'Sessao reiniciada',

    'footer': 'Feito com Next.js, FastAPI e OpenAI',
  },
};

export type Locale = 'en' | 'pt';

export function detectLocale(): Locale {
  if (typeof window === 'undefined') return 'en';
  const lang = navigator.language.toLowerCase();
  if (lang.startsWith('pt')) return 'pt';
  return 'en';
}

export function getTranslations(locale: Locale) {
  const dict = translations[locale] || translations.en;
  return (key: string, params?: Record<string, string | number>): string => {
    let value = dict[key] || translations.en[key] || key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        value = value.replace(`{${k}}`, String(v));
      }
    }
    return value;
  };
}
