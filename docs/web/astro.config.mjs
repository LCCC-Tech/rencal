// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import tailwind from "@astrojs/tailwind";
import remarkMath from "remark-math";
import rehypeMathjax from "rehype-mathjax";

// https://astro.build/config
export default defineConfig({
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
            },
        }),
        tailwind({ applyBaseStyles: false }),
    ],
});
