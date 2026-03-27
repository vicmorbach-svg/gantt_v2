import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time
import numpy as np

# --- Configurações Iniciais do Streamlit ---
st.set_page_config(layout="wide", page_title="Dashboard de Acompanhamento de Call Center")
st.title("Dashboard de Acompanhamento de Equipe de Call Center")

# --- Mapeamento de dias da semana para facilitar a comparação ---
dias_semana_map = {
    "Seg": "Monday", "Ter": "Tuesday", "Qua": "Wednesday",
    "Qui": "Thursday", "Sex": "Friday", "Sab": "Saturday", "Dom": "Sunday"
}
dias_semana_map_inv = {v: k for k, v in dias_semana_map.items()}

# --- Funções de Processamento de Dados ---

def process_uploaded_report(uploaded_file):
    """Processa o arquivo de relatório de status do agente."""
    try:
        # Ler o arquivo sem cabeçalho e atribuir nomes de coluna manualmente
        df = pd.read_excel(uploaded_file, header=None)

        # Mapear as colunas conforme o arquivo de exemplo
        df.columns = [
            'Nome do agente',
            'Dia',
            'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora',
            'Status',
            'Duração (min)'
        ]

        # Converter colunas de data/hora para o formato datetime, com tratamento de erros
        df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(
            df['Hora de início do estado - Carimbo de data/hora'], errors='coerce'
        )
        df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(
            df['Hora de término do estado - Carimbo de data/hora'], errors='coerce'
        )

        # Preencher NaT (Not a Time) na coluna de término com o final do dia atual
        # Isso é uma heurística para status abertos, pode ser ajustado conforme a regra de negócio
        df['Hora de término do estado - Carimbo de data/hora'] = df.apply(
            lambda row: row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
            if pd.isna(row['Hora de término do estado - Carimbo de data/hora'])
            else row['Hora de término do estado - Carimbo de data/hora'],
            axis=1
        )

        # Remover linhas onde a data de início é inválida
        df.dropna(subset=['Hora de início do estado - Carimbo de data/hora'], inplace=True)

        # Ajustar a coluna 'Dia' para ser a data completa
        df['Data'] = df['Hora de início do estado - Carimbo de data/hora'].dt.date

        # Renomear para consistência
        df.rename(columns={
            'Hora de início do estado - Carimbo de data/hora': 'Inicio',
            'Hora de término do estado - Carimbo de data/hora': 'Fim',
            'Status': 'Tipo' # Renomear para 'Tipo' para o gráfico
        }, inplace=True)

        # Filtrar apenas o status 'Unified online' para o gráfico de status real
        df_online = df[df['Tipo'] == 'Unified online'].copy()
        df_online['Tipo'] = 'Status Real (Online)' # Para diferenciar no gráfico

        st.session_state.df_real_status = df_online
        st.success("Relatório de status carregado e processado com sucesso!")
    except Exception as e:
        st.error(f"Erro ao processar o relatório de status: {e}")
        st.exception(e)

def process_uploaded_scale(uploaded_file):
    """Processa o arquivo de escala do agente."""
    try:
        df_escala_raw = pd.read_excel(uploaded_file)

        # Verificar e renomear a coluna 'NOME' para 'Nome do agente'
        if 'NOME' in df_escala_raw.columns:
            df_escala_raw.rename(columns={'NOME': 'Nome do agente'}, inplace=True)
        else:
            st.error("Coluna 'NOME' não encontrada no arquivo de escala. Certifique-se de que o cabeçalho está correto.")
            return

        # Preencher NaNs nas colunas de horário com '00:00:00' antes da conversão
        df_escala_raw['ENTRADA'] = df_escala_raw['ENTRADA'].fillna('00:00:00')
        df_escala_raw['SAÍDA'] = df_escala_raw['SAÍDA'].fillna('00:00:00')

        # Converter ENTRADA e SAÍDA para objetos time, com tratamento de erros
        df_escala_raw['Entrada'] = pd.to_datetime(df_escala_raw['ENTRADA'].astype(str), format='%H:%M:%S', errors='coerce').dt.time
        df_escala_raw['Saída'] = pd.to_datetime(df_escala_raw['SAÍDA'].astype(str), format='%H:%M:%S', errors='coerce').dt.time

        # Remover linhas onde a conversão de horário falhou
        df_escala_raw.dropna(subset=['Entrada', 'Saída'], inplace=True)

        # Expandir a escala para cada dia da semana
        escala_expanded = []
        for _, row in df_escala_raw.iterrows():
            agente = row['Nome do agente']
            dias_atendimento_str = str(row['DIAS DE ATENDIMENTO']).replace(' ', '').split(',')
            entrada = row['Entrada']
            saida = row['Saída']

            # Tratar casos como "Seg e Qui loja, Ter, Qua e Sex Call"
            dias_validos = []
            for dia_str in dias_atendimento_str:
                for k, v in dias_semana_map.items():
                    if k in dia_str:
                        dias_validos.append(v)
                        break # Adiciona apenas uma vez por dia

            for dia_semana_pt in dias_validos:
                escala_expanded.append({
                    'Nome do agente': agente,
                    'Dia da Semana': dia_semana_pt,
                    'Entrada': entrada,
                    'Saída': saida,
                    'Grupo': row.get('CARGA', 'N/A') # Usar 'CARGA' como grupo ou 'N/A'
                })

        st.session_state.df_escala = pd.DataFrame(escala_expanded)
        st.success("Escala carregada e processada com sucesso!")
    except Exception as e:
        st.error(f"Erro ao processar o arquivo de escala: {e}")
        st.exception(e)

# --- Inicialização do Session State ---
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame(columns=['Nome do agente', 'Data', 'Inicio', 'Fim', 'Tipo'])
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame(columns=['Nome do agente', 'Dia da Semana', 'Entrada', 'Saída', 'Grupo'])
if 'grupos_manuais' not in st.session_state:
    st.session_state.grupos_manuais = ['6h20min', '8h12min', 'Outro Grupo']

# --- Abas do Aplicativo ---
tab1, tab2, tab3 = st.tabs(["Upload de Relatório", "Criar/Editar Escala", "Visualização da Escala"])

with tab1:
    st.header("Upload do Relatório de Status dos Agentes")
    uploaded_file_report = st.file_uploader("Escolha um arquivo Excel (.xlsx) para o relatório de status", type=["xlsx"], key="report_uploader")
    if uploaded_file_report:
        process_uploaded_report(uploaded_file_report)

with tab2:
    st.header("Criar/Editar Escala de Agentes")

    st.subheader("Carregar Escala via Arquivo Excel")
    uploaded_file_escala = st.file_uploader("Escolha um arquivo Excel (.xlsx) para a escala", type=["xlsx"], key="escala_uploader")
    if uploaded_file_escala:
        process_uploaded_scale(uploaded_file_escala)

    st.subheader("Adicionar Agente à Escala Manualmente")
    with st.form("form_add_agent_scale"):
        # Obter todos os agentes únicos do relatório real e da escala existente
        all_agents_in_data = set(st.session_state.df_real_status['Nome do agente'].unique())
        all_agents_in_data.update(st.session_state.df_escala['Nome do agente'].unique())

        agent_options = sorted(list(all_agents_in_data))
        agent_options.insert(0, "(Novo Agente)")

        selected_agent_manual = st.selectbox("Selecione o Agente", agent_options, key="selected_agent_manual")
        new_agent_name = ""
        if selected_agent_manual == "(Novo Agente)":
            new_agent_name = st.text_input("Nome do Novo Agente", key="new_agent_name_input")

        dia_semana_manual = st.multiselect("Dias da Semana", list(dias_semana_map.keys()), key="dia_semana_manual")
        hora_inicio_manual = st.time_input("Hora de Início", value=time(9, 0), key="hora_inicio_manual")
        hora_fim_manual = st.time_input("Hora de Término", value=time(17, 0), key="hora_fim_manual")

        grupo_options = sorted(list(set(st.session_state.df_escala['Grupo'].unique()).union(st.session_state.grupos_manuais)))
        grupo_options.insert(0, "Selecione um Grupo")
        selected_grupo_manual = st.selectbox("Grupo (Escala)", grupo_options, key="selected_grupo_manual")

        new_grupo_name = ""
        if selected_grupo_manual == "Outro Grupo":
            new_grupo_name = st.text_input("Nome do Novo Grupo", key="new_grupo_name_input")

        submitted = st.form_submit_button("Adicionar à Escala")
        if submitted:
            agent_to_add = new_agent_name if selected_agent_manual == "(Novo Agente)" else selected_agent_manual
            grupo_to_add = new_grupo_name if selected_grupo_manual == "Outro Grupo" else selected_grupo_manual

            if agent_to_add and dia_semana_manual and grupo_to_add != "Selecione um Grupo":
                new_entries = []
                for dia in dia_semana_manual:
                    new_entries.append({
                        'Nome do agente': agent_to_add,
                        'Dia da Semana': dias_semana_map[dia],
                        'Entrada': hora_inicio_manual,
                        'Saída': hora_fim_manual,
                        'Grupo': grupo_to_add
                    })

                if not new_entries:
                    st.warning("Nenhuma entrada válida para adicionar. Verifique os dias da semana selecionados.")
                else:
                    st.session_state.df_escala = pd.concat([st.session_state.df_escala, pd.DataFrame(new_entries)], ignore_index=True)
                    st.success(f"Escala para {agent_to_add} adicionada com sucesso!")
                    if new_grupo_name and new_grupo_name not in st.session_state.grupos_manuais:
                        st.session_state.grupos_manuais.append(new_grupo_name)
            else:
                st.warning("Por favor, preencha todos os campos para adicionar à escala.")

    st.subheader("Escala Atual")
    if not st.session_state.df_escala.empty:
        st.dataframe(st.session_state.df_escala, use_container_width=True)
    else:
        st.info("Nenhuma escala carregada ou adicionada ainda.")

with tab3:
    st.header("Visualização da Escala e Status Real")

    # --- Filtros na Barra Lateral ---
    st.sidebar.header("Filtros")

    all_agents_in_data = set(st.session_state.df_real_status['Nome do agente'].unique())
    all_agents_in_data.update(st.session_state.df_escala['Nome do agente'].unique())

    if not all_agents_in_data:
        st.sidebar.warning("Carregue os relatórios para ver os agentes.")
        selected_agents = []
    else:
        selected_agents = st.sidebar.multiselect(
            "Selecione os Agentes",
            sorted(list(all_agents_in_data)),
            key="filter_agents"
        )

    all_groups = sorted(list(set(st.session_state.df_escala['Grupo'].unique()).union(st.session_state.grupos_manuais)))
    selected_groups = st.sidebar.multiselect(
        "Selecione os Grupos",
        all_groups,
        key="filter_groups"
    )

    today = datetime.now().date()
    default_start_date = today - timedelta(days=7) # Últimos 7 dias como padrão
    default_end_date = today

    date_range = st.sidebar.date_input(
        "Selecione o Intervalo de Datas",
        value=(default_start_date, default_end_date),
        key="date_range_filter"
    )

    start_date = date_range[0] if date_range else None
    end_date = date_range[1] if len(date_range) > 1 else start_date

    # Limitar o intervalo de datas para evitar muitos subplots
    if start_date and end_date:
        if (end_date - start_date).days > 14: # Limite de 14 dias, ajuste conforme necessário
            st.sidebar.warning("Por favor, selecione um intervalo de datas de no máximo 14 dias para uma melhor visualização do gráfico.")
            end_date = start_date + timedelta(days=13) # Ajusta o fim para 14 dias a partir do início
            st.sidebar.date_input(
                "Intervalo de Datas Ajustado",
                value=(start_date, end_date),
                key="date_range_filter_adjusted",
                disabled=True # Desabilita para mostrar que foi ajustado
            )

    # --- Lógica de Filtragem e Geração do Gráfico ---
    if selected_agents and start_date and end_date:
        # Filtrar df_real_status
        filtered_df_real_status = st.session_state.df_real_status[
            (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
            (st.session_state.df_real_status['Data'] >= start_date) &
            (st.session_state.df_real_status['Data'] <= end_date)
        ].copy()

        # Filtrar df_escala
        filtered_df_escala = st.session_state.df_escala[
            (st.session_state.df_escala['Nome do agente'].isin(selected_agents))
        ].copy()

        if selected_groups:
            filtered_df_escala = filtered_df_escala[filtered_df_escala['Grupo'].isin(selected_groups)]
            # Ajustar selected_agents para incluir apenas os agentes dos grupos selecionados
            agents_in_selected_groups = filtered_df_escala['Nome do agente'].unique()
            selected_agents = [agent for agent in selected_agents if agent in agents_in_selected_groups]
            filtered_df_real_status = filtered_df_real_status[filtered_df_real_status['Nome do agente'].isin(selected_agents)]


        if not filtered_df_real_status.empty or not filtered_df_escala.empty:
            # Expandir a escala para o intervalo de datas selecionado
            expanded_escala_data = []
            current_date = start_date
            while current_date <= end_date:
                day_of_week_en = current_date.strftime('%A') # Ex: 'Monday'

                escala_do_dia = filtered_df_escala[
                    filtered_df_escala['Dia da Semana'] == day_of_week_en
                ]

                for _, row_escala in escala_do_dia.iterrows():
                    escala_start_dt = datetime.combine(current_date, row_escala['Entrada'])
                    escala_end_dt = datetime.combine(current_date, row_escala['Saída'])

                    # Se a escala vira o dia (ex: 22:00-06:00)
                    if escala_end_dt < escala_start_dt:
                        escala_end_dt += timedelta(days=1)

                    expanded_escala_data.append({
                        'Nome do agente': row_escala['Nome do agente'],
                        'Data': current_date,
                        'Inicio': escala_start_dt,
                        'Fim': escala_end_dt,
                        'Tipo': 'Escala'
                    })
                current_date += timedelta(days=1)

            df_expanded_escala = pd.DataFrame(expanded_escala_data)

            # Concatenar dados de escala e status real para o gráfico
            df_gantt = pd.concat([df_expanded_escala, filtered_df_real_status], ignore_index=True)

            # Garantir que apenas agentes selecionados e com dados estejam no df_gantt
            df_gantt = df_gantt[df_gantt['Nome do agente'].isin(selected_agents)]

            if not df_gantt.empty:
                # Ordenar para melhor visualização
                df_gantt = df_gantt.sort_values(by=['Data', 'Nome do agente', 'Inicio'])

                # Ajustar altura do gráfico dinamicamente
                num_unique_rows = df_gantt['Nome do agente'].nunique() * df_gantt['Data'].nunique()
                chart_height = max(400, num_unique_rows * 50) # Altura mínima de 400px, 50px por linha de agente/dia

                st.subheader("Comparativo de Escala vs. Status Real (Online)")

                # Aviso se muitos agentes selecionados
                if len(selected_agents) > 10: # Limite arbitrário, ajuste conforme necessário
                    st.warning(f"Você selecionou {len(selected_agents)} agentes. Para uma melhor visualização, considere selecionar menos agentes.")

                fig = px.timeline(
                    df_gantt,
                    x_start="Inicio",
                    x_end="Fim",
                    y="Nome do agente",
                    color="Tipo",
                    facet_row="Data",
                    title="Comparativo de Escala vs. Status Real (Online)",
                    color_discrete_map={'Escala': 'blue', 'Status Real (Online)': 'green'},
                    height=chart_height,
                    category_orders={"Tipo": ["Escala", "Status Real (Online)"]} # Garante ordem
                )
                fig.update_yaxes(categoryorder="array", categoryarray=selected_agents)
                fig.update_xaxes(
                    tickformat="%H:%M",
                    range=[datetime.combine(start_date, time(0, 0, 0)), datetime.combine(start_date, time(23, 59, 59))],
                    title="Hora do Dia"
                )
                fig.layout.xaxis.rangeselector.buttons = list([
                    dict(count=1, label="1h", step="hour", stepmode="backward"),
                    dict(count=6, label="6h", step="hour", stepmode="backward"),
                    dict(count=12, label="12h", step="hour", stepmode="backward"),
                    dict(count=1, label="1d", step="day", stepmode="backward"),
                    dict(step="all")
                ])
                st.plotly_chart(fig, use_container_width=True)

                st.subheader("Métricas de Desempenho")
                metrics_data = []
                # Recalcular métricas apenas para os agentes e datas filtrados
                for agent_name in selected_agents:
                    for current_date in pd.date_range(start=start_date, end=end_date):
                        current_date = current_date.date() # Garante que é apenas a data

                        # Escala do agente para o dia
                        escala_do_dia_agente = filtered_df_escala[
                            (filtered_df_escala['Nome do agente'] == agent_name) &
                            (filtered_df_escala['Dia da Semana'] == current_date.strftime('%A'))
                        ]

                        total_tempo_escala_segundos = 0
                        for _, escala_row in escala_do_dia_agente.iterrows():
                            escala_start_time = datetime.combine(current_date, escala_row['Entrada'])
                            escala_end_time = datetime.combine(current_date, escala_row['Saída'])
                            if escala_end_time < escala_start_time:
                                escala_end_time += timedelta(days=1)
                            total_tempo_escala_segundos += (escala_end_time - escala_start_time).total_seconds()

                        # Status real do agente para o dia
                        status_do_dia = filtered_df_real_status[
                            (filtered_df_real_status['Nome do agente'] == agent_name) &
                            (filtered_df_real_status['Data'] == current_date)
                        ]

                        total_online_segundos = 0
                        total_online_na_escala_segundos = 0

                        for _, status_row in status_do_dia.iterrows():
                            status_start = status_row['Inicio']
                            status_end = status_row['Fim']

                            # Garantir que o status não passe da meia-noite para o cálculo simples
                            # Se o status termina no dia seguinte, ajustamos para o final do dia atual para o cálculo diário
                            if status_end.date() > status_start.date():
                                status_end = datetime.combine(status_start.date(), time(23, 59, 59))

                            if status_row['Tipo'] == 'Status Real (Online)': # Já filtrado para online
                                total_online_segundos += (status_end - status_start).total_seconds()

                                # Calcular interseção com a escala
                                for _, escala_row in escala_do_dia_agente.iterrows():
                                    escala_start_time = datetime.combine(current_date, escala_row['Entrada'])
                                    escala_end_time = datetime.combine(current_date, escala_row['Saída'])
                                    if escala_end_time < escala_start_time:
                                        escala_end_time += timedelta(days=1) # Ajusta para o dia seguinte se virar a noite

                                    intersecao_start = max(status_start, escala_start_time)
                                    intersecao_end = min(status_end, escala_end_time)

                                    if intersecao_end > intersecao_start:
                                        total_online_na_escala_segundos += (intersecao_end - intersecao_start).total_seconds()

                        # Evitar divisão por zero
                        disponibilidade = (total_online_na_escala_segundos / total_tempo_escala_segundos) if total_tempo_escala_segundos > 0 else 0
                        aderencia = (total_online_na_escala_segundos / total_online_segundos) if total_online_segundos > 0 else 0

                        metrics_data.append({
                            'Agente': agent_name,
                            'Data': current_date,
                            'Disponibilidade (%)': disponibilidade * 100,
                            'Aderência (%)': aderencia * 100
                        })

            if metrics_data:
                df_metrics = pd.DataFrame(metrics_data)

                # Agregação por agente (média diária)
                df_metrics_agg = df_metrics.groupby('Agente').agg(
                    {'Disponibilidade (%)': 'mean', 'Aderência (%)': 'mean'}
                ).reset_index()

                st.dataframe(df_metrics_agg.style.format({'Disponibilidade (%)': "{:.2f}%", 'Aderência (%)': "{:.2f}%"}), use_container_width=True)
            else:
                st.info("Nenhuma métrica calculada para os filtros selecionados. Verifique se há dados de escala e status real.")
        else:
            st.info("Não há dados de status real e/ou escala para calcular as métricas com os filtros selecionados.")
