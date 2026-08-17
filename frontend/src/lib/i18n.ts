const translations: Record<string, Record<string, string>> = {
  en: {
    'nav.title': 'Voice RAG',
    'nav.queries': 'queries',
    'nav.docsLeft': 'docs left',
    'nav.restart': 'Restart',

    'welcome.title': 'Voice-Powered Document Q&A',
    'welcome.subtitle': 'Upload a PDF, choose a voice, and ask questions, get spoken answers grounded in your documents.',

    'pipeline.label': 'How It Works',
    'pipeline.1.title': 'Upload PDF',
    'pipeline.1.desc': 'Your document is split into semantic chunks using LangChain text splitters.',
    'pipeline.2.title': 'Embed Locally',
    'pipeline.2.desc': 'Each chunk is embedded on the server with FastEmbed (multilingual MiniLM), so Portuguese and English share one vector space and no embedding API is called.',
    'pipeline.3.title': 'Vector Search',
    'pipeline.3.desc': 'Your question is embedded and matched against stored chunks via pgvector cosine similarity.',
    'pipeline.4.title': 'AI Agent',
    'pipeline.4.desc': 'A Processor Agent (DeepSeek via OpenRouter) synthesizes a grounded answer from the retrieved context.',
    'pipeline.5.title': 'Voice Response',
    'pipeline.5.desc': 'The answer is streamed as speech via GPT-4o-mini-TTS using Server-Sent Events + Web Audio API.',
    'pipeline.footer': 'FastEmbed (local) \u00b7 PostgreSQL + pgvector \u00b7 OpenAI Agents SDK \u00b7 SSE Audio Streaming',

    'step1.title': 'Upload Documents',
    'step1.subtitle.empty': 'PDF files up to 10MB',
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
    'welcome.subtitle': 'Envie um PDF, escolha uma voz e faça perguntas, recebendo respostas faladas com base nos seus documentos.',

    'pipeline.label': 'Como Funciona',
    'pipeline.1.title': 'Upload do PDF',
    'pipeline.1.desc': 'Seu documento é dividido em chunks semânticos usando LangChain text splitters.',
    'pipeline.2.title': 'Embedding Local',
    'pipeline.2.desc': 'Cada chunk vira embedding no próprio servidor com FastEmbed (MiniLM multilíngue), então português e inglês dividem o mesmo espaço vetorial e nenhuma API de embedding é chamada.',
    'pipeline.3.title': 'Busca Vetorial',
    'pipeline.3.desc': 'Sua pergunta é transformada em embedding e comparada com os chunks armazenados via similaridade de cosseno no pgvector.',
    'pipeline.4.title': 'Agente de IA',
    'pipeline.4.desc': 'Um Agente Processador (DeepSeek via OpenRouter) sintetiza uma resposta fundamentada a partir do contexto recuperado.',
    'pipeline.5.title': 'Resposta por Voz',
    'pipeline.5.desc': 'A resposta é transmitida como fala via GPT-4o-mini-TTS usando Server-Sent Events + Web Audio API.',
    'pipeline.footer': 'FastEmbed (local) \u00b7 PostgreSQL + pgvector \u00b7 OpenAI Agents SDK \u00b7 SSE Audio Streaming',

    'step1.title': 'Enviar Documentos',
    'step1.subtitle.empty': 'Arquivos PDF de até 10MB',
    'step1.subtitle.one': '1 documento indexado',
    'step1.subtitle.many': '{count} documentos indexados',
    'step1.limitReached': 'Limite de documentos atingido',

    'step2.title': 'Escolher Voz',
    'step2.subtitle.locked': 'Escolha como a IA responde',

    'step3.title': 'Fazer uma Pergunta',
    'step3.subtitle.ready': 'Digite sua pergunta e pressione Enter',
    'step3.subtitle.locked': 'Complete as etapas acima primeiro',
    'step3.queryLimit': 'Limite de consultas atingido. Reinicie para criar uma nova sessão.',

    'toast.uploaded': '{name} enviado',
    'toast.uploadFailed': 'Falha no upload',
    'toast.docRemoved': 'Documento removido',
    'toast.docRemoveFailed': 'Falha ao remover documento',
    'toast.queryFailed': 'Falha na consulta',
    'toast.historyFailed': 'Falha ao carregar histórico',
    'toast.restarted': 'Sessão reiniciada',

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
