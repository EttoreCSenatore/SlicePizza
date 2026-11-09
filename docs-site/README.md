# SlicePizza docs site

Docusaurus site for the SlicePizza project documentation.

## Requirements

Node.js 20 or newer (required by Docusaurus 3.10) and npm.

## Commands

Install the dependencies:

```bash
npm install
```

Start the development server (http://localhost:3000/SlicePizza/):

```bash
npm start
```

Build the static site into `build/`:

```bash
npm run build
```

Serve the built site locally:

```bash
npm run serve
```

## Where the content lives

| Content | Source | Sidebar |
|---|---|---|
| Guides (introduction, phases) | `docs-site/docs/` | `sidebars.js` |
| ADRs | `docs/adr/` at the repository root, rendered as-is | `sidebarsAdr.js` (automatic) |

To add an ADR, follow `docs/adr/README.md`. It shows up on the site automatically.

The site is configured for GitHub Pages at `https://ettorecsenatore.github.io/SlicePizza/`
(see `baseUrl` in `docusaurus.config.js`).
