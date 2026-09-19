"use client";
import { useState } from "react";
import { Chat, type ChatMsg } from "./Chat";

type Feature = { theme: string; title: string; body: string; msgs: ChatMsg[]; who: string };

const FEATURES: Feature[] = [
  { theme: "A equipe", title: "Um pedido com dois assuntos, uma resposta só.", body: "Orion divide o trabalho entre os especialistas e você recebe tudo numa mensagem, cada parte assinada por quem cuidou dela.", who: "Ana Souza", msgs: [
    { me: true, text: "como estou na meta e anota na Acme que o CFO aprovou" },
    { text: <><b>Vega</b>: Você está em <b>97,8%</b> da meta. Falta <b>R$ 9.000</b>.<br /><br /><b>Lyra</b>: Registrei ✅ <b>Nota</b> em <b>Acme – Renovação</b>.</>, buttons: ["Editar", "Desfazer"] } ] },
  { theme: "A equipe", title: "Chame pelo nome, como faria com uma pessoa.", body: "“Vega, ...” vai direto para a analista de metas. Se o assunto não for dela, ela diz quem cuida. Diga “me chama de Rê” e a equipe inteira passa a te chamar assim.", who: "Bruno Lima", msgs: [
    { me: true, text: "Altair, como estou na meta?" },
    { text: <><b>Altair</b>: Isso não é comigo. Fale com <b>Vega</b> (Analista de Metas): “Vega, como estou na meta?”.</> } ] },
  { theme: "A equipe", title: "Um auditor que diz quando não dá para confiar.", body: "Argus mostra a cobertura de próximo passo e de motivo de perda, e avisa quando a amostra é pequena demais para comparar.", who: "Carla Mendes", msgs: [
    { me: true, text: "Argus, posso confiar nesse win rate?" },
    { text: <><b>Argus</b>: 12 negócios abertos; 92% com próximo passo. Perdas em 24 meses: 5, 40% com motivo estruturado (meta: 80%). Análises por motivo ainda não são confiáveis.</> } ] },
  { theme: "Perguntas", title: "“Como estou na meta?” Resposta em segundos.", body: "Atingimento, gap, dias restantes e cobertura de pipeline vs. necessária. Se a amostra é pequena, o assistente avisa em vez de comparar.", who: "Ana Souza", msgs: [
    { me: true, text: "como to na meta?" },
    { text: <>Você está em <b>91,0%</b> da meta de setembro. Faltam <b>R$ 9.000</b> e 11 dias. Cobertura: 3,2x (necessária: 1,7x).</> } ] },
  { theme: "Perguntas", title: "Sua manhã, priorizada.", body: "Às 7h30, os cinco negócios que mais merecem atenção, reuniões do dia e status da meta. Um toque abre a conversa.", who: "Bruno Lima", msgs: [
    { text: <>Bom dia, Bruno! Você tem <b>5</b> negócios prioritários hoje.</>, buttons: ["Ver meu dia"] },
    { text: <>1. <b>Lume Saúde – Expansão</b> · parado há 24 dias · sem próximo passo</> } ] },
  { theme: "Ações", title: "Nota e tarefa sem abrir o CRM.", body: "Notas e tarefas executam na hora, com recibo. Desfazer vale por 24h e nunca sobrescreve a alteração de um colega.", who: "Carla Mendes", msgs: [
    { me: true, text: "nota na Casa Verde: CFO aprovou o escopo" },
    { text: <>Registrei ✅ <b>Nota</b> em <b>Casa Verde – Contrato</b>.</>, buttons: ["Editar", "Desfazer"] } ] },
  { theme: "Ações", title: "Mudanças sensíveis pedem confirmação.", body: "Etapa, data de fechamento e valor passam por Confirmar / Ajustar / Cancelar. Confirmar duas vezes executa uma só.", who: "Diego Rocha", msgs: [
    { me: true, text: "move a Pixel Foods pra negociação" },
    { text: <>Mover <b>Pixel Foods – Renovação</b> de <b>Proposta</b> para <b>Negociação</b>?</>, buttons: ["Confirmar", "Ajustar", "Cancelar"] } ] },
  { theme: "Alertas", title: "Só o que importa, sem virar spam.", body: "Máximo de 5 por dia, silêncio das 20h às 7h, uma vez por negócio a cada 3 dias e soneca com um toque.", who: "Ana Souza", msgs: [
    { text: <><b>Vértice Log – Expansão</b> está sem atividade há 12 dias e a data de fechamento venceu.</>, buttons: ["Ver deal", "Soneca 3 dias"] } ] },
  { theme: "Ganhos e perdas", title: "Motivo de perda com um toque.", body: "Quando um negócio é perdido, o assistente pergunta o motivo numa lista curta. Sem formulário, sem “Outro” genérico.", who: "Bruno Lima", msgs: [
    { text: <><b>Cais Digital</b> foi marcado como perdido. Qual o motivo?</>, buttons: ["Preço", "Concorrente", "Sem decisão"] },
    { me: true, text: "Concorrente" }, { text: "Anotado ✅ Obrigado!" } ] },
  { theme: "Gestão", title: "Digest do time e previsão de meta.", body: "Gestores veem números agregados, probabilidade de bater a meta (p10/p50/p90) e os negócios que mais moveram a previsão.", who: "Gestor", msgs: [
    { me: true, text: "digest do time" },
    { text: <>Time em <b>97,8%</b> da meta. Win rate <b>58,3%</b> (IC 95%: 32%–81%) — amostra pequena, evite ranking.</> } ] },
];

const THEMES = ["Todos", ...Array.from(new Set(FEATURES.map((f) => f.theme)))];

export function FeatureList() {
  const [theme, setTheme] = useState("Todos");
  const list = FEATURES.filter((f) => theme === "Todos" || f.theme === theme);
  return (
    <div>
      <div className="chips" role="group" aria-label="Filtrar por tema">
        {THEMES.map((t) => <button key={t} className="chip" aria-pressed={theme === t} onClick={() => setTheme(t)}>{t}</button>)}
      </div>
      <div className="feat-group">
        {list.map((f) => (
          <article key={f.title} className="feat">
            <div className="stack">
              <span className="tag" style={{ alignSelf: "flex-start" }}>{f.theme}</span>
              <h2 className="h3" style={{ fontSize: 24 }}>{f.title}</h2>
              <p className="body">{f.body}</p>
            </div>
            <Chat title={f.who} msgs={f.msgs} />
          </article>
        ))}
      </div>
    </div>
  );
}
