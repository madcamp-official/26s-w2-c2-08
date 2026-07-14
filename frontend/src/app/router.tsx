import { createBrowserRouter, type RouteObject } from 'react-router-dom'

import { AppShell } from '../components/layout/AppShell'
import { AccountPage } from '../features/auth/AccountPage'
import { LoginPage } from '../features/auth/LoginPage'
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
        path: 'login',
        element: <LoginPage />,
      },
      {
        path: 'account',
        element: <AccountPage />,
      },
      {
        path: '*',
        element: <NotFoundPage />,
      },
    ],
  },
]

export const router = createBrowserRouter(appRoutes)
