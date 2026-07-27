import js from "@eslint/js";
import { FlatCompat } from "@eslint/eslintrc";
import { globalIgnores } from "eslint/config";

const compat = new FlatCompat({
  baseDirectory: import.meta.dirname,
  recommendedConfig: js.configs.recommended,
});

const eslintConfig = [
  ...compat.config({
    extends: ["eslint:recommended", "next/core-web-vitals", "next/typescript"],
  }),
  globalIgnores([".next/**", "node_modules/**", "coverage/**", "next-env.d.ts"]),
];

export default eslintConfig;
