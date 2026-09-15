from src.domain.lead import LeadProfile


class SDRAgent:
    """
    Qualifica leads comercialmente usando sinais estruturados.

    O score mede prioridade comercial.
    Não representa a aderência de uma solução específica.
    """

    def qualificar(self, lead: LeadProfile) -> dict:
        score = 0
        evidencias = []

        # ---------------------------------------------------------
        # 1. RELACIONAMENTO SESI / SENAI
        # ---------------------------------------------------------

        if lead.tem_sesi and lead.tem_senai:
            score += 10
            evidencias.append(
                "Empresa já possui relacionamento com SESI e SENAI."
            )

        elif lead.tem_sesi:
            score += 25
            evidencias.append(
                "Empresa possui SESI, mas ainda apresenta potencial de expansão para SENAI."
            )

        elif lead.tem_senai:
            score += 25
            evidencias.append(
                "Empresa possui SENAI, mas ainda apresenta potencial de expansão para SESI."
            )

        else:
            score += 20
            evidencias.append(
                "Empresa sem relacionamento identificado com SESI ou SENAI."
            )

        # ---------------------------------------------------------
        # 2. PORTE
        # ---------------------------------------------------------

        porte = (lead.porte or "").upper()

        if "GRANDE" in porte:
            score += 30
            evidencias.append("Empresa de grande porte.")

        elif "MEDIA" in porte or "MÉDIA" in porte:
            score += 20
            evidencias.append("Empresa de médio porte.")

        elif "PEQUENA" in porte:
            score += 10
            evidencias.append("Empresa de pequeno porte.")

        elif "MICRO" in porte:
            score += 5
            evidencias.append("Empresa de micro porte.")

        # ---------------------------------------------------------
        # 3. SEBRAE
        # ---------------------------------------------------------

        if lead.encontrado_sebrae:
            score += 5
            evidencias.append(
                "Empresa também foi encontrada na base SEBRAE."
            )

        if lead.sebrae_elegivel:
            score += 10
            evidencias.append(
                "Empresa é elegível na base SEBRAE."
            )

        if (
            lead.oportunidade_sebrae
            and lead.oportunidade_sebrae.upper() != "NÃO ATENDIDA"
        ):
            score += 10
            evidencias.append(
                "SEBRAE apresenta sinal adicional de oportunidade comercial."
            )

        # ---------------------------------------------------------
        # 4. OPORTUNIDADE SESI / SENAI
        # ---------------------------------------------------------

        if (lead.oportunidade_sesi or "").upper() == "SIM":
            score += 10
            evidencias.append(
                "Base Mestre indica oportunidade comercial em SESI."
            )

        if (lead.oportunidade_senai or "").upper() == "SIM":
            score += 10
            evidencias.append(
                "Base Mestre indica oportunidade comercial em SENAI."
            )

        # ---------------------------------------------------------
        # 5. CLASSIFICAÇÃO
        # ---------------------------------------------------------

        if score >= 70:
            prioridade = "ALTA"

        elif score >= 45:
            prioridade = "MÉDIA"

        else:
            prioridade = "BAIXA"

        return {
            "cnpj": lead.cnpj,
            "score": score,
            "prioridade": prioridade,
            "evidencias": evidencias,
        }