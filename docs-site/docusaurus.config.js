// @ts-check
// `@type` JSDoc annotations allow editor autocompletion and type checking
// (when paired with `@ts-check`).
// There are various equivalent ways to declare your Docusaurus config.
// See: https://docusaurus.io/docs/api/docusaurus-config

import {themes as prismThemes} from 'prism-react-renderer';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'SlicePizza',
  tagline: "Hands-on DevOps learning project for Zé's Pizzeria",
  favicon: 'img/logo.svg',

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // GitHub Pages serves a project site at https://<user>.github.io/<repo>/,
  // so every asset and link must live under /SlicePizza/.
  url: 'https://ettorecsenatore.github.io',
  baseUrl: '/SlicePizza/',
  // GitHub Pages redirects /page to /page/ unless this is set explicitly.
  trailingSlash: false,

  // GitHub pages deployment config.
  organizationName: 'EttoreCSenatore',
  projectName: 'SlicePizza',

  onBrokenLinks: 'throw',

  markdown: {
    // .md files are plain Markdown and only .mdx files may contain JSX, so
    // the ADRs from docs/adr/ render as written, whoever writes them.
    format: 'detect',
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: './sidebars.js',
          // The site lives in docs-site/, so the edit links must include it.
          editUrl:
            'https://github.com/EttoreCSenatore/SlicePizza/tree/main/docs-site/',
        },
        // The demo blog is not used by SlicePizza.
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      }),
    ],
  ],

  plugins: [
    [
      // Render the ADRs straight from the repository's docs/adr/ folder, so
      // they have a single source of truth and new ADRs appear automatically.
      '@docusaurus/plugin-content-docs',
      /** @type {import('@docusaurus/plugin-content-docs').Options} */
      ({
        id: 'adr',
        path: '../docs/adr',
        routeBasePath: 'adr',
        // Keep the ADR number in the URL: /adr/0001-monorepo, not /adr/monorepo.
        numberPrefixParser: false,
        sidebarPath: './sidebarsAdr.js',
        // docPath is relative to docs/adr/ (a plain string would be joined with
        // the path from docs-site/, giving .../docs/adr/../docs/adr/...).
        editUrl: ({docPath}) =>
          `https://github.com/EttoreCSenatore/SlicePizza/tree/main/docs/adr/${docPath}`,
        // README.md is the overview, placed first in sidebarsAdr.js. Keep it
        // out of the automatic list so it does not appear twice.
        async sidebarItemsGenerator({defaultSidebarItemsGenerator, ...args}) {
          const items = await defaultSidebarItemsGenerator(args);
          return items.filter(
            (item) => !(item.type === 'doc' && item.id === 'README'),
          );
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      colorMode: {
        respectPrefersColorScheme: true,
      },
      navbar: {
        title: 'SlicePizza',
        logo: {
          alt: 'SlicePizza logo',
          src: 'img/logo.svg',
        },
        items: [
          {
            type: 'docSidebar',
            sidebarId: 'docsSidebar',
            position: 'left',
            label: 'Docs',
          },
          {
            type: 'docSidebar',
            sidebarId: 'adrSidebar',
            docsPluginId: 'adr',
            position: 'left',
            label: 'ADRs',
          },
          {
            href: 'https://github.com/EttoreCSenatore/SlicePizza',
            label: 'GitHub',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'Docs',
            items: [
              {
                label: 'Introduction',
                to: '/docs/intro',
              },
              {
                label: 'ADRs',
                to: '/adr',
              },
            ],
          },
          {
            title: 'Project',
            items: [
              {
                label: 'GitHub',
                href: 'https://github.com/EttoreCSenatore/SlicePizza',
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} SlicePizza. Built with Docusaurus.`,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
      },
    }),
};

export default config;
