import { Link as RouterLink } from 'react-router';
import type { ComponentProps } from 'react';

type PrefetchType = boolean | 'none' | 'intent' | 'render' | 'viewport';

export function CustomLink({
  href,
  prefetch,
  ...props
}: ComponentProps<'a'> & { prefetch?: PrefetchType }) {
  if (!href) return <a {...props} />;

  // External or static reference links (like /docs/ref/python/)
  if (
    href.startsWith('http://') ||
    href.startsWith('https://') ||
    href.startsWith('mailto:') ||
    href.startsWith('/docs/ref/')
  ) {
    const isExternal =
      href.startsWith('http://') || href.startsWith('https://');
    return (
      <a
        href={href}
        {...(isExternal
          ? { target: '_blank', rel: 'noopener noreferrer' }
          : {})}
        {...props}
      />
    );
  }

  // If a link is written with the /docs prefix, strip it so React Router's
  // basename="/docs/" does not double-prefix it to /docs/docs/...
  let to = href;
  if (to === '/docs' || to === '/docs/') {
    to = '/';
  } else if (to.startsWith('/docs/')) {
    to = to.slice('/docs'.length);
  }

  const routerPrefetch =
    typeof prefetch === 'boolean' ? (prefetch ? 'intent' : 'none') : prefetch;

  return <RouterLink to={to} prefetch={routerPrefetch} {...props} />;
}

export default CustomLink;
