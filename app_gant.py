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

    # Renomear as colunas existentes para os nomes esperados
    # Usamos um dicionário de mapeamento para evitar erros se a ordem mudar
    current_columns = df.columns.tolist()
    rename_map = {}
    for original_col, new_col in expected_columns_report.items():
        if original_col in current_columns:
            rename_map[original_col] = new_col
        elif new_col in current_columns and original_col != new_col: # Caso o nome já esteja como o esperado
             rename_map[new_col] = new_col # Garante que não será renomeado para si mesmo
        else:
            # Se a coluna não for encontrada, podemos logar um aviso ou levantar um erro
            st.warning(f"Coluna '{original_col}' não encontrada no relatório de status. Verifique o formato do arquivo.")
            return pd.DataFrame() # Retorna DataFrame vazio para evitar erros

    df.rename(columns=rename_map, inplace=True)

    # Normalizar nomes dos agentes
    if 'Nome do agente' in df.columns:
        df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)
    else:
        st.error("Coluna 'Nome do agente' não encontrada após renomear no relatório de status.")
        return pd.DataFrame()

    # Converter colunas de data/hora
    df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
    df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

    # Preencher NaT em 'Hora de término do estado - Carimbo de data/hora'
    # Se o término for NaT, assume-se que o status dura até o final do dia de início
    for index, row in df.iterrows():
        if pd.isna(row['Hora de término do estado - Carimbo de data/hora']):
            if pd.notna(row['Hora de início do estado - Carimbo de data/hora']):
                # Define o término como o final do dia de início
                df.at[index, 'Hora de término do estado - Carimbo de data/hora'] = \
                    row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
            else:
                # Se o início também for NaT, remove a linha ou trata de outra forma
                df.drop(index, inplace=True) # Remove linhas sem data de início

    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'], inplace=True)

    # Criar coluna 'Data' para facilitar a agregação por dia
    df['Data'] = df['Hora de início do estado - Carimbo de data/hora'].dt.normalize()

    # Ajustar status_end para não ultrapassar o dia do status_start para cálculos diários
    # Isso é importante para que o cálculo de métricas por dia seja preciso
    df['status_end_adjusted'] = df.apply(
        lambda row: min(row['Hora de término do estado - Carimbo de data/hora'], 
                        row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59, microsecond=999999))
        if row['Hora de término do estado - Carimbo de data/hora'].date() > row['Hora de início do estado - Carimbo de data/hora'].date()
        else row['Hora de término do estado - Carimbo de data/hora'], axis=1
    )

    return df

def to_time(val):
    if pd.isna(val):
        return None
    try:
        # Tenta converter para datetime primeiro, depois extrai a hora
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
        'SAÍDA': 'Saída'
    }

    # Renomear as colunas existentes para os nomes esperados
    current_columns = df.columns.tolist()
    rename_map = {}
    for original_col, new_col in expected_columns_scale.items():
        if original_col in current_columns:
            rename_map[original_col] = new_col
        elif new_col in current_columns and original_col != new_col:
             rename_map[new_col] = new_col
        else:
            st.warning(f"Coluna '{original_col}' não encontrada no arquivo de escala. Verifique o formato do arquivo.")
            return pd.DataFrame() # Retorna DataFrame vazio para evitar erros

    df.rename(columns=rename_map, inplace=True)

    # Normalizar nomes dos agentes
    if 'Nome do agente' in df.columns:
        df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)
    else:
        st.error("Coluna 'Nome do agente' não encontrada após renomear no arquivo de escala.")
        return pd.DataFrame()

    # Remover linhas onde o nome do agente é NaN após a normalização
    df.dropna(subset=['Nome do agente'], inplace=True)
    if df.empty:
        st.warning("Nenhum agente válido encontrado no arquivo de escala após a normalização.")
        return pd.DataFrame()

    # Converter horários de entrada e saída
    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    # Remover linhas com horários inválidos
    df.dropna(subset=['Entrada', 'Saída'], inplace=True)
    if df.empty:
        st.warning("Nenhuma escala válida encontrada após processar os horários.")
        return pd.DataFrame()

    # Mapeamento de dias da semana para números (0=Seg, 6=Dom)
    dias_map = {
        'SEG': 0, 'SEGUNDA': 0,
        'TER': 1, 'TERCA': 1,
        'QUA': 2, 'QUARTA': 2,
        'QUI': 3, 'QUINTA': 3,
        'SEX': 4, 'SEXTA': 4,
        'SAB': 5, 'SABADO': 5,
        'DOM': 6, 'DOMINGO': 6
    }

    # Expandir a escala para cada dia da semana
    expanded_scale = []
    for _, row in df.iterrows():
        dias_atendimento_str = str(row['Dias de Atendimento']).upper()
        # Lidar com formatos como "Seg e Qui" ou "Seg,Ter,Qua"
        dias_list = []
        if ' E ' in dias_atendimento_str:
            dias_list.extend([d.strip() for d in dias_atendimento_str.split(' E ')])
        else:
            dias_list.extend([d.strip() for d in dias_atendimento_str.split(',')])

        for dia_str in dias_list:
            # Tenta encontrar o dia no mapeamento, usando as 3 primeiras letras
            found_day = None
            for key, val in dias_map.items():
                if dia_str.startswith(key):
                    found_day = val
                    break

            if found_day is not None:
                expanded_scale.append({
                    'Nome do agente': row['Nome do agente'],
                    'Dia da Semana Num': found_day,
                    'Entrada': row['Entrada'],
                    'Saída': row['Saída']
                })
            elif pd.notna(dia_str) and dia_str != '':
                st.warning(f"Dia da semana '{dia_str}' não reconhecido para o agente {row['Nome do agente']}. Ignorando.")

    if not expanded_scale:
        st.warning("Nenhuma escala expandida gerada. Verifique a coluna 'DIAS DE ATENDIMENTO'.")
        return pd.DataFrame()

    df_expanded_scale = pd.DataFrame(expanded_scale)
    return df_expanded_scale

def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    analysis_results = []

    # Garante que as datas sejam datetime.date para comparação
    start_date = start_date.date()
    end_date = end_date.date()

    for agent in selected_agents:
        agent_scale = df_escala[df_escala['Nome do agente'] == agent]
        agent_status = df_real_status[df_real_status['Nome do agente'] == agent]

        total_scheduled_time_minutes = 0
        total_online_in_schedule_minutes = 0

        current_date_metrics = start_date
        while current_date_metrics <= end_date:
            day_of_week_num = current_date_metrics.weekday() # Segunda=0, Domingo=6

            # Escala para o dia atual
            daily_scale = agent_scale[agent_scale['Dia da Semana Num'] == day_of_week_num]

            if not daily_scale.empty:
                for _, scale_row in daily_scale.iterrows():
                    scale_start_time = scale_row['Entrada']
                    scale_end_time = scale_row['Saída']

                    # Cria objetos datetime completos para a escala no dia atual
                    scale_start_dt = datetime.combine(current_date_metrics, scale_start_time)
                    scale_end_dt = datetime.combine(current_date_metrics, scale_end_time)

                    # Se a escala termina no dia seguinte (ex: 22:00 - 06:00), ajusta o fim
                    if scale_end_dt < scale_start_dt:
                        scale_end_dt += timedelta(days=1)

                    total_scheduled_time_minutes += (scale_end_dt - scale_start_dt).total_seconds() / 60

                    # Status online do agente para o dia atual (e potencialmente o próximo se a escala atravessar a meia-noite)
                    # Filtra status que começam no dia atual ou no dia anterior e terminam no dia atual
                    relevant_status = agent_status[
                        ((agent_status['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date_metrics) |
                         (agent_status['Hora de término do estado - Carimbo de data/hora'].dt.date == current_date_metrics) |
                         (agent_status['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date_metrics - timedelta(days=1))) &
                        (agent_status['Estado'] == 'Unified online')
                    ].copy() # Usar .copy() para evitar SettingWithCopyWarning

                    for _, status_row in relevant_status.iterrows():
                        status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                        status_end = status_row['Hora de término do estado - Carimbo de data/hora']

                        # Ajusta status_end se ele for do dia seguinte ao status_start, para não contar duas vezes
                        # ou para garantir que o cálculo seja feito apenas para o dia atual
                        if status_end.date() > status_start.date():
                            status_end_for_current_day = status_start.replace(hour=23, minute=59, second=59, microsecond=999999)
                            # Se o status_start for do dia anterior, ajusta para o início do dia atual
                            if status_start.date() < current_date_metrics:
                                status_start = datetime.combine(current_date_metrics, datetime.min.time())
                            status_end = min(status_end, status_end_for_current_day)

                        # Garante que o status_start não seja anterior ao início do dia atual para o cálculo
                        status_start = max(status_start, datetime.combine(current_date_metrics, datetime.min.time()))

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

# --- Configuração da Aplicação Streamlit ---
st.set_page_config(layout="wide", page_title="Dashboard de Escala e Status de Agentes")

# Inicialização do session_state
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'all_unique_agents' not in st.session_state:
    st.session_state.all_unique_agents = set()
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}

st.title("Dashboard de Escala e Status de Agentes")

tab_upload, tab_groups, tab_visual = st.tabs(["Upload de Dados", "Gerenciar Grupos", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos")

    uploaded_report_file = st.file_uploader("Faça upload do arquivo de relatório de status (Excel)", type=["xlsx"], key="report_uploader")
    if uploaded_report_file is not None:
        try:
            df_report_raw = pd.read_excel(uploaded_report_file, header=0) # Ler com cabeçalho
            st.session_state.df_real_status = process_uploaded_report(df_report_raw)
            if not st.session_state.df_real_status.empty:
                st.success("Relatório de status processado com sucesso!")
                st.dataframe(st.session_state.df_real_status.head())
            else:
                st.error("Erro ao processar o relatório de status ou arquivo vazio.")
        except Exception as e:
            st.error(f"Erro ao processar o relatório de status: {e}")
            st.session_state.df_real_status = pd.DataFrame()

    uploaded_scale_file = st.file_uploader("Faça upload do arquivo de escala (Excel)", type=["xlsx"], key="scale_uploader")
    if uploaded_scale_file is not None:
        try:
            df_scale_raw = pd.read_excel(uploaded_scale_file, header=0) # Ler com cabeçalho
            st.session_state.df_escala = process_uploaded_scale(df_scale_raw)
            if not st.session_state.df_escala.empty:
                st.success("Arquivo de escala processado com sucesso!")
                st.dataframe(st.session_state.df_escala.head())
            else:
                st.error("Erro ao processar o arquivo de escala ou arquivo vazio.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de escala: {e}")
            st.session_state.df_escala = pd.DataFrame()

    # Atualizar a lista de agentes únicos após o upload de ambos os arquivos
    if not st.session_state.df_real_status.empty and 'Nome do agente' in st.session_state.df_real_status.columns:
        st.session_state.all_unique_agents.update(st.session_state.df_real_status['Nome do agente'].unique())
    if not st.session_state.df_escala.empty and 'Nome do agente' in st.session_state.df_escala.columns:
        st.session_state.all_unique_agents.update(st.session_state.df_escala['Nome do agente'].unique())

    if st.session_state.df_real_status.empty and st.session_state.df_escala.empty:
        st.info("Aguardando upload dos arquivos de relatório e escala.")
    elif not st.session_state.df_real_status.empty and st.session_state.df_escala.empty:
        st.warning("Apenas o relatório de status foi carregado. Carregue o arquivo de escala para análise completa.")
    elif st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
        st.warning("Apenas o arquivo de escala foi carregado. Carregue o relatório de status para análise completa.")

with tab_groups:
    st.header("Gerenciar Grupos de Agentes")

    if st.session_state.all_unique_agents:
        st.subheader("Criar Novo Grupo")
        new_group_name = st.text_input("Nome do novo grupo:")

        # Converte o set para lista para o multiselect
        available_agents_for_group = sorted(list(st.session_state.all_unique_agents))
        agents_to_add = st.multiselect(
            "Selecione agentes para adicionar ao grupo:",
            options=available_agents_for_group,
            key="new_group_agents_select"
        )
        if st.button("Criar Grupo") and new_group_name:
            st.session_state.agent_groups[new_group_name] = agents_to_add
            st.success(f"Grupo '{new_group_name}' criado com {len(agents_to_add)} agentes.")
            st.experimental_rerun() # Recarrega para atualizar a lista de grupos

        st.subheader("Grupos Existentes")
        if st.session_state.agent_groups:
            for group_name, agents_in_group in st.session_state.agent_groups.items():
                st.write(f"**{group_name}** ({len(agents_in_group)} agentes)")
                with st.expander(f"Ver agentes em {group_name}"):
                    st.write(", ".join(agents_in_group))
                if st.button(f"Remover Grupo '{group_name}'", key=f"remove_group_{group_name}"):
                    del st.session_state.agent_groups[group_name]
                    st.success(f"Grupo '{group_name}' removido.")
                    st.experimental_rerun()
        else:
            st.info("Nenhum grupo criado ainda.")
    else:
        st.info("Faça o upload dos arquivos na aba 'Upload de Dados' para ver os agentes disponíveis.")

with tab_visual:
    st.header("Visualização da Escala e Métricas")

    if not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
        all_agents_combined = sorted(list(st.session_state.all_unique_agents))

        # Filtros na barra lateral
        st.sidebar.header("Filtros")

        # Seleção de grupo ou agentes individuais
        group_selection = st.sidebar.selectbox(
            "Selecionar por Grupo ou Agentes Individuais:",
            options=["Todos os Agentes", "Selecionar Grupo"] + list(st.session_state.agent_groups.keys()),
            key="group_or_individual_select"
        )

        selected_agents = []
        if group_selection == "Todos os Agentes":
            selected_agents = all_agents_combined
        elif group_selection == "Selecionar Grupo":
            selected_agents = st.sidebar.multiselect(
                "Selecione os agentes:",
                options=all_agents_combined,
                default=all_agents_combined[:min(5, len(all_agents_combined))], # Pega os 5 primeiros como default
                key="individual_agent_select"
            )
        else: # Um grupo foi selecionado
            selected_agents = st.session_state.agent_groups[group_selection]
            st.sidebar.info(f"Agentes do grupo '{group_selection}': {len(selected_agents)}")

        start_date = st.sidebar.date_input("Data de Início", value=st.session_state.df_real_status['Data'].min(), key="start_date_filter")
        end_date = st.sidebar.date_input("Data de Término", value=st.session_state.df_real_status['Data'].max(), key="end_date_filter")

        # Converte as datas para datetime.date para comparação consistente
        start_date_dt = datetime.combine(start_date, datetime.min.time())
        end_date_dt = datetime.combine(end_date, datetime.max.time())

        if selected_agents:
            st.subheader("Gráfico de Escala e Status Real")

            # Filtrar df_real_status e df_escala com base nos agentes e datas selecionadas
            filtered_df_real_status = st.session_state.df_real_status[
                (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
                (st.session_state.df_real_status['Data'] >= start_date_dt.date()) &
                (st.session_state.df_real_status['Data'] <= end_date_dt.date())
            ].copy()

            # Expandir a escala para o intervalo de datas selecionado
            expanded_filtered_scale = []
            current_date = start_date_dt.date()
            while current_date <= end_date_dt.date():
                day_of_week_num = current_date.weekday() # Segunda=0, Domingo=6

                # Filtra a escala para os agentes selecionados e o dia da semana atual
                daily_scale_for_agents = st.session_state.df_escala[
                    (st.session_state.df_escala['Nome do agente'].isin(selected_agents)) &
                    (st.session_state.df_escala['Dia da Semana Num'] == day_of_week_num)
                ]

                for _, scale_row in daily_scale_for_agents.iterrows():
                    scale_start_time = scale_row['Entrada']
                    scale_end_time = scale_row['Saída']

                    scale_start_dt = datetime.combine(current_date, scale_start_time)
                    scale_end_dt = datetime.combine(current_date, scale_end_time)

                    # Se a escala termina no dia seguinte (ex: 22:00 - 06:00), ajusta o fim
                    if scale_end_dt < scale_start_dt:
                        scale_end_dt += timedelta(days=1)

                    expanded_filtered_scale.append({
                        'Nome do agente': scale_row['Nome do agente'],
                        'Data': current_date,
                        'Tipo': 'Escala Planejada',
                        'Início': scale_start_dt,
                        'Fim': scale_end_dt,
                        'Cor': 'blue' # Cor para a escala
                    })
                current_date += timedelta(days=1)

            df_expanded_filtered_scale = pd.DataFrame(expanded_filtered_scale)

            # Preparar dados do status real para o gráfico
            df_chart_real_status = filtered_df_real_status.copy()
            df_chart_real_status['Tipo'] = df_chart_real_status['Estado']
            df_chart_real_status['Início'] = df_chart_real_status['Hora de início do estado - Carimbo de data/hora']
            df_chart_real_status['Fim'] = df_chart_real_status['Hora de término do estado - Carimbo de data/hora']

            # Definir cores para os status reais
            status_colors = {
                'Unified online': 'green',
                'Unified away': 'orange',
                'Unified offline': 'red',
                'Unified transfers only': 'purple',
                'Escala Planejada': 'blue' # Cor para a escala
            }
            df_chart_real_status['Cor'] = df_chart_real_status['Tipo'].map(status_colors).fillna('grey')

            # Combinar dados da escala e do status real para o gráfico
            if not df_expanded_filtered_scale.empty and not df_chart_real_status.empty:
                df_chart_data = pd.concat([
                    df_expanded_filtered_scale[['Nome do agente', 'Data', 'Tipo', 'Início', 'Fim', 'Cor']],
                    df_chart_real_status[['Nome do agente', 'Data', 'Tipo', 'Início', 'Fim', 'Cor']]
                ], ignore_index=True)
            elif not df_expanded_filtered_scale.empty:
                df_chart_data = df_expanded_filtered_scale[['Nome do agente', 'Data', 'Tipo', 'Início', 'Fim', 'Cor']]
            elif not df_chart_real_status.empty:
                df_chart_data = df_chart_real_status[['Nome do agente', 'Data', 'Tipo', 'Início', 'Fim', 'Cor']]
            else:
                df_chart_data = pd.DataFrame()

            if not df_chart_data.empty:
                # Ordenar para melhor visualização
                df_chart_data['Agente_Data_Tipo'] = df_chart_data['Nome do agente'] + ' - ' + df_chart_data['Data'].dt.strftime('%Y-%m-%d') + ' (' + df_chart_data['Tipo'] + ')'
                df_chart_data = df_chart_data.sort_values(by=['Data', 'Nome do agente', 'Início'])

                # Ajustar a altura do gráfico dinamicamente
                unique_rows_count = df_chart_data['Agente_Data_Tipo'].nunique()
                chart_height = max(400, unique_rows_count * 25) # 25 pixels por linha, mínimo de 400

                fig = px.timeline(
                    df_chart_data,
                    x_start="Início",
                    x_end="Fim",
                    y="Agente_Data_Tipo", # Usar a combinação para ter escala e status na mesma linha
                    color="Tipo",
                    color_discrete_map=status_colors,
                    title="Comparativo de Escala Planejada vs. Status Real",
                    hover_name="Nome do agente",
                    hover_data={"Tipo": True, "Início": True, "Fim": True, "Data": "|%Y-%m-%d": True},
                    height=chart_height
                )

                fig.update_yaxes(
                    categoryorder="array",
                    categoryarray=df_chart_data['Agente_Data_Tipo'].unique(),
                    title_text="Agente - Data (Tipo)"
                )
                fig.update_xaxes(
                    title_text="Horário",
                    showgrid=True, gridwidth=1, gridcolor='LightGrey',
                    tickformat="%H:%M" # Formato de hora
                )
                fig.update_yaxes(
                    showgrid=True, gridwidth=1, gridcolor='LightGrey'
                )
                fig.update_layout(
                    xaxis=dict(
                        rangeslider=dict(visible=True),
                        type="date"
                    ),
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
