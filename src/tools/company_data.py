from pathlib import Path

import pandas as pd


BASE_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "processed"
    / "BASE_MESTRE_COMERCIAL.csv"
)


class CompanyDataTool:
    """Ferramenta de consulta da Base Mestre Comercial."""

    def __init__(self, base_path: Path = BASE_PATH):
        self.base_path = base_path
        self._df = None

    def _load(self):
        if self._df is None:
            self._df = pd.read_csv(
                self.base_path,
                dtype={"cnpj": str, "CNPJ_NORMALIZADO": str},
                low_memory=False,
            )

            self._df["cnpj"] = (
                self._df["cnpj"]
                .astype(str)
                .str.replace(r"\D", "", regex=True)
                .str.zfill(14)
            )

        return self._df

    def consultar_empresa(self, cnpj: str) -> dict | None:
        """Consulta uma empresa pelo CNPJ."""

        cnpj_normalizado = (
            str(cnpj)
            .replace(".", "")
            .replace("/", "")
            .replace("-", "")
            .strip()
            .zfill(14)
        )

        df = self._load()

        resultado = df[df["cnpj"] == cnpj_normalizado]

        if resultado.empty:
            return None

        registro = resultado.iloc[0]

        return {
            "cnpj": cnpj_normalizado,
            "razao_social": registro.get("razao_social"),
            "municipio": registro.get("Municipio"),
            "setor": registro.get("SETOR"),
            "cnae_principal": registro.get("CNAE PRIMARIO"),
            "porte": registro.get("Porte"),
            "eh_industria": registro.get("EH_INDUSTRIA"),
            "tem_sesi": registro.get("TEM_SESI"),
            "tem_senai": registro.get("TEM_SENAI"),
            "tem_sesi_senai": registro.get("TEM_SESI_SENAI"),
            "status_relacionamento": registro.get(
                "STATUS_RELACIONAMENTO"
            ),
            "encontrado_sebrae": registro.get(
                "ENCONTRADO_SEBRAE"
            ),
            "sebrae_elegivel": registro.get(
                "SEBRAE_ELEGIVEL"
            ),
            "oportunidade_sesi": registro.get(
                "OPORTUNIDADE_SESI"
            ),
            "oportunidade_senai": registro.get(
                "OPORTUNIDADE_SENAI"
            ),
            "oportunidade_sebrae": registro.get(
                "OPORTUNIDADE_SEBRAE"
            ),
            "oportunidade_geral": registro.get(
                "OPORTUNIDADE_GERAL"
            ),
            "oportunidade_cross_sell": registro.get(
                "OPORTUNIDADE_CROSS_SELL"
            ),
        }