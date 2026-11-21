import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

const noHtmlInjection = [
  "error",
  { property: "innerHTML", message: "No HTML injection (spec §3 Safe). Use text nodes or React." },
  { property: "outerHTML", message: "No HTML injection (spec §3 Safe). Use text nodes or React." },
  {
    property: "insertAdjacentHTML",
    message: "No HTML injection (spec §3 Safe). Use text nodes or React.",
  },
];

export default defineConfig(
  { ignores: ["dist/", "dist-ssr/", "node_modules/", "test-results/", "playwright-report/", "reference/"] },
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { react, "react-hooks": reactHooks },
    settings: { react: { version: "18.3" } },
    languageOptions: { globals: globals.browser },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs["jsx-runtime"].rules,
      // the two classic hook rules, as in v5's recommended set; v7's React Compiler rules
      // are not taken on (the code does not use the compiler)
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react/no-danger": "error",
    },
  },
  // The pre-rendered set: a style prop becomes style="…" in static HTML,
  // which the CSP (style-src 'self') blocks.
  {
    files: ["src/pages/**/*.{ts,tsx}", "src/ui/**/*.{ts,tsx}"],
    rules: { "react/forbid-dom-props": ["error", { forbid: ["style"] }] },
  },
  {
    files: ["scripts/**/*.mjs", "*.config.{js,ts}"],
    languageOptions: { globals: globals.node },
  },
  {
    files: ["public/**/*.js"],
    languageOptions: { sourceType: "script", globals: globals.browser },
  },
  { rules: { "no-restricted-properties": noHtmlInjection } },
);
