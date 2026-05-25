import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

// jsdom doesn't implement ``Element.scrollTo``; the ChatPanel's
// auto-scroll-on-new-message ``useEffect`` blows up on commit when the
// polyfill is absent. We don't assert on scroll behaviour in tests, so
// stubbing it as a no-op is sufficient. Belt-and-braces with the
// ``in`` check so future jsdom upgrades that ship a real ``scrollTo``
// don't get clobbered.
if (typeof Element !== 'undefined' && !('scrollTo' in Element.prototype)) {
  (Element.prototype as unknown as { scrollTo: () => void }).scrollTo = vi.fn();
}
