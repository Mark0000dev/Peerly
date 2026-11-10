import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { TuiLink } from '@taiga-ui/core';

@Component({
  selector: 'peerly-student-navigation',
  imports: [RouterLink, RouterLinkActive, TuiLink],
  template: `<nav aria-label="Student navigation">
    <a tuiLink routerLink="/discover" routerLinkActive="active" ariaCurrentWhenActive="page"
      >Discover</a
    >
    <a tuiLink routerLink="/requests" routerLinkActive="active" ariaCurrentWhenActive="page"
      >Requests</a
    >
    <a tuiLink routerLink="/chats" routerLinkActive="active" ariaCurrentWhenActive="page">Chats</a>
    <a tuiLink routerLink="/profile" routerLinkActive="active" ariaCurrentWhenActive="page"
      >Profile</a
    >
  </nav>`,
  styles: `
    nav {
      display: flex;
      flex-wrap: wrap;
      gap: 1rem;
    }
  `,
})
export class StudentNavigation {}
