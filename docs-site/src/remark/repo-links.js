// @ts-check
/**
 * Remark plugin: make relative links to repository files work on the site.
 *
 * The Markdown in this repository is also read on GitHub, so authors write
 * relative links such as `../ARCHITECTURE.md` or `../../api/README.md`.
 * Docusaurus only understands links to pages it renders itself, and with
 * `onBrokenLinks: 'throw'` any other relative link fails the build.
 *
 * For every relative link to a file that exists, this plugin:
 *   - leaves it alone when the target is a page rendered from the same docs
 *     folder (Docusaurus resolves those and checks them);
 *   - points it to the site page when the site shows it elsewhere
 *     (another docs folder, or a folder's index page);
 *   - points it to the file on GitHub otherwise.
 *
 * Links to files that do not exist are left untouched, so the build still
 * fails on them: a typo is never silently turned into a GitHub 404.
 */

import fs from 'node:fs';
import path from 'node:path';

/**
 * @typedef {object} SitePages
 * @property {string} dir Absolute folder rendered by a docs plugin instance.
 * @property {string} route Site route of that folder, e.g. '/adr'.
 * @property {string} [index] File whose content the folder's index page
 *   stands for (it is not rendered itself), e.g. 'README.md'.
 * @property {string[]} [unpublished] Files of `dir` the site does not show.
 *
 * @typedef {object} Options
 * @property {string} repoRoot Absolute path of the repository root.
 * @property {string} githubUrl Repository URL, e.g. 'https://github.com/<owner>/<repo>'.
 * @property {string} branch Branch the GitHub links point to, e.g. 'main'.
 * @property {string} contentDir Folder of the docs instance using this plugin.
 * @property {SitePages[]} sitePages Every docs folder the site renders.
 */

const SCHEME = /^[a-z][a-z0-9+.-]*:/i;

/** @param {string} child @param {string} parent */
function isInside(child, parent) {
  const relative = path.relative(parent, child);
  return relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative);
}

/** @param {string} filePath */
function toPosix(filePath) {
  return filePath.split(path.sep).join('/');
}

/**
 * Where the site shows `target`: its route, and whether it is a doc rendered
 * from `pages.dir` (as opposed to the folder's index page). Undefined when the
 * site does not show it at all.
 *
 * @param {string} target @param {SitePages[]} sitePages
 * @returns {{route: string, dir: string, isDoc: boolean} | undefined}
 */
function siteLocation(target, sitePages) {
  for (const pages of sitePages) {
    if (!isInside(target, pages.dir)) continue;
    const relative = toPosix(path.relative(pages.dir, target));
    if (relative === pages.index) {
      return {route: pages.route, dir: pages.dir, isDoc: false};
    }
    if (pages.unpublished?.includes(relative) || !/\.mdx?$/.test(relative)) {
      return undefined;
    }
    const slug = relative.replace(/\.mdx?$/, '');
    return {route: `${pages.route}/${slug}`, dir: pages.dir, isDoc: true};
  }
  return undefined;
}

/** @param {any} node @param {(node: any) => void} visit */
function walk(node, visit) {
  visit(node);
  for (const child of node.children ?? []) walk(child, visit);
}

/** @param {Options} options */
export default function repoLinks(options) {
  const {repoRoot, githubUrl, branch, contentDir, sitePages} = options;

  return (/** @type {any} */ tree, /** @type {any} */ file) => {
    if (!file.path) return;
    const fromDir = path.dirname(file.path);

    walk(tree, (node) => {
      if (node.type !== 'link' && node.type !== 'definition') return;
      const url = node.url ?? '';
      if (!url || url.startsWith('#') || url.startsWith('/') || SCHEME.test(url)) {
        return;
      }

      const hashIndex = url.indexOf('#');
      const pathPart = hashIndex === -1 ? url : url.slice(0, hashIndex);
      const hash = hashIndex === -1 ? '' : url.slice(hashIndex);
      if (!pathPart) return;

      const target = path.resolve(fromDir, decodeURIComponent(pathPart));
      if (!fs.existsSync(target)) return; // let the build report it

      const location = siteLocation(target, sitePages);
      if (location?.isDoc && location.dir === contentDir) return;
      if (location) {
        node.url = location.route + hash;
      } else if (isInside(target, repoRoot)) {
        const relative = toPosix(path.relative(repoRoot, target));
        const kind = fs.statSync(target).isDirectory() ? 'tree' : 'blob';
        node.url = `${githubUrl}/${kind}/${branch}/${encodeURI(relative)}${hash}`;
      }
    });
  };
}
