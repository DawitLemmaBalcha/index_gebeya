import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useRefetchOnActivation } from '../hooks/useRefetchOnActivation'

/**
 * TECH-39: useRefetchOnActivation(active, fn) contract (blueprint §2):
 * - mount with active=true runs the effect once → fn() once
 * - hidden tabs never fetch
 * - activation (false→true) refetches
 * - stable deps → no refetch on re-render while active stays true;
 *   changing fn identity while active → one additional call
 */
describe('useRefetchOnActivation', () => {
  it('mounts active → calls fn exactly once', () => {
    const fn = vi.fn()
    renderHook(({ active, fn }) => useRefetchOnActivation(active, fn), {
      initialProps: { active: true, fn },
    })
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('activation (false→true) refetches; each flip adds one call', () => {
    const fn = vi.fn()
    const { rerender } = renderHook(({ active, fn }) => useRefetchOnActivation(active, fn), {
      initialProps: { active: false, fn },
    })
    expect(fn).not.toHaveBeenCalled()

    rerender({ active: true, fn })
    expect(fn).toHaveBeenCalledTimes(1)

    rerender({ active: false, fn })
    expect(fn).toHaveBeenCalledTimes(1)

    rerender({ active: true, fn })
    expect(fn).toHaveBeenCalledTimes(2)
  })

  it('hidden tab never fetches — even across re-renders', () => {
    const fn = vi.fn()
    const { rerender } = renderHook(({ active, fn }) => useRefetchOnActivation(active, fn), {
      initialProps: { active: false, fn },
    })
    rerender({ active: false, fn })
    rerender({ active: false, fn })
    expect(fn).not.toHaveBeenCalled()
  })

  it('stable deps → no extra calls while active; fn identity change while active → one call', () => {
    const fn = vi.fn()
    const { rerender } = renderHook(({ active, fn }) => useRefetchOnActivation(active, fn), {
      initialProps: { active: true, fn },
    })
    expect(fn).toHaveBeenCalledTimes(1)

    // Same active + same fn identity → no loop
    rerender({ active: true, fn })
    rerender({ active: true, fn })
    expect(fn).toHaveBeenCalledTimes(1)

    // fn identity change while active → one additional call (documented contract)
    const fn2 = vi.fn()
    rerender({ active: true, fn: fn2 })
    expect(fn2).toHaveBeenCalledTimes(1)
  })
})
