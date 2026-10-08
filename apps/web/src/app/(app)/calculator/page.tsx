import { PremiumCalculator } from "@/components/insurers/calculator";

export const metadata = { title: "Premium calculator" };

export default function CalculatorPage() {
  return (
    <div className="grid gap-5">
      <h1 className="text-3xl">Premium calculator</h1>
      <PremiumCalculator />
    </div>
  );
}
