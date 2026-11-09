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
    var aberta = { url: null, botao: null };
    var esperaBusca = null;
    var esperaPrevia = null;
    var ultimaBusca = "";
    var ultimaPrevia = "";

    // Sessão vencida ou token antigo: a resposta seria a tela de login ou a
    // página de erro, que não pode entrar no meio da tela. Recarregar resolve.
    function recarregarSeFalhou(resposta) {
        if (resposta.redirected || (!resposta.ok && resposta.status !== 422)) {
            window.location.reload();
            return true;
        }
        return false;
    }

    function pegar(endereco) {
        return fetch(endereco).then(function (resposta) {
            return recarregarSeFalhou(resposta) ? "" : resposta.text();
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
        aberta = { url: endereco, botao: botao };
        marcarAtiva(botao);
        pegar(endereco).then(function (html) {
            configuracao.innerHTML = html;
            var form = document.getElementById("form-criterio");
            if (form) {
                iniciarFormulario(form);
            }
        });
    }

    function botaoDaArvore(endereco) {
        return arvore.querySelector('.variavel-botao[data-url="' + endereco + '"]');
    }

    // Escolher pela busca leva de volta à árvore, com só o grupo da variável aberto.
    function revelarNaArvore(botao) {
        busca.value = "";
        resultados.hidden = true;
        arvore.hidden = false;
        arvore.querySelectorAll("details").forEach(function (grupo) {
            grupo.open = false;
        });
        botao.closest("details").open = true;
        if (botao.scrollIntoView) {
            botao.scrollIntoView({ block: "nearest" });
        }
    }

    tela.addEventListener("click", function (evento) {
        var botao = evento.target.closest(".variavel-botao");
        if (!botao || !botao.dataset.url) {
            return;
        }
        if (resultados.contains(botao)) {
            botao = botaoDaArvore(botao.dataset.url);
            revelarNaArvore(botao);
        }
        abrirConfiguracao(botao.dataset.url, botao);
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

    function semAcento(texto) {
        return texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    }

    // Estado primeiro, municípios depois. Os escolhidos ficam como etiquetas com
    // um campo oculto cada, para a seleção sobreviver à troca de estado.
    function iniciarCascata(form) {
        var bloco = form.querySelector("[data-cascata]");
        if (!bloco) {
            return;
        }
        var pai = bloco.querySelector("#cascata-pai");
        var filtro = bloco.querySelector("#cascata-filtro");
        var lista = bloco.querySelector("#cascata-lista");
        var escolhidos = bloco.querySelector("#cascata-escolhidos");
        var vazio = escolhidos.innerHTML;

        function sincronizar() {
            lista.querySelectorAll('input[type="checkbox"]').forEach(function (caixa) {
                caixa.checked = !!escolhidos.querySelector('input[value="' + caixa.value + '"]');
            });
            if (!escolhidos.children.length) {
                escolhidos.innerHTML = vazio;
            }
        }

        function adicionar(caixa) {
            if (escolhidos.querySelector('input[value="' + caixa.value + '"]')) {
                return;
            }
            if (!escolhidos.querySelector(".etiqueta")) {
                escolhidos.innerHTML = "";
            }
            var etiqueta = document.createElement("span");
            etiqueta.className = "etiqueta";
            var campo = document.createElement("input");
            campo.type = "hidden";
            campo.name = "opcoes";
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
            agendarPrevia(form);
        });

        escolhidos.addEventListener("click", function (evento) {
            var etiqueta = evento.target.closest(".etiqueta");
            if (etiqueta && evento.target.closest("button")) {
                etiqueta.remove();
                sincronizar();
                agendarPrevia(form);
            }
        });

        bloco.querySelector("[data-limpar-cascata]").addEventListener("click", function () {
            escolhidos.innerHTML = vazio;
            sincronizar();
            agendarPrevia(form);
        });
    }

    function iniciarFormulario(form) {
        iniciarCascata(form);
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
                if (recarregarSeFalhou(resposta)) {
                    return;
                }
                return resposta.text().then(function (html) {
                    if (resposta.ok) {
                        regras.innerHTML = html;
                        // Recarrega a mesma variável com o formulário limpo, para
                        // adicionar outro critério sobre ela sem escolhê-la de novo.
                        abrirConfiguracao(aberta.url, aberta.botao);
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
                return recarregarSeFalhou(resposta) ? "" : resposta.text();
            })
            .then(function (html) {
                if (html) {
                    regras.innerHTML = html;
                    regras.focus();
                }
            });
    });

    if (tela.dataset.configuracaoInicial) {
        abrirConfiguracao(tela.dataset.configuracaoInicial, botaoDaArvore(tela.dataset.configuracaoInicial));
    }
})();
