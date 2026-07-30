import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'Parlot SDK',
  tagline: 'Open-source instrumentation for multi-agent observability',
  favicon: 'img/favicon.ico',

  headTags: [
    {
      tagName: 'link',
      attributes: {
        rel: 'icon',
        type: 'image/png',
        sizes: '32x32',
        href: '/docs/img/favicon-32x32.png',
      },
    },
    {
      tagName: 'link',
      attributes: {
        rel: 'icon',
        type: 'image/png',
        sizes: '16x16',
        href: '/docs/img/favicon-16x16.png',
      },
    },
    {
      tagName: 'link',
      attributes: {
        rel: 'apple-touch-icon',
        href: '/docs/img/apple-touch-icon.png',
      },
    },
  ],

  future: {
    v4: true,
  },

  // Served at https://parlot.ai/docs (marketing Worker assets). Local: /docs/
  url: 'https://parlot.ai',
  baseUrl: '/docs/',

  organizationName: 'parlot-ai',
  projectName: 'sdk',

  onBrokenLinks: 'throw',

  markdown: {
    format: 'detect',
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'throw',
    },
  },

  themes: [
    '@docusaurus/theme-mermaid',
    [
      require.resolve('@easyops-cn/docusaurus-search-local'),
      {
        hashed: true,
        language: ['en'],
        indexDocs: true,
        indexBlog: false,
        indexPages: true,
        docsRouteBasePath: '/',
        highlightSearchTermsOnTargetPage: true,
        searchBarShortcutHint: true,
      },
    ],
  ],

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          routeBasePath: '/',
          editUrl: 'https://github.com/parlot-ai/sdk/tree/main/docs/',
        },
        blog: false,
        sitemap: {
          changefreq: 'weekly',
          priority: 0.5,
          // Local search UI is not a content landing page — keep it out of the index.
          ignorePatterns: ['**/search/**'],
          filename: 'sitemap.xml',
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/logo.webp',
    metadata: [
      {
        name: 'description',
        content:
          'Parlot SDK docs — OpenTelemetry instrumentation for multi-agent voice AI. Quick start, concepts, and LiveKit guides.',
      },
      {property: 'og:type', content: 'website'},
      {name: 'twitter:card', content: 'summary'},
    ],
    colorMode: {
      defaultMode: 'light',
      respectPrefersColorScheme: true,
    },
    docs: {
      sidebar: {
        hideable: false,
        autoCollapseCategories: false,
      },
    },
    navbar: {
      title: 'Parlot SDK',
      logo: {
        alt: 'Parlot',
        src: 'img/logo.webp',
      },
      items: [
        {to: '/', label: 'Overview', position: 'left'},
        {to: '/quick-start', label: 'Quick Start', position: 'left'},
        {to: '/concepts', label: 'Concepts', position: 'left'},
        {to: '/guides', label: 'Guides', position: 'left'},
        {to: '/changelog', label: 'Changelog', position: 'left'},
        {
          href: 'https://github.com/parlot-ai/sdk',
          label: 'GitHub',
          position: 'right',
          className: 'header-github-link',
          'aria-label': 'Parlot SDK on GitHub',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            {label: 'Quick Start', to: '/quick-start'},
            {label: 'LiveKit guide', to: '/guides/livekit'},
          ],
        },
        {
          title: 'More',
          items: [
            {
              label: 'GitHub',
              href: 'https://github.com/parlot-ai/sdk',
              className: 'footer-github-link',
              'aria-label': 'Parlot SDK on GitHub',
            },
            {label: 'Changelog', to: '/changelog'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Parlot.ai`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'python', 'toml', 'json'],
    },
    mermaid: {
      theme: {light: 'neutral', dark: 'dark'},
      options: {
        maxTextSize: 100000,
      },
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
