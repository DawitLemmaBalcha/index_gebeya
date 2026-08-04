import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useParams } from 'react-router-dom'
import SellerIntelligenceDashboard from '../components/SellerIntelligenceDashboard'

// Mock dependencies (house pattern from AlertsPage.test.jsx)
vi.mock('../config', () => ({
  API_BASE_URL: '',
}))

vi.mock('../utils/analytics', () => ({
  getAnalyticsHeaders: () => ({}),
}))

const HubStub = () => {
  const { tab } = useParams()
  return <div data-testid="hub-page">{tab || 'none'}</div>
}

const renderDashboard = () => {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<SellerIntelligenceDashboard channelId={1} />} />
        <Route path="/hub/:tab?" element={<HubStub />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  window.Telegram = { WebApp: { initData: 'user=test' } }
  vi.clearAllMocks()
})

describe('SellerIntelligenceDashboard - locked prompt (NB-48 §2.4.3)', () => {
  it('non-subscribers see the prompt with an unlock CTA that opens /hub/all-in-one', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        is_pro: false,
        core: { items: [], matching_buyers: 0, total_dispatched: {} },
        pro: {},
      }),
    })

    renderDashboard()
    await waitFor(() => expect(
      screen.getByRole('button', { name: /Unlock Seller Intelligence/i })
    ).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /Unlock Seller Intelligence/i }))
    expect(screen.getByTestId('hub-page').textContent).toBe('all-in-one')
  })

  it('subscribers see the intelligence block (regression)', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        is_pro: true,
        core: { items: [], matching_buyers: 0, total_dispatched: {} },
        pro: { price_positioning: [], category_pulse: [], top_performers: [] },
      }),
    })

    renderDashboard()
    await waitFor(() => expect(screen.getByText('Seller Intelligence')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /Unlock Seller Intelligence/i })).not.toBeInTheDocument()
    expect(screen.getByText('Price Positioning')).toBeInTheDocument()
  })
})
