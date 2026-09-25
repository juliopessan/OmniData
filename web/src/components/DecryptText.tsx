"use client";

import { useEffect, useRef } from "react";

/** Efeito de "decrypt": cada caractere começa num símbolo aleatório e trava no caractere real, da esquerda
 * pra direita, com atraso e jitter por caractere (irregular, não metronômico). Só herda cor e fonte do
 * elemento pai (currentColor) — nenhuma cor ou fonte nova. Respeita prefers-reduced-motion (resolve na hora,
 * sem nenhum quadro de scramble) e mantém o texto real, limpo, pra leitor de tela. */

const POOL = "#%&@$?!*+=/{}[]<>~^";

function mulberry32(seed: number) {
  let s = seed;
  return () => {
    s |= 0; s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function DecryptText({
  text, className, startDelay = 0, stagger = 34, speed = 45, seed = 1,
}: { text: string; className?: string; startDelay?: number; stagger?: number; speed?: number; seed?: number }) {
  const charsRef = useRef<(HTMLSpanElement | null)[]>([]);

  useEffect(() => {
    const chars = text.split("");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      charsRef.current.forEach((el, i) => { if (el) el.textContent = chars[i]; });
      return;
    }
    const rand = mulberry32(seed);
    const locks = chars.map((_, i) => Math.max(0, startDelay + i * stagger + (rand() * stagger - stagger / 2)));
    const nextGlyphAt = new Array(chars.length).fill(0);
    const locked = new Array(chars.length).fill(false);
    const t0 = performance.now();
    let raf = 0;

    charsRef.current.forEach((el, i) => {
      if (!el) return;
      if (chars[i] === " ") { el.textContent = " "; locked[i] = true; return; }
      el.textContent = POOL[Math.floor(rand() * POOL.length)];
      el.classList.add("dx-scramble");
    });

    const tick = (now: number) => {
      const elapsed = now - t0;
      let allLocked = true;
      chars.forEach((c, i) => {
        if (locked[i]) return;
        const el = charsRef.current[i];
        if (!el) return;
        allLocked = false;
        if (elapsed >= locks[i]) {
          locked[i] = true;
          el.textContent = c;
          el.classList.remove("dx-scramble");
          el.classList.add("dx-lock");
        } else if (elapsed >= nextGlyphAt[i]) {
          el.textContent = POOL[Math.floor(rand() * POOL.length)];
          nextGlyphAt[i] = elapsed + speed + rand() * 35;
        }
      });
      if (!allLocked) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [text, startDelay, stagger, speed, seed]);

  return (
    <span className={className}>
      <span aria-hidden="true">
        {text.split("").map((c, i) => (
          <span key={i} ref={(el) => { charsRef.current[i] = el; }} className="dx-char">{c === " " ? " " : c}</span>
        ))}
      </span>
      <span className="sr-only">{text}</span>
    </span>
  );
}
