import coreWebVitals from 'eslint-config-next/core-web-vitals';
import nextTypescript from 'eslint-config-next/typescript';

/**
 * Flat config. `eslint-config-next` ships native flat configs, so no
 * eslintrc compatibility layer is needed.
 */
const config = [
  { ignores: ['.next/**', 'node_modules/**', 'playwright-report/**', 'test-results/**'] },
  ...coreWebVitals,
  ...nextTypescript,
  {
    rules: {
      // console.warn/error are kept: they are how client-side errors surface.
      'no-console': ['error', { allow: ['warn', 'error'] }],
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      eqeqeq: ['error', 'smart'],
    },
  },
];

export default config;
