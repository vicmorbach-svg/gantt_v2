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
    # Remove acentos e caracteres especiais
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

    # Normalizar nomes dos agentes
    if 'Nome do agente' in df.columns:
        df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)
    else:
        st.error("Coluna 'Nome do agente' não encontrada após renomear no relatório de status.")
        return pd.DataFrame()

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
        if pd.isna(row['Hora de término do estado - Carimbo de data/hora']) and pd.notna(row['Hora de início do estado - Carimbo de data/hora'])
        else row['Hora de término do estado - Carimbo de data/hora'],
        axis=1
    )

    # Remover linhas onde a data de início ainda é NaT
    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora'], inplace=True)

    # Criar coluna 'Data' para o dia do evento
    df['Data'] = df['Hora de início do estado - Carimbo de data/hora'].dt.normalize()

    # Garantir que 'Duração' seja numérico
    if 'Duração' in df.columns:
        df['Duração'] = pd.to_numeric(df['Duração'], errors='coerce').fillna(0)
    else:
        st.warning("Coluna 'Duração' não encontrada no relatório de status. Definindo como 0.")
        df['Duração'] = 0

    return df

def process_uploaded_scale(df_scale_raw):
    df_scale = df_scale_raw.copy()

    # Mapeamento explícito das colunas do arquivo de escala
    # Baseado no arquivo escala_gantt.xlsx
    expected_columns_scale = {
        'NOME': 'Nome do agente',
        'DIAS DE ATENDIMENTO': 'Dias da Semana',
        'ENTRADA': 'Entrada',
        'SAÍDA': 'Saída',
        'CARGA': 'Carga' # Adicionado para garantir que a coluna CARGA seja reconhecida
    }

    # Renomear as colunas existentes para os nomes esperados
    current_columns = df_scale.columns.tolist()
    rename_map = {}
    for original_col_name, new_col_name in expected_columns_scale.items():
        if original_col_name in current_columns:
            rename_map[original_col_name] = new_col_name
        elif new_col_name in current_columns and original_col_name != new_col_name:
             rename_map[new_col_name] = new_col_name
        else:
            # Se a coluna não for encontrada, podemos logar um aviso ou levantar um erro
            # Para 'Carga', é opcional, então não levantamos erro
            if new_col_name != 'Carga':
                st.warning(f"Coluna '{original_col_name}' não encontrada no arquivo de escala. Verifique o formato do arquivo.")
                return pd.DataFrame() # Retorna DataFrame vazio para evitar erros

    df_scale.rename(columns=rename_map, inplace=True)

    # Normalizar nomes dos agentes
    if 'Nome do agente' in df_scale.columns:
        df_scale['Nome do agente'] = df_scale['Nome do agente'].apply(normalize_agent_name)
    else:
        st.error("Coluna 'Nome do agente' não encontrada após renomear no arquivo de escala.")
        return pd.DataFrame()

    # Remover linhas onde o nome do agente é NaN ou vazio após normalização
    df_scale.dropna(subset=['Nome do agente'], inplace=True)
    df_scale = df_scale[df_scale['Nome do agente'] != '']

    # Função auxiliar para converter string de tempo para datetime.time
    def to_time(time_val):
        if pd.isna(time_val):
            return None
        try:
            # Tenta converter de datetime.time (se já for um objeto time)
            if isinstance(time_val, time):
                return time_val
            # Tenta converter de datetime.datetime (se for um objeto datetime completo)
            if isinstance(time_val, datetime):
                return time_val.time()
            # Tenta converter de string HH:MM:SS ou HH:MM
            return datetime.strptime(str(time_val).strip(), '%H:%M:%S').time()
        except ValueError:
            try:
                return datetime.strptime(str(time_val).strip(), '%H:%M').time()
            except ValueError:
                return None

    df_scale['Entrada'] = df_scale['Entrada'].apply(to_time)
    df_scale['Saída'] = df_scale['Saída'].apply(to_time)

    # Remover linhas onde Entrada ou Saída são None (não puderam ser convertidos)
    df_scale.dropna(subset=['Entrada', 'Saída'], inplace=True)

    # Mapeamento de nomes de dias da semana para número (0=Seg, 6=Dom)
    dias_map = {
        'SEG': 0, 'TER': 1, 'QUA': 2, 'QUI': 3, 'SEX': 4, 'SAB': 5, 'DOM': 6,
        'SEGUNDA': 0, 'TERCA': 1, 'QUARTA': 2, 'QUINTA': 3,
        'SEXTA': 4, 'SABADO': 5, 'DOMINGO': 6
    }

    expanded_scale = []

    for _, row in df_scale.iterrows():
        agent_name = row['Nome do agente']
        # Normaliza a lista de dias (remove espaços, substitui 'E' por vírgula)
        dias_atendimento_str = str(row['Dias da Semana']).upper() \
                                 .replace(' ', '') \
                                 .replace('E', ',') \
                                 .split(',')

        entrada = row['Entrada']
        saida   = row['Saída']
        carga   = row.get('Carga') # Usa .get() para acessar 'Carga', tornando-a opcional

        for dia_str in dias_atendimento_str:
            # Normaliza o nome do dia (remove acentos)
            dia_str_clean = unicodedata.normalize('NFKD', dia_str) \
                                          .encode('ascii', 'ignore') \
                                          .decode('utf-8').strip()

            if dia_str_clean in dias_map:
                expanded_scale.append({
                    'Nome do agente'      : agent_name,
                    'Dia da Semana Num'   : dias_map[dia_str_clean],
                    'Dia da Semana'      : dia_str_clean,
                    'Entrada'            : entrada,
                    'Saída'              : saida,
                    'Carga'              : carga   # adiciona a carga aqui
                })
            elif dia_str_clean and dia_str_clean not in ('CALL', 'LOJA'):
                # Emite aviso apenas no Streamlit (não interrompe o processamento)
                st.warning(f"Dia da semana '{dia_str}' não reconhecido para o agente {agent_name}. Ignorando.")

    df_expanded_scale = pd.DataFrame(expanded_scale)

    # Caso a planilha de escala não contenha a coluna 'Carga', preenche com NaN
    if 'Carga' not in df_expanded_scale.columns:
        df_expanded_scale['Carga'] = np.nan

    return df_expanded_scale

# --- Layout do Streamlit ---
st.set_page_config(layout="wide", page_title="Dashboard de Aderência de Escala")

st.title("Dashboard de Aderência de Escala de Agentes")

# Inicializa session_state para armazenar DataFrames e outras variáveis
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'all_unique_agents' not in st.session_state:
    st.session_state.all_unique_agents = []
if 'agents_in_report_only' not in st.session_state:
    st.session_state.agents_in_report_only = []
if 'agents_in_scale_only' not in st.session_state:
    st.session_state.agents_in_scale_only = []
if 'common_agents' not in st.session_state:
    st.session_state.common_agents = []
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}


# Abas
tab_upload, tab_groups, tab_visualization = st.tabs(["Upload de Dados", "Gerenciar Grupos", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos")

    uploaded_file_report = st.file_uploader("Faça upload do relatório de status (Tempo_em_Status_do_agente_por_dia_03202026_1006.xlsx)", type=["xlsx"], key="report_uploader")
    uploaded_file_scale = st.file_uploader("Faça upload do arquivo de escala (escala_gantt.xlsx)", type=["xlsx"], key="scale_uploader")

    if uploaded_file_report and uploaded_file_scale:
        try:
            # Lendo o relatório de status com cabeçalho
            df_report_raw = pd.read_excel(uploaded_file_report, header=0)
            st.session_state.df_real_status = process_uploaded_report(df_report_raw)
            st.success("Relatório de status carregado e processado com sucesso!")

            # Lendo o arquivo de escala com cabeçalho
            df_scale_raw = pd.read_excel(uploaded_file_scale, header=0)
            st.session_state.df_escala = process_uploaded_scale(df_scale_raw)
            st.success("Arquivo de escala carregado e processado com sucesso!")

            # Identificar agentes únicos e comparar
            if not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
                all_agents_report = set(st.session_state.df_real_status['Nome do agente'].unique())
                all_agents_scale = set(st.session_state.df_escala['Nome do agente'].unique())

                st.session_state.agents_in_report_only = sorted(list(all_agents_report - all_agents_scale))
                st.session_state.agents_in_scale_only = sorted(list(all_agents_scale - all_agents_report))
                st.session_state.common_agents = sorted(list(all_agents_report.intersection(all_agents_scale)))
                st.session_state.all_unique_agents = sorted(list(all_agents_report.union(all_agents_scale)))

                st.subheader("Comparativo de Agentes")
                st.write(f"Total de agentes únicos: {len(st.session_state.all_unique_agents)}")
                st.write(f"Agentes presentes em ambos os arquivos: {len(st.session_state.common_agents)}")

                if st.session_state.agents_in_report_only:
                    st.warning(f"Agentes no relatório de status, mas sem escala: {', '.join(st.session_state.agents_in_report_only)}")
                if st.session_state.agents_in_scale_only:
                    st.warning(f"Agentes na escala, mas sem dados de status: {', '.join(st.session_state.agents_in_scale_only)}")
            else:
                st.warning("Um ou ambos os DataFrames estão vazios após o processamento. Verifique os arquivos de entrada.")


        except Exception as e:
            st.error(f"Erro ao processar os arquivos: {e}")
            st.exception(e)
    elif uploaded_file_report:
        st.info("Por favor, faça upload também do arquivo de escala.")
    elif uploaded_file_scale:
        st.info("Por favor, faça upload também do relatório de status.")
    else:
        st.info("Aguardando upload dos arquivos de relatório e escala.")

with tab_groups:
    st.header("Gerenciar Grupos de Agentes")

    if 'all_unique_agents' not in st.session_state or not st.session_state.all_unique_agents:
        st.warning("Por favor, faça o upload dos arquivos na aba 'Upload de Dados' primeiro para ver os agentes.")
    else:
        if 'agent_groups' not in st.session_state:
            st.session_state.agent_groups = {
                '6h20min': [],
                '8h12min': []
            }

        st.subheader("Agentes sem grupo definido")
        assigned_agents = set()
        for group_name, agents_in_group in st.session_state.agent_groups.items():
            assigned_agents.update(agents_in_group)

        unassigned_agents = sorted(list(set(st.session_state.all_unique_agents) - assigned_agents))
        if unassigned_agents:
            st.write(f"Agentes: {', '.join(unassigned_agents)}")
        else:
            st.info("Todos os agentes estão atribuídos a um grupo ou não há agentes carregados.")

        st.subheader("Criar ou Editar Grupos")

        # Exibir grupos existentes e permitir edição
        for group_name, agents_in_group in st.session_state.agent_groups.items():
            st.write(f"**Grupo: {group_name}**")
            selected_agents_for_group = st.multiselect(
                f"Selecione agentes para o grupo '{group_name}'",
                st.session_state.all_unique_agents,
                default=agents_in_group,
                key=f"multiselect_{group_name}"
            )
            st.session_state.agent_groups[group_name] = selected_agents_for_group

        # Adicionar novo grupo
        with st.expander("Adicionar Novo Grupo"):
            new_group_name = st.text_input("Nome do novo grupo")
            if st.button("Adicionar Grupo") and new_group_name:
                if new_group_name not in st.session_state.agent_groups:
                    st.session_state.agent_groups[new_group_name] = []
                    st.success(f"Grupo '{new_group_name}' adicionado.")
                else:
                    st.warning("Já existe um grupo com esse nome.")

with tab_visualization:
    st.header("Visualização da Escala e Métricas")

    if 'df_real_status' not in st.session_state or 'df_escala' not in st.session_state or st.session_state.df_real_status.empty or st.session_state.df_escala.empty:
        st.warning("Por favor, faça o upload de ambos os arquivos na aba 'Upload de Dados' primeiro e certifique-se de que não estão vazios.")
    else:
        # --- Filtros na barra lateral ---
        st.sidebar.header("Filtros")

        # Filtro por grupo
        if 'agent_groups' in st.session_state and st.session_state.agent_groups:
            group_options = ["Todos"] + list(st.session_state.agent_groups.keys())
            selected_group = st.sidebar.selectbox("Filtrar por Grupo", options=group_options)

            if selected_group == "Todos":
                agents_from_group = st.session_state.all_unique_agents
            else:
                agents_from_group = st.session_state.agent_groups.get(selected_group, [])
        else:
            agents_from_group = st.session_state.all_unique_agents
            st.sidebar.info("Nenhum grupo definido. Exibindo todos os agentes.")

        # Filtro por agente
        selected_agents = st.sidebar.multiselect(
            "Selecione os Agentes",
            options=agents_from_group,
            default=agents_from_group if len(agents_from_group) <= 10 else [] # Limita o default para não sobrecarregar
        )

        # Filtro por data
        min_date_report = st.session_state.df_real_status['Data'].min().date()
        max_date_report = st.session_state.df_real_status['Data'].max().date()

        date_range = st.sidebar.date_input(
            "Selecione o Intervalo de Datas",
            value=(min_date_report, max_date_report),
            min_value=min_date_report,
            max_value=max_date_report
        )

        if len(date_range) == 2:
            start_date, end_date = date_range
        else:
            st.warning("Por favor, selecione um intervalo de datas válido.")
            st.stop()

        # --- Processamento e Filtragem ---
        if selected_agents:
            filtered_df_real_status = st.session_state.df_real_status[
                (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
                (st.session_state.df_real_status['Data'] >= pd.to_datetime(start_date)) &
                (st.session_state.df_real_status['Data'] <= pd.to_datetime(end_date))
            ].copy()

            # Filtrar escala pelos agentes selecionados e dias da semana no intervalo de datas
            filtered_df_escala = st.session_state.df_escala[
                st.session_state.df_escala['Nome do agente'].isin(selected_agents)
            ].copy()

            # Criar DataFrame para o gráfico
            df_chart_data = []

            # Adicionar dados de status real
            for _, row in filtered_df_real_status.iterrows():
                df_chart_data.append({
                    'Agente': row['Nome do agente'],
                    'Data': row['Data'],
                    'Início': row['Hora de início do estado - Carimbo de data/hora'],
                    'Fim': row['Hora de término do estado - Carimbo de data/hora'],
                    'Tipo': row['Estado'],
                    'Categoria': 'Status Real'
                })

            # Adicionar dados da escala
            # Gerar datas para o intervalo selecionado
            current_date = start_date
            while current_date <= end_date:
                day_of_week_num = current_date.weekday() # 0=Seg, 6=Dom

                for _, scale_row in filtered_df_escala.iterrows():
                    if scale_row['Dia da Semana Num'] == day_of_week_num:
                        agent_name = scale_row['Nome do agente']

                        # Criar datetime objects para início e fim da escala no dia atual
                        if pd.notna(scale_row['Entrada']) and pd.notna(scale_row['Saída']):
                            scale_start_dt = datetime.combine(current_date, scale_row['Entrada'])
                            scale_end_dt = datetime.combine(current_date, scale_row['Saída'])

                            # Se a escala termina no dia seguinte (ex: 22:00 - 06:00)
                            if scale_end_dt < scale_start_dt:
                                scale_end_dt += timedelta(days=1)

                            df_chart_data.append({
                                'Agente': agent_name,
                                'Data': pd.to_datetime(current_date),
                                'Início': scale_start_dt,
                                'Fim': scale_end_dt,
                                'Tipo': 'Escala Planejada',
                                'Categoria': 'Escala'
                            })
                current_date += timedelta(days=1)

            df_chart = pd.DataFrame(df_chart_data)

            if not df_chart.empty:
                # Ordenar para melhor visualização
                df_chart = df_chart.sort_values(by=['Agente', 'Data', 'Início'])

                # Criar uma coluna combinada para o eixo Y para separar escala e status real
                df_chart['Agente_Data_Tipo'] = df_chart['Agente'] + ' - ' + df_chart['Data'].dt.strftime('%Y-%m-%d') + ' (' + df_chart['Categoria'] + ')'

                # Definir cores para os tipos de status e escala
                color_map = {
                    'Unified online': 'green',
                    'Unified away': 'orange',
                    'Unified offline': 'red',
                    'Unified transfers only': 'purple',
                    'Escala Planejada': 'blue'
                }

                # Ajustar a altura do gráfico dinamicamente
                unique_y_values = df_chart['Agente_Data_Tipo'].nunique()
                chart_height = max(400, unique_y_values * 30) # 30 pixels por linha, mínimo de 400

                fig = px.timeline(
                    df_chart,
                    x_start="Início",
                    x_end="Fim",
                    y="Agente_Data_Tipo",
                    color="Tipo",
                    color_discrete_map=color_map,
                    title="Comparativo de Escala Planejada vs. Status Real",
                    height=chart_height
                )

                fig.update_yaxes(
                    categoryorder="array",
                    categoryarray=df_chart['Agente_Data_Tipo'].unique() # Garante a ordem correta
                )

                # Adicionar linhas de grade
                fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGrey')
                fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGrey')

                st.plotly_chart(fig, use_container_width=True)

                st.subheader("Métricas de Disponibilidade e Aderência")

                # Calcular métricas
                analysis_results = []
                for agent in selected_agents:
                    agent_df_real = filtered_df_real_status[filtered_df_real_status['Nome do agente'] == agent]
                    agent_df_escala = filtered_df_escala[filtered_df_escala['Nome do agente'] == agent]

                    total_scheduled_time_minutes = 0
                    total_online_in_schedule_minutes = 0

                    # Iterar sobre cada dia no intervalo selecionado
                    current_date_metrics = start_date
                    while current_date_metrics <= end_date:
                        day_of_week_num = current_date_metrics.weekday()

                        # Escala para o dia
                        daily_scale = agent_df_escala[agent_df_escala['Dia da Semana Num'] == day_of_week_num]

                        if not daily_scale.empty:
                            for _, scale_entry in daily_scale.iterrows():
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
                st.dataframe(df_analysis)
            else:
                st.info("Nenhum dado para exibir no gráfico com os filtros selecionados.")
        else:
            st.warning("Por favor, selecione pelo menos um agente para a análise.")
