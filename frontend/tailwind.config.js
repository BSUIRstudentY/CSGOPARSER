/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0c0f14",
        panel: "#151a22",
        line: "#2c3544",
        muted: "#8b97a8",
        paper: "#e8edf5",
        gold: "#e0b15a",
        gain: "#3dd68c",
        loss: "#f07178",
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
