import { describe, it, expect } from 'vitest'
import { parseRepo } from './api'

describe('parseRepo', () => {
  it('splits a valid "owner/repo" string correctly', () => {
    const result = parseRepo('rayketcham-lab/gh-tracker')
    expect(result).toEqual({ owner: 'rayketcham-lab', repo: 'gh-tracker' })
  })

  it('handles single-segment owner and repo names', () => {
    const result = parseRepo('acme/widget')
    expect(result).toEqual({ owner: 'acme', repo: 'widget' })
  })

  it('throws when the string has no slash', () => {
    expect(() => parseRepo('noslash')).toThrow('Invalid repo format: noslash')
  })

  it('throws when the string has more than one slash', () => {
    expect(() => parseRepo('a/b/c')).toThrow('Invalid repo format: a/b/c')
  })

  it('preserves case in owner and repo', () => {
    const result = parseRepo('MyOrg/MyRepo')
    expect(result).toEqual({ owner: 'MyOrg', repo: 'MyRepo' })
  })
})
