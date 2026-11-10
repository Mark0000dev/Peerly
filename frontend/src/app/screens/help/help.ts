import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TuiButton, TuiLink } from '@taiga-ui/core';

@Component({
  selector: 'app-help',
  imports: [RouterLink, TuiButton, TuiLink],
  template: `<main>
    <a tuiLink routerLink="/">Peerly home</a>
    <h1>Help and contact</h1>
    <h2>My APU email isn’t accepted</h2>
    <p>
      Use your student address ending in &#64;mail.apu.edu.my. Other APU addresses can’t be used.
    </p>
    <h2>The code doesn’t arrive</h2>
    <p>
      Check Junk and your university email quarantine. APU’s email filter may hold a code before it
      reaches your Outlook inbox. The email service accepting a message does not confirm inbox
      delivery. On the verification screen, check status and resend only when it becomes available.
      Open
      <a
        tuiLink
        href="https://security.microsoft.com/quarantine"
        target="_blank"
        rel="noopener noreferrer"
        >Microsoft quarantine</a
      >
      if your university account has access. Available actions depend on APU’s policy: request
      release if offered. If access is denied or release needs an administrator, contact APU IT. If
      you still cannot find a code, contact support below.
    </p>
    <h2>My APU email is already in use</h2>
    <p>Try the Google account you used before. We don’t move or combine accounts automatically.</p>
    <h2>I can’t sign in</h2>
    <p>Try Google sign-in again in your browser. Keep any reference shown with the error.</p>
    <nav aria-label="Access recovery">
      <a tuiButton routerLink="/help/contact">Contact support</a>
      <a tuiLink routerLink="/help/contact/status">Check a support request</a>
      <a tuiButton routerLink="/onboarding">Back to sign-in</a>
    </nav>
    <p>
      <a tuiLink routerLink="/terms">Terms of Use</a> ·
      <a tuiLink routerLink="/privacy">Privacy Policy</a>
    </p>
  </main>`,
  styles: `
    main {
      max-inline-size: 44rem;
      padding: 1.5rem;
      margin-inline: auto;
      overflow-wrap: anywhere;
    }
    nav {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 1rem;
    }
    nav a {
      max-inline-size: 100%;
      white-space: normal;
      block-size: auto;
      min-block-size: var(--tui-height-l);
    }
    h1 {
      font: var(--tui-typography-heading-h3);
    }
    h2 {
      font: var(--tui-typography-heading-h6);
      margin-block-start: 2rem;
    }
  `,
})
export class Help {}
