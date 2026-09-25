"use client";

import { useEffect, useRef, useState } from "react";

/** Marca o container como "entrou na tela" uma vez (data-reveal="on"), pra CSS animar os filhos em cascata
 * (globals.css: `[data-reveal]`). Sem movimento: já entra visível, sem esperar o scroll. */
export function useReveal<T extends HTMLElement>(threshold = 0.2) {
  const ref = useRef<T>(null);
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setOn(true); return; }
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setOn(true); io.disconnect(); } }, { threshold });
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);
  return { ref, on };
}
