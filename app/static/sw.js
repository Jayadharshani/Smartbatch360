// Minimal service worker: makes the app installable (PWA). Offline order capture is NOT implemented.
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('fetch', e => {});
