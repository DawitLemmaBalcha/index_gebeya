// NB-53 regression: ops-console white screen (React error #31 — "Objects are
// not valid as a React child"). The backend used to send
// {"balance_stars": {"amount": N}}; the section must NEVER render a non-
// scalar balance as a JSX child. Same for ledger amounts.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import OpsPayments from '../sections/OpsPayments'

const fetchMock = vi.fn()

function jsonResponse(body) {
  return { ok: true, status: 200, json: () => Promise.resolve(body) }
}

function stubEndpoints({ balance, ledger = [] }) {
  fetchMock.mockImplementation((url) => {
    if (url === '/ops/payments/ledger') return Promise.resolve(jsonResponse(ledger))
    if (url === '/ops/payments/balance') return Promise.resolve(jsonResponse(balance))
    if (url === '/ops/payments/reconciliation') {
      return Promise.resolve(jsonResponse({ status: 'never run' }))
    }
    return Promise.resolve(jsonResponse({}))
  })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('OpsPayments balance rendering (object-as-child regression)', () => {
  it('does not crash when balance_stars is an object (the legacy buggy shape)', async () => {
    stubEndpoints({ balance: { balance_stars: { amount: 5 } } })
    render(<OpsPayments />)
    // Rendering {amount: 5} as a JSX child throws React error #31 — reaching
    // this assertion proves the defensive guard renders a fallback instead.
    await waitFor(() => expect(screen.getAllByText(/—/).length).toBeGreaterThan(0))
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument()
  })

  it('renders the numeric balance when balance_stars is a number', async () => {
    stubEndpoints({ balance: { balance_stars: 5 } })
    render(<OpsPayments />)
    await waitFor(() => expect(screen.getByText(/5/)).toBeInTheDocument())
  })

  it('renders a dash when balance_stars is missing', async () => {
    stubEndpoints({ balance: {} })
    render(<OpsPayments />)
    await waitFor(() => expect(screen.getAllByText(/—/).length).toBeGreaterThan(0))
  })
})

describe('OpsPayments ledger amount rendering (object-as-child regression)', () => {
  it('does not render "[object Object]" for legacy dict amounts', async () => {
    stubEndpoints({
      balance: { balance_stars: 5 },
      ledger: [
        {
          id: 'chg_1',
          date: 1750000000,
          amount: { amount: 150, nanostar_amount: 0 },
          transaction_type: 'invoice_payment',
          payload_prefix: 'b:',
          user_id: 111,
        },
      ],
    })
    render(<OpsPayments />)
    await waitFor(() => expect(screen.getByText('chg_1')).toBeInTheDocument())
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument()
  })

  it('renders the int amount for well-formed ledger rows', async () => {
    stubEndpoints({
      balance: { balance_stars: 5 },
      ledger: [
        {
          id: 'chg_2',
          date: 1750000000,
          amount: 150,
          transaction_type: 'invoice_payment',
          payload_prefix: 'b:',
          user_id: 111,
        },
      ],
    })
    render(<OpsPayments />)
    await waitFor(() => expect(screen.getByText('chg_2')).toBeInTheDocument())
    expect(screen.getByText('150')).toBeInTheDocument()
  })
})
