from dataclasses import dataclass


@dataclass
class SectorRecommendation:
    area: str
    score: float
    motivo: str


class SectorAffinityEngine:
    """
    Motor determinístico de aderência setorial.

    A função deste componente é responder:
    "Quais áreas do SESI/SENAI possuem maior aderência
    ao setor/CNAE da empresa?"
    """

    MATRIZ = {
        "CONSTRUCAO": [
            SectorRecommendation(
                area="SESI SST & Saúde Ocupacional",
                score=95,
                motivo="Alta exposição a riscos ocupacionais e exigências de SST.",
            ),
            SectorRecommendation(
                area="SENAI Formação Técnica",
                score=88,
                motivo="Demanda recorrente por qualificação técnica da força de trabalho.",
            ),
            SectorRecommendation(
                area="SENAI Eficiência e Processos",
                score=78,
                motivo="Potencial para melhoria de produtividade, processos e gestão.",
            ),
        ],
        "ALIMENTOS": [
            SectorRecommendation(
                area="SESI SST & Ergonomia",
                score=92,
                motivo="Relevância de segurança, saúde ocupacional e ergonomia.",
            ),
            SectorRecommendation(
                area="SENAI Automação, Mecânica e Manutenção",
                score=90,
                motivo="Processos produtivos dependem de máquinas, manutenção e eficiência.",
            ),
            SectorRecommendation(
                area="SENAI Qualidade e Laboratórios",
                score=85,
                motivo="Qualidade e controle de processos são críticos para alimentos.",
            ),
            SectorRecommendation(
                area="SESI Saúde e Bem-estar",
                score=75,
                motivo="Possibilidade de ações relacionadas à saúde dos trabalhadores.",
            ),
        ],
        "METALMECANICA": [
            SectorRecommendation(
                area="SENAI Capacitação Técnica",
                score=94,
                motivo="Alta demanda por competências técnicas industriais.",
            ),
            SectorRecommendation(
                area="SESI Segurança de Máquinas",
                score=91,
                motivo="Relevância de segurança de máquinas e processos industriais.",
            ),
            SectorRecommendation(
                area="SENAI Lean e Processos",
                score=84,
                motivo="Potencial para ganhos de produtividade e redução de desperdícios.",
            ),
            SectorRecommendation(
                area="SESI Saúde Ocupacional",
                score=78,
                motivo="Exposição ocupacional relevante em ambientes industriais.",
            ),
            SectorRecommendation(
                area="SENAI Energia",
                score=60,
                motivo="Possibilidade de ganhos relacionados à eficiência energética.",
            ),
        ],
    }

    def identificar_setor(self, setor: str | None) -> str | None:
        """Normaliza o setor informado."""

        if not setor:
            return None

        texto = setor.upper()

        if "CONSTRU" in texto:
            return "CONSTRUCAO"

        if "ALIMENT" in texto or "BEBIDA" in texto:
            return "ALIMENTOS"

        if (
            "METAL" in texto
            or "MECAN" in texto
            or "MÁQUINA" in texto
            or "MAQUINA" in texto
        ):
            return "METALMECANICA"

        return None

    def recomendar(
        self,
        setor: str | None,
    ) -> list[SectorRecommendation]:

        setor_normalizado = self.identificar_setor(setor)

        if setor_normalizado is None:
            return []

        return sorted(
            self.MATRIZ[setor_normalizado],
            key=lambda item: item.score,
            reverse=True,
        )