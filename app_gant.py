import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time

st.set_page_config(layout="wide", page_title="Dashboard de Escala e Status de Agentes")

st.title("📊 Dashboard de Escala e Status de Agentes")

# --- Mapeamento de dias da semana para facilitar a comparação ---
dias_semana_map = {
    "Seg": "Monday", "Ter": "Tuesday", "Qua": "Wednesday",
    "Qui": "Thursday", "Sex": "Friday", "Sab": "Saturday", "Dom": "Sunday"
}
dias_semana_map_inv = {v: k for k, v in dias_semana_map.items()}

# --- Função para dividir status que atravessam a meia-noite ---
def split_status_across_days(df):
    """
    Divide entradas de status que atravessam a meia-noite em múltiplas entradas,
    uma para cada dia.
    """
    new_rows = []
    for _, row in df.iterrows():
        start = row['Inicio']
        end = row['Fim']

        # Ignora linhas onde Inicio ou Fim são NaT (Not a Time)
        if pd.isna(start) or pd.isna(end):
            continue

        current_day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        next_day_start = current_day_start + timedelta(days=1)

        if start.date() == end.date():
            # Status termina no mesmo dia
            new_rows.append(row.to_dict())
        else:
            # Status atravessa a meia-noite
            # Parte 1: Do início até o final do primeiro dia
            row1 = row.copy()
            row1['Fim'] = next_day_start - timedelta(microseconds=1) # Um microsegundo antes da meia-noite
            new_rows.append(row1.to_dict())

            # Parte 2: Do início do segundo dia até o fim real
            row2 = row.copy()
            row2['Inicio'] = next_day_start
            new_rows.append(row2.to_dict())

            # Se atravessar mais de um dia, a lógica acima pode precisar de mais refinamento
            # para lidar com múltiplos dias completos entre start e end.
            # Por simplicidade, para este caso, estamos considerando apenas uma transição de meia-noite.
            # Para múltiplos dias, seria necessário um loop.

    return pd.DataFrame(new_rows) if new_rows else pd.DataFrame(columns=df.columns)


# --- Inicialização do session_state ---
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {} # {grupo: [agente1, agente2]}

# --- Função para processar o relatório de status ---
def process_uploaded_report(uploaded_file):
    try:
        # Lê o arquivo Excel sem cabeçalho na primeira linha
        df = pd.read_excel(uploaded_file, header=None)

        # Define os nomes das colunas manualmente
        # Baseado no arquivo Tempo_em_Status_do_agente_por_dia_03202026_1006.xlsx
        df.columns = [
            'Nome do agente',
            'Dia',
            'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora',
            'Estado',
            'Duração em minutos'
        ]

        # Converte as colunas de data/hora para o formato datetime
        # Usando errors='coerce' para transformar valores inválidos em NaT
        df['Inicio'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
        df['Fim'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

        # Converte 'Duração em minutos' para numérico, tratando erros
        df['Duração em minutos'] = pd.to_numeric(df['Duração em minutos'], errors='coerce')

        # Remove linhas onde 'Inicio' ou 'Fim' resultaram em NaT
        df.dropna(subset=['Inicio', 'Fim'], inplace=True)

        # Aplica a função para dividir status que atravessam a meia-noite
        df_processed = split_status_across_days(df.copy())

        # Garante que as colunas 'Inicio' e 'Fim' são datetimes após o split
        df_processed['Inicio'] = pd.to_datetime(df_processed['Inicio'])
        df_processed['Fim'] = pd.to_datetime(df_processed['Fim'])

        # Adiciona a coluna 'Data' para facilitar o agrupamento por dia
        df_processed['Data'] = df_processed['Inicio'].dt.normalize() # Apenas a parte da data

        st.session_state.df_real_status = df_processed
        st.success("Relatório de status carregado e processado com sucesso!")
    except Exception as e:
        st.error(f"Erro ao processar o relatório: {e}")
        st.session_state.df_real_status = pd.DataFrame() # Limpa o DataFrame em caso de erro

# --- Função para processar o arquivo de escala ---
def process_uploaded_escala(uploaded_file):
    try:
        df_escala_raw = pd.read_excel(uploaded_file)

        # Renomeia colunas para padronização
        df_escala_raw.rename(columns={
            'NOME': 'Nome do agente',
            'DIAS DE ATENDIMENTO': 'Dias da Semana',
            'ENTRADA': 'Entrada',
            'SAÍDA': 'Saída'
        }, inplace=True)

        # Remove linhas onde 'Nome do agente' é NaN
        df_escala_raw.dropna(subset=['Nome do agente'], inplace=True)

        # Trata valores NaN nas colunas de horário antes da conversão
        # Substitui NaN por um valor padrão ou remove a linha
        df_escala_raw['Entrada'] = df_escala_raw['Entrada'].fillna('00:00:00')
        df_escala_raw['Saída'] = df_escala_raw['Saída'].fillna('00:00:00')

        # Converte as colunas de hora para o formato de tempo
        # Usando errors='coerce' para transformar valores inválidos em NaT
        df_escala_raw['Entrada'] = pd.to_datetime(df_escala_raw['Entrada'], format='%H:%M:%S', errors='coerce').dt.time
        df_escala_raw['Saída'] = pd.to_datetime(df_escala_raw['Saída'], format='%H:%M:%S', errors='coerce').dt.time

        # Trata casos como '1900-01-01 00:00:00' que podem vir do Excel para 00:00:00
        # Isso pode ocorrer se o Excel interpretar 00:00:00 como uma data completa
        df_escala_raw['Saída'] = df_escala_raw['Saída'].apply(lambda x: time(0,0,0) if isinstance(x, datetime) and x.date() == datetime(1900,1,1).date() else x)


        # Remove linhas onde 'Entrada' ou 'Saída' resultaram em NaT
        df_escala_raw.dropna(subset=['Entrada', 'Saída'], inplace=True)

        # Expande a escala para cada dia da semana
        escala_expanded = []
        for index, row in df_escala_raw.iterrows():
            agente = row['Nome do agente']
            dias_str = str(row['Dias da Semana']).replace(' ', '').split(',')
            entrada = row['Entrada']
            saida = row['Saída']

            for dia_abr in dias_str:
                if dia_abr in dias_semana_map:
                    escala_expanded.append({
                        'Nome do agente': agente,
                        'Dia da Semana': dias_semana_map[dia_abr],
                        'Entrada': entrada,
                        'Saída': saida
                    })

        st.session_state.df_escala = pd.DataFrame(escala_expanded)
        st.success("Escala carregada e processada com sucesso!")
    except Exception as e:
        st.error(f"Erro ao processar o arquivo de escala: {e}")
        st.session_state.df_escala = pd.DataFrame() # Limpa o DataFrame em caso de erro


# --- Abas do aplicativo ---
tab1, tab2, tab3 = st.tabs(["Upload de Relatório", "Criar/Editar Escala", "Visualização da Escala"])

with tab1:
    st.header("Upload do Relatório de Status dos Agentes")
    uploaded_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) com o relatório de status", type=["xlsx"])
    if uploaded_file is not None:
        if st.button("Processar Relatório"):
            process_uploaded_report(uploaded_file)
            if not st.session_state.df_real_status.empty:
                st.write("Prévia do Relatório Processado:")
                st.dataframe(st.session_state.df_real_status.head())

with tab2:
    st.header("Criar/Editar Escala de Agentes")

    st.subheader("Upload de Escala via Excel")
    uploaded_escala_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) com a escala dos agentes", type=["xlsx"], key="escala_uploader")
    if uploaded_escala_file is not None:
        if st.button("Carregar Escala do Excel"):
            process_uploaded_escala(uploaded_escala_file)
            if not st.session_state.df_escala.empty:
                st.write("Prévia da Escala Carregada:")
                st.dataframe(st.session_state.df_escala.head())

    st.subheader("Gerenciar Grupos de Agentes")
    # Coleta todos os agentes únicos dos dados de status e da escala
    all_agents_in_data = set()
    if not st.session_state.df_real_status.empty:
        all_agents_in_data.update(st.session_state.df_real_status['Nome do agente'].unique())
    if not st.session_state.df_escala.empty:
        all_agents_in_data.update(st.session_state.df_escala['Nome do agente'].unique())

    available_agents = sorted(list(all_agents_in_data))

    new_group_name = st.text_input("Nome do novo grupo:")
    selected_agents_for_group = st.multiselect(
        "Selecione os agentes para este grupo:",
        options=available_agents,
        key="group_agents_selector"
    )
    if st.button("Salvar Grupo"):
        if new_group_name and selected_agents_for_group:
            st.session_state.agent_groups[new_group_name] = selected_agents_for_group
            st.success(f"Grupo '{new_group_name}' salvo com {len(selected_agents_for_group)} agentes.")
        else:
            st.warning("Por favor, insira um nome para o grupo e selecione pelo menos um agente.")

    st.subheader("Grupos Existentes")
    if st.session_state.agent_groups:
        for group_name, agents in st.session_state.agent_groups.items():
            st.write(f"**{group_name}**: {', '.join(agents)}")
            if st.button(f"Remover Grupo '{group_name}'", key=f"remove_group_{group_name}"):
                del st.session_state.agent_groups[group_name]
                st.experimental_rerun()
    else:
        st.info("Nenhum grupo criado ainda.")

with tab3:
    st.header("Visualização da Escala e Status Real")

    if st.session_state.df_real_status.empty and st.session_state.df_escala.empty:
        st.warning("Por favor, carregue o relatório de status e a escala nas abas anteriores.")
    else:
        # --- Filtros na barra lateral ---
        st.sidebar.header("Filtros")

        # Coleta todos os agentes únicos dos dados de status e da escala
        all_agents_for_filter = set()
        if not st.session_state.df_real_status.empty:
            all_agents_for_filter.update(st.session_state.df_real_status['Nome do agente'].unique())
        if not st.session_state.df_escala.empty:
            all_agents_for_filter.update(st.session_state.df_escala['Nome do agente'].unique())

        sorted_all_agents = sorted(list(all_agents_for_filter))

        # Filtro por Grupo
        group_options = ["Todos"] + list(st.session_state.agent_groups.keys())
        selected_group = st.sidebar.selectbox("Filtrar por Grupo:", options=group_options)

        filtered_agents_by_group = []
        if selected_group == "Todos":
            filtered_agents_by_group = sorted_all_agents
        elif selected_group in st.session_state.agent_groups:
            filtered_agents_by_group = st.session_state.agent_groups[selected_group]

        # Filtro de Agentes (agora depende do grupo selecionado)
        selected_agents = st.sidebar.multiselect(
            "Selecione os Agentes:",
            options=filtered_agents_by_group,
            default=filtered_agents_by_group # Seleciona todos os agentes do grupo por padrão
        )

        # Filtro de Data
        min_date = datetime(2026, 1, 1).date() # Data mínima padrão
        max_date = datetime(2026, 12, 31).date() # Data máxima padrão

        if not st.session_state.df_real_status.empty:
            min_date = min(min_date, st.session_state.df_real_status['Data'].min().date())
            max_date = max(max_date, st.session_state.df_real_status['Data'].max().date())
        if not st.session_state.df_escala.empty:
            # A escala não tem 'Data', então não afeta min/max diretamente, mas pode ser considerada
            pass # Manter min_date e max_date baseados no relatório

        date_range = st.sidebar.date_input(
            "Selecione o Intervalo de Datas:",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )

        start_date = date_range[0]
        end_date = date_range[1] if len(date_range) > 1 else date_range[0]

        if selected_agents and (not st.session_state.df_real_status.empty or not st.session_state.df_escala.empty):
            # --- Preparar dados para o gráfico ---
            df_plot_data = []
            metrics_data = []

            # Filtrar df_real_status
            df_filtered_real_status = st.session_state.df_real_status[
                (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
                (st.session_state.df_real_status['Data'] >= pd.to_datetime(start_date)) &
                (st.session_state.df_real_status['Data'] <= pd.to_datetime(end_date))
            ].copy() # Adicionado .copy() para evitar SettingWithCopyWarning

            # Filtrar df_escala e expandir para o intervalo de datas
            df_filtered_escala = st.session_state.df_escala[
                st.session_state.df_escala['Nome do agente'].isin(selected_agents)
            ].copy() # Adicionado .copy()

            expanded_escala_for_plot = []
            for agent in selected_agents:
                agent_escala = df_filtered_escala[df_filtered_escala['Nome do agente'] == agent]

                current_date = start_date
                while current_date <= end_date:
                    day_of_week_str = current_date.strftime('%A') # Ex: 'Monday'

                    # Mapeia o dia da semana de volta para o formato abreviado se necessário para comparação
                    # ou usa o mapeamento direto se a escala já estiver em inglês
                    escala_day_match = agent_escala[agent_escala['Dia da Semana'] == day_of_week_str]

                    if not escala_day_match.empty:
                        for _, row_escala in escala_day_match.iterrows():
                            escala_start_time = row_escala['Entrada']
                            escala_end_time = row_escala['Saída']

                            # Cria objetos datetime completos para a escala
                            escala_start_dt = datetime.combine(current_date, escala_start_time)
                            escala_end_dt = datetime.combine(current_date, escala_end_time)

                            # Se a saída for 00:00:00 e a entrada não for, significa que a escala termina no dia seguinte
                            if escala_end_time == time(0, 0, 0) and escala_start_time != time(0,0,0):
                                escala_end_dt = datetime.combine(current_date + timedelta(days=1), time(0,0,0))

                            expanded_escala_for_plot.append({
                                'Nome do agente': agent,
                                'Data': current_date,
                                'Inicio': escala_start_dt,
                                'Fim': escala_end_dt,
                                'Estado': 'Escala',
                                'Tipo': 'Escala'
                            })
                    current_date += timedelta(days=1)

            df_expanded_escala = pd.DataFrame(expanded_escala_for_plot)

            # Adicionar dados de status real (apenas 'Unified online')
            df_online_status = df_filtered_real_status[
                df_filtered_real_status['Estado'] == 'Unified online'
            ].copy()
            df_online_status['Tipo'] = 'Status Real (Online)'
            df_online_status['Estado'] = 'Status Real (Online)' # Para garantir que o label do hover seja claro

            # Concatenar dados para o gráfico
            if not df_expanded_escala.empty and not df_online_status.empty:
                df_plot = pd.concat([
                    df_expanded_escala[['Nome do agente', 'Data', 'Inicio', 'Fim', 'Estado', 'Tipo']],
                    df_online_status[['Nome do agente', 'Data', 'Inicio', 'Fim', 'Estado', 'Tipo']]
                ])
            elif not df_expanded_escala.empty:
                df_plot = df_expanded_escala[['Nome do agente', 'Data', 'Inicio', 'Fim', 'Estado', 'Tipo']]
            elif not df_online_status.empty:
                df_plot = df_online_status[['Nome do agente', 'Data', 'Inicio', 'Fim', 'Estado', 'Tipo']]
            else:
                df_plot = pd.DataFrame() # DataFrame vazio se não houver dados

            # --- Cálculo de Métricas ---
            for agent in selected_agents:
                for current_date_dt in pd.date_range(start=start_date, end=end_date, freq='D'):
                    current_date = current_date_dt.date()

                    # Escala do agente para o dia
                    agent_escala_day = df_expanded_escala[
                        (df_expanded_escala['Nome do agente'] == agent) &
                        (df_expanded_escala['Data'].dt.date == current_date)
                    ]

                    # Status online do agente para o dia
                    agent_online_status_day = df_online_status[
                        (df_online_status['Nome do agente'] == agent) &
                        (df_online_status['Data'].dt.date == current_date)
                    ]

                    total_escala_segundos = 0
                    total_online_na_escala_segundos = 0
                    total_online_segundos = 0

                    if not agent_escala_day.empty:
                        for _, row_escala in agent_escala_day.iterrows():
                            escala_inicio = row_escala['Inicio']
                            escala_fim = row_escala['Fim']
                            total_escala_segundos += (escala_fim - escala_inicio).total_seconds()

                            # Calcula tempo online DENTRO da escala
                            for _, row_online in agent_online_status_day.iterrows():
                                online_inicio = row_online['Inicio']
                                online_fim = row_online['Fim']

                                # Encontra a interseção entre o período de escala e o período online
                                intersection_start = max(escala_inicio, online_inicio)
                                intersection_end = min(escala_fim, online_fim)

                                if intersection_start < intersection_end:
                                    total_online_na_escala_segundos += (intersection_end - intersection_start).total_seconds()

                    if not agent_online_status_day.empty:
                        for _, row_online in agent_online_status_day.iterrows():
                            total_online_segundos += (row_online['Fim'] - row_online['Inicio']).total_seconds()

                    disponibilidade = (total_online_na_escala_segundos / total_escala_segundos * 100) if total_escala_segundos > 0 else 0
                    aderencia = (total_online_na_escala_segundos / total_online_segundos * 100) if total_online_segundos > 0 else 0

                    metrics_data.append({
                        'Nome do agente': agent,
                        'Data': current_date.strftime('%Y-%m-%d'),
                        'Disponibilidade (%)': disponibilidade,
                        'Aderência (%)': aderencia
                    })

            # --- Exibir Gráfico ---
            if not df_plot.empty:
                # Ordenar para garantir que 'Escala' venha antes de 'Status Real (Online)'
                df_plot['Tipo'] = pd.Categorical(df_plot['Tipo'], categories=['Escala', 'Status Real (Online)'], ordered=True)
                df_plot = df_plot.sort_values(by=['Nome do agente', 'Data', 'Tipo'])

                # Ajustar a altura do gráfico dinamicamente
                num_agents = len(selected_agents)
                num_days = (end_date - start_date).days + 1
                # Cada agente tem 2 linhas por dia (Escala e Status Real)
                base_height = 100 # Altura base por linha de agente/dia
                fig_height = max(400, num_agents * num_days * base_height / 2) # Ajuste para caber 2 barras por agente/dia

                fig = px.timeline(
                    df_plot,
                    x_start="Inicio",
                    x_end="Fim",
                    y="Nome do agente",
                    color="Tipo",
                    facet_row="Data",
                    color_discrete_map={'Escala': 'blue', 'Status Real (Online)': 'green'},
                    title="Comparativo de Escala vs. Status Real (Online)",
                    height=fig_height
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
                df_metrics = pd.DataFrame(metrics_data)
                # Agrupar por agente para exibir a média das métricas por agente
                df_metrics_agg = df_metrics.groupby('Nome do agente').agg(
                    {'Disponibilidade (%)': 'mean', 'Aderência (%)': 'mean'}
                ).reset_index()
                st.dataframe(df_metrics_agg.set_index('Nome do agente').style.format("{:.2f}%"))
            else:
                st.info("Nenhum dado para exibir com os filtros selecionados.")
        else:
            st.info("Selecione pelo menos um agente e certifique-se de que os dados foram carregados.")
