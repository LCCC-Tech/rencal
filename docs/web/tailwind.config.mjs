import colors from "tailwindcss/colors";
import starlightPlugin from "@astrojs/starlight-tailwind";

// Generated color palettes
const accent = {
    200: "#b5d3ae",
    600: "#257c00",
    900: "#153c0a",
    950: "#132b0d",
};
const gray = {
    100: "#f6f6f6",
    200: "#eeeeee",
    300: "#c2c2c2",
    400: "#8b8b8b",
    500: "#585858",
    700: "#383838",
    800: "#272727",
    900: "#181818",
};

/** @type {import('tailwindcss').Config} */
export default {
    content: ["./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}"],
    theme: {
        extend: {
            colors: {
                accent,
                gray,
            },
        },
    },
    plugins: [starlightPlugin()],
};
