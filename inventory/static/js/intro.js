/* Apresentação do InvenSync — animações da tela de boas-vindas.

   O fundo de bolhas vive em `bolhas.js`, componente compartilhado com a tela
   de login. Aqui ficam só as animações do conteúdo (revelação por scroll) e a
   amarração da câmera ao rolar da página.
*/
import { criarFundoBolhas } from './bolhas.js';

const { gsap } = window;
gsap.registerPlugin(window.ScrollTrigger);

const MENOS_MOVIMENTO = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ------------------------------------------------------------------ */
/* 5. Animações de texto e cards                                       */
/* ------------------------------------------------------------------ */
function animarConteudo() {
  const st = { start: 'top 82%', toggleActions: 'play none none reverse' };

  const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });
  tl.from('#introHero .linha > span', { yPercent: 115, duration: 1.1, stagger: 0.12 })
    .from('#introHero [data-anim="rotulo"]', { opacity: 0, x: -18, duration: 0.7 }, 0.15)
    .from('#introHero [data-anim="logo"]', { opacity: 0, scale: 0.8, duration: 0.8 }, 0.3)
    .from('#introHero [data-anim="lead"]', { opacity: 0, y: 22, duration: 0.8 }, 0.55)
    .from('#introHero [data-anim="btn"]', { opacity: 0, y: 18, duration: 0.7 }, 0.75);

  document.querySelectorAll('[data-split]').forEach((h) => {
    const palavras = h.textContent.trim().split(' ');
    h.innerHTML = palavras.map((p) => `<span class="linha"><span>${p}&nbsp;</span></span>`).join('');
    h.style.display = 'flex';
    h.style.flexWrap = 'wrap';
    h.style.justifyContent = 'center';   // o título vira flex: precisa centralizar
    gsap.from(h.querySelectorAll('.linha > span'), {
      yPercent: 115, duration: 0.85, ease: 'power3.out', stagger: 0.055,
      scrollTrigger: { trigger: h, ...st },
    });
  });

  document.querySelectorAll('[data-anim]:not(#introHero [data-anim])').forEach((el) => {
    gsap.from(el, { opacity: 0, y: 24, duration: 0.8, ease: 'power2.out',
      scrollTrigger: { trigger: el, ...st } });
  });

  document.querySelectorAll('[data-cards]').forEach((grade) => {
    gsap.from(grade.children, {
      opacity: 0, y: 46, scale: 0.96, duration: 0.75, ease: 'power2.out', stagger: 0.075,
      scrollTrigger: { trigger: grade, ...st },
    });
  });

  document.querySelectorAll('[data-stagger]').forEach((box) => {
    gsap.from(box.children, { opacity: 0, y: 16, duration: 0.5, stagger: 0.06,
      ease: 'power2.out', scrollTrigger: { trigger: box, ...st } });
  });

  const trilho = document.getElementById('trilho');
  if (trilho) {
    gsap.to(trilho, { scaleY: 1, ease: 'none',
      scrollTrigger: { trigger: '#linhaFluxo', start: 'top 70%', end: 'bottom 75%', scrub: 0.6 } });
    document.querySelectorAll('.etapa').forEach((et) => {
      // Entrada por baixo: não empurra nada para os lados, então não há risco
      // de criar rolagem horizontal em tela estreita.
      gsap.from(et, { opacity: 0, y: 26, duration: 0.7, ease: 'power2.out',
        scrollTrigger: { trigger: et, start: 'top 84%',
          onEnter: () => et.classList.add('viva'),
          onLeaveBack: () => et.classList.remove('viva') } });
    });
  }

  gsap.to('#introProgresso', { scaleX: 1, ease: 'none',
    scrollTrigger: { trigger: document.body, start: 'top top', end: 'bottom bottom', scrub: 0.3 } });

  gsap.to('#introRolar', { opacity: 0, duration: 0.4,
    scrollTrigger: { trigger: '#introHero', start: 'top -80px', toggleActions: 'play none none reverse' } });

  return tl;
}

/* ------------------------------------------------------------------ */
/* 5b. Conteúdo que flutua sobre o fundo                               */
/* ------------------------------------------------------------------ */
/* Os CARDS (módulos, recursos, benefícios) ficam ESTÁTICOS: sem flutuação
   contínua, sem parallax e sem inclinação 3D. A separação do fundo passa a ser
   feita só pelo estilo — vidro opaco com sombra projetada — e não por
   movimento. A animação de entrada por scroll continua, porque é o que revela
   a seção; o que sai é o movimento permanente.

   As PÍLULAS mantêm um parallax discreto: são elementos leves e soltos, e ali
   o movimento não distrai a leitura. */
function flutuarConteudo() {
  document.querySelectorAll('.pilula').forEach((el, i) => {
    const forca = 3 + (i % 3) * 2.5;
    gsap.fromTo(el, { yPercent: forca }, {
      yPercent: -forca, ease: 'none',
      scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub: 1 },
    });
  });
  return [];   // nenhum listener a limpar depois
}

/* ------------------------------------------------------------------ */
/* Montagem                                                            */
/* ------------------------------------------------------------------ */
const fundo = criarFundoBolhas(document.getElementById('introCena'));

let timelineHero = null;
if (!MENOS_MOVIMENTO) {
  timelineHero = animarConteudo();
  flutuarConteudo();
  // A câmera atravessa o líquido conforme a página desce.
  if (fundo) {
    gsap.to(fundo.camera.position, {
      y: -3.4, z: 10, ease: 'none',
      scrollTrigger: { trigger: document.body, start: 'top top', end: 'bottom bottom', scrub: 1 },
    });
  }
} else {
  gsap.set('.linha > span, [data-anim], [data-cards] > *, [data-stagger] > *', { clearProps: 'all' });
}

/* Limpeza das animações. O fundo cuida da própria (ele também escuta
   `pagehide`), então aqui não se mexe nos recursos dele. */
addEventListener('pagehide', () => {
  if (timelineHero) timelineHero.kill();
  window.ScrollTrigger.getAll().forEach((s) => s.kill());
  gsap.globalTimeline.clear();
}, { once: true });
