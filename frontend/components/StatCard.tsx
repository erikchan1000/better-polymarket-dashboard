interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
  valueClassName?: string;
}

export function StatCard({ label, value, hint, valueClassName }: StatCardProps) {
  return (
    <div className="rounded-xl border border-surface-700 bg-surface-800/60 px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${valueClassName ?? "text-gray-100"}`}>
        {value}
      </div>
      {hint ? <div className="mt-0.5 text-xs text-gray-500">{hint}</div> : null}
    </div>
  );
}
