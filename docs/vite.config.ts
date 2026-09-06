import { reactRouter } from '@react-router/dev/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';
import { fumadocsMdx } from 'fumadocs-mdx/vite';
import tsconfigPaths from 'vite-tsconfig-paths';

export default defineConfig({
  base: '/docs/',
  plugins: [fumadocsMdx(), tailwindcss(), reactRouter(), tsconfigPaths()],
});
