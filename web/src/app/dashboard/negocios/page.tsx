import type { Metadata } from "next";
import { NegociosView } from "@/components/DashViews";

export const metadata: Metadata = { title: "Negócios" };

export default function Negocios() {
  return <NegociosView />;
}
