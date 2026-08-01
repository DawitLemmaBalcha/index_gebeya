import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ProductPage from '../pages/ProductPage'

// Mock the config module
vi.mock('../config', () => ({
  API_BASE_URL: '',
}))

// Mock useParams
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useParams: () => ({ id: '1' }),
  }
})

const mockItem = {
  id: 1,
  title: 'iPhone 13 128GB Gold',
  price: 48500,
  currency: 'ETB',
  description: 'Brand new iPhone 13, still sealed in box.',
  category: 'Mobile Phones',
  location: 'Bole, Addis Ababa',
  condition: 'New',
  image_path: '/img/test.jpg',
  images: ['/img/test.jpg', '/img/test2.jpg'],
  specs: '{"Brand":"Apple","Model":"iPhone 13","Storage":"128GB"}',
  channel: {
    id: 1,
    username: 'testchannel',
    trust_score: 4.2,
    review_count: 15,
  },
  phone_number: '+251911234567',
}

const mockRelated = [
  {
    id: 2,
    title: 'iPhone 12 64GB',
    price: 35000,
    currency: 'ETB',
    channel: { username: 'anothershop' },
    image_path: '/img/r1.jpg',
    images: ['/img/r1.jpg'],
    condition: 'Used',
  },
]

const mockReviews = [
  { id: 1, rating: 5, comment: 'Great seller!', user_name: 'Abebe', user_photo_url: null },
]

describe('ProductPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders skeleton layout while loading', () => {
    // Delayed fetch so loading stays true
    global.fetch = vi.fn().mockImplementation(
      () => new Promise((resolve) => {
        setTimeout(() => {
          resolve({
            ok: true,
            json: () => Promise.resolve(mockItem),
          })
        }, 5000)
      })
    )

    render(
      <MemoryRouter initialEntries={['/item/1']}>
        <Routes>
          <Route path="/item/:id" element={<ProductPage />} />
        </Routes>
      </MemoryRouter>
    )

    // Should show skeleton pulse elements while loading
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)

    // No spinner should be visible (old behavior)
    const spinner = document.querySelector('.animate-spin')
    expect(spinner).toBeNull()
  })

  it('renders product content after loading', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockItem),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockRelated),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockReviews),
      })

    render(
      <MemoryRouter initialEntries={['/item/1']}>
        <Routes>
          <Route path="/item/:id" element={<ProductPage />} />
        </Routes>
      </MemoryRouter>
    )

    // Wait for content to load
    await waitFor(() => {
      expect(screen.getByText('iPhone 13 128GB Gold')).toBeDefined()
    }, { timeout: 5000 })

    // Price should appear
    await waitFor(() => {
      expect(screen.getByText(/48,500/)).toBeDefined()
    }, { timeout: 5000 })

    // Description
    expect(screen.getByText('Brand new iPhone 13, still sealed in box.')).toBeDefined()

    // Channel username
    expect(screen.getByText('@testchannel')).toBeDefined()
  })

  it('shows error state (not eternal skeleton) when item fetch fails', async () => {
    // 404 / dead ID — the fetch resolves non-ok
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: 'Item not found' }),
    })

    render(
      <MemoryRouter initialEntries={['/item/999']}>
        <Routes>
          <Route path="/item/:id" element={<ProductPage />} />
        </Routes>
      </MemoryRouter>
    )

    // Regression: previously the effect's catch set reportError + finally set
    // reportLoading(false), so `loading` never cleared and the page stayed on
    // the skeleton forever. The "Oops!" error screen must appear instead.
    await waitFor(() => {
      expect(screen.getByText(/Oops!/)).toBeDefined()
    }, { timeout: 5000 })

    // The thrown error message ("Item not found") must be shown
    expect(screen.getByText('Item not found')).toBeDefined()
  })

  it('renders owner sold modal on 403 report without crashing, and marks item sold', async () => {
    // Owner flow: item is active, a user id is stored, but the backend rejects
    // the "Report as Sold" POST with 403 (owner reporting own listing).
    // handleReportSold → setShowOwnerSoldModal(true) → the modal JSX renders,
    // which references handleOwnerMarkSold. Regression: that handler used to be
    // declared inside the fetch useEffect closure, so the modal render threw
    // `ReferenceError: handleOwnerMarkSold is not defined` and React unmounted
    // the app (blank screen). The modal appearing proves the render survives.
    localStorage.setItem('index_user_id', '999')
    const activeItem = { ...mockItem, status: 'active' }

    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(activeItem) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(mockRelated) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(mockReviews) })
      .mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: () => Promise.resolve({ detail: "You can't report your own listing." }),
      })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) })

    render(
      <MemoryRouter initialEntries={['/item/1']}>
        <Routes>
          <Route path="/item/:id" element={<ProductPage />} />
        </Routes>
      </MemoryRouter>
    )

    // Wait for product content
    await waitFor(() => {
      expect(screen.getByText('iPhone 13 128GB Gold')).toBeDefined()
    }, { timeout: 5000 })

    // Trigger the owner report path → 403 → owner modal opens
    fireEvent.click(screen.getByText('Report as Sold'))

    await waitFor(() => {
      expect(screen.getByText('This is your product')).toBeDefined()
    }, { timeout: 5000 })

    // Page did NOT blank out — product content still rendered
    expect(screen.getByText('iPhone 13 128GB Gold')).toBeDefined()

    // One-tap Mark as Sold → POST /sold → modal closes, status flips to sold
    fireEvent.click(screen.getByText('Mark as Sold'))
    await waitFor(() => {
      expect(screen.queryByText('This is your product')).toBeNull()
    }, { timeout: 5000 })
    await waitFor(() => {
      expect(screen.getByText('Sold')).toBeDefined()
    }, { timeout: 5000 })

    localStorage.removeItem('index_user_id')
  })
})
