import { QueryClientProvider } from '@tanstack/react-query'
import { type ReactNode, useState } from 'react'

import { ToastProvider } from '../components/feedback/ToastProvider'
import { createQueryClient } from '../lib/query/query-client'

interface AppProvidersProps {
  children: ReactNode
}

export function AppProviders({ children }: AppProvidersProps) {
  const [queryClient] = useState(createQueryClient)

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  )
}
