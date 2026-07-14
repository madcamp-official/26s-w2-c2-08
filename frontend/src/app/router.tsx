import { createBrowserRouter, type RouteObject } from 'react-router-dom'

import { AppShell } from '../components/layout/AppShell'
import { AccountPage } from '../features/auth/AccountPage'
import { LoginPage } from '../features/auth/LoginPage'
import { AuthenticatedCourseArea } from '../features/courses/auth-guard'
import { CourseCreatePage } from '../features/courses/CourseCreatePage'
import { CourseDetailPage } from '../features/courses/CourseDetailPage'
import { CourseJoinPage } from '../features/courses/CourseJoinPage'
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
        path: 'courses/new',
        element: (
          <AuthenticatedCourseArea>
            <CourseCreatePage />
          </AuthenticatedCourseArea>
        ),
      },
      {
        path: 'courses/join',
        element: (
          <AuthenticatedCourseArea>
            <CourseJoinPage />
          </AuthenticatedCourseArea>
        ),
      },
      {
        path: 'courses/:courseId',
        element: (
          <AuthenticatedCourseArea>
            <CourseDetailPage />
          </AuthenticatedCourseArea>
        ),
      },
      {
        path: '*',
        element: <NotFoundPage />,
      },
    ],
  },
]

export const router = createBrowserRouter(appRoutes)
