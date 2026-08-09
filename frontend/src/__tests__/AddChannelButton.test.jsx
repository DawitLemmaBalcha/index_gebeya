import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import AddChannelButton from '../components/AddChannelButton'

/**
 * TECH-39: AddChannelButton contract (blueprint §2):
 * - default label "Add Channel", href deep link, target _blank,
 *   rel noopener noreferrer, accessible name == label
 * - label prop overrides the accessible name + text
 * - className prop overrides the anchor classes
 */
describe('AddChannelButton', () => {
  it('renders the deep link with default label, href, target and rel', () => {
    render(<AddChannelButton />)
    const link = screen.getByRole('link', { name: 'Add Channel' })
    expect(link).toHaveAttribute('href', 'https://t.me/IndexGebeyaBot?start=addchannel')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link).toHaveTextContent('Add Channel')
  })

  it('renders a custom label and keeps the accessible name equal to it', () => {
    render(<AddChannelButton label="Add Channel/Group" />)
    const link = screen.getByRole('link', { name: 'Add Channel/Group' })
    expect(link).toHaveTextContent('Add Channel/Group')
  })

  it('passes className through to the anchor', () => {
    render(<AddChannelButton className="custom-class-a custom-class-b" />)
    const link = screen.getByRole('link', { name: 'Add Channel' })
    expect(link).toHaveClass('custom-class-a')
    expect(link).toHaveClass('custom-class-b')
  })
})
