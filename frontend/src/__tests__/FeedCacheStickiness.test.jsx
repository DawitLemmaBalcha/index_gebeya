import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// House pattern (BrowseSeam.test.jsx): mock config + analytics BEFORE import.
vi.mock('../config', () => ({
  API_BASE_URL: '',
}))

vi.mock('../utils/analytics', () => ({
  getAnalyticsHeaders: () => ({}),
}))

let useShop
let fetchMock

function Harness() {
  const shop = useShop()
  return (
    <div>
      <button onClick={() => shop.fetchMore()}>load-more</button>
      <button onClick={() => shop.retry()}>retry</button>
      {shop.displayItems.map((i) => (
        <div key={i.id} data-testid="item">{i.title}</div>
      ))}
      <div data-testid="has-more">{String(shop.hasMore)}</div>
    </div>
  )
}

const makeItem = (id) => ({
  id,
  title: `Item ${id}`,
  price: 100,
  currency: 'ETB',
  image_path: '/img/x.jpg',
  images: ['/img/x.jpg'],
  is_boosted: false,
})

const LIMIT = 20
const items1toN = (n) => Array.from({ length: n }, (_, i) => makeItem(i + 1))

beforeEach(async () => {
  // Fresh module registry -> _feedCache starts null (TECH-10 module cache
  // would otherwise leak between tests).
  vi.resetModules()
  fetchMock = vi.fn()
  global.fetch = fetchMock
  localStorage.clear()
  useShop = (await import('../hooks/useShop')).useShop
})

describe('Feed cache stickiness (TECH-10 regression)', () => {
  it('REGRESSION: revisiting Explore with a stale hasMore=false cache must refetch and re-derive hasMore', async () => {
    let feedCalls = 0
    fetchMock.mockImplementation((url) => {
      const u = String(url)
      if (u.includes('/feed/foryou')) {
        feedCalls += 1
        // First visit: catalog is small (12 items < LIMIT 20) -> hasMore
        // false. Second visit: catalog has grown -> a full page of 20.
        const items = feedCalls === 1 ? items1toN(12) : items1toN(LIMIT)
        return Promise.resolve({ ok: true, json: () => Promise.resolve(items) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    })

    // First visit — the feed returns only 12 items (limited set).
    const first = render(<Harness />)
    await waitFor(() => expect(screen.getAllByTestId('item')).toHaveLength(12))
    expect(screen.getByTestId('has-more').textContent).toBe('false')

    // Navigate away (hub/welcome round trip) — Home unmounts.
    first.unmount()

    // Second visit — same JS session (module cache NOT reset). The cache
    // hit must NOT freeze the feed: page 0 is re-derived from the server,
    // hasMore tracks the grown catalog, and scrolling can continue.
    render(<Harness />)
    await waitFor(() => expect(screen.getAllByTestId('item')).toHaveLength(LIMIT))
    expect(screen.getByTestId('has-more').textContent).toBe('true')
    expect(feedCalls).toBeGreaterThanOrEqual(2)

    // Scrolling continues: fetchMore issues a page-2 request.
    fireEvent.click(screen.getByText('load-more'))
    await waitFor(() => expect(feedCalls).toBeGreaterThanOrEqual(3))
  })

  it('REGRESSION: pull-to-refresh after exhaustion refetches page 0 WITHOUT the stale exclude and re-derives hasMore', async () => {
    let feedCalls = 0
    fetchMock.mockImplementation((url) => {
      const u = String(url)
      if (u.includes('/feed/foryou')) {
        feedCalls += 1
        if (feedCalls === 1) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(items1toN(LIMIT)) })
        }
        if (feedCalls === 2) {
          // page 2: only 5 items left -> hasMore flips false
          return Promise.resolve({ ok: true, json: () => Promise.resolve(items1toN(5)) })
        }
        // refresh after exhaustion: a full page again
        return Promise.resolve({ ok: true, json: () => Promise.resolve(items1toN(LIMIT)) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    })

    const first = render(<Harness />)
    await waitFor(() => expect(screen.getAllByTestId('item')).toHaveLength(LIMIT))
    expect(screen.getByTestId('has-more').textContent).toBe('true')

    // Scroll to the end -> 5 more items -> hasMore false.
    fireEvent.click(screen.getByText('load-more'))
    await waitFor(() => expect(screen.getAllByTestId('item')).toHaveLength(LIMIT + 5))
    expect(screen.getByTestId('has-more').textContent).toBe('false')

    // Pull-to-refresh: the page-0 refetch must drop the accumulated
    // exclude (25 seen ids) and re-derive hasMore=true from the current
    // catalog — otherwise the refresh returns 0 new items and the feed
    // stays frozen.
    fireEvent.click(screen.getByText('retry'))
    await waitFor(() => expect(screen.getByTestId('has-more').textContent).toBe('true'))

    const refreshCall = fetchMock.mock.calls
      .map(([url]) => String(url))
      .filter((u) => u.includes('/feed/foryou'))
      .pop()
    expect(refreshCall).toContain('offset=0')
    expect(refreshCall).not.toContain('exclude=')
  })
})
