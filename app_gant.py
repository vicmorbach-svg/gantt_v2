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
    if df.empty:
        return df

    new_rows = []
    for _, row in df.iterrows():
        start = row['Inicio']
        end = row['Fim']

        # Se o status termina no mesmo dia ou antes da meia-noite
        if start.date() == end.date() or end.time() == time(0, 0):
            new_rows.append(row)
        else:
            # Divide o status em duas partes: até meia-noite e depois da meia-noite
            current_day_end = datetime.combine(start.date(), time(23, 59, 59))
            next_day_start = datetime.combine(end.date(), time(0, 0, 0))

            # Parte do dia atual
            row_current_day = row.copy()
            row_current_day['Fim'] = current_day_end
            new_rows.append(row_current_day)

            # Parte do dia seguinte
            row_next_day = row.copy()
            row_next_day['Inicio'] = next_day_start
            new_rows.append(row_next_day)

    return pd.DataFrame(new_rows)

# --- Função para calcular a interseção de intervalos de tempo ---
def calculate_overlap_minutes(start1, end1, start2, end2):
    """Calcula a duração em minutos da sobreposição entre dois intervalos de tempo."""
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)
    if overlap_start < overlap_end:
        return (overlap_end - overlap_start).total_seconds() / 60
    return 0

# --- Funções de processamento de dados ---
@st.cache_data
def process_uploaded_report(uploaded_file):
    """Processa o arquivo de relatório de status dos agentes."""
    try:
        # Lê o arquivo Excel, especificando que não há cabeçalho na primeira linha
        # e renomeando as colunas conforme o layout do seu arquivo.
        df = pd.read_excel(uploaded_file, header=None)

        # Renomeia as colunas para facilitar o acesso
        df.columns = [
            'Nome do agente', 
            'Dia', 
            'Hora de início do estado - Carimbo de data/hora', 
            'Hora de término do estado - Carimbo de data/hora', 
            'Estado', 
            'Duração em minutos'
        ]

        # Converte as colunas de data/hora para o formato datetime
        df['Inicio'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'])
        df['Fim'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'])

        # Filtra linhas onde 'Inicio' ou 'Fim' são NaT (Not a Time)
        df = df.dropna(subset=['Inicio', 'Fim'])

        # Aplica a função para dividir status que atravessam a meia-noite
        df_processed = split_status_across_days(df.copy())

        # Adiciona a coluna 'Data' para facilitar o agrupamento por dia
        df_processed['Data'] = df_processed['Inicio'].dt.normalize()

        return df_processed
    except Exception as e:
        st.error(f"Erro ao processar o relatório: {e}")
        return pd.DataFrame()

@st.cache_data
def process_uploaded_schedule(uploaded_file):
    """Processa o arquivo de escala dos agentes."""
    try:
        df_escala = pd.read_excel(uploaded_file)

        # Renomeia as colunas para o padrão esperado
        df_escala = df_escala.rename(columns={
            'NOME': 'Nome do agente',
            'DIAS DE ATENDIMENTO': 'Dias da Semana',
            'ENTRADA': 'Entrada',
            'SAÍDA': 'Saida'
        })

        # Remove linhas onde 'Nome do agente' é NaN
        df_escala = df_escala.dropna(subset=['Nome do agente'])

        # Trata valores NaN nas colunas de horário antes de converter
        df_escala['Entrada'] = df_escala['Entrada'].fillna('00:00:00')
        df_escala['Saida'] = df_escala['Saida'].fillna('00:00:00')

        # Converte as colunas de horário para o formato de tempo
        # Se já for datetime, extrai apenas a parte do tempo
        df_escala['Entrada'] = df_escala['Entrada'].apply(lambda x: x.time() if isinstance(x, datetime) else pd.to_datetime(str(x)).time())
        df_escala['Saida'] = df_escala['Saida'].apply(lambda x: x.time() if isinstance(x, datetime) else pd.to_datetime(str(x)).time())

        # Expande os dias da semana
        expanded_escala = []
        for _, row in df_escala.iterrows():
            agente = row['Nome do agente']
            dias_str = str(row['Dias da Semana']).replace(' ', '').split(',')
            entrada = row['Entrada']
            saida = row['Saida']

            # Trata o caso "Seg e Qui loja, Ter, Qua e Sex Call"
            processed_dias = []
            for dia_item in dias_str:
                if 'loja' in dia_item or 'Call' in dia_item:
                    processed_dias.append(dia_item.split(' ')[0]) # Pega só o "Seg", "Qui", etc.
                else:
                    processed_dias.append(dia_item)

            for dia_abr in processed_dias:
                if dia_abr in dias_semana_map:
                    expanded_escala.append({
                        'Nome do agente': agente,
                        'Dia da Semana': dias_semana_map[dia_abr],
                        'Entrada': entrada,
                        'Saida': saida
                    })
        return pd.DataFrame(expanded_escala)
    except Exception as e:
        st.error(f"Erro ao processar o arquivo de escala: {e}")
        return pd.DataFrame()

# --- Inicialização do session_state ---
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'agente_groups' not in st.session_state:
    st.session_state.agente_groups = {} # {grupo: [agente1, agente2]}

# --- Abas ---
tab1, tab2, tab3 = st.tabs(["Upload de Relatório", "Criar/Editar Escala", "Visualização da Escala"])

with tab1:
    st.header("Upload do Relatório de Status dos Agentes")
    uploaded_file = st.file_uploader("Escolha um arquivo Excel do relatório de status", type=["xlsx"])

    if uploaded_file is not None:
        st.info("Processando o arquivo, por favor aguarde...")
        df_real_status_temp = process_uploaded_report(uploaded_file)
        if not df_real_status_temp.empty:
            st.session_state.df_real_status = df_real_status_temp
            st.success("Relatório de status carregado e processado com sucesso!")
            st.write("Prévia dos dados do relatório:")
            st.dataframe(st.session_state.df_real_status.head())
        else:
            st.error("Não foi possível processar o relatório. Verifique o formato do arquivo.")

with tab2:
    st.header("Criar/Editar Escala de Agentes")

    # Upload de arquivo de escala
    st.subheader("1. Carregar Escala via Arquivo Excel")
    uploaded_schedule_file = st.file_uploader("Escolha um arquivo Excel para a escala", type=["xlsx"], key="schedule_uploader")
    if uploaded_schedule_file is not None:
        st.info("Processando o arquivo de escala, por favor aguarde...")
        df_escala_temp = process_uploaded_schedule(uploaded_schedule_file)
        if not df_escala_temp.empty:
            st.session_state.df_escala = df_escala_temp
            st.success("Escala carregada e processada com sucesso!")
            st.write("Prévia dos dados da escala:")
            st.dataframe(st.session_state.df_escala.head())
        else:
            st.error("Não foi possível processar o arquivo de escala. Verifique o formato do arquivo.")

    st.subheader("2. Gerenciar Grupos de Agentes")

    # Obter todos os agentes disponíveis (do relatório e da escala)
    all_agents_in_data = set()
    if not st.session_state.df_real_status.empty:
        all_agents_in_data.update(st.session_state.df_real_status['Nome do agente'].unique())
    if not st.session_state.df_escala.empty:
        all_agents_in_data.update(st.session_state.df_escala['Nome do agente'].unique())

    available_agents = sorted(list(all_agents_in_data))

    # Seleção de grupo existente ou criação de novo
    group_options = ["- Selecione ou Crie um Grupo -"] + sorted(list(st.session_state.agente_groups.keys()))
    selected_group_name = st.selectbox("Selecione um grupo existente ou crie um novo:", group_options)

    new_group_name = ""
    if selected_group_name == "- Selecione ou Crie um Grupo -":
        new_group_name = st.text_input("Nome do novo grupo:")
        if new_group_name:
            selected_group_name = new_group_name

    if selected_group_name and selected_group_name != "- Selecione ou Crie um Grupo -":
        st.write(f"Gerenciando grupo: **{selected_group_name}**")

        current_group_agents = st.session_state.agente_groups.get(selected_group_name, [])

        # Multi-seleção de agentes para o grupo
        selected_agents_for_group = st.multiselect(
            f"Selecione os agentes para o grupo '{selected_group_name}':",
            options=available_agents,
            default=current_group_agents
        )

        if st.button(f"Salvar Agentes no Grupo '{selected_group_name}'"):
            st.session_state.agente_groups[selected_group_name] = selected_agents_for_group
            st.success(f"Grupo '{selected_group_name}' atualizado com sucesso!")
            st.experimental_rerun() # Recarrega para atualizar a lista de grupos

        if st.button(f"Excluir Grupo '{selected_group_name}'", key=f"delete_group_{selected_group_name}"):
            if selected_group_name in st.session_state.agente_groups:
                del st.session_state.agente_groups[selected_group_name]
                st.success(f"Grupo '{selected_group_name}' excluído com sucesso!")
                st.experimental_rerun()

    st.subheader("Grupos Atuais:")
    if st.session_state.agente_groups:
        for group, agents in st.session_state.agente_groups.items():
            st.write(f"**{group}**: {', '.join(agents)}")
    else:
        st.info("Nenhum grupo criado ainda.")


with tab3:
    st.header("Visualização da Escala e Status Real")

    if st.session_state.df_real_status.empty and st.session_state.df_escala.empty:
        st.warning("Por favor, carregue o relatório de status e/ou a escala nas abas anteriores para visualizar os dados.")
    else:
        # --- Filtros na barra lateral ---
        st.sidebar.header("Filtros")

        # Filtro de grupo
        all_groups = sorted(list(st.session_state.agente_groups.keys()))
        selected_groups = st.sidebar.multiselect("Filtrar por Grupo:", all_groups)

        # Determinar agentes baseados nos grupos selecionados
        filtered_agents_by_group = set()
        if selected_groups:
            for group in selected_groups:
                filtered_agents_by_group.update(st.session_state.agente_groups.get(group, []))

        # Obter todos os agentes disponíveis (do relatório e da escala)
        all_agents_for_filter = set()
        if not st.session_state.df_real_status.empty:
            all_agents_for_filter.update(st.session_state.df_real_status['Nome do agente'].unique())
        if not st.session_state.df_escala.empty:
            all_agents_for_filter.update(st.session_state.df_escala['Nome do agente'].unique())

        # Se grupos foram selecionados, restringir a lista de agentes aos agentes desses grupos
        if selected_groups:
            all_agents_for_filter = all_agents_for_filter.intersection(filtered_agents_by_group)

        available_agents_sorted = sorted(list(all_agents_for_filter))

        # Filtro de agente
        selected_agents = st.sidebar.multiselect(
            "Selecione os Agentes:",
            options=available_agents_sorted,
            default=available_agents_sorted if len(available_agents_sorted) <= 5 else [] # Seleciona todos se forem poucos, senão nenhum
        )

        # Filtro de data
        min_date = datetime(2026, 1, 1).date()
        max_date = datetime(2026, 12, 31).date()

        if not st.session_state.df_real_status.empty:
            min_date_report = st.session_state.df_real_status['Data'].min().date()
            max_date_report = st.session_state.df_real_status['Data'].max().date()
            min_date = min(min_date, min_date_report)
            max_date = max(max_date, max_date_report)

        if not st.session_state.df_escala.empty:
            # A escala não tem datas diretas, então não afeta min/max_date diretamente
            pass

        date_range = st.sidebar.date_input(
            "Selecione o Intervalo de Datas:",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )

        start_date = date_range[0]
        end_date = date_range[1] if len(date_range) > 1 else date_range[0]

        # --- Processamento e Visualização ---
        if selected_agents and (not st.session_state.df_real_status.empty or not st.session_state.df_escala.empty):

            df_plot_data = []
            metrics_data = []

            for agent in selected_agents:
                # Filtrar dados de status real para o agente e período
                df_agent_status = st.session_state.df_real_status[
                    (st.session_state.df_real_status['Nome do agente'] == agent) &
                    (st.session_state.df_real_status['Data'] >= pd.to_datetime(start_date)) &
                    (st.session_state.df_real_status['Data'] <= pd.to_datetime(end_date))
                ].copy()

                # Filtrar dados de escala para o agente
                df_agent_escala = st.session_state.df_escala[
                    st.session_state.df_escala['Nome do agente'] == agent
                ].copy()

                # Expandir a escala para o intervalo de datas selecionado
                expanded_agent_escala = []
                for single_date in pd.date_range(start=start_date, end=end_date):
                    day_of_week_str = single_date.strftime('%A') # Ex: 'Monday'

                    # Encontrar a escala para este dia da semana
                    escala_do_dia = df_agent_escala[df_agent_escala['Dia da Semana'] == day_of_week_str]

                    if not escala_do_dia.empty:
                        for _, row_escala in escala_do_dia.iterrows():
                            escala_inicio_time = row_escala['Entrada']
                            escala_fim_time = row_escala['Saida']

                            escala_inicio_dt = datetime.combine(single_date.date(), escala_inicio_time)
                            escala_fim_dt = datetime.combine(single_date.date(), escala_fim_time)

                            # Se a saída for 00:00:00, significa que termina no dia seguinte
                            if escala_fim_time == time(0, 0, 0):
                                escala_fim_dt = datetime.combine(single_date.date() + timedelta(days=1), time(0, 0, 0))

                            expanded_agent_escala.append({
                                'Nome do agente': agent,
                                'Data': single_date.normalize(),
                                'Inicio': escala_inicio_dt,
                                'Fim': escala_fim_dt,
                                'Tipo': 'Escala',
                                'Estado': 'Escala' # Para consistência no gráfico
                            })
                df_expanded_escala = pd.DataFrame(expanded_agent_escala)

                # Preparar dados de status real (apenas 'Unified online') para o gráfico
                df_online_status = df_agent_status[df_agent_status['Estado'] == 'Unified online'].copy()
                if not df_online_status.empty:
                    df_online_status['Tipo'] = 'Status Real (Online)'

                # Concatenar dados para o gráfico
                df_plot_agent = pd.concat([df_expanded_escala, df_online_status[['Nome do agente', 'Data', 'Inicio', 'Fim', 'Tipo', 'Estado']]])
                df_plot_data.append(df_plot_agent)

                # --- Cálculo de Métricas (Disponibilidade e Aderência) ---
                total_escala_min = 0
                total_online_na_escala_min = 0
                total_online_min = 0

                for _, escala_row in df_expanded_escala.iterrows():
                    escala_inicio = escala_row['Inicio']
                    escala_fim = escala_row['Fim']

                    duracao_escala = (escala_fim - escala_inicio).total_seconds() / 60
                    total_escala_min += duracao_escala

                    # Calcular tempo online dentro da escala
                    for _, status_row in df_online_status.iterrows():
                        status_inicio = status_row['Inicio']
                        status_fim = status_row['Fim']
                        total_online_na_escala_min += calculate_overlap_minutes(escala_inicio, escala_fim, status_inicio, status_fim)

                # Calcular tempo total online para o agente no período
                if not df_online_status.empty:
                    total_online_min = df_online_status['Duração em minutos'].sum()

                disponibilidade = (total_online_na_escala_min / total_escala_min) * 100 if total_escala_min > 0 else 0
                aderencia = (total_online_na_escala_min / total_online_min) * 100 if total_online_min > 0 else 0

                metrics_data.append({
                    'Nome do agente': agent,
                    'Disponibilidade (%)': disponibilidade,
                    'Aderência (%)': aderencia
                })

            if df_plot_data:
                df_final_plot = pd.concat(df_plot_data)

                # Ordenar para melhor visualização
                df_final_plot = df_final_plot.sort_values(by=['Nome do agente', 'Data', 'Inicio'])

                # Ajustar altura do gráfico dinamicamente
                num_agents = len(selected_agents)
                num_days = (end_date - start_date).days + 1
                chart_height = max(300, num_agents * num_days * 50) # Ajuste o multiplicador conforme necessário

                fig = px.timeline(
                    df_final_plot,
                    x_start="Inicio",
                    x_end="Fim",
                    y="Nome do agente",
                    color="Tipo",
                    facet_row="Data",
                    title="Comparativo de Escala vs. Status Real (Online)",
                    color_discrete_map={'Escala': 'blue', 'Status Real (Online)': 'green'},
                    height=chart_height
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
                st.dataframe(df_metrics.set_index('Nome do agente').style.format("{:.2f}%"))
            else:
                st.info("Nenhum dado para exibir com os filtros selecionados.")
        else:
            st.info("Selecione pelo menos um agente e certifique-se de que os dados foram carregados.")
