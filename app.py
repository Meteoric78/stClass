import secrets

import streamlit as st
from st_supabase_connection import SupabaseConnection

st.set_page_config(page_title="Biblioteca", page_icon="📚")

conn = st.connection("supabase", type=SupabaseConnection)


# ---------- Acesso a dados ----------

def get_leitores():
    return conn.table("leitor").select("*").order("nome_leitor").execute().data


def get_livros():
    return conn.table("livro").select("*").order("titulo_livro").execute().data


def get_operacoes():
    return conn.table("operacoes").select("*").execute().data


def codigos_devolvidos(operacoes):
    return {op["codigo"] for op in operacoes if op["tipo_operacao"] == "devolucao"}


def emprestimos_abertos(operacoes):
    devolvidos = codigos_devolvidos(operacoes)
    return [
        op for op in operacoes
        if op["tipo_operacao"] == "emprestimo" and op["codigo"] not in devolvidos
    ]


def livros_disponiveis(livros, operacoes):
    ids_emprestados = {op["id_livro"] for op in emprestimos_abertos(operacoes)}
    return [l for l in livros if l["id_livro"] not in ids_emprestados]


def gerar_codigo():
    return secrets.token_hex(3).upper()


# ---------- Acesso do bibliotecário ----------
# Chave única e compartilhada, guardada em secrets.toml — não é um sistema
# de contas de usuário, apenas um portão simples para separar a página
# pública da interface de empréstimo/devolução.

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

with st.sidebar:
    st.subheader("Acesso do bibliotecário")
    if st.session_state.autenticado:
        st.success("Acesso liberado.")
        if st.button("Sair"):
            st.session_state.autenticado = False
            st.rerun()
    else:
        chave_input = st.text_input("Chave de acesso", type="password")
        if st.button("Entrar"):
            chave_correta = st.secrets.get("CHAVE_BIBLIOTECARIO", "")
            if chave_input and chave_input == chave_correta:
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("Chave incorreta.")


# ---------- App ----------

st.title("📚 Biblioteca")

livros = get_livros()
operacoes = get_operacoes()
disponiveis = livros_disponiveis(livros, operacoes)

if not st.session_state.autenticado:
    # ===================== Página pública =====================
    st.subheader("📊 Estatísticas")
    col1, col2 = st.columns(2)
    col1.metric("Livros no acervo", len(livros))
    col2.metric("Disponíveis agora", len(disponiveis))
    # Adicione outras estatísticas aqui quando definir quais fazem sentido
    # (ex.: total de empréstimos no mês) — nenhuma delas deve expor nomes
    # de leitores nesta página pública.

    st.subheader("📖 Livros disponíveis")
    if not disponiveis:
        st.info("Nenhum livro disponível no momento.")
    else:
        for l in disponiveis:
            st.write(f"**{l['titulo_livro']}** — {l['autor_livro']}")

else:
    # ================= Interface do bibliotecário =================
    leitores = get_leitores()
    livro_by_id = {l["id_livro"]: l for l in livros}
    leitor_by_id = {l["id_leitor"]: l for l in leitores}

    tab_emprestimo, tab_devolucao = st.tabs(["Emprestar livro", "Devolver livro"])

    # ----- Empréstimo -----
    with tab_emprestimo:
        st.subheader("Novo empréstimo")

        with st.expander("Leitor não está na lista? Cadastre aqui"):
            novo_nome = st.text_input("Nome do novo leitor", key="novo_leitor_input")
            if st.button("Cadastrar leitor"):
                nome_limpo = novo_nome.strip()
                if nome_limpo:
                    conn.table("leitor").insert({"nome_leitor": nome_limpo}).execute()
                    st.success(f"Leitor '{nome_limpo}' cadastrado. Selecione-o abaixo.")
                    st.rerun()
                else:
                    st.warning("Digite um nome.")

        if not disponiveis:
            st.info("Nenhum livro disponível no momento.")
        else:
            with st.form("form_emprestimo", clear_on_submit=True):
                livro_opcoes = {
                    f"{l['titulo_livro']} — {l['autor_livro']}": l["id_livro"]
                    for l in disponiveis
                }
                livro_escolhido = st.selectbox("Livro", options=list(livro_opcoes.keys()))

                leitor_opcoes = {l["nome_leitor"]: l["id_leitor"] for l in leitores}
                nomes = ["— selecione —"] + list(leitor_opcoes.keys())
                leitor_escolhido = st.selectbox("Leitor", options=nomes)

                enviar = st.form_submit_button("Registrar empréstimo")

            if enviar:
                if leitor_escolhido == "— selecione —":
                    st.error("Selecione um leitor.")
                else:
                    codigo = gerar_codigo()
                    conn.table("operacoes").insert({
                        "codigo": codigo,
                        "id_livro": livro_opcoes[livro_escolhido],
                        "id_leitor": leitor_opcoes[leitor_escolhido],
                        "tipo_operacao": "emprestimo",
                    }).execute()
                    st.success(
                        f"Empréstimo registrado! Código: **{codigo}** "
                        "— anote para a devolução."
                    )
                    st.rerun()

    # ----- Devolução -----
    with tab_devolucao:
        st.subheader("Devolver livro")

        abertos = emprestimos_abertos(operacoes)

        metodo = st.radio(
            "Como deseja identificar o empréstimo?",
            ["Tenho o código", "Não tenho o código"],
        )

        if metodo == "Tenho o código":
            with st.form("form_devolucao_codigo", clear_on_submit=True):
                codigo_input = st.text_input("Código do empréstimo")
                enviar_dev = st.form_submit_button("Registrar devolução")

            if enviar_dev:
                codigo_normalizado = codigo_input.strip().upper()
                correspondente = next(
                    (op for op in abertos if op["codigo"] == codigo_normalizado), None
                )
                if not correspondente:
                    st.error("Código não encontrado ou já devolvido.")
                else:
                    conn.table("operacoes").insert({
                        "codigo": correspondente["codigo"],
                        "id_livro": correspondente["id_livro"],
                        "id_leitor": correspondente["id_leitor"],
                        "tipo_operacao": "devolucao",
                    }).execute()
                    st.success("Devolução registrada!")
                    st.rerun()

        else:
            if not abertos:
                st.info("Não há empréstimos em aberto.")
            else:
                opcoes = {
                    f"{livro_by_id[op['id_livro']]['titulo_livro']} — "
                    f"{leitor_by_id[op['id_leitor']]['nome_leitor']} ({op['codigo']})": op
                    for op in abertos
                }
                escolhido = st.selectbox("Empréstimo em aberto", options=list(opcoes.keys()))
                if st.button("Registrar devolução", key="dev_sem_codigo"):
                    op = opcoes[escolhido]
                    conn.table("operacoes").insert({
                        "codigo": op["codigo"],
                        "id_livro": op["id_livro"],
                        "id_leitor": op["id_leitor"],
                        "tipo_operacao": "devolucao",
                    }).execute()
                    st.success("Devolução registrada!")
                    st.rerun()

    # ----- Visão do bibliotecário (dados de leitores ficam só aqui) -----
    st.divider()
    with st.expander("📋 Empréstimos em aberto"):
        abertos = emprestimos_abertos(operacoes)
        if not abertos:
            st.write("Nenhum empréstimo em aberto.")
        else:
            for op in abertos:
                livro = livro_by_id.get(op["id_livro"], {})
                leitor = leitor_by_id.get(op["id_leitor"], {})
                st.write(
                    f"**{op['codigo']}** — {livro.get('titulo_livro', '?')} — "
                    f"{leitor.get('nome_leitor', '?')} — desde {op['data_operacao']}"
                )
