import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://voicerag.pgdev.com.br"),
  title: "Voice RAG — ask out loud, hear the cited answer",
  description:
    "Speak your question, get a spoken answer with the source cited. Hybrid retrieval (pgvector + full-text) with reranking, and TTS that starts talking while the model is still writing.",
  authors: [{ name: "Pedro Gomes", url: "https://gomio.com.br" }],
  creator: "Pedro Gomes",
  // Sem openGraph/twitter o link vira URL crua no LinkedIn, no WhatsApp e no
  // Upwork — que e onde estas demos de facto circulam.
  openGraph: {
    type: "website",
    url: "https://voicerag.pgdev.com.br",
    siteName: "Gomio",
    locale: "en_US",
    title: "Voice RAG — ask out loud, hear the cited answer",
    description:
      "Speak your question, get a spoken answer with the source cited. Hybrid retrieval (pgvector + full-text) with reranking, and TTS that starts talking while the model is still writing.",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "Voice RAG — voice-first document assistant" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Voice RAG — ask out loud, hear the cited answer",
    description:
      "Speak your question, get a spoken answer with the source cited. Hybrid retrieval (pgvector + full-text) with reranking, and TTS that starts talking while the model is still writing.",
    images: ["/og.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
        <Toaster />
      </body>
    </html>
  );
}
