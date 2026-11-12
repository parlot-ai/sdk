export type DocsSection = 'sdk' | 'app' | 'hub' | 'other';
export type DocsFramework = 'livekit' | 'pipecat' | 'langgraph' | 'none';
export type DocsPageKind =
  | 'hub'
  | 'quickstart'
  | 'install'
  | 'integration_guide'
  | 'concepts'
  | 'api'
  | 'other';

/** Normalize browser pathname under `/docs` basename to content path segments. */
export function docsPathSegments(pathname: string): string[] {
  const raw = pathname.replace(/^\/docs\/?/, '/').replace(/\/+$/, '') || '/';
  return raw.split('/').filter(Boolean);
}

export function classifyDocsPath(pathname: string): {
  section: DocsSection;
  framework: DocsFramework;
  pageKind: DocsPageKind;
} {
  const segments = docsPathSegments(pathname);
  if (segments.length === 0) {
    return { section: 'hub', framework: 'none', pageKind: 'hub' };
  }

  const [root, ...rest] = segments;
  let section: DocsSection = 'other';
  if (root === 'sdk') section = 'sdk';
  else if (root === 'app') section = 'app';

  const joined = rest.join('/');
  let framework: DocsFramework = 'none';
  if (joined.includes('livekit')) framework = 'livekit';
  else if (joined.includes('pipecat')) framework = 'pipecat';
  else if (joined.includes('langgraph')) framework = 'langgraph';

  let pageKind: DocsPageKind = 'other';
  if (rest.length === 0) {
    pageKind = section === 'sdk' || section === 'app' ? 'hub' : 'other';
  } else if (joined.includes('quick-start')) {
    pageKind = 'quickstart';
  } else if (joined.includes('concepts')) {
    pageKind = 'concepts';
  } else if (joined.startsWith('guides/') || joined === 'guides') {
    pageKind = joined === 'guides' ? 'hub' : 'integration_guide';
  } else if (
    joined.startsWith('get-started') ||
    joined === 'python' ||
    joined.startsWith('typescript') ||
    joined === 'env-vars'
  ) {
    pageKind = 'install';
  } else if (root === 'ref' || joined.includes('api')) {
    pageKind = 'api';
  }

  return { section, framework, pageKind };
}

export function isQuickStartPath(pathname: string): boolean {
  return classifyDocsPath(pathname).pageKind === 'quickstart';
}
