export type PollableJobStatus = 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'

export function pollingIntervalForJob(
  status: PollableJobStatus | undefined,
): number | false {
  if (status === 'PENDING') {
    return 1_500
  }

  if (status === 'RUNNING') {
    return 1_000
  }

  return false
}
