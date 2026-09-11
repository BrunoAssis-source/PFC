(function () {
    var seletor = document.querySelector(".seletor");
    if (!seletor) {
        return;
    }

    var busca = document.getElementById("busca-variavel");
    var resultados = document.getElementById("resultados-variaveis");
    var destino = "";
    var ativo = -1;
    var espera = null;
    var ultimoEndereco = "";

    function itens() {
        return Array.prototype.slice.call(resultados.querySelectorAll(".seletor-item:not(.indisponivel)"));
    }

    function destacar(indice) {
        var lista = itens();
        lista.forEach(function (item) {
            item.classList.remove("ativo");
            item.setAttribute("aria-selected", "false");
        });
        if (indice < 0 || indice >= lista.length) {
            ativo = -1;
            busca.removeAttribute("aria-activedescendant");
            return;
        }
        ativo = indice;
        var item = lista[indice];
        item.classList.add("ativo");
        item.setAttribute("aria-selected", "true");
        busca.setAttribute("aria-activedescendant", item.id);
        item.scrollIntoView({ block: "nearest" });
    }

    function abrir(item) {
        if (!item) {
            return;
        }
        if (item.dataset.url) {
            window.location.href = item.dataset.url;
        } else if (item.dataset.destino !== undefined) {
            destino = item.dataset.destino;
            carregar();
        }
    }

    function carregar() {
        var endereco = seletor.dataset.url + "?q=" + encodeURIComponent(busca.value);
        if (destino) {
            endereco += "&" + destino;
        }
        ultimoEndereco = endereco;
        fetch(endereco)
            .then(function (resposta) { return resposta.text(); })
            .then(function (html) {
                // Resposta de uma busca anterior que chegou atrasada.
                if (endereco !== ultimoEndereco) {
                    return;
                }
                resultados.innerHTML = html;
                destacar(-1);
            });
    }

    busca.addEventListener("input", function () {
        clearTimeout(espera);
        espera = setTimeout(carregar, 200);
    });

    busca.addEventListener("keydown", function (evento) {
        var lista = itens();
        if (evento.key === "ArrowDown") {
            evento.preventDefault();
            destacar(ativo + 1 >= lista.length ? 0 : ativo + 1);
        } else if (evento.key === "ArrowUp") {
            evento.preventDefault();
            destacar(ativo - 1 < 0 ? lista.length - 1 : ativo - 1);
        } else if (evento.key === "Enter") {
            evento.preventDefault();
            abrir(ativo >= 0 ? lista[ativo] : lista[0]);
        } else if (evento.key === "Escape") {
            evento.preventDefault();
            busca.value = "";
            carregar();
        } else if (evento.key === "Backspace" && busca.value === "" && destino) {
            evento.preventDefault();
            destino = "";
            carregar();
        }
    });

    resultados.addEventListener("click", function (evento) {
        var chip = evento.target.closest(".chip");
        if (chip) {
            destino = chip.dataset.sub ? "sub=" + chip.dataset.sub : "";
            carregar();
            busca.focus();
            return;
        }

        var migalha = evento.target.closest(".migalha");
        if (migalha && migalha.dataset.destino !== undefined) {
            destino = migalha.dataset.destino;
            carregar();
            busca.focus();
            return;
        }

        abrir(evento.target.closest(".seletor-item"));
    });

    busca.addEventListener("search", function () {
        if (busca.value === "") {
            carregar();
        }
    });
})();
