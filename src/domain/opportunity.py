from pydantic import BaseModel, Field


class Opportunity(BaseModel):
    company_cnpj: str
    origem: str
    area: str
    solucao: str
    motivo: str

    score_fit: float = Field(ge=0, le=100)

    # Heurística operacional (definida pelo caso de relacionamento em
    # OpportunityEngine), não uma probabilidade calibrada de conversão.
    # Só vira estatística de verdade quando cruzada com feedback real
    # do consultor (aceite/rejeição) e resultado de conversão.
    confidence: float = Field(ge=0, le=1)

    evidencias: list[str] = Field(default_factory=list)

    fonte: str

    tipo_evidencia: str

    prioridade: str

    produto_codigo: str | None = None
    caminho_catalogo: str | None = None

    consultor_destino: str | None = None