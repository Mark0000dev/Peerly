interface NoticeText {
  readonly title: string;
  readonly description: string;
  readonly cancelled: boolean;
}
export interface LoginNotice extends NoticeText {
  readonly reference: string | null;
}
const notices: Readonly<Record<string, NoticeText>> = Object.freeze({
  login_invalid: {
    title: 'We couldn’t complete sign-in',
    description: 'Please start Google sign-in again.',
    cancelled: false,
  },
  login_cancelled: {
    title: 'Sign-in cancelled',
    description: 'You can try again when you’re ready.',
    cancelled: true,
  },
  login_provider_unavailable: {
    title: 'Google sign-in is unavailable',
    description: 'Please try again later.',
    cancelled: false,
  },
  login_rate_limited: {
    title: 'Too many sign-in attempts',
    description: 'Please try again later.',
    cancelled: false,
  },
  account_unavailable: {
    title: 'Account unavailable',
    description: 'Get help with your account to continue.',
    cancelled: false,
  },
  request_context_invalid: {
    title: 'We couldn’t complete sign-in',
    description: 'Please start Google sign-in again.',
    cancelled: false,
  },
});
export function callbackNotice(code: string | null, reference: string | null): LoginNotice | null {
  if (code === null || !Object.hasOwn(notices, code)) return null;
  const notice = notices[code];
  if (notice === undefined) return null;
  return {
    ...notice,
    reference:
      reference !== null &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(reference)
        ? reference
        : null,
  };
}
