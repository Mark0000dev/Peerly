import type { DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import type { TuiDialogService } from '@taiga-ui/core';
import { TUI_CONFIRM } from '@taiga-ui/kit';
import { firstValueFrom } from 'rxjs';

// One leave-confirmation flow shared by actual student editing workspaces.
// Only transient form/operation facts enter the dialog; no copied server state.
export async function confirmDraftExit(
  dialogs: Readonly<TuiDialogService>,
  destroy: Readonly<DestroyRef>,
  draft: Readonly<{ readonly dirty: boolean; readonly unconfirmed: boolean }>,
): Promise<boolean> {
  if (!draft.dirty && !draft.unconfirmed) return true;
  return await firstValueFrom(
    dialogs
      .open<boolean>(TUI_CONFIRM, {
        label: draft.unconfirmed
          ? 'Leave before the save is confirmed?'
          : 'Discard unsaved changes?',
        data: {
          content: draft.unconfirmed
            ? 'The save may already have reached the server. Check the saved result when you return.'
            : 'Your unsaved edits will be discarded.',
          yes: draft.unconfirmed ? 'Leave editor' : 'Discard changes',
          no: 'Keep editing',
        },
      })
      .pipe(takeUntilDestroyed(destroy)),
    { defaultValue: false },
  );
}
