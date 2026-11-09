// Estado primeiro, municípios depois. Os escolhidos ficam como etiquetas com um campo oculto cada, para a seleção
// sobreviver à troca de estado. Serve à tela de critérios (vários municípios) e à coleta (um só).
window.iniciarCascata = function (bloco, opcoes) {
    var pegar = opcoes.pegar;
    var aoMudar = opcoes.aoMudar || function () {};
    var unico = !!opcoes.unico;
    var nomeDoCampo = opcoes.campo || "opcoes";

    var pai = bloco.querySelector("#cascata-pai");
    var filtro = bloco.querySelector("#cascata-filtro");
    var lista = bloco.querySelector("#cascata-lista");
    var escolhidos = bloco.querySelector("#cascata-escolhidos");
    var vazio = bloco.querySelector("#cascata-vazio");

    function semAcento(texto) {
        return texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    }

    function sincronizar() {
        lista.querySelectorAll("input").forEach(function (caixa) {
            caixa.checked = !!escolhidos.querySelector('input[value="' + caixa.value + '"]');
        });
        vazio.hidden = !!escolhidos.querySelector(".etiqueta");
    }

    function limparEscolhidos() {
        escolhidos.querySelectorAll(".etiqueta").forEach(function (etiqueta) {
            etiqueta.remove();
        });
    }

    function adicionar(caixa) {
        if (escolhidos.querySelector('input[value="' + caixa.value + '"]')) {
            return;
        }
        if (unico) {
            limparEscolhidos();
        }
        var etiqueta = document.createElement("span");
        etiqueta.className = "etiqueta";
        var campo = document.createElement("input");
        campo.type = "hidden";
        campo.name = nomeDoCampo;
        campo.value = caixa.value;
        var rotulo = document.createElement("span");
        rotulo.textContent = caixa.parentNode.textContent.trim();
        var remover = document.createElement("button");
        remover.type = "button";
        remover.setAttribute("aria-label", "Remover " + rotulo.textContent);
        remover.textContent = "×";
        etiqueta.append(campo, rotulo, remover);
        escolhidos.appendChild(etiqueta);
    }

    pai.addEventListener("change", function () {
        filtro.value = "";
        filtro.disabled = !pai.value;
        if (!pai.value) {
            lista.innerHTML = "";
            return;
        }
        pegar(bloco.dataset.opcoesUrl + "?pai=" + pai.value).then(function (html) {
            lista.innerHTML = html;
            sincronizar();
        });
    });

    filtro.addEventListener("input", function () {
        var termo = semAcento(filtro.value.trim());
        lista.querySelectorAll(".escolha").forEach(function (item) {
            item.hidden = semAcento(item.textContent).indexOf(termo) < 0;
        });
    });

    lista.addEventListener("change", function (evento) {
        var caixa = evento.target;
        if (caixa.checked) {
            adicionar(caixa);
        } else {
            var campo = escolhidos.querySelector('input[value="' + caixa.value + '"]');
            if (campo) {
                campo.parentNode.remove();
            }
        }
        sincronizar();
        aoMudar();
    });

    escolhidos.addEventListener("click", function (evento) {
        var etiqueta = evento.target.closest(".etiqueta");
        if (etiqueta && evento.target.closest("button")) {
            etiqueta.remove();
            sincronizar();
            aoMudar();
        }
    });

    bloco.querySelector("[data-limpar-cascata]").addEventListener("click", function () {
        limparEscolhidos();
        sincronizar();
        aoMudar();
    });
};
