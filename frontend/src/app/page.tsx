export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">NFA Studio</h1>
      <p className="text-slate-600 dark:text-slate-400">
        Describe a regular language in plain English and get a verified ε-NFA.
      </p>
      <p className="font-mono text-sm text-slate-500">
        N = (Q, Σ, δ, q₀, F) · δ : Q × (Σ ∪ {"{ε}"}) → 2<sup>Q</sup> · ∅ ≠ {"{ε}"}
      </p>
    </main>
  );
}
