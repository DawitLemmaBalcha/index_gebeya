// NB-49: the shared data table of the ops console kit (Rule 1.2).
// columns: [{key, label, render?}], data: rows, loading + empty slot.

export default function OpsTable({ columns, data = [], loading = false, empty = null }) {
  if (loading) {
    return (
      <div className="p-6 text-center text-sm text-gray-400" data-testid="ops-table-loading">
        Loading…
      </div>
    );
  }
  if (data.length === 0) {
    return empty || (
      <div className="p-6 text-center text-sm text-gray-400">No data</div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500"
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {data.map((row, i) => (
            <tr key={row.id ?? i} className="hover:bg-gray-50">
              {columns.map((col) => (
                <td key={col.key} className="px-3 py-2 text-gray-700">
                  {col.render ? col.render(row) : String(row[col.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
