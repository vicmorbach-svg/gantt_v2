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
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    return name

# --- Funções de Processamento de Dados ---
def process_uploaded_report(df_report_raw):
    # O arquivo de status real TEM cabeçalhos na primeira linha.
    # Vamos renomear as colunas para os nomes esperados.
    df = df_report_raw.copy() # Trabalha com uma cópia para evitar SettingWithCopyWarning

    # Mapeamento explícito das colunas do arquivo de status real
    # Baseado no arquivo Tempo_em_Status_do_agente_por_dia_03202026_1006.xlsx
    expected_columns_report = {
        'Nome do agente': 'Nome do agente',
        'Hora de início do estado - Dia do mês': 'Dia',
        'Hora de início do estado - Carimbo de data/hora': 'Hora de início do estado - Carimbo de data/hora',
        'Hora de término do estado - Carimbo de data/hora': 'Hora de término do estado - Carimbo de data/hora',
        'Estado': 'Estado',
        'Tempo do agente no estado / Minutos': 'Tempo do agente no estado / Minutos'
    }

    # Renomear colunas
    df.rename(columns=expected_columns_report, inplace=True)

    # Verificar se as colunas essenciais existem após o renomeamento
    required_cols = ['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora', 'Estado']
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        st.error(f"Erro: O arquivo de status real está faltando as colunas essenciais: {', '.join(missing)}. Por favor, verifique o formato do arquivo.")
        st.stop()

    # Normalizar nomes dos agentes
    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Remover linhas onde o nome do agente é NaN ou vazio após normalização
    df.dropna(subset=['Nome do agente'], inplace=True)
    df = df[df['Nome do agente'] != '']

    # Converter colunas de data/hora
    df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
    df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

    # Preencher NaT em 'Hora de término do estado - Carimbo de data/hora'
    for index, row in df.iterrows():
        if pd.isna(row['Hora de término do estado - Carimbo de data/hora']):
            if pd.notna(row['Hora de início do estado - Carimbo de data/hora']):
                df.at[index, 'Hora de término do estado - Carimbo de data/hora'] = row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
            else:
                df.drop(index, inplace=True)
                continue

    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora'], inplace=True)
    df['Data'] = df['Hora de início do estado - Carimbo de data/hora'].dt.normalize()
    df['Tempo do agente no estado / Minutos'] = pd.to_numeric(df['Tempo do agente no estado / Minutos'], errors='coerce').fillna(0)

    return df

def to_time(val):
    if pd.isna(val):
        return None
    try:
        # Tenta converter para datetime e depois extrair a hora
        dt_obj = pd.to_datetime(val, errors='coerce')
        if pd.notna(dt_obj):
            return dt_obj.time()
        # Se falhar, tenta converter como string de hora (ex: "HH:MM")
        return datetime.strptime(str(val).split(' ')[0], '%H:%M:%S').time()
    except (ValueError, TypeError):
        try:
            return datetime.strptime(str(val).split(' ')[0], '%H:%M').time()
        except (ValueError, TypeError):
            return None

def process_uploaded_scale(df_scale_raw):
    df = df_scale_raw.copy()

    # Mapeamento explícito das colunas do arquivo de escala
    # Baseado no arquivo escala_gantt.xlsx
    expected_columns_scale = {
        'NOME': 'Nome do agente',
        'DIAS DE ATENDIMENTO': 'Dias de Atendimento',
        'ENTRADA': 'Entrada',
        'SAÍDA': 'Saída',
        'CARGA': 'Carga' # Incluindo a coluna CARGA
    }

    # Renomear as colunas existentes para os nomes esperados
    # Usamos um dicionário de mapeamento para evitar erros se a ordem mudar
    current_columns = df.columns.tolist()
    rename_map = {}
    for original_col_name, new_col_name in expected_columns_scale.items():
        if original_col_name in current_columns:
            rename_map[original_col_name] = new_col_name
        # Adiciona o mapeamento inverso se o novo nome já existir no df e for diferente do original
        elif new_col_name in current_columns and original_col_name != new_col_name:
            rename_map[new_col_name] = new_col_name
        # Se a coluna original não for encontrada, e o novo nome não for o mesmo que o original,
        # e o novo nome não estiver nas colunas atuais, podemos ignorar ou avisar.
        # Por exemplo, se 'CARGA' não estiver no arquivo, 'Carga' não será mapeado.
        # Não vamos levantar erro aqui, apenas não mapear.

    df.rename(columns=rename_map, inplace=True)

    # Verificar se as colunas essenciais existem após o renomeamento
    required_cols = ['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída']
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        st.error(f"Erro: O arquivo de escala está faltando as colunas essenciais: {', '.join(missing)}. Por favor, verifique o formato do arquivo.")
        return pd.DataFrame() # Retorna DataFrame vazio para evitar erros

    # Normalizar nomes dos agentes
    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Remover linhas onde o nome do agente é NaN ou vazio após normalização
    df.dropna(subset=['Nome do agente'], inplace=True)
    df = df[df['Nome do agente'] != '']

    # Converter horários de entrada e saída
    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    # Remover linhas onde Entrada ou Saída não puderam ser convertidos
    df.dropna(subset=['Entrada', 'Saída'], inplace=True)
    if df.empty:
        st.warning("Nenhuma escala válida foi encontrada após o processamento dos horários. Verifique as colunas 'ENTRADA' e 'SAÍDA'.")
        return pd.DataFrame()

    # Mapeamento de dias da semana para números (0=Segunda, 6=Domingo)
    dias_map = {
        'SEG': 0, 'SEGUNDA': 0, 'SEGUNDA-FEIRA': 0,
        'TER': 1, 'TERCA': 1, 'TERÇA': 1, 'TERCA-FEIRA': 1, 'TERÇA-FEIRA': 1,
        'QUA': 2, 'QUARTA': 2, 'QUARTA-FEIRA': 2,
        'QUI': 3, 'QUINTA': 3, 'QUINTA-FEIRA': 3,
        'SEX': 4, 'SEXTA': 4, 'SEXTA-FEIRA': 4,
        'SAB': 5, 'SABADO': 5, 'SÁBADO': 5,
        'DOM': 6, 'DOMINGO': 6
    }

    expanded_scale_data = []
    for index, row in df.iterrows():
        agent_name = row['Nome do agente']
        dias_str = str(row['Dias de Atendimento'])
        entrada = row['Entrada']
        saida = row['Saída']
        carga = row.get('Carga') # Usar .get() para acessar 'Carga' de forma segura

        if pd.isna(dias_str) or not dias_str.strip():
            st.warning(f"Dias de atendimento vazios para o agente {agent_name}. Ignorando.")
            continue

        # Limpar e dividir a string de dias
        # Substitui ' e ' por ',' e remove qualquer texto extra após a vírgula
        dias_processed = dias_str.upper().replace(' E ', ',').replace(' E', ',').replace('E ', ',')
        dias_list_raw = [d.strip() for d in dias_processed.split(',') if d.strip()]

        # Processar cada parte para extrair o dia da semana
        valid_days_for_agent = []
        for d_raw in dias_list_raw:
            # Remove qualquer texto adicional que não seja o dia da semana (ex: "LOJA", "CALL")
            day_part = d_raw.split(' ')[0]
            day_normalized = unicodedata.normalize('NFKD', day_part).encode('ascii', 'ignore').decode('utf-8').strip()

            if day_normalized in dias_map:
                valid_days_for_agent.append(dias_map[day_normalized])
            else:
                st.warning(f"Dia da semana '{d_raw}' não reconhecido para o agente {agent_name}. Ignorando.")

        if not valid_days_for_agent:
            st.warning(f"Nenhum dia de atendimento válido encontrado para o agente {agent_name}. Ignorando.")
            continue

        for day_of_week_num in valid_days_for_agent:
            expanded_scale_data.append({
                'Nome do agente': agent_name,
                'Dia da Semana Num': day_of_week_num,
                'Entrada': entrada,
                'Saída': saida,
                'Carga': carga # Incluir Carga na escala expandida
            })

    if not expanded_scale_data:
        st.warning("Nenhuma escala válida foi encontrada após o processamento. Verifique a coluna 'DIAS DE ATENDIMENTO' e os horários.")
        return pd.DataFrame()

    df_expanded_scale = pd.DataFrame(expanded_scale_data)
    return df_expanded_scale

# --- Funções de Cálculo de Métricas ---
def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    analysis_results = []

    # Filtrar df_real_status e df_escala para os agentes e datas selecionadas
    filtered_real_status = df_real_status[
        (df_real_status['Nome do agente'].isin(selected_agents)) &
        (df_real_status['Data'] >= start_date) &
        (df_real_status['Data'] <= end_date)
    ].copy()

    filtered_escala = df_escala[
        df_escala['Nome do agente'].isin(selected_agents)
    ].copy()

    if filtered_real_status.empty and filtered_escala.empty:
        return pd.DataFrame()

    for agent in selected_agents:
        agent_df_real = filtered_real_status[filtered_real_status['Nome do agente'] == agent]
        agent_df_escala = filtered_escala[filtered_escala['Nome do agente'] == agent]

        total_scheduled_time_minutes = 0
        total_online_in_schedule_minutes = 0

        current_date_metrics = start_date
        while current_date_metrics <= end_date:
            day_of_week_num = current_date_metrics.weekday() # 0=Segunda, 6=Domingo

            # Encontrar a escala para o agente e o dia da semana atual
            daily_schedule = agent_df_escala[agent_df_escala['Dia da Semana Num'] == day_of_week_num]

            if not daily_schedule.empty:
                for _, schedule_entry in daily_schedule.iterrows():
                    scale_start_time = schedule_entry['Entrada']
                    scale_end_time = schedule_entry['Saída']

                    if pd.notna(scale_start_time) and pd.notna(scale_end_time):
                        scale_start_dt = datetime.combine(current_date_metrics, scale_start_time)
                        scale_end_dt = datetime.combine(current_date_metrics, scale_end_time)

                        if scale_end_dt < scale_start_dt: # Escala que vira o dia
                            scale_end_dt += timedelta(days=1)

                        # Calcular tempo total de escala para o dia
                        total_scheduled_time_minutes += (scale_end_dt - scale_start_dt).total_seconds() / 60

                        # Status real para o dia
                        daily_real_status = agent_df_real[
                            (agent_df_real['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date_metrics) |
                            (agent_df_real['Hora de término do estado - Carimbo de data/hora'].dt.date == current_date_metrics)
                        ]

                        for _, status_entry in daily_real_status.iterrows():
                            if status_entry['Estado'] == 'Unified online':
                                status_start = status_entry['Hora de início do estado - Carimbo de data/hora']
                                status_end = status_entry['Hora de término do estado - Carimbo de data/hora']

                                # Ajustar status_end se ele for para o dia seguinte mas a escala termina no dia atual
                                if status_end.date() > current_date_metrics and scale_end_dt.date() == current_date_metrics:
                                    status_end = datetime.combine(current_date_metrics, datetime(1,1,1,23,59,59).time()) # Fim do dia da escala

                                # Calcular interseção entre o status online e a escala
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

    return pd.DataFrame(analysis_results)


# --- Configurações iniciais do Streamlit ---
st.set_page_config(layout="wide")
st.title("Análise de Escalas e Status de Agentes")

# Inicializa session_state para armazenar DataFrames e outras variáveis
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'all_unique_agents' not in st.session_state:
    st.session_state.all_unique_agents = set()
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}

# --- Abas ---
tab_upload, tab_groups, tab_view_metrics = st.tabs(["Upload de Dados", "Gerenciar Grupos", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos")

    uploaded_report_file = st.file_uploader("Selecione o arquivo de Status Real (Excel)", type=["xlsx"], key="report_uploader")
    if uploaded_report_file is not None:
        try:
            df_report_raw = pd.read_excel(uploaded_report_file, header=0) # Assumindo cabeçalhos na primeira linha
            st.session_state.df_real_status = process_uploaded_report(df_report_raw)
            if not st.session_state.df_real_status.empty:
                st.success("Arquivo de Status Real carregado e processado com sucesso!")
                st.dataframe(st.session_state.df_real_status.head())
            else:
                st.error("Erro ao processar o relatório de status. Verifique o formato do arquivo.")
        except Exception as e:
            st.error(f"Erro ao carregar ou processar o arquivo de Status Real: {e}")

    uploaded_scale_file = st.file_uploader("Selecione o arquivo de Escala (Excel)", type=["xlsx"], key="scale_uploader")
    if uploaded_scale_file is not None:
        try:
            df_scale_raw = pd.read_excel(uploaded_scale_file, header=0) # Assumindo cabeçalhos na primeira linha
            st.session_state.df_escala = process_uploaded_scale(df_scale_raw)
            if not st.session_state.df_escala.empty:
                st.success("Arquivo de Escala carregado e processado com sucesso!")
                st.dataframe(st.session_state.df_escala.head())
            else:
                st.error("Erro ao processar o arquivo de escala. Verifique o formato do arquivo.")
        except Exception as e:
            st.error(f"Erro ao carregar ou processar o arquivo de Escala: {e}")

    # Atualizar a lista de todos os agentes únicos após o upload
    if not st.session_state.df_real_status.empty:
        st.session_state.all_unique_agents.update(st.session_state.df_real_status['Nome do agente'].unique())
    if not st.session_state.df_escala.empty:
        st.session_state.all_unique_agents.update(st.session_state.df_escala['Nome do agente'].unique())

with tab_groups:
    st.header("Gerenciar Grupos de Agentes")

    if not st.session_state.all_unique_agents:
        st.info("Faça o upload dos arquivos na aba 'Upload de Dados' para ver os agentes disponíveis.")
    else:
        st.subheader("Criar Novo Grupo")
        group_name = st.text_input("Nome do Grupo")
        available_agents_for_group = sorted(list(st.session_state.all_unique_agents))
        selected_agents_for_group = st.multiselect(
            "Selecione os agentes para este grupo",
            available_agents_for_group,
            key=f"multiselect_new_group"
        )
        if st.button("Salvar Grupo") and group_name:
            st.session_state.agent_groups[group_name] = selected_agents_for_group
            st.success(f"Grupo '{group_name}' salvo com {len(selected_agents_for_group)} agentes.")
            st.experimental_rerun() # Recarrega para limpar o multiselect

        st.subheader("Grupos Existentes")
        if st.session_state.agent_groups:
            for name, agents in st.session_state.agent_groups.items():
                st.write(f"**{name}**: {', '.join(agents)}")
                if st.button(f"Excluir {name}", key=f"delete_group_{name}"):
                    del st.session_state.agent_groups[name]
                    st.success(f"Grupo '{name}' excluído.")
                    st.experimental_rerun()
        else:
            st.info("Nenhum grupo criado ainda.")

with tab_view_metrics:
    st.header("Visualização e Métricas")

    if not st.session_state.df_real_status.empty or not st.session_state.df_escala.empty:
        all_agents_sorted = sorted(list(st.session_state.all_unique_agents))

        # Filtro por grupo
        group_options = ["Nenhum"] + list(st.session_state.agent_groups.keys())
        selected_group_name = st.sidebar.selectbox("Filtrar por Grupo", group_options)

        pre_selected_agents = []
        if selected_group_name != "Nenhum":
            pre_selected_agents = st.session_state.agent_groups.get(selected_group_name, [])

        selected_agents = st.sidebar.multiselect(
            "Selecione os Agentes",
            all_agents_sorted,
            default=pre_selected_agents
        )

        # Filtro de datas
        min_date = datetime(2026, 1, 1).date()
        max_date = datetime(2026, 12, 31).date()
        if not st.session_state.df_real_status.empty:
            min_date = min(min_date, st.session_state.df_real_status['Data'].min().date())
            max_date = max(max_date, st.session_state.df_real_status['Data'].max().date())

        start_date = st.sidebar.date_input("Data de Início", value=min_date)
        end_date = st.sidebar.date_input("Data de Fim", value=max_date)

        # Garantir que start_date e end_date sejam objetos datetime.date
        start_date = pd.to_datetime(start_date).date()
        end_date = pd.to_datetime(end_date).date()

        if selected_agents:
            st.subheader("Comparativo de Agentes")
            all_agents_report = set(st.session_state.df_real_status['Nome do agente'].unique()) if not st.session_state.df_real_status.empty else set()
            all_agents_scale = set(st.session_state.df_escala['Nome do agente'].unique()) if not st.session_state.df_escala.empty else set()

            agents_in_report_only = all_agents_report - all_agents_scale
            agents_in_scale_only = all_agents_scale - all_agents_report
            agents_in_both = all_agents_report.intersection(all_agents_scale)

            if agents_in_report_only:
                st.warning(f"Agentes no relatório de status, mas não na escala: {', '.join(sorted(list(agents_in_report_only)))}")
            if agents_in_scale_only:
                st.warning(f"Agentes na escala, mas não no relatório de status: {', '.join(sorted(list(agents_in_scale_only)))}")
            if agents_in_both:
                st.info(f"Agentes presentes em ambos os arquivos: {len(agents_in_both)} agentes.")
            else:
                st.info("Nenhum agente em comum encontrado entre os arquivos de status e escala.")

            st.subheader("Linha do Tempo de Status e Escala")
            df_chart_data = []

            # Filtrar dados de status real para os agentes e datas selecionadas
            filtered_real_status_for_chart = st.session_state.df_real_status[
                (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
                (st.session_state.df_real_status['Data'] >= start_date) &
                (st.session_state.df_real_status['Data'] <= end_date)
            ].copy()

            # Adicionar status real ao df_chart_data
            for _, row in filtered_real_status_for_chart.iterrows():
                df_chart_data.append({
                    'Nome do agente': row['Nome do agente'],
                    'Data': row['Data'],
                    'Start': row['Hora de início do estado - Carimbo de data/hora'],
                    'Finish': row['Hora de término do estado - Carimbo de data/hora'],
                    'Tipo': row['Estado'],
                    'Label': row['Estado'],
                    'Categoria': 'Status Real'
                })

            # Adicionar escala planejada ao df_chart_data
            filtered_escala_for_chart = st.session_state.df_escala[
                st.session_state.df_escala['Nome do agente'].isin(selected_agents)
            ].copy()

            current_date_chart = start_date
            while current_date_chart <= end_date:
                day_of_week_num = current_date_chart.weekday()
                for agent in selected_agents:
                    agent_daily_schedule = filtered_escala_for_chart[
                        (filtered_escala_for_chart['Nome do agente'] == agent) &
                        (filtered_escala_for_chart['Dia da Semana Num'] == day_of_week_num)
                    ]
                    for _, schedule_entry in agent_daily_schedule.iterrows():
                        scale_start_time = schedule_entry['Entrada']
                        scale_end_time = schedule_entry['Saída']

                        if pd.notna(scale_start_time) and pd.notna(scale_end_time):
                            scale_start_dt = datetime.combine(current_date_chart, scale_start_time)
                            scale_end_dt = datetime.combine(current_date_chart, scale_end_time)

                            if scale_end_dt < scale_start_dt: # Escala que vira o dia
                                scale_end_dt += timedelta(days=1)

                            df_chart_data.append({
                                'Nome do agente': agent,
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

                # Criar uma coluna combinada para o eixo Y
                df_chart['Agente_Data_Tipo'] = df_chart['Nome do agente'] + ' - ' + df_chart['Data'].dt.strftime('%Y-%m-%d') + ' (' + df_chart['Tipo'] + ')'

                # Ordenar o eixo Y para melhor visualização
                # Primeiro por agente, depois por data, depois por tipo (Escala primeiro)
                df_chart['Tipo_Order'] = df_chart['Tipo'].apply(lambda x: 0 if x == 'Escala Planejada' else 1)
                df_chart = df_chart.sort_values(by=['Nome do agente', 'Data', 'Tipo_Order'])

                # Definir a ordem das categorias no eixo Y
                y_order = df_chart['Agente_Data_Tipo'].unique().tolist()

                # Altura dinâmica do gráfico
                chart_height = max(500, len(y_order) * 25) # 25 pixels por linha, mínimo de 500

                fig = px.timeline(
                    df_chart,
                    x_start="Start",
                    x_end="Finish",
                    y="Agente_Data_Tipo", # Usar a coluna combinada
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
                    showgrid=True, # Mostrar grade no eixo X
                    gridcolor='lightgray',
                    griddash='dot'
                )
                fig.update_yaxes(
                    title_text="Agente - Data (Tipo)",
                    showgrid=True, # Mostrar grade no eixo Y
                    gridcolor='lightgray',
                    griddash='dot'
                )
                fig.update_layout(hovermode="y unified") # Melhorar o hover

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
