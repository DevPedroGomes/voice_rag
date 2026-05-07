import Link from "next/link";
import {
  Mic,
  FileUp,
  Cpu,
  Search,
  MessageSquare,
  Volume2,
  ArrowRight,
  Zap,
  Lock,
  Sparkles,
  Github,
  Play,
  Layers,
  Database,
  Activity,
} from "lucide-react";

export const metadata = {
  title: "Voice RAG — Speak the question. Hear the answer.",
  description:
    "Upload PDFs, ask out loud, hear cited answers in natural speech. End-to-end voice loop with hybrid retrieval and streaming TTS.",
};

const PIPELINE = [
  {
    n: 1,
    icon: FileUp,
    title: "Upload PDF",
    desc: "Document is split into semantic chunks via LangChain text splitters.",
    accent: "text-blue-600 bg-blue-50",
  },
  {
    n: 2,
    icon: Cpu,
    title: "Embed Locally",
    desc: "FastEmbed (BAAI/bge-small-en-v1.5) runs on the server — no external embedding API.",
    accent: "text-violet-600 bg-violet-50",
  },
  {
    n: 3,
    icon: Search,
    title: "Hybrid Retrieval",
    desc: "Question is embedded and fused with full-text search via pgvector + tsvector.",
    accent: "text-emerald-600 bg-emerald-50",
  },
  {
    n: 4,
    icon: MessageSquare,
    title: "AI Synthesis",
    desc: "Processor Agent (GPT-4.1-mini) writes a grounded answer with citations.",
    accent: "text-orange-600 bg-orange-50",
  },
  {
    n: 5,
    icon: Volume2,
    title: "Stream Speech",
    desc: "GPT-4o-mini-TTS streams PCM audio over SSE into the Web Audio API.",
    accent: "text-pink-600 bg-pink-50",
  },
];

const FEATURES = [
  {
    icon: Activity,
    title: "Sub-1.5s first audible word",
    desc: "Audio starts streaming before the LLM has finished writing — perceived latency drops to near-zero.",
    span: "md:col-span-2",
  },
  {
    icon: Lock,
    title: "Tenant-isolated retrieval",
    desc: "Every chunk row carries a session_id. Vector and keyword queries WHERE-filter on it before fusion. No cross-tenant leak.",
  },
  {
    icon: Database,
    title: "Hybrid search, not just vectors",
    desc: "pgvector HNSW + tsvector GIN, merged via RRF. Catches both semantic similarity and exact-term matches.",
  },
  {
    icon: Zap,
    title: "Local embeddings",
    desc: "FastEmbed runs on the server in ONNX. No OpenAI cost for ingestion, full data control.",
  },
  {
    icon: Sparkles,
    title: "9 distinct voices",
    desc: "Coral, alloy, echo, fable, onyx, nova, sage, shimmer, verse — pick a voice that fits the use case.",
    span: "md:col-span-2",
  },
];

const STACK = [
  "Next.js 16",
  "React 19",
  "FastAPI",
  "PostgreSQL 17",
  "pgvector",
  "FastEmbed (ONNX)",
  "OpenAI Whisper",
  "GPT-4.1-mini",
  "GPT-4o-mini-TTS",
  "OpenAI Agents SDK",
  "Server-Sent Events",
  "Web Audio API",
];

function Waveform() {
  // Static visual: 32 vertical bars with staggered animation.
  const bars = Array.from({ length: 32 });
  return (
    <div className="flex items-end justify-center gap-1.5 h-24" aria-hidden>
      {bars.map((_, i) => {
        const delay = (i % 8) * 0.08;
        const heightSeed = 30 + ((i * 37) % 70);
        return (
          <span
            key={i}
            className="w-1.5 rounded-full bg-gradient-to-t from-orange-400/40 via-orange-500/80 to-pink-500/80 animate-pulse"
            style={{
              height: `${heightSeed}%`,
              animationDelay: `${delay}s`,
              animationDuration: "1.4s",
            }}
          />
        );
      })}
    </div>
  );
}

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-[#fafafa] text-neutral-900 antialiased">
      {/* ─── Nav ─── */}
      <header className="sticky top-0 z-50 border-b border-neutral-200/70 bg-white/80 backdrop-blur-xl">
        <nav className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-pink-500 text-white">
              <Mic size={16} strokeWidth={2.5} />
            </span>
            <span className="font-semibold tracking-tight">Voice RAG</span>
          </Link>
          <div className="hidden sm:flex items-center gap-6 text-sm text-neutral-600">
            <a href="#how" className="hover:text-neutral-900 transition-colors">How it works</a>
            <a href="#features" className="hover:text-neutral-900 transition-colors">Features</a>
            <a href="#stack" className="hover:text-neutral-900 transition-colors">Stack</a>
          </div>
          <div className="flex items-center gap-2">
            <a
              href="https://github.com/devpedrogomes/voice_rag"
              target="_blank"
              rel="noopener noreferrer"
              className="hidden sm:inline-flex items-center gap-1.5 text-xs text-neutral-600 hover:text-neutral-900 transition-colors px-3 py-1.5 rounded-full border border-neutral-200 bg-white"
            >
              <Github size={14} /> Source
            </a>
            <Link
              href="/app"
              className="inline-flex items-center gap-1.5 text-xs sm:text-sm font-medium text-white bg-neutral-900 hover:bg-neutral-800 transition-colors px-3 sm:px-4 py-1.5 sm:py-2 rounded-full"
            >
              Try it <ArrowRight size={14} />
            </Link>
          </div>
        </nav>
      </header>

      {/* ─── Hero ─── */}
      <section className="relative overflow-hidden">
        {/* Soft radial bg */}
        <div
          className="absolute inset-0 -z-10"
          aria-hidden
          style={{
            background:
              "radial-gradient(ellipse 60% 40% at 50% 0%, rgba(251,146,60,0.12), transparent 60%), radial-gradient(ellipse 50% 30% at 50% 80%, rgba(236,72,153,0.08), transparent 70%)",
          }}
        />

        <div className="max-w-5xl mx-auto px-6 pt-16 pb-20 sm:pt-24 sm:pb-28 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white border border-neutral-200 text-xs text-neutral-600 mb-6 animate-fade-in-up shadow-sm">
            <span className="inline-flex items-center gap-1 text-orange-600 font-medium">
              <Sparkles size={12} /> Voice + RAG
            </span>
            <span className="text-neutral-300">·</span>
            <span>Production showcase</span>
          </div>

          <h1
            className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-semibold tracking-tighter text-neutral-900 max-w-4xl mx-auto animate-fade-in-up"
            style={{ animationDelay: "0.1s" }}
          >
            Speak the question.
            <br />
            <span className="bg-gradient-to-r from-orange-500 via-pink-500 to-violet-500 bg-clip-text text-transparent">
              Hear the answer.
            </span>
          </h1>

          <p
            className="mt-6 text-lg sm:text-xl text-neutral-600 max-w-2xl mx-auto leading-relaxed animate-fade-in-up"
            style={{ animationDelay: "0.2s" }}
          >
            Upload PDFs, ask out loud, hear cited answers streamed back as natural speech.
            Full voice loop in production — mic capture, Whisper STT, hybrid retrieval, low-latency TTS.
          </p>

          <div
            className="flex flex-col sm:flex-row gap-3 items-center justify-center mt-8 animate-fade-in-up"
            style={{ animationDelay: "0.3s" }}
          >
            <Link
              href="/app"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-neutral-900 text-white text-sm font-semibold hover:bg-neutral-800 transition-all hover:-translate-y-0.5 shadow-lg shadow-neutral-900/10"
            >
              <Play size={16} /> Try the live demo
            </Link>
            <a
              href="#how"
              className="inline-flex items-center gap-2 px-5 py-3 rounded-full bg-white text-neutral-700 text-sm font-medium border border-neutral-200 hover:border-neutral-300 transition-colors"
            >
              How it works <ArrowRight size={14} />
            </a>
          </div>

          <p className="text-xs text-neutral-400 mt-5 font-mono">
            Showcase mode · 5 queries / 3 docs / 5-min session TTL
          </p>

          {/* Waveform */}
          <div className="mt-12 max-w-md mx-auto animate-fade-in-up" style={{ animationDelay: "0.4s" }}>
            <Waveform />
          </div>
        </div>
      </section>

      {/* ─── How it works ─── */}
      <section id="how" className="border-y border-neutral-200/70 bg-white">
        <div className="max-w-6xl mx-auto px-6 py-16 sm:py-20">
          <div className="text-center mb-12">
            <span className="text-xs uppercase tracking-widest text-neutral-400 font-mono">Pipeline</span>
            <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-2">
              Five stages, end to end
            </h2>
            <p className="text-neutral-600 mt-3 max-w-xl mx-auto">
              Every voice query travels this exact path. No black box.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {PIPELINE.map((step) => (
              <div
                key={step.n}
                className="relative bg-white border border-neutral-200/80 rounded-2xl p-5 card-shadow hover-lift"
              >
                <div className="flex items-center gap-3 mb-3">
                  <span className={`inline-flex items-center justify-center w-9 h-9 rounded-lg ${step.accent}`}>
                    <step.icon size={16} strokeWidth={2.4} />
                  </span>
                  <span className="text-xs font-mono text-neutral-400">{`0${step.n}`}</span>
                </div>
                <h3 className="font-semibold text-sm text-neutral-900 mb-1.5">{step.title}</h3>
                <p className="text-xs text-neutral-500 leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>

          <p className="text-center text-xs text-neutral-400 font-mono mt-10">
            FastEmbed local · pgvector + tsvector · OpenAI Agents SDK · SSE audio streaming
          </p>
        </div>
      </section>

      {/* ─── Features bento ─── */}
      <section id="features" className="bg-[#fafafa]">
        <div className="max-w-6xl mx-auto px-6 py-16 sm:py-24">
          <div className="text-center mb-12">
            <span className="text-xs uppercase tracking-widest text-neutral-400 font-mono">What makes it different</span>
            <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-2">
              Engineered for production, not demos
            </h2>
          </div>

          <div className="grid gap-4 md:grid-cols-3 auto-rows-[180px]">
            {FEATURES.map((f, i) => (
              <article
                key={i}
                className={`relative rounded-2xl bg-white border border-neutral-200/80 p-6 card-shadow hover-lift ${f.span ?? ""}`}
              >
                <div className="flex items-start justify-between mb-4">
                  <span className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-neutral-100 text-neutral-700">
                    <f.icon size={16} strokeWidth={2.4} />
                  </span>
                  <Layers size={14} className="text-neutral-300" />
                </div>
                <h3 className="font-semibold text-base mb-1.5">{f.title}</h3>
                <p className="text-sm text-neutral-500 leading-relaxed">{f.desc}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Tech stack ─── */}
      <section id="stack" className="border-t border-neutral-200/70 bg-white">
        <div className="max-w-4xl mx-auto px-6 py-16 sm:py-20 text-center">
          <span className="text-xs uppercase tracking-widest text-neutral-400 font-mono">Stack</span>
          <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-2 mb-8">
            Built with
          </h2>
          <div className="flex flex-wrap justify-center gap-2">
            {STACK.map((tech) => (
              <span
                key={tech}
                className="inline-flex items-center px-3.5 py-1.5 rounded-full bg-neutral-50 border border-neutral-200 text-sm text-neutral-700"
              >
                {tech}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Final CTA ─── */}
      <section className="border-t border-neutral-200/70 bg-gradient-to-b from-[#fafafa] to-white">
        <div className="max-w-3xl mx-auto px-6 py-20 text-center">
          <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight">
            Ready to talk to your documents?
          </h2>
          <p className="text-neutral-600 mt-3 max-w-xl mx-auto">
            Upload a PDF, pick a voice, ask anything. The demo runs on a 5-minute session.
          </p>
          <Link
            href="/app"
            className="inline-flex items-center gap-2 mt-8 px-6 py-3 rounded-full bg-neutral-900 text-white text-sm font-semibold hover:bg-neutral-800 transition-all hover:-translate-y-0.5 shadow-lg shadow-neutral-900/10"
          >
            <Mic size={16} /> Open the app
          </Link>
        </div>
      </section>

      {/* ─── Footer ─── */}
      <footer className="border-t border-neutral-200/70 bg-white">
        <div className="max-w-6xl mx-auto px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-neutral-500">
          <p>Built by Pedro Gomes — full-stack AI engineer.</p>
          <div className="flex items-center gap-4">
            <a
              href="https://github.com/devpedrogomes/voice_rag"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-neutral-900 transition-colors inline-flex items-center gap-1.5"
            >
              <Github size={14} /> GitHub
            </a>
            <Link href="/app" className="hover:text-neutral-900 transition-colors">
              Live demo →
            </Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
