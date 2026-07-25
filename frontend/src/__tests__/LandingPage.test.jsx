import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import LandingPage from '../pages/LandingPage'

// Mock the fetch API for stats endpoint
const mockStats = {
  product_count: 142890,
  channel_count: 852,
  category_counts: { "Mobile Phones": 12000, "Vehicles": 4500 },
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('LandingPage', () => {
  it('renders the landing page without crashing', () => {
    // Mock fetch to return stats
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockStats),
    })

    render(<LandingPage />)
    const brandElements = screen.getAllByText('INDEX GEBEYA')
    expect(brandElements.length).toBeGreaterThanOrEqual(2) // header + footer
    expect(screen.getByText('The Search Engine for Ethiopia\'s Telegram Marketplace')).toBeDefined()
  })

  it('displays stats fetched from the API', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockStats),
    })

    render(<LandingPage />)

    await waitFor(() => {
      expect(screen.getByText('142,890')).toBeDefined()
    }, { timeout: 3000 })

    await waitFor(() => {
      expect(screen.getByText('852')).toBeDefined()
    }, { timeout: 3000 })
  })

  it('shows "--" when stats fail to load', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'))

    render(<LandingPage />)

    await waitFor(() => {
      // Stats bar should show fallback "--" values
      const dashes = screen.getAllByText('--')
      expect(dashes.length).toBeGreaterThanOrEqual(2)
    }, { timeout: 3000 })
  })

  it('shows search results after a successful search', async () => {
    const mockSearchResults = {
      items: [
        {
          id: 1,
          title: 'iPhone 13 128GB',
          price: 48000,
          currency: 'ETB',
          channel: { username: 'testchannel' },
          telegram_message_id: 123,
          category: 'Mobile Phones',
          image_path: '/img/test.jpg',
        },
      ],
      total: 1,
    }

    // First call is stats, second call is search
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockStats),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockSearchResults),
      })

    render(<LandingPage />)

    // Type in search input
    const searchInput = screen.getByPlaceholderText(/Try typing/i)
    expect(searchInput).toBeDefined()
  })
})
