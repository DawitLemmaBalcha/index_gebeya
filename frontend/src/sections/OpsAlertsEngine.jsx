// NB-58/NB-59: Section 5 — Alerts & Notifications → the engine cockpit.
// Two sub-views: Diagnostics (per-item decision traces, Rule 5) and Actions
// (engine verbs: re-run, retry, trigger, Rule 6). Tabs are state-based —
// no router sub-routes (shell contract, ops-console.md Rule 1.6).

import { useState } from 'react';
import OpsDiagnostics from './OpsDiagnostics';
import OpsActions from './OpsActions';

const TABS = [
  { id: 'diagnostics', label: 'Diagnostics' },
  { id: 'actions', label: 'Actions' },
];

export default function OpsAlertsEngine({ setToast }) {
  const [tab, setTab] = useState('diagnostics');

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-gray-800">Alerts & Notifications</h2>

      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-t border-b-2 px-3 py-1.5 text-sm ${
              tab === t.id
                ? 'border-blue-600 font-medium text-blue-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div hidden={tab !== 'diagnostics'} data-testid="ops-diagnostics-pane">
        <OpsDiagnostics setToast={setToast} />
      </div>
      <div hidden={tab !== 'actions'} data-testid="ops-actions-pane">
        <OpsActions setToast={setToast} />
      </div>
    </div>
  );
}
