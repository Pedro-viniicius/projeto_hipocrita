// Melhorias opcionais dos formulários de conta. Sem JavaScript, tudo funciona igual.
// - Foco no <main> quando a página abre com um aviso (leitores de tela leem a mensagem).
// - Botão "Mostrar senha" (aria-pressed) nos campos com data-mostrar-senha.
// - Texto "Salvando…" no botão de envio e bloqueio de envio duplo.
// Os textos vêm dos atributos data-texto-* do <form> (definidos no template).
(function () {
  "use strict";

  function focusMainWithNotice() {
    var main = document.getElementById("conteudo");
    if (main && main.querySelector(".aviso")) {
      if (!main.hasAttribute("tabindex")) main.setAttribute("tabindex", "-1");
      main.focus();
    }
  }

  function addPasswordToggles(form) {
    var show = form.dataset.textoMostrar;
    var hide = form.dataset.textoOcultar;
    if (!show || !hide) return;
    form.querySelectorAll("input[data-mostrar-senha]").forEach(function (input) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "botao botao--link mostrar-senha";
      button.textContent = show;
      button.setAttribute("aria-pressed", "false");
      if (input.id) button.setAttribute("aria-controls", input.id);
      button.addEventListener("click", function () {
        var visible = input.type === "text";
        input.type = visible ? "password" : "text";
        button.textContent = visible ? show : hide;
        button.setAttribute("aria-pressed", visible ? "false" : "true");
      });
      input.insertAdjacentElement("afterend", button);
    });
    // Volta para "password" antes de enviar, para o navegador não guardar em texto.
    form.addEventListener("submit", function () {
      form.querySelectorAll("input[data-mostrar-senha]").forEach(function (input) {
        input.type = "password";
      });
    });
  }

  function addSavingState(form) {
    var saving = form.dataset.textoSalvando;
    if (!saving) return;
    var button = form.querySelector("button[type=submit]");
    var original = button ? button.textContent : "";
    // Ao voltar pelo histórico (cache do navegador), o botão volta ao normal.
    window.addEventListener("pageshow", function () {
      form.dataset.enviando = "";
      if (button) {
        button.textContent = original;
        button.removeAttribute("aria-disabled");
      }
    });
    form.addEventListener("submit", function (event) {
      if (form.dataset.enviando === "1") {
        event.preventDefault();
        return;
      }
      form.dataset.enviando = "1";
      if (button) {
        button.textContent = saving;
        button.setAttribute("aria-disabled", "true");
      }
    });
  }

  function init() {
    focusMainWithNotice();
    document.querySelectorAll("form[data-texto-mostrar], form[data-texto-salvando]").forEach(
      function (form) {
        addPasswordToggles(form);
        addSavingState(form);
      }
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
