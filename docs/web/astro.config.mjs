// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import tailwind from "@astrojs/tailwind";
import remarkMath from "remark-math";
import rehypeMathjax from "rehype-mathjax";
import { writeFileSync, unlinkSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Google Analytics is injected only when both of these are true:
//   - PUBLIC_GA_MEASUREMENT_ID is set (only populated by infra for the
//     production Amplify app; empty/unset everywhere else)
//   - PUBLIC_DEPLOYMENT_ENVIRONMENT is exactly "production"
// This dual gate means a misconfiguration in either layer alone (e.g. the ID
// accidentally being set for a non-prod environment) still won't cause
// analytics to be sent from localhost or a lower environment.
const gaMeasurementId = process.env.PUBLIC_GA_MEASUREMENT_ID;
const isProductionDeployment = process.env.PUBLIC_DEPLOYMENT_ENVIRONMENT === "production";
const gaEnabled = Boolean(gaMeasurementId && isProductionDeployment);

// The gtag.js init snippet must call `gtag('config', ID)` with JS, which
// normally means an inline <script>. Astro's CSP hashing only auto-hashes
// scripts it compiles itself (see note below) — it does NOT hash raw content
// injected via Starlight's `head` config, and the hash would depend on the
// exact GA ID text anyway. To avoid a fragile hand-computed hash, the init
// code is instead written to a same-origin static file at config-eval time
// and loaded via a normal external <script src>, which needs no CSP hash at
// all (only `script-src 'self'`, already allowed by default).
const gaInitScriptPath = fileURLToPath(new URL("./public/ga-init.js", import.meta.url));
if (gaEnabled) {
    writeFileSync(
        gaInitScriptPath,
        `window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag("js", new Date());
gtag("config", "${gaMeasurementId}");
`,
    );
} else {
    // Remove any stale file from a previous local build so a leftover
    // (unreferenced) file never lingers with an old ID.
    try {
        unlinkSync(gaInitScriptPath);
    } catch {
        // Nothing to remove.
    }
}

const analyticsHead = gaEnabled
    ? [
          {
              tag: "script",
              attrs: {
                  src: `https://www.googletagmanager.com/gtag/js?id=${gaMeasurementId}`,
                  async: true,
              },
          },
          {
              tag: "script",
              attrs: { src: "/ga-init.js", defer: true },
          },
      ]
    : [];

// https://astro.build/config
export default defineConfig({
    experimental: {
        // Emit per-page CSP <meta> tags with hashes for Astro/Starlight's
        // bundled inline scripts so they satisfy a strict `script-src 'self'`
        // policy (e.g. the default security headers applied by AWS Amplify
        // Hosting) without needing 'unsafe-inline'.
        //
        // Astro only auto-hashes inline scripts/styles that pass through its
        // own build pipeline. A few pieces of inline content bypass that
        // pipeline by design and are therefore never auto-hashed, so their
        // hashes are listed explicitly below:
        //   - Starlight's `<script is:inline>` tags (ThemeProvider,
        //     SidebarPersister, Search) are intentionally left untouched by
        //     Astro to avoid a flash of unstyled/wrong-theme content.
        //   - The `<style>` block injected by rehype-mathjax for SVG math
        //     rendering is raw HTML emitted by the markdown pipeline, not an
        //     Astro-owned `<style>` tag.
        //
        // NOTE: if `@astrojs/starlight` or `rehype-mathjax` are upgraded and
        // change the exact content of these scripts/styles, these hashes will
        // no longer match and the CSP will block them again. Recompute them
        // (e.g. `openssl dgst -sha256 -binary <<< '<script content>' | openssl base64`)
        // if console CSP errors reappear after a dependency upgrade.
        csp: {
            scriptDirective: {
                hashes: [
                    // @astrojs/starlight/components/ThemeProvider.astro
                    "sha256-VWo5Wp4aqSj6nSgMpeAp9cKieaoIfwFUAunAVugI5gA=",
                    // @astrojs/starlight/components/Search.astro
                    "sha256-f/zAUE74ucc3JYp4r4QQvkJofoQdkOIhHYK+jeZ6eko=",
                    // @astrojs/starlight/components/SidebarPersister.astro (x2)
                    "sha256-wX2yOADeV+NMngflD5uYi3vl50SHC4sfM1EmylVjlX4=",
                    "sha256-7eCV4jtsr4t4knb3c4FCRPeu7GGZeOUGE3XvWix0XOQ=",
                ],
                // Astro's default script-src resources already include
                // 'self'; since setting `resources` overrides that default
                // entirely, 'self' must be repeated here whenever we add the
                // Google Tag Manager host for the gtag.js loader script.
                ...(gaEnabled && { resources: ["'self'", "https://www.googletagmanager.com"] }),
            },
            styleDirective: {
                hashes: [
                    // rehype-mathjax SVG output styles
                    "sha256-kuk5TvxZ/Kwuobo4g6uasb1xRQwr1+nfa1A3YGePO7U=",
                ],
            },
        },
    },
    vite: {
        resolve: {
            alias: {
                "@": new URL("./src", import.meta.url).pathname,
            },
        },
    },
    markdown: {
        remarkPlugins: [remarkMath],
        rehypePlugins: [rehypeMathjax],
    },
    integrations: [
        starlight({
            title: "Low Carbon Contracts",
            favicon: "/favicon.ico",
            head: analyticsHead,
            logo: {
                light: "./src/assets/logo-light.png",
                dark: "./src/assets/logo-dark.png",
                alt: "Low Carbon Contracts Logo",
                replacesTitle: true,
            },
            social: [
                {
                    icon: "github",
                    label: "GitHub",
                    href: "https://github.com/LCCC-Tech",
                },
            ],
            sidebar: [
                {
                    label: "Intro",
                    link: "/",
                },
                {
                    label: "Concepts",
                    autogenerate: {
                        directory: "concepts",
                        collapsed: true,
                    },
                },
                {
                    label: "Guides",
                    autogenerate: {
                        directory: "guides",
                        collapsed: true,
                    },
                },
                {
                    label: "Tutorials",
                    autogenerate: {
                        directory: "tutorials",
                        collapsed: true,
                    },
                },
                {
                    label: "Reference",
                    autogenerate: {
                        directory: "reference",
                        collapsed: true,
                    },
                },
            ],
            customCss: ["./src/global.css"],
            components: {
                Header: "./src/components/Header.astro",
                ThemeSelect: "./src/components/ThemeSelect.astro",
                TwoColumnContent: "./src/components/AccessibleTwoColumnContent.astro",
            },
        }),
        tailwind({ applyBaseStyles: false }),
    ],
});
