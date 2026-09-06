import { source } from '@/lib/source';
import { llms } from 'fumadocs-core/source';

export function loader() {
  return new Response(llms(source).index(), {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
}
