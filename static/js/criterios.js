(function () {
    var tela = document.querySelector(".criterios");
    if (!tela) {
        return;
    }

    var busca = document.getElementById("busca-variavel");
    var arvore = document.getElementById("arvore");
    var resultados = document.getElementById("resultados-busca");
    var configuracao = document.getElementById("configuracao");
    var regras = document.getElementById("regras");
    var textoInicial = configuracao.innerHTML;
    var esperaBusca = null;
    var esperaPrevia = null;
    var ultimaBusca = "";
    var ultimaPrevia = "";

    function pegar(endereco) {
        return fetch(endereco).then(function (resposta) {
            return resposta.text();
        });
    }

    function buscar() {
        var termo = busca.value.trim();
        if (!termo) {
            resultados.hidden = true;
            arvore.hidden = false;
            return;
        }
        var endereco = tela.dataset.buscaUrl + "?q=" + encodeURIComponent(termo);
        ultimaBusca = endereco;
        pegar(endereco).then(function (html) {
            // Resposta de uma busca anterior que chegou atrasada.
            if (endereco !== ultimaBusca) {
                return;
            }
            resultados.innerHTML = html;
            resultados.hidden = false;
            arvore.hidden = true;
        });
    }

    busca.addEventListener("input", function () {
        clearTimeout(esperaBusca);
        esperaBusca = setTimeout(buscar, 200);
    });

    function marcarAtiva(botao) {
        tela.querySelectorAll(".variavel-botao[aria-current]").forEach(function (outro) {
            outro.removeAttribute("aria-current");
        });
        if (botao) {
            botao.setAttribute("aria-current", "true");
        }
    }

    function abrirConfiguracao(endereco, botao) {
        marcarAtiva(botao);
        pegar(endereco).then(function (html) {
            configuracao.innerHTML = html;
            var form = document.getElementById("form-criterio");
            if (form) {
                iniciarFormulario(form);
            }
        });
    }

    tela.addEventListener("click", function (evento) {
        var botao = evento.target.closest(".variavel-botao");
        if (botao && botao.dataset.url) {
            abrirConfiguracao(botao.dataset.url, botao);
        }
    });

    function dadosDoFormulario(form) {
        var dados = new FormData(form);
        dados.delete("csrfmiddlewaretoken");
        return new URLSearchParams(dados).toString();
    }

    function ajustarValores(form) {
        var escolhido = form.querySelector('input[name="operador"]:checked');
        var entre = !!escolhido && escolhido.value === "entre";
        form.querySelectorAll("[data-so-entre]").forEach(function (bloco) {
            bloco.hidden = !entre;
            bloco.querySelector("input").disabled = !entre;
        });
        var rotulo = form.querySelector("[data-rotulo-valor]");
        if (rotulo) {
            rotulo.textContent = entre ? "De" : "Valor";
        }
    }

    function atualizarPrevia(form) {
        var endereco = form.dataset.previaUrl + "?" + dadosDoFormulario(form);
        ultimaPrevia = endereco;
        pegar(endereco).then(function (html) {
            if (endereco !== ultimaPrevia) {
                return;
            }
            var previa = document.getElementById("previa");
            previa.innerHTML = html;
            var completo = previa.querySelector("[data-completo]").dataset.completo === "1";
            form.querySelector(".config-adicionar").disabled = !completo;
        });
    }

    function agendarPrevia(form) {
        clearTimeout(esperaPrevia);
        esperaPrevia = setTimeout(function () {
            atualizarPrevia(form);
        }, 150);
    }

    function iniciarFormulario(form) {
        ajustarValores(form);
        atualizarPrevia(form);

        form.addEventListener("input", function () {
            ajustarValores(form);
            agendarPrevia(form);
        });

        form.addEventListener("click", function (evento) {
            var botao = evento.target.closest("[data-marcar]");
            if (!botao) {
                return;
            }
            var marcar = botao.dataset.marcar === "todas";
            form.querySelectorAll('input[name="opcoes"]').forEach(function (caixa) {
                caixa.checked = marcar;
            });
            agendarPrevia(form);
        });

        form.addEventListener("submit", function (evento) {
            evento.preventDefault();
            fetch(form.action, { method: "POST", body: new FormData(form) }).then(function (resposta) {
                return resposta.text().then(function (html) {
                    if (resposta.ok) {
                        regras.innerHTML = html;
                        configuracao.innerHTML = textoInicial;
                        marcarAtiva(null);
                    } else {
                        document.getElementById("previa").innerHTML = html;
                    }
                });
            });
        });
    }

    regras.addEventListener("submit", function (evento) {
        var form = evento.target.closest(".remover-criterio");
        if (!form) {
            return;
        }
        evento.preventDefault();
        fetch(form.action, { method: "POST", body: new FormData(form) })
            .then(function (resposta) {
                return resposta.text();
            })
            .then(function (html) {
                regras.innerHTML = html;
                regras.focus();
            });
    });

    if (tela.dataset.configuracaoInicial) {
        abrirConfiguracao(tela.dataset.configuracaoInicial, null);
    }
})();
