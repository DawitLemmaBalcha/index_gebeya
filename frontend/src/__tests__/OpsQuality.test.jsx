// NB-55: OpsQuality section tests — events list rendering (joined title +
// editor) and the Revert verb calling opsFetch with the right path.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import OpsQuality from '../sections/OpsQuality'

const fetchMock = vi.fn()

function jsonResponse(body) {
  return { ok: true, status: 200, json: () => Promise.resolve(body) }
}

const analyticsBody = {
  views_over_time: {
    days: ['2026-08-09', '2026-08-10'],
    total: [5, 3],
    top_items: [{ item_id: 9, title: 'iPhone 13', total: 5, daily: [5, 0] }],
  },
  price_distribution: [
    {
      category: 'Mobile Phones',
      buckets: { '0-1000': 2, '1000-5000': 1, '5000-20000': 1, '20000-100000': 1, '100000+': 1 },
    },
  ],
  per_channel: [
    { channel_id: 1, username: 'ch_shop', title: 'Shop', items: 4, views: 8, sold_reports: 2 },
  ],
}

function stubEvents(events) {
  fetchMock.mockImplementation((url, opts) => {
    if (url === '/ops/quality/events' && (!opts || opts.method === 'GET')) {
      return Promise.resolve(jsonResponse(events))
    }
    if (url === '/ops/items/analytics' && (!opts || opts.method === 'GET')) {
      return Promise.resolve(jsonResponse(analyticsBody))
    }
    if (url === '/ops/quality/events/2/revert' && opts?.method === 'POST') {
      return Promise.resolve(jsonResponse({ status: 'reverted', item_id: 9, field: 'price' }))
    }
    return Promise.resolve(jsonResponse({}))
  })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('OpsQuality events list', () => {
  it('renders events with joined title and editor username', async () => {
    stubEvents([
      {
        id: 2,
        item_id: 9,
        title: 'iPhone 13',
        field: 'category',
        old_value: 'Mobile Phones',
        new_value: 'Vehicles',
        edited_by: 1,
        edited_by_username: 'owner101',
        timestamp: '2026-08-09T10:00:00Z',
      },
    ])
    render(<OpsQuality />)
    expect(await screen.findByText('iPhone 13')).toBeInTheDocument()
    expect(screen.getByText('owner101')).toBeInTheDocument()
    expect(screen.getByText('Vehicles')).toBeInTheDocument()
  })

  it('shows the empty state when there are no events', async () => {
    stubEvents([])
    render(<OpsQuality />)
    expect(await screen.findByText('No owner corrections yet')).toBeInTheDocument()
  })

  it('revert opens the confirm dialog and calls the revert verb', async () => {
    stubEvents([
      {
        id: 2,
        item_id: 9,
        title: 'iPhone 13',
        field: 'price',
        old_value: '50.0',
        new_value: '250.0',
        edited_by_username: 'owner101',
        timestamp: '2026-08-09T10:00:00Z',
      },
    ])
    const setToast = vi.fn()
    render(<OpsQuality setToast={setToast} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Revert' }))
    const dialog = await screen.findByTestId('ops-confirm-dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revert' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/ops/quality/events/2/revert',
        expect.objectContaining({ method: 'POST' }),
      )
    })
    await waitFor(() => expect(setToast).toHaveBeenCalledWith(expect.objectContaining({ type: 'success' })))
  })

  it('Analytics tab fetches and renders the three blocks', async () => {
    stubEvents([])
    render(<OpsQuality />)
    fireEvent.click(await screen.findByRole('button', { name: 'Analytics' }))

    expect(await screen.findByText(/Views — last 14 days/i)).toBeInTheDocument()
    expect(screen.getByText(/Top items by views/i)).toBeInTheDocument()
    expect(screen.getByText(/iPhone 13/)).toBeInTheDocument()
    // price buckets + per-channel table
    expect(screen.getByTestId('bucket-100000+')).toBeInTheDocument()
    expect(screen.getByText('@ch_shop')).toBeInTheDocument()
    expect(screen.getByText('Sold reports')).toBeInTheDocument()
  })
})
