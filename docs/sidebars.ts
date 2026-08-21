import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    {
      type: 'category',
      label: 'Get started',
      collapsed: false,
      items: ['quick-start', 'concepts'],
    },
    {
      type: 'category',
      label: 'Guides',
      collapsed: false,
      link: {type: 'doc', id: 'guides/index'},
      items: ['guides/livekit', 'guides/langgraph'],
    },
    {
      type: 'category',
      label: 'API Reference',
      collapsed: false,
      link: {type: 'doc', id: 'api/index'},
      items: [
        'api/livekit',
        'api/langgraph',
        'api/core',
        'api/env-vars',
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      collapsed: false,
      items: ['changelog'],
    },
  ],
};

export default sidebars;
