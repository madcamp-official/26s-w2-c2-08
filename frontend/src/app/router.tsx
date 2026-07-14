import { createBrowserRouter, type RouteObject } from 'react-router-dom'

import { AppShell } from '../components/layout/AppShell'
import { AccountPage } from '../features/auth/AccountPage'
import { LoginPage } from '../features/auth/LoginPage'
import { SignupPage } from '../features/auth/SignupPage'
import { CourseMaterialsPage } from '../features/course-workspace/CourseMaterialsPage'
import { CourseQnaPage } from '../features/course-workspace/CourseQnaPage'
import { CourseSummariesPage } from '../features/course-workspace/CourseSummariesPage'
import { CourseTranscriptsPage } from '../features/course-workspace/CourseTranscriptsPage'
import { CourseWorkspaceLayout } from '../features/course-workspace/CourseWorkspaceLayout'
import { AuthenticatedCourseArea } from '../features/courses/auth-guard'
import { CourseCreatePage } from '../features/courses/CourseCreatePage'
import { CourseDetailPage } from '../features/courses/CourseDetailPage'
import { CourseJoinPage } from '../features/courses/CourseJoinPage'
import { SessionCreatePage } from '../features/courses/SessionCreatePage'
import { SessionDetailPage } from '../features/courses/SessionDetailPage'
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
        path: 'signup',
        element: <SignupPage />,
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
            <CourseWorkspaceLayout />
          </AuthenticatedCourseArea>
        ),
        children: [
          {
            index: true,
            element: <CourseDetailPage />,
          },
          {
            path: 'materials',
            element: <CourseMaterialsPage />,
          },
          {
            path: 'transcripts',
            element: <CourseTranscriptsPage />,
          },
          {
            path: 'summaries',
            element: <CourseSummariesPage />,
          },
          {
            path: 'qna',
            element: <CourseQnaPage />,
          },
        ],
      },
      {
        path: 'courses/:courseId/sessions/new',
        element: (
          <AuthenticatedCourseArea>
            <SessionCreatePage />
          </AuthenticatedCourseArea>
        ),
      },
      {
        path: 'sessions/:sessionId',
        element: (
          <AuthenticatedCourseArea>
            <SessionDetailPage />
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
