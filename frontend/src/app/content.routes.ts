import type { ProfilePage } from './screens/onboarding/profile-page';
import type { SupportContact } from './screens/help/contact/support-contact';
import type { NotificationPreferences } from './screens/notifications/notification-preferences';
import type { Onboarding } from './screens/onboarding/onboarding';
import { HttpClient } from '@angular/common/http';
import { ApplicationRef, DestroyRef, inject, provideEnvironmentInitializer } from '@angular/core';
import { watchChanges } from './screens/changes';
import type { Routes } from '@angular/router';
import { provideTanStackQuery, QueryClient } from '@tanstack/angular-query-experimental';
export const contentRoutes: Routes = [
  {
    path: '',
    providers: [
      provideTanStackQuery(
        new QueryClient({
          defaultOptions: {
            queries: { staleTime: 30_000, retry: false },
            mutations: { retry: false },
          },
        }),
      ),
      provideEnvironmentInitializer(() => {
        const application = inject(ApplicationRef);
        const destroy = inject(DestroyRef);
        const http = inject(HttpClient);
        const client = inject(QueryClient);
        // A long-lived HTTP stream must not prevent the initial stable boot.
        // This gate runs once; reconnects use only transport/identity lifetime.
        void application.whenStable().then(() => {
          if (!destroy.destroyed) watchChanges(http, client, destroy);
        });
      }),
    ],
    children: [
      {
        path: 'profile/blocks',
        data: { editor: 'blocks' },
        title: 'Blocked people · Peerly',
        loadComponent: async () => (await import('./screens/onboarding/profile-page')).ProfilePage,
      },
      {
        path: 'profile/edit',
        data: { editor: 'profile' },
        title: 'Edit profile · Peerly',
        canDeactivate: [(component: Readonly<ProfilePage>) => component.canLeave()],
        loadComponent: async () => (await import('./screens/onboarding/profile-page')).ProfilePage,
      },
      {
        path: 'profile/goal',
        data: { editor: 'goal' },
        title: 'Study goal · Peerly',
        canDeactivate: [(component: Readonly<ProfilePage>) => component.canLeave()],
        loadComponent: async () => (await import('./screens/onboarding/profile-page')).ProfilePage,
      },
      {
        path: 'profile/help',
        data: { editor: 'help' },
        title: 'Help areas · Peerly',
        canDeactivate: [(component: Readonly<ProfilePage>) => component.canLeave()],
        loadComponent: async () => (await import('./screens/onboarding/profile-page')).ProfilePage,
      },
      {
        path: 'profile/visibility',
        data: { editor: 'visibility' },
        title: 'Profile visibility · Peerly',
        canDeactivate: [(component: Readonly<ProfilePage>) => component.canLeave()],
        loadComponent: async () => (await import('./screens/onboarding/profile-page')).ProfilePage,
      },
      {
        path: 'profile',
        title: 'Profile · Peerly',
        canDeactivate: [(component: Readonly<ProfilePage>) => component.canLeave()],
        loadComponent: async () => (await import('./screens/onboarding/profile-page')).ProfilePage,
      },
      {
        path: 'help/contact/status',
        title: 'Support status · Peerly',
        loadComponent: async () =>
          (await import('./screens/help/contact/support-recovery')).SupportRecovery,
      },
      {
        path: 'help/contact',
        title: 'Contact support · Peerly',
        canDeactivate: [(component: Readonly<SupportContact>) => component.canLeave()],
        loadComponent: async () =>
          (await import('./screens/help/contact/support-contact')).SupportContact,
      },
      {
        path: 'profile/notifications',
        title: 'Notifications · Peerly',
        canDeactivate: [(component: Readonly<NotificationPreferences>) => component.canLeave()],
        loadComponent: async () =>
          (await import('./screens/notifications/notification-preferences'))
            .NotificationPreferences,
      },
      {
        path: 'account/delete',
        title: 'Delete account · Peerly',
        loadComponent: async () => (await import('./screens/account/delete-account')).DeleteAccount,
      },
      {
        path: 'account/deletion-status',
        title: 'Deletion status · Peerly',
        loadComponent: async () =>
          (await import('./screens/account/deletion-status')).DeletionStatus,
      },
      {
        path: 'operator/conversations',
        title: 'Conversation inspector · Peerly',
        loadComponent: async () =>
          (await import('./screens/operator/operator-conversation')).OperatorConversation,
      },
      {
        path: 'operator/reports',
        title: 'Operator reports · Peerly',
        loadComponent: async () =>
          (await import('./screens/operator/operator-reports')).OperatorReports,
      },
      {
        path: 'operator/accounts',
        title: 'Operator accounts · Peerly',
        loadComponent: async () => (await import('./screens/operator/operator')).Operator,
      },
      {
        path: 'discover',
        title: 'Discover · Peerly',
        loadComponent: async () => (await import('./screens/discovery/discovery')).Discovery,
      },
      {
        path: 'requests',
        title: 'Requests · Peerly',
        loadComponent: async () => (await import('./screens/requests/requests')).Requests,
      },
      {
        path: 'chats',
        title: 'Chats · Peerly',
        loadComponent: async () => (await import('./screens/chats/chats')).Chats,
      },
      {
        path: 'people/:personId',
        title: 'Profile · Peerly',
        loadComponent: async () => (await import('./screens/person/person')).Person,
      },
      {
        path: 'onboarding',
        canDeactivate: [(component: Readonly<Onboarding>) => component.canLeave()],
        title: 'Sign in · Peerly',
        loadComponent: async () => (await import('./screens/onboarding/onboarding')).Onboarding,
      },
      {
        path: 'terms',
        title: 'Terms of Use · Peerly',
        loadComponent: async () => (await import('./screens/policy/policy')).Policy,
      },
      {
        path: 'privacy',
        title: 'Privacy Policy · Peerly',
        loadComponent: async () => (await import('./screens/policy/policy')).Policy,
      },
      {
        path: 'help',
        title: 'Help · Peerly',
        loadComponent: async () => (await import('./screens/help/help')).Help,
      },
    ],
  },
];
