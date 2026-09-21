import path from "node:path";
import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
// NEXT_DIST_DIR permite builds/servidores de teste em paralelo sem sobrescrever o .next do `npm run dev` de quem está desenvolvendo.
// Nesse caso o Next também reescreve o tsconfig; NEXT_TSCONFIG aponta para uma cópia descartável (tsconfig.iso.json, ignorada pelo git).

// Política de conteúdo (só em produção: o modo de desenvolvimento precisa de eval e WebSocket para o hot reload).
// - script/style 'unsafe-inline': o Next injeta scripts e o app usa atributos style; um CSP com nonce exigiria middleware (melhoria futura).
// - connect-src: a página Datasets chama a API cuja URL o usuário informa. Aceita HTTPS ou localhost; http em outro host é bloqueado,
//   o que também impede o token de admin de sair em texto puro por engano.
// - frame-ancestors 'none': ninguém pode embutir o painel em outro site (clickjacking sobre a tela do token).
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self' https: http://localhost:* http://127.0.0.1:*",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  ...(process.env.NODE_ENV === "production" ? [{ key: "Content-Security-Policy", value: CSP }] : []),
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
  // HSTS não é definido aqui de propósito: a Vercel já envia max-age=63072000; includeSubDomains; preload, e um valor nosso o enfraqueceria.
];

// Raiz do projeto fixa: sem isso o Next escolhe o lockfile mais alto que achar (ex.: um bun.lock solto na pasta do usuário) e avisa.
const root = path.dirname(fileURLToPath(import.meta.url));

export default {
  reactStrictMode: true,
  outputFileTracingRoot: root,
  poweredByHeader: false,
  distDir: process.env.NEXT_DIST_DIR || ".next",
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  ...(process.env.NEXT_TSCONFIG ? { typescript: { tsconfigPath: process.env.NEXT_TSCONFIG } } : {}),
};
