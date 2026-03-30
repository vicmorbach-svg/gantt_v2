import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
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
            df.loc[idx, 'Hora de término do estado - Carimbo de data/hora'] = row['Data'] + timedelta(days=1) - timedelta(seconds=1)
        elif row['Hora de término do estado - Carimbo de data/hora'].date() > row['Data'].date():
            df.loc[idx, 'Hora de término do estado - Carimbo de data/hora'] = row['Data'] + timedelta(days=1) - timedelta(seconds=1)

    # Remover linhas onde a data de início é NaT (não pôde ser parseada)
    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Data'], inplace=True)

    return df

def to_time(val):
    if pd.isna(val):
        return None
    try:
        # Tenta converter diretamente para time se já for datetime.time
        if isinstance(val, datetime.time):
            return val
        # Tenta converter de string HH:MM:SS
        return datetime.strptime(str(val).split(' ')[-1], '%H:%M:%S').time()
    except ValueError:
        try:
            # Tenta converter de string HH:MM
            return datetime.strptime(str(val).split(' ')[-1], '%H:%M').time()
        except ValueError:
            # Se for um datetime completo (ex: 1900-01-01 00:00:00), extrai apenas a hora
            try:
                return pd.to_datetime(val).time()
            except Exception:
                return None

def process_uploaded_scale(df):
    # Renomear colunas para padronização
    df.rename(columns={
        'NOME': 'Nome do agente',
        'DIAS DE ATENDIMENTO': 'Dias da Semana',
        'ENTRADA': 'Entrada',
        'SAÍDA': 'Saída'
    }, inplace=True)

    # Normalizar nomes dos agentes
    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Remover linhas onde o nome do agente é NaN ou vazio após normalização
    df.dropna(subset=['Nome do agente'], inplace=True)
    df = df[df['Nome do agente'] != '']

    # Aplicar a função to_time para converter as colunas de horário
    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    # Remover linhas onde Entrada ou Saída são NaT após a conversão
    df.dropna(subset=['Entrada', 'Saída'], inplace=True)

    # Expandir a escala para cada dia da semana
    expanded_scale = []
    dias_map = {
        'SEG': 0, 'TER': 1, 'QUA': 2, 'QUI': 3, 'SEX': 4, 'SAB': 5, 'DOM': 6,
        'SEGUNDA': 0, 'TERCA': 1, 'QUARTA': 2, 'QUINTA': 3, 'SEXTA': 4, 'SABADO': 5, 'DOMINGO': 6
    }

    for _, row in df.iterrows():
        agent_name = row['Nome do agente']
        days_str = str(row['Dias da Semana']).upper().replace(' E ', ',').replace(' ', '') # Trata "Seg e Qui"

        # Ignora linhas com 'NaN' ou strings vazias após o replace
        if not days_str or days_str == 'NAN':
            continue

        days_list = [dias_map[d.strip()[:3]] for d in days_str.split(',') if d.strip()[:3] in dias_map] # Pega os 3 primeiros chars

        for day_of_week_num in days_list:
            expanded_scale.append({
                'Nome do agente': agent_name,
                'Dia da Semana Num': day_of_week_num,
                'Entrada': row['Entrada'],
                'Saída': row['Saída']
            })

    return pd.DataFrame(expanded_scale)

# --- Funções de Cálculo de Métricas ---
def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    if df_real_status.empty or df_escala.empty or not selected_agents:
        return pd.DataFrame()

    analysis_results = []

    # Mapeamento de número do dia da semana para nome (para df_escala)
    day_name_map = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}

    for agent in selected_agents:
        agent_real_status = df_real_status[df_real_status['Nome do agente'] == agent].copy()
        agent_escala = df_escala[df_escala['Nome do agente'] == agent].copy()

        total_scheduled_time_minutes_agent = 0
        total_online_in_schedule_minutes_agent = 0

        current_date = start_date
        while current_date <= end_date:
            day_of_week_num = current_date.weekday() # 0=Segunda, 6=Domingo

            # Filtra a escala para o dia da semana atual
            daily_escala = agent_escala[agent_escala['Dia da Semana Num'] == day_of_week_num]

            if not daily_escala.empty:
                for _, schedule_row in daily_escala.iterrows():
                    schedule_start_time = schedule_row['Entrada']
                    schedule_end_time = schedule_row['Saída']

                    if schedule_start_time is None or schedule_end_time is None:
                        continue

                    schedule_start_dt = datetime.combine(current_date, schedule_start_time)
                    schedule_end_dt = datetime.combine(current_date, schedule_end_time)

                    # Lidar com escalas que atravessam a meia-noite
                    if schedule_end_dt < schedule_start_dt:
                        schedule_end_dt += timedelta(days=1)

                    total_scheduled_time_minutes_agent += (schedule_end_dt - schedule_start_dt).total_seconds() / 60

                    # Filtrar status real para o dia atual
                    daily_real_status = agent_real_status[agent_real_status['Data'] == current_date]

                    for _, status_row in daily_real_status.iterrows():
                        status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                        status_end = status_row['Hora de término do estado - Carimbo de data/hora']
                        status_state = status_row['Estado']

                        if status_start is None or status_end is None:
                            continue

                        # Ajustar status_end se ele for no dia seguinte ao status_start para o cálculo diário
                        if status_end.date() > status_start.date():
                            status_end = datetime.combine(status_start.date(), datetime.max.time())

                        if status_state == 'Unified online':
                            # Encontrar a interseção entre o período da escala e o período online
                            overlap_start = max(schedule_start_dt, status_start)
                            overlap_end = min(schedule_end_dt, status_end)

                            if overlap_end > overlap_start:
                                online_duration_in_overlap = (overlap_end - overlap_start).total_seconds() / 60
                                total_online_in_schedule_minutes_agent += online_duration_in_overlap

            current_date += timedelta(days=1)

        availability_percentage = (total_online_in_schedule_minutes_agent / total_scheduled_time_minutes_agent * 100) if total_scheduled_time_minutes_agent > 0 else 0

        analysis_results.append({
            'Agente': agent,
            'Total Tempo Escala (min)': total_scheduled_time_minutes_agent,
            'Total Tempo Online na Escala (min)': total_online_in_schedule_minutes_agent,
            'Disponibilidade na Escala (%)': f"{availability_percentage:.2f}%"
        })

    return pd.DataFrame(analysis_results)


# --- Layout do Streamlit ---
tab1, tab2, tab3 = st.tabs(["Upload de Dados", "Gerenciar Grupos", "Visualização e Métricas"])

with tab1:
    st.header("Carregar Relatórios de Agentes e Escalas")

    st.subheader("Upload do Relatório de Status do Agente (Excel)")
    uploaded_report_file = st.file_uploader("Escolha o arquivo Excel do relatório de status", type=["xlsx"], key="report_uploader")
    if uploaded_report_file is not None:
        try:
            df_report_raw = pd.read_excel(uploaded_report_file, header=0)
            st.session_state.df_real_status = process_uploaded_report(df_report_raw.copy())
            st.success("Relatório de status carregado e processado com sucesso!")
            st.dataframe(st.session_state.df_real_status.head())
        except Exception as e:
            st.error(f"Erro ao processar o relatório de status: {e}")

    st.subheader("Upload do Arquivo de Escala (Excel)")
    uploaded_scale_file = st.file_uploader("Escolha o arquivo Excel da escala", type=["xlsx"], key="scale_uploader")
    if uploaded_scale_file is not None:
        try:
            df_scale_raw = pd.read_excel(uploaded_scale_file, header=0)
            st.session_state.df_escala = process_uploaded_scale(df_scale_raw.copy())
            st.success("Arquivo de escala carregado e processado com sucesso!")
            st.dataframe(st.session_state.df_escala.head())
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de escala: {e}")

    # Atualizar a lista de todos os agentes após o upload de ambos os arquivos
    if not st.session_state.df_real_status.empty:
        st.session_state.normalized_agents_real = set(st.session_state.df_real_status['Nome do agente'].unique())
    else:
        st.session_state.normalized_agents_real = set()

    if not st.session_state.df_escala.empty:
        st.session_state.normalized_agents_escala = set(st.session_state.df_escala['Nome do agente'].unique())
    else:
        st.session_state.normalized_agents_escala = set()

    st.session_state.all_agents = sorted(list(st.session_state.normalized_agents_real.union(st.session_state.normalized_agents_escala)))


with tab2:
    st.header("Gerenciar Grupos de Agentes")

    if 'agent_groups' not in st.session_state:
        st.session_state.agent_groups = {}

    group_name = st.text_input("Nome do novo grupo:")
    if st.session_state.all_agents:
        selected_agents_for_group = st.multiselect("Selecione os agentes para este grupo:", st.session_state.all_agents, key="group_agents_selector")
        if st.button("Criar/Atualizar Grupo"):
            if group_name:
                st.session_state.agent_groups[group_name] = selected_agents_for_group
                st.success(f"Grupo '{group_name}' criado/atualizado com {len(selected_agents_for_group)} agentes.")
            else:
                st.warning("Por favor, insira um nome para o grupo.")
    else:
        st.info("Carregue os arquivos de dados na aba 'Upload de Dados' para gerenciar grupos.")

    st.subheader("Grupos Existentes")
    if st.session_state.agent_groups:
        for name, agents in st.session_state.agent_groups.items():
            st.write(f"**{name}**: {', '.join(agents)}")

        group_to_delete = st.selectbox("Selecione um grupo para excluir:", [""] + list(st.session_state.agent_groups.keys()))
        if st.button("Excluir Grupo") and group_to_delete:
            del st.session_state.agent_groups[group_to_delete]
            st.success(f"Grupo '{group_to_delete}' excluído.")
            st.rerun()
    else:
        st.info("Nenhum grupo criado ainda.")


with tab3:
    st.header("Visualização e Métricas")

    # --- Comparativo de Agentes ---
    st.subheader("Comparativo de Agentes entre Relatório e Escala")
    if not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
        agents_in_real_only = st.session_state.normalized_agents_real - st.session_state.normalized_agents_escala
        agents_in_escala_only = st.session_state.normalized_agents_escala - st.session_state.normalized_agents_real
        agents_in_both = st.session_state.normalized_agents_real.intersection(st.session_state.normalized_agents_escala)

        if agents_in_real_only:
            st.warning(f"Agentes no relatório de status, mas SEM escala definida: {', '.join(sorted(list(agents_in_real_only)))}")
        if agents_in_escala_only:
            st.info(f"Agentes na escala, mas SEM dados no relatório de status: {', '.join(sorted(list(agents_in_escala_only)))}")
        if agents_in_both:
            st.success(f"Agentes presentes em AMBOS (relatório e escala): {', '.join(sorted(list(agents_in_both)))}")
        else:
            st.info("Nenhum agente encontrado em ambos os arquivos após normalização.")
    elif not st.session_state.df_real_status.empty:
        st.info("Carregue o arquivo de escala para comparar os agentes.")
    elif not st.session_state.df_escala.empty:
        st.info("Carregue o relatório de status para comparar os agentes.")
    else:
        st.info("Carregue ambos os arquivos para ver o comparativo de agentes.")

    st.markdown("---")

    # --- Filtros na Barra Lateral ---
    st.sidebar.header("Filtros")

    # Filtro por grupo
    all_groups = ["Todos"] + list(st.session_state.agent_groups.keys())
    selected_group_name = st.sidebar.selectbox("Filtrar por Grupo:", all_groups)

    if selected_group_name == "Todos":
        available_agents_for_selection = st.session_state.all_agents
    else:
        available_agents_for_selection = st.session_state.agent_groups.get(selected_group_name, [])
        if not available_agents_for_selection:
            st.sidebar.warning(f"O grupo '{selected_group_name}' não possui agentes definidos.")

    selected_agents = st.sidebar.multiselect(
        "Selecione os Agentes:",
        options=available_agents_for_selection,
        default=available_agents_for_selection[:min(len(available_agents_for_selection), 5)] # Seleciona os 5 primeiros por padrão
    )

    # Filtro de data
    today = datetime.now().date()
    default_start_date = today - timedelta(days=7)
    default_end_date = today

    date_range = st.sidebar.date_input(
        "Selecione o Intervalo de Datas:",
        value=(default_start_date, default_end_date),
        key="date_range_picker"
    )

    start_date = date_range[0] if date_range else default_start_date
    end_date = date_range[1] if len(date_range) > 1 else (date_range[0] if date_range else default_end_date)

    # Limitar o intervalo de datas para o gráfico
    max_days_for_chart = 14
    if (end_date - start_date).days > max_days_for_chart:
        st.sidebar.warning(f"O intervalo de datas para o gráfico é limitado a {max_days_for_chart} dias para melhor visualização. Ajustando data final.")
        end_date = start_date + timedelta(days=max_days_for_chart - 1)
        st.sidebar.date_input(
            "Intervalo de Datas Ajustado:",
            value=(start_date, end_date),
            key="adjusted_date_range_picker",
            disabled=True
        )

    st.subheader("Gráfico de Gantt Comparativo")
    if selected_agents and not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
        filtered_df_real = st.session_state.df_real_status[
            (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
            (st.session_state.df_real_status['Data'] >= pd.to_datetime(start_date)) &
            (st.session_state.df_real_status['Data'] <= pd.to_datetime(end_date))
        ].copy()

        filtered_df_escala = st.session_state.df_escala[
            st.session_state.df_escala['Nome do agente'].isin(selected_agents)
        ].copy()

        if not filtered_df_real.empty or not filtered_df_escala.empty:
            # Preparar dados para o gráfico
            df_chart_data = []

            # Adicionar dados de status real
            if not filtered_df_real.empty:
                filtered_df_real['Categoria'] = 'Status Real'
                filtered_df_real['Tipo'] = filtered_df_real['Estado']
                df_chart_data.append(filtered_df_real[['Nome do agente', 'Data', 'Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora', 'Categoria', 'Tipo']])

            # Adicionar dados de escala planejada
            if not filtered_df_escala.empty:
                current_date = start_date
                while current_date <= end_date:
                    day_of_week_num = current_date.weekday() # 0=Segunda, 6=Domingo
                    daily_escala = filtered_df_escala[filtered_df_escala['Dia da Semana Num'] == day_of_week_num]

                    for _, row in daily_escala.iterrows():
                        agent_name = row['Nome do agente']
                        schedule_start_time = row['Entrada']
                        schedule_end_time = row['Saída']

                        if schedule_start_time is None or schedule_end_time is None:
                            continue

                        schedule_start_dt = datetime.combine(current_date, schedule_start_time)
                        schedule_end_dt = datetime.combine(current_date, schedule_end_time)

                        # Lidar com escalas que atravessam a meia-noite
                        if schedule_end_dt < schedule_start_dt:
                            schedule_end_dt += timedelta(days=1)

                        df_chart_data.append(pd.DataFrame([{
                            'Nome do agente': agent_name,
                            'Data': current_date,
                            'Hora de início do estado - Carimbo de data/hora': schedule_start_dt,
                            'Hora de término do estado - Carimbo de data/hora': schedule_end_dt,
                            'Categoria': 'Escala Planejada',
                            'Tipo': 'Escala Planejada'
                        }]))
                    current_date += timedelta(days=1)

            if df_chart_data:
                df_chart = pd.concat(df_chart_data, ignore_index=True)
                df_chart['Agente_Data_Tipo'] = df_chart['Nome do agente'] + ' - ' + df_chart['Data'].dt.strftime('%Y-%m-%d') + ' (' + df_chart['Categoria'] + ')'

                # Ordenar para melhor visualização
                df_chart.sort_values(by=['Nome do agente', 'Data', 'Hora de início do estado - Carimbo de data/hora'], inplace=True)

                # Mapeamento de cores para os estados e escala
                color_map = {
                    'Unified online': 'green',
                    'Unified away': 'orange',
                    'Unified offline': 'red',
                    'Unified transfers only': 'purple',
                    'Escala Planejada': 'blue'
                }

                # Altura dinâmica do gráfico
                unique_chart_rows = df_chart['Agente_Data_Tipo'].nunique()
                chart_height = max(300, unique_chart_rows * 30) # 30 pixels por linha, mínimo de 300

                fig = px.timeline(
                    df_chart,
                    x_start="Hora de início do estado - Carimbo de data/hora",
                    x_end="Hora de término do estado - Carimbo de data/hora",
                    y="Agente_Data_Tipo",
                    color="Tipo",
                    color_discrete_map=color_map,
                    title="Comparativo de Escala Planejada vs. Status Real",
                    height=chart_height
                )

                fig.update_yaxes(category_orders={"Agente_Data_Tipo": sorted(df_chart['Agente_Data_Tipo'].unique(), reverse=True)})
                fig.update_xaxes(
                    title_text="Hora do Dia",
                    tickformat="%H:%M",
                    range=[datetime.combine(start_date, datetime.min.time()), datetime.combine(start_date, datetime.max.time())],
                    showgrid=True, gridwidth=1, gridcolor='LightGrey'
                )
                fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGrey')
                fig.update_layout(
                    hovermode="y unified",
                    legend_title_text="Legenda",
                    xaxis_range=[datetime.combine(start_date, datetime.min.time()), datetime.combine(start_date, datetime.max.time())]
                )
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
