import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { globals: globals.browser },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // Features talk to each other only through their index.ts.
      "no-restricted-imports": [
        "error",
        { patterns: [{ group: ["**/features/*/*"], message: "Import from the feature's index instead." }] },
      ],
    },
  },
  // Unit tests may reach into a feature to test one module directly.
  { files: ["tests/**"], rules: { "no-restricted-imports": "off" } },
);
