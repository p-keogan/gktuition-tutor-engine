/**
 * GKTuition AI Tutor widget — script-tag mountable entry point.
 *
 * The Vite IIFE build (see vite.config.ts) exposes the default export of
 * this file as ``window.GKTuitionTutor``. The WordPress plugin's inline
 * post-load script then calls ``window.GKTuitionTutor.mount(target, opts)``.
 *
 * Auth: every render boots by fetching ``/wp-json/gktuition/v1/tier`` from
 * the same WordPress origin. The JWT it returns lives in memory inside the
 * api client's closure for as long as the widget is mounted — never in
 * localStorage / sessionStorage. See ADR-002 redline note 3.
 */

import { useEffect, useMemo, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { createApiClient, type ApiClient } from './api/client';
import type { Tier, WidgetOptions } from './api/types';
import { FloatingButton } from './components/FloatingButton';
import { ChatPanel } from './components/ChatPanel';
import './style.css';

interface WidgetState {
  open: boolean;
  tier: Tier;
  bootstrapping: boolean;
  bootError: string | null;
}

interface WidgetProps {
  opts: Required<Pick<WidgetOptions, 'position' | 'anonymousRateLimit'>> & WidgetOptions;
  /** Optional override so tests can inject a fake. */
  client?: ApiClient;
}

function Widget({ opts, client: clientOverride }: WidgetProps) {
  const [state, setState] = useState<WidgetState>({
    open: false,
    tier: 'anonymous',
    bootstrapping: true,
    bootError: null,
  });

  const client = useMemo<ApiClient>(() => {
    if (clientOverride) return clientOverride;
    return createApiClient({
      tierEndpoint: opts.tierEndpoint ?? '/wp-json/gktuition/v1/tier',
      fastapiUrl: opts.fastapiUrl ?? '',
      restNonce: opts.restNonce,
    });
  }, [clientOverride, opts.tierEndpoint, opts.fastapiUrl, opts.restNonce]);

  useEffect(() => {
    let cancelled = false;
    client
      .fetchTier()
      .then((res) => {
        if (cancelled) return;
        setState((s) => ({ ...s, tier: res.tier, bootstrapping: false, bootError: null }));
      })
      .catch((err) => {
        if (cancelled) return;
        // Bootstrap failure is non-fatal — the widget still works for
        // anonymous tier; we just can't authenticate to the FastAPI side.
        // Per the brief's anonymous-tier path we surface a soft error in
        // the panel on first send, not the FAB.
        setState((s) => ({
          ...s,
          bootstrapping: false,
          bootError: (err as Error).message ?? 'tier endpoint unreachable',
        }));
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  return (
    <div className="gktuition-tutor">
      <FloatingButton
        position={opts.position}
        isOpen={state.open}
        onClick={() => setState((s) => ({ ...s, open: !s.open }))}
      />
      {state.open ? (
        <ChatPanel
          position={opts.position}
          client={client}
          tier={state.tier}
          anonymousRateLimit={opts.anonymousRateLimit}
          onClose={() => setState((s) => ({ ...s, open: false }))}
        />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mount API — the IIFE bundle exposes this as window.GKTuitionTutor.mount.
// ---------------------------------------------------------------------------

const ROOTS = new WeakMap<HTMLElement, Root>();

export function mount(target: HTMLElement, opts: WidgetOptions = {}): () => void {
  if (!target) throw new Error('GKTuitionTutor.mount: target element is required');
  const filled: WidgetProps['opts'] = {
    tierEndpoint: opts.tierEndpoint ?? '/wp-json/gktuition/v1/tier',
    fastapiUrl: opts.fastapiUrl ?? '',
    position: opts.position ?? 'bottom-right',
    anonymousRateLimit: opts.anonymousRateLimit ?? 3,
    restNonce: opts.restNonce,
  };
  let root = ROOTS.get(target);
  if (!root) {
    root = createRoot(target);
    ROOTS.set(target, root);
  }
  root.render(<Widget opts={filled} />);
  return () => unmount(target);
}

export function unmount(target: HTMLElement): void {
  const root = ROOTS.get(target);
  if (root) {
    root.unmount();
    ROOTS.delete(target);
  }
}

// Test-only export — lets unit tests render with an injected ApiClient.
export function __renderWithClient(
  target: HTMLElement,
  opts: WidgetOptions,
  client: ApiClient,
): () => void {
  const filled: WidgetProps['opts'] = {
    tierEndpoint: opts.tierEndpoint ?? '/wp-json/gktuition/v1/tier',
    fastapiUrl: opts.fastapiUrl ?? '',
    position: opts.position ?? 'bottom-right',
    anonymousRateLimit: opts.anonymousRateLimit ?? 3,
    restNonce: opts.restNonce,
  };
  let root = ROOTS.get(target);
  if (!root) {
    root = createRoot(target);
    ROOTS.set(target, root);
  }
  root.render(<Widget opts={filled} client={client} />);
  return () => unmount(target);
}

// Default export = the namespace the IIFE attaches to window.GKTuitionTutor.
export default { mount, unmount, __renderWithClient };
