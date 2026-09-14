import { execSync } from 'node:child_process';
import { readFileSync, readdirSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const docsDir = resolve(import.meta.dirname, '..');
const tsDir = resolve(docsDir, 'content/docs/sdk/typescript');
const tsDocsBase = '/docs/sdk/typescript';

console.log('Running TypeDoc to generate TypeScript reference...');
execSync('bunx typedoc', { cwd: docsDir, stdio: 'inherit' });

/**
 * TypeDoc emits sibling links like `(index.mdx)`. Fumadocs serves pages with a
 * trailing slash (e.g. `/docs/sdk/typescript/README/`), so those relative
 * destinations resolve under the current page (`.../README/index.mdx`) and 404.
 * Rewrite them to absolute, extensionless docs routes.
 */
function rewriteFumadocsLinks(content: string): string {
  return content.replace(
    /\]\((?:\.\.?\/)*([^)#\s]+)\.mdx(#[^)]*)?\)/g,
    (_match, page: string, hash = '') => `](${tsDocsBase}/${page}${hash})`
  );
}

function updateFrontmatter(filePath: string, title: string, description: string) {
  if (!existsSync(filePath)) return;
  let content = readFileSync(filePath, 'utf-8');
  // Strip existing frontmatter
  if (content.startsWith('---')) {
    const secondFence = content.indexOf('---', 3);
    if (secondFence !== -1) {
      content = content.slice(secondFence + 3).trimStart();
    }
  }
  // Strip any leading H1 heading since DocsTitle handles the page title
  content = content.trimStart().replace(/^#\s+[^\n]*\n*/, '');
  content = rewriteFumadocsLinks(content);
  const newHeader = `---\ntitle: ${title}\ndescription: ${description}\n---\n\n`;
  writeFileSync(filePath, newHeader + content);
}

updateFrontmatter(
  resolve(tsDir, 'README.mdx'),
  'Overview',
  'TypeScript semantic convention constants and attributes for @parlot/core.'
);

updateFrontmatter(
  resolve(tsDir, 'index.mdx'),
  'Core Constants',
  'Parlot core semantic convention constants and span attributes.'
);

updateFrontmatter(
  resolve(tsDir, 'livekit.mdx'),
  'LiveKit Constants',
  'LiveKit voice agent semantic convention constants and metrics.'
);

// Catch any other generated pages TypeDoc may add later.
for (const name of readdirSync(tsDir)) {
  if (!name.endsWith('.mdx')) continue;
  if (name === 'README.mdx' || name === 'index.mdx' || name === 'livekit.mdx') continue;
  const filePath = resolve(tsDir, name);
  const content = readFileSync(filePath, 'utf-8');
  const rewritten = rewriteFumadocsLinks(content);
  if (rewritten !== content) writeFileSync(filePath, rewritten);
}

writeFileSync(
  resolve(tsDir, 'meta.json'),
  JSON.stringify(
    {
      title: 'TypeScript Reference',
      pages: ['README', 'index', 'livekit'],
    },
    null,
    2
  ) + '\n'
);

console.log('TypeScript reference generation complete.');
