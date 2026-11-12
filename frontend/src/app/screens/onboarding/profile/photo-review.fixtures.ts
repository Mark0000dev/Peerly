import type { Api } from '../../../api.generated';

export const noPhotoReview = {
  version: 0,
  state: 'not_required',
} as const satisfies Api['schemas']['OwnPhotoReviewResponse'];
