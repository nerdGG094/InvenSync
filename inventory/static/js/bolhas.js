/* Fundo de bolhas de refrigerante — componente reutilizável.

   Usado pela apresentação (/apresentacao) e pela tela de login. Depende só do
   Three.js: nenhuma animação de conteúdo, nenhum GSAP. Quem quiser amarrar a
   câmera ao scroll usa o objeto devolvido por `criarFundoBolhas`.

   A bolha é DESENHADA NO SHADER (anel, especular, contra-luz e iridescência) e
   a subida é calculada na GPU a partir de uma DISTÂNCIA ACUMULADA — usar
   tempo x velocidade faria as bolhas saltarem quando o scroll acelera o gás.

   Uso:
       import { criarFundoBolhas } from './bolhas.js';
       const fundo = criarFundoBolhas(canvas, { densidade: 0.5 });
       // fundo.camera ... fundo.destruir()
*/
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.js';

const MENOS_MOVIMENTO = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const CELULAR = window.innerWidth < 768;

/* Quantidade ajustada pela densidade pedida. O mínimo evita que o efeito
   desapareça de vez numa densidade muito baixa. */
const qtd = (base, densidade) => Math.max(12, Math.round(base * densidade));

/* Direção da luz do ambiente, em coordenadas de TELA (x direita, y para cima).
   Vem da esquerda e um pouco de cima. É a MESMA para as bolhas e para o fundo —
   se as duas discordassem, a cena inteira perderia a leitura de volume. */
const DIR_LUZ = new THREE.Vector2(-0.88, 0.47).normalize();

/* Dimensões do "copo" */
const ALTURA = 22;      // altura do ciclo: a bolha reaparece embaixo ao passar
const BASE = -11;       // onde começa
const LARGURA = 30;
const PROFUNDIDADE = 20;

/* ------------------------------------------------------------------ */
/* 1. Skybox procedural — o ambiente ao redor (nenhum arquivo externo) */
/* ------------------------------------------------------------------ */
function desenharFace(tipo) {
  const N = 256;
  const c = document.createElement('canvas');
  c.width = c.height = N;
  const g = c.getContext('2d');
  const cima = tipo === 'py';
  const baixo = tipo === 'ny';

  const base = g.createLinearGradient(0, 0, 0, N);
  if (cima) { base.addColorStop(0, '#123a22'); base.addColorStop(1, '#08200f'); }
  else if (baixo) { base.addColorStop(0, '#020c07'); base.addColorStop(1, '#010604'); }
  else { base.addColorStop(0, '#0c2917'); base.addColorStop(0.6, '#05140b'); base.addColorStop(1, '#020a06'); }
  g.fillStyle = base;
  g.fillRect(0, 0, N, N);

  const focos = cima
    ? [[0.32, 0.30, 0.46, 'rgba(200,255,225,0.9)'], [0.74, 0.66, 0.32, 'rgba(0,230,118,0.6)']]
    : baixo ? [[0.5, 0.5, 0.55, 'rgba(0,120,55,0.12)']]
      : [[0.20, 0.22, 0.32, 'rgba(160,255,205,0.34)'], [0.82, 0.40, 0.26, 'rgba(0,230,118,0.26)']];
  focos.forEach(([x, y, r, cor]) => {
    const gr = g.createRadialGradient(x * N, y * N, 0, x * N, y * N, r * N);
    gr.addColorStop(0, cor);
    gr.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = gr;
    g.fillRect(0, 0, N, N);
  });
  return c;
}

function criarSkybox() {
  // Ordem exigida pelo Three: +X, -X, +Y, -Y, +Z, -Z
  const cubo = new THREE.CubeTexture(['px', 'nx', 'py', 'ny', 'pz', 'nz'].map(desenharFace));
  cubo.colorSpace = THREE.SRGBColorSpace;
  cubo.needsUpdate = true;
  return cubo;
}

/* ------------------------------------------------------------------ */
/* 2. A bolha, em GLSL                                                 */
/* ------------------------------------------------------------------ */
const VERTEX = /* glsl */`
  uniform float uPercurso;    // distância acumulada (respeita o impulso do scroll)
  uniform float uTempo;
  uniform float uPixelRatio;
  uniform float uImpulso;

  attribute float aTam;       // raio em unidades de mundo
  attribute float aVel;
  attribute float aFase;
  attribute float aAmp;       // amplitude do balanço lateral
  attribute float aGiro;

  varying float vFase;
  varying float vTam;

  void main() {
    vec3 p = position;

    // Sobe em ciclo: ao passar do topo reaparece embaixo, sem "pulo" visível.
    p.y = mod(p.y + uPercurso * aVel, ${ALTURA.toFixed(1)}) + ${BASE.toFixed(1)};

    // Bolha real não sobe reta: serpenteia enquanto sobe.
    p.x += sin(uTempo * aGiro + aFase) * aAmp;
    p.z += cos(uTempo * aGiro * 0.7 + aFase) * aAmp * 0.6;

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;

    // Tamanho em perspectiva + leve inchaço quando o gás acelera.
    float inchaco = 1.0 + (uImpulso - 1.0) * 0.04;
    // Teto de 300px: placas antigas recortam pontos muito grandes, e a bolha
    // apareceria cortada em quadrado ao passar rente à câmera.
    gl_PointSize = min(aTam * inchaco * uPixelRatio * (420.0 / max(0.001, -mv.z)), 300.0);

    vFase = aFase;
    vTam = aTam;
  }
`;

const FRAGMENT = /* glsl */`
  precision highp float;
  uniform float uOpacidade;
  uniform vec2 uLuz;          // direção da luz em coordenadas de TELA (y p/ cima)
  varying float vFase;
  varying float vTam;

  void main() {
    // Coordenada dentro do ponto, de -1 a 1.
    // Atenção: em gl_PointCoord o Y cresce para BAIXO, ao contrário da tela —
    // por isso a direção da luz é invertida em Y antes de ser usada aqui.
    vec2 uv = gl_PointCoord * 2.0 - 1.0;
    float d2 = dot(uv, uv);
    if (d2 > 1.0) discard;                 // fora do círculo
    float r = sqrt(d2);

    vec2 luz = vec2(uLuz.x, -uLuz.y);
    // Normal da esfera falsa: reconstruída a partir da posição no disco.
    vec3 n = vec3(uv, sqrt(max(0.0, 1.0 - d2)));
    vec3 dirLuz = normalize(vec3(luz, 0.55));
    float lambert = max(0.0, dot(n, dirLuz));

    // Suaviza a borda externa (antisserrilhado do próprio círculo)
    float borda = 1.0 - smoothstep(0.94, 1.0, r);

    // ANEL: a película vista de lado é mais densa, então acende perto da borda.
    float anel = smoothstep(0.55, 0.97, r) * borda;
    anel = pow(anel, 1.6);
    // A luz lateral faz o anel acender de um lado e apagar do outro.
    float ladoAceso = 0.35 + 0.85 * lambert;
    anel *= ladoAceso;

    // BRILHO principal: fica sobre o lado iluminado, não num ponto fixo.
    float spec = pow(max(0.0, 1.0 - length(uv - luz * 0.42) * 2.2), 8.0);
    // CONTRA-LUZ: a borda oposta acende fininho, luz atravessando a bolha.
    // É o detalhe que faz esfera transparente parecer transparente.
    float contra = pow(max(0.0, dot(normalize(uv + vec2(0.0001)), -luz)), 3.5)
                 * smoothstep(0.72, 0.99, r) * borda * 0.55;
    // Reflexo rebatido, bem fraco, no lado da sombra.
    float spec2 = pow(max(0.0, 1.0 - length(uv + luz * 0.36) * 3.0), 10.0) * 0.22;

    // IRIDESCÊNCIA: a cor da película muda com o ângulo de visão (aqui, com o
    // raio) e com a espessura (aqui, a fase de cada bolha).
    vec3 iris = 0.5 + 0.5 * cos(6.28318 * (vec3(0.0, 0.33, 0.67) + r * 1.35 + vFase));
    vec3 corAnel = mix(vec3(0.0, 0.86, 0.45), iris, 0.55);

    // Miolo: quase vazio, e mais escuro no lado da sombra.
    float miolo = (1.0 - smoothstep(0.0, 0.85, r)) * 0.055 * (0.45 + 0.8 * lambert);

    vec3 cor = corAnel * anel
             + vec3(1.0) * spec
             + vec3(0.72, 1.0, 0.84) * contra
             + vec3(0.75, 1.0, 0.86) * spec2
             + vec3(0.35, 1.0, 0.6) * miolo;

    float alpha = (anel * 0.85 + spec * 0.95 + contra + spec2 + miolo * 1.4)
                * uOpacidade * borda;
    if (alpha < 0.004) discard;
    gl_FragColor = vec4(cor, alpha);
  }
`;

/* ------------------------------------------------------------------ */
/* 3. População de bolhas                                              */
/* ------------------------------------------------------------------ */
/* Um único objeto Points. Como o movimento é feito no shader, o JS não
   percorre nada por quadro — dá para ter milhares sem custo perceptível. */
function criarBolhas(qtd, { tamMin, tamMax, velMin, velMax, opacidade, fontes = 14 }) {
  const pos = new Float32Array(qtd * 3);
  const tam = new Float32Array(qtd);
  const vel = new Float32Array(qtd);
  const fase = new Float32Array(qtd);
  const amp = new Float32Array(qtd);
  const giro = new Float32Array(qtd);

  // PONTOS DE NUCLEAÇÃO: no copo, o gás não nasce espalhado — brota de alguns
  // pontos da parede e sobe em COLUNA. É a assinatura visual do refrigerante.
  const colunas = Array.from({ length: fontes }, () => ({
    x: (Math.random() - 0.5) * LARGURA,
    z: (Math.random() - 0.5) * PROFUNDIDADE,
  }));

  for (let i = 0; i < qtd; i++) {
    // ~60% saem de uma coluna; o resto fica solto, senão fica artificial demais.
    if (Math.random() < 0.6) {
      const c = colunas[(Math.random() * fontes) | 0];
      pos[i * 3] = c.x + (Math.random() - 0.5) * 1.1;
      pos[i * 3 + 2] = c.z + (Math.random() - 0.5) * 1.1;
    } else {
      pos[i * 3] = (Math.random() - 0.5) * LARGURA;
      pos[i * 3 + 2] = (Math.random() - 0.5) * PROFUNDIDADE;
    }
    pos[i * 3 + 1] = Math.random() * ALTURA;      // espalhadas, não todas embaixo

    // Curva para o quadrado: muitas pequenas, poucas grandes — como no copo.
    const s = Math.pow(Math.random(), 2.2);
    tam[i] = tamMin + s * (tamMax - tamMin);
    // Bolha maior sobe mais rápido (empuxo maior) — detalhe que o olho cobra.
    vel[i] = velMin + (velMax - velMin) * (0.35 + 0.65 * s) * (0.75 + Math.random() * 0.5);
    fase[i] = Math.random() * Math.PI * 2;
    // Balanço curto e nervoso: gás sobe tremendo, não bamboleando devagar.
    amp[i] = 0.05 + Math.random() * 0.22;
    giro[i] = 1.6 + Math.random() * 2.6;
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('aTam', new THREE.BufferAttribute(tam, 1));
  geo.setAttribute('aVel', new THREE.BufferAttribute(vel, 1));
  geo.setAttribute('aFase', new THREE.BufferAttribute(fase, 1));
  geo.setAttribute('aAmp', new THREE.BufferAttribute(amp, 1));
  geo.setAttribute('aGiro', new THREE.BufferAttribute(giro, 1));
  geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 60);   // sem recalcular

  const mat = new THREE.ShaderMaterial({
    vertexShader: VERTEX,
    fragmentShader: FRAGMENT,
    uniforms: {
      uPercurso: { value: 0 },
      uTempo: { value: 0 },
      uPixelRatio: { value: Math.min(devicePixelRatio, 2) },
      uImpulso: { value: 1 },
      uOpacidade: { value: opacidade },
      uLuz: { value: DIR_LUZ },
    },
    transparent: true,
    depthWrite: false,
    blending: THREE.NormalBlending,   // aditivo viraria névoa; aqui é vidro
  });

  return { pontos: new THREE.Points(geo, mat), geo, mat };
}

/* ------------------------------------------------------------------ */
/* 3b. Vidro suado — pós-processamento                                 */
/* ------------------------------------------------------------------ */
/* A cena das bolhas é desenhada numa textura; depois um retângulo do tamanho
   da tela reprocessa essa textura simulando a PAREDE DE VIDRO TRANSPARENTE da
   garrafa. Nada de embaçado, gotas ou água: o vidro é limpo e seco, e o que o
   denuncia são quatro coisas — discretas, mas todas ao mesmo tempo:

     - CURVATURA: perto das laterais a parede é vista de viés e desvia a
       imagem, como olhar através de uma garrafa redonda;
     - ABERRAÇÃO CROMÁTICA: fora do centro o vidro separa levemente as cores;
     - REFLEXOS VERTICAIS: as faixas longas de luz, assinatura de garrafa;
     - ESPESSURA NAS BORDAS: as laterais escurecem, porque ali se atravessa
       mais material.

   Tudo de intensidade baixa — a imagem continua nítida e as bolhas bem
   visíveis; o vidro se percebe, mas não atrapalha. */
const VIDRO_VERTEX = /* glsl */`
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

const VIDRO_FRAGMENT = /* glsl */`
  precision highp float;
  uniform sampler2D tCena;
  uniform vec2 uRes;
  uniform float uVidro;      // intensidade geral do efeito (0 = sem vidro)
  uniform float uAspecto;
  uniform vec2 uLuz;         // mesma direção usada nas bolhas
  varying vec2 vUv;

  void main() {
    vec2 uv = vUv;
    vec2 p = uv - 0.5;                       // centrado: -0.5 a 0.5
    float lateral = clamp(abs(p.x) * 2.0, 0.0, 1.0);   // 0 no meio, 1 nas bordas

    // CURVATURA: perto das laterais a parede é atravessada de viés e empurra a
    // imagem para fora. No centro, onde o olhar é perpendicular, não desvia.
    float curva = pow(lateral, 2.2);
    vec2 desvio = vec2(sign(p.x) * curva * 0.032 * uVidro, 0.0);

    // ABERRAÇÃO CROMÁTICA: fora do centro o vidro separa levemente as cores.
    float sep = curva * 0.0062 * uVidro;
    vec2 base = uv - desvio;
    vec3 cor = vec3(
      texture2D(tCena, base - vec2(sep, 0.0)).r,
      texture2D(tCena, base).g,
      texture2D(tCena, base + vec2(sep, 0.0)).b
    );

    // ILUMINAÇÃO LATERAL: o ambiente é mais claro do lado de onde vem a luz e
    // cai para a sombra do lado oposto. Leve — só o bastante para as bolhas
    // terem de onde "receber" a luz e o fundo deixar de ser chapado.
    vec2 dir = normalize(uLuz);
    float lado = clamp(0.5 + dot(p, dir) * 1.15, 0.0, 1.0);
    cor *= mix(0.80, 1.16, lado);

    // Halo suave junto à borda por onde a luz entra, sugerindo a fonte.
    float halo = exp(-length(p - dir * 0.60) * 3.0) * 0.14 * uVidro;
    cor += halo * vec3(0.75, 1.0, 0.86);

    // REFLEXOS VERTICAIS: duas faixas longas de luz, a assinatura da garrafa.
    // A do lado iluminado é mais forte, coerente com a fonte.
    float faixaA = exp(-pow((uv.x - 0.235) * 18.0, 2.0)) * (dir.x < 0.0 ? 1.0 : 0.55);
    float faixaB = exp(-pow((uv.x - 0.775) * 30.0, 2.0)) * (dir.x > 0.0 ? 1.0 : 0.55);
    float extensao = smoothstep(0.0, 0.18, uv.y) * (1.0 - smoothstep(0.78, 1.0, uv.y));
    cor += (faixaA + faixaB) * extensao * 0.17 * uVidro * vec3(0.80, 1.0, 0.90);

    // ESPESSURA: nas bordas atravessa-se mais material, então escurece.
    cor *= 1.0 - smoothstep(0.45, 1.0, lateral) * 0.32 * uVidro;

    // Vinheta, para fechar a forma do cilindro.
    cor *= 1.0 - dot(p, p) * 0.36 * uVidro;

    gl_FragColor = vec4(cor, 1.0);
  }
`;

/* ------------------------------------------------------------------ */
/* 4. Cena                                                             */
/* ------------------------------------------------------------------ */
function criarCena(canvas, densidade) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setSize(innerWidth, innerHeight);
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;

  const cena = new THREE.Scene();
  cena.background = criarSkybox();
  cena.backgroundIntensity = 0.28;      // escuro: o texto continua legível
  cena.fog = new THREE.FogExp2(0x04120a, 0.028);

  const camera = new THREE.PerspectiveCamera(58, innerWidth / innerHeight, 0.1, 120);
  camera.position.set(0, 0, 13);

  // Três profundidades. As da frente são bem maiores e mais lentas de aparecer,
  // as do fundo são finas e numerosas — é o contraste que cria o volume.
  // Velocidades: a bolha atravessa o campo de visão (~14 unidades) em 3 a 8
  // segundos. É um meio-termo — na primeira versão levava até 44 s (parecia
  // óleo) e depois ficou em 1,5 s, rápido demais para servir de fundo.
  const grupos = [
    criarBolhas(qtd(CELULAR ? 520 : 1300, densidade), { tamMin: 0.02, tamMax: 0.10, velMin: 1.5, velMax: 2.8,
                                        opacidade: 0.5, fontes: 18 }),
    criarBolhas(qtd(CELULAR ? 190 : 430, densidade), { tamMin: 0.09, tamMax: 0.28, velMin: 2.0, velMax: 3.7,
                                       opacidade: 0.75, fontes: 12 }),
    criarBolhas(qtd(CELULAR ? 55 : 120, densidade), { tamMin: 0.26, tamMax: 0.62, velMin: 2.6, velMax: 4.8,
                                      opacidade: 0.9, fontes: 8 }),
  ];
  grupos.forEach((g) => cena.add(g.pontos));

  // --- Alvo de renderização + retângulo do vidro ---
  const pr = Math.min(devicePixelRatio, 2);
  const alvo = new THREE.WebGLRenderTarget(innerWidth * pr, innerHeight * pr, {
    minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter,
    type: THREE.HalfFloatType,          // combina com o tone mapping
  });

  const matVidro = new THREE.ShaderMaterial({
    vertexShader: VIDRO_VERTEX,
    fragmentShader: VIDRO_FRAGMENT,
    uniforms: {
      tCena: { value: alvo.texture },
      uRes: { value: new THREE.Vector2(innerWidth * pr, innerHeight * pr) },
      uVidro: { value: 1 },
      uAspecto: { value: innerWidth / innerHeight },
      uLuz: { value: DIR_LUZ },
    },
    depthTest: false, depthWrite: false,
  });
  const cenaVidro = new THREE.Scene();
  const cameraVidro = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  cenaVidro.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), matVidro));

  return { renderer, cena, camera, grupos, alvo, matVidro, cenaVidro, cameraVidro };
}

/* ------------------------------------------------------------------ */
/* 5. Ponto de entrada                                                 */
/* ------------------------------------------------------------------ */
/* Cria a cena e cuida do laço de render, do redimensionamento, da pausa com a
   aba oculta e da limpeza. Devolve o que a página pode querer complementar
   (a câmera, para amarrar ao scroll) e o `destruir`. */
export function criarFundoBolhas(canvas, opcoes) {
  if (!canvas) return null;                       // página sem canvas: não faz nada
  const densidade = (opcoes && opcoes.densidade) || 1;

  const { renderer, cena, camera, grupos, alvo, matVidro, cenaVidro, cameraVidro } =
    criarCena(canvas, densidade);

  const mouse = { x: 0, y: 0, alvoX: 0, alvoY: 0 };
  const relogio = new THREE.Clock();
  let rodando = true;
  let quadro = 0;
  let percurso = 0;          // distância que o gás já subiu (acumulada)

  /* --- Impulso do scroll --- */
  const IMPULSO_MAX = 9;
  const REFERENCIA = 550;    // px/s de scroll que já valem ~1x extra
  const SOBE_RAPIDO = 14;
  const VOLTA_DEVAGAR = 2.2;
  const efeito = { empurrao: 1 };
  let ultimoScroll = window.scrollY;

  function atualizarImpulso(dt) {
    // Velocidade medida no próprio quadro: vale para roda, barra, teclado,
    // toque e scroll suave, e volta sozinha a zero quando a página para.
    // Numa tela sem rolagem, como o login, fica sempre em 1x.
    const y = window.scrollY;
    const vel = (y - ultimoScroll) / Math.max(dt, 0.001);
    ultimoScroll = y;
    const alvoImp = vel >= 0
      ? 1 + Math.min(vel / REFERENCIA, IMPULSO_MAX - 1)
      : Math.max(0.25, 1 - Math.min(-vel / REFERENCIA, 1) * 0.75);
    const ganho = alvoImp > efeito.empurrao ? SOBE_RAPIDO : VOLTA_DEVAGAR;
    efeito.empurrao += (alvoImp - efeito.empurrao) * Math.min(1, dt * ganho);
  }

  function aoMover(e) {
    mouse.alvoX = (e.clientX / innerWidth - 0.5) * 2;
    mouse.alvoY = (e.clientY / innerHeight - 0.5) * 2;
  }
  function aoRedimensionar() {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
    const pr = Math.min(devicePixelRatio, 2);
    renderer.setPixelRatio(pr);
    grupos.forEach((g) => { g.mat.uniforms.uPixelRatio.value = pr; });
    // O alvo do pós-processamento acompanha a tela, senão o vidro estica e a
    // curvatura das laterais sai do lugar.
    alvo.setSize(innerWidth * pr, innerHeight * pr);
    matVidro.uniforms.uRes.value.set(innerWidth * pr, innerHeight * pr);
    matVidro.uniforms.uAspecto.value = innerWidth / innerHeight;
  }
  function aoTrocarAba() {
    rodando = !document.hidden;
    if (rodando) { relogio.getDelta(); laco(); }
  }

  addEventListener('pointermove', aoMover, { passive: true });
  addEventListener('resize', aoRedimensionar);
  document.addEventListener('visibilitychange', aoTrocarAba);

  function laco() {
    if (!rodando) return;
    quadro = requestAnimationFrame(laco);

    const dt = Math.min(relogio.getDelta(), 0.05);
    const t = relogio.elapsedTime;

    // Parallax: girar a câmera desliza o skybox atrás das bolhas.
    mouse.x += (mouse.alvoX - mouse.x) * 0.05;
    mouse.y += (mouse.alvoY - mouse.y) * 0.05;
    camera.rotation.y = -mouse.x * 0.10;
    camera.rotation.x = mouse.y * 0.06;

    if (!MENOS_MOVIMENTO) atualizarImpulso(dt);
    const empurrao = MENOS_MOVIMENTO ? 0.25 : efeito.empurrao;

    // Acumula a distância em vez de multiplicar o tempo pelo impulso: assim a
    // mudança de velocidade não faz as bolhas saltarem de posição.
    percurso += dt * empurrao;

    for (let i = 0; i < grupos.length; i++) {
      const u = grupos[i].mat.uniforms;
      u.uPercurso.value = percurso;
      u.uTempo.value = t;
      u.uImpulso.value = empurrao;
    }

    // 1) bolhas e skybox vão para a textura; 2) o vidro reprocessa e vai à tela.
    renderer.setRenderTarget(alvo);
    renderer.render(cena, camera);
    renderer.setRenderTarget(null);
    renderer.render(cenaVidro, cameraVidro);
  }
  laco();

  /* Limpeza: sem isso a GPU segura buffers e os listeners vazam. */
  function destruir() {
    rodando = false;
    cancelAnimationFrame(quadro);
    removeEventListener('pointermove', aoMover);
    removeEventListener('resize', aoRedimensionar);
    document.removeEventListener('visibilitychange', aoTrocarAba);
    if (cena.background && cena.background.dispose) cena.background.dispose();
    alvo.dispose();
    cenaVidro.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) o.material.dispose();
    });
    cena.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose());
    });
    renderer.dispose();
  }
  addEventListener('pagehide', destruir, { once: true });

  return { renderer, cena, camera, grupos, matVidro, destruir };
}
