import type { Route } from './+types/docs';
import { DocsLayout } from 'fumadocs-ui/layouts/notebook';
import {
  DocsBody,
  DocsDescription,
  DocsPage,
  DocsTitle,
} from 'fumadocs-ui/layouts/notebook/page';
import { LLMCopyButton } from '@/components/llm-copy-button';
import { docs, getPageMarkdownUrl, source } from '@/lib/source';
import { baseOptions } from '@/lib/layout.shared';
import { gitConfig } from '@/lib/shared';
import { useFumadocsLoader } from 'fumadocs-core/source/client';
import { useMDXComponents } from '@/components/mdx';
import { use } from 'react';
import NotFound from './not-found';

export async function loader({ params }: Route.LoaderArgs) {
  const rawPath = params['*'] || '';
  const slugs = rawPath.split('/').filter((v) => v.length > 0);
  const page = source.getPage(slugs);
  if (!page) {
    throw new Response('Not found', { status: 404 });
  }

  return {
    path: page.path,
    markdownUrl: getPageMarkdownUrl(page).url,
    pageTree: await source.serializePageTree(source.getPageTree()),
  };
}

function Content({ path, markdownUrl }: { path: string; markdownUrl: string }) {
  const page = docs.getPage(path);
  if (!page) throw new Error(`unknown page: ${path}`);

  const { toc } = use(page.load());
  const Mdx = page.body;
  const filteredToc = toc.filter((item) => item.depth > 1);
  const pageId = path.split('/').pop()?.replace(/\.(mdx|md)$/, '');

  return (
    <DocsPage toc={filteredToc}>
      <title>{page.title}</title>
      <meta name="description" content={page.description} />
      <DocsTitle id={pageId}>{page.title}</DocsTitle>
      {page.description && <DocsDescription>{page.description}</DocsDescription>}
      <div className="flex flex-row gap-2 items-center border-b border-fd-border -mt-4 pb-6 mb-6">
        <LLMCopyButton markdownUrl={markdownUrl} />
      </div>
      <DocsBody>
        <Mdx components={useMDXComponents()} />
      </DocsBody>
    </DocsPage>
  );
}

export default function Page({ loaderData }: Route.ComponentProps) {
  const { pageTree, path, markdownUrl } = useFumadocsLoader(loaderData);
  const base = baseOptions();

  return (
    <DocsLayout
      {...base}
      nav={{
        ...base.nav,
        mode: 'top',
      }}
      tree={pageTree}
      tabs={[
        {
          title: 'SDK Guide',
          url: '/sdk',
          description: 'Open-source voice AI observability SDK',
        },
        {
          title: 'App Guide',
          url: '/app',
          description: 'Parlot dashboard, policies, and evaluation',
        },
        {
          title: 'Python API',
          url: '/docs/ref/python/',
          description: 'Generated Python SDK reference (pdoc)',
        },
      ]}
    >
      <Content path={path} markdownUrl={markdownUrl} />
    </DocsLayout>
  );
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  return <NotFound />;
}
