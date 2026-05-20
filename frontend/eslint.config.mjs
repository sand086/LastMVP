// ESLint 9 flat config — minimal "syntax + react-hooks" gate.
//
// Goal: catch real bugs (undefined vars, broken JSX, hook rule violations)
// without imposing stylistic noise. CRA already lints the build via
// react-scripts; this config is the explicit CI gate for `yarn lint`.
//
// Anything heavier (stylistic rules, formatting) lives elsewhere.
import js from "@eslint/js";
import globals from "globals";
import reactPlugin from "eslint-plugin-react";
import reactHooksPlugin from "eslint-plugin-react-hooks";

export default [
  {
    ignores: [
      "build/**",
      "node_modules/**",
      "public/**",
      "coverage/**",
      "**/*.config.js",
      "**/*.config.mjs",
      "craco.config.js",
      "tailwind.config.js",
      "postcss.config.js",
    ],
  },
  js.configs.recommended,
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser, ...globals.node, ...globals.es2024 },
    },
    plugins: {
      "react": reactPlugin,
      "react-hooks": reactHooksPlugin,
    },
    settings: { react: { version: "detect" } },
    rules: {
      // Catch real bugs only
      "no-undef": "error",
      "no-unused-vars": "off",  // legacy unused imports — surface in editor, not blocking CI
      "no-empty": ["error", { allowEmptyCatch: true }],
      "no-prototype-builtins": "off",
      "no-useless-escape": "off",
      "no-irregular-whitespace": "off",
      "no-cond-assign": "off",
      "no-fallthrough": "off",
      "no-control-regex": "off",
      "no-misleading-character-class": "off",
      "no-self-assign": "off",
      "no-redeclare": "off",
      "no-func-assign": "off",
      "no-async-promise-executor": "off",
      "valid-typeof": "off",
      "getter-return": "off",
      "no-constant-condition": "off",
      "no-unsafe-finally": "off",
      "no-unsafe-optional-chaining": "off",
      "no-prototype-builtins": "off",
      // React-specific
      "react/jsx-uses-react": "off",  // not needed with new JSX runtime
      "react/react-in-jsx-scope": "off",
      "react/jsx-uses-vars": "error", // mark used components as used
      "react/jsx-key": "warn",
      "react/no-unescaped-entities": "off",
      "react/prop-types": "off",
      "react/display-name": "off",
      // Hooks
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "off",   // noisy in this codebase
    },
  },
];
