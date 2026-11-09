// @ts-check

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/**
 * Sidebar for the SlicePizza documentation.
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
    {
      type: 'category',
      label: 'ADRs',
      items: ['adr/overview'],
    },
  ],
};

export default sidebars;
