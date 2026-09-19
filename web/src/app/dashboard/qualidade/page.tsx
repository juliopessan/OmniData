import type { Metadata } from "next";
import { QualidadeView } from "@/components/DashViews";

export const metadata: Metadata = { title: "Qualidade dos dados" };

export default function Qualidade() {
  return <QualidadeView />;
}
