import { access, readFile, readdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const siteOrigin = "https://docs.lowcarboncontracts.uk";
const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const outputDirectory = path.resolve(scriptDirectory, "../dist");

async function collectHtmlFiles(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    const files = await Promise.all(
        entries.map((entry) => {
            const entryPath = path.join(directory, entry.name);
            return entry.isDirectory() ? collectHtmlFiles(entryPath) : [entryPath];
        }),
    );

    return files.flat().filter((file) => file.endsWith(".html"));
}

function routeForFile(file) {
    const relativePath = path.relative(outputDirectory, file);
    if (relativePath === "index.html") return "/";
    if (relativePath.endsWith(`${path.sep}index.html`)) {
        return `/${relativePath.slice(0, -"index.html".length).split(path.sep).join("/")}`;
    }
    return `/${relativePath.split(path.sep).join("/")}`;
}

function outputPathForUrl(url) {
    const pathname = decodeURIComponent(url.pathname);
    const relativePath = pathname.replace(/^\/+/, "");

    if (pathname.endsWith("/")) return path.join(outputDirectory, relativePath, "index.html");
    return path.join(outputDirectory, relativePath);
}

function extractAttributes(html) {
    return [...html.matchAll(/\b(?:href|src)=(?:"([^"]+)"|'([^']+)')/g)].map(
        (match) => match[1] ?? match[2],
    );
}

function extractIds(html) {
    return new Set(
        [...html.matchAll(/\bid=(?:"([^"]+)"|'([^']+)')/g)].map(
            (match) => match[1] ?? match[2],
        ),
    );
}

async function exists(file) {
    try {
        await access(file);
        return true;
    } catch {
        return false;
    }
}

function decode(value, sourceRoute, rawTarget) {
    try {
        return decodeURIComponent(value);
    } catch {
        failures.push(`${sourceRoute} -> ${rawTarget} (invalid percent encoding)`);
        return undefined;
    }
}

const htmlFiles = await collectHtmlFiles(outputDirectory);
const documents = new Map();

for (const file of htmlFiles) {
    const html = await readFile(file, "utf8");
    documents.set(file, { html, ids: extractIds(html) });
}

const failures = [];

for (const [sourceFile, { html }] of documents) {
    const sourceRoute = routeForFile(sourceFile);
    if (sourceRoute === "/404.html") continue;
    const sourceUrl = new URL(sourceRoute, siteOrigin);

    for (const rawTarget of extractAttributes(html)) {
        if (
            rawTarget === "" ||
            rawTarget.startsWith("mailto:") ||
            rawTarget.startsWith("tel:") ||
            rawTarget.startsWith("data:") ||
            rawTarget.startsWith("javascript:")
        ) {
            continue;
        }

        const targetUrl = new URL(rawTarget, sourceUrl);
        if (targetUrl.origin !== siteOrigin) continue;

        const decodedPathname = decode(targetUrl.pathname, sourceRoute, rawTarget);
        if (decodedPathname === undefined) continue;
        targetUrl.pathname = decodedPathname;

        let targetFile = outputPathForUrl(targetUrl);
        if (!path.extname(targetUrl.pathname) && !targetUrl.pathname.endsWith("/")) {
            targetFile = path.join(targetFile, "index.html");
        }
        if (!(await exists(targetFile))) {
            failures.push(`${sourceRoute} -> ${rawTarget} (missing ${targetUrl.pathname})`);
            continue;
        }

        if (targetUrl.hash && targetFile.endsWith(".html")) {
            const fragment = decode(targetUrl.hash.slice(1), sourceRoute, rawTarget);
            if (fragment === undefined) continue;
            const targetDocument =
                documents.get(targetFile) ?? {
                    ids: extractIds(await readFile(targetFile, "utf8")),
                };
            if (!targetDocument.ids.has(fragment)) {
                failures.push(`${sourceRoute} -> ${rawTarget} (missing #${fragment})`);
            }
        }
    }
}

if (failures.length > 0) {
    console.error(`Found ${failures.length} invalid internal link(s):`);
    for (const failure of failures) console.error(`- ${failure}`);
    process.exitCode = 1;
} else {
    console.log(`Checked ${htmlFiles.length} generated HTML files: all internal links are valid.`);
}
