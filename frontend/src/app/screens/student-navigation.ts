import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { TuiTabBar } from '@taiga-ui/addon-mobile';

@Component({
  selector: 'peerly-student-navigation',
  imports: [RouterLink, RouterLinkActive, TuiTabBar],
  template: `<nav tuiTabBar aria-label="Student navigation">
    <a
      tuiTabBarItem
      icon="@tui.compass"
      routerLink="/discover"
      routerLinkActive
      ariaCurrentWhenActive="page"
      >Discover</a
    >
    <a
      tuiTabBarItem
      icon="@tui.inbox"
      routerLink="/requests"
      routerLinkActive
      ariaCurrentWhenActive="page"
      >Requests</a
    >
    <a
      tuiTabBarItem
      icon="@tui.messages-square"
      routerLink="/chats"
      routerLinkActive
      ariaCurrentWhenActive="page"
      >Chats</a
    >
    <a
      tuiTabBarItem
      icon="@tui.user"
      routerLink="/profile"
      routerLinkActive
      ariaCurrentWhenActive="page"
      >Profile</a
    >
  </nav>`,
  styles: `
    :host {
      display: block;
      margin-block-start: auto;
      background: var(--tui-background-base);
    }
    nav {
      padding-block-end: env(safe-area-inset-bottom);
    }
  `,
})
export class StudentNavigation {}
