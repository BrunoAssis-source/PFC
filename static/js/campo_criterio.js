(function () {
    var operador = document.getElementById("id_operador");
    if (!operador) {
        return;
    }

    var opcoes = document.getElementById("id_opcoes");
    var precisao = document.getElementById("id_precisao");
    var segundos = ["id_valor_numero_ate", "id_data_ate", "id_mes_ano_ate", "id_ano_ate"];

    function bloco(id) {
        var campo = document.getElementById(id);
        return campo ? campo.closest(".mb-3") : null;
    }

    function ajudaDe(campo) {
        var linha = campo.closest(".mb-3");
        return linha ? linha.querySelector(".ajuda-campo") : null;
    }

    function ajustar() {
        var valor = operador.value;
        var entre = valor === "entre";

        segundos.forEach(function (id) {
            var linha = bloco(id);
            if (linha) {
                linha.hidden = !entre;
            }
        });

        if (precisao) {
            var campos = { dia: "id_data", mes: "id_mes_ano", ano: "id_ano" };
            Object.keys(campos).forEach(function (chave) {
                var escolhido = precisao.value === chave;
                var linha = bloco(campos[chave]);
                if (linha) {
                    linha.hidden = !escolhido;
                }
                var linhaAte = bloco(campos[chave] + "_ate");
                if (linhaAte) {
                    linhaAte.hidden = !(escolhido && entre);
                }
            });
        }

        if (opcoes) {
            var varios = entre || valor === "esta_em" || valor === "nao_esta_em";
            opcoes.multiple = varios;
            opcoes.size = varios ? 6 : 1;
            var ajuda = ajudaDe(opcoes);
            if (ajuda) {
                if (entre) {
                    ajuda.textContent = "Escolha dois valores, o de baixo e o de cima da faixa.";
                } else if (varios) {
                    ajuda.textContent = "Escolha um ou mais valores, segurando Ctrl.";
                } else {
                    ajuda.textContent = "Escolha um valor.";
                }
            }
        }
    }

    operador.addEventListener("change", ajustar);
    if (precisao) {
        precisao.addEventListener("change", ajustar);
    }
    ajustar();
})();
