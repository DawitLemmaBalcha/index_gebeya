// NB-57: OpsRadar section tests — the anomaly radar renders computed
// problems with severity badges, and every one-click verb calls opsFetch
// with the endpoint carried on the anomaly's actions array (Rule 4.2).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import OpsRadar from '../sections/OpsRadar'

const fetchMock = vi.fn()

function jsonResponse(body) {
  return { ok: true, status: 200, json: () => Promise.resolve(body) }
}

const radarBody = {
  generated_at: '2026-08-10T08:00:00Z',
  anomalies: [
    {
      type: 'dead_chat_buyer',
      severity: 'high',
      entity_id: '1010',
      summary: 'Buyer 1010 has 3 failed notification deliveries (ids: [7]) — chat unreachable.',
      actions: [
        { verb: 'Retry delivery', endpoint: '/ops/actions/notifications/7/retry', method: 'POST' },
        { verb: 'Dismiss', endpoint: '/ops/radar/resolve', method: 'POST' },
      ],
    },
    {
      type: 'report_spike',
      severity: 'medium',
      entity_id: '5',
      summary: "Item #5 ('iPhone 13') has 2/3 sold reports — near the take-down threshold.",
      actions: [
        { verb: 'Clear reports', endpoint: '/ops/radar/items/5/clear-reports', method: 'POST' },
        { verb: 'View item', endpoint: '/item/5', method: 'GET' },
        { verb: 'Dismiss', endpoint: '/ops/radar/resolve', method: 'POST' },
      ],
    },
    {
      type: 'scam_pattern_channel',
      severity: 'high',
      entity_id: '3',
      summary: 'Channel @scamshop (trust 1.0) has a price outlier vs its category median and 2 sold reports.',
      actions: [
        { verb: 'Pause indexing', endpoint: '/ops/radar/channels/3/pause', method: 'POST' },
        { verb: 'Ban owner', endpoint: '/ops/users/555/ban', method: 'POST' },
        { verb: 'Dismiss', endpoint: '/ops/radar/resolve', method: 'POST' },
      ],
    },
    {
      type: 'price_anomaly',
      severity: 'medium',
      entity_id: '9',
      summary: "Item #9 ('Free bike') is listed at 0 ETB.",
      actions: [
        { verb: 'Hide item', endpoint: '/ops/radar/items/9/hide', method: 'POST' },
        { verb: 'Dismiss', endpoint: '/ops/radar/resolve', method: 'POST' },
      ],
    },
  ],
}

function stubRadar(body = radarBody) {
  fetchMock.mockImplementation((url, opts) => {
    if (url === '/ops/radar' && (!opts || opts.method === 'GET')) {
      return Promise.resolve(jsonResponse(body))
    }
    if (opts?.method === 'POST') {
      // every radar verb resolves; the assertions focus on the wiring
      return Promise.resolve(jsonResponse({ status: 'ok' }))
    }
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'nope' }) })
  })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('OpsRadar anomaly list', () => {
  it('loads the radar on mount and renders summaries with severity badges', async () => {
    stubRadar()
    render(<OpsRadar />)

    expect(await screen.findByText(/Buyer 1010 has 3 failed notification deliveries/)).toBeInTheDocument()
    expect(screen.getByText(/near the take-down threshold/)).toBeInTheDocument()
    expect(screen.getAllByText('high').length).toBe(2)
    expect(screen.getAllByText('medium').length).toBe(2)
  })

  it('renders the empty state when there are no anomalies', async () => {
    stubRadar({ generated_at: '2026-08-10T08:00:00Z', anomalies: [] })
    render(<OpsRadar />)
    expect(await screen.findByText(/no anomalies/i)).toBeInTheDocument()
  })

  it('retry verb calls the shared notification retry endpoint', async () => {
    stubRadar()
    const setToast = vi.fn()
    render(<OpsRadar setToast={setToast} />)
    const retryBtn = await screen.findByRole('button', { name: /retry delivery/i })
    fireEvent.click(retryBtn)

    const dialog = await screen.findByTestId('ops-confirm-dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: /retry/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/ops/actions/notifications/7/retry',
        expect.objectContaining({ method: 'POST' }),
      )
    })
    await waitFor(() => expect(setToast).toHaveBeenCalledWith(expect.objectContaining({ type: 'success' })))
  })

  it('clear-reports verb calls the enforcement endpoint', async () => {
    stubRadar()
    render(<OpsRadar />)
    const btn = await screen.findByRole('button', { name: /clear reports/i })
    fireEvent.click(btn)
    const dialog = await screen.findByTestId('ops-confirm-dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: /clear/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/ops/radar/items/5/clear-reports',
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('pause and ban-owner verbs call their endpoints', async () => {
    stubRadar()
    render(<OpsRadar />)

    fireEvent.click(await screen.findByRole('button', { name: /pause indexing/i }))
    const pauseDialog = await screen.findByTestId('ops-confirm-dialog')
    fireEvent.click(within(pauseDialog).getByRole('button', { name: /pause/i }))
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/ops/radar/channels/3/pause',
        expect.objectContaining({ method: 'POST' }),
      )
    })

    fireEvent.click(screen.getByRole('button', { name: /ban owner/i }))
    const banDialog = await screen.findByTestId('ops-confirm-dialog')
    fireEvent.click(within(banDialog).getByRole('button', { name: /ban/i }))
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/ops/users/555/ban',
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('hide verb calls the enforcement endpoint', async () => {
    stubRadar()
    render(<OpsRadar />)
    fireEvent.click(await screen.findByRole('button', { name: /hide item/i }))
    const dialog = await screen.findByTestId('ops-confirm-dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: /hide/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/ops/radar/items/9/hide',
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('dismiss verb posts the type+entity_id pair and refreshes the list', async () => {
    stubRadar()
    render(<OpsRadar />)
    const dismissButtons = await screen.findAllByRole('button', { name: /dismiss/i })
    fireEvent.click(dismissButtons[0])
    const dialog = await screen.findByTestId('ops-confirm-dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: /dismiss/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/ops/radar/resolve',
        expect.objectContaining({ method: 'POST' }),
      )
    })
    const dismissBody = JSON.parse(fetchMock.mock.calls.find(([u]) => u === '/ops/radar/resolve')[1].body)
    expect(dismissBody).toEqual({ type: 'dead_chat_buyer', entity_id: '1010' })
  })

  it('renders GET actions (view item) as links, not fetch calls', async () => {
    stubRadar()
    render(<OpsRadar />)
    const link = await screen.findByRole('link', { name: /view item/i })
    expect(link.getAttribute('href')).toBe('/item/5')
    expect(fetchMock).not.toHaveBeenCalledWith('/item/5', expect.anything())
  })
})
