import data from "./team.json";

export interface Member { key: string; name: string; title: string; tagline: string; tools: string[]; examples: string[] }
export const TEAM: { name: string; tagline: string; members: Member[] } = data;
