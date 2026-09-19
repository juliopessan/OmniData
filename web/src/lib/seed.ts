// Dados sintéticos (equivalente ao `omnidata dev seed`). Nenhum PII real.
export type Stage = "Qualificação" | "Proposta" | "Negociação" | "Ganho" | "Perdido";

export interface Deal {
  id: string;
  name: string;
  owner: string;
  stage: Stage;
  amount: number;
  daysInStage: number;
  nextStep: boolean;
  quietDays: number;
  overdue: boolean;
  reason?: string | null; // só para Perdido; null = sem motivo estruturado
}

export const STAGE_PROB: Record<Stage, number> = {
  Qualificação: 0.2,
  Proposta: 0.4,
  Negociação: 0.7,
  Ganho: 1,
  Perdido: 0,
};

// p75 de dias por etapa (gold.stage_benchmarks, sintético)
export const STAGE_P75: Record<string, number> = { Qualificação: 10, Proposta: 14, Negociação: 15 };

export const MIN_N_RANKING = 20;
export const PERIOD = "setembro de 2026";

export const owners = [
  { id: "ana", name: "Ana Souza", quota: 100000 },
  { id: "bruno", name: "Bruno Lima", quota: 100000 },
  { id: "carla", name: "Carla Mendes", quota: 100000 },
  { id: "diego", name: "Diego Rocha", quota: 100000 },
];

const d = (
  id: string, name: string, owner: string, stage: Stage, amount: number,
  daysInStage = 0, nextStep = true, quietDays = 0, overdue = false, reason?: string | null,
): Deal => ({ id, name, owner, stage, amount, daysInStage, nextStep, quietDays, overdue, reason });

export const deals: Deal[] = [
  d("D-1001", "Acme – Renovação", "Ana Souza", "Negociação", 84000, 9, true, 2),
  d("D-1002", "Vértice Log – Expansão", "Ana Souza", "Proposta", 46000, 18, false, 12, true),
  d("D-1003", "Nuvem Sul – Novo", "Bruno Lima", "Qualificação", 22000, 5, true, 1),
  d("D-1004", "Grupo Alfa – Piloto", "Bruno Lima", "Proposta", 61000, 21, false, 11),
  d("D-1005", "Casa Verde – Contrato", "Carla Mendes", "Negociação", 120000, 16, true, 3, true),
  d("D-1006", "Orbita Tech – Upsell", "Carla Mendes", "Proposta", 38000, 7, true, 4),
  d("D-1007", "Mercato – Novo", "Diego Rocha", "Qualificação", 18000, 12, false, 14),
  d("D-1008", "Pixel Foods – Renovação", "Diego Rocha", "Negociação", 72000, 6, true, 1),
  d("D-1009", "Ferro & Cia – Novo", "Ana Souza", "Qualificação", 27000, 4, true, 2),
  d("D-1010", "Lume Saúde – Expansão", "Bruno Lima", "Negociação", 95000, 24, false, 10, true),
  d("D-1011", "Tri Energia – Piloto", "Carla Mendes", "Proposta", 54000, 10, true, 5),
  d("D-1012", "Beta Educação – Novo", "Diego Rocha", "Proposta", 33000, 19, true, 6),
  d("D-0901", "Kappa Retail", "Ana Souza", "Ganho", 68000),
  d("D-0902", "Delta Auto", "Ana Souza", "Ganho", 52000),
  d("D-0903", "Sol Imóveis", "Bruno Lima", "Ganho", 41000),
  d("D-0904", "Rio Pay", "Carla Mendes", "Ganho", 88000),
  d("D-0905", "Zênite", "Bruno Lima", "Ganho", 36000),
  d("D-0906", "Marés", "Diego Rocha", "Ganho", 47000),
  d("D-0907", "Onda Média", "Carla Mendes", "Ganho", 59000),
  d("D-0801", "Fênix ETL", "Ana Souza", "Perdido", 30000, 0, true, 0, false, "price"),
  d("D-0802", "Prisma", "Bruno Lima", "Perdido", 44000, 0, true, 0, false, "competitor"),
  d("D-0803", "Vento Norte", "Carla Mendes", "Perdido", 26000, 0, true, 0, false, null),
  d("D-0804", "Ágata", "Diego Rocha", "Perdido", 19000, 0, true, 0, false, null),
  d("D-0805", "Cais Digital", "Bruno Lima", "Perdido", 51000, 0, true, 0, false, null),
];
