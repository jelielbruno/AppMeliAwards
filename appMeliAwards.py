import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import textwrap
import numpy as np

# IDs das planilhas compartilhadas no Google Sheets
PERGUNTAS_ID = "1-mlYet1m6pN510WN8V-6XEJyDovXdlQN0TLzlr0WcPY"
ACESSOS_ID = "1p5bzFBwAOAisFZLlt3lqXjDPJG-GfL2xkkm3fxQhQRU"
RESPOSTAS_ID = "1OKhItXlUwmYGGIVBpNIO_48Hsb5wIRZlZ6a8p_ZbheA"
ADMIN_PASSWORD = "admin123"

# Conectar com Google Sheets
def conectar_planilha(sheet_id):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gspread"], scope)
    client = gspread.authorize(creds)
    return client.open_by_key(sheet_id)

def ler_perguntas(_):
    sheet = conectar_planilha(PERGUNTAS_ID)
    worksheet = sheet.get_worksheet(0)
    df = pd.DataFrame(worksheet.get_all_records())
    perguntas = {}
    tipos_avaliacao = {'Comercial': [], 'Técnica': [], 'ESG': []}
    for tipo in tipos_avaliacao.keys():
        cols_questao = [c for c in df.columns if tipo.lower() in str(c).lower() and "peso" not in str(c).lower()]
        cols_peso = [c for c in df.columns if tipo.lower() in str(c).lower() and "peso" in str(c).lower()]
        cols_questao.sort(); cols_peso.sort()
        for col_q, col_p in zip(cols_questao, cols_peso):
            for idx in range(len(df)):
                q = df.at[idx, col_q]
                p = df.at[idx, col_p]
                if pd.notnull(q) and pd.notnull(p) and str(q).strip() != "":
                    tipos_avaliacao[tipo].append((str(q).strip(), float(p)))
        perguntas[tipo] = tipos_avaliacao[tipo]
    return perguntas

def carregar_acessos(_):
    sheet = conectar_planilha(ACESSOS_ID)
    acessos = pd.DataFrame(sheet.worksheet("Acessos").get_all_records())
    categorias = pd.DataFrame(sheet.worksheet("Categorias").get_all_records())
    return acessos, categorias

def obter_df_resposta(aba):
    sheet = conectar_planilha(RESPOSTAS_ID)
    try:
        worksheet = sheet.worksheet(aba)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

def obter_todas_respostas():
    abas = ['Comercial', 'Técnica', 'ESG']
    frames = []
    for aba in abas:
        df = obter_df_resposta(aba)
        if not df.empty:
            df['Tipo'] = aba
            frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    else:
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
    salvar_df_em_planilha(aba, df)
    return aba, df

def salvar_df_em_planilha(aba, df):
    sheet = conectar_planilha(RESPOSTAS_ID)
    try:
        worksheet = sheet.worksheet(aba)
        worksheet.clear()
    except:
        worksheet = sheet.add_worksheet(title=aba, rows="1000", cols="50")
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())

def salvar_excel(tabela: dict):
    for aba, df in tabela.items():
        salvar_df_em_planilha(aba, df)

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

def wrap_col_names(df, width=25):
    df = df.copy()
    df.columns = ['\n'.join(textwrap.wrap(str(col), width=width)) for col in df.columns]
    return df

st.set_page_config("Scorecard de Fornecedores", layout="wide", initial_sidebar_state="expanded")

# ======================================
# CSS: Modo escuro total e campos custom dark By: Bruno Jeliel
# ======================================
st.markdown("""
    <style>
    body, .stApp {background: #111 !important; color: #fff !important;}
    section[data-testid="stSidebar"] {background: #181818 !important;color: #fff !important;}
    /* Input fields */
    input, textarea, select {
        background-color: #181818 !important;
        color: #fff !important;
    }
    /* Streamlit Selectbox/dropdown e opcionais, SIMULA SEMPRE ESCURO */
    div[data-baseweb="select"], div[data-baseweb="select"] * {
        background-color: #181818 !important;
        color: #fff !important;
        border-color: #FFD700 !important;
    }
    /* Placeholders nos selectbox */
    .css-1wa3eu0-placeholder, .css-14el2xx-placeholder, .css-1u9des2-indicatorSeparator {color: #ccc !important;}
    /* Itens marcados ou destacados */
    [role="option"] {color:#fff !important;background:#181818 !important;}
    .stSelectbox>div>div>div>div {color: #fff !important;}
    /* Botões Streamlit */
    .stButton>button, .stFormSubmitButton>button, .css-1x8cf1d, .stDownloadButton>button {
        background-color: #222 !important;
        border: 1.5px solid #FFD700 !important;
        color: #fff !important;
        font-weight: bold;
        border-radius:8px !important;
        padding:6px 20px !important;
    }
    .stButton>button:focus, .stButton>button:hover, .stFormSubmitButton>button:focus, .stFormSubmitButton>button:hover {
        background-color: #FFD700 !important;
        color: #222 !important;
    }
    /* Checkboxes & Radios no modo escuro */
    .stCheckbox>label, .stRadio>label, .stRadio>div>div, .stRadio>div {color:#fff !important;}
    .stRadio [data-baseweb="radio"] {background-color:#181818 !important;}
    /* Slider (barra e ponteiro) */
    .stSlider, .stSlider > div {color:#fff !important;}
    .stSlider [role="slider"] {background: #FFD700 !important;}
    .stSlider .css-14xtw13, .stSlider .css-1yycgk5 {background: #181818;}
    /* Scrollbar escuro */
    ::-webkit-scrollbar, ::-webkit-scrollbar-thumb {background: #222 !important;border-radius:6px;}
    /* DataFrame headers/células */
    .stDataFrame .css-1v9z3k5 {background: #222 !important;color: #FFD700 !important;font-weight: bold;}
    .stDataFrame .css-1qg05tj {color: #fff !important;background: #161616 !important;}
    /* Textos especiais */
    .stMarkdown, .stHeader, h1,h2,h3,h4,h5 {font-family: 'Montserrat', 'Arial', sans-serif !important;}
    /* Placeholders e help/erro */
    .st-curriculum {color:#FFD700 !important;}
    .stAlert, .css-1kyxreq, .st-cc, .css-vfskoc {background:#222 !important;color:#FFD700 !important;}
    </style>
""", unsafe_allow_html=True)

# LOGO CENTRALIZADO
col1, col2, col3, col4, col5 = st.columns([1,2,2,2,1])
with col3:
    st.image("MeliAwards.png", width=550)

st.markdown(""" <h1 style='text-align: center; color: white; font-family: Montserrat, Arial, sans-serif;'>Scorecard de Fornecedores<br></h1>
    """, unsafe_allow_html=True)
st.markdown("<h1 style='text-align: center; color: #FFD700;font-family: Montserrat, Arial, sans-serif;'>Programa - Meli Awards<br></h1>", unsafe_allow_html=True)

perguntas_ref = ler_perguntas(PERGUNTA_ARQUIVO)
acessos, categorias_df = carregar_acessos(ACESSOS_ARQUIVO)

if "email_logado" not in st.session_state:
    st.session_state.email_logado = ""
if "fornecedores_responsaveis" not in st.session_state:
    st.session_state.fornecedores_responsaveis = {}
if "pagina" not in st.session_state:
    st.session_state.pagina = "login"
if "admin_mode" not in st.session_state:
    st.session_state.admin_mode = False

# -------- Sidebar consistente + botão sair --------
with st.sidebar:
    if st.session_state.pagina == "login":
        st.title("Menu")
        st.info("Acesse e preencha o seu Scorecard")
    elif st.session_state.pagina == "admin":
        st.title("Painel Admin")
        st.info("Gerenciamento e relatórios")
        if st.button("Sair do Painel Admin") or st.button("Sair"):
            st.session_state.clear()
            st.rerun()
    else:
        st.title("Menu")
        pag = st.radio(
            "Navegação",
            ["Avaliar Fornecedores", "Prévia das Notas"],
            index=0 if st.session_state.pagina == "Avaliar Fornecedores" else 1
        )
        if pag == "Avaliar Fornecedores":
            st.session_state.pagina = "Avaliar Fornecedores"
        elif pag == "Prévia das Notas":
            st.session_state.pagina = "Resumo Final"
        st.write(f"**E-mail logado:** {st.session_state.email_logado}")
        if st.button("Sair"):
            st.session_state.clear()
            st.rerun()

# LOGIN
if st.session_state.pagina == "login":
    with st.form("login_form"):
        email = st.text_input("Seu e-mail corporativo").strip()
        admin_check = st.checkbox("Sou administrador")
        admin_password = None
        col_login1, col_login2 = st.columns([1,1])
        if admin_check:
            admin_password = st.text_input("Senha do Administrador", type="password")
        submitted_login = col_login1.form_submit_button("Entrar")
    if submitted_login:
        if admin_check:
            if admin_password == ADMIN_PASSWORD:
                st.session_state.admin_mode = True
                st.session_state.pagina = "admin"
                st.rerun()
            else:
                st.error("Senha de administrador incorreta!")
        else:
            tipos = get_opcoes_tipo(email, acessos)
            if not tipos:
                st.error("E-mail sem permissão cadastrada.")
                st.stop()
            st.session_state.email_logado = email
            st.session_state.fornecedores_responsaveis = {}
            st.session_state.pagina = "Avaliar Fornecedores"
            st.session_state.admin_mode = False
            st.rerun()

# Painel admin
if st.session_state.pagina == "admin":
    st.title("Painel Administrador")
    df_respostas = obter_todas_respostas()
    if df_respostas.empty:
        st.warning("Nenhuma avaliação registrada ainda.")
    else:
        st.info(f"Total de avaliações registradas: **{len(df_respostas)}**")
        tipo_data = df_respostas.groupby("Tipo").agg({"E-mail": "count"}).rename(columns={"E-mail": "Qtd. Avaliações"})
        st.bar_chart(tipo_data)
        fornecedor_data = df_respostas.groupby("Fornecedor").agg({"E-mail": "count"}).rename(columns={"E-mail": "Qtd. Avaliações"}).sort_values("Qtd. Avaliações", ascending=False)
        st.subheader("Avaliações por Fornecedor")
        st.bar_chart(fornecedor_data)
        ponderadas_cols = [col for col in df_respostas.columns if "PONDERADA" in col]
        medias_ponderadas = {}
        for forn in fornecedor_data.index:
            df_forn = df_respostas[df_respostas["Fornecedor"] == forn]
            vals = []
            for idx, row in df_forn.iterrows():
                total_pond = sum([row[col] for col in ponderadas_cols if col in row and pd.notnull(row[col])])
                vals.append(total_pond)
            if vals:
                medias_ponderadas[forn] = np.mean(vals)
        if medias_ponderadas:
            st.subheader("Média das Notas Ponderadas por Fornecedor")
            st.bar_chart(pd.DataFrame(medias_ponderadas.values(), index=medias_ponderadas.keys(), columns=["Média Ponderada"]))
        st.subheader("Todas as Avaliações")
        st.dataframe(df_respostas, use_container_width=True, hide_index=True)
        st.download_button('Baixar todas as avaliações (CSV)', df_respostas.to_csv(index=False).encode('utf-8'), file_name='todas_avaliacoes.csv', mime='text/csv')

# Avaliação
if st.session_state.email_logado != "" and st.session_state.pagina == "Avaliar Fornecedores":
    tipos = get_opcoes_tipo(st.session_state.email_logado, acessos)
    tipo = st.selectbox("Tipo de avaliação", tipos, key="tipo")
    categorias = get_opcoes_categorias(st.session_state.email_logado, tipo, acessos)
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
        if not checar_usuario(st.session_state.email_logado, tipo, categoria, acessos):
            st.error("Acesso negado! Verifique seu e-mail, categoria e tipo de avaliação.")
            st.stop()
        st.markdown("---")
        st.header(f"Avaliação {tipo} para {fornecedor_selecionado} ({categoria})")
        st.markdown("""
            <div style="font-size: 13px;">
                <span style="color:#999"><b>1</b> = Ruim &nbsp;&nbsp;&nbsp; <b>2</b> = Regular &nbsp;&nbsp;&nbsp; <b>3</b> = Bom</span>
            </div>""", unsafe_allow_html=True)
        perguntas = perguntas_ref.get(tipo.capitalize()) or perguntas_ref.get(tipo)
        if perguntas:
            df_respostas = obter_df_resposta(tipo.capitalize())
            ja_respondeu = False
            if not df_respostas.empty:
                mask = (
                    (df_respostas['E-mail'].str.lower() == st.session_state.email_logado.lower()) &
                    (df_respostas['Categoria'] == categoria) &
                    (df_respostas['Fornecedor'] == fornecedor_selecionado)
                )
                ja_respondeu = df_respostas[mask].shape[0] > 0
            if ja_respondeu:
                st.info("Você já respondeu esta avaliação para essa combinação de tipo, categoria e fornecedor. Só é permitido um envio por usuário.")
            else:
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
                            tipo, st.session_state.email_logado, categoria, fornecedor_selecionado, notas, perguntas
                        )
                        st.session_state.fornecedores_responsaveis.setdefault(tipo, []).append(fornecedor_selecionado)
                        salvar_excel({aba: df_atualizada})
                        st.success("Avaliação registrada com sucesso!")

# Prévia das Notas
if st.session_state.email_logado != "" and st.session_state.pagina == "Resumo Final":
    st.subheader("Resumo Final das Suas Avaliações")
    email = st.session_state.email_logado
    tipos = get_opcoes_tipo(email, acessos)
    mostrou_nota = False
    for tipo_avaliacao in tipos:
        perguntas_tipo = perguntas_ref.get(tipo_avaliacao.capitalize()) or perguntas_ref.get(tipo_avaliacao)
        if not perguntas_tipo:
            continue
        df_tipo = obter_df_resposta(tipo_avaliacao.capitalize())
        if df_tipo.empty or "E-mail" not in df_tipo.columns:
            continue
        mask_email = (df_tipo['E-mail'].str.lower() == email.lower())
        respostas_email = df_tipo[mask_email]
        if respostas_email.empty:
            continue
        mostrou_nota = True
        for idx, linha in respostas_email.iterrows():
            categoria_ = linha['Categoria']
            fornecedor_ = linha['Fornecedor']
            st.markdown(f"**[{tipo_avaliacao}] | {categoria_} | {fornecedor_}**")
            colunas_ponderadas = [q + " (PONDERADA)" for (q, _) in perguntas_tipo if (q + " (PONDERADA)") in linha]
            notas_ponderadas = [(q, linha[q + " (PONDERADA)"] if (q + " (PONDERADA)") in linha else None) for (q, _) in perguntas_tipo]
            soma_ponderada = sum([val for (q, val) in notas_ponderadas if pd.notnull(val)])
            df_show = pd.DataFrame({
                "Questão": [q for (q, _) in perguntas_tipo],
                "Nota Ponderada": [linha[q + " (PONDERADA)"] if (q + " (PONDERADA)") in linha else None for (q, _) in perguntas_tipo]
            })
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            st.markdown(f"**Resultado Final (Soma das Notas Ponderadas):** `{soma_ponderada:.2f}`")
            st.markdown("---")
    if not mostrou_nota:
        st.info("Você ainda não realizou nenhuma avaliação.")
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("Voltar para Avaliação"):
            st.session_state.pagina = "Avaliar Fornecedores"
            st.rerun()
    with col2:
        if st.button("Encerrar Avaliação"):
            st.session_state.clear()
            st.rerun()

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
            background: #222; border-radius: 18px; padding: 40px 36px 30px 36px;
            max-width: 97vw; width: 420px; text-align: center; box-shadow: 0 0 40px #0002;
            border: 1.5px solid #888;
            color: #fff;
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
    if st.form("sairfake").form_submit_button("sairfake", type="primary"):
        st.session_state.clear()
        st.rerun()