import { Component, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TuiLink } from '@taiga-ui/core';
import { TuiAccordion } from '@taiga-ui/kit';
import { TuiCardLarge } from '@taiga-ui/layout';
import { PublicHeader } from '../public-header';
import { PublicFooter } from '../public-footer';
import { SupportContact } from './contact/support-contact';

@Component({
  selector: 'app-help',
  imports: [
    RouterLink,
    TuiLink,
    TuiAccordion,
    TuiCardLarge,
    PublicHeader,
    PublicFooter,
    SupportContact,
  ],
  template: `<peerly-public-header />
    <main>
      <h1>Help and contact</h1>
      <div class="columns">
        <section aria-labelledby="help-questions">
          <h2 id="help-questions">How can we help?</h2>
          <tui-accordion [closeOthers]="false">
            <button tuiAccordion type="button">My APU email isn’t accepted</button>
            <tui-expand
              ><p>
                Use your student address ending in &#64;mail.apu.edu.my. Other APU addresses can’t
                be used.
              </p></tui-expand
            >
            <button [tuiAccordion]="true" type="button">The code doesn’t arrive</button>
            <tui-expand
              ><p>
                Check Junk and your university email quarantine. APU’s email filter may hold a code
                before it reaches your Outlook inbox. The email service accepting a message does not
                confirm inbox delivery. On the verification screen, check status and resend only
                when it becomes available. Open
                <a
                  tuiLink
                  href="https://security.microsoft.com/quarantine"
                  target="_blank"
                  rel="noopener noreferrer"
                  >Microsoft quarantine</a
                >
                if your university account has access. Available actions depend on APU’s policy:
                request release if offered. If access is denied or release needs an administrator,
                contact APU IT. If you still cannot find a code, contact support below.
              </p></tui-expand
            >
            <button tuiAccordion type="button">My APU email is already in use</button>
            <tui-expand
              ><p>
                Try the Google account you used before. We don’t move or combine accounts
                automatically.
              </p></tui-expand
            >
            <button tuiAccordion type="button">I can’t sign in</button>
            <tui-expand
              ><p>
                Try Google sign-in again in your browser. Keep any reference shown with the error.
              </p>
              <a tuiLink routerLink="/onboarding">Back to sign-in</a>
            </tui-expand>
            <button tuiAccordion type="button">How do I delete my account?</button>
            <tui-expand
              ><p>Open Profile and choose Delete account.</p>
              <a tuiLink routerLink="/account/delete">Delete your account</a>
            </tui-expand>
          </tui-accordion>
          <p><a tuiLink routerLink="/help/contact/status">Check a support request</a></p>
        </section>
        <section tuiCardLarge appearance="floating" aria-label="Contact support">
          <app-support-contact [embedded]="true" />
        </section>
      </div>
    </main>
    <peerly-public-footer />`,
  styles: `
    :host {
      display: block;
      background: var(--tui-background-base-alt);
    }
    main {
      max-inline-size: 90rem;
      padding: 2rem max(1rem, env(safe-area-inset-right)) 3rem max(1rem, env(safe-area-inset-left));
      margin-inline: auto;
      overflow-wrap: anywhere;
    }
    h1 {
      font: var(--tui-typography-heading-h3);
      margin-block: 0 2rem;
    }
    h2 {
      font: var(--tui-typography-heading-h5);
    }
    .columns {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      align-items: start;
      gap: 2rem;
    }
    section {
      min-inline-size: 0;
    }
    p {
      margin-block: 0.5rem 1rem;
    }
    @media (width >= 64rem) {
      main {
        padding-inline: 4rem;
      }
      .columns {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
  `,
})
export class Help {
  private readonly contact = viewChild(SupportContact);

  public async canLeave(): Promise<boolean> {
    const contact = this.contact();
    return contact === undefined || (await contact.canLeave());
  }
}
