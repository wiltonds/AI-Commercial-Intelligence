import re


class CNAEClassificador:
    """
    Classifica uma empresa a partir da descrição do CNAE.
    """

    REGRAS = {
        "ALIMENTOS": [
            "alimento",
            "alimentos",
            "massa alimenticia",
            "massas alimenticias",
            "panificacao",
            "padaria",
            "confeitaria",
            "laticinio",
            "bebida",
            "frigorifico",
            "carne",
            "abate",
        ],
        "CONSTRUCAO": [
            "construcao",
            "construção",
            "obra",
            "edificacao",
            "edificação",
            "engenharia civil",
            "instalacao eletrica",
            "instalação elétrica",
            "instalacoes",
            "instalações",
        ],
        "METALMECANICA": [
            "metal",
            "metalmecanica",
            "metalmecânica",
            "mecanica",
            "mecânica",
            "usinagem",
            "solda",
            "soldagem",
            "maquinas",
            "máquinas",
            "equipamentos",
            "caldeiraria",
            "tornearia",
        ],
        "TEXTIL": [
            "textil",
            "têxtil",
            "vestuario",
            "vestuário",
            "confeccao",
            "confecção",
            "tecelagem",
            "malharia",
        ],
        "QUIMICA": [
            "quimica",
            "química",
            "produtos quimicos",
            "produtos químicos",
            "cosmetico",
            "cosmético",
            "farmaceutico",
            "farmacêutico",
            "plastico",
            "plástico",
            "borracha",
        ],
    }

    @staticmethod
    def normalizar(texto: str) -> str:
        if not texto:
            return ""

        texto = str(texto).upper()

        substituicoes = {
            "Á": "A",
            "À": "A",
            "Ã": "A",
            "Â": "A",
            "É": "E",
            "Ê": "E",
            "Í": "I",
            "Ó": "O",
            "Ô": "O",
            "Õ": "O",
            "Ú": "U",
            "Ç": "C",
        }

        for origem, destino in substituicoes.items():
            texto = texto.replace(origem, destino)

        texto = re.sub(r"[^A-Z0-9 ]", " ", texto)
        texto = re.sub(r"\s+", " ", texto)

        return texto.strip().lower()

    def classificar(self, cnae: str | None) -> str | None:
        if not cnae:
            return None

        texto = self.normalizar(cnae)

        for setor, palavras in self.REGRAS.items():
            for palavra in palavras:
                if self.normalizar(palavra) in texto:
                    return setor

        return None