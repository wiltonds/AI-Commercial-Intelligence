from src.domain.lead import LeadProfile


class DataQualityAgent:
    """
    Avalia se os dados disponíveis de um lead são suficientes
    e consistentes para apoiar uma decisão comercial.
    """

    def avaliar(self, lead: LeadProfile) -> dict:
        score = 0
        evidencias = []
        alertas = []

        # Identidade
        if lead.cnpj:
            score += 15
            evidencias.append("CNPJ identificado.")
        else:
            alertas.append("CNPJ não identificado.")

        if lead.razao_social:
            score += 10
            evidencias.append("Razão social identificada.")
        else:
            alertas.append("Razão social não identificada.")

        # Localização
        if lead.municipio:
            score += 5
            evidencias.append("Município identificado.")
        else:
            alertas.append("Município não identificado.")

        # Atividade econômica
        if lead.cnae_principal:
            score += 15
            evidencias.append("CNAE principal identificado.")
        else:
            alertas.append("CNAE principal não identificado.")

        if lead.setor:
            score += 15
            evidencias.append(
                f"Setor econômico classificado como {lead.setor}."
            )
        else:
            alertas.append(
                "Não foi possível classificar o setor econômico."
            )

        # Porte
        if lead.porte:
            score += 10
            evidencias.append("Porte da empresa identificado.")
        else:
            alertas.append("Porte da empresa não identificado.")

        # Relacionamento
        if lead.status_relacionamento:
            score += 10
            evidencias.append(
                "Status de relacionamento SESI/SENAI identificado."
            )
        else:
            alertas.append(
                "Status de relacionamento não identificado."
            )

        # SEBRAE
        if lead.encontrado_sebrae:
            score += 5
            evidencias.append(
                "Empresa encontrada na base SEBRAE."
            )

        # Classificação
        if score >= 80:
            confianca = "ALTA"
        elif score >= 60:
            confianca = "MÉDIA"
        else:
            confianca = "BAIXA"

        return {
            "cnpj": lead.cnpj,
            "score": score,
            "confianca": confianca,
            "evidencias": evidencias,
            "alertas": alertas,
            "apto_para_decisao": score >= 60,
        }