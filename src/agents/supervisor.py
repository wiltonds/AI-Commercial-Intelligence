from src.intelligence.portfolio_matcher import ProdutoMatch


FIT_MINIMO = 60

# Abaixo disso, poucos termos da área de afinidade realmente aparecem
# no produto — mesmo que o termo encontrado seja raro no catálogo
# (ex: "manutenção" sozinho casa com cursos de motocicleta, rede de
# computadores etc., sem nenhuma relação com a área de origem).
COBERTURA_MINIMA = 40.0


class Supervisor:
    """
    Audita um ProdutoMatch antes de virar recomendação comercial.

    Decide se a evidência reunida pelo PortfolioMatcher sustenta
    a recomendação, ou se ela deve ser rejeitada.
    """

    def avaliar(self, produto: ProdutoMatch) -> dict:
        checks = {}
        alertas = []

        checks["produto_existe"] = bool(produto.codigo)

        if not checks["produto_existe"]:
            alertas.append("Produto sem código no catálogo oficial.")

        checks["tem_evidencia"] = bool(produto.evidencias)

        if not checks["tem_evidencia"]:
            alertas.append("Recomendação sem evidências registradas.")

        checks["fit_minimo"] = produto.score_fit >= FIT_MINIMO

        if not checks["fit_minimo"]:
            alertas.append(
                f"Fit {produto.score_fit} abaixo do mínimo ({FIT_MINIMO})."
            )

        checks["correspondencia_aceitavel"] = (
            produto.correspondencia_especifica
        )

        if not checks["correspondencia_aceitavel"]:
            alertas.append(
                "Correspondência textual sustentada apenas por termos "
                "genéricos do catálogo, sem evidência específica."
            )

        checks["cobertura_minima"] = (
            produto.score_correspondencia_texto >= COBERTURA_MINIMA
        )

        if not checks["cobertura_minima"]:
            alertas.append(
                f"Cobertura textual de {produto.score_correspondencia_texto}%"
                f" abaixo do mínimo ({COBERTURA_MINIMA}%) — poucos termos "
                "da área de afinidade aparecem no produto."
            )

        checks["setor_compativel"] = produto.area_origem.upper().startswith(
            produto.entidade
        )

        if not checks["setor_compativel"]:
            alertas.append(
                "Entidade do produto não corresponde à área de "
                "afinidade setorial de origem."
            )

        aprovado = all(checks.values())

        return {
            "produto": produto.produto,
            "codigo": produto.codigo,
            "entidade": produto.entidade,
            "area_origem": produto.area_origem,
            "score_fit": produto.score_fit,
            "aprovado": aprovado,
            "checks": checks,
            "alertas": alertas,
            "evidencias": produto.evidencias,
        }

    def avaliar_lote(
        self,
        produtos: list[ProdutoMatch],
    ) -> list[dict]:
        return [self.avaliar(produto) for produto in produtos]
