import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, time
import numpy as np
import unicodedata
import os # Para operações de arquivo

# --- Configurações Iniciais do Streamlit ---
st.set_page_config(layout="wide")
st.title("Análise de Escalas e Status de Agentes")

# --- Variáveis de Estado para Armazenamento em Parquet ---
PARQUET_DIR = "parquet_data"
os.makedirs(PARQUET_DIR, exist_ok=True) # Garante que o diretório exista

PARQUET_REPORT_FILE = os.path.join(PARQUET_DIR, "df_real_status.parquet")
PARQUET_SCALE_FILE = os.path.join(PARQUET_DIR, "df_escala.parquet")
PARQUET_GROUPS_FILE = os.path.join(PARQUET_DIR, "agent_groups.parquet")

# --- Funções de Normalização ---
def normalize_agent_name(name):
    if pd.isna(name):
        return name
    name = str(name).strip().upper()
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    return name

# --- Funções de Processamento de Dados ---
def process_uploaded_report(df_report_raw):
    df = df_report_raw.copy()

    expected_columns_report = {
        'Nome do agente': 'Nome do agente',
        'Hora de início do estado - Dia do mês': 'Dia',
        'Hora de início do estado - Carimbo de data/hora': 'Hora de início do estado - Carimbo de data/hora',
        'Hora de término do estado - Carimbo de data/hora': 'Hora de término do estado - Carimbo de data/hora',
        'Estado': 'Estado',
        'Tempo do agente no estado / Minutos': 'Tempo do agente no estado / Minutos'
    }

    df = df.rename(columns=expected_columns_report)

    required_cols = ['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora', 'Estado']
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        st.error(f"Erro: O arquivo de status real está faltando as colunas essenciais: {', '.join(missing)}. Por favor, verifique o formato do arquivo.")
        return pd.DataFrame()

    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)
    df.dropna(subset=['Nome do agente'], inplace=True)
    df = df[df['Nome do agente'] != '']

    df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
    df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

    df['Hora de término do estado - Carimbo de data/hora'] = df.apply(
        lambda row: row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
        if pd.isna(row['Hora de término do estado - Carimbo de data/hora']) and pd.notna(row['Hora de início do estado - Carimbo de data/hora'])
        else row['Hora de término do estado - Carimbo de data/hora'],
        axis=1
    )

    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'], inplace=True)

    df['Hora de término do estado - Carimbo de data/hora'] = df.apply(
        lambda row: row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
        if row['Hora de término do estado - Carimbo de data/hora'].date() > row['Hora de início do estado - Carimbo de data/hora'].date()
        else row['Hora de término do estado - Carimbo de data/hora'],
        axis=1
    )

    df['Data'] = df['Hora de início do estado - Carimbo de data/hora'].dt.normalize()
    df['Tempo do agente no estado / Minutos'] = pd.to_numeric(df['Tempo do agente no estado / Minutos'], errors='coerce').fillna(0)

    return df

def to_time(val):
    if pd.isna(val):
        return None
    try:
        # Tenta converter para datetime e depois extrai a hora
        dt_obj = pd.to_datetime(val, errors='coerce')
        if pd.notna(dt_obj):
            return dt_obj.time()
    except Exception:
        pass
    return None

def process_uploaded_scale(df_scale_raw):
    df = df_scale_raw.copy()

    expected_columns_scale = {
        'NOME': 'Nome do agente',
        'DIAS DE ATENDIMENTO': 'Dias de Atendimento',
        'ENTRADA': 'Entrada',
        'SAÍDA': 'Saída',
        'CARGA': 'Carga'
    }

    df = df.rename(columns=expected_columns_scale)

    required_cols = ['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída']
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        st.error(f"Erro: O arquivo de escala está faltando as colunas essenciais: {', '.join(missing)}. Por favor, verifique o formato do arquivo.")
        return pd.DataFrame(), pd.DataFrame()

    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)
    df.dropna(subset=['Nome do agente'], inplace=True)
    df = df[df['Nome do agente'] != '']

    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    df.dropna(subset=['Entrada', 'Saída'], inplace=True)

    dias_map = {
        'SEG': 0, 'SEGUNDA': 0, 'SEGUNDA-FEIRA': 0,
        'TER': 1, 'TERCA': 1, 'TERÇA': 1, 'TERCA-FEIRA': 1, 'TERÇA-FEIRA': 1,
        'QUA': 2, 'QUARTA': 2, 'QUARTA-FEIRA': 2,
        'QUI': 3, 'QUINTA': 3, 'QUINTA-FEIRA': 3,
        'SEX': 4, 'SEXTA': 4, 'SEXTA-FEIRA': 4,
        'SAB': 5, 'SABADO': 5, 'SÁBADO': 5,
        'DOM': 6, 'DOMINGO': 6
    }

    df_expanded_scale = []
    agent_groups_data = []

    for _, row in df.iterrows():
        agent_name = row['Nome do agente']
        dias_str = str(row['Dias de Atendimento']).strip().upper()
        entrada = row['Entrada']
        saida = row['Saída']
        carga = row.get('Carga') # Usar .get() para evitar KeyError se a coluna não existir

        if carga and pd.notna(carga):
            agent_groups_data.append({'Agente': agent_name, 'Grupo_Carga': str(carga)})

        # Substituir " E " por "," e remover texto adicional como "LOJA", "CALL"
        dias_str_cleaned = dias_str.replace(' E ', ',').replace(' LOJA', '').replace(' CALL', '')
        dias_list = [d.strip() for d in dias_str_cleaned.split(',') if d.strip()]

        valid_days_for_agent = []
        for dia_abbr in dias_list:
            normalized_dia = unicodedata.normalize('NFKD', dia_abbr).encode('ascii', 'ignore').decode('utf-8').strip()
            if normalized_dia in dias_map:
                valid_days_for_agent.append(dias_map[normalized_dia])
            else:
                st.warning(f"Dia da semana '{dia_abbr}' não reconhecido para o agente {agent_name}. Ignorando.")

        if not valid_days_for_agent:
            st.warning(f"Nenhum dia de atendimento válido encontrado para o agente {agent_name}. Ignorando esta escala.")
            continue

        for day_of_week_num in valid_days_for_agent:
            df_expanded_scale.append({
                'Nome do agente': agent_name,
                'Dia da Semana Num': day_of_week_num,
                'Entrada': entrada,
                'Saída': saida,
                'Carga': carga # Incluir a carga na escala expandida
            })

    if not df_expanded_scale:
        st.warning("Nenhuma escala válida foi encontrada após o processamento. Verifique a coluna 'DIAS DE ATENDIMENTO' e os horários.")
        return pd.DataFrame(), pd.DataFrame()

    df_expanded_scale = pd.DataFrame(df_expanded_scale)
    df_agent_groups = pd.DataFrame(agent_groups_data).drop_duplicates(subset=['Agente', 'Grupo_Carga'])

    return df_expanded_scale, df_agent_groups

def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    analysis_results = []

    for agent in selected_agents:
        agent_df_real = df_real_status[df_real_status['Nome do agente'] == agent]
        agent_df_escala = df_escala[df_escala['Nome do agente'] == agent]

        total_scheduled_time_minutes = 0
        total_online_in_schedule_minutes = 0

        if not agent_df_escala.empty:
            current_date_metrics = start_date
            while current_date_metrics <= end_date:
                day_of_week_num = current_date_metrics.weekday()

                # Filtrar escala para o dia da semana atual
                daily_schedule = agent_df_escala[agent_df_escala['Dia da Semana Num'] == day_of_week_num]

                for _, scale_entry in daily_schedule.iterrows():
                    scale_start_time = scale_entry['Entrada']
                    scale_end_time = scale_entry['Saída']

                    if pd.notna(scale_start_time) and pd.notna(scale_end_time):
                        scale_start_dt = datetime.combine(current_date_metrics, scale_start_time)
                        scale_end_dt = datetime.combine(current_date_metrics, scale_end_time)

                        if scale_end_dt < scale_start_dt: # Escala que vira o dia
                            scale_end_dt += timedelta(days=1)

                        total_scheduled_time_minutes += (scale_end_dt - scale_start_dt).total_seconds() / 60

                        daily_real_status = agent_df_real[
                            (agent_df_real['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date_metrics) |
                            (agent_df_real['Hora de término do estado - Carimbo de data/hora'].dt.date == current_date_metrics)
                        ]

                        for _, status_entry in daily_real_status.iterrows():
                            if status_entry['Estado'] == 'Unified online':
                                status_start = status_entry['Hora de início do estado - Carimbo de data/hora']
                                status_end = status_entry['Hora de término do estado - Carimbo de data/hora']

                                if status_end.date() > current_date_metrics and scale_end_dt.date() == current_date_metrics:
                                    status_end = datetime.combine(current_date_metrics, datetime(1,1,1,23,59,59).time())

                                overlap_start = max(scale_start_dt, status_start)
                                overlap_end = min(scale_end_dt, status_end)

                                if overlap_end > overlap_start:
                                    total_online_in_schedule_minutes += (overlap_end - overlap_start).total_seconds() / 60
                current_date_metrics += timedelta(days=1)

            availability_percentage = (total_online_in_schedule_minutes / total_scheduled_time_minutes * 100) if total_scheduled_time_minutes > 0 else 0

            analysis_results.append({
                'Agente': agent,
                'Total Tempo Escala (min)': total_scheduled_time_minutes,
                'Total Tempo Online na Escala (min)': total_online_in_schedule_minutes,
                'Disponibilidade na Escala (%)': f"{availability_percentage:.2f}%"
            })
        else:
            analysis_results.append({
                'Agente': agent,
                'Total Tempo Escala (min)': 0,
                'Total Tempo Online na Escala (min)': 0,
                'Disponibilidade na Escala (%)': "N/A - Sem escala definida"
            })

    return pd.DataFrame(analysis_results)

# --- Funções de Carregamento/Salvamento de Parquet ---
def load_data_from_parquet():
    if os.path.exists(PARQUET_REPORT_FILE) and os.path.exists(PARQUET_SCALE_FILE) and os.path.exists(PARQUET_GROUPS_FILE):
        st.session_state.df_real_status = pd.read_parquet(PARQUET_REPORT_FILE)
        st.session_state.df_escala = pd.read_parquet(PARQUET_SCALE_FILE)
        st.session_state.agent_groups = pd.read_parquet(PARQUET_GROUPS_FILE)

        # Reconstruir all_unique_agents
        all_agents_report = set(st.session_state.df_real_status['Nome do agente'].unique()) if not st.session_state.df_real_status.empty else set()
        all_agents_scale = set(st.session_state.df_escala['Nome do agente'].unique()) if not st.session_state.df_escala.empty else set()
        st.session_state.all_unique_agents = sorted(list(all_agents_report.union(all_agents_scale)))

        st.success("Dados carregados com sucesso dos arquivos Parquet!")
        return True
    st.info("Nenhum arquivo Parquet encontrado para carregar.")
    return False

def save_data_to_parquet():
    if not st.session_state.df_real_status.empty:
        st.session_state.df_real_status.to_parquet(PARQUET_REPORT_FILE, index=False)
    if not st.session_state.df_escala.empty:
        st.session_state.df_escala.to_parquet(PARQUET_SCALE_FILE, index=False)
    if not st.session_state.agent_groups.empty:
        st.session_state.agent_groups.to_parquet(PARQUET_GROUPS_FILE, index=False)
    st.success("Dados salvos em arquivos Parquet para uso futuro.")

# --- Inicialização do Session State ---
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'all_unique_agents' not in st.session_state:
    st.session_state.all_unique_agents = []
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = pd.DataFrame()
if 'selected_group' not in st.session_state:
    st.session_state.selected_group = "Todos"

# --- Interface do Streamlit ---
tab_upload, tab_groups, tab_metrics = st.tabs(["Upload de Dados", "Gerenciar Grupos", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos")

    uploaded_report_file = st.file_uploader("Faça upload do relatório de status (Excel)", type=["xlsx"], key="report_uploader")
    uploaded_scale_file = st.file_uploader("Faça upload do arquivo de escala (Excel)", type=["xlsx"], key="scale_uploader")

    if st.button("Processar Arquivos"):
        if uploaded_report_file and uploaded_scale_file:
            try:
                df_report_raw = pd.read_excel(uploaded_report_file, header=0)
                df_scale_raw = pd.read_excel(uploaded_scale_file, header=0)

                st.session_state.df_real_status = process_uploaded_report(df_report_raw)
                st.session_state.df_escala, st.session_state.agent_groups = process_uploaded_scale(df_scale_raw)

                if not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
                    all_agents_report = set(st.session_state.df_real_status['Nome do agente'].unique())
                    all_agents_scale = set(st.session_state.df_escala['Nome do agente'].unique())
                    st.session_state.all_unique_agents = sorted(list(all_agents_report.union(all_agents_scale)))
                    st.success("Arquivos processados e dados carregados com sucesso!")
                    save_data_to_parquet() # Salvar após processamento
                else:
                    st.error("Erro ao processar um ou ambos os arquivos. Verifique os logs para mais detalhes.")
            except Exception as e:
                st.error(f"Erro ao processar os arquivos: {e}")
        else:
            st.warning("Por favor, faça upload de ambos os arquivos.")

    if st.button("Carregar Dados Salvos (Parquet)"):
        load_data_from_parquet()

with tab_groups:
    st.header("Grupos de Agentes por Carga Horária")
    if not st.session_state.agent_groups.empty:
        st.dataframe(st.session_state.agent_groups, use_container_width=True)
    else:
        st.info("Nenhum grupo de agentes por carga horária encontrado. Faça o upload e processe o arquivo de escala.")

with tab_metrics:
    st.header("Visualização e Métricas")

    # Filtros na barra lateral
    st.sidebar.header("Filtros")

    # Filtro por grupo de carga
    all_groups = ["Todos"] + sorted(st.session_state.agent_groups['Grupo_Carga'].unique().tolist()) if not st.session_state.agent_groups.empty else ["Todos"]
    selected_group = st.sidebar.selectbox("Filtrar por Grupo de Carga", all_groups, key="group_filter")

    # Filtrar agentes com base no grupo selecionado
    if selected_group != "Todos" and not st.session_state.agent_groups.empty:
        agents_in_group = st.session_state.agent_groups[st.session_state.agent_groups['Grupo_Carga'] == selected_group]['Agente'].tolist()
        available_agents_for_selection = [agent for agent in st.session_state.all_unique_agents if agent in agents_in_group]
    else:
        available_agents_for_selection = st.session_state.all_unique_agents

    selected_agents = st.sidebar.multiselect(
        "Selecione os Agentes",
        available_agents_for_selection,
        key="agent_selector"
    )

    today = datetime.now().date()
    start_date = st.sidebar.date_input("Data de Início", value=today - timedelta(days=7), key="start_date")
    end_date = st.sidebar.date_input("Data de Fim", value=today, key="end_date")

    start_date = datetime.combine(start_date, datetime.min.time())
    end_date = datetime.combine(end_date, datetime.max.time())

    if st.button("Gerar Gráfico e Métricas"):
        if selected_agents:
            df_chart_data = []

            # Adicionar dados de status real ao df_chart_data
            if not st.session_state.df_real_status.empty:
                filtered_real_status = st.session_state.df_real_status[
                    (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
                    (st.session_state.df_real_status['Hora de início do estado - Carimbo de data/hora'] >= start_date) &
                    (st.session_state.df_real_status['Hora de início do estado - Carimbo de data/hora'] <= end_date)
                ].copy() # Adicionado .copy() para evitar SettingWithCopyWarning

                for _, row in filtered_real_status.iterrows():
                    df_chart_data.append({
                        'Nome do agente': row['Nome do agente'],
                        'Data': row['Data'],
                        'Start': row['Hora de início do estado - Carimbo de data/hora'],
                        'Finish': row['Hora de término do estado - Carimbo de data/hora'],
                        'Tipo': row['Estado'],
                        'Label': f"{row['Estado']}: {row['Hora de início do estado - Carimbo de data/hora'].strftime('%H:%M')} - {row['Hora de término do estado - Carimbo de data/hora'].strftime('%H:%M')}",
                        'Categoria': 'Status Real'
                    })

            # Adicionar dados de escala ao df_chart_data
            if not st.session_state.df_escala.empty:
                filtered_escala = st.session_state.df_escala[
                    st.session_state.df_escala['Nome do agente'].isin(selected_agents)
                ]

                current_date_chart = start_date.date()
                while current_date_chart <= end_date.date():
                    day_of_week_num = current_date_chart.weekday()
                    daily_schedule = filtered_escala[filtered_escala['Dia da Semana Num'] == day_of_week_num]

                    for _, scale_entry in daily_schedule.iterrows():
                        scale_start_time = scale_entry['Entrada']
                        scale_end_time = scale_entry['Saída']

                        if pd.notna(scale_start_time) and pd.notna(scale_end_time):
                            scale_start_dt = datetime.combine(current_date_chart, scale_start_time)
                            scale_end_dt = datetime.combine(current_date_chart, scale_end_time)

                            if scale_end_dt < scale_start_dt:
                                scale_end_dt += timedelta(days=1)

                            df_chart_data.append({
                                'Nome do agente': scale_entry['Nome do agente'],
                                'Data': current_date_chart,
                                'Start': scale_start_dt,
                                'Finish': scale_end_dt,
                                'Tipo': 'Escala Planejada',
                                'Label': f"Escala: {scale_start_time.strftime('%H:%M')} - {scale_end_time.strftime('%H:%M')}",
                                'Categoria': 'Escala'
                            })
                    current_date_chart += timedelta(days=1)

            if df_chart_data:
                df_chart = pd.DataFrame(df_chart_data)

                # CONVERSÃO CRUCIAL AQUI: Garantir que 'Data' seja datetime
                df_chart['Data'] = pd.to_datetime(df_chart['Data']) 

                # Criar uma coluna combinada para o eixo Y
                df_chart['Agente_Data'] = df_chart['Nome do agente'] + ' - ' + df_chart['Data'].dt.strftime('%Y-%m-%d')

                # Ordenar para visualização
                df_chart['Tipo_Order'] = df_chart['Tipo'].apply(lambda x: 0 if x == 'Escala Planejada' else 1)
                df_chart = df_chart.sort_values(by=['Nome do agente', 'Data', 'Tipo_Order'])

                y_order = df_chart['Agente_Data'].unique().tolist()

                # Calcular altura do gráfico dinamicamente
                num_unique_rows = len(y_order)
                chart_height = max(400, num_unique_rows * 30) # Ajuste a altura conforme necessário

                fig = px.timeline(
                    df_chart,
                    x_start="Start",
                    x_end="Finish",
                    y="Agente_Data", # Eixo Y agora é Agente - Data
                    color="Tipo", # Colorir por tipo (Escala, Online, Away, Offline)
                    color_discrete_map={
                        'Escala Planejada': 'lightgray',
                        'Unified online': 'green',
                        'Unified away': 'orange',
                        'Unified offline': 'red',
                        'Unified transfers only': 'purple'
                    },
                    title="Linha do Tempo de Status e Escala dos Agentes",
                    height=chart_height
                )

                fig.update_yaxes(categoryorder='array', categoryarray=y_order)
                fig.update_xaxes(
                    title_text="Hora do Dia",
                    tickformat="%H:%M",
                    showgrid=True,
                    gridcolor='lightgray',
                    griddash='dot'
                )
                fig.update_yaxes(
                    title_text="Agente - Data",
                    showgrid=True,
                    gridcolor='lightgray',
                    griddash='dot'
                )
                fig.update_layout(hovermode="y unified")

                st.plotly_chart(fig, use_container_width=True)

                st.subheader("Métricas de Disponibilidade na Escala")
                if not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
                    df_metrics = calculate_metrics(
                        st.session_state.df_real_status,
                        st.session_state.df_escala,
                        selected_agents,
                        start_date,
                        end_date
                    )
                    if not df_metrics.empty:
                        st.dataframe(df_metrics, use_container_width=True)
                    else:
                        st.info("Nenhuma métrica calculada para os filtros selecionados. Verifique se há dados de escala e status real.")
                else:
                    st.info("Não há dados de status real e/ou escala para calcular as métricas com os filtros selecionados.")
            else:
                st.info("Nenhum dado para exibir no gráfico com os filtros selecionados.")
        else:
            st.warning("Por favor, selecione pelo menos um agente para a análise.")
    else:
        st.info("Por favor, faça o upload de ambos os arquivos na aba 'Upload de Dados' primeiro.")
