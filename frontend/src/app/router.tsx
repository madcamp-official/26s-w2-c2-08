import { createBrowserRouter, type RouteObject } from 'react-router-dom'

import { AppShell } from '../components/layout/AppShell'
import { FoundationPage } from './routes/FoundationPage'
import { NotFoundPage } from './routes/NotFoundPage'
import { RouteErrorBoundary } from './RouteErrorBoundary'

export const appRoutes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    errorElement: <RouteErrorBoundary />,
    children: [
      {
        index: true,
        element: <FoundationPage />,
      },
      {
        path: '*',
        element: <NotFoundPage />,
      },
    ],
  },
]

export const router = createBrowserRouter(appRoutes)
