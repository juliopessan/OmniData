/** Decisões sugeridas para a reunião de vendas. Cada uma vem de uma REGRA fixa aplicada a números medidos (sem LLM):
 *  a tela mostra a regra e a evidência ao lado da sugestão, para que ninguém confunda "medido" com "sugerido". */
import type { Analysis } from "./insights";
import type { FixQueue } from "./hygiene";
import type { Deal } from "./seed";
import { brl, pct, statusOf } from "./metrics";

export interface Decision {
  id: string; priority: number; title: string;
  rule: string;            // a regra que disparou, com o limite
  evidence: string[];      // números medidos
  action: string;          // a sugestão (afirmação, não medição)
  agent: string;           // quem cuida do assunto (chave em team.json)
  caution?: string;        // limite da evidência (amostra pequena, pode ser do export…)
}

export const LIMITS = { concentration: 0.4, noAmount: 0.3, demandShare: 0.2, erpMinDeals: 5, lostMinN: 5, lostWithReason: 0.8, painsCoverage: 0.3, painsMinN: 20 };

const n0 = (n: number) => n.toLocaleString("pt-BR");
const short = (s: string, k = 46) => (s.length > k ? `${s.slice(0, k - 1)}…` : s);

export function decide(deals: Deal[], a: Analysis, q: FixQueue): Decision[] {
  const out: Decision[] = [];
  const add = (d: Omit<Decision, "priority">) => out.push({ ...d, priority: out.length + 1 });
  const open = deals.filter((d) => statusOf(d) === "open");
  const total = open.reduce((s, d) => s + d.amount, 0);
  const issue = (code: string) => q.issues.find((i) => i.code === code);

  // 1. Um negócio concentra o pipeline
  const top = [...open].sort((x, y) => y.amount - x.amount)[0];
  if (top && total > 0 && top.amount / total >= LIMITS.concentration) {
    add({ id: "concentration", title: "Proteger o negócio que sustenta o pipeline",
      rule: `Um negócio concentra ${pct(LIMITS.concentration, 0)} ou mais do valor em aberto.`,
      evidence: [`${short(top.name)}: ${brl(top.amount)} de ${brl(total)} (${pct(top.amount / total, 0)})`],
      action: "Definir dono, próximo passo e data para este negócio ainda hoje; sem ele, a previsão desmonta.", agent: "altair" });
  }
  // 2. Valor faltando
  const na = issue("no_amount");
  if (na && na.share >= LIMITS.noAmount) {
    add({ id: "value_gap", title: "Qualificar o valor antes de falar de previsão",
      rule: `${pct(LIMITS.noAmount, 0)} ou mais dos negócios abertos estão sem valor.`,
      evidence: [`${n0(na.deals)} de ${n0(q.openDeals)} abertos sem valor (${pct(na.share, 0)})`, `Só ${n0(q.openDeals - na.deals)} têm valor, somando ${brl(total)}`],
      action: "Cada vendedor informa uma estimativa de valor para os seus negócios, começando pelos de maior potencial.", agent: "polaris" });
  }
  // 3. Demanda dominante
  const withDemand = a.demand.reduce((s, g) => s + g.deals, 0);
  const d0 = a.demand[0];
  if (d0 && withDemand && d0.deals / withDemand >= LIMITS.demandShare) {
    add({ id: "demand_focus", title: `Preparar a oferta de ${d0.key}`,
      rule: `Um tipo de demanda concentra ${pct(LIMITS.demandShare, 0)} ou mais dos negócios que têm demanda identificada.`,
      evidence: [`${d0.key}: ${n0(d0.deals)} negócios (${pct(d0.deals / withDemand, 0)})`, d0.closed ? `Ganho: ${pct(d0.winRate ?? 0, 0)} em ${d0.closed} ${d0.closed === 1 ? "fechado" : "fechados"}` : "Nenhum negócio fechado nesta demanda"],
      action: `Reunir material e um caso de uso para ${d0.key}, e confirmar a conversão antes de priorizar mais esforço.`, agent: "altair",
      caution: d0.lowN ? "Poucos negócios fechados: a conversão é só indicativa." : undefined });
  }
  // 4. ERP que mais aparece
  const erp = a.systems.erp.find((s) => !/^ERP\b/i.test(s.system));
  if (erp && erp.deals >= LIMITS.erpMinDeals) {
    add({ id: "erp_focus", title: `Preparar argumentos e integração para ${erp.system}`,
      rule: `Um ERP específico aparece em ${LIMITS.erpMinDeals} negócios ou mais.`,
      evidence: [`${erp.system}: citado em ${n0(erp.deals)} negócios (${pct(erp.deals / a.coverage.deals, 0)} do total)`],
      action: `Levantar como o produto se integra ao ${erp.system} e levar isso para as conversas em andamento.`, agent: "altair",
      caution: "Conta o que foi anotado nas notas, não o mercado todo." });
  }
  // 5. Motivo de perda
  const lostWith = a.coverage.lostWithReason;
  if (a.lost >= LIMITS.lostMinN && lostWith !== null && lostWith < LIMITS.lostWithReason) {
    add({ id: "loss_reason", title: "Registrar o motivo de cada perda",
      rule: `Há ${LIMITS.lostMinN}+ negócios perdidos e menos de ${pct(LIMITS.lostWithReason, 0)} têm motivo.`,
      evidence: [`${n0(Math.round(lostWith * a.lost))} de ${n0(a.lost)} perdidos têm motivo (${pct(lostWith, 0)}); meta ${pct(LIMITS.lostWithReason, 0)}`],
      action: "Passar a exigir o motivo ao marcar um negócio como perdido; sem isso, análise por motivo não é confiável.", agent: "argus" });
  }
  // 6. Dores
  const pc = a.coverage.withPain;
  if (pc !== null && pc < LIMITS.painsCoverage) {
    add({ id: "pains_coverage", title: "Registrar a dor da conta em toda reunião",
      rule: `Menos de ${pct(LIMITS.painsCoverage, 0)} dos negócios têm dor registrada nas notas.`,
      evidence: [`${n0(a.pains.withPain)} de ${n0(a.coverage.deals)} negócios com dor registrada (${pct(pc, 0)})`],
      action: "Ao fim de cada reunião com o cliente, anotar a dor validada (por exemplo, “Dor validada: …”) para o time enxergar padrões.", agent: "lyra" });
  } else if (!a.pains.lowN && a.pains.items[0]) {
    const p = a.pains.items[0];
    add({ id: "top_pain", title: `Levar a dor “${short(p.pain, 60)}” para a abordagem`,
      rule: `Há ${LIMITS.painsMinN}+ negócios com dor registrada; a mais citada vira pauta.`,
      evidence: [`${short(p.pain, 70)}: ${n0(p.deals)} negócios (${pct(p.share, 0)} dos que têm dor)`],
      action: "Incluir essa dor no roteiro de descoberta e no material de abordagem.", agent: "lyra" });
  }
  // 7. Datas de fechamento e próximo passo (sistêmico = pode ser do export, não do vendedor)
  for (const [code, sys, fix, ask] of [
    ["close_date_past", "Conferir a origem das datas de fechamento", "Reagendar a data de fechamento", "Verificar no HubSpot se a data é um padrão do CRM; depois, definir a data real nos negócios com valor."],
    ["no_next_step", "Conferir a origem do campo Próxima atividade", "Definir o próximo passo", "Verificar se o export traz esse campo; depois, criar uma tarefa com data nos negócios com valor."],
  ] as const) {
    const i = issue(code);
    if (!i) continue;
    add({ id: code, title: i.systemic ? sys : `${fix} nos negócios que estão sem`,
      rule: i.systemic ? "A lacuna aparece em 90% ou mais dos negócios abertos, o que aponta mais para o export ou o CRM do que para hábito." : "A lacuna aparece em parte dos negócios abertos.",
      evidence: [`${i.label}: ${n0(i.deals)} de ${n0(q.openDeals)} abertos (${pct(i.share, 0)})`],
      action: i.systemic ? ask : `${fix} nos ${n0(i.deals)} negócios listados; comece pelos de maior valor.`, agent: "polaris",
      caution: i.systemic ? "Não cobre cada vendedor antes de conferir a origem do dado." : undefined });
  }
  // 8. Limpeza do gestor
  if (q.managerInactive.length || q.managerDuplicates.length) {
    add({ id: "manager_cleanup", title: "Limpeza que só o gestor resolve",
      rule: "Há negócios com dono desativado ou nomes possivelmente duplicados.",
      evidence: [q.managerInactive.length ? `${n0(q.managerInactive.length)} negócio(s) com dono desativado` : "", q.managerDuplicates.length ? `${n0(q.managerDuplicates.length)} nome(s) possivelmente duplicado(s)` : ""].filter(Boolean),
      action: "Redistribuir os negócios de donos desativados e conferir se as duplicatas devem ser mescladas ou arquivadas.", agent: "polaris" });
  }
  return out;
}
