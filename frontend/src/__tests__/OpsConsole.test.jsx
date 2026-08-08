// NB-49: ops console shell tests — login flow, rail, section stubs.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import OpsConsole from '../pages/OpsConsole'

let meOk = false
const fetchMock = vi.fn()

beforeEach(() => {
  meOk = false
  fetchMock.mockReset()
  fetchMock.mockImplementation((url, opts) => {
    if (url === '/ops/auth/me') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(meOk ? { user: 'admin', role: 'admin' } : { detail: 'Not authenticated' }),
      })
    }
    if (url === '/ops/auth/login' && opts?.method === 'POST') {
      const body = JSON.parse(opts.body)
      if (body.username === 'admin' && body.password === 'secret') {
        meOk = true
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ user: 'admin', role: 'admin' }) })
      }
      return Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({ detail: 'Invalid credentials' }) })
    }
    if (url === '/ops/auth/logout' && opts?.method === 'POST') {
      meOk = false
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    }
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) })
  })
  vi.stubGlobal('fetch', fetchMock)
})

describe('OpsConsole shell', () => {
  it('shows the login form when unauthenticated', async () => {
    render(<OpsConsole />)
    expect(await screen.findByTestId('ops-login-form')).toBeInTheDocument()
  })

  it('logs in with valid credentials and renders the ten-section rail', async () => {
    render(<OpsConsole />)
    await screen.findByTestId('ops-login-form')
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'secret' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(screen.getByText(/signed in as admin/i)).toBeInTheDocument())
    for (const title of [
      'Overview', 'Catalog', 'Trust & Moderation', 'Users',
      'Alerts & Notifications', 'Monetization', 'Payments',
      'Settings & Flags', 'Audit', 'Support Toolkit',
    ]) {
      expect(screen.getByRole('button', { name: title })).toBeInTheDocument()
    }
  })

  it('rejects invalid credentials with an error message', async () => {
    render(<OpsConsole />)
    await screen.findByTestId('ops-login-form')
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText('Invalid credentials')).toBeInTheDocument()
  })

  it('renders the coming-soon stub for a deferred section', async () => {
    render(<OpsConsole />)
    await screen.findByTestId('ops-login-form')
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'secret' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => expect(screen.getByText(/signed in as admin/i)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Catalog' }))
    expect(screen.getByText(/Catalog — coming soon/i)).toBeInTheDocument()
  })
})
