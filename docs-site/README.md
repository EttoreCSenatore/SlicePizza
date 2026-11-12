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
| ADRs | `docs/adr/` at the repository root, rendered as-is | `sidebarsAdr.js` (generated) |

- The ADR list at `/adr` is **generated from the files**, so a new ADR shows up
  automatically. Follow `docs/adr/README.md` to write one.
- `docs/adr/README.md` (how to write an ADR) and `0000-template.md` stay on
  GitHub only; links to them from the site go to GitHub (or, for the README,
  to the `/adr` list).
- The guides explain concepts; exact commands and API details live in the
  READMEs next to the code (`README.md`, `api/README.md`). Link to them instead
  of copying them, so the two never disagree.

### Links

Write normal **relative** links, the kind that work on GitHub
(`../ARCHITECTURE.md`, `../../../api/README.md#tests`). The
`src/remark/repo-links.js` plugin makes them work on the site too: a page the
site renders opens on the site, anything else opens on GitHub. A link to a file
that does not exist still fails the build.

### Markdown vs MDX

`.md` files are plain Markdown (`markdown.format: 'detect'`), so the ADRs render
exactly as written. To use MDX (imports, JSX components such as `<Tabs>`,
`{expressions}`), name the page `.mdx`.

### CI and deploy

The site is built from **two** folders: `docs-site/` and `docs/adr/`. Any CI or
deploy workflow filtered by path must watch both:

```yaml
on:
  push:
    paths: ["docs-site/**", "docs/adr/**"]
```

The [Docs site](../.github/workflows/docs-site.yml) workflow does exactly that:

- On a Pull Request that touches those folders, it builds the site. A broken
  link fails the build, so it fails the check.
- On `main`, it builds and publishes the site to GitHub Pages at
  **https://senatoreteam.github.io/SlicePizza/** (see `baseUrl` in
  `docusaurus.config.js`). Nobody publishes by hand: merging is the deploy.

GitHub Pages is set to **Source: GitHub Actions** (Settings → Pages). To
publish again without a change, run the workflow from the Actions tab.

## Images

`static/img/logo.svg` is the source. If it changes, regenerate the PNGs with
ImageMagick 7:

```bash
# Favicon for browsers without SVG favicon support
magick -background none -density 600 static/img/logo.svg -trim -resize 32x32 \
  -gravity center -extent 32x32 static/img/favicon.png

# Social card (link previews on Slack, X, LinkedIn...)
magick -respect-parentheses -size 1200x630 xc:'#1f2937' \
  \( -background none -density 1200 static/img/logo.svg -resize '380x380!' \) \
  -gravity west -geometry +70+0 -composite -gravity northwest \
  -font DejaVu-Sans-Bold -pointsize 96 -fill white -annotate +500+200 'SlicePizza' \
  -font DejaVu-Sans -pointsize 38 -fill '#f6c445' -annotate +506+335 'Hands-on DevOps learning project' \
  -fill '#d1d5db' -pointsize 36 -annotate +506+392 "for Zé's Pizzeria" \
  -strip static/img/social-card.png
```
