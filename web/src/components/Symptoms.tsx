"use client";

import { useReveal } from "@/lib/useReveal";

const ROWS: [string, string, string][] = [
  ["Lyra", "O vendedor atualiza o CRM na sexta à noite, se lembrar.", "Lyra registra a nota ou a tarefa na hora, por texto ou áudio, com recibo e Desfazer por 24h."],
  ["Altair", "O negócio esfria e ninguém vê até o fim do trimestre.", "Altair aponta o que está parado, sem próximo passo ou com a data vencida, do mais valioso ao menos."],
  ["Vega", "O forecast é discutido com números que ninguém consegue defender.", "Vega só usa número calculado em SQL. Nada de conta feita pelo modelo."],
  ["Argus", "A amostra é pequena e todo mundo compara vendedores mesmo assim.", "Argus avisa quando não dá para confiar, e o OmniData suprime o ranking abaixo de 20 fechados."],
];

/** As 4 linhas "antes → depois" entram em cascata ao rolar, e a frase do "antes" ganha um risco animado
 * (mesmo dispositivo da StoryFilm: uma linha que varre da esquerda, não um text-decoration estático). */
export function Symptoms() {
  const { ref, on } = useReveal<HTMLDivElement>();
  return (
    <div ref={ref} className="symptoms" data-reveal={on ? "on" : "idle"}>
      {ROWS.map(([who, before, after], i) => (
        <div key={who} className="symptom" style={{ "--i": i } as React.CSSProperties}>
          <p className="before">{before}</p>
          <span className="arrow" aria-hidden="true">→</span>
          <p className="after"><b>{who}:</b> {after}</p>
        </div>
      ))}
    </div>
  );
}
