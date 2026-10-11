import type { Config } from "tailwindcss";
const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: { extend: { colors: { brand: { 50: "#f0fdf4", 500: "#22c55e", 600: "#16a34a", 700: "#15803d", 900: "#14532d" } } } },
  plugins: [],
};
export default config;
