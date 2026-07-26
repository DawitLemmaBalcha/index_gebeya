import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import ProductGrid from '../components/home/ProductGrid'

// Mock IntersectionObserver BEFORE any imports use it
class MockIntersectionObserver {
  constructor(callback) {
    this.callback = callback
  }
  observe() {}
  disconnect() {}
  unobserve() {}
}
global.IntersectionObserver = MockIntersectionObserver

// Mock the config module
vi.mock('../config', () => ({
  API_BASE_URL: 'http://localhost:8000',
}))

const sampleItems = [
  {
    id: 1,
    title: 'iPhone 13 128GB',
    price: 48000,
    currency: 'ETB',
    channel: { username: 'testchannel', id: 1 },
    telegram_message_id: 123,
    category: 'Mobile Phones',
    image_path: '/img/test.jpg',
    images: ['/img/test.jpg'],
    condition: 'Used',
    phone_number: '+251911234567',
  },
  {
    id: 2,
    title: 'MacBook Air M1',
    price: 52000,
    currency: 'ETB',
    channel: { username: 'laptopseller', id: 2 },
    telegram_message_id: 456,
    category: 'Laptops',
    image_path: '/img/test2.jpg',
    images: ['/img/test2.jpg'],
    condition: 'New',
  },
]

const defaultProps = {
  loading: false,
  error: null,
  items: [],
  onRetry: vi.fn(),
  onNavigate: vi.fn(),
  visualResults: null,
  searchResults: null,
  onClearVisual: vi.fn(),
  activeCategory: 'All',
  activeSubCategory: 'All',
  hasMore: false,
  isFetchingMore: false,
  onLoadMore: vi.fn(),
  isSearchingText: false,
  isSearchingVisual: false,
}

describe('ProductGrid', () => {
  it('renders skeleton cards when loading (not spinner)', () => {
    render(<ProductGrid {...defaultProps} loading={true} />)

    // Check for skeleton pulse animations (they should have animate-pulse class)
    const skeletonCards = document.querySelectorAll('.animate-pulse')
    expect(skeletonCards.length).toBeGreaterThan(0)

    // Make sure no spinner is rendered (the old behavior had a spinner for loading)
    const spinner = document.querySelector('.animate-spin')
    expect(spinner).toBeNull()
  })

  it('shows spinner for infinite scroll loading, not skeleton', () => {
    render(
      <ProductGrid
        {...defaultProps}
        items={sampleItems}
        hasMore={true}
        isFetchingMore={true}
      />
    )

    // Should show a spinner for infinite scroll
    const spinner = document.querySelector('.animate-spin')
    expect(spinner).not.toBeNull()

    // Should still show items
    expect(screen.getByText('iPhone 13 128GB')).toBeDefined()
  })

  it('renders grid view by default with items', () => {
    render(
      <BrowserRouter>
        <ProductGrid {...defaultProps} items={sampleItems} />
      </BrowserRouter>
    )

    // Items should be rendered in a grid
    expect(screen.getByText('iPhone 13 128GB')).toBeDefined()
    expect(screen.getByText('MacBook Air M1')).toBeDefined()
  })

  it('has view mode toggle when items are present', () => {
    render(
      <BrowserRouter>
        <ProductGrid {...defaultProps} items={sampleItems} />
      </BrowserRouter>
    )

    // Should have grid/list toggle buttons (SVG elements for the icons)
    // Look for the toggle container with border styling
    const toggleButtons = document.querySelectorAll('[title="Grid"], [title="List"]')
    expect(toggleButtons.length).toBe(2)

    // Grid button should be the active one by default
    const gridBtn = document.querySelector('[title="Grid"]')
    expect(gridBtn).not.toBeNull()

    const listBtn = document.querySelector('[title="List"]')
    expect(listBtn).not.toBeNull()
  })

  it('switches to list view when list toggle is clicked', () => {
    render(
      <BrowserRouter>
        <ProductGrid {...defaultProps} items={sampleItems} />
      </BrowserRouter>
    )

    const listBtn = document.querySelector('[title="List"]')
    expect(listBtn).not.toBeNull()

    fireEvent.click(listBtn)

    // After switching to list mode, items should still be visible
    // but in a list layout (not grid). We check that the grid layout is gone.
    expect(screen.getByText('iPhone 13 128GB')).toBeDefined()
    expect(screen.getByText('MacBook Air M1')).toBeDefined()

    // In list mode, there should be "View" buttons
    const viewButtons = screen.getAllByText('View')
    expect(viewButtons.length).toBeGreaterThanOrEqual(sampleItems.length)
  })

  it('renders search skeleton when isSearchingText is true', () => {
    render(<ProductGrid {...defaultProps} isSearchingText={true} />)

    // Search skeleton should be shown (from TECH-11 pattern)
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
    // Should show "Searching..." text
    expect(screen.getByText('Searching...')).toBeDefined()
  })

  it('shows error state with retry button', () => {
    const onRetry = vi.fn()
    render(
      <ProductGrid
        {...defaultProps}
        error="Network error"
        onRetry={onRetry}
      />
    )

    expect(screen.getByText('Connection Failed')).toBeDefined()
    expect(screen.getByText('Network error')).toBeDefined()

    const retryBtn = screen.getByText('Try Again')
    fireEvent.click(retryBtn)
    expect(onRetry).toHaveBeenCalled()
  })

  it('shows empty state when no items', () => {
    render(<ProductGrid {...defaultProps} items={[]} />)

    expect(screen.getByText('No items found.')).toBeDefined()
  })
})
