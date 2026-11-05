// Copiar e compartilhar o link da página do vendedor (CA5). Opcional: sem
// JavaScript, o endereço fica num campo somente leitura, fácil de selecionar.
// Os textos vêm dos atributos data-texto-* do bloco .copiar-link (no template).
(function () {
  "use strict";

  function copyWithSelection(input) {
    input.focus();
    input.select();
    try {
      return document.execCommand("copy");
    } catch (error) {
      return false;
    }
  }

  function makeButton(label) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "botao botao--secundario";
    button.textContent = label;
    return button;
  }

  function enhance(box) {
    var input = box.querySelector("input[readonly]");
    var status = box.querySelector("[data-copiar-status]");
    if (!input) return;

    input.addEventListener("focus", function () {
      input.select();
    });

    var actions = document.createElement("div");
    actions.className = "linha-acoes";

    var copy = makeButton(box.dataset.textoCopiar || "Copiar link");
    copy.addEventListener("click", function () {
      var done = function () {
        if (status) status.textContent = box.dataset.textoCopiado || "";
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(input.value).then(done, function () {
          if (copyWithSelection(input)) done();
        });
      } else if (copyWithSelection(input)) {
        done();
      }
    });
    actions.appendChild(copy);

    if (typeof navigator.share === "function") {
      var share = makeButton(box.dataset.textoCompartilhar || "Compartilhar");
      share.addEventListener("click", function () {
        navigator.share({ title: document.title, url: input.value }).catch(function () {
          // Cancelado pela pessoa: nada a fazer.
        });
      });
      actions.appendChild(share);
    }

    input.insertAdjacentElement("afterend", actions);
  }

  function init() {
    document.querySelectorAll("[data-copiar-link]").forEach(enhance);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
