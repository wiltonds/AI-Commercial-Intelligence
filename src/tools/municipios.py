"""Grafia única dos municípios de Alagoas.

As bases vêm de fontes diferentes e o mesmo município aparece escrito de
jeitos diferentes ("Arapiraca" e "ARAPIRACA", "São Miguel dos Campos" e
"Sao Miguel Dos Campos"). No painel isso vira duas opções no filtro e divide
os números. Aqui fica a grafia oficial (IBGE, com acento) e a função que
troca qualquer variação por ela. A comparação ignora maiúsculas, acentos,
espaços e pontuação; o que não é município de AL fica como está.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

# Os 102 municípios de Alagoas, grafia oficial
MUNICIPIOS_AL = [
    'Anadia',
    'Arapiraca',
    'Atalaia',
    'Barra de Santo Antônio',
    'Barra de São Miguel',
    'Batalha',
    'Belo Monte',
    'Belém',
    'Boca da Mata',
    'Branquinha',
    'Cacimbinhas',
    'Cajueiro',
    'Campestre',
    'Campo Alegre',
    'Campo Grande',
    'Canapi',
    'Capela',
    'Carneiros',
    'Chã Preta',
    'Coité do Nóia',
    'Colônia Leopoldina',
    'Coqueiro Seco',
    'Coruripe',
    'Craíbas',
    'Delmiro Gouveia',
    'Dois Riachos',
    'Estrela de Alagoas',
    'Feira Grande',
    'Feliz Deserto',
    'Flexeiras',
    'Girau do Ponciano',
    'Ibateguara',
    'Igaci',
    'Igreja Nova',
    'Inhapi',
    'Jacaré dos Homens',
    'Jacuípe',
    'Japaratinga',
    'Jaramataia',
    'Jequiá da Praia',
    'Joaquim Gomes',
    'Jundiá',
    'Junqueiro',
    'Lagoa da Canoa',
    'Limoeiro de Anadia',
    'Maceió',
    'Major Isidoro',
    'Mar Vermelho',
    'Maragogi',
    'Maravilha',
    'Marechal Deodoro',
    'Maribondo',
    'Mata Grande',
    'Matriz de Camaragibe',
    'Messias',
    'Minador do Negrão',
    'Monteirópolis',
    'Murici',
    'Novo Lino',
    "Olho d'Água Grande",
    "Olho d'Água das Flores",
    "Olho d'Água do Casado",
    'Olivença',
    'Ouro Branco',
    'Palestina',
    'Palmeira dos Índios',
    'Pariconha',
    'Paripueira',
    'Passo de Camaragibe',
    'Paulo Jacinto',
    'Penedo',
    'Piaçabuçu',
    'Pilar',
    'Pindoba',
    'Piranhas',
    'Porto Calvo',
    'Porto Real do Colégio',
    'Porto de Pedras',
    'Poço das Trincheiras',
    'Pão de Açúcar',
    'Quebrangulo',
    'Rio Largo',
    'Roteiro',
    'Santa Luzia do Norte',
    'Santana do Ipanema',
    'Santana do Mundaú',
    'Satuba',
    'Senador Rui Palmeira',
    'São Brás',
    'São José da Laje',
    'São José da Tapera',
    'São Luís do Quitunde',
    'São Miguel dos Campos',
    'São Miguel dos Milagres',
    'São Sebastião',
    "Tanque d'Arca",
    'Taquarana',
    'Teotônio Vilela',
    'Traipu',
    'União dos Palmares',
    'Viçosa',
    'Água Branca',
]


def chave(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", t)


OFICIAL = {chave(n): n for n in MUNICIPIOS_AL}


def padronizar(serie: pd.Series) -> pd.Series:
    """Troca cada valor pela grafia oficial; o que não é município de AL fica igual."""
    return serie.map(lambda v: OFICIAL.get(chave(v), v) if isinstance(v, str) and v.strip() else v)


def colunas_municipio(colunas) -> list[str]:
    """Colunas com nome de município (ignora as de código IBGE)."""
    return [c for c in colunas if "municipio" in chave(c) and "codigo" not in chave(c)]


def padronizar_df(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica a grafia oficial em todas as colunas de município do DataFrame."""
    for c in colunas_municipio(df.columns):
        df[c] = padronizar(df[c])
    return df
