import type { Metadata } from "next";
import { Inter_Tight, Instrument_Serif, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const display = Inter_Tight({ subsets: ["latin"], weight: ["400", "500", "700", "800"], variable: "--font-display" });
const voice = Instrument_Serif({ subsets: ["latin"], weight: "400", style: "italic", variable: "--font-voice" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: { default: "OmniData — inteligência de vendas no WhatsApp", template: "%s · OmniData" },
  description: "Plataforma de dados que centraliza o HubSpot e entrega inteligência de vendas no WhatsApp do vendedor.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className={`${display.variable} ${voice.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
