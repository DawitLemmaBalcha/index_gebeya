import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import ItemCard from '../components/ItemCard'

// House pattern (BrowseSeam.test.jsx / ProductGrid.test.jsx): mock config +
// analytics BEFORE importing the component.
vi.mock('../config', () => ({
  API_BASE_URL: '',
}))

vi.mock('../utils/analytics', () => ({
  getAnalyticsHeaders: () => ({}),
}))

function boostedCard(overrides = {}) {
  return {
    id: 1,
    title: 'BLU G 34',
    price: 48000,
    currency: 'ETB',
    category: 'Mobile Phones',
    channel: { username: 'testchannel', id: 1 },
    telegram_message_id: 123,
    image_path: '/img/test.jpg',
    images: ['/img/test.jpg'],
    condition: 'Used',
    is_boosted: true,
    ...overrides,
  }
}

describe('ItemCard badge layout (BUG 2 — boosted/condition collision)', () => {
  it('boosted badge sits far-left (left-2) with the condition badge rendered — no overlap', () => {
    render(<ItemCard item={boostedCard()} apiUrl="" onSelect={vi.fn()} />)

    const boostedBadge = screen.getByText('⚡ Boosted')
    // FAR-LEFT corner: must be `left-2`, never the old colliding `left-16`.
    expect(boostedBadge.className).toContain('left-2')
    expect(boostedBadge.className).not.toContain('left-16')
    // Condition badge still renders at its own corner (untouched).
    expect(screen.getByText('Used')).toBeDefined()
  })

  it('match badge stacks BELOW the boosted badge (top-9) when both are present', () => {
    render(
      <ItemCard item={boostedCard({ total_score: 0.8 })} apiUrl="" onSelect={vi.fn()} />
    )

    const boostedBadge = screen.getByText('⚡ Boosted')
    expect(boostedBadge.className).toContain('left-2')
    expect(boostedBadge.className).not.toContain('left-16')

    const matchBadge = screen.getByText('BEST MATCH')
    // Stacked vertically under the boosted badge — never overlapping.
    expect(matchBadge.className).toContain('top-9')
    expect(matchBadge.className).toContain('left-2')
  })

  it('unboosted match badge stays at top-2 left-2 (unchanged when not boosted)', () => {
    render(
      <ItemCard
        item={boostedCard({ is_boosted: false, total_score: 0.5 })}
        apiUrl=""
        onSelect={vi.fn()}
      />
    )

    const matchBadge = screen.getByText('High Match')
    expect(matchBadge.className).toContain('top-2')
    expect(matchBadge.className).toContain('left-2')
    expect(screen.queryByText('⚡ Boosted')).toBeNull()
  })
})

describe('ItemCard condition/location from API (NB-17/19)', () => {
  it('renders a real extracted condition (New) instead of the Used fallback', () => {
    render(<ItemCard item={boostedCard({ condition: 'New' })} apiUrl="" onSelect={vi.fn()} />)
    expect(screen.getByText('New')).toBeDefined()
    expect(screen.queryByText('Used')).toBeNull()
  })

  it('renders the extracted location line', () => {
    render(
      <ItemCard item={boostedCard({ location: 'Bole' })} apiUrl="" onSelect={vi.fn()} />
    )
    expect(screen.getByText('Bole')).toBeDefined()
  })
})
