import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useParams } from 'react-router-dom'
import StoresPage from '../pages/StoresPage'

// Mock dependencies (house pattern from AlertsPage.test.jsx)
vi.mock('../config', () => ({
  API_BASE_URL: '',
}))

vi.mock('../utils/analytics', () => ({
  getAnalyticsHeaders: () => ({}),
}))

vi.mock('../components/ChannelInventory', () => ({
  default: () => <div data-testid="channel-inventory" />,
}))

const mockFetchChannels = vi.fn()
const mockGetStatus = vi.fn()
const mockOpenInvoice = vi.fn()
const mockFetchBoosts = vi.fn()

let mockChannels = []
let mockHasBeenFetched = false
let mockSubStatus = null
let mockBoosts = []
let mockBoostsError = null
let mockBoostsFetched = false

vi.mock('../hooks/useOwnerChannels', () => ({
  useOwnerChannels: () => ({
    channels: mockChannels,
    loading: false,
    error: null,
    fetchChannels: mockFetchChannels,
    hasBeenFetched: mockHasBeenFetched,
    togglePause: vi.fn(),
    removeChannel: vi.fn(),
  }),
}))

vi.mock('../hooks/useSubscription', () => ({
  useSubscription: () => ({
    status: mockSubStatus,
    loading: false,
    error: null,
    getStatus: mockGetStatus,
    openInvoice: mockOpenInvoice,
    applyCreditBoost: vi.fn(),
  }),
}))

vi.mock('../hooks/useBoosts', () => ({
  useBoosts: () => ({
    boosts: mockBoosts,
    loading: false,
    error: mockBoostsError,
    hasBeenFetched: mockBoostsFetched,
    fetchBoosts: mockFetchBoosts,
  }),
}))

// Hub stub records the tab so we can assert the navigation target
const HubStub = () => {
  const { tab } = useParams()
  return <div data-testid="hub-page">{tab || 'none'}</div>
}

const renderStores = () => {
  return render(
    <MemoryRouter initialEntries={['/stores']}>
      <Routes>
        <Route path="/stores" element={<StoresPage />} />
        <Route path="/hub/:tab?" element={<HubStub />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockChannels = [
    { id: 1, username: 'channel_one', title: 'Channel One', indexing_paused: false, product_count: 3 },
  ]
  mockHasBeenFetched = true
  mockSubStatus = {
    product: null,
    status: null,
    current_period_end: null,
    extra_alerts: 0,
    credit_remaining: 0,
    credit_total: 2,
    free_cap: 20,
    effective_cap: 20,
  }
  mockBoosts = []
  mockBoostsError = null
  mockBoostsFetched = true
  vi.clearAllMocks()
  mockFetchBoosts.mockResolvedValue([])
})

describe('StoresPage - subscription card (NB-48 Rule 10.3.1)', () => {
  it('no longer offers "Upgrade to Alerts Only"', () => {
    renderStores()
    expect(screen.queryByText('Upgrade to Alerts Only')).not.toBeInTheDocument()
    expect(screen.queryByText('alerts_only')).not.toBeInTheDocument()
  })

  it('never calls the alerts_only invoice from Stores', () => {
    renderStores()
    expect(mockOpenInvoice).not.toHaveBeenCalledWith('alerts_only')
    expect(mockOpenInvoice).not.toHaveBeenCalledWith('all_in_one')
  })

  it('the All-in-One CTA navigates to /hub/all-in-one', () => {
    renderStores()
    fireEvent.click(screen.getByText('All-in-One'))
    expect(screen.getByTestId('hub-page').textContent).toBe('all-in-one')
  })
})

describe('StoresPage - boost management card (NB-48)', () => {
  it('fetches boosts for the owner channels on mount', () => {
    renderStores()
    expect(mockFetchBoosts).toHaveBeenCalledWith(mockChannels)
  })

  it('renders active boosts with item title and time remaining', () => {
    mockBoosts = [
      {
        item_id: 11,
        title: 'iPhone 13',
        ends_at: new Date(Date.now() + 2.5 * 86400000).toISOString(),
        source: 'paid',
      },
    ]
    renderStores()
    expect(screen.getByText('iPhone 13')).toBeInTheDocument()
    expect(screen.getByText(/3 days left/i)).toBeInTheDocument()
  })

  it('"Boost a product" navigates to /hub/boost', () => {
    renderStores()
    fireEvent.click(screen.getByText('Boost a product'))
    expect(screen.getByTestId('hub-page').textContent).toBe('boost')
  })

  it('renders the All-in-One upsell on the boost card', () => {
    renderStores()
    fireEvent.click(screen.getByText(/All-in-One includes free boosts/i))
    expect(screen.getByTestId('hub-page').textContent).toBe('all-in-one')
  })

  it('renders the empty state when there are no active boosts', () => {
    mockBoosts = []
    renderStores()
    expect(screen.getByText('No active boosts')).toBeInTheDocument()
  })

  it('hides the whole card when the boosts fetch fails (503 kill switch)', () => {
    mockBoostsError = 'Status unavailable (503)'
    renderStores()
    expect(screen.queryByText('No active boosts')).not.toBeInTheDocument()
    expect(screen.queryByText('Boost a product')).not.toBeInTheDocument()
  })
})

describe('StoresPage - zero-channel (non-owner) monetization sections (BUG 1)', () => {
  beforeEach(() => {
    mockChannels = []
    mockHasBeenFetched = true
  })

  it('shows the subscription card ("Boost your selling power") + All-in-One CTA', () => {
    renderStores()
    expect(screen.getByText('Boost your selling power')).toBeInTheDocument()
    expect(screen.getByText('All-in-One')).toBeInTheDocument()
  })

  it('shows the Active Boosts card with its empty state', () => {
    renderStores()
    expect(screen.getByText('Active Boosts')).toBeInTheDocument()
    expect(screen.getByText('No active boosts')).toBeInTheDocument()
  })

  it('fetches boosts for zero channels (empty fan-out) so the card can render', () => {
    renderStores()
    expect(mockFetchBoosts).toHaveBeenCalledWith([])
  })

  it('keeps the educational prompt plus an Add Channel link to /addchannel', () => {
    renderStores()
    expect(screen.getByText('Add Your Store')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'Add Channel' })
    expect(link).toHaveAttribute('href', 'https://t.me/IndexGebeyaBot?start=addchannel')
  })
})

describe('StoresPage - owner layout regression (BUG 1)', () => {
  it('owner with channels still sees the full existing layout', () => {
    mockChannels = [
      { id: 1, username: 'channel_one', title: 'Channel One', indexing_paused: false, product_count: 3 },
    ]
    renderStores()
    // header
    expect(screen.getByText('My Stores')).toBeInTheDocument()
    // monetization cards
    expect(screen.getByText('Boost your selling power')).toBeInTheDocument()
    expect(screen.getByText('Active Boosts')).toBeInTheDocument()
    // channel management UI
    expect(screen.getByText('@channel_one')).toBeInTheDocument()
    expect(screen.getByText('Manage')).toBeInTheDocument()
    // add-another-channel CTA
    expect(screen.getByRole('link', { name: 'Add Channel' })).toHaveAttribute(
      'href',
      'https://t.me/IndexGebeyaBot?start=addchannel'
    )
    // no non-owner prompt
    expect(screen.queryByText('Add Your Store')).not.toBeInTheDocument()
  })
})

describe('StoresPage - subscription status freshness (BUG 2)', () => {
  it('does not fetch status while the tab is hidden; refetches on activation', () => {
    const { rerender } = render(
      <MemoryRouter initialEntries={['/stores']}>
        <Routes>
          <Route path="/stores" element={<StoresPage active={false} />} />
          <Route path="/hub/:tab?" element={<HubStub />} />
        </Routes>
      </MemoryRouter>
    )
    // Hidden at mount: no status fetch (pre-fix the page is always mounted
    // and fetches once at app start, so this assertion fails)
    expect(mockGetStatus).not.toHaveBeenCalled()

    rerender(
      <MemoryRouter initialEntries={['/stores']}>
        <Routes>
          <Route path="/stores" element={<StoresPage active={true} />} />
          <Route path="/hub/:tab?" element={<HubStub />} />
        </Routes>
      </MemoryRouter>
    )
    expect(mockGetStatus).toHaveBeenCalledTimes(1)
  })
})
