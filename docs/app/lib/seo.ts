const SITE = 'https://parlot.ai';
const DEFAULT_OG = `${SITE}/og-image.png`;

/** Align with marketing site definitional copy. */
export const PRODUCT_DEFINITION =
  'Parlot is a voice AI observability platform that shows the cost, quality, latency, and margin of every production voice agent call, for LiveKit, Pipecat, and LangGraph.';

export type SeoInput = {
  title: string;
  description: string;
  /** Absolute path on parlot.ai, e.g. `/docs` or `/docs/sdk/get-started/quick-start`. */
  path: string;
  image?: string;
  type?: 'website' | 'article';
};

export function absoluteUrl(path: string): string {
  if (path.startsWith('http')) return path;
  return `${SITE}${path.startsWith('/') ? path : `/${path}`}`;
}

/** Path for a docs page given fumadocs `page.url` (usually starts with `/`). */
export function docsCanonicalPath(pageUrl: string): string {
  const normalized = pageUrl.startsWith('/') ? pageUrl : `/${pageUrl}`;
  if (normalized === '/' || normalized === '') return '/docs';
  if (normalized.startsWith('/docs')) return normalized.replace(/\/$/, '') || '/docs';
  return `/docs${normalized}`.replace(/\/$/, '');
}

export function seoMeta({
  title,
  description,
  path,
  image = DEFAULT_OG,
  type = 'website',
}: SeoInput) {
  const url = absoluteUrl(path);
  const ogImage = absoluteUrl(image);
  return [
    { title },
    { name: 'description', content: description },
    { property: 'og:title', content: title },
    { property: 'og:description', content: description },
    { property: 'og:type', content: type },
    { property: 'og:url', content: url },
    { property: 'og:image', content: ogImage },
    { property: 'og:image:width', content: '1200' },
    { property: 'og:image:height', content: '630' },
    { name: 'twitter:card', content: 'summary_large_image' },
    { name: 'twitter:title', content: title },
    { name: 'twitter:description', content: description },
    { name: 'twitter:image', content: ogImage },
    { tagName: 'link' as const, rel: 'canonical', href: url },
  ];
}

export function techArticleJsonLd(input: {
  title: string;
  description: string;
  path: string;
}) {
  return {
    '@context': 'https://schema.org',
    '@type': 'TechArticle',
    headline: input.title,
    description: input.description,
    url: absoluteUrl(input.path),
    author: { '@type': 'Organization', name: 'Parlot' },
    publisher: {
      '@type': 'Organization',
      name: 'Parlot',
      logo: { '@type': 'ImageObject', url: absoluteUrl('/logo.webp') },
    },
    mainEntityOfPage: absoluteUrl(input.path),
  };
}

export function breadcrumbJsonLd(items: Array<{ name: string; path: string }>) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: item.name,
      item: absoluteUrl(item.path),
    })),
  };
}

export { SITE, DEFAULT_OG };
