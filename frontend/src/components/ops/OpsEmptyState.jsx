// NB-49: shared empty-state block (Rule 1.2) — used for "Coming soon"
// section stubs and data-less views.

export default function OpsEmptyState({ title, hint }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 bg-gray-50 p-10 text-center">
      <div className="text-2xl mb-2">🗂️</div>
      <div className="font-medium text-gray-700">{title}</div>
      {hint && <div className="mt-1 text-sm text-gray-400">{hint}</div>}
    </div>
  );
}
