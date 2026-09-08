import js from '@eslint/js';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'node_modules'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    settings: {
      react: { version: 'detect' },
    },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/consistent-type-imports': 'error',

      // ТЗ 10.3: интерфейс на трёх письменностях. Забытый литерал в компоненте — это
      // строка, которая никогда не переведётся, и обнаружится она на приёмке у
      // заказчика. Правило переводит эту ошибку из «когда-нибудь заметим» в «сборка
      // не прошла». Разрешены только разделители, не несущие смысла.
      'react/jsx-no-literals': [
        'error',
        {
          noStrings: true,
          ignoreProps: true,
          allowedStrings: ['·', '—', '–', '/', '×', ':', ',', '.'],
        },
      ],
    },
  },
  {
    // В тестах ожидаемые строки пишутся прямо в проверках — это и есть предмет проверки.
    files: ['**/*.test.{ts,tsx}', 'src/test-setup.ts'],
    rules: {
      'react/jsx-no-literals': 'off',
    },
  },
);
