import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

// Локализация инициализируется до первого рендера: иначе интерфейс успевает
// показаться на языке по умолчанию и переключиться уже на глазах у пользователя.
import './shared/i18n';
import './styles/global.css';

import { App } from './App';

const container = document.getElementById('root');

if (!container) {
  throw new Error('Не найден элемент #root — проверьте index.html');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
