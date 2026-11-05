// Reduz as fotos no navegador antes do envio (melhoria opcional).
// A hospedagem recusa requisições grandes; uma foto de celular passa fácil de 4 MB.
// - No `change` de input[type=file][data-max-mb][data-max-photos], cada imagem vira JPEG
//   com o lado maior de até 1280 px (qualidade 0,85), uma de cada vez (celular modesto não
//   aguenta várias fotos grandes decodificadas juntas). A foto é endireitada pela orientação
//   do EXIF antes de redesenhar; redesenhar no canvas descarta o EXIF (GPS, por exemplo).
// - Enquanto processa, o botão de envio fica aria-disabled e o formulário não envia.
// - Se uma foto não puder ser lida (ex.: HEIC fora do Safari), segue o arquivo original e o
//   servidor decide.
// - Se o total passar de data-max-photos × data-max-mb + 1 MiB (o teto do corpo da
//   requisição no servidor), aparece o aviso e o envio fica bloqueado.
// Os textos (aviso e "preparando") ficam no template: elementos [data-fotos-aviso] e
// [data-fotos-status], escondidos por padrão. Sem JavaScript, o servidor valida tudo igual.
(function () {
  "use strict";

  var MAX_SIDE = 1280;
  var QUALITY = 0.85;
  var MIB = 1024 * 1024;
  var ACCEPTED = /^image\/(jpeg|png|webp)$/;

  function supported() {
    return (
      typeof createImageBitmap === "function" &&
      typeof DataTransfer === "function" &&
      typeof File === "function" &&
      !!document.createElement("canvas").toBlob
    );
  }

  function jpegName(name) {
    var base = String(name || "foto").replace(/\.[^.\/\\]*$/, "");
    return (base || "foto") + ".jpg";
  }

  // Decodifica já endireitada pelo EXIF. Navegador que não conhece a opção recusa: tenta
  // de novo sem ela.
  function decode(file) {
    try {
      return createImageBitmap(file, { imageOrientation: "from-image" }).catch(function () {
        return createImageBitmap(file);
      });
    } catch (e) {
      return createImageBitmap(file);
    }
  }

  // Devolve uma Promise com o arquivo reduzido ou, se algo falhar, com o original.
  function shrink(file) {
    if (!ACCEPTED.test(file.type)) return Promise.resolve(file);
    // Promise.resolve().then: mesmo um erro síncrono vira rejeição e cai no catch abaixo.
    return Promise.resolve(file)
      .then(decode)
      .then(function (bitmap) {
        var scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
        var width = Math.max(1, Math.round(bitmap.width * scale));
        var height = Math.max(1, Math.round(bitmap.height * scale));
        var canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        var ctx = canvas.getContext("2d");
        // JPEG não tem transparência: fundo branco em vez de preto.
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, width, height);
        ctx.drawImage(bitmap, 0, 0, width, height);
        if (bitmap.close) bitmap.close();
        return new Promise(function (resolve) {
          canvas.toBlob(
            function (blob) {
              // Não deixa a foto maior do que era (ex.: WebP já pequeno).
              if (!blob || (scale === 1 && blob.size >= file.size)) return resolve(file);
              resolve(new File([blob], jpegName(file.name), { type: "image/jpeg" }));
            },
            "image/jpeg",
            QUALITY
          );
        });
      })
      .catch(function () {
        return file;
      });
  }

  function setup(form) {
    var inputs = Array.prototype.slice.call(form.querySelectorAll("input[type=file][data-max-mb]"));
    if (!inputs.length || !supported()) return;
    var button = form.querySelector("button[type=submit]");
    var warning = form.querySelector("[data-fotos-aviso]");
    var status = form.querySelector("[data-fotos-status]");
    // Estado por input: processando? total acima do limite?
    var states = inputs.map(function () {
      return { run: 0, busy: false, tooBig: false };
    });

    function any(key) {
      return states.some(function (state) {
        return state[key];
      });
    }

    function refresh() {
      var busy = any("busy");
      var tooBig = any("tooBig");
      if (button) {
        if (busy || tooBig) button.setAttribute("aria-disabled", "true");
        else button.removeAttribute("aria-disabled");
      }
      if (status) status.hidden = !busy;
      if (warning) warning.hidden = !tooBig;
    }

    // Na fase de captura do document, antes dos outros ouvintes do formulário (o enhance.js
    // trocaria o botão para "Enviando…" mesmo com o envio bloqueado).
    document.addEventListener(
      "submit",
      function (event) {
        if (event.target !== form || !(any("busy") || any("tooBig"))) return;
        event.preventDefault();
        event.stopPropagation();
        if (warning && !warning.hidden) warning.focus();
      },
      true
    );

    inputs.forEach(function (input, index) {
      var state = states[index];
      var maxMb = parseFloat(input.getAttribute("data-max-mb"));
      var maxPhotos = parseInt(input.getAttribute("data-max-photos"), 10);
      if (!(maxMb > 0) || !(maxPhotos > 0)) return;

      input.addEventListener("change", function () {
        var files = Array.prototype.slice.call(input.files || []);
        var mine = ++state.run;
        state.tooBig = false;
        state.busy = files.length > 0;
        refresh();
        if (!files.length) return;
        var result = [];
        // Uma foto de cada vez; para no meio se escolherem outras fotos.
        var chain = files.reduce(function (previous, file) {
          return previous.then(function () {
            if (mine !== state.run) return;
            return shrink(file).then(function (smaller) {
              result.push(smaller);
            });
          });
        }, Promise.resolve());
        chain.then(function () {
          if (mine !== state.run) return; // escolheu outras fotos no meio do caminho
          try {
            var transfer = new DataTransfer();
            result.forEach(function (file) {
              transfer.items.add(file);
            });
            input.files = transfer.files;
          } catch (e) {
            result = files; // não deu para trocar: o navegador envia os originais
          }
          var total = result.reduce(function (sum, file) {
            return sum + file.size;
          }, 0);
          state.tooBig = total > (maxPhotos * maxMb + 1) * MIB;
          state.busy = false;
          refresh();
        });
      });
    });

    // Voltar pelo histórico com a página guardada inteira (bfcache): o processamento que
    // estava no meio não vale mais. Refaz a conta com as fotos que estão no campo, para o
    // botão não ficar travado nem liberar um envio grande demais.
    window.addEventListener("pageshow", function (event) {
      if (!event.persisted) return;
      inputs.forEach(function (input, index) {
        var state = states[index];
        state.run += 1;
        state.busy = false;
        state.tooBig = false;
        if (input.files && input.files.length) {
          input.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
      refresh();
    });
  }

  function init() {
    document.querySelectorAll("form").forEach(setup);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
