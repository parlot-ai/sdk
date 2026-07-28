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
      items: ['guides/livekit', 'guides/livekit-integration'],
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
