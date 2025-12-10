import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import textwrap
import numpy as np
from gspread.exceptions import APIError, WorksheetNotFound  # <-- import extra

# IDs das planilhas compartilhadas no Google Sheets
PERGUNTAS_ID = "1-mlYet1m6pN510WN8V-6XEJyDovXdlQN0TLzlr0WcPY"
ACESSOS_ID = "1p5bzFBwAOAisFZLlt3lqXjDPJG-GfL2xkkm3fxQhQRU"
RESPOSTAS_ID = "1OKhItXlUwmYGGIVBpNIO_48Hsb5wIRZlZ6a8p_ZbheA"
ADMIN_PASSWORD = "admin123"

# Escala de notas para Comercial, Técnica e ESG
NOTAS_COM_TEC = [1.0, 1.3, 1.5, 1.7, 2.0, 2.3, 2.5, 2.7, 3.0]

# --------------------------------------------------------------------------------
# Funções utilitárias de formatação numérica
# --------------------------------------------------------------------------------
def to_number(value):
    """Converte textos como '2,7' ou '2.7' para float 2.7; vazio -> NaN."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    s = str(value).strip()
    if s == "":
        return np.nan
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return np.nan

# OBS: vamos parar de mandar texto com vírgula para o Sheets.
# Em vez disso, manteremos os valores como float e deixaremos o formato (vírgula)
# ser controlado pelo próprio Google Sheets (formatação de célula).
def format_float_with_comma(value, ndigits=1):
    """MANTIDA para eventual uso interno, mas não será usada ao gravar no Sheets."""
    try:
        f = float(value)
    except Exception:
        return value
    s = f"{f:.{ndigits}f}"
    return s.replace(".", ",")

def format_df_notes_with_comma(df, pergunta_cols, ponderada_cols, ndigits=1):
    """NÃO usaremos mais ao enviar ao Sheets, mantida só se precisar exibir no app."""
    df = df.copy()
    for col in pergunta_cols + ponderada_cols:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: format_float_with_comma(x, ndigits))
    return df

# --------------------------------------------------------------------------------
# Mapeamento Tipo -> Nome da Aba na planilha de respostas
# --------------------------------------------------------------------------------
def mapear_tipo_para_aba(tipo: str) -> str:
    """
    Converte o tipo de avaliação no nome da aba da planilha de respostas.
    - "Comercial" -> "Comercial"
    - "Técnica"   -> "Técnica"
    - "ESG"       -> "Esg"  (aba já existente)
    """
    tipo_norm = (tipo or "").strip()
    if tipo_norm.lower() == "esg":
        return "Esg"  # nome da aba existente na planilha
    return tipo_norm  # para Comercial e Técnica segue igual

# --------------------------------------------------------------------------------
# Conexão com Google Sheets
# --------------------------------------------------------------------------------
def conectar_planilha(sheet_id):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gspread"], scope)
    client = gspread.authorize(creds)
    return client.open_by_key(sheet_id)

def ler_perguntas():
    tipos = ["Comercial", "Técnica", "ESG"]
    perguntas = {t: [] for t in tipos}
    sheet = conectar_planilha(PERGUNTAS_ID)
    worksheet = sheet.get_worksheet(0)
    df = pd.DataFrame(worksheet.get_all_records())
    for tipo in tipos:
        col_pergunta = tipo
        col_peso = f"Peso_{tipo}"
        if col_pergunta in df.columns and col_peso in df.columns:
            for _, linha in df.iterrows():
                pergunta = str(linha[col_pergunta]).strip()
                try:
                    peso = float(str(linha[col_peso]).replace(",", ".").replace("%", "").strip())
                except Exception:
                    peso = 0
                if pergunta and pergunta.lower() != "nan" and peso > 0:
                    perguntas[tipo].append((pergunta, peso/100.0))
    return perguntas

def padronizar_colunas(df, todas_colunas):
    for col in todas_colunas:
        if col not in df.columns:
            df[col] = ""
    for col in list(df.columns):
        if col not in todas_colunas:
            df.drop(columns=[col], inplace=True)
    return df[todas_colunas]

def atualizar_em_blocos(worksheet, df, colunas_perguntas, colunas_ponderada, bloco=500):
    """
    Envia o DataFrame ao Sheets em blocos, com:
    - cabeçalhos na primeira linha
    - notas puras e ponderadas como FLOAT (não texto)
    - value_input_option="RAW".
    O formato (vírgula/ponto) deve ser ajustado no próprio Google Sheets
    via formatação de célula.
    """
    df_envio = df.copy()
    headers = [df_envio.columns.tolist()]
    data = df_envio.values.tolist()
    worksheet.clear()
    for i in range(0, len(data), bloco):
        chunk = data[i:i+bloco]
        worksheet.append_rows(headers + chunk if i == 0 else chunk, value_input_option="RAW")

def carregar_acessos():
    sheet = conectar_planilha(ACESSOS_ID)
    acessos = pd.DataFrame(sheet.worksheet("Acessos").get_all_records())
    categorias = pd.DataFrame(sheet.worksheet("Categorias").get_all_records())
    return acessos, categorias

def obter_df_resposta(aba_ou_tipo):
    """
    Recebe um nome de aba ou tipo ("Comercial", "Técnica", "ESG")
    e sempre converte para o nome real da aba usando mapear_tipo_para_aba.
    Converte colunas de notas em float internamente.
    """
    sheet = conectar_planilha(RESPOSTAS_ID)
    aba_real = mapear_tipo_para_aba(aba_ou_tipo)
    try:
        worksheet = sheet.worksheet(aba_real)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            return df
        # Converter colunas de notas para float interno
        for col in df.columns:
            if col not in ["Data", "Hora", "E-mail", "Categoria", "Fornecedor", "Tipo"]:
                df[col] = df[col].apply(to_number)
        return df
    except:
        return pd.DataFrame()

def obter_todas_respostas():
    # Tipos lógicos
    tipos_logicos = ['Comercial', 'Técnica', 'ESG']
    frames = []
    for tipo in tipos_logicos:
        df = obter_df_resposta(tipo)  # internamente mapeia ESG -> Esg
        if not df.empty:
            df['Tipo'] = tipo  # mantemos o rótulo lógico "ESG"
            frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    else:
        return pd.DataFrame()

def salvar_resposta_ponderada(tipo, email, categoria, fornecedor, respostas, perguntas):
    hoje = datetime.now()
    data_str = hoje.strftime("%d/%m/%Y")
    hora_str = hoje.strftime("%H:%M:%S")
    aba = mapear_tipo_para_aba(tipo)

    df = obter_df_resposta(aba)
    colunas_fixas = ["Data", "Hora", "E-mail", "Categoria", "Fornecedor"]
    colunas_perguntas = [q for (q, p) in perguntas]
    colunas_ponderada = [q + " (PONDERADA)" for (q, p) in perguntas]
    todas_colunas = colunas_fixas + colunas_perguntas + colunas_ponderada

    notas_puras = []
    notas_ponderadas = []
    for (pergunta, peso) in perguntas:
        nota = to_number(respostas[pergunta])  # slider -> float
        notas_puras.append(nota)
        ponderada = nota * peso if nota is not None else np.nan
        notas_ponderadas.append(ponderada)

    nova_linha = [data_str, hora_str, email, categoria, fornecedor] + notas_puras + notas_ponderadas
    nova_df = pd.DataFrame([nova_linha], columns=todas_colunas)

    if not df.empty:
        df = padronizar_colunas(df, todas_colunas)
        nova_df = padronizar_colunas(nova_df, todas_colunas)
        mask = (df['E-mail'].astype(str).str.lower() == email.lower()) & \
               (df['Categoria'] == categoria) & \
               (df['Fornecedor'] == fornecedor)
        df = df[~mask]
        df = pd.concat([df, nova_df], ignore_index=True)
    else:
        df = nova_df

    salvar_df_em_planilha(aba, df, colunas_perguntas, colunas_ponderada)
    return aba, df

def salvar_df_em_planilha(aba, df, colunas_perguntas, colunas_ponderada):
    sheet = conectar_planilha(RESPOSTAS_ID)

    # Tentar obter a worksheet, se não existir criar
    try:
        worksheet = sheet.worksheet(aba)
    except WorksheetNotFound:
        try:
            linhas = max(len(df), 1)
            colunas = max(len(df.columns), 1)
            worksheet = sheet.add_worksheet(
                title=aba,
                rows=str(linhas),
                cols=str(colunas)
            )
        except APIError as e:
            st.error(
                "Não foi possível criar a aba no Google Sheets. "
                "Possíveis causas:\n"
                "- O nome da aba já existe ou é inválido;\n"
                "- A planilha atingiu o limite de abas;\n"
                "- O usuário de serviço não tem permissão de edição.\n\n"
                "Entre em contato com o administrador do sistema."
            )
            st.write("Detalhes técnicos (para o administrador):", str(e))
            raise
    except APIError as e:
        st.error(
            "Erro ao acessar a aba de respostas no Google Sheets. "
            "Tente novamente em alguns instantes. Se o problema persistir, "
            "entre em contato com o administrador."
        )
        st.write("Detalhes técnicos (para o administrador):", str(e))
        raise

    # Se chegou aqui, temos uma worksheet válida
    atualizar_em_blocos(worksheet, df, colunas_perguntas, colunas_ponderada)

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

# --------------------------------------------------------------------------------
# Configuração de página e CSS
# --------------------------------------------------------------------------------
st.set_page_config("Scorecard de Fornecedores", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    body, .stApp {background: #111 !important; color: #fff !important;}
    section[data-testid="stSidebar"] {background: #181818 !important;color: #fff !important;}
    input, textarea, select { background-color: #181818 !important; color: #fff !important; }
    div[data-baseweb="select"], div[data-baseweb="select"] * { background-color: #181818 !important; color: #fff !important; border-color: #FFD700 !important; }
    .css-1wa3eu0-placeholder, .css-14el2xx-placeholder, .css-1u9des2-indicatorSeparator {color: #ccc !important;}
    [role="option"] {color:#fff !important;background:#181818 !important;}
    .stSelectbox>div>div>div>div {color: #fff !important;}
    .stButton>button, .stFormSubmitButton>button, .stDownloadButton>button {
        background-color: #222 !important; border: 1.5px solid #FFD700 !important; color: #fff !important; font-weight: bold; border-radius:8px !important; padding:6px 20px !important;
    }
    .stButton>button:focus, .stButton>button:hover, .stFormSubmitButton>button:focus, .stFormSubmitButton>button:hover { background-color: #FFD700 !important; color: #222 !important; }
    .stCheckbox>label, .stRadio>label, .stRadio>div>div, .stRadio>div {color:#fff !important;}
    .stRadio [data-baseweb="radio"] {background-color:#181818 !important;}
    .stSlider, .stSlider > div {color:#fff !important;}
    .stSlider [role="slider"] {background: #FFD700 !important;}
    .stSlider .css-14xtw13, .stSlider .css-1yycgk5 {background: #181818;}
    ::-webkit-scrollbar, ::-webkit-scrollbar-thumb {background: #222 !important;border-radius:6px;}
    .stDataFrame .css-1v9z3k5 {background: #222 !important;color: #FFD700 !important;font-weight: bold;}
    .stDataFrame .css-1qg05tj {color: #fff !important;background: #161616 !important;}
    .stMarkdown, .stHeader, h1,h2,h3,h4,h5 {font-family: 'Montserrat', 'Arial', sans-serif !important;}
    .stAlert {background:#222 !important;color:#FFD700 !important;}
    .nota-scale { display: flex; justify-content: space-between; margin-top: 6px; margin-bottom: 10px; font-size: 12px; color: #bbb; font-family: 'Montserrat', 'Arial', sans-serif; }
    .nota-scale span { min-width: 16px; text-align: center; }
    </style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------------
# Logo e Títulos
# --------------------------------------------------------------------------------
col1, col2, col3, col4, col5 = st.columns([1,2,2,2,1])
with col3:
    st.image("MeliAwards.png", width=550)

st.markdown(""" <h1 style='text-align: center; color: white; font-family: Montserrat, Arial, sans-serif;'>Scorecard de Fornecedores<br></h1>""", unsafe_allow_html=True)
st.markdown("<h1 style='text-align: center; color: #FFD700;font-family: Montserrat, Arial, sans-serif;'>Programa - Meli Awards<br></h1>", unsafe_allow_html=True)

# --------------------------------------------------------------------------------
# Estado de sessão
# --------------------------------------------------------------------------------
perguntas_ref = ler_perguntas()
acessos, categorias_df = carregar_acessos()

if "email_logado" not in st.session_state:
    st.session_state.email_logado = ""
if "fornecedores_responsaveis" not in st.session_state:
    st.session_state.fornecedores_responsaveis = {}
if "pagina" not in st.session_state:
    st.session_state.pagina = "login"
if "admin_mode" not in st.session_state:
    st.session_state.admin_mode = False

# --------------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------------
with st.sidebar:
    if st.session_state.pagina == "login":
        st.title("Menu")
        st.info("Acesse e preencha o seu Scorecard")
    elif st.session_state.pagina == "admin" and st.session_state.admin_mode:
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

# --------------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------------
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

# --------------------------------------------------------------------------------
# Painel Admin (SOMENTE quando admin_mode True e pagina == "admin")
# --------------------------------------------------------------------------------
if st.session_state.pagina == "admin" and st.session_state.admin_mode:
    st.title("Painel Administrador")

    df_respostas = obter_todas_respostas()

    if df_respostas.empty:
        st.warning("Nenhuma avaliação registrada ainda.")
    else:
        st.info(f"Total de registros de avaliações: {len(df_respostas)}")

        pesos_map = {}
        for tipo_nome, lista_q in perguntas_ref.items():
            pesos_map[tipo_nome] = {q: float(p) for (q, p) in lista_q}

        def _to_float(x):
            return to_number(x)

        def recalc_total_por_linha(row):
            tipo = str(row.get("Tipo", "")).strip()
            pesos = pesos_map.get(tipo, {})
            total = 0.0
            for q, w in pesos.items():
                if q in row:
                    v = _to_float(row[q])
                    if pd.notnull(v):
                        total += v * w
            return total

        df_respostas["Total Ponderado (recalc)"] = df_respostas.apply(recalc_total_por_linha, axis=1)

        # Top 3
        st.subheader("Top 3 Fornecedores por Categoria (Nota Final = (Comercial + Técnica + ESG) / 3)")
        req_cols_top3 = ["Categoria", "Fornecedor", "Tipo", "Total Ponderado (recalc)"]
        faltando_top3 = [c for c in req_cols_top3 if c not in df_respostas.columns]
        if faltando_top3:
            st.error(f"Colunas ausentes para o Top 3: {faltando_top3}")
        else:
            base = df_respostas[req_cols_top3].dropna(subset=["Categoria", "Fornecedor", "Tipo"]).copy()
            base["Tipo"] = base["Tipo"].astype(str).str.strip()
            tipo_media = (
                base.groupby(["Categoria", "Fornecedor", "Tipo"], as_index=False)["Total Ponderado (recalc)"]
                .mean()
                .rename(columns={"Total Ponderado (recalc)": "Média por Tipo"})
            )
            pivot = (
                tipo_media
                .pivot_table(index=["Categoria", "Fornecedor"], columns="Tipo", values="Média por Tipo", aggfunc="first")
                .reset_index()
            )
            for t in ["Comercial", "Técnica", "ESG"]:
                if t not in pivot.columns:
                    pivot[t] = 0.0
            pivot["Nota Final"] = (pivot["Comercial"].fillna(0) + pivot["Técnica"].fillna(0) + pivot["ESG"].fillna(0)) / 3.0
            top3_list = []
            for categoria_val, dfcat in pivot.groupby("Categoria", dropna=False):
                top = (
                    dfcat.sort_values("Nota Final", ascending=False)
                    .head(3)[["Categoria", "Fornecedor", "Comercial", "Técnica", "ESG", "Nota Final"]]
                )
                top3_list.append(top)
            if top3_list:
                df_top3 = pd.concat(top3_list, ignore_index=True)
                st.dataframe(df_top3, use_container_width=True, hide_index=True)
                st.download_button(
                    "Baixar Top 3 por Categoria (CSV)",
                    df_top3.to_csv(index=False).encode("utf-8"),
                    file_name="top3_por_categoria.csv",
                    mime="text/csv",
                )
            else:
                st.info("Sem dados suficientes para calcular Top 3 por categoria.")

        # Contagem completas/incompletas
        st.subheader("Contagem de Avaliações Completas e Incompletas por E-mail, Categoria e Tipo")

        req_cols_cnt = ["E-mail", "Categoria", "Fornecedor", "Tipo"]
        faltando_cnt = [c for c in req_cols_cnt if c not in df_respostas.columns]
        if faltando_cnt:
            st.error(f"Colunas ausentes para esta contagem: {faltando_cnt}")
        else:
            questoes_map = {tipo: [q for (q, _) in lista] for tipo, lista in perguntas_ref.items()}

            def conta_respondidas(row):
                tipo = str(row.get("Tipo", "")).strip()
                qs = questoes_map.get(tipo, [])
                respondidas = 0
                for q in qs:
                    if q in row:
                        val = row[q]
                        if pd.notnull(val) and str(val).strip() != "":
                            respondidas += 1
                return pd.Series({"Respondidas": respondidas, "TotalPerguntas": len(qs)})

            tmp = df_respostas.copy()
            aux = tmp.apply(conta_respondidas, axis=1)
            tmp["Respondidas"] = aux["Respondidas"]
            tmp["TotalPerguntas"] = aux["TotalPerguntas"]
            tmp["Completa?"] = (tmp["TotalPerguntas"] > 0) & (tmp["Respondidas"] == tmp["TotalPerguntas"])

            completos = (
                tmp[tmp["Completa?"]]
                .groupby(["E-mail", "Categoria", "Tipo"], as_index=False)["Fornecedor"]
                .nunique()
                .rename(columns={"Fornecedor": "Completas"})
            )
            incompletos = (
                tmp[~tmp["Completa?"]]
                .groupby(["E-mail", "Categoria", "Tipo"], as_index=False)["Fornecedor"]
                .nunique()
                .rename(columns={"Fornecedor": "Incompletas"})
            )

            contagem = pd.merge(completos, incompletos, on=["E-mail", "Categoria", "Tipo"], how="outer").fillna(0)
            for c in ["Completas", "Incompletas"]:
                contagem[c] = contagem[c].astype(int)
            contagem["Total Fornecedores Avaliados"] = contagem["Completas"] + contagem["Incompletas"]

            if contagem.empty:
                st.info("Nenhuma avaliação encontrada para compor a contagem.")
            else:
                st.dataframe(contagem.sort_values(["E-mail", "Categoria", "Tipo"]), use_container_width=True, hide_index=True)
                st.download_button(
                    "Baixar Contagem (CSV)",
                    contagem.to_csv(index=False).encode("utf-8"),
                    file_name="contagem_completas_incompletas_por_email_categoria_tipo.csv",
                    mime="text/csv",
                )

            st.markdown("Detalhes das avaliações incompletas (por fornecedor):")
            detalhes_incomp = tmp[~tmp["Completa?"]][
                ["E-mail", "Categoria", "Tipo", "Fornecedor", "Respondidas", "TotalPerguntas"]
            ].copy()
            if detalhes_incomp.empty:
                st.info("Sem avaliações incompletas.")
            else:
                st.dataframe(detalhes_incomp.sort_values(["E-mail", "Categoria", "Tipo", "Fornecedor"]),
                             use_container_width=True, hide_index=True)
                st.download_button(
                    "Baixar Detalhes Incompletas (CSV)",
                    detalhes_incomp.to_csv(index=False).encode("utf-8"),
                    file_name="detalhes_avaliacoes_incompletas.csv",
                    mime="text/csv",
                )

        # Tabelas por tipo
        st.subheader("Todas as Avaliações por Tipo")
        abas = st.tabs(["Comercial", "Técnica", "ESG"])
        tipos_ordem = ["Comercial", "Técnica", "ESG"]

        for aba_st, tipo_t in zip(abas, tipos_ordem):
            with aba_st:
                dft = df_respostas[df_respostas["Tipo"] == tipo_t]
                if dft.empty:
                    st.info(f"Sem avaliações do tipo {tipo_t}.")
                else:
                    st.dataframe(dft, use_container_width=True, hide_index=True)
                    st.download_button(
                        f"Baixar {tipo_t} (CSV)",
                        dft.to_csv(index=False).encode("utf-8"),
                        file_name=f"avaliacoes_{tipo_t.lower()}.csv",
                        mime="text/csv",
                    )

# --------------------------------------------------------------------------------
# Avaliação (público não-admin)
# --------------------------------------------------------------------------------
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

        # Legenda com a escala permitida
        escala_str = " • ".join([str(x).rstrip('0').rstrip('.') for x in NOTAS_COM_TEC])
        st.markdown(f"""
            <div style="font-size: 13px;">
                <span style="color:#999"><b>Escala permitida:</b> {escala_str} &nbsp;&nbsp;&nbsp; <b>1</b> = Ruim &nbsp;&nbsp; <b>3</b> = Bom</span>
            </div>""", unsafe_allow_html=True)

        perguntas = perguntas_ref.get(tipo)
        if perguntas is None or len(perguntas) == 0:
            st.error("Não foram encontradas perguntas para esse tipo de avaliação. Verifique a planilha de perguntas!")
            st.stop()
        else:
            df_respostas_tipo = obter_df_resposta(tipo)
            ja_respondeu = False
            if not df_respostas_tipo.empty:
                mask = (
                    (df_respostas_tipo['E-mail'].astype(str).str.lower() == st.session_state.email_logado.lower()) &
                    (df_respostas_tipo['Categoria'] == categoria) &
                    (df_respostas_tipo['Fornecedor'] == fornecedor_selecionado)
                )
                ja_respondeu = df_respostas_tipo[mask].shape[0] > 0
            if ja_respondeu:
                st.info("Você já respondeu esta avaliação para essa combinação de tipo, categoria e fornecedor. Só é permitido um envio por usuário.")
            else:
                with st.form("avaliacao"):
                    notas = {}
                    for idx, (pergunta, peso) in enumerate(perguntas, 1):
                        st.markdown(f"<b>{idx}. {pergunta} (Peso {peso*100:.0f}%)</b>", unsafe_allow_html=True)
                        notas[pergunta] = st.select_slider(
                            label="Selecione sua nota:",
                            options=NOTAS_COM_TEC,
                            value=2.0,
                            key=f"slider_{idx}_{pergunta}"
                        )
                        labels = [str(x).rstrip('0').rstrip('.') for x in NOTAS_COM_TEC]
                        labels_html = '<div class="nota-scale">' + ''.join([f'<span>{v}</span>' for v in labels]) + '</div>'
                        st.markdown(labels_html, unsafe_allow_html=True)

                    submitted = st.form_submit_button("Enviar avaliação")
                    if submitted:
                        aba, df_atualizada = salvar_resposta_ponderada(
                            tipo, st.session_state.email_logado, categoria, fornecedor_selecionado, notas, perguntas
                        )
                        st.session_state.fornecedores_responsaveis.setdefault(tipo, []).append(fornecedor_selecionado)
                        st.success("Avaliação registrada com sucesso!")

# --------------------------------------------------------------------------------
# Prévia das Notas (público não-admin)
# --------------------------------------------------------------------------------
if st.session_state.email_logado != "" and st.session_state.pagina == "Resumo Final":
    st.subheader("Resumo Final das Suas Avaliações")
    email = st.session_state.email_logado
    tipos = get_opcoes_tipo(email, acessos)
    mostrou_nota = False
    for tipo_avaliacao in tipos:
        perguntas_tipo = perguntas_ref.get(tipo_avaliacao)
        if not perguntas_tipo:
            continue
        df_tipo = obter_df_resposta(tipo_avaliacao)
        if df_tipo.empty or "E-mail" not in df_tipo.columns:
            continue
        mask_email = (df_tipo['E-mail'].astype(str).str.lower() == email.lower())
        respostas_email = df_tipo[mask_email]
        if respostas_email.empty:
            continue
        mostrou_nota = True
        for _, linha in respostas_email.iterrows():
            categoria_ = linha['Categoria']
            fornecedor_ = linha['Fornecedor']
            st.markdown(f"**[{tipo_avaliacao}] | {categoria_} | {fornecedor_}**")
            colunas_perguntas = [q for (q, _) in perguntas_tipo]
            df_show = pd.DataFrame({
                "Questão": [q for (q, _) in perguntas_tipo],
                "Nota Atribuída": [linha[q] if q in linha else None for q in colunas_perguntas]
            })
            st.dataframe(df_show, use_container_width=True, hide_index=True)
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

# --------------------------------------------------------------------------------
# Tela Final (modal)
# --------------------------------------------------------------------------------
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
