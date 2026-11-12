import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { readJson } from '../../api-http';
import { isOwnGoal, isOwnHelp } from '../study-context-contract';

type Context = Api['schemas']['DiscoveryContextBody'];

export function goalOptions(http: Readonly<HttpClient>, actorId: string | null, enabled: boolean) {
  return queryOptions({
    queryKey: actorId === null ? ['discovery-context-idle', 'goal'] : ['account', actorId, 'goal'],
    enabled,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, '/api/v1/me/goal', signal, isOwnGoal),
  });
}

export function helpOptions(http: Readonly<HttpClient>, actorId: string | null, enabled: boolean) {
  return queryOptions({
    queryKey:
      actorId === null
        ? ['discovery-context-idle', 'help-subjects']
        : ['account', actorId, 'help-subjects'],
    enabled,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, '/api/v1/me/help-subjects', signal, isOwnHelp),
  });
}

export function contextLabel(
  context: Context | null | undefined,
  goal: Api['schemas']['OwnGoalResponse'] | undefined,
  help: Api['schemas']['OwnHelpResponse'] | undefined,
): string | null {
  if (context === null || context === undefined) return null;
  if (context.mode === 'offer_help') {
    const selection = help?.selection;
    if (selection?.version !== context.help_version) return null;
    const label = selection.subjects.map((subject) => subject.label).join(' · ');
    return label === '' ? null : label;
  }
  const active = goal?.goal;
  if (active?.id !== context.goal_id || active.version !== context.goal_version) return null;
  return active.topic === null ? active.subject.label : `${active.subject.label} · ${active.topic}`;
}
