/* Tabela equivalente de um gráfico Chart.js — o caminho sem cor para os dados.

   Por que existe: nenhum valor pode ser legível só pela cor ou só pelo tooltip.
   Três cores da paleta do sistema ficam abaixo de 3:1 contra o cartão branco do
   tema claro, o que obriga uma alternativa visível; e um tooltip não serve para
   quem navega por teclado ou lê a tela em voz alta.

   A tabela é montada a partir do próprio `chart.data`, então nunca diverge do
   gráfico nem precisa que a rota mande os dados duas vezes.

   Script clássico de propósito (não módulo): os painéis usam <script> inline
   com nonce e não podem fazer `import`. Expõe `window.tabelaDoGrafico`. */
(function () {
  'use strict';

  var seq = 0;

  /**
   * @param {Chart}  chart   instância do Chart.js
   * @param {Object} opts
   *   opts.cartao  seletor do contêiner que recebe a tabela (sobe do canvas)
   *   opts.cabeca  seletor, dentro do cartão, onde entra o botão "Dados"
   */
  window.tabelaDoGrafico = function (chart, opts) {
    opts = opts || {};
    var cartao = chart.canvas.closest(opts.cartao || '.card');
    if (!cartao) return;
    var cabeca = cartao.querySelector(opts.cabeca || 'h6');
    if (!cabeca) return;

    var d = chart.data || {};
    var series = d.datasets || [];
    var rotulos = d.labels || [];
    if (!rotulos.length || !series.length) return;

    var esc = function (v) {
      return String(v == null ? '' : v)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    };

    var cx = document.createElement('div');
    cx.className = 'ch-table';
    cx.hidden = true;
    cx.id = 'chTab' + (seq++);
    cx.innerHTML =
      '<table><thead><tr><th></th>' +
      series.map(function (s) { return '<th>' + esc(s.label || 'Valor') + '</th>'; }).join('') +
      '</tr></thead><tbody>' +
      rotulos.map(function (l, j) {
        return '<tr><th scope="row">' + esc(l) + '</th>' +
          series.map(function (s) {
            return '<td class="num">' + esc((s.data || [])[j]) + '</td>';
          }).join('') + '</tr>';
      }).join('') +
      '</tbody></table>';
    cartao.appendChild(cx);

    /* O título do cartão é um nó de texto solto ao lado do ícone. Sem embrulhar,
       ele vira um item de flex sem `min-width` controlável e o botão o espreme
       até quebrar linha. Embrulhado, o texto é quem absorve a sobra. */
    var txt = document.createElement('span');
    txt.className = 'ch-head-txt';
    while (cabeca.firstChild) txt.appendChild(cabeca.firstChild);
    cabeca.appendChild(txt);

    var bt = document.createElement('button');
    bt.type = 'button';
    bt.className = 'ch-tab-btn';
    bt.setAttribute('aria-expanded', 'false');
    bt.setAttribute('aria-controls', cx.id);
    // Só o ícone: com o rótulo "Dados" o botão comia ~70px do cabeçalho e os
    // títulos mais longos quebravam. O nome vive no title/aria-label.
    bt.title = 'Ver os dados em tabela';
    bt.setAttribute('aria-label', 'Ver os dados em tabela');
    bt.innerHTML = '<i class="bi bi-table"></i>';
    bt.addEventListener('click', function () {
      var abrir = cx.hidden;
      cx.hidden = !abrir;
      bt.setAttribute('aria-expanded', String(abrir));
    });
    // O cabeçalho pode ser um <h6> comum (painel de Chamados); sem flex o
    // `margin-left:auto` do botão não empurra nada e ele cola no título.
    cabeca.style.display = 'flex';
    cabeca.style.alignItems = 'center';
    cabeca.appendChild(bt);
  };
})();
