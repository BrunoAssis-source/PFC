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
    var aberta = { url: null, botao: null };
    var esperaBusca = null;
    var esperaPrevia = null;
    var ultimaBusca = "";
    var pedidoDaPrevia = 0;

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
            marcarUsadas();
            resultados.hidden = false;
            arvore.hidden = true;
        });
    }

    busca.addEventListener("input", function () {
        clearTimeout(esperaBusca);
        esperaBusca = setTimeout(buscar, 200);
    });

    // RN19: variável já usada em critério do estudo fica indisponível na árvore e nos resultados da busca.
    function marcarUsadas() {
        var marca = regras.querySelector("[data-usadas]");
        var usadas = marca && marca.dataset.usadas ? marca.dataset.usadas.split(",") : [];
        tela.querySelectorAll(".variavel-botao[data-variavel]").forEach(function (botao) {
            var emUso = usadas.indexOf(botao.dataset.variavel) >= 0;
            botao.disabled = emUso;
            var tipo = botao.querySelector(".variavel-tipo");
            if (tipo) {
                tipo.textContent = emUso ? "em uso" : tipo.dataset.tipo;
            }
        });
    }

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

    // Data: o mês e o dia só aparecem quando a precisão pede, e o segundo período só no "entre".
    function ajustarData(form) {
        var precisao = form.querySelector('input[name="precisao"]:checked');
        if (!precisao) {
            return;
        }
        var escolhido = form.querySelector('input[name="operador"]:checked');
        var entre = !!escolhido && escolhido.value === "entre";
        form.querySelectorAll("[data-mes]").forEach(function (bloco) {
            bloco.hidden = precisao.value === "ano";
        });
        form.querySelectorAll("[data-dia]").forEach(function (bloco) {
            bloco.hidden = precisao.value !== "dia";
        });
        form.querySelectorAll("[data-entre-data]").forEach(function (bloco) {
            bloco.hidden = !entre;
        });
    }

    function atualizarPrevia(form) {
        var pedido = ++pedidoDaPrevia;
        // O corpo leva o formulário inteiro, inclusive o token CSRF.
        fetch(form.dataset.previaUrl, { method: "POST", body: new FormData(form) }).then(function (resposta) {
            return recarregarSeFalhou(resposta) ? "" : resposta.text();
        }).then(function (html) {
            // Resposta de uma prévia anterior que chegou atrasada.
            if (pedido !== pedidoDaPrevia || !html) {
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

    function iniciarCascataDoFormulario(form) {
        var bloco = form.querySelector("[data-cascata]");
        if (bloco) {
            window.iniciarCascata(bloco, {
                pegar: pegar,
                aoMudar: function () {
                    agendarPrevia(form);
                },
            });
        }
    }

    function fecharConfiguracao() {
        configuracao.innerHTML = textoInicial;
        marcarAtiva(null);
    }

    function iniciarFormulario(form) {
        iniciarCascataDoFormulario(form);
        ajustarValores(form);
        ajustarData(form);
        atualizarPrevia(form);

        form.addEventListener("input", function () {
            ajustarValores(form);
            ajustarData(form);
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

        var cancelar = form.querySelector("[data-cancelar]");
        if (cancelar) {
            cancelar.addEventListener("click", fecharConfiguracao);
        }

        form.addEventListener("submit", function (evento) {
            evento.preventDefault();
            fetch(form.action, { method: "POST", body: new FormData(form) }).then(function (resposta) {
                if (recarregarSeFalhou(resposta)) {
                    return;
                }
                return resposta.text().then(function (html) {
                    if (resposta.ok) {
                        regras.innerHTML = html;
                        marcarUsadas();
                        if (form.dataset.modo === "edicao") {
                            fecharConfiguracao();
                        } else {
                            // Recarrega a mesma variável com o formulário limpo, para
                            // adicionar outro critério sobre ela sem escolhê-la de novo.
                            abrirConfiguracao(aberta.url, aberta.botao);
                        }
                    } else {
                        document.getElementById("previa").innerHTML = html;
                    }
                });
            });
        });
    }

    function alternarConfirmacao(regra, pedir) {
        regra.querySelector(".regra-acoes").hidden = pedir;
        regra.querySelector(".regra-confirmacao").hidden = !pedir;
        // O foco vai para o "Não", o botão seguro, e volta ao × quando se desiste.
        regra.querySelector(pedir ? ".regra-nao" : ".regra-remover").focus();
    }

    regras.addEventListener("click", function (evento) {
        var editar = evento.target.closest(".regra-editar");
        if (editar) {
            abrirConfiguracao(editar.dataset.url, null);
            return;
        }
        var pedido = evento.target.closest("[data-pedir-remocao]");
        if (pedido) {
            regras.querySelectorAll(".regra-confirmacao:not([hidden])").forEach(function (aberta) {
                alternarConfirmacao(aberta.closest(".regra"), false);
            });
            alternarConfirmacao(pedido.closest(".regra"), true);
            return;
        }
        var desistencia = evento.target.closest("[data-cancelar-remocao]");
        if (desistencia) {
            alternarConfirmacao(desistencia.closest(".regra"), false);
        }
    });

    regras.addEventListener("keydown", function (evento) {
        var confirmacao = evento.target.closest(".regra-confirmacao");
        if (evento.key === "Escape" && confirmacao) {
            alternarConfirmacao(confirmacao.closest(".regra"), false);
        }
    });

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
                        marcarUsadas();
                    regras.focus();
                }
            });
    });

    if (tela.dataset.configuracaoInicial) {
        abrirConfiguracao(tela.dataset.configuracaoInicial, botaoDaArvore(tela.dataset.configuracaoInicial));
    }
})();
