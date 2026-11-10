import type { Routes } from '@angular/router';
export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    title: 'Peerly · Find someone to study with',
    loadComponent: async () => (await import('./screens/home/home')).Home,
  },
  { path: '', loadChildren: async () => (await import('./content.routes')).contentRoutes },
  { path: '**', redirectTo: '' },
];
