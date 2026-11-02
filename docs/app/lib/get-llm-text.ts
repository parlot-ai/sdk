import type { source } from './source';

/** Strip Shiki / Fumadocs code-notation comments left in processed markdown. */
function stripCodeNotations(markdown: string): string {
  return markdown
    .replace(/[ \t]*#\s*\[!code[^\]]*\]/g, '')
    .replace(/[ \t]*\/\/\s*\[!code[^\]]*\]/g, '')
    .replace(/[ \t]*\{\/\*\s*\[!code[^\]]*\]\s*\*\/\}/g, '');
}

export async function getLLMText(page: (typeof source)['$inferPage']) {
  let processed = (await page.data.getText('processed')).trimStart();
  // Strip duplicate leading H1 header if processed markdown already starts with one
  processed = processed.replace(/^#\s+[^\n]*\n*/, '');
  processed = stripCodeNotations(processed);
  return `# ${page.data.title} (${page.url})\n\n${processed.trim()}`;
}
