// NB-56: OpsUsers section tests — lookup by telegram id, footprint counts
// rendering, and the ban/unban verbs calling opsFetch with the right path.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import OpsUsers from '../sections/OpsUsers'

const fetchMock = vi.fn()

function jsonResponse(body) {
  return { ok: true, status: 200, json: () => Promise.resolve(body) }
}

const statusBody = {
  telegram_id: 1010,
  username: 'candidate',
  banned: false,
  footprint: {
    reviews: 3,
    alerts_active: 2,
    alerts_total: 5,
    subscriptions_active: 1,
    boosts: 1,
    sold_reports: 0,
  },
}

const footprintBody = {
  user: { telegram_id: 1010, username: 'candidate', banned: false },
  reviews: {
    total: 3,
    rating_distribution: { '1': 0, '2': 0, '3': 1, '4': 1, '5': 1 },
    recent: [
      {
        channel_id: 1,
        channel_username: 'ch_shop',
        rating: 5,
        comment: 'great',
        created_at: '2026-08-10T10:00:00Z',
      },
    ],
  },
  alerts: { active: 2, total: 5 },
  subscriptions: { active: 1, product: 'all_in_one' },
  boosts: { total: 1, active: 1 },
  interactions: {
    counts_by_type: { view_item: 4, search: 1 },
    recent_50: [
      { id: 1, item_id: 9, interaction_type: 'view_item', created_at: '2026-08-10T10:00:00Z' },
    ],
  },
}

function stubEndpoints({ status = statusBody, banned = null } = {}) {
  fetchMock.mockImplementation((url, opts) => {
    if (url === '/ops/users/1010/status' && (!opts || opts.method === 'GET')) {
      return Promise.resolve(jsonResponse(status))
    }
    if (url === '/ops/users/1010/footprint' && (!opts || opts.method === 'GET')) {
      return Promise.resolve(jsonResponse(footprintBody))
    }
    if (url === '/ops/users/1010/ban' && opts?.method === 'POST') {
      return Promise.resolve(jsonResponse({ telegram_id: 1010, banned: banned ?? true }))
    }
    if (url === '/ops/users/1010/unban' && opts?.method === 'POST') {
      return Promise.resolve(jsonResponse({ telegram_id: 1010, banned: banned ?? false }))
    }
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'User not found' }) })
  })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('OpsUsers lookup + footprint', () => {
  it('looks up a user by telegram id and shows the footprint counts', async () => {
    stubEndpoints()
    render(<OpsUsers />)
    fireEvent.change(screen.getByPlaceholderText(/telegram id/i), { target: { value: '1010' } })
    fireEvent.click(screen.getByRole('button', { name: /look up/i }))

    expect(await screen.findByText(/candidate/)).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument() // reviews
    expect(screen.getByText('5')).toBeInTheDocument() // alerts total
    expect(screen.getByText('active')).toBeInTheDocument()
  })

  it('ban calls the ban verb and reflects the banned state', async () => {
    stubEndpoints({ banned: true })
    const setToast = vi.fn()
    render(<OpsUsers setToast={setToast} />)
    fireEvent.change(screen.getByPlaceholderText(/telegram id/i), { target: { value: '1010' } })
    fireEvent.click(screen.getByRole('button', { name: /look up/i }))
    fireEvent.click(await screen.findByRole('button', { name: 'Ban' }))

    const dialog = await screen.findByTestId('ops-confirm-dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ban' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/ops/users/1010/ban',
        expect.objectContaining({ method: 'POST' }),
      )
    })
    expect(await screen.findByText('BANNED')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Unban' })).toBeInTheDocument()
    await waitFor(() => expect(setToast).toHaveBeenCalledWith(expect.objectContaining({ type: 'success' })))
  })

  it('unban calls the unban verb', async () => {
    stubEndpoints({ status: { ...statusBody, banned: true }, banned: false })
    const setToast = vi.fn()
    render(<OpsUsers setToast={setToast} />)
    fireEvent.change(screen.getByPlaceholderText(/telegram id/i), { target: { value: '1010' } })
    fireEvent.click(screen.getByRole('button', { name: /look up/i }))
    fireEvent.click(await screen.findByRole('button', { name: 'Unban' }))

    const dialog = await screen.findByTestId('ops-confirm-dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Unban' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/ops/users/1010/unban',
        expect.objectContaining({ method: 'POST' }),
      )
    })
    expect(await screen.findByText('active')).toBeInTheDocument()
  })

  it('shows the not-found state for an unknown telegram id', async () => {
    stubEndpoints()
    render(<OpsUsers />)
    fireEvent.change(screen.getByPlaceholderText(/telegram id/i), { target: { value: '999' } })
    fireEvent.click(screen.getByRole('button', { name: /look up/i }))
    expect(await screen.findByText('User not found')).toBeInTheDocument()
  })

  it('renders the deep footprint: rating distribution, recent review, activity', async () => {
    stubEndpoints()
    render(<OpsUsers />)
    fireEvent.change(screen.getByPlaceholderText(/telegram id/i), { target: { value: '1010' } })
    fireEvent.click(screen.getByRole('button', { name: /look up/i }))

    expect(await screen.findByText(/Reviews — 3 total/i)).toBeInTheDocument()
    // rating distribution bars for 1..5
    expect(screen.getByTestId('rating-5')).toBeInTheDocument()
    expect(screen.getByTestId('rating-1')).toBeInTheDocument()
    // recent review with channel username + stars
    expect(screen.getByText('@ch_shop')).toBeInTheDocument()
    // interaction counts + recent activity (the chip label and count are
    // separate text nodes inside the same span)
    expect(screen.getByText(/view_item:/)).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText(/search:/)).toBeInTheDocument()
    expect(screen.getByText(/view_item on item #9/)).toBeInTheDocument()
  })
})
