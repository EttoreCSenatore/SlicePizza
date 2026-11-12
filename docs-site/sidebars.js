// @ts-check

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/**
 * Sidebar for the SlicePizza documentation. The order of the pages is defined
 * here (not with sidebar_position front matter).
 *
 * The ADRs have their own sidebar: see sidebarsAdr.js.
 *
 * @type {import('@docusaurus/plugin-content-docs').SidebarsConfig}
 */
const sidebars = {
  docsSidebar: [
    'intro',
    {
      type: 'category',
      label: 'Phase 1',
      items: ['phase-1/overview', 'phase-1/api', 'phase-1/docker'],
    },
  ],
};

export default sidebars;
