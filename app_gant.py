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
    df = df.rename(columns=expected_columns_report)

    # Normalizar nomes dos agentes
    if 'Nome do agente' in df.columns:
        df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)
    else:
        st.error("Coluna 'Nome do agente' não encontrada no arquivo de status real após renomear. Verifique o cabeçalho do arquivo.")
        return pd.DataFrame()

    # Converter colunas de data/hora
    df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
    df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

    # Preencher NaT em 'Hora de término do estado - Carimbo de data/hora'
    # Se o status_end for NaT, preenche com o final do dia do status_start
    df['Hora de término do estado - Carimbo de data/hora'] = df.apply(
        lambda row: row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
        if pd.isna(row['Hora de término do estado - Carimbo de data/hora']) and pd.notna(row['Hora de início do estado - Carimbo de data/hora'])
        else row['Hora de término do estado - Carimbo de data/hora'],
        axis=1
    )

    # Remover linhas onde as datas de início ou término são inválidas após a conversão
    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'], inplace=True)

    # Ajuste na lógica de cálculo de métricas: se status_end for no dia seguinte ao status_start,
    # ajustar para o final do dia status_start para cálculo diário
    df['Hora de término do estado - Carimbo de data/hora'] = df.apply(
        lambda row: row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
        if row['Hora de término do estado - Carimbo de data/hora'].date() > row['Hora de início do estado - Carimbo de data/hora'].date()
        else row['Hora de término do estado - Carimbo de data/hora'],
        axis=1
    )

    return df

def to_time(val):
    if pd.isna(val):
        return None
    try:
        # Tenta converter para datetime e depois extrair a hora
        dt_val = pd.to_datetime(val, errors='coerce')
        if pd.notna(dt_val):
            return dt_val.time()
        # Se não for um datetime, tenta converter diretamente como string de hora
        return datetime.strptime(str(val).strip(), '%H:%M:%S').time()
    except (ValueError, TypeError):
        try:
            # Tenta formato sem segundos
            return datetime.strptime(str(val).strip(), '%H:%M').time()
        except (ValueError, TypeError):
            return None # Retorna None se não conseguir converter

def process_uploaded_scale(df_scale_raw):
    df = df_scale_raw.copy() # Trabalha com uma cópia para evitar SettingWithCopyWarning

    # Mapeamento explícito das colunas do arquivo de escala
    # Baseado no arquivo escala_gantt.xlsx
    expected_columns_scale = {
        'NOME': 'Nome do agente',
        'DIAS DE ATENDIMENTO': 'Dias de Atendimento',
        'ENTRADA': 'Entrada',
        'SAÍDA': 'Saída',
        'CARGA': 'Carga' # Incluir a coluna CARGA
    }

    # Renomear colunas
    df = df.rename(columns=expected_columns_scale)

    # Verificar se as colunas essenciais existem após o renomeamento
    required_cols = ['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída']
    if not all(col in df.columns for col in required_cols):
        st.error(f"Uma ou mais colunas essenciais ({', '.join(required_cols)}) não foram encontradas no arquivo de escala após renomear. Verifique os cabeçalhos do arquivo.")
        return pd.DataFrame()

    # Normalizar nomes dos agentes
    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Remover linhas onde o nome do agente é NaN após a normalização
    df.dropna(subset=['Nome do agente'], inplace=True)
    if df.empty:
        st.warning("Nenhum agente válido encontrado no arquivo de escala após a limpeza.")
        return pd.DataFrame()

    # Converter horários de entrada e saída
    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    # Remover linhas onde Entrada ou Saída são None após a conversão
    df.dropna(subset=['Entrada', 'Saída'], inplace=True)
    if df.empty:
        st.warning("Nenhuma escala válida encontrada após o processamento dos horários. Verifique as colunas 'ENTRADA' e 'SAÍDA'.")
        return pd.DataFrame()

    # Mapeamento de dias da semana para números (0=Segunda, 6=Domingo)
    dias_map = {
        'SEG': 0, 'SEGUNDA': 0, 'SEGUNDA-FEIRA': 0,
        'TER': 1, 'TERCA': 1, 'TERÇA': 1, 'TERÇA-FEIRA': 1,
        'QUA': 2, 'QUARTA': 2, 'QUARTA-FEIRA': 2,
        'QUI': 3, 'QUINTA': 3, 'QUINTA-FEIRA': 3,
        'SEX': 4, 'SEXTA': 4, 'SEXTA-FEIRA': 4,
        'SAB': 5, 'SABADO': 5,
        'DOM': 6, 'DOMINGO': 6
    }

    expanded_scale_data = []
    for index, row in df.iterrows():
        agent_name = row['Nome do agente']
        dias_str = str(row['Dias de Atendimento'])
        entrada = row['Entrada']
        saida = row['Saída']
        carga = row.get('Carga') # Usar .get() para acessar 'Carga'

        # Limpar e dividir a string de dias de atendimento
        # Substituir " e " por "," para padronizar a divisão
        dias_str_cleaned = dias_str.replace(' E ', ',').replace(' e ', ',')
        # Remover texto adicional como "loja" ou "Call"
        dias_str_cleaned = ''.join(c for c in dias_str_cleaned if c.isalpha() or c == ',')

        dias_list = [
            unicodedata.normalize('NFKD', d.strip()).encode('ascii', 'ignore').decode('utf-8').upper()
            for d in dias_str_cleaned.split(',') if d.strip()
        ]

        for dia_abbr in dias_list:
            dia_num = dias_map.get(dia_abbr)
            if dia_num is not None:
                expanded_scale_data.append({
                    'Nome do agente': agent_name,
                    'Dia da Semana Num': dia_num,
                    'Entrada': entrada,
                    'Saída': saida,
                    'Carga': carga # Incluir Carga na escala expandida
                })
            else:
                st.warning(f"Dia da semana '{dia_abbr}' não reconhecido para o agente {agent_name}. Ignorando.")

    df_escala_expanded = pd.DataFrame(expanded_scale_data)

    if df_escala_expanded.empty:
        st.warning("Nenhuma escala válida foi encontrada após o processamento. Verifique a coluna 'DIAS DE ATENDIMENTO'.")
        return pd.DataFrame()

    return df_escala_expanded

def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    analysis_results = []

    # Filtrar df_real_status e df_escala pelos agentes e datas selecionadas
    df_real_status_filtered = df_real_status[
        (df_real_status['Nome do agente'].isin(selected_agents)) &
        (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
        (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
    ].copy()

    df_escala_filtered = df_escala[
        (df_escala['Nome do agente'].isin(selected_agents))
    ].copy()

    if df_real_status_filtered.empty and df_escala_filtered.empty:
        return pd.DataFrame()

    for agent in selected_agents:
        agent_real_status = df_real_status_filtered[df_real_status_filtered['Nome do agente'] == agent]
        agent_escala = df_escala_filtered[df_escala_filtered['Nome do agente'] == agent]

        if not agent_escala.empty:
            total_scheduled_time_minutes = 0
            total_online_in_schedule_minutes = 0

            current_date_metrics = start_date
            while current_date_metrics <= end_date:
                day_of_week_num = current_date_metrics.weekday() # 0=Seg, 6=Dom

                # Escala para o dia atual
                daily_escala = agent_escala[agent_escala['Dia da Semana Num'] == day_of_week_num]

                for _, scale_row in daily_escala.iterrows():
                    scale_start_time = scale_row['Entrada']
                    scale_end_time = scale_row['Saída']

                    scale_start_dt = datetime.combine(current_date_metrics, scale_start_time)
                    scale_end_dt = datetime.combine(current_date_metrics, scale_end_time)

                    # Se a escala passa da meia-noite, ajusta o end_dt para o dia seguinte
                    if scale_end_dt < scale_start_dt:
                        scale_end_dt += timedelta(days=1)

                    total_scheduled_time_minutes += (scale_end_dt - scale_start_dt).total_seconds() / 60

                    # Status real para o agente no dia atual
                    daily_real_status = agent_real_status[
                        (agent_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date_metrics) &
                        (agent_real_status['Estado'] == 'Unified online')
                    ]

                    for _, status_row in daily_real_status.iterrows():
                        status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                        status_end = status_row['Hora de término do estado - Carimbo de data/hora']

                        # Se o status_end for no dia seguinte ao status_start, ajusta para o final do dia do status_start
                        if status_end.date() > status_start.date() and scale_end_dt.date() == current_date_metrics:
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
        else:
            analysis_results.append({
                'Agente': agent,
                'Total Tempo Escala (min)': 0,
                'Total Tempo Online na Escala (min)': 0,
                'Disponibilidade na Escala (%)': "N/A - Sem escala definida"
            })

    return pd.DataFrame(analysis_results)

# --- Configuração da Página Streamlit ---
st.set_page_config(layout="wide", page_title="Dashboard de Produtividade de Agentes")

st.title("Dashboard de Produtividade de Agentes")

# --- Inicialização do Session State ---
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'all_unique_agents' not in st.session_state:
    st.session_state.all_unique_agents = set() # Inicializa como um conjunto vazio

# --- Abas ---
tab_upload, tab_groups, tab_visualization = st.tabs(["Upload de Dados", "Gerenciar Grupos", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos")

    uploaded_report_file = st.file_uploader("Faça upload do arquivo de Status Real (Tempo_em_Status_do_agente_por_dia_03202026_1006.xlsx)", type=["xlsx"], key="report_uploader")
    uploaded_scale_file = st.file_uploader("Faça upload do arquivo de Escala (escala_gantt.xlsx)", type=["xlsx"], key="scale_uploader")

    if uploaded_report_file is not None:
        try:
            df_report_raw = pd.read_excel(uploaded_report_file, header=0) # O arquivo de status real tem cabeçalhos
            st.session_state.df_real_status = process_uploaded_report(df_report_raw)
            st.success("Arquivo de Status Real carregado e processado com sucesso!")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de status real. Verifique o formato do arquivo. Erro: {e}")
            st.session_state.df_real_status = pd.DataFrame()

    if uploaded_scale_file is not None:
        try:
            df_scale_raw = pd.read_excel(uploaded_scale_file, header=0) # O arquivo de escala tem cabeçalhos
            st.session_state.df_escala = process_uploaded_scale(df_scale_raw)
            st.success("Arquivo de Escala carregado e processado com sucesso!")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de escala. Verifique o formato do arquivo. Erro: {e}")
            st.session_state.df_escala = pd.DataFrame()

    # Atualizar a lista de agentes únicos após o upload
    if not st.session_state.df_real_status.empty and 'Nome do agente' in st.session_state.df_real_status.columns:
        st.session_state.all_unique_agents.update(st.session_state.df_real_status['Nome do agente'].unique())
    if not st.session_state.df_escala.empty and 'Nome do agente' in st.session_state.df_escala.columns:
        st.session_state.all_unique_agents.update(st.session_state.df_escala['Nome do agente'].unique())

    st.write("---")
    st.subheader("Agentes Encontrados nos Arquivos:")
    if st.session_state.all_unique_agents:
        st.write(f"Total de agentes únicos: {len(st.session_state.all_unique_agents)}")
        st.dataframe(pd.DataFrame(list(st.session_state.all_unique_agents), columns=["Nome do Agente"]))
    else:
        st.info("Nenhum agente encontrado. Por favor, faça o upload dos arquivos.")

with tab_groups:
    st.header("Gerenciar Grupos de Agentes")
    if 'agent_groups' not in st.session_state:
        st.session_state.agent_groups = {}

    if st.session_state.all_unique_agents:
        group_name = st.text_input("Nome do novo grupo:")
        selected_agents_for_group = st.multiselect(
            "Selecione os agentes para este grupo:",
            options=sorted(list(st.session_state.all_unique_agents)),
            key="group_agent_selector"
        )
        if st.button("Criar/Atualizar Grupo"):
            if group_name and selected_agents_for_group:
                st.session_state.agent_groups[group_name] = selected_agents_for_group
                st.success(f"Grupo '{group_name}' criado/atualizado com {len(selected_agents_for_group)} agentes.")
            else:
                st.warning("Por favor, insira um nome para o grupo e selecione pelo menos um agente.")

        st.subheader("Grupos Existentes")
        if st.session_state.agent_groups:
            for name, agents in st.session_state.agent_groups.items():
                st.write(f"**{name}** ({len(agents)} agentes)")
                with st.expander(f"Ver agentes em '{name}'"):
                    st.write(", ".join(agents))
            group_to_delete = st.selectbox("Selecione um grupo para excluir:", [""] + list(st.session_state.agent_groups.keys()))
            if st.button("Excluir Grupo") and group_to_delete:
                del st.session_state.agent_groups[group_to_delete]
                st.success(f"Grupo '{group_to_delete}' excluído.")
                st.rerun()
        else:
            st.info("Nenhum grupo criado ainda.")
    else:
        st.info("Faça o upload dos arquivos na aba 'Upload de Dados' para gerenciar grupos.")

with tab_visualization:
    st.header("Visualização e Métricas")

    if not st.session_state.df_real_status.empty or not st.session_state.df_escala.empty:
        all_available_agents = sorted(list(st.session_state.all_unique_agents))

        # Filtro por grupo ou agentes individuais
        filter_by_group = st.checkbox("Filtrar por Grupo de Agentes?")
        selected_agents = []

        if filter_by_group:
            if st.session_state.agent_groups:
                group_selection = st.selectbox(
                    "Selecione um grupo:",
                    options=[""] + list(st.session_state.agent_groups.keys()),
                    key="group_filter"
                )
                if group_selection:
                    selected_agents = st.session_state.agent_groups[group_selection]
            else:
                st.warning("Nenhum grupo disponível. Crie grupos na aba 'Gerenciar Grupos'.")
        else:
            selected_agents = st.multiselect(
                "Selecione os agentes para visualizar:",
                options=all_available_agents,
                default=all_available_agents if len(all_available_agents) <= 5 else [], # Default para poucos agentes
                key="agent_multiselect"
            )

        # Filtro de datas
        min_date_report = st.session_state.df_real_status['Hora de início do estado - Carimbo de data/hora'].min().date() if not st.session_state.df_real_status.empty else datetime.now().date()
        max_date_report = st.session_state.df_real_status['Hora de início do estado - Carimbo de data/hora'].max().date() if not st.session_state.df_real_status.empty else datetime.now().date()

        start_date = st.date_input("Data de Início", value=min_date_report, min_value=min_date_report, max_value=max_date_report)
        end_date = st.date_input("Data de Fim", value=max_date_report, min_value=min_date_report, max_value=max_date_report)

        if selected_agents:
            # Filtrar dados para o gráfico
            df_chart_data = pd.DataFrame()

            # Adicionar dados de status real
            if not st.session_state.df_real_status.empty:
                df_real_status_filtered_chart = st.session_state.df_real_status[
                    (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
                    (st.session_state.df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
                    (st.session_state.df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
                ].copy()
                if not df_real_status_filtered_chart.empty:
                    df_real_status_filtered_chart['Start'] = df_real_status_filtered_chart['Hora de início do estado - Carimbo de data/hora']
                    df_real_status_filtered_chart['Finish'] = df_real_status_filtered_chart['Hora de término do estado - Carimbo de data/hora']
                    df_real_status_filtered_chart['Tipo'] = df_real_status_filtered_chart['Estado']
                    df_real_status_filtered_chart['Data'] = df_real_status_filtered_chart['Start'].dt.date
                    df_real_status_filtered_chart['Agente_Data_Tipo'] = df_real_status_filtered_chart['Nome do agente'] + ' - ' + df_real_status_filtered_chart['Data'].astype(str) + ' (' + df_real_status_filtered_chart['Tipo'] + ')'
                    df_chart_data = pd.concat([df_chart_data, df_real_status_filtered_chart[['Agente_Data_Tipo', 'Start', 'Finish', 'Tipo', 'Nome do agente', 'Data']]])

            # Adicionar dados de escala
            if not st.session_state.df_escala.empty:
                df_escala_filtered_chart = st.session_state.df_escala[
                    (st.session_state.df_escala['Nome do agente'].isin(selected_agents))
                ].copy()

                if not df_escala_filtered_chart.empty:
                    expanded_scale_for_chart = []
                    for agent in selected_agents:
                        agent_escala = df_escala_filtered_chart[df_escala_filtered_chart['Nome do agente'] == agent]
                        if not agent_escala.empty:
                            current_date_chart = start_date
                            while current_date_chart <= end_date:
                                day_of_week_num = current_date_chart.weekday()
                                daily_escala = agent_escala[agent_escala['Dia da Semana Num'] == day_of_week_num]

                                for _, scale_row in daily_escala.iterrows():
                                    scale_start_time = scale_row['Entrada']
                                    scale_end_time = scale_row['Saída']

                                    scale_start_dt = datetime.combine(current_date_chart, scale_start_time)
                                    scale_end_dt = datetime.combine(current_date_chart, scale_end_time)

                                    if scale_end_dt < scale_start_dt:
                                        scale_end_dt += timedelta(days=1)

                                    expanded_scale_for_chart.append({
                                        'Nome do agente': agent,
                                        'Start': scale_start_dt,
                                        'Finish': scale_end_dt,
                                        'Tipo': 'Escala Planejada',
                                        'Data': current_date_chart,
                                        'Agente_Data_Tipo': agent + ' - ' + str(current_date_chart) + ' (Escala Planejada)'
                                    })
                                current_date_chart += timedelta(days=1)

                    if expanded_scale_for_chart:
                        df_expanded_scale_chart = pd.DataFrame(expanded_scale_for_chart)
                        df_chart_data = pd.concat([df_chart_data, df_expanded_scale_chart[['Agente_Data_Tipo', 'Start', 'Finish', 'Tipo', 'Nome do agente', 'Data']]])

            if not df_chart_data.empty:
                # Ordenar para visualização
                df_chart_data['Agente_Data_Tipo_Order'] = df_chart_data['Nome do agente'] + df_chart_data['Data'].astype(str) + df_chart_data['Tipo']
                y_order = df_chart_data['Agente_Data_Tipo'].unique()
                y_order = sorted(y_order, key=lambda x: (x.split(' - ')[0], x.split(' - ')[1].split(' ')[0], x.split('(')[1]))

                # Calcular altura do gráfico dinamicamente
                num_unique_rows = len(df_chart_data['Agente_Data_Tipo'].unique())
                chart_height = max(400, num_unique_rows * 30) # Ajuste a altura conforme necessário

                fig = px.timeline(
                    df_chart_data,
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
