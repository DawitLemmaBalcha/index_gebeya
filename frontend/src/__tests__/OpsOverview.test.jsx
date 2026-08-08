// NB-50: Section 1 Overview — age-labeling unit tests (blueprint §5).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import OpsOverview, { ageLabel } from '../sections/OpsOverview'

const fetchMock = vi.fn()

function healthPayload({ generatedAt, services = {} }) {
  return {
    generated_at: generatedAt,
    services: {
      'services.api': { status: 'up', value: null, source: 'endpoint' },
      'services.listener': { status: 'up', value: null, source: 'heartbeat' },
      'bot.handler_error_rate': { status: 'unavailable', value: null, source: null, note: 'no data source' },
      ...services,
    },
  }
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('ageLabel', () => {
  it('labels fresh signals with seconds', () => {
    const now = Date.now()
    expect(ageLabel(new Date(now - 5000).toISOString(), now)).toBe('5s old')
  })

  it('labels signals older than 90s as stale', () => {
    const now = Date.now()
    expect(ageLabel(new Date(now - 95000).toISOString(), now)).toBe('stale')
  })

  it('returns a dash for missing generated_at', () => {
    expect(ageLabel(null, Date.now())).toBe('—')
  })
})

describe('OpsOverview rendering', () => {
  it('renders unavailable verbatim', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(healthPayload({ generatedAt: new Date().toISOString() })),
    })
    render(<OpsOverview />)
    await waitFor(() => expect(screen.getByText('unavailable')).toBeInTheDocument())
    expect(screen.getByText('no data source')).toBeInTheDocument()
  })

  it('labels stale signals from generated_at', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(healthPayload({
        generatedAt: new Date(Date.now() - 120000).toISOString(),
      })),
    })
    render(<OpsOverview />)
    await waitFor(() => expect(screen.getAllByText('stale').length).toBeGreaterThan(0))
  })

  it('shows an error state when the endpoint is unreachable', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 500, json: () => Promise.resolve({ detail: 'boom' }) })
    render(<OpsOverview />)
    await waitFor(() => expect(screen.getByText('Health unavailable')).toBeInTheDocument())
    expect(screen.getByText('boom')).toBeInTheDocument()
  })
})
