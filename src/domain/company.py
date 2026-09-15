from pydantic import BaseModel, Field


class Company(BaseModel):
    """
    Representa uma empresa no universo de mercado.

    Company descreve quem é a empresa.
    Informações específicas de oportunidade comercial
    ficam no LeadProfile.
    """

    cnpj: str = Field(..., description="CNPJ da empresa")

    razao_social: str | None = None
    nome_fantasia: str | None = None

    municipio: str | None = None
    uf: str | None = None

    cnae_principal: str | None = None
    setor: str | None = None
    porte: str | None = None