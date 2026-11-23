import calendar
from datetime import date

from django import forms
from django.core.exceptions import ValidationError

from autenticacao.forms import EstiloBootstrapMixin
from catalogo.models import Operador, Variavel, normalizar

from .models import Criterio, Estudo, Tcle

TAMANHO_MAXIMO_TCLE = 5 * 1024 * 1024

# Operadores que a tela de critérios oferece em cada tipo, com o rótulo do botão.
# O modelo aceita mais combinações, mas o pesquisador escolhe entre estas.
OPERADORES_DA_TELA = {
    Variavel.Tipo.NUMERICA: (
        (Operador.ENTRE, "entre"),
        (Operador.MAIOR_IGUAL, "pelo menos"),
        (Operador.MENOR_IGUAL, "no máximo"),
        (Operador.IGUAL, "exatamente"),
        (Operador.DIFERENTE, "diferente de"),
        (Operador.MAIOR, "acima de"),
        (Operador.MENOR, "abaixo de"),
    ),
    Variavel.Tipo.ORDINAL: (
        (Operador.MAIOR_IGUAL, "a partir de"),
        (Operador.MENOR_IGUAL, "até"),
        (Operador.E, "exatamente"),
    ),
    Variavel.Tipo.NOMINAL: ((Operador.ESTA_EM, "está em"),),
    Variavel.Tipo.BOOLEANA: ((Operador.VERDADEIRO, "Sim"), (Operador.FALSO, "Não")),
    Variavel.Tipo.DATA: ((Operador.ANTES, "antes de"), (Operador.DEPOIS, "depois de"), (Operador.ENTRE, "entre")),
}

# O pesquisador informa ano, mês e dia conforme a precisão. A data gravada sai desses campos.
CAMPOS_DE_DATA = (
    ("ano", 1900, 2100), ("mes", 1, 12), ("dia", 1, 31),
    ("ano_ate", 1900, 2100), ("mes_ate", 1, 12), ("dia_ate", 1, 31),
)


class EstudoForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Estudo
        fields = ("nome", "condicao", "descricao", "participantes_necessarios", "prazo_guarda_ate", "situacao")
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
            "prazo_guarda_ate": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
        help_texts = {
            "prazo_guarda_ate": (
                "Só preencha se a aprovação ética exigir guardar os dados por mais tempo. Ao encerrar o estudo antes "
                "dessa data, a eliminação espera por ela. Depois do encerramento o prazo não muda."
            ),
            "participantes_necessarios": "Quantos participantes o estudo precisa reunir. Deixe em branco se ainda não houver número definido.",
        }

    tcle = forms.FileField(
        label="TCLE (PDF)",
        required=False,
        help_text="Termo de Consentimento Livre e Esclarecido. Sem ele o estudo não pode ser ativado. Até 5 MB.",
    )

    def clean_tcle(self):
        arquivo = self.cleaned_data["tcle"]
        if not arquivo:
            return arquivo
        if arquivo.size > TAMANHO_MAXIMO_TCLE:
            raise forms.ValidationError("O arquivo passa de 5 MB.")
        # A extensão é digitada pelo usuário, então confere também a assinatura do PDF.
        if not arquivo.name.lower().endswith(".pdf") or arquivo.read(5) != b"%PDF-":
            raise forms.ValidationError("Envie o TCLE em PDF.")
        arquivo.seek(0)
        return arquivo

    def salvar_tcle(self, estudo):
        arquivo = self.cleaned_data.get("tcle")
        if arquivo:
            Tcle.objects.update_or_create(
                estudo=estudo, defaults={"nome_arquivo": arquivo.name[:255], "conteudo": arquivo.read()}
            )
        return bool(arquivo)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.tem_tcle:
            self.fields["tcle"].label = "Substituir o TCLE (PDF)"
        if self.instance.situacao == Estudo.Situacao.ENCERRADO:
            del self.fields["tcle"]
        if not self.instance.pk:
            # Todo estudo nasce como rascunho. A ativação passa pela tela de confirmação.
            del self.fields["situacao"]
        elif self.instance.situacao == Estudo.Situacao.ENCERRADO:
            # Mudar o prazo depois do encerramento deixaria dado guardado sem rotina que o elimine.
            self.fields["prazo_guarda_ate"].disabled = True
            self.fields["situacao"].choices = [(Estudo.Situacao.ENCERRADO, Estudo.Situacao.ENCERRADO.label)]
            self.fields["situacao"].help_text = "Estudo encerrado não volta a ficar ativo, porque os dados dos voluntários já foram eliminados."
        elif self.instance.situacao == Estudo.Situacao.ATIVO:
            self.fields["situacao"].choices = [
                (Estudo.Situacao.ATIVO, Estudo.Situacao.ATIVO.label),
                (Estudo.Situacao.ENCERRADO, Estudo.Situacao.ENCERRADO.label),
            ]
            self.fields["situacao"].help_text = (
                "Estudo ativado não volta a ser rascunho. Ao escolher Encerrado, o sistema pede uma confirmação e elimina "
                "os dados dos voluntários sem outro estudo ativo."
            )
        else:
            self.fields["situacao"].help_text = (
                "Ao escolher Ativo, o sistema pede uma confirmação e os critérios deixam de poder ser alterados. "
                "Ao escolher Encerrado, pede outra confirmação e elimina os dados dos voluntários sem outro estudo ativo."
            )

    def clean_situacao(self):
        situacao = self.cleaned_data["situacao"]
        if self.instance.situacao == Estudo.Situacao.ENCERRADO and situacao != Estudo.Situacao.ENCERRADO:
            raise forms.ValidationError("Estudo encerrado não volta a ficar ativo, porque os dados dos voluntários já foram eliminados.")
        if self.instance.situacao == Estudo.Situacao.ATIVO and situacao == Estudo.Situacao.RASCUNHO:
            raise forms.ValidationError("Estudo ativado não volta a ser rascunho, porque os critérios já não podem mudar.")
        return situacao


class CriterioForm(forms.ModelForm):
    class Meta:
        model = Criterio
        fields = ("tipo_regra", "operador", "valor_numero", "valor_numero_ate", "opcoes", "precisao")
        widgets = {"opcoes": forms.CheckboxSelectMultiple, "precisao": forms.RadioSelect}
        error_messages = {"operador": {"required": "Escolha como comparar."}}

    def __init__(self, *args, variavel, **kwargs):
        self.variavel = variavel
        super().__init__(*args, **kwargs)

        self.operadores = OPERADORES_DA_TELA[variavel.tipo]
        self.fields["operador"].choices = [(operador.value, rotulo) for operador, rotulo in self.operadores]
        if variavel.tipo == Variavel.Tipo.BOOLEANA:
            self.fields["operador"].error_messages["required"] = "Escolha sim ou não."

        if variavel.tipo != Variavel.Tipo.NUMERICA:
            del self.fields["valor_numero"], self.fields["valor_numero_ate"]
        if variavel.tipo in (Variavel.Tipo.NOMINAL, Variavel.Tipo.ORDINAL):
            self.fields["opcoes"].queryset = variavel.dominio.opcoes.all()
        else:
            del self.fields["opcoes"]
        if variavel.tipo == Variavel.Tipo.DATA:
            for nome, minimo, maximo in CAMPOS_DE_DATA:
                self.fields[nome] = forms.IntegerField(required=False, min_value=minimo, max_value=maximo)
        else:
            del self.fields["precisao"]

    def clean(self):
        dados = super().clean()
        # A ModelForm só copia os campos para a instância depois do clean, e a
        # validação das opções precisa deles agora.
        self.instance.variavel = self.variavel
        self.instance.operador = dados.get("operador", "")
        if "opcoes" in self.fields and "operador" in dados:
            escolhidas = list(dados.get("opcoes") or [])
            self.instance.opcoes_em_memoria = escolhidas
            try:
                self.instance.validar_opcoes()
            except ValidationError as erro:
                self.add_error(None, erro)
            else:
                self.recusar_todas_as_opcoes(dados, escolhidas)
        if self.variavel.tipo == Variavel.Tipo.DATA and "operador" in dados:
            self.montar_datas(dados)
        if not self.errors:
            self.recusar_variavel_repetida()
        return dados

    def periodo(self, sufixo, precisao):
        """Primeiro e último dia do período informado, ou None com o erro junto do campo que falta."""
        valores = {nome: self.cleaned_data.get(nome + sufixo) for nome in ("ano", "mes", "dia")}
        exigidos = {Criterio.Precisao.ANO: ("ano",), Criterio.Precisao.MES: ("ano", "mes")}.get(
            precisao, ("ano", "mes", "dia")
        )
        rotulos = {"ano": "o ano", "mes": "o mês", "dia": "o dia"}
        for nome in exigidos:
            if valores[nome] is None:
                if nome + sufixo not in self.errors:
                    self.add_error(nome + sufixo, f"Informe {rotulos[nome]}.")
                return None
        ano, mes, dia = valores["ano"], valores["mes"], valores["dia"]
        try:
            if precisao == Criterio.Precisao.ANO:
                return date(ano, 1, 1), date(ano, 12, 31)
            if precisao == Criterio.Precisao.MES:
                return date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])
            return date(ano, mes, dia), date(ano, mes, dia)
        except ValueError:
            self.add_error("dia" + sufixo if precisao == Criterio.Precisao.DIA else "mes" + sufixo, "Essa data não existe.")
            return None

    def montar_datas(self, dados):
        """RN17: antes de usa o primeiro dia do período e depois de, o último."""
        precisao = dados.get("precisao") or Criterio.Precisao.DIA
        operador = dados["operador"]
        inicio = self.periodo("", precisao)
        fim = self.periodo("_ate", precisao) if operador == Operador.ENTRE else None
        instancia = self.instance
        instancia.precisao = precisao
        instancia.valor_data = instancia.valor_data_ate = None
        if inicio is None or (operador == Operador.ENTRE and fim is None):
            return
        instancia.valor_data = inicio[1] if operador == Operador.DEPOIS else inicio[0]
        if operador == Operador.ENTRE:
            instancia.valor_data_ate = fim[1]

    def recusar_variavel_repetida(self):
        """RN19: cada variável aparece em um só critério do estudo."""
        if not self.instance.estudo_id:
            return
        repetida = Criterio.objects.filter(estudo_id=self.instance.estudo_id, variavel=self.variavel)
        if repetida.exclude(pk=self.instance.pk).exists():
            self.add_error(None, "Esta variável já é usada em um critério deste estudo.")

    def recusar_todas_as_opcoes(self, dados, escolhidas):
        # Um critério que cobre todas as opções não restringe ninguém: na inclusão
        # aceita todo mundo, na exclusão barra todo mundo.
        if not self.cobre_todas_as_opcoes(dados["operador"], escolhidas):
            return
        verbo = "exclui" if dados.get("tipo_regra") == Criterio.TipoRegra.EXCLUSAO else "inclui"
        self.add_error("opcoes", f"Esse critério {verbo} todos os participantes.")

    def cobre_todas_as_opcoes(self, operador, escolhidas):
        niveis = self.fields["opcoes"].queryset
        if self.variavel.tipo != Variavel.Tipo.ORDINAL:
            return operador == Operador.ESTA_EM and len(escolhidas) == niveis.count()

        # Na escala, um nível só já cobre tudo quando é "a partir do mais baixo"
        # ou "até o mais alto".
        ordem = [nivel.pk for nivel in niveis.order_by("ordem")]
        if operador == Operador.MAIOR_IGUAL:
            return escolhidas[0].pk == ordem[0]
        return operador == Operador.MENOR_IGUAL and escolhidas[0].pk == ordem[-1]

    def pendencia(self):
        for erros in self.errors.values():
            return erros[0]


class VariavelPropostaForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Variavel
        fields = ("subcategoria", "nome", "tipo", "unidade", "minimo", "maximo", "dominio", "vida_util_dias", "sensivel")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Texto livre não serve de critério, e data o pesquisador não informa: a
        # idade em anos já vem do que o voluntário registrar.
        self.fields["tipo"].choices = [
            (valor, rotulo)
            for valor, rotulo in Variavel.Tipo.choices
            if valor not in (Variavel.Tipo.TEXTO, Variavel.Tipo.DATA)
        ]
        self.fields["unidade"].help_text = "Obrigatória para variável numérica."
        self.fields["vida_util_dias"].help_text = "Em branco significa permanente."

    def clean(self):
        dados = super().clean()
        nome = dados.get("nome")
        if nome:
            # O código sai do nome normalizado, para o catálogo não ganhar
            # identificadores digitados à mão e divergentes entre si.
            self.instance.codigo = normalizar(nome).replace(" ", "_")[:60]
            if Variavel.objects.filter(codigo=self.instance.codigo).exists():
                raise forms.ValidationError("Já existe uma variável com esse nome no catálogo.")
        return dados

    def parecidas(self):
        nome = self.cleaned_data.get("nome", "")
        palavras = [p for p in normalizar(nome).split() if len(p) > 3]
        if not palavras:
            return []
        consulta = Variavel.objects.none()
        for palavra in palavras:
            consulta = consulta | Variavel.objects.filter(busca__contains=palavra)
        return list(consulta.select_related("subcategoria").distinct()[:8])
