import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, time # Importar time explicitamente
import numpy as np
import unicodedata

# --- Funções de Normalização ---
def normalize_agent_name(name):
    if pd.isna(name):
        return name
    name = str(name).strip().upper()
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    return name

# --- Funções de Processamento de Dados ---
def process_uploaded_report(df):
    # Renomear colunas para facilitar o acesso
    df.columns = [
        'Nome do agente',
        'Dia',
        'Hora de início do estado - Carimbo de data/hora',
        'Hora de término do estado - Carimbo de data/hora',
        'Estado',
        'Duração'
    ]

    # Normalizar nomes dos agentes
    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Converter colunas de data/hora para o tipo datetime
    df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
    df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

    # Criar coluna 'Data' a partir da data de início
    df['Data'] = df['Hora de início do estado - Carimbo de data/hora'].dt.normalize()

    # Preencher NaT na coluna de término:
    # Se o estado termina no dia seguinte, preenche com o final do dia de início.
    # Se o estado não tem término (NaT), preenche com o final do dia de início.
    # Isso é uma heurística para garantir que todos os intervalos tenham um fim no mesmo dia para cálculos diários.
    for idx, row in df.iterrows():
        if pd.isna(row['Hora de término do estado - Carimbo de data/hora']):
            if pd.notna(row['Data']): # Verifica se a data de início é válida
                df.loc[idx, 'Hora de término do estado - Carimbo de data/hora'] = row['Data'] + timedelta(days=1) - timedelta(seconds=1)
            else:
                # Se a data de início também é inválida, marca para remoção
                df.loc[idx, 'Hora de término do estado - Carimbo de data/hora'] = pd.NaT
        elif row['Hora de término do estado - Carimbo de data/hora'].date() > row['Data'].date():
            df.loc[idx, 'Hora de término do estado - Carimbo de data/hora'] = row['Data'] + timedelta(days=1) - timedelta(seconds=1)

    # Remover linhas onde a data de início ou término ainda é NaT
    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora', 'Data'], inplace=True)

    return df

def to_time(val):
    if pd.isna(val):
        return None
    try:
        # Tenta converter para datetime e depois extrai a parte da hora
        # errors='coerce' transformará valores inválidos em NaT
        dt_val = pd.to_datetime(val, errors='coerce')
        if pd.notna(dt_val):
            return dt_val.time()
        return None
    except Exception:
        return None

def process_uploaded_scale(df):
    # Renomear colunas para facilitar o acesso
    df.rename(columns={'NOME': 'Nome do agente', 'DIAS DE ATENDIMENTO': 'Dias da Semana', 'ENTRADA': 'Entrada', 'SAÍDA': 'Saída'}, inplace=True)

    # Normalizar nomes dos agentes
    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Remover linhas onde o nome do agente é NaN ou vazio após normalização
    df.dropna(subset=['Nome do agente'], inplace=True)
    df = df[df['Nome do agente'] != '']

    # Converter horários de entrada e saída
    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    # Remover linhas onde a conversão de horário falhou
    df.dropna(subset=['Entrada', 'Saída'], inplace=True)

    # Mapeamento de dias da semana
    dias_map = {
        'SEG': 'Monday', 'TER': 'Tuesday', 'QUA': 'Wednesday', 'QUI': 'Thursday',
        'SEX': 'Friday', 'SAB': 'Saturday', 'DOM': 'Sunday'
    }

    # Expandir a escala para cada dia da semana
    expanded_scale_data = []
    for _, row in df.iterrows():
        dias_str = str(row['Dias da Semana']).upper().replace(' E ', ', ').replace(' E', ', ').replace('E ', ', ')
        dias = [d.strip() for d in dias_str.split(',') if d.strip()]

        for dia_abr in dias:
            # Pega as 3 primeiras letras para o mapeamento
            dia_completo = dias_map.get(dia_abr[:3], None)
            if dia_completo:
                expanded_scale_data.append({
                    'Nome do agente': row['Nome do agente'],
                    'Dia da Semana': dia_completo,
                    'Entrada': row['Entrada'],
                    'Saída': row['Saída']
                })

    return pd.DataFrame(expanded_scale_data)

# --- Funções de Cálculo de Métricas ---
def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    metrics_data = []

    # Itera por cada dia no intervalo de datas
    current_date_metrics = start_date
    while current_date_metrics <= end_date:
        day_of_week_str = current_date_metrics.strftime('%A') # Ex: 'Monday'

        for agent in selected_agents:
            # Filtra o status real para o agente e o dia atual
            agent_real_status_day = df_real_status[
                (df_real_status['Nome do agente'] == agent) &
                (df_real_status['Data'] == current_date_metrics)
            ]

            # Filtra a escala para o agente e o dia da semana atual
            agent_escala_day = df_escala[
                (df_escala['Nome do agente'] == agent) &
                (df_escala['Dia da Semana'] == day_of_week_str)
            ]

            total_scheduled_time_minutes = 0
            total_online_in_schedule_minutes = 0
            total_online_minutes = 0

            # Calcula o tempo online total para o dia
            for _, status_row in agent_real_status_day.iterrows():
                status_start_dt = status_row['Hora de início do estado - Carimbo de data/hora']
                status_end_dt = status_row['Hora de término do estado - Carimbo de data/hora']
                if status_row['Estado'] == 'Unified online':
                    total_online_minutes += (status_end_dt - status_start_dt).total_seconds() / 60

            if not agent_escala_day.empty:
                for _, escala_row in agent_escala_day.iterrows():
                    escala_start_time = escala_row['Entrada']
                    escala_end_time = escala_row['Saída']

                    # Cria objetos datetime para a escala do dia atual
                    escala_start_dt = datetime.combine(current_date_metrics, escala_start_time)
                    escala_end_dt = datetime.combine(current_date_metrics, escala_end_time)

                    # Se a escala termina no dia seguinte (ex: 23:00 - 07:00)
                    if escala_end_dt < escala_start_dt:
                        escala_end_dt += timedelta(days=1)

                    total_scheduled_time_minutes += (escala_end_dt - escala_start_dt).total_seconds() / 60

                    # Calcula a sobreposição com o status online
                    for _, status_row in agent_real_status_day.iterrows():
                        status_start_dt = status_row['Hora de início do estado - Carimbo de data/hora']
                        status_end_dt = status_row['Hora de término do estado - Carimbo de data/hora']
                        status_state = status_row['Estado']

                        if status_state == 'Unified online':
                            overlap_start = max(escala_start_dt, status_start_dt)
                            overlap_end = min(escala_end_dt, status_end_dt)

                            if overlap_end > overlap_start:
                                total_online_in_schedule_minutes += (overlap_end - overlap_start).total_seconds() / 60

                # Aderência: tempo online na escala / tempo online total
                # Disponibilidade: tempo online na escala / tempo total de escala
                disponibilidade = (total_online_in_schedule_minutes / total_scheduled_time_minutes * 100) if total_scheduled_time_minutes > 0 else 0
                aderencia = (total_online_in_schedule_minutes / total_online_minutes * 100) if total_online_minutes > 0 else 0

                metrics_data.append({
                    'Agente': agent,
                    'Data': current_date_metrics.strftime('%Y-%m-%d'),
                    'Disponibilidade na Escala (%)': f"{disponibilidade:.2f}%",
                    'Aderência ao Online (%)': f"{aderencia:.2f}%"
                })
            else:
                metrics_data.append({
                    'Agente': agent,
                    'Data': current_date_metrics.strftime('%Y-%m-%d'),
                    'Disponibilidade na Escala (%)': "N/A",
                    'Aderência ao Online (%)': "N/A"
                })
        current_date_metrics += timedelta(days=1)

    return pd.DataFrame(metrics_data)

# --- Configurações Iniciais do Streamlit ---
st.set_page_config(layout="wide", page_title="Dashboard de Acompanhamento de Call Center")
st.title("Dashboard de Acompanhamento de Equipe de Call Center")

# --- Inicialização de session_state ---
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'normalized_agents_escala' not in st.session_state:
    st.session_state.normalized_agents_escala = set()
if 'normalized_agents_real_status' not in st.session_state:
    st.session_state.normalized_agents_real_status = set()
if 'all_agents_combined' not in st.session_state:
    st.session_state.all_agents_combined = []
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}

# --- Abas de Navegação ---
tab1, tab2, tab3 = st.tabs(["Upload de Dados", "Gerenciar Grupos", "Visualização e Métricas"])

with tab1:
    st.header("Upload de Arquivos")

    uploaded_file_report = st.file_uploader("Escolha o arquivo de Relatório de Status (Excel)", type=["xlsx"], key="report_upload")
    if uploaded_file_report is not None:
        try:
            df_raw_report = pd.read_excel(uploaded_file_report, header=0)
            st.session_state.df_real_status = process_uploaded_report(df_raw_report.copy())
            st.success("Arquivo de Relatório de Status carregado e processado com sucesso!")
            st.write("Prévia do Relatório de Status:")
            st.dataframe(st.session_state.df_real_status.head())
            st.session_state.normalized_agents_real_status = set(st.session_state.df_real_status['Nome do agente'].unique())
        except Exception as e:
            st.error(f"Erro ao processar o relatório: {e}")

    uploaded_file_escala = st.file_uploader("Escolha o arquivo da Escala (Excel)", type=["xlsx"], key="escala_upload")
    if uploaded_file_escala is not None:
        try:
            df_raw_escala = pd.read_excel(uploaded_file_escala, header=0)
            st.session_state.df_escala = process_uploaded_scale(df_raw_escala.copy())
            st.success("Arquivo de Escala carregado e processado com sucesso!")
            st.write("Prévia da Escala:")
            st.dataframe(st.session_state.df_escala.head())
            st.session_state.normalized_agents_escala = set(st.session_state.df_escala['Nome do agente'].unique())
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de escala: {e}")

    # Atualizar lista combinada de agentes após uploads
    st.session_state.all_agents_combined = sorted(list(st.session_state.normalized_agents_real_status.union(st.session_state.normalized_agents_escala)))

    if st.session_state.all_agents_combined:
        st.subheader("Comparativo de Agentes entre Relatório e Escala")
        agents_only_in_report = st.session_state.normalized_agents_real_status - st.session_state.normalized_agents_escala
        agents_only_in_escala = st.session_state.normalized_agents_escala - st.session_state.normalized_agents_real_status
        agents_in_both = st.session_state.normalized_agents_real_status.intersection(st.session_state.normalized_agents_escala)

        if agents_only_in_report:
            st.warning(f"Agentes no relatório, mas NÃO na escala: {', '.join(sorted(list(agents_only_in_report)))}")
        if agents_only_in_escala:
            st.warning(f"Agentes na escala, mas NÃO no relatório: {', '.join(sorted(list(agents_only_in_escala)))}")
        if agents_in_both:
            st.success(f"Agentes presentes em ambos: {', '.join(sorted(list(agents_in_both)))}")
        else:
            st.info("Nenhum agente em comum entre o relatório e a escala ou nenhum arquivo carregado.")
    else:
        st.info("Carregue os arquivos para ver o comparativo de agentes.")

with tab2:
    st.header("Gerenciar Grupos de Agentes")

    if st.session_state.all_agents_combined:
        new_group_name = st.text_input("Nome do novo grupo:")
        if st.button("Criar Grupo") and new_group_name:
            if new_group_name not in st.session_state.agent_groups:
                st.session_state.agent_groups[new_group_name] = []
                st.success(f"Grupo '{new_group_name}' criado.")
            else:
                st.warning(f"Grupo '{new_group_name}' já existe.")

        if st.session_state.agent_groups:
            group_to_edit = st.selectbox("Selecionar grupo para editar:", list(st.session_state.agent_groups.keys()))
            if group_to_edit:
                current_members = st.session_state.agent_groups[group_to_edit]
                available_agents = [a for a in st.session_state.all_agents_combined if a not in current_members]

                selected_agents_for_group = st.multiselect(
                    f"Adicionar/Remover agentes do grupo '{group_to_edit}':",
                    st.session_state.all_agents_combined,
                    default=current_members
                )
                st.session_state.agent_groups[group_to_edit] = selected_agents_for_group
                st.success(f"Membros do grupo '{group_to_edit}' atualizados.")

            if st.button("Excluir Grupo", key="delete_group_btn"):
                if group_to_edit in st.session_state.agent_groups:
                    del st.session_state.agent_groups[group_to_edit]
                    st.success(f"Grupo '{group_to_edit}' excluído.")
                    st.rerun() # Recarrega para atualizar o selectbox
        else:
            st.info("Nenhum grupo criado ainda.")
    else:
        st.info("Carregue os arquivos de dados para gerenciar grupos de agentes.")

with tab3:
    st.header("Visualização e Métricas de Desempenho")

    # --- Filtros na Barra Lateral ---
    st.sidebar.header("Filtros")

    # Filtro de Grupo
    group_options = ["Todos os Agentes"] + list(st.session_state.agent_groups.keys())
    selected_group = st.sidebar.selectbox("Filtrar por Grupo:", group_options)

    # Filtro de Agentes
    if selected_group == "Todos os Agentes":
        available_agents_for_selection = st.session_state.all_agents_combined
    else:
        available_agents_for_selection = st.session_state.agent_groups.get(selected_group, [])
        if not available_agents_for_selection:
            st.sidebar.warning(f"O grupo '{selected_group}' não possui agentes.")

    selected_agents = st.sidebar.multiselect(
        "Selecionar Agentes:",
        available_agents_for_selection,
        default=available_agents_for_selection # Seleciona todos por padrão
    )

    # Filtro de Data
    today = datetime.now().date()
    default_start_date = today - timedelta(days=7)
    default_end_date = today

    date_range = st.sidebar.date_input(
        "Selecionar Intervalo de Datas:",
        value=(default_start_date, default_end_date),
        min_value=datetime(2020, 1, 1).date(),
        max_value=datetime(2030, 12, 31).date()
    )

    start_date = date_range[0] if len(date_range) > 0 else default_start_date
    end_date = date_range[1] if len(date_range) > 1 else start_date

    # Limitar o intervalo de datas para evitar sobrecarga no gráfico
    max_days_for_chart = 14
    if (end_date - start_date).days > max_days_for_chart:
        st.sidebar.warning(f"Intervalo de datas muito grande. Limitando a {max_days_for_chart} dias para o gráfico.")
        end_date = start_date + timedelta(days=max_days_for_chart - 1)
        st.sidebar.date_input(
            "Intervalo de Datas Ajustado:",
            value=(start_date, end_date),
            disabled=True # Desabilita para mostrar que foi ajustado
        )

    # --- Seção de Comparativo de Agentes ---
    if st.session_state.all_agents_combined:
        st.subheader("Comparativo de Agentes entre Relatório e Escala")
        agents_only_in_report = st.session_state.normalized_agents_real_status - st.session_state.normalized_agents_escala
        agents_only_in_escala = st.session_state.normalized_agents_escala - st.session_state.normalized_agents_real_status
        agents_in_both = st.session_state.normalized_agents_real_status.intersection(st.session_state.normalized_agents_escala)

        if agents_only_in_report:
            st.warning(f"Agentes no relatório, mas NÃO na escala: {', '.join(sorted(list(agents_only_in_report)))}")
        if agents_only_in_escala:
            st.warning(f"Agentes na escala, mas NÃO no relatório: {', '.join(sorted(list(agents_only_in_escala)))}")
        if agents_in_both:
            st.success(f"Agentes presentes em ambos: {', '.join(sorted(list(agents_in_both)))}")
        else:
            st.info("Nenhum agente em comum entre o relatório e a escala ou nenhum arquivo carregado.")
    else:
        st.info("Carregue os arquivos para ver o comparativo de agentes.")

    # --- Geração do Gráfico de Gantt ---
    st.subheader("Gráfico de Escala e Status")
    if selected_agents and not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
        df_chart_data = []

        # Iterar por cada dia no intervalo de datas
        current_date_chart = start_date
        while current_date_chart <= end_date:
            day_of_week_str = current_date_chart.strftime('%A') # Ex: 'Monday'

            for agent in selected_agents:
                # Adicionar dados da escala
                agent_escala_day = st.session_state.df_escala[
                    (st.session_state.df_escala['Nome do agente'] == agent) &
                    (st.session_state.df_escala['Dia da Semana'] == day_of_week_str)
                ]
                if not agent_escala_day.empty:
                    for _, escala_row in agent_escala_day.iterrows():
                        escala_start_time = escala_row['Entrada']
                        escala_end_time = escala_row['Saída']

                        # Criar objetos datetime para a escala do dia atual
                        escala_start_dt = datetime.combine(current_date_chart, escala_start_time)
                        escala_end_dt = datetime.combine(current_date_chart, escala_end_time)

                        # Se a escala termina no dia seguinte (ex: 23:00 - 07:00)
                        if escala_end_dt < escala_start_dt:
                            escala_end_dt += timedelta(days=1)

                        df_chart_data.append({
                            'Agente': agent,
                            'Data': current_date_chart,
                            'Start': escala_start_dt,
                            'End': escala_end_dt,
                            'Categoria': 'Escala',
                            'Status': 'Escala Planejada'
                        })

                # Adicionar dados de status real
                agent_real_status_day = st.session_state.df_real_status[
                    (st.session_state.df_real_status['Nome do agente'] == agent) &
                    (st.session_state.df_real_status['Data'] == current_date_chart)
                ]
                if not agent_real_status_day.empty:
                    for _, status_row in agent_real_status_day.iterrows():
                        df_chart_data.append({
                            'Agente': agent,
                            'Data': current_date_chart,
                            'Start': status_row['Hora de início do estado - Carimbo de data/hora'],
                            'End': status_row['Hora de término do estado - Carimbo de data/hora'],
                            'Categoria': 'Status Real',
                            'Status': status_row['Estado']
                        })
            current_date_chart += timedelta(days=1)

        if df_chart_data:
            df_chart = pd.DataFrame(df_chart_data)
            df_chart['Agente_Data_Tipo'] = df_chart['Agente'] + ' - ' + df_chart['Data'].dt.strftime('%Y-%m-%d') + ' (' + df_chart['Categoria'] + ')'

            # Mapeamento de cores para os status
            color_map = {
                'Escala Planejada': 'lightgrey',
                'Unified online': 'green',
                'Unified away': 'orange',
                'Unified offline': 'red',
                'Unified transfers only': 'purple'
            }

            # Altura dinâmica do gráfico
            num_unique_rows = df_chart['Agente_Data_Tipo'].nunique()
            chart_height = max(300, num_unique_rows * 30) # 30 pixels por linha

            fig = px.timeline(
                df_chart,
                x_start="Start",
                x_end="End",
                y="Agente_Data_Tipo",
                color="Status",
                color_discrete_map=color_map,
                title="Comparativo de Escala Planejada vs. Status Real do Agente",
                height=chart_height
            )

            fig.update_yaxes(categoryorder="array", categoryarray=df_chart['Agente_Data_Tipo'].unique())
            fig.update_xaxes(
                title_text="Hora do Dia",
                tickformat="%H:%M",
                range=[datetime.combine(start_date, time.min), datetime.combine(start_date, time.max)],
                showgrid=True, gridwidth=1, gridcolor='LightGrey'
            )
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGrey')
            fig.update_layout(
                hovermode="y unified",
                legend_title_text="Legenda",
                xaxis_range=[datetime.combine(start_date, time.min), datetime.combine(start_date, time.max)]
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhum dado de status real ou escala para exibir com os filtros selecionados.")
    else:
        st.info("Selecione os agentes e o intervalo de datas para visualizar o gráfico.")

    st.subheader("Métricas de Disponibilidade e Aderência")
    if selected_agents and not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
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
