import posthog from 'posthog-js';
import {
  classifyDocsPath,
  isQuickStartPath,
  type DocsFramework,
  type DocsPageKind,
  type DocsSection,
} from './docs-path-meta';

const UTM_KEYS = [
  'utm_source',
  'utm_medium',
  'utm_campaign',
  'utm_content',
  'utm_term',
] as const;

type UtmKey = (typeof UTM_KEYS)[number];
type UtmProps = Partial<Record<UtmKey, string>>;

const UTM_STORAGE_KEY = 'parlot_marketing_utms';
const QUICKSTART_STARTED_KEY = 'parlot_docs_quickstart_started';

let initialized = false;

function resolvePostHogKey(): string | null {
  return import.meta.env.VITE_PUBLIC_POSTHOG_KEY?.trim() || null;
}

function resolvePostHogHost(): string {
  return (
    import.meta.env.VITE_PUBLIC_POSTHOG_HOST?.trim() ||
    'https://us.i.posthog.com'
  );
}

function readUtmsFromLocation(): UtmProps {
  if (typeof window === 'undefined') return {};
  const params = new URLSearchParams(window.location.search);
  const out: UtmProps = {};
  for (const key of UTM_KEYS) {
    const value = params.get(key)?.trim();
    if (value) out[key] = value;
  }
  return out;
}

function loadStoredUtms(): UtmProps {
  if (typeof sessionStorage === 'undefined') return {};
  try {
    const raw = sessionStorage.getItem(UTM_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as UtmProps;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function persistUtms(utms: UtmProps): void {
  if (typeof sessionStorage === 'undefined') return;
  if (Object.keys(utms).length === 0) return;
  try {
    sessionStorage.setItem(UTM_STORAGE_KEY, JSON.stringify(utms));
  } catch {
    // ignore
  }
}

export function getActiveUtms(): UtmProps {
  const fromUrl = readUtmsFromLocation();
  if (Object.keys(fromUrl).length > 0) {
    persistUtms(fromUrl);
    return fromUrl;
  }
  return loadStoredUtms();
}

export function initDocsPostHog(): void {
  if (initialized) return;
  if (typeof window === 'undefined') return;
  const key = resolvePostHogKey();
  if (!key) return;

  posthog.init(key, {
    api_host: resolvePostHogHost(),
    ui_host: 'https://us.posthog.com',
    person_profiles: 'identified_only',
    capture_pageview: false,
    capture_pageleave: true,
    cookieless_mode: 'on_reject',
    opt_out_capturing_persistence_type: 'cookie',
    cross_subdomain_cookie: true,
    cookieWinsOnConflict: true,
  });
  initialized = true;

  const utms = getActiveUtms();
  if (Object.keys(utms).length > 0) {
    posthog.register(utms);
  }
}

export function isDocsPostHogReady(): boolean {
  return initialized;
}

export function getConsentStatus(): 'pending' | 'granted' | 'denied' | 'unknown' {
  if (!initialized) return 'unknown';
  return posthog.get_explicit_consent_status();
}

export function acceptDocsAnalytics(): void {
  if (!initialized) return;
  posthog.opt_in_capturing();
  const utms = getActiveUtms();
  if (Object.keys(utms).length > 0) {
    posthog.register(utms);
  }
}

export function rejectDocsAnalytics(): void {
  if (!initialized) return;
  posthog.opt_out_capturing();
}

function baseProps(pathname: string): {
  path: string;
  section: DocsSection;
  framework: DocsFramework;
  page_kind: DocsPageKind;
} & UtmProps {
  const meta = classifyDocsPath(pathname);
  return {
    path: pathname,
    section: meta.section,
    framework: meta.framework,
    page_kind: meta.pageKind,
    ...getActiveUtms(),
  };
}

export function trackDocsView(input: { path: string; title?: string }): void {
  if (!initialized) return;
  posthog.capture('docs_view', {
    ...baseProps(input.path),
    title: input.title,
  });
}

/** Once per browser session when the Quick Start page is opened. */
export function trackQuickstartStarted(input: { path: string }): void {
  if (!initialized) return;
  if (!isQuickStartPath(input.path)) return;
  if (typeof sessionStorage !== 'undefined') {
    try {
      if (sessionStorage.getItem(QUICKSTART_STARTED_KEY) === '1') return;
      sessionStorage.setItem(QUICKSTART_STARTED_KEY, '1');
    } catch {
      // still capture once this call
    }
  }
  posthog.capture('quickstart_started', {
    ...baseProps(input.path),
  });
}

export function trackCodeSnippetCopied(input: {
  path: string;
  copyType: 'code_block' | 'page_markdown';
}): void {
  if (!initialized) return;
  posthog.capture('code_snippet_copied', {
    ...baseProps(input.path),
    copy_type: input.copyType,
  });
}

export function trackGithubClicked(input: {
  path: string;
  placement: string;
  destination?: string;
}): void {
  if (!initialized) return;
  posthog.capture('github_clicked', {
    ...baseProps(input.path),
    placement: input.placement,
    destination: input.destination ?? 'sdk',
  });
}
