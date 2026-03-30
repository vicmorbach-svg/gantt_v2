import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, time
import numpy as np
import unicodedata

# --- Funções de Normalização ---
def normalize_agent_name(name):
    if pd.isna(name):
        return name
    name = str(name).strip().upper()
    # Remove acentos e caracteres especiais
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    return name

# --- Funções de Processamento de Dados ---
def process_uploaded_report(df):
    # Renomear colunas para facilitar o acesso
    # Assumindo que o arquivo de status real tem cabeçalhos na primeira linha
    df.columns = [
        'Nome do agente',
        'Dia',
        'Hora de início do estado - Carimbo de data/hora',
        'Hora de término do estado - Carimbo de data/hora',
        'Estado',
        'Duração'
    ]

    # Normalizar nomes dos agentes AQUI
    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Remover linhas onde o nome do agente é NaN ou vazio após normalização
    df.dropna(subset=['Nome do agente'], inplace=True)
    df = df[df['Nome do agente'] != '']

    # Converter colunas de data/hora
    df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
    df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

    # Preencher NaT em 'Hora de término' com o final do dia de 'Hora de início'
    # Isso é para status que ainda estão abertos ou não têm um término definido
    df['Hora de término do estado - Carimbo de data/hora'] = df.apply(
        lambda row: row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
        if pd.isna(row['Hora de término do estado - Carimbo de data/hora'])
        else row['Hora de término do estado - Carimbo de data/hora'],
        axis=1
    )

    # Remover linhas com datas/horas inválidas após a conversão
    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'], inplace=True)

    # Criar coluna 'Data' para o dia do evento
    df['Data'] = df['Hora de início do estado - Carimbo de data/hora'].dt.normalize()

    # Garantir que a duração seja numérica
    df['Duração'] = pd.to_numeric(df['Duração'], errors='coerce').fillna(0)

    return df

def to_time(val):
    # Converte um valor para um objeto datetime.time
    # Lida com formatos de hora (HH:MM:SS) e datetime completos (YYYY-MM-DD HH:MM:SS)
    if pd.isna(val):
        return None
    try:
        # Tenta converter para datetime e depois extrair a hora
        dt_obj = pd.to_datetime(val, errors='coerce')
        if pd.notna(dt_obj):
            return dt_obj.time()
        return None
    except Exception:
        return None

def process_uploaded_scale(df):
    # Renomear colunas para facilitar o acesso
    df.rename(columns={
        'NOME': 'Nome do agente',
        'DIAS DE ATENDIMENTO': 'Dias da Semana',
        'ENTRADA': 'Entrada',
        'SAÍDA': 'Saída'
    }, inplace=True)

    # Normalizar nomes dos agentes AQUI
    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Remover linhas onde o nome do agente é NaN ou vazio após normalização
    df.dropna(subset=['Nome do agente'], inplace=True)
    df = df[df['Nome do agente'] != '']

    # Converter horários de entrada e saída
    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    # Remover linhas com horários inválidos
    df.dropna(subset=['Entrada', 'Saída'], inplace=True)

    # Mapeamento de dias da semana
    dias_map = {
        'SEG': 0, 'TER': 1, 'QUA': 2, 'QUI': 3, 'SEX': 4, 'SAB': 5, 'DOM': 6
    }

    # Expandir a escala para cada dia da semana
    expanded_scale = []
    for index, row in df.iterrows():
        dias_atendimento_str = str(row['Dias da Semana']).upper().replace(' E ', ', ').replace(' E', ', ').replace('E ', ', ').replace('LOJA', '').replace('CALL', '').strip()
        dias_list = [d.strip()[:3] for d in dias_atendimento_str.split(',') if d.strip()] # Pega as 3 primeiras letras

        for dia_abbr in dias_list:
            if dia_abbr in dias_map:
                expanded_scale.append({
                    'Nome do agente': row['Nome do agente'],
                    'Dia da Semana Num': dias_map[dia_abbr],
                    'Entrada': row['Entrada'],
                    'Saída': row['Saída']
                })
    return pd.DataFrame(expanded_scale)

def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    metrics_results = []
    date_range = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]

    for agent in selected_agents:
        agent_status = df_real_status[df_real_status['Nome do agente'] == agent]
        agent_schedule = df_escala[df_escala['Nome do agente'] == agent]

        total_scheduled_time_minutes_agent = 0
        total_online_in_schedule_minutes_agent = 0
        total_online_minutes_agent = 0

        for current_date in date_range:
            day_of_week_num = current_date.weekday() # 0=Seg, 6=Dom

            # Filtrar escala para o dia da semana atual
            daily_schedule = agent_schedule[agent_schedule['Dia da Semana Num'] == day_of_week_num]

            # Filtrar status real para o dia atual
            daily_status = agent_status[agent_status['Data'] == current_date]

            # Calcular tempo total de escala para o dia
            for _, schedule_row in daily_schedule.iterrows():
                schedule_start_time = schedule_row['Entrada']
                schedule_end_time = schedule_row['Saída']

                if schedule_start_time and schedule_end_time:
                    schedule_start_dt = datetime.combine(current_date, schedule_start_time)
                    schedule_end_dt = datetime.combine(current_date, schedule_end_time)

                    # Se a escala passa da meia-noite, ajustar o final para o dia seguinte
                    if schedule_end_dt < schedule_start_dt:
                        schedule_end_dt += timedelta(days=1)

                    total_scheduled_time_minutes_agent += (schedule_end_dt - schedule_start_dt).total_seconds() / 60

                    # Calcular tempo online dentro da escala
                    for _, status_row in daily_status.iterrows():
                        if status_row['Estado'] == 'Unified online':
                            status_start_dt = status_row['Hora de início do estado - Carimbo de data/hora']
                            status_end_dt = status_row['Hora de término do estado - Carimbo de data/hora']

                            # Ajustar status_end_dt se ele for no dia seguinte ao status_start_dt para o cálculo diário
                            if status_end_dt.date() > status_start_dt.date():
                                status_end_dt = datetime.combine(status_start_dt.date(), time(23, 59, 59))

                            overlap_start = max(schedule_start_dt, status_start_dt)
                            overlap_end = min(schedule_end_dt, status_end_dt)

                            if overlap_end > overlap_start:
                                online_duration_in_overlap = (overlap_end - overlap_start).total_seconds() / 60
                                total_online_in_schedule_minutes_agent += online_duration_in_overlap

            # Calcular tempo total online para o dia (para aderência)
            for _, status_row in daily_status.iterrows():
                if status_row['Estado'] == 'Unified online':
                    status_start_dt = status_row['Hora de início do estado - Carimbo de data/hora']
                    status_end_dt = status_row['Hora de término do estado - Carimbo de data/hora']

                    # Ajustar status_end_dt se ele for no dia seguinte ao status_start_dt para o cálculo diário
                    if status_end_dt.date() > status_start_dt.date():
                        status_end_dt = datetime.combine(status_start_dt.date(), time(23, 59, 59))

                    total_online_minutes_agent += (status_end_dt - status_start_dt).total_seconds() / 60

        # Calcular métricas finais para o agente no período
        availability_percentage = (total_online_in_schedule_minutes_agent / total_scheduled_time_minutes_agent * 100) if total_scheduled_time_minutes_agent > 0 else 0
        adherence_percentage = (total_online_in_schedule_minutes_agent / total_online_minutes_agent * 100) if total_online_minutes_agent > 0 else 0

        metrics_results.append({
            'Agente': agent,
            'Total Tempo Escala (min)': round(total_scheduled_time_minutes_agent, 2),
            'Total Tempo Online na Escala (min)': round(total_online_in_schedule_minutes_agent, 2),
            'Total Tempo Online (min)': round(total_online_minutes_agent, 2),
            'Disponibilidade na Escala (%)': f"{availability_percentage:.2f}%",
            'Aderência (%)': f"{adherence_percentage:.2f}%"
        })

    return pd.DataFrame(metrics_results)


# --- Interface do Streamlit ---
st.sidebar.header("Filtros e Configurações")

# Abas principais
tab_upload, tab_groups, tab_visualization = st.tabs(["Upload de Dados", "Gerenciar Grupos", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Dados")

    uploaded_report_file = st.file_uploader("Faça upload do relatório de status do agente (Excel)", type=["xlsx"], key="report_uploader")
    if uploaded_report_file is not None:
        try:
            df_report_raw = pd.read_excel(uploaded_report_file, header=None) # Ler sem cabeçalho para atribuir manualmente
            st.session_state.df_real_status = process_uploaded_report(df_report_raw.copy())
            st.success("Relatório de status carregado e processado com sucesso!")
            st.dataframe(st.session_state.df_real_status.head())
        except Exception as e:
            st.error(f"Erro ao processar o relatório: {e}")

    uploaded_scale_file = st.file_uploader("Faça upload do arquivo de escala (Excel)", type=["xlsx"], key="scale_uploader")
    if uploaded_scale_file is not None:
        try:
            df_scale_raw = pd.read_excel(uploaded_scale_file) # O arquivo de escala tem cabeçalhos
            st.session_state.df_escala = process_uploaded_scale(df_scale_raw.copy())
            st.success("Arquivo de escala carregado e processado com sucesso!")
            st.dataframe(st.session_state.df_escala.head())
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de escala: {e}")

with tab_groups:
    st.header("Gerenciar Grupos")

    if 'df_real_status' in st.session_state and not st.session_state.df_real_status.empty:
        all_agents = sorted(st.session_state.df_real_status['Nome do agente'].unique())
    elif 'df_escala' in st.session_state and not st.session_state.df_escala.empty:
        all_agents = sorted(st.session_state.df_escala['Nome do agente'].unique())
    else:
        all_agents = []

    if 'agent_groups' not in st.session_state:
        st.session_state.agent_groups = {
            '6h20min': [],
            '8h12min': []
        }

    group_name = st.text_input("Nome do novo grupo:")
    if st.button("Criar Grupo") and group_name:
        if group_name not in st.session_state.agent_groups:
            st.session_state.agent_groups[group_name] = []
            st.success(f"Grupo '{group_name}' criado.")
        else:
            st.warning(f"Grupo '{group_name}' já existe.")

    st.subheader("Adicionar/Remover Agentes dos Grupos")
    selected_group_to_edit = st.selectbox("Selecione um grupo para editar:", list(st.session_state.agent_groups.keys()))

    if selected_group_to_edit:
        current_agents_in_group = st.session_state.agent_groups[selected_group_to_edit]
        available_agents_for_group = [agent for agent in all_agents if agent not in current_agents_in_group]

        agents_to_add = st.multiselect(f"Adicionar agentes ao grupo '{selected_group_to_edit}':", available_agents_for_group)
        if st.button(f"Adicionar selecionados ao '{selected_group_to_edit}'"):
            st.session_state.agent_groups[selected_group_to_edit].extend(agents_to_add)
            st.session_state.agent_groups[selected_group_to_edit] = sorted(list(set(st.session_state.agent_groups[selected_group_to_edit]))) # Remove duplicatas e ordena
            st.success(f"Agentes adicionados ao grupo '{selected_group_to_edit}'.")

        agents_to_remove = st.multiselect(f"Remover agentes do grupo '{selected_group_to_edit}':", current_agents_in_group)
        if st.button(f"Remover selecionados do '{selected_group_to_edit}'"):
            st.session_state.agent_groups[selected_group_to_edit] = [agent for agent in current_agents_in_group if agent not in agents_to_remove]
            st.success(f"Agentes removidos do grupo '{selected_group_to_edit}'.")

    st.subheader("Grupos Atuais")
    for group, agents in st.session_state.agent_groups.items():
        st.write(f"**{group}**: {', '.join(agents) if agents else 'Nenhum agente'}")

with tab_visualization:
    st.header("Visualização e Métricas")

    # --- Comparativo de Agentes ---
    st.subheader("Comparativo de Agentes entre Arquivos")
    if 'df_real_status' in st.session_state and not st.session_state.df_real_status.empty and \
       'df_escala' in st.session_state and not st.session_state.df_escala.empty:

        agents_in_report = set(st.session_state.df_real_status['Nome do agente'].unique())
        agents_in_scale = set(st.session_state.df_escala['Nome do agente'].unique())

        only_in_report = sorted(list(agents_in_report - agents_in_scale))
        only_in_scale = sorted(list(agents_in_scale - agents_in_report))
        in_both = sorted(list(agents_in_report.intersection(agents_in_scale)))

        if only_in_report:
            st.warning(f"Agentes no relatório de status, mas NÃO na escala: {', '.join(only_in_report)}")
        if only_in_scale:
            st.warning(f"Agentes na escala, mas NÃO no relatório de status: {', '.join(only_in_scale)}")
        if in_both:
            st.info(f"Agentes presentes em AMBOS os arquivos: {', '.join(in_both)}")
        if not only_in_report and not only_in_scale:
            st.success("Todos os agentes estão presentes em ambos os arquivos (relatório de status e escala).")
    else:
        st.info("Faça o upload de ambos os arquivos para ver o comparativo de agentes.")

    # --- Filtros na barra lateral ---
    st.sidebar.subheader("Seleção de Agentes e Período")

    all_available_agents = set()
    if 'df_real_status' in st.session_state and not st.session_state.df_real_status.empty:
        all_available_agents.update(st.session_state.df_real_status['Nome do agente'].unique())
    if 'df_escala' in st.session_state and not st.session_state.df_escala.empty:
        all_available_agents.update(st.session_state.df_escala['Nome do agente'].unique())

    all_available_agents = sorted(list(all_available_agents))

    selected_groups = st.sidebar.multiselect(
        "Filtrar por Grupo:",
        list(st.session_state.agent_groups.keys()) if 'agent_groups' in st.session_state else [],
        key="group_filter"
    )

    agents_from_groups = set()
    if selected_groups:
        for group in selected_groups:
            agents_from_groups.update(st.session_state.agent_groups.get(group, []))

    if agents_from_groups:
        # Se grupos foram selecionados, o multiselect de agentes deve mostrar apenas os agentes desses grupos
        selected_agents = st.sidebar.multiselect(
            "Selecione os Agentes:",
            sorted(list(agents_from_groups)),
            key="agent_filter"
        )
    else:
        # Se nenhum grupo foi selecionado, mostra todos os agentes disponíveis
        selected_agents = st.sidebar.multiselect(
            "Selecione os Agentes:",
            all_available_agents,
            key="agent_filter"
        )

    # Definir datas padrão para o filtro
    default_start_date = datetime.now().date() - timedelta(days=7)
    default_end_date = datetime.now().date()

    if 'df_real_status' in st.session_state and not st.session_state.df_real_status.empty:
        min_date_data = st.session_state.df_real_status['Data'].min().date()
        max_date_data = st.session_state.df_real_status['Data'].max().date()
        default_start_date = max(min_date_data, default_start_date)
        default_end_date = min(max_date_data, default_end_date)
    else:
        min_date_data = datetime(2023, 1, 1).date() # Data mínima arbitrária
        max_date_data = datetime(2027, 12, 31).date() # Data máxima arbitrária


    start_date = st.sidebar.date_input("Data de Início:", value=default_start_date, min_value=min_date_data, max_value=max_date_data)
    end_date = st.sidebar.date_input("Data de Fim:", value=default_end_date, min_value=min_date_data, max_value=max_date_data)

    if start_date > end_date:
        st.sidebar.error("Erro: A data de início deve ser anterior ou igual à data de fim.")
        selected_agents = [] # Impede a geração do gráfico se as datas estiverem inválidas

    # --- Geração do Gráfico de Gantt ---
    st.subheader("Gráfico de Escala e Status Real")
    if selected_agents and not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
        if len(selected_agents) > 10:
            st.warning("Muitos agentes selecionados. O gráfico pode ficar sobrecarregado. Considere reduzir a seleção.")

        # Filtrar dados de status real
        filtered_df_real_status = st.session_state.df_real_status[
            (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
            (st.session_state.df_real_status['Data'] >= pd.to_datetime(start_date)) &
            (st.session_state.df_real_status['Data'] <= pd.to_datetime(end_date))
        ].copy()

        # Filtrar dados de escala
        filtered_df_escala = st.session_state.df_escala[
            st.session_state.df_escala['Nome do agente'].isin(selected_agents)
        ].copy()

        if not filtered_df_real_status.empty or not filtered_df_escala.empty:
            df_chart_data = []

            # Adicionar dados de status real
            for _, row in filtered_df_real_status.iterrows():
                df_chart_data.append({
                    'Agente': row['Nome do agente'],
                    'Data': row['Data'],
                    'Início': row['Hora de início do estado - Carimbo de data/hora'],
                    'Fim': row['Hora de término do estado - Carimbo de data/hora'],
                    'Estado': row['Estado'],
                    'Categoria': 'Status Real'
                })

            # Adicionar dados de escala planejada
            date_range_for_chart = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
            for agent in selected_agents:
                agent_schedule = filtered_df_escala[filtered_df_escala['Nome do agente'] == agent]
                for current_date in date_range_for_chart:
                    day_of_week_num = current_date.weekday() # 0=Seg, 6=Dom
                    daily_schedule = agent_schedule[agent_schedule['Dia da Semana Num'] == day_of_week_num]

                    for _, schedule_row in daily_schedule.iterrows():
                        schedule_start_time = schedule_row['Entrada']
                        schedule_end_time = schedule_row['Saída']

                        if schedule_start_time and schedule_end_time:
                            schedule_start_dt = datetime.combine(current_date, schedule_start_time)
                            schedule_end_dt = datetime.combine(current_date, schedule_end_time)

                            # Se a escala passa da meia-noite, ajustar o final para o dia seguinte
                            if schedule_end_dt < schedule_start_dt:
                                schedule_end_dt += timedelta(days=1)

                            df_chart_data.append({
                                'Agente': agent,
                                'Data': current_date,
                                'Início': schedule_start_dt,
                                'Fim': schedule_end_dt,
                                'Estado': 'Escala Planejada',
                                'Categoria': 'Escala'
                            })

            df_chart = pd.DataFrame(df_chart_data)

            if not df_chart.empty:
                # Criar uma coluna combinada para o eixo Y para separar as barras de escala e status
                df_chart['Agente_Data_Tipo'] = df_chart['Agente'] + ' - ' + df_chart['Data'].dt.strftime('%Y-%m-%d') + ' (' + df_chart['Categoria'] + ')'

                # Ordenar para melhor visualização
                df_chart = df_chart.sort_values(by=['Agente', 'Data', 'Categoria', 'Início'])

                # Definir cores para os estados e categorias
                color_map = {
                    'Unified online': 'green',
                    'Unified away': 'orange',
                    'Unified offline': 'red',
                    'Unified transfers only': 'purple',
                    'Escala Planejada': 'blue'
                }

                # Ajustar altura do gráfico dinamicamente
                num_unique_y_values = df_chart['Agente_Data_Tipo'].nunique()
                chart_height = max(500, num_unique_y_values * 30) # 30 pixels por linha, mínimo de 500

                fig = px.timeline(
                    df_chart,
                    x_start="Início",
                    x_end="Fim",
                    y="Agente_Data_Tipo",
                    color="Estado",
                    color_discrete_map=color_map,
                    title="Comparativo de Escala Planejada vs. Status Real do Agente",
                    hover_name="Agente",
                    hover_data={"Data": "|%Y-%m-%d", "Início": "|%H:%M:%S", "Fim": "|%H:%M:%S", "Estado": True, "Categoria": True},
                    height=chart_height
                )

                fig.update_yaxes(
                    categoryorder="array",
                    categoryarray=df_chart['Agente_Data_Tipo'].unique(), # Garante a ordem correta
                    title_text="" # Remove o título do eixo Y
                )

                fig.update_xaxes(
                    title_text="Horário do Dia",
                    tickformat="%H:%M",
                    showgrid=True, gridwidth=1, gridcolor='LightGrey', # Grade visível
                    range=[datetime.combine(start_date, time.min), datetime.combine(start_date, time.max)]
                )
                fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGrey') # Grade visível no eixo Y

                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nenhum dado de status real ou escala para exibir com os filtros selecionados.")
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
