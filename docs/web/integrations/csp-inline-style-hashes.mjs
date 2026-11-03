import { createHash } from "node:crypto";
import { readdir, readFile, writeFile } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const STYLE_ATTR_RE = /\sstyle="([^"]*)"/g;
const CSP_META_RE =
    /(<meta http-equiv="content-security-policy" content=")([^"]*)("\s*\/?>)/i;

/**
 * Astro's `experimental.csp` feature (as of Astro 5.16) only ever
 * auto-hashes `<style>` *element* content — it never sees `style="..."`
 * *attribute* values, and per the CSP3 spec, hash-sources don't apply to
 * style attributes at all unless the `'unsafe-hashes'` keyword is present
 * in `style-src`.
 *
 * A handful of things on this site render unique inline `style="..."`
 * attributes per page (Starlight icon sizes, Expressive Code's per-token
 * syntax-highlight colors, and — critically — rehype-mathjax's per-equation
 * `vertical-align` value, which is unique to every formula and grows with
 * every new doc page). Hardcoding these hashes in `astro.config.mjs` would
 * need updating every time a new formula or color combination is added.
 *
 * This integration runs after `astro build`, re-reads each generated HTML
 * file, hashes whatever inline `style="..."` values actually ended up on
 * that page, and rewrites that page's own CSP <meta> tag to add
 * `'unsafe-hashes'` plus those hashes — so it never goes stale.
 */
export default function cspInlineStyleHashes() {
    return {
        name: "csp-inline-style-hashes",
        hooks: {
            "astro:build:done": async ({ dir, logger }) => {
                const outDir = fileURLToPath(dir);
                const htmlFiles = await findHtmlFiles(outDir);

                let patchedCount = 0;
                for (const file of htmlFiles) {
                    const html = await readFile(file, "utf-8");
                    const patched = patchCsp(html);
                    if (patched !== html) {
                        await writeFile(file, patched, "utf-8");
                        patchedCount++;
                    }
                }

                logger.info(
                    `csp-inline-style-hashes: patched style-src in ${patchedCount}/${htmlFiles.length} page(s)`,
                );
            },
        },
    };
}

async function findHtmlFiles(dir) {
    const entries = await readdir(dir, { withFileTypes: true });
    const files = [];
    for (const entry of entries) {
        const fullPath = join(dir, entry.name);
        if (entry.isDirectory()) {
            files.push(...(await findHtmlFiles(fullPath)));
        } else if (extname(entry.name) === ".html") {
            files.push(fullPath);
        }
    }
    return files;
}

function patchCsp(html) {
    const match = html.match(CSP_META_RE);
    if (!match) return html;

    const [fullMatch, prefix, cspContent, suffix] = match;
    if (!/style-src/i.test(cspContent)) return html;

    const styleHashes = new Set();
    let attrMatch;
    STYLE_ATTR_RE.lastIndex = 0;
    while ((attrMatch = STYLE_ATTR_RE.exec(html))) {
        const value = attrMatch[1];
        if (!value) continue;
        const hash = createHash("sha256").update(value, "utf-8").digest("base64");
        styleHashes.add(`'sha256-${hash}'`);
    }

    if (styleHashes.size === 0) return html;

    const patchedCsp = cspContent.replace(
        /(style-src[^;]*)/i,
        (styleSrc) => {
            const additions = ["'unsafe-hashes'", ...styleHashes].filter(
                (token) => !styleSrc.includes(token),
            );
            return additions.length > 0
                ? `${styleSrc} ${additions.join(" ")}`
                : styleSrc;
        },
    );

    return html.replace(fullMatch, `${prefix}${patchedCsp}${suffix}`);
}
