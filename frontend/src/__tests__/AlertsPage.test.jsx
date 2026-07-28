import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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
