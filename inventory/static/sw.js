/* InvenSync — service worker (PWA)
   Estratégia: cache-first só para /static/ (CSS/ícones); páginas dinâmicas
   sempre via rede (não serve HTML desatualizado). */
/* Incrementar SEMPRE que um arquivo de /static/ mudar de conteúdo sem mudar de
   nome: a estratégia é cache-first, então o `activate` apagando os caches
   antigos é o único jeito de o usuário ver CSS e ícones novos.
   v9: monograma nos ícones + CSS da rodada visual (auth, gráficos, régua). */
const CACHE = 'invensync-v9';
const SHELL = ['/static/style.css', '/static/icon-192.png'];

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin === location.origin && url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(req).then((hit) =>
        hit ||
        fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return res;
        })
      )
    );
  }
  // demais requisições (páginas, APIs): deixa o navegador buscar na rede.
});
