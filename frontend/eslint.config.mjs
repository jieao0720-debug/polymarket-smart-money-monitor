import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({ baseDirectory: __dirname });

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // Security guard: never log payloads/secrets from app code (development-rules #16).
      "no-console": ["error", { allow: ["warn", "error"] }],
    },
  },
  { ignores: ["node_modules/**", ".next/**", "out/**"] },
];

export default eslintConfig;
