import Link from "next/link";

import { PoliciesList } from "@/components/policies/policies-list";
import { Button } from "@/components/ui/button";

export const metadata = { title: "Policies" };

export default function PoliciesPage() {
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl">Policies</h1>
          <p className="mt-1 text-muted-foreground">To add an existing policy, open the client and choose Add policy.</p>
        </div>
        <Button asChild variant="outline"><Link href="/renewals">Renewals</Link></Button>
      </div>
      <PoliciesList />
    </div>
  );
}
