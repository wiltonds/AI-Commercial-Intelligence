from dataclasses import dataclass

from src.tools.portfolio import PortfolioTool
from src.intelligence.cnae_classifier import CNAEClassificador
from src.intelligence.sector_affinity import (
    SectorAffinityEngine,
    SectorRecommendation,
)


STOPWORDS = {
    "e",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "em",
    "para",
    "com",
    "a",
    "o",
    "as",
    "os",
    "no",
    "na",
}

# Termo que aparece em uma fração grande do catálogo (ex: "técnica",
# "segurança") é evidência fraca por si só — precisa vir acompanhado
# de outro termo mais raro/específico para sustentar o match.
LIMIAR_TERMO_GENERICO = 0.03


@dataclass
class ProdutoPortfolio:
    entidade: str
    codigo: str | None
    nome: str
    caminho: list[str]
    caminho_texto: str
    texto_busca: str


@dataclass
class ProdutoMatch:
    entidade: str
    codigo: str | None
    produto: str
    caminho_texto: str
    area_origem: str
    score_afinidade_setor: float
    score_correspondencia_texto: float
    correspondencia_especifica: bool
    score_fit: float
    evidencias: list[str]


class PortfolioMatcher:
    """
    Encontra produtos reais do catálogo SESI/SENAI
    compatíveis com o perfil de um lead.
    """

    def __init__(
        self,
        portfolio_tool: PortfolioTool | None = None,
        affinity_engine: SectorAffinityEngine | None = None,
    ):
        self.portfolio_tool = portfolio_tool or PortfolioTool()
        self.affinity_engine = affinity_engine or SectorAffinityEngine()
        self._catalogo_pesquisavel: list[ProdutoPortfolio] | None = None
        self._frequencia_termo_cache: dict[str, int] = {}

    def catalogo_pesquisavel(self) -> list[ProdutoPortfolio]:
        """
        Retorna os produtos do catálogo já normalizados
        para busca textual (sem acento, caixa única).
        """

        if self._catalogo_pesquisavel is not None:
            return self._catalogo_pesquisavel

        produtos = []

        for item in self.portfolio_tool.catalogo():
            produtos.append(
                ProdutoPortfolio(
                    entidade=item["entidade"],
                    codigo=item["codigo"],
                    nome=item["nome"],
                    caminho=item["caminho"],
                    caminho_texto=item["caminho_texto"],
                    texto_busca=CNAEClassificador.normalizar(
                        item["caminho_texto"]
                    ),
                )
            )

        self._catalogo_pesquisavel = produtos

        return self._catalogo_pesquisavel

    def _entidade_da_area(self, area: str) -> str | None:
        area_upper = area.upper()

        if area_upper.startswith("SESI"):
            return "SESI"

        if area_upper.startswith("SENAI"):
            return "SENAI"

        return None

    def _frequencia_termo(self, termo: str) -> int:
        if termo not in self._frequencia_termo_cache:
            self._frequencia_termo_cache[termo] = sum(
                1
                for produto in self.catalogo_pesquisavel()
                if termo in produto.texto_busca
            )

        return self._frequencia_termo_cache[termo]

    def _termo_especifico(self, termo: str) -> bool:
        total_produtos = len(self.catalogo_pesquisavel())
        frequencia = self._frequencia_termo(termo)

        return (frequencia / total_produtos) < LIMIAR_TERMO_GENERICO

    def _termos_busca(self, area: str) -> list[str]:
        entidade = self._entidade_da_area(area)

        resto = area[len(entidade):] if entidade else area

        normalizado = CNAEClassificador.normalizar(resto)

        return [
            palavra
            for palavra in normalizado.split()
            if len(palavra) > 2 and palavra not in STOPWORDS
        ]

    def buscar_por_area(
        self,
        recomendacao: SectorRecommendation,
        limite: int = 3,
    ) -> list[ProdutoMatch]:
        """
        Busca produtos reais do catálogo compatíveis com
        uma área de afinidade setorial.
        """

        entidade = self._entidade_da_area(recomendacao.area)
        termos = self._termos_busca(recomendacao.area)

        if not termos:
            return []

        candidatos = []

        for produto in self.catalogo_pesquisavel():

            if entidade and produto.entidade != entidade:
                continue

            termos_encontrados = [
                termo for termo in termos if termo in produto.texto_busca
            ]

            if not termos_encontrados:
                continue

            score_texto = round(
                100 * len(termos_encontrados) / len(termos), 1
            )

            candidatos.append((score_texto, termos_encontrados, produto))

        candidatos.sort(key=lambda candidato: candidato[0], reverse=True)

        # O catálogo repete o mesmo curso sob códigos diferentes
        # (ex: natureza + oferta específica) — mantém só a melhor
        # ocorrência de cada nome para não duplicar a recomendação.
        vistos = set()
        candidatos_unicos = []

        for candidato in candidatos:
            _, _, produto = candidato
            chave = (produto.entidade, produto.nome)

            if chave in vistos:
                continue

            vistos.add(chave)
            candidatos_unicos.append(candidato)

        resultados = []

        for score_texto, termos_encontrados, produto in candidatos_unicos[
            :limite
        ]:

            score_fit = round(
                0.5 * recomendacao.score + 0.5 * score_texto, 1
            )

            especificos = [
                termo
                for termo in termos_encontrados
                if self._termo_especifico(termo)
            ]

            termo_mais_raro = min(
                termos_encontrados,
                key=lambda termo: self._frequencia_termo(termo),
            )

            resultados.append(
                ProdutoMatch(
                    entidade=produto.entidade,
                    codigo=produto.codigo,
                    produto=produto.nome,
                    caminho_texto=produto.caminho_texto,
                    area_origem=recomendacao.area,
                    score_afinidade_setor=recomendacao.score,
                    score_correspondencia_texto=score_texto,
                    correspondencia_especifica=bool(especificos),
                    score_fit=score_fit,
                    evidencias=[
                        f"Área de afinidade: {recomendacao.area} "
                        f"(score {recomendacao.score})",
                        "Termos compatíveis no catálogo: "
                        + ", ".join(termos_encontrados),
                        f"Termo mais específico do match: "
                        f"'{termo_mais_raro}' (presente em "
                        f"{self._frequencia_termo(termo_mais_raro)} de "
                        f"{len(self.catalogo_pesquisavel())} produtos "
                        f"do catálogo)",
                        f"Motivo setorial: {recomendacao.motivo}",
                    ],
                )
            )

        return resultados

    def recomendar(
        self,
        setor: str | None,
        areas: int = 3,
        produtos_por_area: int = 3,
    ) -> list[ProdutoMatch]:
        """
        A partir de um setor, percorre as áreas de maior afinidade
        e retorna produtos reais do catálogo compatíveis com cada uma.
        """

        recomendacoes = self.affinity_engine.recomendar(setor)

        resultados = []

        for recomendacao in recomendacoes[:areas]:
            resultados.extend(
                self.buscar_por_area(recomendacao, limite=produtos_por_area)
            )

        return sorted(
            resultados,
            key=lambda resultado: resultado.score_fit,
            reverse=True,
        )
