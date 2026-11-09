(function () {
    var bloco = document.querySelector("[data-cascata]");
    if (!bloco) {
        return;
    }

    // Sessão vencida: a resposta seria a tela de login, que não pode entrar no meio da lista.
    function pegar(endereco) {
        return fetch(endereco).then(function (resposta) {
            if (resposta.redirected || !resposta.ok) {
                window.location.reload();
                return "";
            }
            return resposta.text();
        });
    }

    window.iniciarCascata(bloco, { pegar: pegar, unico: true, campo: "valor" });
})();
