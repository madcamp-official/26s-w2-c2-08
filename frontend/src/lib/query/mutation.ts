import { normalizeApiError } from '../../api/errors'

export type MutationFunction<TData, TVariables> = (
  variables: TVariables,
) => Promise<TData>

export function withApiErrorNormalization<TData, TVariables>(
  mutation: MutationFunction<TData, TVariables>,
): MutationFunction<TData, TVariables> {
  return async (variables) => {
    try {
      return await mutation(variables)
    } catch (error) {
      throw normalizeApiError(error)
    }
  }
}
