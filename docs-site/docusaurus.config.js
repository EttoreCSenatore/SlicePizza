// @ts-check
// `@type` JSDoc annotations allow editor autocompletion and type checking
// (when paired with `@ts-check`).
// There are various equivalent ways to declare your Docusaurus config.
// See: https://docusaurus.io/docs/api/docusaurus-config

import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {themes as prismThemes} from 'prism-react-renderer';

import repoLinks from './src/remark/repo-links.js';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const siteDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(siteDir, '..');
const repoUrl = 'https://github.com/EttoreCSenatore/SlicePizza';
const baseUrl = '/SlicePizza/';

// The docs/adr/ files the site does not show as pages: README.md (how to
// write an ADR, with a hand-maintained table) and the blank template.
const ADR_INDEX = 'README.md';
const ADR_UNPUBLISHED = ['0000-template.md'];

// Every docs folder the site renders, for the repo-links remark plugin.
const sitePages = [
  {dir: path.join(siteDir, 'docs'), route: '/docs'},
  {
    dir: path.join(repoRoot, 'docs/adr'),
    route: '/adr',
    index: ADR_INDEX,
    unpublished: ADR_UNPUBLISHED,
  },
];

/** Remark plugin config for a docs instance whose content is in `contentDir`. */
const repoLinksFor = (contentDir) => [
  repoLinks,
  {repoRoot, githubUrl: repoUrl, branch: 'main', contentDir, sitePages},
];

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'SlicePizza',
  tagline: "Hands-on DevOps learning project for Zé's Pizzeria",
  // PNG for every browser; SVG (sharper) for browsers that support it.
  // See headTags below.
  favicon: 'img/favicon.png',

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // GitHub Pages serves a project site at https://<user>.github.io/<repo>/,
  // so every asset and link must live under /SlicePizza/.
  url: 'https://ettorecsenatore.github.io',
  baseUrl,
  // GitHub Pages redirects /page to /page/ unless this is set explicitly.
  trailingSlash: false,

  // GitHub pages deployment config.
  organizationName: 'EttoreCSenatore',
  projectName: 'SlicePizza',

  onBrokenLinks: 'throw',

  headTags: [
    {
      tagName: 'link',
      attributes: {rel: 'icon', type: 'image/svg+xml', href: `${baseUrl}img/logo.svg`},
    },
  ],

  markdown: {
    // For the WHOLE site: .md files are plain Markdown (CommonMark) and only
    // .mdx files may use MDX (imports, JSX components such as <Tabs>,
    // {expressions}). This lets the ADRs from docs/adr/, written by anyone
    // for GitHub, render as written. To use a component in a page, name the
    // page .mdx.
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
          editUrl: `${repoUrl}/tree/main/docs-site/`,
          beforeDefaultRemarkPlugins: [repoLinksFor(path.join(siteDir, 'docs'))],
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
      // The site now depends on files outside docs-site/: a CI or deploy job
      // filtered by path must watch both docs-site/** and docs/adr/**.
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
        editUrl: ({docPath}) => `${repoUrl}/tree/main/docs/adr/${docPath}`,
        // The ADR list at /adr is generated from the files (sidebarsAdr.js),
        // so it can never miss one. README.md and the template stay on GitHub.
        exclude: [
          // Docusaurus defaults (setting `exclude` replaces them):
          '**/_*.{js,jsx,ts,tsx,md,mdx}',
          '**/_*/**',
          '**/*.test.{js,jsx,ts,tsx}',
          '**/__tests__/**',
          ADR_INDEX,
          ...ADR_UNPUBLISHED,
        ],
        // Relative links in ADRs (../ARCHITECTURE.md, README.md...) work on
        // GitHub; this plugin makes them work on the site too.
        beforeDefaultRemarkPlugins: [repoLinksFor(path.join(repoRoot, 'docs/adr'))],
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      // Preview image when a page is shared (Slack, X, LinkedIn...).
      image: 'img/social-card.png',
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
