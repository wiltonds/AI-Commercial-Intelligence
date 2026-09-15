import re


ORIGEM_LABEL = {
    "CROSS_SELL": "Venda cruzada (já é cliente SESI/SENAI)",
    "AQUISIÇÃO": "Novo cliente (prospecção)",
}

# O que cada check do Supervisor verifica, em uma frase — o nome cru
# da chave (ex: "correspondencia_aceitavel") não deixa claro o que
# está sendo avaliado nem para uma leitura técnica/auditoria.
CHECK_LABELS = {
    "produto_existe": (
        "O produto recomendado existe de fato no catálogo oficial "
        "(tem código válido)"
    ),
    "tem_evidencia": (
        "A recomendação tem pelo menos uma evidência registrada"
    ),
    "fit_minimo": (
        "O fit combinado (afinidade setorial + correspondência "
        "textual) está acima do mínimo aceitável"
    ),
    "correspondencia_aceitavel": (
        "Pelo menos uma das palavras que conectam o produto à área "
        "de afinidade é específica o suficiente — não depende só de "
        "termos genéricos (ex: \"técnica\", \"segurança\") que "
        "aparecem em muitos produtos do catálogo"
    ),
    "cobertura_minima": (
        "Uma parcela mínima das palavras-chave da área de afinidade "
        "realmente aparece no produto (não é só 1 palavra isolada "
        "num conjunto de várias)"
    ),
    "setor_compativel": (
        "A entidade do produto (SESI/SENAI) é compatível com a área "
        "de afinidade que originou a recomendação"
    ),
}


def descrever_check(nome_check: str) -> str:
    return CHECK_LABELS.get(nome_check, nome_check)


def traduzir_alerta(alerta: str) -> str:
    """
    Traduz o motivo técnico de rejeição do Supervisor para uma frase
    que explica em linguagem comercial por que aquele produto não foi
    sugerido — sem números de score ou nomes de check.
    """

    if "sem código no catálogo" in alerta:
        return "Esse item não tem um código válido no catálogo oficial."

    if "sem evidências registradas" in alerta:
        return (
            "Não foi possível reunir evidências suficientes para "
            "sustentar essa recomendação."
        )

    if re.match(r"^Fit .* abaixo do mínimo", alerta):
        return (
            "A aderência geral desse produto ao perfil da empresa "
            "ficou abaixo do esperado."
        )

    if "termos genéricos do catálogo" in alerta:
        return (
            "A conexão com esse produto se baseia só em palavras muito "
            "genéricas do catálogo — não há uma evidência específica "
            "forte o bastante."
        )

    if re.match(r"^Cobertura textual de", alerta):
        return (
            "Poucas características da área de interesse realmente "
            "aparecem nesse produto específico."
        )

    if "não corresponde à área de afinidade" in alerta:
        return (
            "Inconsistência entre o produto e a área de origem da "
            "recomendação."
        )

    return alerta


def classificar_aderencia(score_fit: float) -> str:
    if score_fit >= 80:
        return "Alta"
    if score_fit >= 65:
        return "Média"
    return "Baixa"


def traduzir_evidencia(evidencia: str) -> str | None:
    """
    Traduz uma evidência técnica interna para linguagem comercial.

    Retorna None para evidências que só interessam ao modo auditoria
    (estatísticas de frequência de termo no catálogo, por exemplo).
    """

    if evidencia == "TEM_SESI=True":
        return "Já é cliente SESI"

    if evidencia == "TEM_SESI=False":
        return "Ainda não é cliente SESI"

    if evidencia == "TEM_SENAI=True":
        return "Já é cliente SENAI"

    if evidencia == "TEM_SENAI=False":
        return "Ainda não é cliente SENAI"

    match = re.match(r"^Setor=(.+)$", evidencia)
    if match:
        return f"Setor identificado: {match.group(1)}"

    match = re.match(r"^Área de afinidade: (.+?) \(score", evidencia)
    if match:
        return f"Área com maior aderência ao setor: {match.group(1)}"

    match = re.match(r"^Termos compatíveis no catálogo: (.+)$", evidencia)
    if match:
        return f"Conexão encontrada no catálogo: {match.group(1)}"

    match = re.match(r"^Motivo setorial: (.+)$", evidencia)
    if match:
        return match.group(1)

    if evidencia.startswith("Termo mais específico do match"):
        return None

    return evidencia
