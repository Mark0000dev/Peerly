import { Component, computed, input } from '@angular/core';
import { TuiAppearance } from '@taiga-ui/core';
import { TuiCardLarge } from '@taiga-ui/layout';
import type { Api } from '../../api.generated';

interface Field {
  readonly label: string;
  readonly value: string | number | boolean | null;
}
interface Section {
  readonly title: string;
  readonly fields: readonly Field[];
}
function fields(
  values: Readonly<Record<string, string | number | boolean | null>>,
): readonly Field[] {
  return Object.entries(values)
    .filter(([, value]: readonly [string, string | number | boolean | null]) => value !== null)
    .map(([label, value]: readonly [string, string | number | boolean | null]) => ({
      label,
      value,
    }));
}
function sections(detail: Api['schemas']['OperatorAccountDetailResponse']): readonly Section[] {
  const account = detail.account;
  const profile = detail.profile;
  const goal = detail.goal;
  const help = detail.help_subjects;
  const lifecycle = detail.lifecycle;
  const exposure = detail.exposure;
  const registration = detail.registration;
  const photo = detail.photo;
  return [
    {
      title: 'Account and identity',
      fields: fields({
        'Account ID': account.account_id,
        'Created at': account.created_at,
        'Banned at': account.banned_at,
        'Deleted at': account.deleted_at,
        'Hidden at': account.hidden_at,
        'Profile version': account.profile_version,
        'Stored display name': account.display_name,
        'Google link ID': account.google_link?.id ?? null,
        'Google issuer': account.google_link?.issuer ?? null,
        'Google subject': account.google_link?.subject ?? null,
        'Google linked at': account.google_link?.created_at ?? null,
        'Institutional email': account.membership?.email ?? null,
        'Email verified at': account.membership?.verified_at ?? null,
        'Membership revoked at': account.membership?.revoked_at ?? null,
      }),
    },
    {
      title: 'Profile',
      fields:
        profile === null
          ? []
          : fields({
              'Display name': profile.display_name,
              About: profile.about,
              Programme: profile.programme,
              Year: profile.year_label,
              Languages: profile.languages.join(', '),
              Task: profile.task,
              Version: profile.version,
              'Saved at': profile.saved_at,
            }),
    },
    {
      title: 'Current goal',
      fields:
        goal === null
          ? []
          : fields({
              'Goal ID': goal.id,
              Version: goal.version,
              Subject: goal.subject.label,
              Topic: goal.topic,
              Context: goal.context,
              'Shared learning': goal.shared_learning,
              'Created at': goal.created_at,
              'Updated at': goal.updated_at,
              'Completed at': goal.completed_at,
            }),
    },
    {
      title: 'Help subjects',
      fields:
        help === null
          ? []
          : [
              ...fields({ Version: help.version, 'Saved at': help.saved_at }),
              ...help.subjects.flatMap((subject) =>
                fields({
                  Subject: subject.label,
                  'Subject ID': subject.subject_id,
                  'Topic note': subject.topic_note,
                }),
              ),
            ],
    },
    {
      title: 'Photo reference',
      fields:
        photo === null
          ? []
          : fields({
              'Photo version': photo.version,
              'Upload ID': photo.upload_id,
              'Saved at': photo.saved_at,
            }),
    },
    {
      title: 'Profile lifecycle',
      fields:
        lifecycle === null
          ? []
          : fields({
              'Setup completed at': lifecycle.completed_at,
              'Visibility version': lifecycle.visibility_version,
              'Hidden at': lifecycle.hidden_at,
              'Changed at': lifecycle.changed_at,
            }),
    },
    {
      title: 'Discovery exposure',
      fields:
        exposure === null
          ? []
          : fields({
              'Last activity at': exposure.last_activity_at,
              'Confirmed at': exposure.confirmed_at,
              'Paused at': exposure.paused_at,
              'Inactivity interval (seconds)': exposure.inactivity_seconds,
            }),
    },
    {
      title: 'Registration receipt',
      fields:
        registration === null
          ? []
          : fields({
              'Receipt ID': registration.id,
              'Context ID': registration.context_id,
              'Registered at': registration.registered_at,
              Surface: registration.surface,
              Notice: registration.notice_text,
              'Terms ID': registration.terms.id,
              'Terms version': registration.terms.version,
              'Terms published at': registration.terms.published_at,
              'Privacy ID': registration.privacy.id,
              'Privacy version': registration.privacy.version,
              'Privacy published at': registration.privacy.published_at,
            }),
    },
  ];
}
@Component({
  selector: 'app-operator-overview',
  imports: [TuiAppearance, TuiCardLarge],
  template: `
    <section aria-label="Account overview">
      <h2>{{ detail().account.display_name ?? detail().account.account_id }}</h2>
      @if (detail().account.deleted_at !== null) {
        <p>Deleted account · identity retained</p>
      }
      @if (detail().account.banned_at !== null) {
        <p>Banned account</p>
      }
      @if (detail().account.hidden_at !== null) {
        <p>Hidden profile</p>
      }
      <div class="panels">
        @for (section of sections(); track section.title) {
          <section tuiCardLarge="compact" tuiAppearance="neutral" [attr.aria-label]="section.title">
            <div class="record-content">
              <h3>{{ section.title }}</h3>
              @if (section.fields.length === 0) {
                <p>No stored record.</p>
              }
              <dl>
                @for (field of section.fields; track field) {
                  <div>
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value }}</dd>
                  </div>
                }
              </dl>
            </div>
          </section>
        }
        <section tuiCardLarge="compact" tuiAppearance="neutral" aria-label="Record references">
          <div class="record-content">
            <h3>Record references</h3>
            @for (link of detail().links; track link.kind) {
              <dl>
                <dt>{{ link.kind }}</dt>
                <dd>{{ link.id }}</dd>
                @if (link.version !== null) {
                  <dt>Version</dt>
                  <dd>{{ link.version }}</dd>
                }
              </dl>
            } @empty {
              <p>No stored references.</p>
            }
          </div>
        </section>
      </div>
    </section>
  `,
  styles: `
    :host {
      display: block;
      min-inline-size: 0;
    }
    .panels {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      align-items: start;
      gap: 1rem;
    }
    section {
      min-inline-size: 0;
    }
    .record-content,
    dl,
    dl > div {
      min-inline-size: 0;
    }
    h3,
    dt {
      overflow-wrap: anywhere;
    }
    dl {
      margin: 0;
      display: grid;
      gap: 0.75rem;
    }
    dd {
      margin: 0;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }
    @media (min-width: 64rem) {
      .panels {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
  `,
})
export class OperatorOverview {
  public readonly detail = input.required<Api['schemas']['OperatorAccountDetailResponse']>();
  protected readonly sections = computed(() => sections(this.detail()));
}
