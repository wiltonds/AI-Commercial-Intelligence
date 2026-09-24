"""Recruiter-facing demo for AI Commercial Intelligence.

Uses synthetic/anonymized data and mirrors the real commercial workflow:
company profile -> data quality -> qualification -> product matching ->
quality gate -> opportunity briefing.

This demo does not use production company/customer data.
"""

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="AI Commercial Intelligence | Demo",
    page_icon="🎯",
    layout="wide",
)

st.markdown("""
<style>
.block-container {max-width: 1250px; padding-top: 2rem;}
.kpi {border:1px solid #ddd;border-radius:10px;padding:16px;background:#fff;}
.badge {display:inline-block;padding:5px 10px;border-radius:999px;border:1px solid #ddd;font-size:12px;}
</style>
""", unsafe_allow_html=True)

companies = pd.DataFrame([
    {
        "CNPJ":"12.345.678/0001-90",
        "Empresa":"Metalúrgica Horizonte Ltda.",
        "Município":"Maceió",
        "Setor":"Fabricação de produtos de metal",
        "Porte":"Médio",
        "SESI":"Sim","SENAI":"Não","Score":92,
    },
    {
        "CNPJ":"98.765.432/0001-10",
        "Empresa":"Alagoas Equipamentos Industriais",
        "Município":"Rio Largo",
        "Setor":"Máquinas e equipamentos",
        "Porte":"Médio","SESI":"Não","SENAI":"Sim","Score":87,
    },
    {
        "CNPJ":"45.678.901/0001-22",
        "Empresa":"Nordeste Processos Industriais",
        "Município":"Marechal Deodoro",
        "Setor":"Produtos químicos",
        "Porte":"Grande","SESI":"Não","SENAI":"Não","Score":84,
    },
])

offers = [
    ("NR-12 — Segurança em Máquinas e Equipamentos","Segurança do Trabalho",94,"CNAE + setor + catálogo"),
    ("Manutenção Industrial — Formação Técnica","Manutenção Industrial",89,"Setor + afinidade técnica"),
    ("Programa de Melhoria da Produtividade","Gestão Industrial",82,"Porte + setor"),
]

st.title("🎯 AI Commercial Intelligence")
st.caption("Demo executável · dados sintéticos · fluxo representativo do sistema")

c1,c2,c3,c4 = st.columns(4)
for col,title,value,sub in [
    (c1,"Empresas analisadas","3","universo demonstrativo"),
    (c2,"Produtos no catálogo","3.712","referência do sistema"),
    (c3,"Lead prioritário","92/100","score demonstrativo"),
    (c4,"Quality Gate","Aprovado","evidência suficiente"),
]:
    with col:
        st.markdown(f'<div class="kpi"><b>{title}</b><h2>{value}</h2><small>{sub}</small></div>', unsafe_allow_html=True)

st.divider()

empresa = st.selectbox("Empresa para diagnóstico", companies["Empresa"])
lead = companies[companies["Empresa"] == empresa].iloc[0]

left, mid, right = st.columns(3)
with left:
    st.subheader("Company Profile")
    st.write(f"**Empresa:** {lead['Empresa']}")
    st.write(f"**CNPJ:** {lead['CNPJ']}")
    st.write(f"**Município:** {lead['Município']}")
    st.write(f"**Setor:** {lead['Setor']}")
    st.write(f"**Porte:** {lead['Porte']}")
with mid:
    st.subheader("Data Quality")
    st.metric("Score", "96/100")
    st.success("Apto para decisão")
    st.write("CNPJ identificado")
    st.write("CNAE disponível")
    st.write("Setor classificado")
with right:
    st.subheader("SDR Qualification")
    st.metric("Priority", f"{lead['Score']}/100")
    st.info("Alta prioridade")
    st.write(f"SESI: {lead['SESI']} · SENAI: {lead['SENAI']}")
    st.write("Opportunity type: Cross-sell / Acquisition")

st.divider()
st.subheader("Approved Recommendations")

for name, area, score, evidence in offers:
    with st.container(border=True):
        a,b,c = st.columns([5,2,2])
        a.markdown(f"**{name}**")
        a.caption(f"{area} · evidence: {evidence}")
        b.metric("Fit", f"{score}%")
        c.success("APPROVED")
        st.write("**Why recommended:** sector affinity + company profile + verified catalog item.")
        st.caption("Decision remains with the commercial team; AI assists communication but does not invent the product.")

st.divider()
st.subheader("🤖 AI Sales Brief")
st.markdown("""
**Pain hypothesis:** operational safety and workforce qualification may be relevant given the company's industrial profile.

**Qualification questions**
- Which machine-safety risks are currently most difficult to control?
- Which teams require mandatory or recurring training?
- Are there recent incidents, audits or compliance gaps?

**Next action:** validate the hypothesis with the customer before proposing the approved offering.
""")

st.caption("DEMO — all company identifiers, scores and recommendations shown above are synthetic and are not production customer data.")
