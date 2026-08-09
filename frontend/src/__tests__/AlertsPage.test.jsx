import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import AlertsPage from '../pages/AlertsPage'

// Mock dependencies
vi.mock('../config', () => ({
  API_BASE_URL: '',
}))

vi.mock('../utils/analytics', () => ({
  getAnalyticsHeaders: () => ({}),
}))

vi.mock('../components/AlertModal', () => ({
  default: ({ isOpen }) => isOpen ? <div data-testid="alert-modal">Modal</div> : null,
}))

// Create a mock for useAlerts to return controlled data
const mockFetchAlerts = vi.fn()
const mockFetchMatchHistory = vi.fn()
const mockPauseAlert = vi.fn()
const mockDeleteAlert = vi.fn()

let mockAlerts = []
let mockMatchHistory = []
let mockLoading = false
let mockError = null
let mockHasBeenFetched = false

vi.mock('../hooks/useAlerts', () => ({
  useAlerts: () => ({
    alerts: mockAlerts,
    matchHistory: mockMatchHistory,
    loading: mockLoading,
    error: mockError,
    fetchAlerts: mockFetchAlerts,
    fetchMatchHistory: mockFetchMatchHistory,
    pauseAlert: mockPauseAlert,
    deleteAlert: mockDeleteAlert,
    hasBeenFetched: mockHasBeenFetched,
  }),
}))

// NB-48: subscription status for the cap-awareness banner
const mockGetStatus = vi.fn()
let mockSubStatus = null
let mockSubLoading = false

vi.mock('../hooks/useSubscription', () => ({
  useSubscription: () => ({
    status: mockSubStatus,
    loading: mockSubLoading,
    error: null,
    getStatus: mockGetStatus,
    openInvoice: vi.fn(),
    applyCreditBoost: vi.fn(),
  }),
}))

const renderAlertsPage = () => {
  return render(
    <MemoryRouter>
      <AlertsPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockAlerts = []
  mockMatchHistory = []
  mockLoading = false
  mockError = null
  mockHasBeenFetched = false
  mockSubStatus = null
  mockSubLoading = false
  vi.clearAllMocks()
})

describe('AlertsPage - Smart Filter Badges (TECH-21)', () => {
  it('shows "Strict Brand" badge when strict_brand is true', () => {
    mockAlerts = [
      {
        id: 1,
        query_text: 'Toyota Corolla',
        max_price: null,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        preferences: JSON.stringify({ strict_brand: true }),
      },
    ]
    mockHasBeenFetched = true
    renderAlertsPage()

    expect(screen.getByText('Strict Brand')).toBeInTheDocument()
    // Should NOT show Strict Model
    expect(screen.queryByText('Strict Model')).not.toBeInTheDocument()
  })

  it('shows "Strict Model" badge when strict_model is true', () => {
    mockAlerts = [
      {
        id: 2,
        query_text: 'iPhone 15',
        max_price: null,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        preferences: JSON.stringify({ strict_model: true }),
      },
    ]
    mockHasBeenFetched = true
    renderAlertsPage()

    expect(screen.getByText('Strict Model')).toBeInTheDocument()
    expect(screen.queryByText('Strict Brand')).not.toBeInTheDocument()
  })

  it('shows both badges when both strict flags are true', () => {
    mockAlerts = [
      {
        id: 3,
        query_text: 'Samsung Galaxy',
        max_price: 50000,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        preferences: JSON.stringify({ strict_brand: true, strict_model: true }),
      },
    ]
    mockHasBeenFetched = true
    renderAlertsPage()

    expect(screen.getByText('Strict Brand')).toBeInTheDocument()
    expect(screen.getByText('Strict Model')).toBeInTheDocument()
  })

  it('shows no pills when preferences is empty', () => {
    mockAlerts = [
      {
        id: 4,
        query_text: 'Laptop',
        max_price: null,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        preferences: JSON.stringify({}),
      },
    ]
    mockHasBeenFetched = true
    renderAlertsPage()

    expect(screen.queryByText('Strict Brand')).not.toBeInTheDocument()
    expect(screen.queryByText('Strict Model')).not.toBeInTheDocument()
  })

  it('shows no pills when strict flags are false', () => {
    mockAlerts = [
      {
        id: 5,
        query_text: 'Table',
        max_price: null,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        preferences: JSON.stringify({ strict_brand: false, strict_model: false }),
      },
    ]
    mockHasBeenFetched = true
    renderAlertsPage()

    expect(screen.queryByText('Strict Brand')).not.toBeInTheDocument()
    expect(screen.queryByText('Strict Model')).not.toBeInTheDocument()
  })

  it('handles malformed preferences JSON gracefully (no crash)', () => {
    mockAlerts = [
      {
        id: 6,
        query_text: 'Chair',
        max_price: null,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        preferences: '{broken json',
      },
    ]
    mockHasBeenFetched = true

    // Should not throw — just render without badges
    expect(() => renderAlertsPage()).not.toThrow()
    expect(screen.queryByText('Strict Brand')).not.toBeInTheDocument()
    expect(screen.queryByText('Strict Model')).not.toBeInTheDocument()
  })

  it('shows only strict badges, ignoring other preference keys', () => {
    mockAlerts = [
      {
        id: 7,
        query_text: 'Car',
        max_price: null,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        preferences: JSON.stringify({ strict_brand: true, some_other_key: true, another: false }),
      },
    ]
    mockHasBeenFetched = true
    renderAlertsPage()

    // Only strict_brand should show; other keys should be filtered out
    expect(screen.getByText('Strict Brand')).toBeInTheDocument()
    expect(screen.queryByText(/some_other_key/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/another/i)).not.toBeInTheDocument()
  })
})

describe('AlertsPage - cap awareness banner (NB-48 §2.4.1)', () => {
  const makeAlerts = (n) =>
    Array.from({ length: n }, (_, i) => ({
      id: i + 1,
      query_text: `Alert ${i + 1}`,
      max_price: null,
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      preferences: '{}',
    }))

  const capStatus = (overrides = {}) => ({
    product: null,
    status: null,
    effective_cap: 20,
    cap_banner_threshold: 2,
    extra_alerts: 0,
    alerts_extra_allowance: 10,  // FIX 3: the allowance (not the held count)
    alerts_only_price_stars: 30,
    ...overrides,
  })

  it('shows the banner at 18 of 20 (within threshold 2)', () => {
    mockAlerts = makeAlerts(18)
    mockSubStatus = capStatus()
    mockHasBeenFetched = true
    renderAlertsPage()
    expect(screen.getByText(/You're at 18 of 20 active alerts/i)).toBeInTheDocument()
  })

  it('banner carries the extra-alert allowance number (FIX 3)', () => {
    mockAlerts = makeAlerts(18)
    mockSubStatus = capStatus()
    mockHasBeenFetched = true
    renderAlertsPage()
    expect(screen.getByText('Get 10 more active alerts')).toBeInTheDocument()
  })

  it('hides the banner at 17 of 20 (3 above the threshold)', () => {
    mockAlerts = makeAlerts(17)
    mockSubStatus = capStatus()
    mockHasBeenFetched = true
    renderAlertsPage()
    expect(screen.queryByText(/You're at 17 of 20 active alerts/i)).not.toBeInTheDocument()
  })

  it('shows the banner at the cap (20 of 20)', () => {
    mockAlerts = makeAlerts(20)
    mockSubStatus = capStatus()
    mockHasBeenFetched = true
    renderAlertsPage()
    expect(screen.getByText(/You're at 20 of 20 active alerts/i)).toBeInTheDocument()
  })

  it('hides the banner while the status is loading', () => {
    mockAlerts = makeAlerts(18)
    mockSubStatus = capStatus()
    mockSubLoading = true
    mockHasBeenFetched = true
    renderAlertsPage()
    expect(screen.queryByText(/You're at 18 of 20 active alerts/i)).not.toBeInTheDocument()
  })

  it('hides the banner when status is null (monetization disabled)', () => {
    mockAlerts = makeAlerts(20)
    mockSubStatus = null
    mockHasBeenFetched = true
    renderAlertsPage()
    expect(screen.queryByText(/active alerts/i)).not.toBeInTheDocument()
  })

  it('tapping the banner navigates to /hub/alerts', () => {
    mockAlerts = makeAlerts(18)
    mockSubStatus = capStatus()
    mockHasBeenFetched = true
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<AlertsPage />} />
          <Route path="/hub/alerts" element={<div data-testid="hub-alerts" />} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByText(/You're at 18 of 20 active alerts/i))
    expect(screen.getByTestId('hub-alerts')).toBeInTheDocument()
  })
})

describe('AlertsPage - standing subscription card (UAT round-2 FIX 3)', () => {
  const makeAlerts = (n) =>
    Array.from({ length: n }, (_, i) => ({
      id: i + 1,
      query_text: `Alert ${i + 1}`,
      max_price: null,
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      preferences: '{}',
    }))

  const capStatus = (overrides = {}) => ({
    product: null,
    status: null,
    effective_cap: 20,
    cap_banner_threshold: 2,
    extra_alerts: 0,
    alerts_extra_allowance: 10,
    alerts_only_price_stars: 30,
    ...overrides,
  })

  it('not subscribed: shows the pitch with the allowance and price', () => {
    mockAlerts = makeAlerts(5)
    mockSubStatus = capStatus()
    mockHasBeenFetched = true
    renderAlertsPage()
    expect(
      screen.getByText('More alert space — get 10 more active alerts for 30 Stars')
    ).toBeInTheDocument()
  })

  it('is visible regardless of proximity to the cap (far from it here)', () => {
    mockAlerts = makeAlerts(5)
    mockSubStatus = capStatus()
    mockHasBeenFetched = true
    renderAlertsPage()
    // The cap banner is hidden at 5 of 20 (threshold 2)...
    expect(screen.queryByText(/You're at 5 of 20 active alerts/i)).not.toBeInTheDocument()
    // ...but the standing card still renders.
    expect(screen.getByText(/More alert space/i)).toBeInTheDocument()
  })

  it('subscribed: shows the active status with the effective cap', () => {
    mockAlerts = makeAlerts(3)
    mockSubStatus = capStatus({ product: 'alerts_only', status: 'active', effective_cap: 30 })
    mockHasBeenFetched = true
    renderAlertsPage()
    expect(screen.getByText('Alerts Plus active — 30 alerts')).toBeInTheDocument()
    expect(screen.queryByText(/More alert space/i)).not.toBeInTheDocument()
  })

  it('hidden while the subscription status is loading', () => {
    mockAlerts = makeAlerts(5)
    mockSubStatus = capStatus()
    mockSubLoading = true
    mockHasBeenFetched = true
    renderAlertsPage()
    expect(screen.queryByText(/More alert space/i)).not.toBeInTheDocument()
  })

  it('hidden when status is null (monetization disabled)', () => {
    mockAlerts = makeAlerts(5)
    mockSubStatus = null
    mockHasBeenFetched = true
    renderAlertsPage()
    expect(screen.queryByText(/More alert space/i)).not.toBeInTheDocument()
  })

  it('tapping the card navigates to /hub/alerts', () => {
    mockAlerts = makeAlerts(5)
    mockSubStatus = capStatus()
    mockHasBeenFetched = true
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<AlertsPage />} />
          <Route path="/hub/alerts" element={<div data-testid="hub-alerts" />} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByText(/More alert space/i))
    expect(screen.getByTestId('hub-alerts')).toBeInTheDocument()
  })
})

describe('AlertsPage - subscription status freshness on re-activation (BUG 2)', () => {
  const makeAlerts = (n) =>
    Array.from({ length: n }, (_, i) => ({
      id: i + 1,
      query_text: `Alert ${i + 1}`,
      max_price: null,
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      preferences: '{}',
    }))

  const capStatus = (overrides = {}) => ({
    product: null,
    status: null,
    effective_cap: 20,
    cap_banner_threshold: 2,
    extra_alerts: 0,
    alerts_extra_allowance: 10,
    alerts_only_price_stars: 30,
    ...overrides,
  })

  it('stale allowance is replaced when the tab is hidden and shown again', () => {
    mockAlerts = makeAlerts(5)
    mockSubStatus = null
    const allowances = [10, 15]
    mockGetStatus.mockImplementation(async () => {
      mockSubStatus = capStatus({ alerts_extra_allowance: allowances.shift() })
      return mockSubStatus
    })

    const { rerender } = render(
      <MemoryRouter>
        <AlertsPage active={false} />
      </MemoryRouter>
    )
    // Hidden tab must NOT fetch at app-start mount (pre-fix: AlertsPage is
    // always mounted and fetches once at app start — this assertion fails)
    expect(mockGetStatus).not.toHaveBeenCalled()

    // First activation → fetch #1 (allowance 10)
    rerender(
      <MemoryRouter>
        <AlertsPage active={true} />
      </MemoryRouter>
    )
    expect(mockGetStatus).toHaveBeenCalledTimes(1)
    rerender(
      <MemoryRouter>
        <AlertsPage active={true} />
      </MemoryRouter>
    )
    expect(
      screen.getByText('More alert space — get 10 more active alerts for 30 Stars')
    ).toBeInTheDocument()

    // Leave the tab; ops bumps alerts_subscription_extra_alerts → 15; come back
    rerender(
      <MemoryRouter>
        <AlertsPage active={false} />
      </MemoryRouter>
    )
    expect(mockGetStatus).toHaveBeenCalledTimes(1)
    rerender(
      <MemoryRouter>
        <AlertsPage active={true} />
      </MemoryRouter>
    )
    expect(mockGetStatus).toHaveBeenCalledTimes(2)
    rerender(
      <MemoryRouter>
        <AlertsPage active={true} />
      </MemoryRouter>
    )
    // The fresh fetch's allowance (15) must replace the stale one (10)
    expect(
      screen.getByText('More alert space — get 15 more active alerts for 30 Stars')
    ).toBeInTheDocument()
  })
})
