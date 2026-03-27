import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time

st.set_page_config(layout="wide", page_title="Acompanhamento de Equipe Call Center")

st.title("📊 Acompanhamento de Equipe de Call Center")

# --- Função para processar status que atravessam a meia-noite ---
def split_status_across_days(df):
    processed_data = []
    for index, row in df.iterrows():
        start_time = row['Start Time']
        end_time = row['End Time']

        # Certifica-se de que as colunas são datetime
        if not pd.api.types.is_datetime64_any_dtype(start_time):
            start_time = pd.to_datetime(start_time)
        if not pd.api.types.is_datetime64_any_dtype(end_time):
            end_time = pd.to_datetime(end_time)

        current_start = start_time
        while current_start.date() < end_time.date():
            # O status termina no final do dia atual
            end_of_day = datetime.combine(current_start.date(), time(23, 59, 59))
            processed_data.append({
                'Agente': row['Agente'],
                'Status': row['Status'],
                'Start Time': current_start,
                'End Time': end_of_day,
                'Tipo': row['Tipo'] # Adiciona o tipo para diferenciar real/escala
            })
            # O status continua no início do próximo dia
            current_start = datetime.combine(current_start.date() + timedelta(days=1), time(0, 0, 0))

        # Adiciona a parte final do status (ou o status completo se não atravessou dias)
        processed_data.append({
            'Agente': row['Agente'],
            'Status': row['Status'],
            'Start Time': current_start,
            'End Time': end_time,
            'Tipo': row['Tipo']
        })
    return pd.DataFrame(processed_data)

# --- Seção de Upload do Relatório ---
st.header("1. Upload do Relatório de Status")
uploaded_file = st.file_uploader("Escolha um arquivo CSV ou Excel", type=["csv", "xlsx"])

df_real_status = pd.DataFrame()
if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df_real_status = pd.read_csv(uploaded_file)
        else:
            df_real_status = pd.read_excel(uploaded_file)

        st.success("Relatório carregado com sucesso!")
        st.subheader("Prévia do Relatório Carregado:")
        st.dataframe(df_real_status.head())

        # Assumindo que o relatório tem colunas como 'Agente', 'Status', 'Inicio', 'Fim'
        # Adapte os nomes das colunas conforme o seu relatório real
        required_cols = ['Agente', 'Status', 'Inicio', 'Fim'] # Exemplo, ajuste conforme seu anexo
        if all(col in df_real_status.columns for col in required_cols):
            df_real_status = df_real_status.rename(columns={
                'Inicio': 'Start Time', 
                'Fim': 'End Time'
            })
            df_real_status['Start Time'] = pd.to_datetime(df_real_status['Start Time'])
            df_real_status['End Time'] = pd.to_datetime(df_real_status['End Time'])
            df_real_status['Tipo'] = 'Real' # Adiciona uma coluna para diferenciar

            # Aplica a função de divisão de status
            df_real_status = split_status_across_days(df_real_status)

            st.session_state['df_real_status'] = df_real_status
            st.success("Dados do relatório processados e prontos para visualização.")
        else:
            st.error(f"O relatório deve conter as colunas: {', '.join(required_cols)}. Por favor, verifique o arquivo.")
            st.session_state['df_real_status'] = pd.DataFrame() # Limpa o estado se houver erro
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        st.session_state['df_real_status'] = pd.DataFrame()
else:
    st.info("Por favor, faça o upload de um relatório para começar.")

# --- Seção de Criação/Edição da Escala ---
st.header("2. Criar/Editar Escala de Agentes")

# Inicializa a escala no session_state se não existir
if 'df_escala' not in st.session_state:
    st.session_state['df_escala'] = pd.DataFrame(columns=['Agente', 'Dia', 'Inicio', 'Fim', 'Status', 'Tipo'])

# Obter lista de agentes do relatório ou permitir adicionar manualmente
agentes_disponiveis = []
if 'df_real_status' in st.session_state and not st.session_state['df_real_status'].empty:
    agentes_disponiveis = st.session_state['df_real_status']['Agente'].unique().tolist()

# Interface para adicionar um novo item à escala
with st.expander("Adicionar item à escala"):
    col1, col2 = st.columns(2)
    with col1:
        agente_selecionado = st.selectbox("Agente", [''] + agentes_disponiveis, key="escala_agente_select")
        novo_dia = st.date_input("Dia", datetime.now().date(), key="escala_dia")
        novo_status_escala = st.text_input("Status da Escala (ex: Trabalho, Pausa, Almoço)", "Trabalho", key="escala_status")
    with col2:
        novo_inicio = st.time_input("Início", time(9, 0), key="escala_inicio")
        novo_fim = st.time_input("Fim", time(17, 0), key="escala_fim")

    if st.button("Adicionar à Escala"):
        if agente_selecionado and novo_dia and novo_inicio and novo_fim and novo_status_escala:
            # Combina data e hora para criar datetime objects
            start_dt = datetime.combine(novo_dia, novo_inicio)
            end_dt = datetime.combine(novo_dia, novo_fim)

            if end_dt <= start_dt:
                st.warning("A hora de fim deve ser posterior à hora de início.")
            else:
                nova_linha = pd.DataFrame([{
                    'Agente': agente_selecionado,
                    'Dia': novo_dia,
                    'Inicio': start_dt,
                    'Fim': end_dt,
                    'Status': novo_status_escala,
                    'Tipo': 'Escala'
                }])
                st.session_state['df_escala'] = pd.concat([st.session_state['df_escala'], nova_linha], ignore_index=True)
                st.success(f"Item adicionado à escala para {agente_selecionado}.")
        else:
            st.warning("Por favor, preencha todos os campos para adicionar à escala.")

st.subheader("Escala Atual:")
if not st.session_state['df_escala'].empty:
    # Exibe a escala e permite edição/exclusão
    st.dataframe(st.session_state['df_escala'].drop(columns=['Tipo']).sort_values(by=['Agente', 'Dia', 'Inicio']), use_container_width=True)

    # Opção para limpar a escala
    if st.button("Limpar Escala"):
        st.session_state['df_escala'] = pd.DataFrame(columns=['Agente', 'Dia', 'Inicio', 'Fim', 'Status', 'Tipo'])
        st.success("Escala limpa.")
else:
    st.info("Nenhum item na escala ainda. Adicione acima.")

# --- Seção de Visualização Gantt ---
st.header("3. Visualização Gantt de Acompanhamento")

df_combinado = pd.DataFrame()
if 'df_real_status' in st.session_state and not st.session_state['df_real_status'].empty:
    # Prepara df_escala para combinação
    df_escala_temp = st.session_state['df_escala'].copy()
    if not df_escala_temp.empty:
        df_escala_temp = df_escala_temp.rename(columns={'Inicio': 'Start Time', 'Fim': 'End Time'})
        # Aplica a função de divisão de status também para a escala
        df_escala_temp = split_status_across_days(df_escala_temp)
        df_combinado = pd.concat([st.session_state['df_real_status'], df_escala_temp], ignore_index=True)
    else:
        df_combinado = st.session_state['df_real_status'].copy()

    if not df_combinado.empty:
        # --- Filtros ---
        st.subheader("Filtros")
        col_filtros1, col_filtros2, col_filtros3 = st.columns(3)

        with col_filtros1:
            todos_agentes = ['Todos'] + df_combinado['Agente'].unique().tolist()
            filtro_agente = st.selectbox("Filtrar por Agente", todos_agentes)

        with col_filtros2:
            min_date = df_combinado['Start Time'].min().date() if not df_combinado.empty else datetime.now().date()
            max_date = df_combinado['End Time'].max().date() if not df_combinado.empty else datetime.now().date()
            filtro_data_inicio = st.date_input("Data Início", min_date)
            filtro_data_fim = st.date_input("Data Fim", max_date)

        with col_filtros3:
            # Para grupos, você precisaria de uma coluna 'Grupo' no seu relatório ou escala.
            # Por enquanto, vamos simular ou deixar como um placeholder.
            # Se você tiver uma coluna 'Grupo' no seu df_combinado, pode usá-la aqui.
            # Exemplo: grupos_disponiveis = ['Todos'] + df_combinado['Grupo'].unique().tolist()
            # filtro_grupo = st.selectbox("Filtrar por Grupo", grupos_disponiveis)
            st.info("Funcionalidade de filtro por grupo requer uma coluna 'Grupo' nos dados.")
            filtro_grupo = 'Todos' # Placeholder

        df_filtrado = df_combinado.copy()

        # Aplicar filtro de agente
        if filtro_agente != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['Agente'] == filtro_agente]

        # Aplicar filtro de data
        df_filtrado = df_filtrado[
            (df_filtrado['Start Time'].dt.date >= filtro_data_inicio) &
            (df_filtrado['End Time'].dt.date <= filtro_data_fim)
        ]

        # Aplicar filtro de grupo (se implementado)
        # if filtro_grupo != 'Todos' and 'Grupo' in df_filtrado.columns:
        #     df_filtrado = df_filtrado[df_filtrado['Grupo'] == filtro_grupo]

        if not df_filtrado.empty:
            # Ordenar para melhor visualização
            df_filtrado = df_filtrado.sort_values(by=['Agente', 'Start Time'])

            # Criação do gráfico Gantt
            # Usamos 'Tipo' (Real/Escala) para colorir e diferenciar
            fig = px.timeline(
                df_filtrado, 
                x_start="Start Time", 
                x_end="End Time", 
                y="Agente", 
                color="Tipo", # Colore por 'Real' ou 'Escala'
                text="Status", # Mostra o status no gráfico
                hover_name="Status", # Nome ao passar o mouse
                hover_data={"Start Time": "|%Y-%m-%d %H:%M", "End Time": "|%Y-%m-%d %H:%M", "Tipo": True},
                title="Comparativo de Escala vs. Status Real",
                color_discrete_map={'Real': 'blue', 'Escala': 'green'} # Cores personalizadas
            )

            fig.update_yaxes(autorange="reversed") # Agentes em ordem normal
            fig.update_layout(
                xaxis_title="Tempo",
                yaxis_title="Agente",
                hovermode="x unified",
                height=600 # Altura do gráfico
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Nenhum dado encontrado com os filtros aplicados.")
    else:
        st.info("Faça o upload de um relatório e/ou crie uma escala para visualizar o gráfico.")
else:
    st.info("Faça o upload de um relatório para visualizar o gráfico.")

st.markdown("---")
st.markdown("Desenvolvido com Streamlit")
