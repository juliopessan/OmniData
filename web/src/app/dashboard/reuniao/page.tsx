import type { Metadata } from "next";
import { ReuniaoView } from "@/components/ReuniaoView";

export const metadata: Metadata = { title: "Reunião de vendas" };

export default function Reuniao() {
  return <ReuniaoView />;
}
