import type { Config } from '@react-router/dev/config';
import { glob } from 'node:fs/promises';
import { getSlugs } from 'fumadocs-core/source';

export default {
  // Must match the live canonical path. Cloudflare Assets
  // html_handling=drop-trailing-slash serves /docs (not /docs/), and React
  // Router only mounts when location.pathname starts with basename — a
  // trailing slash here leaves the hub at /docs as inert prerendered HTML.
  basename: '/docs',
  ssr: false,
  async prerender({ getStaticPaths }) {
    const paths: string[] = ['/', '/api/search', '/sitemap.xml', '/llms.txt', '/llms-full.txt'];

    try {
      for await (const entry of glob('**/*.{mdx,md}', { cwd: 'content/docs' })) {
        const slugs = getSlugs(entry);
        const docPath = '/' + slugs.join('/');
        paths.push(docPath);
        paths.push(`/llms.mdx/docs/${[...slugs, 'content.md'].join('/')}`);
      }
    } catch {
      // content/docs directory might be empty initially
    }

    for (const p of getStaticPaths()) {
      if (!paths.includes(p)) paths.push(p);
    }

    return paths;
  },
} satisfies Config;
