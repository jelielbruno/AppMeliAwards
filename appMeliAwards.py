import streamlit as st
import pandas as pd
import os
from datetime import datetime
import textwrap

PERGUNTA_ARQUIVO = "Perguntas.xlsx"
ACESSOS_ARQUIVO = "Acessos.xlsx"
RESPOSTA_ARQUIVO = "Respostas.xlsx"

def ler_perguntas(path):
    df = pd.read_excel(path, header=0)
    perguntas = {}
    tipos_avaliacao = [
        ('Comercial', 0, 1),
        ('Técnica', 2, 3),
        ('ESG', 4, 5)
    ]
    for tipo, col_q, col_p in tipos_avaliacao:
        perguntas[tipo] = []
        for idx in range(len(df)):
            q = df.iloc[idx, col_q]
            p = df.iloc[idx, col_p]
            if pd.notnull(q) and pd.notnull(p) and str(q).strip() != "":
                perguntas[tipo].append((str(q).strip(), float(p)))
    return perguntas

def carregar_acessos(path):
    acessos = pd.read_excel(path, sheet_name='Acessos')
    categorias = pd.read_excel(path, sheet_name='Categorias')
    return acessos, categorias

def checar_usuario(email, tipo, categoria, acessos):
    filtro = (
        (acessos.iloc[:, 0].str.lower() == email.lower()) &
        (acessos.iloc[:, 1].str.lower() == tipo.lower()) &
        (acessos.iloc[:, 2] == categoria)
    )
    return not acessos[filtro].empty

def get_opcoes_tipo(email, acessos):
    return acessos[acessos.iloc[:,0].str.lower() == email.lower()].iloc[:,1].dropna().unique().tolist()

def get_opcoes_categorias(email, tipo, acessos):
    return acessos[
        (acessos.iloc[:,0].str.lower() == email.lower()) &
        (acessos.iloc[:,1].str.lower() == tipo.lower())
    ].iloc[:,2].dropna().unique().tolist()

def fornecedores_para_categoria(categoria, categorias):
    fornecedores = categorias[categorias.iloc[:,0] == categoria].iloc[:,1].dropna().tolist()
    return fornecedores

def obter_df_resposta(aba):
    if os.path.exists(RESPOSTA_ARQUIVO):
        xls = pd.ExcelFile(RESPOSTA_ARQUIVO)
        if aba in xls.sheet_names:
            return pd.read_excel(RESPOSTA_ARQUIVO, sheet_name=aba)
    return pd.DataFrame()

def obter_consolidado():
    if os.path.exists(RESPOSTA_ARQUIVO):
        xls = pd.ExcelFile(RESPOSTA_ARQUIVO)
        if 'Consolidado' in xls.sheet_names:
            return pd.read_excel(RESPOSTA_ARQUIVO, sheet_name='Consolidado')
    return pd.DataFrame()

def salvar_resposta_ponderada(tipo, email, categoria, fornecedor, respostas, perguntas):
    hoje = datetime.now()
    data_str = hoje.strftime("%d/%m/%Y")
    hora_str = hoje.strftime("%H:%M:%S")
    aba = tipo.capitalize()
    df = obter_df_resposta(aba)
    colunas_fixas = ["Data", "Hora", "E-mail", "Categoria", "Fornecedor"]
    colunas_perguntas = [q for (q, p) in perguntas]
    colunas_ponderada = [q + " (PONDERADA)" for (q, p) in perguntas]
    todas_colunas = colunas_fixas + colunas_perguntas + colunas_ponderada
    notas_puras = []
    notas_ponderadas = []
    for (pergunta, peso) in perguntas:
        nota = respostas[pergunta]
        notas_puras.append(nota)
        ponderada = nota * peso
        notas_ponderadas.append(ponderada)
    nova_linha = [data_str, hora_str, email, categoria, fornecedor] + notas_puras + notas_ponderadas
    nova_df = pd.DataFrame([nova_linha], columns=todas_colunas)

    if not df.empty:
        for col in todas_colunas:
            if col not in df.columns:
                df[col] = ""
        for col in df.columns:
            if col not in todas_colunas:
                nova_df[col] = ""

        mask = (df['E-mail'].str.lower() == email.lower()) & \
               (df['Categoria'] == categoria) & \
               (df['Fornecedor'] == fornecedor)
        df = df[~mask]
        df = pd.concat([df, nova_df], ignore_index=True)
        df = df[todas_colunas]
    else:
        df = nova_df
    return aba, df

def salvar_consolidado(email, categoria, fornecedor, perguntas_dict):
    cons = obter_consolidado()
    colunas_fixas = ['Categoria', 'Fornecedor']
    avaliacoes = ['Comercial', 'Técnica', 'ESG']
    colunas_puras = []
    for t in avaliacoes:
        colunas_puras.extend([q for (q, p) in perguntas_dict[t]])

    resultado_col = "Resultado Final"
    if cons.empty:
        cons = pd.DataFrame(columns=colunas_fixas + colunas_puras + [resultado_col])

    for col in colunas_fixas + colunas_puras + [resultado_col]:
        if col not in cons.columns:
            cons[col] = 0.0 if col not in colunas_fixas else ""

    mask = (cons['Categoria'] == categoria) & (cons['Fornecedor'] == fornecedor)
    if mask.any():
        idx = cons[mask].index[0]
    else:
        nova = dict()
        nova['Categoria'] = categoria
        nova['Fornecedor'] = fornecedor
        for c in colunas_puras:
            nova[c] = 0.0
        nova[resultado_col] = 0.0
        cons = pd.concat([cons, pd.DataFrame([nova])], ignore_index=True)
        idx = cons.shape[0] - 1

    soma_puras = 0.0
    count_puras = 0
    for t in avaliacoes:
        col_perguntas = [q for (q, p) in perguntas_dict[t]]
        dfresp = obter_df_resposta(t)
        if not dfresp.empty:
            mask_user = (dfresp['E-mail'].str.lower() == email.lower()) & \
                        (dfresp['Categoria'] == categoria) & \
                        (dfresp['Fornecedor'] == fornecedor)
            linhas = dfresp[mask_user].copy()
            if not linhas.empty:
                linha = linhas.iloc[-1]
                for col in col_perguntas:
                    val = linha.get(col, 0.0)
                    cons.loc[idx, col] = val
                    if pd.notnull(val) and str(val) != "":
                        soma_puras += float(val)
                        count_puras += 1
            else:
                for col in col_perguntas:
                    cons.loc[idx, col] = 0.0
        else:
            for col in col_perguntas:
                cons.loc[idx, col] = 0.0

    cons.loc[idx, resultado_col] = soma_puras / count_puras if count_puras else 0.0
    ordered = colunas_fixas + colunas_puras + [resultado_col]
    cons = cons[ordered]
    return cons

def salvar_excel(tabela: dict):
    if os.path.exists(RESPOSTA_ARQUIVO):
        xls = pd.ExcelFile(RESPOSTA_ARQUIVO)
        abas_existentes = {s: pd.read_excel(RESPOSTA_ARQUIVO, sheet_name=s) for s in xls.sheet_names if s not in tabela}
    else:
        abas_existentes = {}
    with pd.ExcelWriter(RESPOSTA_ARQUIVO, engine="openpyxl", mode='w') as writer:
        for aba, df in tabela.items():
            df.to_excel(writer, sheet_name=aba, index=False)
        for aba, df in abas_existentes.items():
            df.to_excel(writer, sheet_name=aba, index=False)

def wrap_col_names(df, width=25):
    df = df.copy()
    df.columns = ['\n'.join(textwrap.wrap(str(col), width=width)) for col in df.columns]
    return df

st.set_page_config("Scorecard de Fornecedores", layout="wide")
st.markdown(""" <h1 style='text-align: center; color: white;'>📊 Scorecard de Fornecedores<br></h1>
""", unsafe_allow_html=True)
st.markdown("<h1 style='text-align: center; color: #FFD700;'>Programa - Meli Awards<br></h1>", unsafe_allow_html=True)

perguntas_ref = ler_perguntas(PERGUNTA_ARQUIVO)
acessos, categorias_df = carregar_acessos(ACESSOS_ARQUIVO)

if "email_logado" not in st.session_state:
    st.session_state.email_logado = ""

if "fornecedores_responsaveis" not in st.session_state:
    st.session_state.fornecedores_responsaveis = {}

if "pagina" not in st.session_state:
    st.session_state.pagina = "Avaliar Fornecedores"

# LOGIN
if st.session_state.email_logado == "":
    with st.form("login"):
        email = st.text_input("Seu e-mail corporativo").strip()
        submitted_login = st.form_submit_button("Entrar")
    if submitted_login:
        tipos = get_opcoes_tipo(email, acessos)
        if not tipos:
            st.error("E-mail sem permissão cadastrada.")
            st.stop()
        st.session_state.email_logado = email
        st.session_state.fornecedores_responsaveis = {}
        st.session_state.pagina = "Avaliar Fornecedores"
        st.rerun()
else:
    st.sidebar.write(f"**E-mail logado:** {st.session_state.email_logado}")
    if st.sidebar.button("Sair"):
        st.session_state.email_logado = ""
        st.session_state.fornecedores_responsaveis = {}
        st.session_state.pagina = "Avaliar Fornecedores"
        st.rerun()
    pagina_radio = st.sidebar.radio(
        "Navegar",
        ["Avaliar Fornecedores", "Resumo Final"],
        index=0 if st.session_state.pagina=="Avaliar Fornecedores" else 1
    )
    if pagina_radio != st.session_state.pagina:
        st.session_state.pagina = pagina_radio
        st.rerun()

# PÁGINA 1: Avaliação
if st.session_state.email_logado != "" and st.session_state.pagina == "Avaliar Fornecedores":
    email = st.session_state.email_logado
    tipos = get_opcoes_tipo(email, acessos)
    tipo = st.selectbox("Tipo de avaliação", tipos, key="tipo")
    categorias = get_opcoes_categorias(email, tipo, acessos)
    if len(categorias) == 0:
        st.warning("Nenhuma categoria para este tipo.")
        st.stop()
    categoria = st.selectbox("Categoria", categorias, key="cat")
    fornecedores = fornecedores_para_categoria(categoria, categorias_df)

    fornecedores_responsaveis = st.session_state.fornecedores_responsaveis.get(tipo, [])

    for f in fornecedores:
        if f in fornecedores_responsaveis:
            st.markdown(f"<span style='color: green;'>{f}</span>", unsafe_allow_html=True)
        else:
            st.write(f"{f}")

    if len(fornecedores) > 0:
        fornecedor_selecionado = st.selectbox("Selecionar Fornecedor", fornecedores, key="forn")

        if not checar_usuario(email, tipo, categoria, acessos):
            st.error("Acesso negado! Verifique seu e-mail, categoria e tipo de avaliação.")
            st.stop()

        st.markdown("---")
        st.header(f"Avaliação {tipo} para {fornecedor_selecionado} ({categoria})")

        # Legenda para as notas
        st.markdown("""
            <div style="font-size: 13px;">
                <span style="color:#999"><b>1</b> = Ruim &nbsp;&nbsp;&nbsp; <b>2</b> = Regular &nbsp;&nbsp;&nbsp; <b>3</b> = Bom</span>
            </div>""", unsafe_allow_html=True)

        perguntas = perguntas_ref.get(tipo.capitalize())
        if perguntas:
            with st.form("avaliacao"):
                notas = {}
                for idx, (pergunta, peso) in enumerate(perguntas, 1):
                    st.markdown(f"<b>{idx}. {pergunta} (Peso {peso})</b>", unsafe_allow_html=True)
                    notas[pergunta] = st.slider(
                        label="Selecione sua nota:",
                        min_value=1,
                        max_value=3,
                        value=2,
                        step=1,
                        key=f"slider_{idx}_{pergunta}"
                    )
                submitted = st.form_submit_button("Enviar avaliação")
                if submitted:
                    notas_lista = [notas[q] for (q, p) in perguntas]
                    ponderadas_lista = [notas[q] * p for (q, p) in perguntas]
                    aba, df_atualizada = salvar_resposta_ponderada(
                        tipo, email, categoria, fornecedor_selecionado, notas, perguntas
                    )
                    st.session_state.fornecedores_responsaveis.setdefault(tipo, []).append(fornecedor_selecionado)
                    consolidado_df = salvar_consolidado(
                        email, categoria, fornecedor_selecionado, perguntas_ref
                    )
                    salvar_excel({aba: df_atualizada, 'Consolidado': consolidado_df})
                    st.success("Avaliação registrada e consolidação atualizada com sucesso!")

    fornecedores_responsaveis = st.session_state.fornecedores_responsaveis.get(tipo, [])
    if len(fornecedores_responsaveis) > 0:
        if st.button("Prévia das Notas"):
            st.session_state.pagina = "Resumo Final"
            st.rerun()

# PÁGINA 2: Resumo Final
if st.session_state.email_logado != "" and st.session_state.pagina == "Resumo Final":
    st.subheader("Resultado Final das Suas Avaliações")
    email = st.session_state.email_logado
    consolidado_df = obter_consolidado()

    if not consolidado_df.empty:
        tipos_avaliados = []
        fornecedores_usu = set()
        for t in ['Comercial', 'Técnica', 'ESG']:
            df_t = obter_df_resposta(t)
            if not df_t.empty and "E-mail" in df_t.columns:
                df_user = df_t[df_t["E-mail"].str.lower() == email.lower()]
                if not df_user.empty:
                    tipos_avaliados.append(t)
                    fornec = df_user["Fornecedor"].unique().tolist()
                    fornecedores_usu.update(fornec)
        fornecedores_usu = list(fornecedores_usu)
        mask = consolidado_df["Fornecedor"].isin(fornecedores_usu)
        resumo_exclusivo = consolidado_df[mask].copy()

        if not resumo_exclusivo.empty and tipos_avaliados:
            colunas_fixas = ['Categoria', 'Fornecedor']
            colunas_mostrar = []
            for tipo in tipos_avaliados:
                perguntas = perguntas_ref.get(tipo, [])
                colunas_mostrar.extend([q for (q, _) in perguntas])
            colunas_resultado = ["Resultado Final"]
            cols_finais = colunas_fixas + colunas_mostrar + colunas_resultado
            cols_finais_show = [c for c in cols_finais if c in resumo_exclusivo.columns]

            st.dataframe(wrap_col_names(resumo_exclusivo[cols_finais_show], width=25),
                         use_container_width=True, hide_index=True)

            if st.button("Finalizar avaliação"):
                st.session_state.pagina = "Final"
                st.rerun()
        else:
            st.info("Nenhuma avaliação encontrada para exibir o resultado final.")
    else:
        st.info("Nenhum dado consolidado disponível ainda.")

# "Pop-up" final central (sobrepondo a tela toda)
if st.session_state.pagina == "Final":
    st.markdown(
        """
        <style>
        .my-modal-bg {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; 
            background: rgba(0,0,0,0.40); z-index: 99999;
            display: flex; align-items: center; justify-content: center;
        }
        .my-modal-box {
            background: #fff; border-radius: 18px; padding: 40px 36px 30px 36px;
            max-width: 97vw; width: 420px; text-align: center; box-shadow: 0 0 40px #0002;
            border: 1.5px solid #888;
        }
        .my-modal-box h3 { margin-bottom: 25px; }
        .my-modal-sair { font-size: 1.14em; margin-top:10px; padding:12px 30px;
        border-radius:9px;border:none;background:#ffd700;color:#222;cursor:pointer;}
        </style>
        <div class="my-modal-bg">
            <div class="my-modal-box">
                <h3>
                    Avaliação finalizada, notas atribuídas com sucesso.<br>
                    <span style="font-weight:normal">Obrigado pela contribuição!</span>
                </h3>
                <form action="" method="post">
                    <button class="my-modal-sair" type="submit" name="sairfake">Sair</button>
                </form>
            </div>
        </div>
        """, unsafe_allow_html=True
    )
    # Fake POST para detectar clique
    if st.form("sairfake").form_submit_button("sairfake", type="primary"):
        st.session_state.clear()
        st.rerun()