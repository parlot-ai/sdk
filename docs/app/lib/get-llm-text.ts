import type { source } from './source';

export async function getLLMText(page: (typeof source)['$inferPage']) {
  let processed = (await page.data.getText('processed')).trimStart();
  // Strip duplicate leading H1 header if processed markdown already starts with one
  processed = processed.replace(/^#\s+[^\n]*\n*/, '');
  return `# ${page.data.title} (${page.url})\n\n${processed.trim()}`;
}
