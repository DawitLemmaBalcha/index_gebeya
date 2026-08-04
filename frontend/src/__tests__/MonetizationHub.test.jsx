import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import MonetizationHub from '../pages/MonetizationHub'

// Mock dependencies (house pattern from AlertsPage.test.jsx)
vi.mock('../config', () => ({
  API_BASE_URL: '',
}))

vi.mock('../utils/analytics', () => ({
  getAnalyticsHeaders: () => ({}),
}))

const mockGetStatus = vi.fn()
const mockOpenInvoice = vi.fn()
const mockFetchAlerts = vi.fn()
const mockRefreshQuote = vi.fn()
const mockPayWithStars = vi.fn()

let mockStatus = null
let mockSubLoading = false
let mockAlerts = []
let mockHasBeenFetched = false
let mockQuote = null
let mockActiveBoost = null
let mockBoostError = null

vi.mock('../hooks/useSubscription', () => ({
  useSubscription: () => ({
    status: mockStatus,
    loading: mockSubLoading,
    error: null,
    getStatus: mockGetStatus,
    openInvoice: mockOpenInvoice,
    applyCreditBoost: vi.fn(),
  }),
}))

vi.mock('../hooks/useAlerts', () => ({
  useAlerts: () => ({
    alerts: mockAlerts,
    loading: false,
    error: null,
    fetchAlerts: mockFetchAlerts,
    fetchMatchHistory: vi.fn(),
    pauseAlert: vi.fn(),
    deleteAlert: vi.fn(),
    hasBeenFetched: mockHasBeenFetched,
  }),
}))

vi.mock('../hooks/useBoost', () => ({
  useBoost: () => ({
    quote: mockQuote,
    activeBoost: mockActiveBoost,
    boosting: false,
    boostable: mockQuote?.boostable ?? false,
    error: mockBoostError,
    payWithStars: mockPayWithStars,
    refreshQuote: mockRefreshQuote,
  }),
}))

const defaultStatus = {
  product: null,
  status: null,
  current_period_end: null,
  extra_alerts: 0,
  credit_remaining: 0,
  credit_total: 2,
  free_cap: 20,
  effective_cap: 20,
  cap_banner_threshold: 2,
  alerts_only_price_stars: 30,
  all_in_one_price_stars: 100,
  boost_floor_price_stars: 25,
  boost_duration_days: 7,
}

// Stub route for the "Choose a product" navigation target
const StoresStub = () => <div data-testid="stores-page" />

const renderHub = (path = '/hub/boost') => {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/hub/:tab?" element={<MonetizationHub />} />
        <Route path="/stores" element={<StoresStub />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockStatus = { ...defaultStatus }
  mockSubLoading = false
  mockAlerts = []
  mockHasBeenFetched = false
  mockQuote = null
  mockActiveBoost = null
  mockBoostError = null
  vi.clearAllMocks()
  mockGetStatus.mockResolvedValue({ ...defaultStatus })
})

describe('MonetizationHub - tabs & deep links (NB-48 §2.1)', () => {
  it('opens the Boost tab for /hub/boost', () => {
    renderHub('/hub/boost')
    expect(screen.getByTestId('hub-tab-boost')).toBeInTheDocument()
  })

  it('opens the Alerts tab for /hub/alerts', () => {
    renderHub('/hub/alerts')
    expect(screen.getByTestId('hub-tab-alerts')).toBeInTheDocument()
  })

  it('opens the All-in-One tab for /hub/all-in-one', () => {
    renderHub('/hub/all-in-one')
    expect(screen.getByTestId('hub-tab-all-in-one')).toBeInTheDocument()
  })

  it('falls back to All-in-One for an invalid tab', () => {
    renderHub('/hub/bogus')
    expect(screen.getByTestId('hub-tab-all-in-one')).toBeInTheDocument()
  })

  it('falls back to All-in-One when no tab is given', () => {
    renderHub('/hub')
    expect(screen.getByTestId('hub-tab-all-in-one')).toBeInTheDocument()
  })

  it('switches tabs via the tab buttons', () => {
    renderHub('/hub/boost')
    fireEvent.click(screen.getByTestId('hub-tab-btn-alerts'))
    expect(screen.getByTestId('hub-tab-alerts')).toBeInTheDocument()
  })

  it('fetches subscription status on mount', () => {
    renderHub('/hub/boost')
    expect(mockGetStatus).toHaveBeenCalled()
  })
})

describe('MonetizationHub - boost tab (Rule 2.4: never a rate card)', () => {
  it('shows the floor price and NEVER a category table', () => {
    renderHub('/hub/boost')
    expect(screen.getByText(/from 25 Stars/i)).toBeInTheDocument()
    expect(screen.getByText('Choose a product')).toBeInTheDocument()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('Choose a product navigates to /stores', () => {
    renderHub('/hub/boost')
    fireEvent.click(screen.getByText('Choose a product'))
    expect(screen.getByTestId('stores-page')).toBeInTheDocument()
  })

  it('preselected item shows exact price + "Boost this item"', async () => {
    mockQuote = { price_stars: 150, duration_days: 7, boostable: true, active_boost: null }
    renderHub('/hub/boost?item=42')
    await waitFor(() => expect(mockRefreshQuote).toHaveBeenCalled())
    expect(screen.getByText(/150 Stars/i)).toBeInTheDocument()
    expect(screen.getByText('Boost this item')).toBeInTheDocument()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('"Boost this item" triggers the payment flow', async () => {
    mockQuote = { price_stars: 150, duration_days: 7, boostable: true, active_boost: null }
    renderHub('/hub/boost?item=42')
    await waitFor(() => expect(screen.getByText('Boost this item')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Boost this item'))
    expect(mockPayWithStars).toHaveBeenCalled()
  })

  it('shows the active-boost state for an already-boosted preselected item', () => {
    mockQuote = {
      price_stars: 150, duration_days: 7, boostable: false,
      active_boost: { ends_at: '2026-08-11T00:00:00Z', source: 'paid' },
    }
    mockActiveBoost = { ends_at: '2026-08-11T00:00:00Z', source: 'paid' }
    renderHub('/hub/boost?item=42')
    expect(screen.getByText(/Boosted/i)).toBeInTheDocument()
    expect(screen.queryByText('Boost this item')).not.toBeInTheDocument()
  })

  it('falls back to the guide state when the quote fails (403/404/503)', async () => {
    mockBoostError = 'Quote unavailable (503)'
    renderHub('/hub/boost?item=42')
    await waitFor(() => expect(screen.getByText('Choose a product')).toBeInTheDocument())
    expect(screen.getByText(/from 25 Stars/i)).toBeInTheDocument()
  })
})

describe('MonetizationHub - alerts tab', () => {
  it('shows the seller own usage and the price', () => {
    mockAlerts = [{ id: 1 }, { id: 2 }, { id: 3 }]
    renderHub('/hub/alerts')
    expect(screen.getByText(/You're at 3 of 20 active alerts/i)).toBeInTheDocument()
    expect(screen.getByText(/30 Stars/i)).toBeInTheDocument()
  })

  it('buy opens the alerts_only invoice', () => {
    renderHub('/hub/alerts')
    fireEvent.click(screen.getByText('Buy Alerts Only'))
    expect(mockOpenInvoice).toHaveBeenCalledWith('alerts_only')
  })

  it('shows the subscribed state instead of buy when a subscription exists', () => {
    mockStatus = { ...defaultStatus, product: 'all_in_one', status: 'active' }
    renderHub('/hub/alerts')
    expect(screen.queryByText('Buy Alerts Only')).not.toBeInTheDocument()
    expect(screen.getByText(/subscription active/i)).toBeInTheDocument()
  })
})

describe('MonetizationHub - all-in-one tab (the superset story)', () => {
  it('lists the superset with the credit counter', () => {
    mockStatus = { ...defaultStatus, credit_remaining: 1, credit_total: 2 }
    renderHub('/hub/all-in-one')
    expect(screen.getByText(/Seller Intelligence/i)).toBeInTheDocument()
    expect(screen.getByText(/1\/2/i)).toBeInTheDocument()
  })

  it('buy opens the all_in_one invoice', () => {
    renderHub('/hub/all-in-one')
    fireEvent.click(screen.getByText('Get All-in-One'))
    expect(mockOpenInvoice).toHaveBeenCalledWith('all_in_one')
  })

  it('hides the buy action when already subscribed', () => {
    mockStatus = { ...defaultStatus, product: 'all_in_one', status: 'active' }
    renderHub('/hub/all-in-one')
    expect(screen.queryByText('Get All-in-One')).not.toBeInTheDocument()
  })
})

describe('MonetizationHub - kill switch (blueprint §2.5)', () => {
  it('shows an unavailable state with NO buy actions when status is null', () => {
    mockStatus = null
    mockSubLoading = false
    renderHub('/hub/alerts')
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument()
    expect(screen.queryByText('Buy Alerts Only')).not.toBeInTheDocument()
    expect(screen.queryByText('Get All-in-One')).not.toBeInTheDocument()
    expect(mockOpenInvoice).not.toHaveBeenCalled()
  })
})

describe('MonetizationHub - How Stars explainer (Rule 10.2.5)', () => {
  it('toggles the collapsible explainer on the boost tab', () => {
    renderHub('/hub/boost')
    expect(screen.queryByText(/auto-renewing/i)).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('How Stars work'))
    expect(screen.getByText(/auto-renewing/i)).toBeInTheDocument()
  })

  it('the explainer is available on the alerts tab too', () => {
    renderHub('/hub/alerts')
    expect(screen.getByText('How Stars work')).toBeInTheDocument()
    fireEvent.click(screen.getByText('How Stars work'))
    expect(screen.getByText(/auto-renewing/i)).toBeInTheDocument()
  })
})

describe('MonetizationHub - cross-sell one-liners (Rule 10.2.7)', () => {
  it('boost tab cross-sells All-in-One', () => {
    renderHub('/hub/boost')
    expect(screen.getByText(/2 free boosts/i)).toBeInTheDocument()
  })

  it('alerts tab cross-sells All-in-One', () => {
    renderHub('/hub/alerts')
    expect(screen.getByText(/Want insights too\? All-in-One includes everything/i)).toBeInTheDocument()
  })

  it('all-in-one tab cross-sells boosts and navigates to the boost tab', () => {
    renderHub('/hub/all-in-one')
    expect(screen.getByText(/Need visibility now\? Buy a boost/i)).toBeInTheDocument()
    fireEvent.click(screen.getByText(/Buy a boost/i))
    expect(screen.getByTestId('hub-tab-boost')).toBeInTheDocument()
  })
})
