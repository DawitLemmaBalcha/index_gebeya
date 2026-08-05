import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import ItemCard from '../components/ItemCard'

// House pattern (ProductGrid.test.jsx): mock config + analytics BEFORE import.
vi.mock('../config', () => ({
  API_BASE_URL: '',
}))

vi.mock('../utils/analytics', () => ({
  getAnalyticsHeaders: () => ({}),
}))

const browseItem = {
  id: 1,
  title: 'iPhone 13 128GB',
  price: 48000,
  currency: 'ETB',
  category: 'Mobile Phones',
  subcategory: 'Cases',
  channel: { username: 'testchannel', id: 1 },
  telegram_message_id: 123,
  image_path: '/img/test.jpg',
  images: ['/img/test.jpg'],
  is_boosted: true,
}

const organicItem = {
  ...browseItem,
  id: 2,
  title: 'Samsung Galaxy S21',
  is_boosted: false,
}

let useShop
let fetchMock

function Harness() {
  const shop = useShop()
  return (
    <div>
      <button onClick={() => shop.setActiveCategory('Mobile Phones')}>cat-phones</button>
      <button onClick={() => shop.setActiveCategory('Laptops & Computers')}>cat-laptops</button>
      <button onClick={() => shop.setActiveCategory('All')}>cat-all</button>
      <button onClick={() => shop.setActiveSubCategory('Cases')}>sub-cases</button>
      {/* CategorySheet seam: handleSelectSubcategory batches category +
          subcategory in one handler (useShop's own subcategory reset then
          lands on "All"). */}
      <button onClick={() => { shop.setActiveCategory('Mobile Phones'); shop.setActiveSubCategory('All'); }}>cat-phones-sheet</button>
      <input
        data-testid="search-input"
        value={shop.searchQuery}
        onChange={(e) => shop.setSearchQuery(e.target.value)}
      />
      {shop.displayItems.map((i) => (
        <div key={i.id} data-testid="item">{i.title}</div>
      ))}
    </div>
  )
}

beforeEach(async () => {
  // Fresh module registry -> _feedCache starts null (TECH-10 module cache
  // would otherwise leak between tests).
  vi.resetModules()
  fetchMock = vi.fn()
  global.fetch = fetchMock
  localStorage.clear()
  useShop = (await import('../hooks/useShop')).useShop
})

describe('BrowseSeam', () => {
  it('browse mode hits /items/browse with encoded category and renders items', async () => {
    fetchMock.mockImplementation((url) => {
      const u = String(url)
      if (u.includes('/items/browse')) {
        expect(u).toBe(
          `/items/browse?category=${encodeURIComponent('Mobile Phones')}&limit=20&offset=0`
        )
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [browseItem], total: 1 }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    })

    render(<Harness />)
    fireEvent.click(screen.getByText('cat-phones'))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/items/browse'),
        expect.anything()
      )
    })
    expect(await screen.findByText('iPhone 13 128GB')).toBeDefined()
    // Browse results unwrap data.items (not the bare feed array).
    expect(screen.getAllByTestId('item')).toHaveLength(1)
  })

  it('neutral "All" mode hits /feed/foryou (feed untouched)', async () => {
    fetchMock.mockImplementation((url) => {
      const u = String(url)
      if (u.includes('/feed/foryou')) {
        expect(u).toBe('/feed/foryou?limit=20&offset=0')
        return Promise.resolve({ ok: true, json: () => Promise.resolve([organicItem]) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) })
    })

    render(<Harness />)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/feed/foryou'),
        expect.anything()
      )
    })
    expect(await screen.findByText('Samsung Galaxy S21')).toBeDefined()
    // Neutral mode must NEVER hit the browse seam.
    const browseCalls = fetchMock.mock.calls.filter(([u]) => String(u).includes('/items/browse'))
    expect(browseCalls).toHaveLength(0)
  })

  it('switching category refetches browse with the new category', async () => {
    fetchMock.mockImplementation((url) => {
      const u = String(url)
      if (u.includes('/items/browse')) {
        if (u.includes(encodeURIComponent('Mobile Phones'))) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [browseItem], total: 1 }) })
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [organicItem], total: 1 }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    })

    render(<Harness />)
    fireEvent.click(screen.getByText('cat-phones'))
    await waitFor(() => expect(screen.getByText('iPhone 13 128GB')).toBeDefined())

    fireEvent.click(screen.getByText('cat-laptops'))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(encodeURIComponent('Laptops & Computers')),
        expect.anything()
      )
    })
    expect(await screen.findByText('Samsung Galaxy S21')).toBeDefined()
    expect(screen.queryByText('iPhone 13 128GB')).toBeNull()
  })

  it('subcategory switch does NOT refetch', async () => {
    fetchMock.mockImplementation((url) => {
      const u = String(url)
      if (u.includes('/items/browse')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [browseItem], total: 1 }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    })

    render(<Harness />)
    fireEvent.click(screen.getByText('cat-phones'))
    await waitFor(() => expect(screen.getByText('iPhone 13 128GB')).toBeDefined())

    const browseCallsBefore = fetchMock.mock.calls.filter(([u]) => String(u).includes('/items/browse')).length
    expect(browseCallsBefore).toBe(1)

    fireEvent.click(screen.getByText('sub-cases'))

    // Subcategory filtering stays client-side — no new network request.
    expect(fetchMock.mock.calls.filter(([u]) => String(u).includes('/items/browse')).length).toBe(1)
    expect(screen.getByText('iPhone 13 128GB')).toBeDefined()
  })

  it('ItemCard renders the ⚡ Boosted badge from a browse item with is_boosted: true', () => {
    render(<ItemCard item={browseItem} apiUrl="" onSelect={vi.fn()} />)
    render(<ItemCard item={organicItem} apiUrl="" onSelect={vi.fn()} />)

    // Exactly ONE badge on screen: the boosted card's; the organic card's
    // is_boosted: false must NOT render a second one.
    expect(screen.getAllByText('⚡ Boosted')).toHaveLength(1)
  })

  it('REGRESSION: stale text search must not mask browse results (feed → search → browse user flow)', async () => {
    // Real user session (api logs): /feed/foryou → POST /search/ → then
    // /items/browse. The browse response updates `items`, but if a stale
    // searchResults overrides displayItems, the screen keeps rendering the
    // old search results — boosted item 952 never appears pinned/badged.
    const boostedPhone = { ...browseItem, id: 952, title: 'BLU G 34', subcategory: 'Other', is_boosted: true }
    const organicPhone = { ...organicItem, id: 953, title: 'Organic Phone', subcategory: 'Android Phones', is_boosted: false }
    const searchOnlyItem = { ...organicItem, id: 900, title: 'Search-Only Item', is_boosted: false }

    fetchMock.mockImplementation((url) => {
      const u = String(url)
      if (u.includes('/items/browse')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [boostedPhone, organicPhone], total: 2 }) })
      }
      if (u.includes('/search/')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [searchOnlyItem], total: 1 }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    })

    render(<Harness />)

    // 1. User performs a text search (debounced 600ms) — results render.
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'blu' } })
    await waitFor(() => expect(screen.getByText('Search-Only Item')).toBeDefined(), { timeout: 3000 })
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/search/'), expect.anything())

    // 2. User opens the CategorySheet and picks Mobile Phones (the sheet
    //    batches category + subcategory in one handler — cat-phones-sheet).
    fireEvent.click(screen.getByText('cat-phones-sheet'))

    // 3. The browse page must take over the screen: boosted item FIRST,
    //    stale search results GONE.
    await waitFor(() => expect(screen.getByText('BLU G 34')).toBeDefined(), { timeout: 3000 })
    const renderedTitles = screen.getAllByTestId('item').map((el) => el.textContent)
    expect(renderedTitles[0]).toBe('BLU G 34')
    expect(screen.queryByText('Search-Only Item')).toBeNull()
  })
})
