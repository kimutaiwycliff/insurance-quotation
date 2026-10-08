import { RenewalsBoard } from "@/components/policies/renewals-board";

export const metadata = { title: "Renewals" };

export default async function RenewalsPage({ searchParams }: { searchParams: Promise<{ focus?: string }> }) {
  const { focus } = await searchParams;
  return <RenewalsBoard focus={focus} />;
}
