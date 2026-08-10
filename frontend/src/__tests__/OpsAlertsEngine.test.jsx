// NB-58/NB-59: OpsAlertsEngine section tests — the Diagnostics sub-view
// (item trace fetch, stage table, drill-down) and the Actions sub-view
// (reprocess/retry/reconcile verbs calling opsFetch through the shared
// confirm dialog; dropped verbs rendered as documented copy).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import OpsAlertsEngine from '../sections/OpsAlertsEngine'

const fetchMock = vi.fn()

function jsonResponse(body) {
  return { ok: true, status: 200, json: () => Promise.resolve(body) }
}

const traceBody = {
  item_id: 42,
  generated_at: '2026-08-10T10:00:00Z',
  alerts_evaluated: 2,
  stages: [
    {
      alert_id: 7,
      query_text: 'iphone 13',
      outcome: 'dispatched',
      score: 0.95,
      tier: 'bullseye',
      reason: 'All gates passed — the pipeline would dispatch',
    },
    {
      alert_id: 8,
      query_text: 'laptop',
      outcome: 'throttled',
      score: 0.6,
      tier: 'ring',
      reason: 'Ring match inside 3600s cooldown',
    },
  ],
}

function stubEndpoints({ trace = traceBody } = {}) {
  fetchMock.mockImplementation((url, opts) => {
    if (url === '/ops/diagnostics/items/42/trace' && (!opts || opts.method === 'GET')) {
      return Promise.resolve(jsonResponse(trace))
    }
    if (url === '/ops/actions/items/9/reprocess' && opts?.method === 'POST') {
      return Promise.resolve(jsonResponse({ status: 'reprocessed', item_id: 9 }))
    }
    if (url === '/ops/actions/notifications/5/retry' && opts?.method === 'POST') {
      return Promise.resolve(jsonResponse({ status: 'pending', notification_id: 5 }))
    }
    if (url === '/ops/actions/reconcile' && opts?.method === 'POST') {
      return Promise.resolve(jsonResponse({
        status: 'reconcile_done',
        summary: { fetched: 2, replayed_boost: 1, replayed_subscription: 0, skipped: 1, errors: 0 },
      }))
    }
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'Not found' }) })
  })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('Diagnostics sub-view', () => {
  it('fetches and renders the item trace with stage outcomes', async () => {
    stubEndpoints()
    render(<OpsAlertsEngine />)
    const pane = await screen.findByTestId('ops-diagnostics-pane')

    fireEvent.change(within(pane).getByPlaceholderText(/item id/i), { target: { value: '42' } })
    fireEvent.click(within(pane).getByRole('button', { name: /trace item/i }))

    expect(await screen.findByText(/2 alerts evaluated/i)).toBeInTheDocument()
    expect(screen.getByText('dispatched')).toBeInTheDocument()
    expect(screen.getByText('throttled')).toBeInTheDocument()
    expect(screen.getByText('iphone 13')).toBeInTheDocument()
    expect(screen.getByText('bullseye')).toBeInTheDocument()
  })

  it('drill-down reveals the stage reason', async () => {
    stubEndpoints()
    render(<OpsAlertsEngine />)
    const pane = await screen.findByTestId('ops-diagnostics-pane')
    fireEvent.change(within(pane).getByPlaceholderText(/item id/i), { target: { value: '42' } })
    fireEvent.click(within(pane).getByRole('button', { name: /trace item/i }))

    fireEvent.click(await screen.findByRole('button', { name: 'Alert #8' }))
    expect(await screen.findByTestId('trace-drill-down')).toHaveTextContent(/cooldown/)
  })

  it('shows the not-found state for an unknown item', async () => {
    stubEndpoints()
    render(<OpsAlertsEngine />)
    const pane = await screen.findByTestId('ops-diagnostics-pane')
    fireEvent.change(within(pane).getByPlaceholderText(/item id/i), { target: { value: '999' } })
    fireEvent.click(within(pane).getByRole('button', { name: /trace item/i }))
    expect(await screen.findByText('Item not found')).toBeInTheDocument()
  })
})

describe('Actions sub-view', () => {
  it('reprocess calls the verb through the confirm dialog', async () => {
    stubEndpoints()
    const setToast = vi.fn()
    render(<OpsAlertsEngine setToast={setToast} />)
    fireEvent.click(screen.getByRole('button', { name: 'Actions' }))
    const pane = await screen.findByTestId('ops-actions-pane')

    fireEvent.change(within(pane).getByPlaceholderText('Item id'), { target: { value: '9' } })
    fireEvent.click(within(pane).getByRole('button', { name: 'Reprocess' }))

    const dialog = await screen.findByTestId('ops-confirm-dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reprocess' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/ops/actions/items/9/reprocess',
        expect.objectContaining({ method: 'POST' }),
      )
    })
    expect(await screen.findByTestId('action-result')).toHaveTextContent('reprocessed')
    await waitFor(() => expect(setToast).toHaveBeenCalledWith(expect.objectContaining({ type: 'success' })))
  })

  it('retry notification calls the shared verb', async () => {
    stubEndpoints()
    render(<OpsAlertsEngine />)
    fireEvent.click(screen.getByRole('button', { name: 'Actions' }))
    const pane = await screen.findByTestId('ops-actions-pane')

    fireEvent.change(within(pane).getByPlaceholderText('Notification id'), { target: { value: '5' } })
    fireEvent.click(within(pane).getByRole('button', { name: 'Retry' }))

    const dialog = await screen.findByTestId('ops-confirm-dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Retry' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/ops/actions/notifications/5/retry',
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('reconcile calls the verb and renders the summary', async () => {
    stubEndpoints()
    render(<OpsAlertsEngine />)
    fireEvent.click(screen.getByRole('button', { name: 'Actions' }))
    const pane = await screen.findByTestId('ops-actions-pane')

    fireEvent.click(within(pane).getByRole('button', { name: /reconcile now/i }))
    const dialog = await screen.findByTestId('ops-confirm-dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reconcile' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/ops/actions/reconcile',
        expect.objectContaining({ method: 'POST' }),
      )
    })
    expect(await screen.findByTestId('action-result')).toHaveTextContent('replayed_boost')
  })

  it('documents the dropped verbs as copy, not actions', async () => {
    stubEndpoints()
    render(<OpsAlertsEngine />)
    fireEvent.click(screen.getByRole('button', { name: 'Actions' }))
    const pane = await screen.findByTestId('ops-actions-pane')

    expect(within(pane).getByText(/Re-process an ingestion post/i)).toBeInTheDocument()
    expect(within(pane).getByText(/Trigger photo refresh/i)).toBeInTheDocument()
    expect(within(pane).getAllByText(/Dropped from v1/i)).toHaveLength(2)
  })
})
