/** @type {import('next').NextConfig} */
// NEXT_DIST_DIR permite builds/servidores de teste em paralelo sem sobrescrever o .next do `npm run dev` de quem está desenvolvendo.
export default { reactStrictMode: true, distDir: process.env.NEXT_DIST_DIR || ".next" };
