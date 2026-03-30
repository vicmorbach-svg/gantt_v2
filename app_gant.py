import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time
import numpy as np
import unicodedata # Para normalização de strings

# --- Configurações Iniciais do Streamlit ---
st.set_page_config(layout="wide", page_title="Dashboard de Acompanhamento de Call Center")
st.title("Dashboard de Acompanhamento de Equipe de Call Center")

# --- Funções Auxiliares ---

def normalize_agent_name(name):
    """Normaliza o nome do agente (remove acentos, converte para maiúsculas, remove espaços extras)."""
    if pd.isna(name): # Usando pd.isna no lugar de pd.isnat
        return name
    name = str(name).strip().upper()
    name = ''.join(c for c in name if c.isalnum() or c.isspace())
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    return name

def calculate_time_overlap(start1, end1, start2, end2):
    """Calcula a sobreposição em segundos entre dois intervalos de tempo."""
    # Garante que os objetos sejam datetime para comparação
    # Se forem apenas time, combina com uma data mínima para permitir comparação
    if not isinstance(start1, datetime): start1 = datetime.combine(datetime.min.date(), start1)
    if not isinstance(end1, datetime): end1 = datetime.combine(datetime.min.date(), end1)
    if not isinstance(start2, datetime): start2 = datetime.combine(datetime.min.date(), start2)
    if not isinstance(end2, datetime): end2 = datetime.combine(datetime.min.date(), end2)

    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)

    if overlap_end > overlap_start:
        return (overlap_end - overlap_start).total_seconds()
    return 0

# --- Funções de Processamento de Dados ---

@st.cache_data(ttl=3600) # Cache para 1 hora
def process_uploaded_report(uploaded_file):
    """Processa o arquivo de relatório de status dos agentes."""
    try:
        # Ler o arquivo com cabeçalho na primeira linha
        df = pd.read_excel(uploaded_file, header=0)

        # Renomear colunas para padronizar, se necessário.
        # Baseado no arquivo fornecido, os nomes já estão bons, mas vamos garantir.
        df.rename(columns={
            'Nome do agente': 'Nome do agente',
            'Hora de início do estado - Dia do mês': 'Dia', # Renomeando para 'Dia'
            'Hora de início do estado - Carimbo de data/hora': 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora': 'Hora de término do estado - Carimbo de data/hora',
            'Estado': 'Estado',
            'Tempo do agente no estado / Minutos': 'Duração' # Renomeando para 'Duração'
        }, inplace=True)

        # Converte as colunas de data/hora para o tipo datetime
        df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(
            df['Hora de início do estado - Carimbo de data/hora'], errors='coerce'
        )
        df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(
            df['Hora de término do estado - Carimbo de data/hora'], errors='coerce'
        )

        # Preenche NaT na coluna de término com o final do dia de início
        # Isso é importante para status que ainda estão abertos ou não têm um fim definido
        df['Hora de término do estado - Carimbo de data/hora'] = df.apply(
            lambda row: row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
            if pd.isna(row['Hora de término do estado - Carimbo de data/hora']) # Usando pd.isna
            else row['Hora de término do estado - Carimbo de data/hora'],
            axis=1
        )

        # Remove linhas onde a data de início ainda é NaT após o preenchimento
        df.dropna(subset=['Hora de início do estado - Carimbo de data/hora'], inplace=True)

        # Cria a coluna 'Data' para o dia do evento
        df['Data'] = df['Hora de início do estado - Carimbo de data/hora'].dt.normalize() # Garante que 'Data' seja datetime

        # Normaliza os nomes dos agentes
        df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

        return df
    except Exception as e:
        st.error(f"Erro ao processar o relatório: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600) # Cache para 1 hora
def process_uploaded_scale(uploaded_file):
    """Processa o arquivo de escala dos agentes."""
    try:
        df_escala_raw = pd.read_excel(uploaded_file)

        # Verifica se a coluna 'NOME' existe e renomeá-la para 'Nome do agente'
        if 'NOME' in df_escala_raw.columns:
            df_escala_raw.rename(columns={'NOME': 'Nome do agente'}, inplace=True)
        else:
            st.error("A coluna 'NOME' não foi encontrada no arquivo de escala. Por favor, verifique o cabeçalho.")
            return pd.DataFrame()

        # Normaliza os nomes dos agentes
        df_escala_raw['Nome do agente'] = df_escala_raw['Nome do agente'].apply(normalize_agent_name)

        # Preencher NaN nas colunas de horário com um valor padrão antes da conversão
        df_escala_raw['ENTRADA'] = df_escala_raw['ENTRADA'].fillna('00:00:00')
        df_escala_raw['SAÍDA'] = df_escala_raw['SAÍDA'].fillna('00:00:00')

        # Converte as colunas de horário para o tipo time
        # Lida com formatos datetime.time, datetime.datetime (extraindo apenas a hora) e strings de hora
        def to_time(value):
            if pd.isna(value): # Usando pd.isna
                return None
            if isinstance(value, time):
                return value
            if isinstance(value, datetime):
                return value.time()
            try:
                # Tenta converter string para time, aceitando HH:MM ou HH:MM:SS
                return datetime.strptime(str(value), '%H:%M:%S').time()
            except ValueError:
                try:
                    return datetime.strptime(str(value), '%H:%M').time()
                except ValueError:
                    return None # Retorna None para valores que não podem ser convertidos

        df_escala_raw['Entrada'] = df_escala_raw['ENTRADA'].apply(to_time)
        df_escala_raw['Saída'] = df_escala_raw['SAÍDA'].apply(to_time)

        # Remove linhas onde a conversão de horário falhou
        df_escala_raw.dropna(subset=['Entrada', 'Saída'], inplace=True)

        # Mapeamento de dias da semana para o formato completo em inglês
        dias_semana_map = {
            "Seg": "Monday", "Ter": "Tuesday", "Qua": "Wednesday",
            "Qui": "Thursday", "Sex": "Friday", "Sab": "Saturday", "Dom": "Sunday",
            "Segunda-feira": "Monday", "Terça-feira": "Tuesday", "Quarta-feira": "Wednesday",
            "Quinta-feira": "Thursday", "Sexta-feira": "Friday", "Sábado": "Saturday", "Domingo": "Sunday"
        }

        # Expande a escala para ter uma linha por dia da semana
        expanded_escala = []
        for _, row in df_escala_raw.iterrows():
            dias_atendimento_str = str(row['DIAS DE ATENDIMENTO']).replace(' ', '').split(',')
            for dia_curto in dias_atendimento_str:
                dia_completo = dias_semana_map.get(dia_curto, None)
                if dia_completo:
                    expanded_escala.append({
                        'Nome do agente': row['Nome do agente'],
                        'Dia da Semana': dia_completo,
                        'Entrada': row['Entrada'],
                        'Saída': row['Saída'],
                        'Grupo': row.get('GRUPO', 'Não Definido') # Assume 'GRUPO' se existir
                    })

        df_escala = pd.DataFrame(expanded_escala)
        st.success("Escala carregada e processada com sucesso!")
        return df_escala
    except Exception as e:
        st.error(f"Erro ao processar o arquivo de escala: {e}")
        return pd.DataFrame()

# --- Inicialização do Session State ---
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {} # {grupo: [agente1, agente2]}

# --- Layout do Aplicativo ---
tab1, tab2, tab3 = st.tabs(["Upload de Dados", "Gerenciar Grupos", "Visualização e Métricas"])

with tab1:
    st.header("Upload de Relatório de Status e Escala")

    st.subheader("1. Upload do Relatório de Status dos Agentes (.xlsx)")
    uploaded_report_file = st.file_uploader("Escolha um arquivo Excel para o relatório de status", type=["xlsx"], key="report_uploader")
    if uploaded_report_file is not None:
        st.session_state.df_real_status = process_uploaded_report(uploaded_report_file)

    st.subheader("2. Upload da Escala dos Agentes (.xlsx)")
    uploaded_escala_file = st.file_uploader("Escolha um arquivo Excel para a escala", type=["xlsx"], key="escala_uploader")
    if uploaded_escala_file is not None:
        st.session_state.df_escala = process_uploaded_scale(uploaded_escala_file)

with tab2:
    st.header("Gerenciar Grupos de Agentes")

    all_agents_in_data = set()
    if not st.session_state.df_real_status.empty:
        all_agents_in_data.update(st.session_state.df_real_status['Nome do agente'].unique())
    if not st.session_state.df_escala.empty:
        all_agents_in_data.update(st.session_state.df_escala['Nome do agente'].unique())

    available_agents_for_grouping = sorted(list(all_agents_in_data))

    st.subheader("Criar ou Editar Grupos")
    group_name = st.text_input("Nome do Novo Grupo:")
    selected_agents_for_group = st.multiselect(
        "Selecione os agentes para este grupo:",
        options=available_agents_for_grouping,
        key="group_agent_selector"
    )
    if st.button("Salvar Grupo"):
        if group_name and selected_agents_for_group:
            st.session_state.agent_groups[group_name] = selected_agents_for_group
            st.success(f"Grupo '{group_name}' salvo com {len(selected_agents_for_group)} agentes.")
        else:
            st.warning("Por favor, insira um nome para o grupo e selecione pelo menos um agente.")

    st.subheader("Grupos Existentes")
    if st.session_state.agent_groups:
        for group, agents in st.session_state.agent_groups.items():
            st.write(f"**{group}**: {', '.join(agents)}")
            if st.button(f"Remover Grupo '{group}'", key=f"remove_group_{group}"):
                del st.session_state.agent_groups[group]
                st.rerun()
    else:
        st.info("Nenhum grupo criado ainda.")

with tab3:
    st.header("Visualização e Métricas de Desempenho")

    # --- Comparativo de Agentes ---
    st.subheader("Comparativo de Agentes entre Relatório e Escala")
    agents_in_report = set(st.session_state.df_real_status['Nome do agente'].unique()) if not st.session_state.df_real_status.empty else set()
    agents_in_escala = set(st.session_state.df_escala['Nome do agente'].unique()) if not st.session_state.df_escala.empty else set()

    agents_only_in_report = agents_in_report - agents_in_escala
    agents_only_in_escala = agents_in_escala - agents_in_report
    agents_in_both = agents_in_report.intersection(agents_in_escala)

    if agents_only_in_report:
        st.warning(f"Agentes no relatório, mas sem escala: {', '.join(sorted(list(agents_only_in_report)))}")
    if agents_only_in_escala:
        st.warning(f"Agentes na escala, mas sem dados de relatório: {', '.join(sorted(list(agents_only_in_escala)))}")
    if agents_in_both:
        st.success(f"Agentes com relatório e escala: {len(agents_in_both)} agentes.")
    else:
        st.info("Nenhum agente encontrado em ambos os arquivos ou nenhum arquivo carregado.")

    st.sidebar.header("Filtros")

    # Filtro de Grupo
    all_groups = ['Todos'] + list(st.session_state.agent_groups.keys())
    selected_group = st.sidebar.selectbox("Filtrar por Grupo:", options=all_groups)

    # Obter lista de agentes baseada no grupo selecionado
    if selected_group == 'Todos':
        all_agents_for_filter = sorted(list(all_agents_in_data))
    else:
        all_agents_for_filter = sorted(list(st.session_state.agent_groups.get(selected_group, [])))

    # Filtro de Agentes
    selected_agents = st.sidebar.multiselect(
        "Selecione os Agentes:",
        options=all_agents_for_filter,
        default=all_agents_for_filter if len(all_agents_for_filter) <= 10 else [] # Limita default para não sobrecarregar
    )

    # Filtro de Data
    today = datetime.now().date()
    default_start_date = today - timedelta(days=6) # Últimos 7 dias
    default_end_date = today

    start_date = st.sidebar.date_input("Data de Início:", value=default_start_date)
    end_date = st.sidebar.date_input("Data de Término:", value=default_end_date)

    # Validação do intervalo de datas
    if start_date > end_date:
        st.sidebar.error("A data de início não pode ser posterior à data de término.")
        st.stop()

    # Limite de dias para evitar sobrecarga do gráfico
    max_days_for_chart = 14
    if (end_date - start_date).days > max_days_for_chart:
        st.sidebar.warning(f"Intervalo de datas muito grande. Limitando a {max_days_for_chart} dias para o gráfico.")
        end_date = start_date + timedelta(days=max_days_for_chart - 1)
        st.sidebar.date_input("Data de Término (ajustada):", value=end_date, disabled=True)

    if st.button("Gerar Gráfico e Métricas"):
        if not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty and selected_agents:
            filtered_df_real_status = st.session_state.df_real_status[
                (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
                (st.session_state.df_real_status['Data'].dt.date >= start_date) &
                (st.session_state.df_real_status['Data'].dt.date <= end_date)
            ].copy()

            filtered_df_escala = st.session_state.df_escala[
                st.session_state.df_escala['Nome do agente'].isin(selected_agents)
            ].copy()

            if filtered_df_real_status.empty and filtered_df_escala.empty:
                st.info("Nenhum dado de status ou escala encontrado para os filtros selecionados.")
            else:
                st.subheader("Gráfico Comparativo de Escala vs. Status Real (Online)")

                df_chart_data = []
                for agent in selected_agents:
                    agent_df_status = filtered_df_real_status[filtered_df_real_status['Nome do agente'] == agent]
                    agent_df_escala = filtered_df_escala[filtered_df_escala['Nome do agente'] == agent]

                    for single_date in pd.date_range(start=start_date, end=end_date):
                        # Adicionar entradas de escala
                        day_of_week = single_date.strftime('%A')
                        escala_do_dia = agent_df_escala[agent_df_escala['Dia da Semana'] == day_of_week]

                        for _, row_escala in escala_do_dia.iterrows():
                            escala_start_dt = datetime.combine(single_date, row_escala['Entrada'])
                            escala_end_dt = datetime.combine(single_date, row_escala['Saída'])
                            if escala_end_dt < escala_start_dt: # Escala atravessa a meia-noite
                                escala_end_dt += timedelta(days=1)

                            df_chart_data.append({
                                'Nome do agente': agent,
                                'Data': single_date,
                                'Inicio': escala_start_dt,
                                'Fim': escala_end_dt,
                                'Tipo': 'Escala'
                            })

                        # Adicionar entradas de status real (Unified online)
                        status_do_dia = agent_df_status[
                            (agent_df_status['Data'].dt.date == single_date.date()) &
                            (agent_df_status['Estado'] == 'Unified online')
                        ]
                        for _, row_status in status_do_dia.iterrows():
                            status_start_dt = row_status['Hora de início do estado - Carimbo de data/hora']
                            status_end_dt = row_status['Hora de término do estado - Carimbo de data/hora']

                            # Ajusta o fim do status para o final do dia se ele atravessar a meia-noite
                            if status_end_dt.date() > status_start_dt.date():
                                status_end_dt = status_start_dt.replace(hour=23, minute=59, second=59)

                            df_chart_data.append({
                                'Nome do agente': agent,
                                'Data': single_date,
                                'Inicio': status_start_dt,
                                'Fim': status_end_dt,
                                'Tipo': 'Status Real (Online)'
                            })

                if df_chart_data:
                    df_chart = pd.DataFrame(df_chart_data)

                    # Criar uma coluna combinada para o eixo Y para melhor agrupamento visual
                    df_chart['Agente_Data_Tipo'] = df_chart['Nome do agente'] + ' - ' + df_chart['Data'].dt.strftime('%Y-%m-%d') + ' (' + df_chart['Tipo'] + ')'

                    # Ordenar para melhor visualização
                    df_chart = df_chart.sort_values(by=['Nome do agente', 'Data', 'Tipo', 'Inicio'])

                    # Ajustar altura do gráfico dinamicamente
                    num_unique_rows = df_chart['Agente_Data_Tipo'].nunique()
                    chart_height = max(400, num_unique_rows * 30) # Ajuste o multiplicador conforme necessário

                    fig = px.timeline(
                        df_chart,
                        x_start="Inicio",
                        x_end="Fim",
                        y="Agente_Data_Tipo", # Usando a coluna combinada para o eixo Y
                        color="Tipo",
                        title="Comparativo de Escala vs. Status Real (Online)",
                        color_discrete_map={'Escala': 'blue', 'Status Real (Online)': 'green'},
                        height=chart_height
                    )
                    # Ajustar o range do eixo X para cobrir o dia inteiro
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

                else:
                    st.info("Nenhum dado para exibir no gráfico com os filtros selecionados.")

                st.subheader("Métricas de Desempenho")
                metrics_data = []
                for agent in selected_agents:
                    agent_df_status = filtered_df_real_status[filtered_df_real_status['Nome do agente'] == agent]
                    agent_df_escala = filtered_df_escala[filtered_df_escala['Nome do agente'] == agent]

                    for single_date in pd.date_range(start=start_date, end=end_date):
                        # Escala do agente para o dia
                        daily_scale_entries = agent_df_escala[agent_df_escala['Dia da Semana'] == single_date.strftime('%A')]

                        total_escala_segundos = 0
                        for _, row_escala in daily_scale_entries.iterrows():
                            escala_start_dt = datetime.combine(single_date, row_escala['Entrada'])
                            escala_end_dt = datetime.combine(single_date, row_escala['Saída'])
                            if escala_end_dt < escala_start_dt: # Escala atravessa a meia-noite
                                escala_end_dt += timedelta(days=1)
                            total_escala_segundos += (escala_end_dt - escala_start_dt).total_seconds()

                        total_online_na_escala_segundos = 0
                        total_online_segundos = 0

                        # Status real do agente no dia atual
                        status_do_dia = agent_df_status[agent_df_status['Data'] == single_date]

                        for _, row_status in status_do_dia.iterrows():
                            status_start_dt = row_status['Hora de início do estado - Carimbo de data/hora']
                            status_end_dt = row_status['Hora de término do estado - Carimbo de data/hora']

                            # Ajusta o fim do status para o final do dia se ele atravessar a meia-noite
                            if status_end_dt.date() > status_start_dt.date():
                                status_end_dt = status_start_dt.replace(hour=23, minute=59, second=59)

                            if row_status['Estado'] == 'Unified online':
                                total_online_segundos += (status_end_dt - status_start_dt).total_seconds()

                                # Calcular interseção com a escala
                                for _, row_escala in daily_scale_entries.iterrows():
                                    escala_start_time = row_escala['Entrada']
                                    escala_end_time = row_escala['Saída']

                                    escala_start_dt_overlap = datetime.combine(single_date, escala_start_time)
                                    escala_end_dt_overlap = datetime.combine(single_date, escala_end_time)
                                    if escala_end_dt_overlap < escala_start_dt_overlap: # Escala atravessa a meia-noite
                                        escala_end_dt_overlap += timedelta(days=1)

                                    total_online_na_escala_segundos += calculate_time_overlap(
                                        status_start_dt, status_end_dt,
                                        escala_start_dt_overlap, escala_end_dt_overlap
                                    )

                        disponibilidade = (total_online_na_escala_segundos / total_escala_segundos * 100) if total_escala_segundos > 0 else 0
                        aderencia = (total_online_na_escala_segundos / total_online_segundos * 100) if total_online_segundos > 0 else 0

                        metrics_data.append({
                            'Agente': agent,
                            'Data': single_date.strftime('%Y-%m-%d'),
                            'Disponibilidade (%)': disponibilidade,
                            'Aderência (%)': aderencia
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
        else:
            st.info("Selecione os agentes e o intervalo de datas para visualizar o gráfico e as métricas.")
