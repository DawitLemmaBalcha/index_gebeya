// NB-49: the ops console shell (ops-console.md §1, Rule 1.6).
// Full standalone page: left-rail nav with ALL ten sections, "Coming soon"
// stubs for unimplemented ones. Tabs are state-based — no router
// sub-routes. Every section uses the shared kit (Rule 1.2).

import { useState } from 'react';
import { useOpsAuth } from '../hooks/useOpsAuth';
import OpsEmptyState from '../components/ops/OpsEmptyState';
import OpsToast from '../components/ops/OpsToast';
import OpsOverview from '../sections/OpsOverview';
import OpsMonetization from '../sections/OpsMonetization';
import OpsSettings from '../sections/OpsSettings';
import OpsAudit from '../sections/OpsAudit';
import OpsPayments from '../sections/OpsPayments';
import OpsTools from '../sections/OpsTools';

const SECTIONS = [
  { id: 'overview', title: 'Overview' },
  { id: 'catalog', title: 'Catalog' },
  { id: 'trust', title: 'Trust & Moderation' },
  { id: 'users', title: 'Users' },
  { id: 'alerts', title: 'Alerts & Notifications' },
  { id: 'monetization', title: 'Monetization' },
  { id: 'payments', title: 'Payments' },
  { id: 'settings', title: 'Settings & Flags' },
  { id: 'audit', title: 'Audit' },
  { id: 'tools', title: 'Support Toolkit' },
];

function LoginForm({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onLogin(username, password);
    } catch (err) {
      setError(err.message || 'Login failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100 p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-lg bg-white p-6 shadow"
        data-testid="ops-login-form"
      >
        <h1 className="text-lg font-semibold text-gray-800">Platform Ops Console</h1>
        <p className="mt-1 text-sm text-gray-400">Admin access only</p>
        <label className="mt-4 block text-sm text-gray-600">
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            autoComplete="username"
          />
        </label>
        <label className="mt-3 block text-sm text-gray-600">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            autoComplete="current-password"
          />
        </label>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="mt-4 w-full rounded-md bg-blue-600 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}

function ComingSoon({ title }) {
  return (
    <OpsEmptyState
      title={`${title} — coming soon`}
      hint="Action center (no row editing). Ships when the operational need is real."
    />
  );
}

export default function OpsConsole() {
  const { user, loading, login, logout } = useOpsAuth();
  const [active, setActive] = useState('overview');
  const [toast, setToast] = useState(null);

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-gray-400">Loading…</div>;
  }

  if (!user) {
    return <LoginForm onLogin={login} />;
  }

  return (
    <div className="flex min-h-screen bg-gray-100 font-sans">
      {/* Left rail */}
      <aside className="w-56 shrink-0 border-r border-gray-200 bg-white">
        <div className="px-4 py-4">
          <h1 className="text-sm font-bold text-gray-800">Ops Console</h1>
          <p className="text-xs text-gray-400">Signed in as {user}</p>
        </div>
        <nav className="px-2 pb-4">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setActive(s.id)}
              className={`block w-full rounded-md px-3 py-2 text-left text-sm ${
                active === s.id
                  ? 'bg-blue-600 font-medium text-white'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {s.title}
            </button>
          ))}
        </nav>
        <div className="px-4 pb-4">
          <button
            type="button"
            onClick={async () => {
              await logout();
              setToast(null);
            }}
            className="text-xs text-gray-400 hover:text-red-600"
          >
            Logout
          </button>
        </div>
      </aside>

      {/* Main pane */}
      <main className="flex-1 p-6">
        {SECTIONS.map((s) => (
          <div key={s.id} hidden={active !== s.id}>
            {renderSection(s.id, { setToast })}
          </div>
        ))}
      </main>

      <OpsToast
        message={toast?.message}
        type={toast?.type}
        onDismiss={() => setToast(null)}
      />
    </div>
  );
}

// Section render map — phases 2..6 replace the stubs with the real
// Ops* section components (the shell shape never changes, Rule 1.6).
function renderSection(id, { setToast }) {
  const title = SECTIONS.find((s) => s.id === id)?.title ?? id;
  switch (id) {
    case 'overview':
      return <OpsOverview setToast={setToast} />;
    case 'monetization':
      return <OpsMonetization setToast={setToast} />;
    case 'settings':
      return <OpsSettings setToast={setToast} />;
    case 'audit':
      return <OpsAudit setToast={setToast} />;
    case 'payments':
      return <OpsPayments setToast={setToast} />;
    case 'tools':
      return <OpsTools setToast={setToast} />;
    default:
      return <ComingSoon title={title} />;
  }
}
