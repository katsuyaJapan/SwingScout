import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "public/data"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  { languageOptions: { globals: globals.browser }, rules: { "@typescript-eslint/no-unused-vars": ["error", { "argsIgnorePattern": "^_" }] } },
);
