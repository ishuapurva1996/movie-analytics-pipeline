/* Apply the saved theme before styles load, including when data is unavailable. */
(() => {
  'use strict';
  const root = document.documentElement;
  const storageKey = 'movie-observatory-theme';
  try {
    root.dataset.theme = localStorage.getItem(storageKey) === 'light' ? 'light' : 'dark';
  } catch {
    root.dataset.theme = 'dark';
  }

  document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('theme-toggle');
    const label = button.querySelector('.theme-toggle-text');
    function updateControl() {
      const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      label.textContent = `${next === 'light' ? 'Light' : 'Dark'} mode`;
      button.setAttribute('aria-label', `Switch to ${next} mode`);
      button.title = `Switch to ${next} mode`;
      document.querySelector('meta[name="theme-color"]').content = root.dataset.theme === 'light' ? '#f0f2f5' : '#090b10';
    }
    updateControl();
    button.hidden = false;
    button.addEventListener('click', () => {
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(storageKey, root.dataset.theme); } catch { /* Browsing without storage still supports switching. */ }
      updateControl();
      document.dispatchEvent(new Event('dashboard-theme-change'));
    });
  });
})();
