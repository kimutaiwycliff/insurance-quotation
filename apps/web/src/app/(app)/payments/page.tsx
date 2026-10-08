import { MpesaQueue } from "@/components/billing/mpesa-queue";
import { PaymentsList } from "@/components/billing/payments-list";

export const metadata = { title: "Payments" };

export default function PaymentsPage() {
  return (
    <div className="grid gap-5">
      <div>
        <h1 className="text-3xl">Payments</h1>
        <p className="mt-1 text-muted-foreground">Money clients paid into your accounts, with a numbered receipt for each.</p>
      </div>
      <MpesaQueue />
      <PaymentsList />
    </div>
  );
}
