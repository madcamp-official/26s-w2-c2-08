import { ApiError } from '../../api/errors'
import type { StatePanelKind } from './StatePanel'

export function statePanelKindForApiError(error: unknown): StatePanelKind {
  if (!(error instanceof ApiError)) {
    return 'error'
  }

  switch (error.kind) {
    case 'unauthorized':
      return 'unauthorized'
    case 'forbidden':
      return 'forbidden'
    case 'not-found':
      return 'not-found'
    case 'conflict':
      return 'conflict'
    case 'validation':
      return 'validation'
    default:
      return 'error'
  }
}
