/** @type {import('next').NextConfig} */
// NEXT_DIST_DIR permite builds/servidores de teste em paralelo sem sobrescrever o .next do `npm run dev` de quem está desenvolvendo.
// Nesse caso o Next também reescreve o tsconfig; NEXT_TSCONFIG aponta para uma cópia descartável (tsconfig.iso.json, ignorada pelo git).
export default {
  reactStrictMode: true,
  distDir: process.env.NEXT_DIST_DIR || ".next",
  ...(process.env.NEXT_TSCONFIG ? { typescript: { tsconfigPath: process.env.NEXT_TSCONFIG } } : {}),
};
