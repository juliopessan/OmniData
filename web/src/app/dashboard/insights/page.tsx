import type { Metadata } from "next";
import { InsightsView } from "@/components/InsightsView";

export const metadata: Metadata = { title: "Insights" };

export default function Insights() {
  return <InsightsView />;
}
