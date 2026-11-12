import { useEffect, useLayoutEffect, useState } from 'react';
import { useLocation } from 'react-router';
import posthog from 'posthog-js';
import { CookieConsentBanner } from './cookie-consent-banner';
import {
  getActiveUtms,
  getConsentStatus,
  initDocsPostHog,
  isDocsPostHogReady,
  trackCodeSnippetCopied,
  trackDocsView,
  trackGithubClicked,
  trackQuickstartStarted,
} from '@/lib/posthog';

function copyTypeFromTarget(target: EventTarget | null): 'code_block' | 'page_markdown' | null {
  if (!(target instanceof Element)) return null;
  const button = target.closest('button');
  if (!button) return null;
  const label = (
    button.getAttribute('aria-label') ||
    button.textContent ||
    ''
  ).toLowerCase();
  if (label.includes('copy markdown')) return 'page_markdown';
  if (label.includes('copy text') || label.includes('copy code')) {
    return 'code_block';
  }
  // Fumadocs code-block copy often has only an icon; prefer pre ancestors.
  if (button.closest('pre, [data-codeblock], .fd-codeblock')) {
    return 'code_block';
  }
  return null;
}

/** Client-only: PostHog init, docs funnel events, consent banner. */
export function DocsAnalytics() {
  const location = useLocation();
  const [consentPending, setConsentPending] = useState(false);

  useLayoutEffect(() => {
    initDocsPostHog();
    if (isDocsPostHogReady()) {
      setConsentPending(getConsentStatus() === 'pending');
    }
  }, []);

  useEffect(() => {
    if (!isDocsPostHogReady()) return;
    const utms = getActiveUtms();
    if (Object.keys(utms).length > 0) {
      posthog.register(utms);
    }
    const path = location.pathname;
    trackDocsView({
      path,
      title: typeof document !== 'undefined' ? document.title : undefined,
    });
    trackQuickstartStarted({ path });
  }, [location.pathname, location.search]);

  useEffect(() => {
    if (!isDocsPostHogReady()) return;

    function onClick(event: MouseEvent) {
      const path =
        typeof window !== 'undefined' ? window.location.pathname : location.pathname;

      const copyType = copyTypeFromTarget(event.target);
      if (copyType) {
        trackCodeSnippetCopied({ path, copyType });
        return;
      }

      if (!(event.target instanceof Element)) return;
      const anchor = event.target.closest('a');
      if (!anchor) return;
      const href = anchor.href || '';
      if (!/github\.com\/parlot-ai\//i.test(href)) return;
      trackGithubClicked({
        path,
        placement: 'docs_nav',
        destination: 'sdk',
      });
    }

    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, [location.pathname]);

  return (
    <CookieConsentBanner
      visible={consentPending}
      onDismiss={() => setConsentPending(false)}
    />
  );
}
