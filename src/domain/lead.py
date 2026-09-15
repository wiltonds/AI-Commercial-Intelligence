from pydantic import BaseModel, Field


class LeadProfile(BaseModel):
    cnpj: str
    razao_social: str | None = None
    municipio: str | None = None
    cnae_principal: str | None = None
    setor: str | None = None
    porte: str | None = None

    tem_sesi: bool = False
    tem_senai: bool = False
    tem_sesi_senai: bool = False

    status_relacionamento: str | None = None

    encontrado_sebrae: bool = False
    sebrae_elegivel: bool = False

    oportunidade_sesi: str | None = None
    oportunidade_senai: str | None = None
    oportunidade_sebrae: str | None = None
    oportunidade_geral: str | None = None
    oportunidade_cross_sell: str | None = None

    produtos_atuais: list[str] = Field(default_factory=list)
    oportunidades: list[str] = Field(default_factory=list)
    score_aderencia: float | None = None