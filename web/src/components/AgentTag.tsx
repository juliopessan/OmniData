import Link from "next/link";
import { TEAM } from "@/lib/team";

/** Quem cuida de cada insight: o cadastro da equipe vem do back-end (team.json). */
export function AgentTag({ k }: { k: string }) {
  const m = TEAM.members.find((x) => x.key === k)!;
  return (
    <Link href="/dashboard/equipe" className="agent-tag" title={m.tagline}>
      <span className="mono-tile sm" aria-hidden="true">{m.name.slice(0, 2)}</span>
      <span><b>{m.name}</b> · {m.title}</span>
    </Link>
  );
}
