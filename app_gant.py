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
        start = row['Hora de início do estado - Carimbo de data/hora']
        end = row['Hora de término do estado - Carimbo de data/hora']

        # Certifica-se de que 'end' não é NaT antes de prosseguir
        if pd.isna(end):
            # Se o término for NaN, tratamos como um status que continua indefinidamente
            # Para fins de cálculo diário, podemos limitar ao final do dia atual
            end_of_day = start.replace(hour=23, minute=59, second=59, microsecond=999999)
            if start.date() == end_of_day.date():
                new_rows.append(row.to_dict())
            else:
                # Se o status sem fim começa em um dia e continua,
                # a primeira parte vai até o fim do dia
                row_copy = row.copy()
                row_copy['Hora de término do estado - Carimbo de data/hora'] = end_of_day
                new_rows.append(row_copy.to_dict())
                # E o restante é ignorado ou tratado de outra forma, dependendo da necessidade.
                # Para este caso, vamos considerar apenas o que está no dia de início.
            continue

        current_day = start.date()
        while start.date() < end.date():
            end_of_day = datetime(start.year, start.month, start.day, 23, 59, 59, 999999)
            if start < end_of_day: # Garante que há um intervalo válido no dia
                new_row = row.copy()
                new_row['Hora de início do estado - Carimbo de data/hora'] = start
                new_row['Hora de término do estado - Carimbo de data/hora'] = end_of_day
                new_rows.append(new_row.to_dict())
            start = end_of_day + timedelta(microseconds=1)
            start = start.replace(hour=0, minute=0, second=0, microsecond=0) # Garante que o próximo dia começa à meia-noite
            current_day = start.date()

        # Adiciona a parte final do status (ou o status completo se não atravessou a meia-noite)
        if start < end: # Garante que há um intervalo válido
            new_row = row.copy()
            new_row['Hora de início do estado - Carimbo de data/hora'] = start
            new_row['Hora de término do estado - Carimbo de data/hora'] = end
            new_rows.append(new_row.to_dict())

    if not new_rows:
        return pd.DataFrame(columns=df.columns)

    return pd.DataFrame(new_rows)

# --- Funções para calcular disponibilidade e aderência ---
def calculate_metrics(df_real_status, df_schedule_expanded, selected_agents, start_date, end_date):
    metrics_data = []

    # Filtra os dados de status real para 'Unified online' e dentro do período
    df_online = df_real_status[
        (df_real_status['Estado'] == 'Unified online') &
        (df_real_status['Data'].dt.date >= start_date) &
        (df_real_status['Data'].dt.date <= end_date)
    ].copy()

    # Filtra a escala para o período
    df_schedule_filtered = df_schedule_expanded[
        (df_schedule_expanded['Data'].dt.date >= start_date) &
        (df_schedule_expanded['Data'].dt.date <= end_date)
    ].copy()

    for agent in selected_agents:
        agent_online_df = df_online[df_online['Nome do agente'] == agent]
        agent_schedule_df = df_schedule_filtered[df_schedule_filtered['Nome do agente'] == agent]

        total_scheduled_time_minutes = 0
        total_online_time_minutes = 0
        online_within_schedule_minutes = 0

        # Agrupa por dia para calcular as métricas diárias
        for day in pd.date_range(start_date, end_date):
            day_str = day.strftime('%Y-%m-%d')

            # Tempo de escala para o dia
            daily_schedule = agent_schedule_df[agent_schedule_df['Data'].dt.date == day.date()]
            daily_scheduled_minutes = 0
            for _, sch_row in daily_schedule.iterrows():
                sch_start = sch_row['Hora de início do estado - Carimbo de data/hora']
                sch_end = sch_row['Hora de término do estado - Carimbo de data/hora']
                daily_scheduled_minutes += (sch_end - sch_start).total_seconds() / 60
            total_scheduled_time_minutes += daily_scheduled_minutes

            # Tempo online para o dia
            daily_online = agent_online_df[agent_online_df['Data'].dt.date == day.date()]
            daily_online_minutes = 0
            for _, online_row in daily_online.iterrows():
                online_start = online_row['Hora de início do estado - Carimbo de data/hora']
                online_end = online_row['Hora de término do estado - Carimbo de data/hora']
                daily_online_minutes += (online_end - online_start).total_seconds() / 60
            total_online_time_minutes += daily_online_minutes

            # Tempo online dentro da escala
            for _, sch_row in daily_schedule.iterrows():
                sch_start = sch_row['Hora de início do estado - Carimbo de data/hora']
                sch_end = sch_row['Hora de término do estado - Carimbo de data/hora']

                for _, online_row in daily_online.iterrows():
                    online_start = online_row['Hora de início do estado - Carimbo de data/hora']
                    online_end = online_row['Hora de término do estado - Carimbo de data/hora']

                    # Calcula a interseção dos intervalos
                    overlap_start = max(sch_start, online_start)
                    overlap_end = min(sch_end, online_end)

                    if overlap_start < overlap_end:
                        online_within_schedule_minutes += (overlap_end - overlap_start).total_seconds() / 60

        # Evita divisão por zero
        disponibilidade = (online_within_schedule_minutes / total_scheduled_time_minutes) * 100 if total_scheduled_time_minutes > 0 else 0
        aderencia = (online_within_schedule_minutes / total_online_time_minutes) * 100 if total_online_time_minutes > 0 else 0

        metrics_data.append({
            'Nome do agente': agent,
            'Total Escala (min)': total_scheduled_time_minutes,
            'Total Online (min)': total_online_time_minutes,
            'Online na Escala (min)': online_within_schedule_minutes,
            'Disponibilidade (%)': disponibilidade,
            'Aderência (%)': aderencia
        })

    return pd.DataFrame(metrics_data)


# --- Inicialização do session_state ---
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'df_schedule' not in st.session_state:
    st.session_state.df_schedule = pd.DataFrame(columns=['Nome do agente', 'Dia da semana', 'Hora de início', 'Hora de término', 'Grupo'])
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}

# --- Abas ---
tab1, tab2, tab3 = st.tabs(["Upload de Relatório", "Criar/Editar Escala", "Visualização da Escala"])

with tab1:
    st.header("Upload do Relatório de Status dos Agentes")
    uploaded_file = st.file_uploader("Escolha um arquivo Excel", type=["xlsx"])

    if uploaded_file is not None:
        try:
            df_raw = pd.read_excel(uploaded_file)
            st.write("Prévia do arquivo carregado:")
            st.dataframe(df_raw.head())

            # Renomear colunas para padronização, se necessário
            df_raw.rename(columns={
                'Nome do agente': 'Nome do agente',
                'Dia': 'Dia',
                'Hora de início do estado - Carimbo de data/hora': 'Hora de início do estado - Carimbo de data/hora',
                'Hora de término do estado - Carimbo de data/hora': 'Hora de término do estado - Carimbo de data/hora',
                'Estado': 'Estado',
                'Duração em minutos': 'Duração em minutos'
            }, inplace=True)

            # Converter colunas de data/hora
            df_raw['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df_raw['Hora de início do estado - Carimbo de data/hora'])
            df_raw['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df_raw['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

            # Adicionar coluna 'Data' para facilitar filtros
            df_raw['Data'] = df_raw['Hora de início do estado - Carimbo de data/hora'].dt.normalize()

            # Processar status que atravessam a meia-noite
            df_processed = split_status_across_days(df_raw)
            df_processed['Data'] = df_processed['Hora de início do estado - Carimbo de data/hora'].dt.normalize()

            st.session_state.df_real_status = df_processed
            st.success("Relatório de status carregado e processado com sucesso!")

        except Exception as e:
            st.error(f"Erro ao carregar ou processar o arquivo: {e}")

with tab2:
    st.header("Criar/Editar Escala de Agentes")

    st.subheader("Upload de Escala via Excel")
    uploaded_schedule_file = st.file_uploader("Escolha um arquivo Excel para a escala", type=["xlsx"], key="schedule_upload")

    if uploaded_schedule_file is not None:
        try:
            df_schedule_uploaded = pd.read_excel(uploaded_schedule_file)
            st.write("Prévia da escala carregada:")
            st.dataframe(df_schedule_uploaded.head())

            # Mapear e processar colunas do arquivo de escala
            processed_schedule_rows = []
            for _, row in df_schedule_uploaded.iterrows():
                agent_name = row['NOME']
                days_str = row['DIAS DE ATENDIMENTO']
                entrada_str = str(row['ENTRADA'])
                saida_str = str(row['SAÍDA'])

                # Tratar valores NaN ou formatos inesperados para ENTRADA/SAÍDA
                if pd.isna(entrada_str) or pd.isna(saida_str) or 'NaT' in entrada_str or 'NaT' in saida_str:
                    st.warning(f"Horário inválido para o agente {agent_name}. Linha ignorada.")
                    continue

                # Converter para formato de hora
                try:
                    entrada_time = datetime.strptime(entrada_str, '%H:%M:%S').time()
                    saida_time = datetime.strptime(saida_str, '%H:%M:%S').time()
                except ValueError:
                    try: # Tentar outro formato comum (ex: apenas HH:MM)
                        entrada_time = datetime.strptime(entrada_str, '%H:%M').time()
                        saida_time = datetime.strptime(saida_str, '%H:%M').time()
                    except ValueError:
                        st.warning(f"Formato de horário inválido para o agente {agent_name} ({entrada_str} - {saida_str}). Linha ignorada.")
                        continue

                # Processar dias da semana
                # Ignorar partes como "loja" ou "Call"
                days_clean = [d.strip() for d in days_str.replace(' e ', ',').split(',') if d.strip() not in ['loja', 'Call']]

                for day_abbr in days_clean:
                    if day_abbr in dias_semana_map:
                        processed_schedule_rows.append({
                            'Nome do agente': agent_name,
                            'Dia da semana': day_abbr,
                            'Hora de início': entrada_time,
                            'Hora de término': saida_time,
                            'Grupo': 'Padrão' # Pode ser ajustado se houver coluna de grupo no Excel
                        })
                    else:
                        st.warning(f"Dia da semana '{day_abbr}' não reconhecido para o agente {agent_name}. Linha ignorada.")

            if processed_schedule_rows:
                st.session_state.df_schedule = pd.DataFrame(processed_schedule_rows)
                st.success("Escala carregada e processada com sucesso!")
            else:
                st.warning("Nenhuma escala válida foi encontrada no arquivo carregado.")

        except Exception as e:
            st.error(f"Erro ao carregar ou processar o arquivo de escala: {e}")

    st.subheader("Adicionar/Editar Escala Manualmente")
    with st.form("add_schedule_form"):
        agent_name = st.text_input("Nome do Agente")
        day_of_week = st.selectbox("Dia da Semana", list(dias_semana_map.keys()))
        start_time = st.time_input("Hora de Início", value=time(9, 0))
        end_time = st.time_input("Hora de Término", value=time(17, 0))
        group_name = st.text_input("Grupo (opcional)", value="Padrão")

        submitted = st.form_submit_button("Adicionar Escala")
        if submitted:
            new_schedule_entry = pd.DataFrame([{
                'Nome do agente': agent_name,
                'Dia da semana': day_of_week,
                'Hora de início': start_time,
                'Hora de término': end_time,
                'Grupo': group_name
            }])
            st.session_state.df_schedule = pd.concat([st.session_state.df_schedule, new_schedule_entry], ignore_index=True)
            st.success(f"Escala para {agent_name} adicionada.")

    st.subheader("Grupos de Agentes")
    group_action = st.radio("Ação de Grupo", ["Ver Grupos", "Criar Novo Grupo", "Adicionar Agente a Grupo Existente"])

    if group_action == "Ver Grupos":
        if st.session_state.agent_groups:
            for group, agents in st.session_state.agent_groups.items():
                st.write(f"**{group}**: {', '.join(agents)}")
        else:
            st.info("Nenhum grupo criado ainda.")

    elif group_action == "Criar Novo Grupo":
        new_group_name = st.text_input("Nome do Novo Grupo")
        if st.button("Criar Grupo") and new_group_name:
            if new_group_name not in st.session_state.agent_groups:
                st.session_state.agent_groups[new_group_name] = []
                st.success(f"Grupo '{new_group_name}' criado.")
            else:
                st.warning(f"Grupo '{new_group_name}' já existe.")

    elif group_action == "Adicionar Agente a Grupo Existente":
        if st.session_state.agent_groups:
            selected_group = st.selectbox("Selecione o Grupo", list(st.session_state.agent_groups.keys()))

            # Obter lista de agentes únicos do relatório e da escala
            all_agents = set()
            if not st.session_state.df_real_status.empty:
                all_agents.update(st.session_state.df_real_status['Nome do agente'].unique())
            if not st.session_state.df_schedule.empty:
                all_agents.update(st.session_state.df_schedule['Nome do agente'].unique())

            if all_agents:
                agent_to_add = st.selectbox("Selecione o Agente", sorted(list(all_agents)))
                if st.button(f"Adicionar {agent_to_add} ao Grupo {selected_group}"):
                    if agent_to_add not in st.session_state.agent_groups[selected_group]:
                        st.session_state.agent_groups[selected_group].append(agent_to_add)
                        st.success(f"Agente '{agent_to_add}' adicionado ao grupo '{selected_group}'.")
                    else:
                        st.info(f"Agente '{agent_to_add}' já está no grupo '{selected_group}'.")
            else:
                st.warning("Nenhum agente disponível para adicionar a grupos. Carregue um relatório ou escala primeiro.")
        else:
            st.warning("Nenhum grupo criado ainda. Crie um grupo primeiro.")

    st.subheader("Escala Atual")
    if not st.session_state.df_schedule.empty:
        st.dataframe(st.session_state.df_schedule)
    else:
        st.info("Nenhuma escala carregada ou adicionada ainda.")

with tab3:
    st.header("Visualização da Escala e Status Real")

    if st.session_state.df_real_status.empty and st.session_state.df_schedule.empty:
        st.warning("Por favor, carregue o relatório de status e a escala nas abas anteriores para visualizar os dados.")
    else:
        # --- Filtros na barra lateral ---
        st.sidebar.header("Filtros")

        # Obter lista de agentes únicos do relatório e da escala
        all_agents_in_data = set()
        if not st.session_state.df_real_status.empty:
            all_agents_in_data.update(st.session_state.df_real_status['Nome do agente'].unique())
        if not st.session_state.df_schedule.empty:
            all_agents_in_data.update(st.session_state.df_schedule['Nome do agente'].unique())

        selected_agents = st.sidebar.multiselect(
            "Selecionar Agentes",
            sorted(list(all_agents_in_data)),
            default=sorted(list(all_agents_in_data)) if all_agents_in_data else []
        )

        # Filtro por grupo
        group_options = ["Todos"] + list(st.session_state.agent_groups.keys())
        selected_group_filter = st.sidebar.selectbox("Filtrar por Grupo", group_options)

        if selected_group_filter != "Todos":
            agents_in_group = st.session_state.agent_groups.get(selected_group_filter, [])
            # Intersect with already selected agents if any
            if selected_agents:
                selected_agents = list(set(selected_agents) & set(agents_in_group))
            else: # If no agents were selected initially, use all agents in the group
                selected_agents = agents_in_group
            if not selected_agents:
                st.sidebar.warning(f"Nenhum agente selecionado no grupo '{selected_group_filter}'.")


        # Filtro de data
        min_date = datetime(2026, 1, 1).date()
        max_date = datetime(2026, 12, 31).date()

        if not st.session_state.df_real_status.empty:
            min_date_report = st.session_state.df_real_status['Data'].min().date()
            max_date_report = st.session_state.df_real_status['Data'].max().date()
            min_date = min(min_date, min_date_report)
            max_date = max(max_date, max_date_report)

        if not st.session_state.df_schedule.empty:
            # Para a escala, precisamos expandir para datas reais para determinar min/max
            # Isso é um pouco mais complexo, então vamos manter a data do relatório como base por enquanto
            pass # A expansão da escala será feita mais abaixo para o gráfico

        date_range = st.sidebar.date_input(
            "Selecionar Intervalo de Datas",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )

        if len(date_range) == 2:
            start_date, end_date = date_range
        else:
            st.warning("Por favor, selecione um intervalo de duas datas.")
            st.stop()

        # --- Preparar dados para o gráfico ---
        df_plot = pd.DataFrame()

        # 1. Adicionar dados de Escala
        if not st.session_state.df_schedule.empty and selected_agents:
            df_schedule_filtered = st.session_state.df_schedule[
                st.session_state.df_schedule['Nome do agente'].isin(selected_agents)
            ].copy()

            expanded_schedule_rows = []
            for _, row in df_schedule_filtered.iterrows():
                agent_name = row['Nome do agente']
                day_abbr = row['Dia da semana']
                start_time = row['Hora de início']
                end_time = row['Hora de término']

                # Mapear abreviação para nome completo do dia em inglês
                day_full_name = dias_semana_map.get(day_abbr)
                if not day_full_name:
                    continue

                current_date = start_date
                while current_date <= end_date:
                    if current_date.strftime('%A') == day_full_name:
                        # Criar datetime objects para o início e fim da escala no dia específico
                        schedule_start_dt = datetime.combine(current_date, start_time)
                        schedule_end_dt = datetime.combine(current_date, end_time)

                        # Se a hora de término for anterior à de início (ex: 22:00 - 06:00),
                        # significa que a escala atravessa a meia-noite.
                        if schedule_end_dt < schedule_start_dt:
                            schedule_end_dt += timedelta(days=1) # Adiciona um dia para o cálculo correto

                        expanded_schedule_rows.append({
                            'Nome do agente': agent_name,
                            'Tipo': 'Escala',
                            'Hora de início do estado - Carimbo de data/hora': schedule_start_dt,
                            'Hora de término do estado - Carimbo de data/hora': schedule_end_dt,
                            'Data': current_date,
                            'Estado': 'Escala' # Usar 'Escala' como estado para diferenciação
                        })
                    current_date += timedelta(days=1)

            if expanded_schedule_rows:
                df_schedule_expanded = pd.DataFrame(expanded_schedule_rows)
                df_plot = pd.concat([df_plot, df_schedule_expanded], ignore_index=True)
            else:
                df_schedule_expanded = pd.DataFrame() # Garante que df_schedule_expanded existe mesmo vazio

        # 2. Adicionar dados de Status Real (apenas 'Unified online')
        if not st.session_state.df_real_status.empty and selected_agents:
            df_real_filtered = st.session_state.df_real_status[
                (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
                (st.session_state.df_real_status['Data'].dt.date >= start_date) &
                (st.session_state.df_real_status['Data'].dt.date <= end_date) &
                (st.session_state.df_real_status['Estado'] == 'Unified online') # Apenas Unified online
            ].copy()

            # Adicionar coluna 'Tipo' para diferenciar no gráfico
            df_real_filtered['Tipo'] = 'Status Real (Online)'
            df_plot = pd.concat([df_plot, df_real_filtered], ignore_index=True)

        if not df_plot.empty:
            # Ordenar para melhor visualização
            df_plot = df_plot.sort_values(by=['Nome do agente', 'Data', 'Tipo', 'Hora de início do estado - Carimbo de data/hora'])

            # Criar o gráfico de Gantt
            # Usar 'Tipo' para criar sub-barras para Escala e Status Real
            fig = px.timeline(
                df_plot,
                x_start="Hora de início do estado - Carimbo de data/hora",
                x_end="Hora de término do estado - Carimbo de data/hora",
                y="Nome do agente",
                color="Tipo", # Colorir por Tipo (Escala ou Status Real)
                facet_row="Data", # Criar uma linha para cada dia
                title="Comparativo de Escala vs. Status Real (Unified Online)",
                category_orders={"Tipo": ["Escala", "Status Real (Online)"]}, # Ordem das barras
                color_discrete_map={
                    'Escala': 'lightblue',
                    'Status Real (Online)': 'darkgreen'
                }
            )

            fig.update_yaxes(autorange="reversed") # Inverte a ordem dos agentes para o mais recente ficar em cima
            fig.update_layout(
                hovermode="x unified",
                height=max(400, len(df_plot['Nome do agente'].unique()) * len(df_plot['Data'].unique()) * 50), # Altura dinâmica
                xaxis_title="Horário",
                yaxis_title="Agente"
            )
            fig.update_xaxes(
                tickformat="%H:%M",
                range=[datetime.combine(start_date, time(0,0)), datetime.combine(end_date, time(23,59,59))]
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhum dado para exibir no gráfico com os filtros selecionados.")

        st.subheader("Métricas de Disponibilidade e Aderência")
        if not st.session_state.df_real_status.empty and 'df_schedule_expanded' in locals() and not df_schedule_expanded.empty and selected_agents:
            metrics_df = calculate_metrics(st.session_state.df_real_status, df_schedule_expanded, selected_agents, start_date, end_date)
            if not metrics_df.empty:
                st.dataframe(metrics_df.style.format({
                    'Total Escala (min)': "{:.2f}",
                    'Total Online (min)': "{:.2f}",
                    'Online na Escala (min)': "{:.2f}",
                    'Disponibilidade (%)': "{:.2f}%",
                    'Aderência (%)': "{:.2f}%"
                }))
            else:
                st.info("Nenhuma métrica calculada para os filtros selecionados.")
        else:
            st.info("Carregue o relatório de status e a escala para calcular as métricas.")
