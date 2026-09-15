from pathlib import Path
import json


PORTFOLIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "knowledge"
    / "portfolio"
    / "portfolio_compact.json"
)


class PortfolioTool:
    """
    Consulta o catálogo oficial de produtos e cursos
    do portfólio SESI/SENAI.
    """

    def __init__(self, portfolio_path: Path = PORTFOLIO_PATH):
        self.portfolio_path = portfolio_path
        self._portfolio = None
        self._catalogo = None

    def _load(self):
        if self._portfolio is None:
            with open(self.portfolio_path, "r", encoding="utf-8") as file:
                self._portfolio = json.load(file)

        return self._portfolio

    def _percorrer(
        self,
        no: dict,
        entidade: str,
        caminho: list[str] | None = None,
    ):
        if caminho is None:
            caminho = []

        nome = no.get("n")
        tipo = no.get("t")

        novo_caminho = caminho.copy()

        if nome:
            novo_caminho.append(nome)

        # Nó final: curso/produto
        if tipo == "c":
            self._catalogo.append(
                {
                    "entidade": entidade,
                    "codigo": no.get("c"),
                    "nome": nome,
                    "tipo": tipo,
                    "caminho": novo_caminho,
                    "caminho_texto": " > ".join(novo_caminho),
                }
            )

        for filho in no.get("ch", []):
            self._percorrer(
                filho,
                entidade,
                novo_caminho,
            )

    def catalogo(self) -> list[dict]:
        """
        Retorna todos os produtos/cursos finais
        do portfólio SESI e SENAI.
        """

        self._load()

        if self._catalogo is not None:
            return self._catalogo

        self._catalogo = []

        for entidade in ["SESI", "SENAI"]:
            raiz = self._portfolio["trees"].get(entidade)

            if raiz:
                self._percorrer(
                    raiz,
                    entidade,
                )

        return self._catalogo

    def buscar(
        self,
        termo: str,
        entidade: str | None = None,
        limite: int = 20,
    ) -> list[dict]:
        """
        Busca textual no catálogo.
        """

        termo = termo.strip().upper()

        if not termo:
            return []

        resultados = []

        for item in self.catalogo():

            if entidade and item["entidade"] != entidade.upper():
                continue

            texto = item["caminho_texto"].upper()

            if termo in texto:
                resultados.append(item)

            if len(resultados) >= limite:
                break

        return resultados