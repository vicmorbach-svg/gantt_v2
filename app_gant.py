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
        'Tempo do agente no estado / Minutos': 'Duração' # Renomeado para Duração para consistência
    }

    # Renomear as colunas existentes para os nomes esperados
    # Usamos um dicionário de mapeamento para evitar erros se a ordem mudar
    current_columns = df.columns.tolist()
    rename_map = {}
    for original_col_name, new_col_name in expected_columns_report.items():
        if original_col_name in current_columns:
            rename_map[original_col_name] = new_col_name
        elif new_col_name in current_columns and original_col_name != new_col_name:
             rename_map[new_col_name] = new_col_name
        else:
            # Se a coluna não for encontrada, podemos logar um aviso ou levantar um erro
            st.warning(f"Coluna '{original_col_name}' não encontrada no relatório de status. Verifique o formato do arquivo.")
            return pd.DataFrame() # Retorna DataFrame vazio para evitar erros

    df.rename(columns=rename_map, inplace=True)

    # Normalizar nomes dos agentes AQUI
    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Remover linhas onde o nome do agente é NaN ou vazio após normalização
    df.dropna(subset=['Nome do agente'], inplace=True)
    df = df[df['Nome do agente'] != '']

    # Converter colunas de data/hora
    df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
    df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

    # Preencher NaT em 'Hora de término do estado - Carimbo de data/hora'
    # Se o término for NaT, assume-se que o status dura até o final do dia de início
    for index, row in df.iterrows():
        if pd.isna(row['Hora de término do estado - Carimbo de data/hora']):
            if pd.notna(row['Hora de início do estado - Carimbo de data/hora']):
                df.at[index, 'Hora de término do estado - Carimbo de data/hora'] = row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
            else:
                # Se nem o início existe, remove a linha ou trata como erro
                df.drop(index, inplace=True)
                continue

    # Remover linhas onde a data de início ainda é NaT
    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora'], inplace=True)

    # Criar coluna 'Data' para o dia do evento
    df['Data'] = df['Hora de início do estado - Carimbo de data/hora'].dt.normalize()

    # Garantir que 'Duração' seja numérico
    df['Duração'] = pd.to_numeric(df['Duração'], errors='coerce').fillna(0)

    return df

def to_time(val):
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
    current_columns = df.columns.tolist()
    rename_map = {}
    for original_col_name, new_col_name in expected_columns_scale.items():
        if original_col_name in current_columns:
            rename_map[original_col_name] = new_col_name
        elif new_col_name in current_columns and original_col_name != new_col_name:
             rename_map[new_col_name] = new_col_name
        else:
            # Se a coluna não for encontrada, podemos logar um aviso ou levantar um erro
            # Para 'Carga', se não existir, não é crítico, pode ser ignorado
            if new_col_name != 'Carga':
                st.warning(f"Coluna '{original_col_name}' não encontrada no arquivo de escala. Verifique o formato do arquivo.")
                return pd.DataFrame() # Retorna DataFrame vazio para evitar erros

    df.rename(columns=rename_map, inplace=True)

    # Normalizar nomes dos agentes AQUI
    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Remover linhas onde o nome do agente é NaN ou vazio após normalização
    df.dropna(subset=['Nome do agente'], inplace=True)
    df = df[df['Nome do agente'] != '']

    # Converter colunas de horário usando a função to_time
    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    # Remover linhas onde Entrada ou Saída são NaN após a conversão
    df.dropna(subset=['Entrada', 'Saída'], inplace=True)

    # Mapeamento de dias da semana mais robusto
    dias_map = {
        'SEG': 0, 'SEGUNDA': 0, 'SEGUNDA-FEIRA': 0,
        'TER': 1, 'TERCA': 1, 'TERÇA': 1, 'TERÇA-FEIRA': 1,
        'QUA': 2, 'QUARTA': 2, 'QUARTA-FEIRA': 2,
        'QUI': 3, 'QUINTA': 3, 'QUINTA-FEIRA': 3,
        'SEX': 4, 'SEXTA': 4, 'SEXTA-FEIRA': 4,
        'SAB': 5, 'SABADO': 5, 'SÁBADO': 5,
        'DOM': 6, 'DOMINGO': 6
    }

    expanded_scale_data = []
    for _, row in df.iterrows():
        agent_name = row['Nome do agente']
        dias_str = str(row['Dias de Atendimento']).upper()
        entrada = row['Entrada']
        saida = row['Saída']
        carga = row.get('Carga') # Usar .get() para acessar 'Carga' de forma segura

        # Dividir a string de dias e limpar cada dia
        dias_list = [d.strip() for d in dias_str.replace(' E ', ',').split(',') if d.strip()]

        for dia_abbr in dias_list:
            # Normalizar a abreviação do dia para o mapeamento
            normalized_dia_abbr = unicodedata.normalize('NFKD', dia_abbr).encode('ascii', 'ignore').decode('utf-8').strip()

            if normalized_dia_abbr in dias_map:
                day_of_week_num = dias_map[normalized_dia_abbr]
                expanded_scale_data.append({
                    'Nome do agente': agent_name,
                    'Dia da Semana Num': day_of_week_num,
                    'Entrada': entrada,
                    'Saída': saida,
                    'Carga': carga # Incluir Carga na escala expandida
                })
            else:
                st.warning(f"Dia da semana '{dia_abbr}' não reconhecido para o agente {agent_name}. Ignorando.")

    if not expanded_scale_data:
        return pd.DataFrame() # Retorna DataFrame vazio se não houver dados de escala válidos

    df_escala_expanded = pd.DataFrame(expanded_scale_data)
    return df_escala_expanded

# --- Funções de Cálculo de Métricas ---
def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    analysis_results = []

    # Filtrar dados de status real e escala para os agentes e datas selecionadas
    filtered_real_status = df_real_status[
        (df_real_status['Nome do agente'].isin(selected_agents)) &
        (df_real_status['Data'] >= start_date) &
        (df_real_status['Data'] <= end_date)
    ].copy()

    filtered_escala = df_escala[df_escala['Nome do agente'].isin(selected_agents)].copy()

    # Iterar por cada agente selecionado
    for agent in selected_agents:
        agent_df_real = filtered_real_status[filtered_real_status['Nome do agente'] == agent]
        agent_df_escala = filtered_escala[filtered_escala['Nome do agente'] == agent]

        total_scheduled_time_minutes = 0
        total_online_in_schedule_minutes = 0

        # Iterar por cada dia no intervalo de datas selecionado
        current_date_metrics = start_date
        while current_date_metrics <= end_date:
            day_of_week_num = current_date_metrics.weekday() # 0=Seg, 6=Dom

            # Encontrar a escala para o agente e dia da semana atual
            scale_for_day = agent_df_escala[agent_df_escala['Dia da Semana Num'] == day_of_week_num]

            if not scale_for_day.empty:
                # Pode haver múltiplas entradas de escala para o mesmo agente/dia, pegar a primeira ou combinar
                # Por simplicidade, vamos considerar a primeira entrada encontrada
                scale_entry = scale_for_day.iloc[0] 
                scale_start_time = scale_entry['Entrada']
                scale_end_time = scale_entry['Saída']

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
    else:
        analysis_results.append({
            'Agente': agent,
            'Total Tempo Escala (min)': 0,
            'Total Tempo Online na Escala (min)': 0,
            'Disponibilidade na Escala (%)': "N/A - Sem escala definida"
        })

    df_analysis = pd.DataFrame(analysis_results)
    return df_analysis # Retorna o DataFrame de análise

# --- Layout do Streamlit ---
st.sidebar.header("Filtros")

# Inicializa session_state para armazenar DataFrames e outras variáveis
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'all_unique_agents' not in st.session_state:
    st.session_state.all_unique_agents = set()
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}

tab_upload, tab_groups, tab_visualization = st.tabs(["Upload de Dados", "Gerenciar Grupos", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos")

    uploaded_report_file = st.file_uploader("Carregar Relatório de Status (Excel)", type=["xlsx"])
    if uploaded_report_file is not None:
        try:
            df_report_raw = pd.read_excel(uploaded_report_file, header=0) # Ler com cabeçalho
            st.session_state.df_real_status = process_uploaded_report(df_report_raw)
            if not st.session_state.df_real_status.empty:
                st.success("Relatório de Status carregado e processado com sucesso!")
                # Atualizar lista de agentes únicos
                st.session_state.all_unique_agents.update(st.session_state.df_real_status['Nome do agente'].unique())
            else:
                st.error("Erro ao processar o relatório de status. Verifique o formato do arquivo.")
        except Exception as e:
            st.error(f"Erro ao processar o relatório de status: {e}")
            st.session_state.df_real_status = pd.DataFrame()

    uploaded_scale_file = st.file_uploader("Carregar Escala Pré-definida (Excel)", type=["xlsx"])
    if uploaded_scale_file is not None:
        try:
            df_scale_raw = pd.read_excel(uploaded_scale_file, header=0) # Ler com cabeçalho
            st.session_state.df_escala = process_uploaded_scale(df_scale_raw)
            if not st.session_state.df_escala.empty:
                st.success("Escala Pré-definida carregada e processada com sucesso!")
                # Atualizar lista de agentes únicos
                st.session_state.all_unique_agents.update(st.session_state.df_escala['Nome do agente'].unique())
            else:
                st.error("Erro ao processar o arquivo de escala. Verifique o formato do arquivo.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de escala: {e}")
            st.session_state.df_escala = pd.DataFrame()

with tab_groups:
    st.header("Gerenciar Grupos de Agentes")
    if st.session_state.all_unique_agents:
        all_agents_list = sorted(list(st.session_state.all_unique_agents))

        group_name = st.text_input("Nome do novo grupo:")
        selected_agents_for_group = st.multiselect("Selecione agentes para o grupo:", all_agents_list)

        if st.button("Criar/Atualizar Grupo"):
            if group_name:
                st.session_state.agent_groups[group_name] = selected_agents_for_group
                st.success(f"Grupo '{group_name}' criado/atualizado com {len(selected_agents_for_group)} agentes.")
            else:
                st.warning("Por favor, insira um nome para o grupo.")

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
    else:
        st.info("Faça o upload dos arquivos na aba 'Upload de Dados' para gerenciar grupos.")

with tab_visualization:
    st.header("Visualização e Métricas")

    if not st.session_state.df_real_status.empty or not st.session_state.df_escala.empty:
        all_agents_in_data = set()
        if not st.session_state.df_real_status.empty and 'Nome do agente' in st.session_state.df_real_status.columns:
            all_agents_in_data.update(st.session_state.df_real_status['Nome do agente'].unique())
        if not st.session_state.df_escala.empty and 'Nome do agente' in st.session_state.df_escala.columns:
            all_agents_in_data.update(st.session_state.df_escala['Nome do agente'].unique())

        all_agents_list = sorted(list(all_agents_in_data))

        # Comparativo de Agentes
        st.subheader("Comparativo de Agentes")
        if not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
            agents_in_report = set(st.session_state.df_real_status['Nome do agente'].unique())
            agents_in_scale = set(st.session_state.df_escala['Nome do agente'].unique())

            only_in_report = agents_in_report - agents_in_scale
            only_in_scale = agents_in_scale - agents_in_report
            in_both = agents_in_report.intersection(agents_in_scale)

            if only_in_report:
                st.warning(f"Agentes no relatório de status, mas não na escala: {', '.join(sorted(list(only_in_report)))}")
            if only_in_scale:
                st.warning(f"Agentes na escala, mas não no relatório de status: {', '.join(sorted(list(only_in_scale)))}")
            if in_both:
                st.success(f"Agentes presentes em ambos os arquivos: {', '.join(sorted(list(in_both)))}")
            if not only_in_report and not only_in_scale and not in_both:
                st.info("Nenhum agente encontrado em ambos os arquivos após a normalização. Verifique os dados.")
        else:
            st.info("Carregue ambos os arquivos para ver o comparativo de agentes.")

        # Filtros para visualização
        st.sidebar.subheader("Filtros de Visualização")
        selected_group = st.sidebar.selectbox("Selecionar Grupo de Agentes:", ["Todos"] + list(st.session_state.agent_groups.keys()))

        if selected_group == "Todos":
            selected_agents = st.sidebar.multiselect("Selecionar Agentes:", all_agents_list, default=all_agents_list)
        else:
            selected_agents = st.sidebar.multiselect("Selecionar Agentes:", all_agents_list, default=st.session_state.agent_groups.get(selected_group, []))

        # Ajustar o default do seletor de agentes para incluir todos se nenhum grupo for selecionado
        if not selected_agents and all_agents_list:
            selected_agents = all_agents_list

        min_date_report = st.session_state.df_real_status['Data'].min().date() if not st.session_state.df_real_status.empty else datetime.today().date()
        max_date_report = st.session_state.df_real_status['Data'].max().date() if not st.session_state.df_real_status.empty else datetime.today().date()

        start_date, end_date = st.sidebar.date_input(
            "Intervalo de Datas:",
            value=[min_date_report, max_date_report],
            min_value=min_date_report,
            max_value=max_date_report
        )

        # Converter para datetime para comparação com colunas datetime
        start_date = datetime.combine(start_date, datetime.min.time())
        end_date = datetime.combine(end_date, datetime.max.time())

        if selected_agents:
            st.subheader("Gráfico de Escala e Status Real")
            # Filtrar dados para o gráfico
            df_chart_data = pd.DataFrame()

            if not st.session_state.df_real_status.empty:
                filtered_real_status_chart = st.session_state.df_real_status[
                    (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
                    (st.session_state.df_real_status['Hora de início do estado - Carimbo de data/hora'] >= start_date) &
                    (st.session_state.df_real_status['Hora de início do estado - Carimbo de data/hora'] <= end_date)
                ].copy()
                if not filtered_real_status_chart.empty:
                    filtered_real_status_chart['Categoria'] = 'Status Real'
                    filtered_real_status_chart['Start'] = filtered_real_status_chart['Hora de início do estado - Carimbo de data/hora']
                    filtered_real_status_chart['End'] = filtered_real_status_chart['Hora de término do estado - Carimbo de data/hora']
                    filtered_real_status_chart['Label'] = filtered_real_status_chart['Estado']
                    df_chart_data = pd.concat([df_chart_data, filtered_real_status_chart[['Nome do agente', 'Data', 'Categoria', 'Start', 'End', 'Label']]])

            if not st.session_state.df_escala.empty:
                filtered_escala_chart = st.session_state.df_escala[
                    st.session_state.df_escala['Nome do agente'].isin(selected_agents)
                ].copy()

                if not filtered_escala_chart.empty:
                    expanded_scale_for_chart = []
                    for _, row in filtered_escala_chart.iterrows():
                        agent_name = row['Nome do agente']
                        day_of_week_num = row['Dia da Semana Num']
                        entrada = row['Entrada']
                        saida = row['Saída']

                        current_date_chart = start_date.date()
                        while current_date_chart <= end_date.date():
                            if current_date_chart.weekday() == day_of_week_num:
                                scale_start_dt = datetime.combine(current_date_chart, entrada)
                                scale_end_dt = datetime.combine(current_date_chart, saida)
                                if scale_end_dt < scale_start_dt: # Escala que vira o dia
                                    scale_end_dt += timedelta(days=1)

                                expanded_scale_for_chart.append({
                                    'Nome do agente': agent_name,
                                    'Data': current_date_chart,
                                    'Categoria': 'Escala Planejada',
                                    'Start': scale_start_dt,
                                    'End': scale_end_dt,
                                    'Label': 'Escala'
                                })
                            current_date_chart += timedelta(days=1)

                    if expanded_scale_for_chart:
                        df_expanded_scale_chart = pd.DataFrame(expanded_scale_for_chart)
                        df_chart_data = pd.concat([df_chart_data, df_expanded_scale_chart])

            if not df_chart_data.empty:
                # Ordenar para garantir que a escala apareça antes do status real para o mesmo agente/data
                df_chart_data['Agente_Data_Tipo'] = df_chart_data['Nome do agente'] + ' - ' + df_chart_data['Data'].dt.strftime('%Y-%m-%d') + ' (' + df_chart_data['Categoria'] + ')'

                # Definir a ordem das categorias para o gráfico
                category_order = ['Escala Planejada', 'Status Real']
                df_chart_data['Categoria'] = pd.Categorical(df_chart_data['Categoria'], categories=category_order, ordered=True)
                df_chart_data = df_chart_data.sort_values(by=['Nome do agente', 'Data', 'Categoria'])

                # Ajustar a altura do gráfico dinamicamente
                unique_y_values = df_chart_data['Agente_Data_Tipo'].nunique()
                chart_height = max(300, unique_y_values * 25) # 25 pixels por linha, mínimo de 300

                fig = px.timeline(
                    df_chart_data,
                    x_start="Start",
                    x_end="End",
                    y="Agente_Data_Tipo", # Usar a coluna combinada para o eixo Y
                    color="Label",
                    hover_name="Nome do agente",
                    hover_data={"Start": "|%H:%M:%S", "End": "|%H:%M:%S", "Label": True, "Categoria": True},
                    title="Escala Planejada vs. Status Real do Agente",
                    height=chart_height
                )

                fig.update_yaxes(categoryorder="array", categoryarray=df_chart_data['Agente_Data_Tipo'].unique())
                fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGrey', tickformat="%H:%M")
                fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGrey')
                fig.update_layout(
                    xaxis_title="Hora do Dia",
                    yaxis_title="Agente e Data",
                    legend_title_text='Legenda'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nenhum dado para exibir no gráfico com os filtros selecionados.")

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
            st.warning("Por favor, selecione pelo menos um agente para a análise.")
    else:
        st.info("Por favor, faça o upload de ambos os arquivos na aba 'Upload de Dados' primeiro.")
