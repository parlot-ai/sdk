import { source } from '@/lib/source';

export function loader() {
  const baseUrl = 'https://parlot.ai/docs';
  const urls = [
    baseUrl,
    ...source.getPages().map((p) => {
      // p.url is /docs/...
      return `https://parlot.ai${p.url}`;
    }),
  ];
  const uniqueUrls = Array.from(new Set(urls)).filter((u) => !u.includes('/search'));

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${uniqueUrls
  .map(
    (url) => `  <url>
    <loc>${url}</loc>
    <changefreq>weekly</changefreq>
    <priority>${url === baseUrl ? '1.0' : '0.8'}</priority>
  </url>`,
  )
  .join('\n')}
</urlset>`;

  return new Response(xml, {
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
    },
  });
}
