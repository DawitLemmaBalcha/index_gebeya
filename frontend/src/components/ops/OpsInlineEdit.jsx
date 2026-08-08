// NB-49: shared inline-edit cell — value with a pencil that swaps to an
// input + confirm/cancel row (Rule 1.2 shared kit).

import { useEffect, useRef, useState } from 'react';

export default function OpsInlineEdit({
  value,
  onSave,
  onCancel,
  inputType = 'text',
  step,
  min,
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(value ?? ''));
  const inputRef = useRef(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  if (!editing) {
    return (
      <div className="flex items-center gap-1.5">
        <span>{value ?? '—'}</span>
        <button
          type="button"
          onClick={() => {
            setDraft(String(value ?? ''));
            setEditing(true);
          }}
          className="text-gray-400 hover:text-blue-600"
          aria-label="edit"
        >
          ✏️
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <input
        ref={inputRef}
        type={inputType}
        step={step}
        min={min}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        className="w-24 rounded border border-gray-300 px-1.5 py-0.5 text-sm"
        data-testid="ops-inline-edit-input"
      />
      <button
        type="button"
        onClick={() => onSave(draft)}
        className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white hover:bg-blue-700"
      >
        ✓
      </button>
      <button
        type="button"
        onClick={() => {
          setEditing(false);
          onCancel?.();
        }}
        className="rounded border border-gray-300 px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-50"
      >
        ✕
      </button>
    </div>
  );
}
