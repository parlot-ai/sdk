import type { Route } from './+types/mdx';
import { getLLMText, source } from '@/lib/source';

export async function loader({ params }: Route.LoaderArgs) {
  const rawPath = params['*'] || '';
  const slugs = rawPath.split('/').filter((v) => v.length > 0);
  if (slugs[slugs.length - 1] === 'content.md') {
    slugs.pop();
  }
  const page = source.getPage(slugs);
  if (!page) {
    return new Response('Not found', { status: 404 });
  }
  return new Response(await getLLMText(page), {
    headers: {
      'Content-Type': 'text/markdown; charset=utf-8',
    },
  });
}
