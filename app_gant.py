import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, time, date
import numpy as np
import unicodedata

# --- Funções de Normalização ---
def normalize_agent_name(name):
    if pd.isna(name):
        return name
    name = str(name).strip().upper()
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    return name

# Nova função para normalizar nomes de colunas
def normalize_column_name(col_name):
    if pd.isna(col_name):
        return col_name
    col_name = str(col_name).strip().upper()
    col_name = unicodedata.normalize('NFKD', col_name).encode('ascii', 'ignore').decode('utf-8')
    # Remover caracteres especiais que não sejam letras ou números, e substituir espaços por underscore
    col_name = ''.join(c for c in col_name if c.isalnum() or c == ' ')
    col_name = col_name.replace(' ', '_')
    return col_name

# --- Funções de Processamento de Dados ---
def process_uploaded_report(df_report_raw):
    df = df_report_raw.copy()

    expected_columns_report = {
        'Nome do agente': 'Nome do agente',
        'Hora de início do estado - Dia do mês': 'Dia',
        'Hora de início do estado - Carimbo de data/hora': 'Hora de início do estado - Carimbo de data/hora',
        'Hora de término do estado - Carimbo de data/hora': 'Hora de término do estado - Carimbo de data/hora',
        'Estado': 'Estado',
        'Tempo do agente no estado / Minutos': 'Tempo do agente no estado / Minutos'
    }

    # Normalizar os nomes das colunas do DataFrame antes de tentar renomear
    df.columns = [normalize_column_name(col) for col in df.columns]

    # Criar um mapeamento reverso com os nomes normalizados esperados
    normalized_expected_columns_report = {
        normalize_column_name(original): new_name
        for original, new_name in expected_columns_report.items()
    }

    # Renomear colunas que existem no DataFrame e no mapeamento
    rename_map = {
        col_in_df: normalized_expected_columns_report[col_in_df]
        for col_in_df in df.columns if col_in_df in normalized_expected_columns_report
    }
    df = df.rename(columns=rename_map)

    if 'Nome do agente' not in df.columns:
        st.error("Coluna 'Nome do agente' não encontrada no arquivo de status real após renomear. Verifique o cabeçalho do arquivo.")
        return pd.DataFrame()

    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
    df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

    # Preencher NaT em 'Hora de término do estado - Carimbo de data/hora' com o final do dia do início
    df['Hora de término do estado - Carimbo de data/hora'] = df.apply(
        lambda row: row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
        if pd.isna(row['Hora de término do estado - Carimbo de data/hora']) and pd.notna(row['Hora de início do estado - Carimbo de data/hora'])
        else row['Hora de término do estado - Carimbo de data/hora'],
        axis=1
    )

    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'], inplace=True)

    # FORÇAR O TIPO DA COLUNA PARA DATETIME64[NS] AQUI
    df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
    df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'], errors='coerce')


    # Ajuste na lógica de cálculo de métricas: se status_end for no dia seguinte ao status_start,
    # ajustar para o final do dia status_start para cálculo diário.
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
        dt_val = pd.to_datetime(val, errors='coerce')
        if pd.notna(dt_val):
            return dt_val.time()
        return datetime.strptime(str(val).strip(), '%H:%M:%S').time()
    except (ValueError, TypeError):
        try:
            return datetime.strptime(str(val).strip(), '%H:%M').time()
        except (ValueError, TypeError):
            return None

def process_uploaded_scale(df_scale_raw, start_effective_date, end_effective_date=None):
    df = df_scale_raw.copy()

    # Mapeamento de colunas esperadas para os nomes internos
    expected_columns_scale = {
        'NOME': 'Nome do agente',
        'DIAS DE ATENDIMENTO': 'Dias de Atendimento',
        'ENTRADA': 'Entrada',
        'SAIDA': 'Saída', # Corrigido para SAIDA sem acento, se for o caso no arquivo
        'CARGA': 'Carga'
    }

    # 1. Normalizar os nomes das colunas do DataFrame de entrada
    df.columns = [normalize_column_name(col) for col in df.columns]

    # 2. Criar um mapeamento reverso com os nomes normalizados esperados
    # Isso permite que o rename funcione mesmo se o arquivo tiver "NOME DO AGENTE" ou "NOME_DO_AGENTE"
    normalized_expected_columns_map = {
        normalize_column_name(original_name): internal_name
        for original_name, internal_name in expected_columns_scale.items()
    }

    # 3. Renomear as colunas do DataFrame usando o mapeamento normalizado
    # Apenas renomeia se o nome normalizado da coluna existir no mapeamento
    rename_dict = {
        col_in_df: normalized_expected_columns_map[col_in_df]
        for col_in_df in df.columns if col_in_df in normalized_expected_columns_map
    }
    df = df.rename(columns=rename_dict)

    required_cols = ['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída']
    if not all(col in df.columns for col in required_cols):
        missing_cols = [col for col in required_cols if col not in df.columns]
        st.error(f"Uma ou mais colunas essenciais ({', '.join(missing_cols)}) não foram encontradas no arquivo de escala após renomear. Verifique os cabeçalhos do arquivo e o mapeamento.")
        return pd.DataFrame()

    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)
    df.dropna(subset=['Nome do agente'], inplace=True)
    if df.empty:
        st.warning("Nenhum agente válido encontrado no arquivo de escala após a limpeza.")
        return pd.DataFrame()

    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)
    df.dropna(subset=['Entrada', 'Saída'], inplace=True)
    if df.empty:
        st.warning("Nenhuma escala válida encontrada após o processamento dos horários. Verifique as colunas 'ENTRADA' e 'SAÍDA'.")
        return pd.DataFrame()

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
        carga = row.get('Carga')

        dias_str_cleaned = dias_str.replace(' E ', ',').replace(' e ', ',')
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
                    'Carga': carga,
                    'Data Início Vigência': pd.Timestamp(start_effective_date), # Convert to Timestamp
                    'Data Fim Vigência': pd.Timestamp(end_effective_date) if end_effective_date else pd.NaT # Convert to Timestamp or NaT
                })

    if not expanded_scale_data:
        st.warning("Nenhuma escala expandida gerada. Verifique os dias de atendimento e o formato.")
        return pd.DataFrame()

    df_expanded = pd.DataFrame(expanded_scale_data)
    return df_expanded

def get_effective_scale_for_day(agent_name, current_date, df_escala_history):
    # current_date é um objeto date, converter para Timestamp para comparação consistente
    current_timestamp = pd.Timestamp(current_date)

    if df_escala_history.empty:
        return pd.DataFrame()

    # Filtrar escalas para o agente e dia da semana
    filtered_by_agent_day = df_escala_history[
        (df_escala_history['Nome do agente'] == agent_name) &
        (df_escala_history['Dia da Semana Num'] == current_date.weekday())
    ].copy()

    if filtered_by_agent_day.empty:
        return pd.DataFrame()

    # Filtrar por datas de vigência
    # Usar pd.Timestamp para comparar com as colunas do DataFrame
    valid_scales = filtered_by_agent_day[
        (filtered_by_agent_day['Data Início Vigência'] <= current_timestamp) &
        (
            filtered_by_agent_day['Data Fim Vigência'].isna() | # Vigência indefinida
            (filtered_by_agent_day['Data Fim Vigência'] >= current_timestamp) # OU a data de fim é maior ou igual à current_date
        )
    ]

    if valid_scales.empty:
        return pd.DataFrame()

    # Se houver múltiplas escalas válidas, pegar a mais recente (maior Data Início Vigência)
    # Isso resolve conflitos se houver sobreposição de vigências
    latest_scale = valid_scales.loc[valid_scales['Data Início Vigência'].idxmax()]

    # Retornar um DataFrame com a escala mais recente (pode ter múltiplas entradas para o mesmo dia se houver turnos)
    # Para garantir que retorne um DataFrame, mesmo que seja uma única linha
    return valid_scales[valid_scales['Data Início Vigência'] == latest_scale['Data Início Vigência']]


def calculate_metrics(df_real_status, df_escala_history, selected_agents, start_date, end_date):
    metrics_data = []
    date_range = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]

    for agent in selected_agents:
        for current_date in date_range:
            # Obter a escala efetiva para o agente e o dia
            daily_escala = get_effective_scale_for_day(agent, current_date, df_escala_history)

            total_scheduled_time_minutes = 0
            if not daily_escala.empty:
                for _, scale_row in daily_escala.iterrows():
                    start_time = scale_row['Entrada']
                    end_time = scale_row['Saída']

                    start_dt = datetime.combine(current_date, start_time)
                    end_dt = datetime.combine(current_date, end_time)

                    if end_dt < start_dt: # Escala que vira o dia
                        end_dt += timedelta(days=1)

                    total_scheduled_time_minutes += (end_dt - start_dt).total_seconds() / 60

            # Filtrar status real para o agente e o dia
            df_agent_day_status = df_real_status[
                (df_real_status['Nome do agente'] == agent) &
                (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date)
            ].copy()

            total_online_time_minutes = 0
            if not df_agent_day_status.empty:
                # Considerar apenas estados "online" ou produtivos
                online_statuses = ['Unified online', 'Unified transfers only', 'Unified busy', 'Unified wrap up'] # Ajuste conforme seus estados produtivos
                df_online_status = df_agent_day_status[df_agent_day_status['Estado'].isin(online_statuses)]

                for _, status_row in df_online_status.iterrows():
                    status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                    status_end = status_row['Hora de término do estado - Carimbo de data/hora']

                    # Interseção com o período de escala (se houver)
                    # Isso garante que o tempo online seja contado apenas dentro da escala planejada
                    if not daily_escala.empty:
                        for _, scale_row in daily_escala.iterrows():
                            scale_start_time = scale_row['Entrada']
                            scale_end_time = scale_row['Saída']
                            scale_start_dt = datetime.combine(current_date, scale_start_time)
                            scale_end_dt = datetime.combine(current_date, scale_end_time)
                            if scale_end_dt < scale_start_dt:
                                scale_end_dt += timedelta(days=1)

                            # Calcular a interseção
                            overlap_start = max(status_start, scale_start_dt)
                            overlap_end = min(status_end, scale_end_dt)

                            if overlap_end > overlap_start:
                                total_online_time_minutes += (overlap_end - overlap_start).total_seconds() / 60
                    else: # Se não há escala, apenas soma o tempo online
                        total_online_time_minutes += (status_end - status_start).total_seconds() / 60


            availability_percentage = (total_online_time_minutes / total_scheduled_time_minutes * 100) if total_scheduled_time_minutes > 0 else 0

            metrics_data.append({
                'Agente': agent,
                'Data': current_date.strftime('%Y-%m-%d'),
                'Tempo Escala (min)': round(total_scheduled_time_minutes, 2),
                'Tempo Online (min)': round(total_online_time_minutes, 2),
                'Disponibilidade (%)': round(availability_percentage, 2)
            })

    return pd.DataFrame(metrics_data)

# --- Configuração do Streamlit ---
st.set_page_config(layout="wide", page_title="Análise de Produtividade de Agentes")

st.title("📊 Análise de Produtividade de Agentes")

# Inicialização do session_state
if 'df_real_status_history' not in st.session_state:
    st.session_state.df_real_status_history = pd.DataFrame(columns=[
        'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
        'Hora de término do estado - Carimbo de data/hora', 'Estado',
        'Tempo do agente no estado / Minutos'
    ]).astype({
        'Hora de início do estado - Carimbo de data/hora': 'datetime64[ns]',
        'Hora de término do estado - Carimbo de data/hora': 'datetime64[ns]'
    })

if 'df_escala_history' not in st.session_state:
    st.session_state.df_escala_history = pd.DataFrame(columns=[
        'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Carga',
        'Data Início Vigência', 'Data Fim Vigência'
    ]).astype({
        'Data Início Vigência': 'datetime64[ns]',
        'Data Fim Vigência': 'datetime64[ns]'
    })

if 'all_unique_agents' not in st.session_state:
    st.session_state.all_unique_agents = []

if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}

# Abas
tab_upload, tab_manage_scales, tab_manage_groups, tab_visualization = st.tabs([
    "Upload de Dados", "Gerenciar Escalas", "Gerenciar Grupos", "Visualização e Métricas"
])

with tab_upload:
    st.header("Upload de Arquivos")

    st.subheader("Upload de Relatório de Status Real")
    uploaded_report_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) para o Status Real", type=["xlsx"], key="report_uploader")
    if uploaded_report_file:
        try:
            df_report_raw = pd.read_excel(uploaded_report_file)
            df_processed_report = process_uploaded_report(df_report_raw)

            if not df_processed_report.empty:
                # Remover duplicatas antes de adicionar ao histórico
                # Considera 'Nome do agente', 'Hora de início do estado', 'Estado' como chaves para duplicidade
                df_processed_report['temp_key'] = df_processed_report['Nome do agente'] + \
                                                  df_processed_report['Hora de início do estado - Carimbo de data/hora'].dt.strftime('%Y%m%d%H%M%S') + \
                                                  df_processed_report['Estado']

                existing_keys = set(st.session_state.df_real_status_history['Nome do agente'] + \
                                    st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.strftime('%Y%m%d%H%M%S') + \
                                    st.session_state.df_real_status_history['Estado'])

                new_records = df_processed_report[~df_processed_report['temp_key'].isin(existing_keys)].drop(columns=['temp_key'])

                if not new_records.empty:
                    st.session_state.df_real_status_history = pd.concat([st.session_state.df_real_status_history, new_records], ignore_index=True)
                    st.success(f"Relatório de status real carregado e {len(new_records)} novos registros adicionados ao histórico.")
                else:
                    st.info("Nenhum novo registro encontrado no relatório de status real para adicionar ao histórico.")
            else:
                st.warning("O arquivo de relatório de status real processado está vazio ou houve um erro.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de relatório de status real. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Upload de Arquivo de Escala")
    uploaded_scale_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) para a Escala", type=["xlsx"], key="scale_uploader")
    if uploaded_scale_file:
        st.info("Ao carregar um novo arquivo de escala, ele substituirá as escalas existentes para os agentes e dias da semana correspondentes a partir da 'Data de Início de Vigência' informada.")
        new_scale_start_date = st.date_input("Data de Início de Vigência para esta escala", value=datetime.now().date(), key="new_scale_start_date_upload")
        new_scale_end_date = st.date_input("Data de Fim de Vigência para esta escala (opcional)", value=None, key="new_scale_end_date_upload")

        if st.button("Processar e Adicionar Escala", key="process_scale_button"):
            try:
                df_scale_raw = pd.read_excel(uploaded_scale_file)
                df_processed_scale = process_uploaded_scale(df_scale_raw, new_scale_start_date, new_scale_end_date)

                if not df_processed_scale.empty:
                    # Lógica para atualizar o histórico de escalas
                    # Para cada agente/dia da semana na nova escala, ajustar a Data Fim Vigência das escalas antigas
                    for _, new_row in df_processed_scale.iterrows():
                        agent = new_row['Nome do agente']
                        day_num = new_row['Dia da Semana Num']
                        new_start_ts = new_row['Data Início Vigência']

                        # Encontrar escalas antigas para o mesmo agente/dia que se sobrepõem ou são substituídas
                        # Usar .copy() para evitar SettingWithCopyWarning
                        overlapping_old_scales_idx = st.session_state.df_escala_history[
                            (st.session_state.df_escala_history['Nome do agente'] == agent) &
                            (st.session_state.df_escala_history['Dia da Semana Num'] == day_num) &
                            (st.session_state.df_escala_history['Data Fim Vigência'].isna() | (st.session_state.df_escala_history['Data Fim Vigência'] >= new_start_ts)) &
                            (st.session_state.df_escala_history['Data Início Vigência'] < new_start_ts)
                        ].index

                        if not overlapping_old_scales_idx.empty:
                            # Ajustar a Data Fim Vigência das escalas antigas para o dia anterior à nova escala
                            st.session_state.df_escala_history.loc[overlapping_old_scales_idx, 'Data Fim Vigência'] = new_start_ts - timedelta(days=1)

                    # Adicionar a nova escala ao histórico
                    st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, df_processed_scale], ignore_index=True)
                    st.session_state.df_escala_history.sort_values(by=['Nome do agente', 'Dia da Semana Num', 'Data Início Vigência'], inplace=True)
                    st.session_state.df_escala_history.reset_index(drop=True, inplace=True)

                    st.success(f"Arquivo de escala carregado e {len(df_processed_scale)} registros de escala adicionados/atualizados no histórico.")
                    # Atualizar a lista de agentes únicos
                    st.session_state.all_unique_agents = sorted(st.session_state.df_escala_history['Nome do agente'].unique())
                else:
                    st.warning("O arquivo de escala processado está vazio ou houve um erro.")
            except Exception as e:
                st.error(f"Erro ao processar o arquivo de escala. Verifique o formato do arquivo. Erro: {e}")

    if st.button("Limpar Histórico de Dados", key="clear_history_button"):
        st.session_state.df_real_status_history = pd.DataFrame(columns=[
            'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado',
            'Tempo do agente no estado / Minutos'
        ]).astype({
            'Hora de início do estado - Carimbo de data/hora': 'datetime64[ns]',
            'Hora de término do estado - Carimbo de data/hora': 'datetime64[ns]'
        })
        st.session_state.df_escala_history = pd.DataFrame(columns=[
            'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Carga',
            'Data Início Vigência', 'Data Fim Vigência'
        ]).astype({
            'Data Início Vigência': 'datetime64[ns]',
            'Data Fim Vigência': 'datetime64[ns]'
        })
        st.session_state.all_unique_agents = []
        st.session_state.agent_groups = {}
        st.success("Histórico de dados e grupos limpos.")

with tab_manage_scales:
    st.header("Gerenciar Escalas Manuais")

    if st.session_state.all_unique_agents:
        agent_to_manage = st.selectbox("Selecione o agente para gerenciar a escala:", options=[""] + st.session_state.all_unique_agents, key="manage_agent_select")

        if agent_to_manage:
            st.subheader(f"Escalas Atuais para {agent_to_manage}")
            df_agent_scales = st.session_state.df_escala_history[st.session_state.df_escala_history['Nome do agente'] == agent_to_manage].copy()
            if not df_agent_scales.empty:
                st.dataframe(df_agent_scales.sort_values(by=['Dia da Semana Num', 'Data Início Vigência']), use_container_width=True)
            else:
                st.info("Nenhuma escala definida para este agente.")

            st.subheader(f"Adicionar/Atualizar Escala para {agent_to_manage}")
            col1, col2 = st.columns(2)
            with col1:
                day_of_week_str = st.selectbox("Dia da Semana:", options=["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"], key="new_scale_day")
                day_of_week_num = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"].index(day_of_week_str)
                new_entrada = st.time_input("Hora de Entrada:", value=time(9, 0), key="new_scale_entrada")
            with col2:
                new_saida = st.time_input("Hora de Saída:", value=time(18, 0), key="new_scale_saida")
                new_carga = st.number_input("Carga Horária (minutos):", min_value=0, value=480, key="new_scale_carga")

            new_start_effective_date = st.date_input("Data de Início de Vigência:", value=datetime.now().date(), key="new_scale_start_effective_date")
            new_end_effective_date = st.date_input("Data de Fim de Vigência (opcional):", value=None, key="new_scale_end_effective_date")

            if st.button(f"Salvar Escala para {agent_to_manage}", key="save_manual_scale"):
                # Converter datas para Timestamp para consistência
                new_start_ts = pd.Timestamp(new_start_effective_date)
                new_end_ts = pd.Timestamp(new_end_effective_date) if new_end_effective_date else pd.NaT

                # 1. Ajustar Data Fim Vigência de escalas antigas que se sobrepõem
                # Usar .copy() para evitar SettingWithCopyWarning
                overlapping_old_scales_idx = st.session_state.df_escala_history[
                    (st.session_state.df_escala_history['Nome do agente'] == agent_to_manage) &
                    (st.session_state.df_escala_history['Dia da Semana Num'] == day_of_week_num) &
                    (st.session_state.df_escala_history['Data Fim Vigência'].isna() | (st.session_state.df_escala_history['Data Fim Vigência'] >= new_start_ts)) &
                    (st.session_state.df_escala_history['Data Início Vigência'] < new_start_ts)
                ].index

                if not overlapping_old_scales_idx.empty:
                    st.session_state.df_escala_history.loc[overlapping_old_scales_idx, 'Data Fim Vigência'] = new_start_ts - timedelta(days=1)

                # 2. Adicionar a nova escala
                new_scale_entry = pd.DataFrame([{
                    'Nome do agente': agent_to_manage,
                    'Dia da Semana Num': day_of_week_num,
                    'Entrada': new_entrada,
                    'Saída': new_saida,
                    'Carga': new_carga,
                    'Data Início Vigência': new_start_ts,
                    'Data Fim Vigência': new_end_ts
                }])
                st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, new_scale_entry], ignore_index=True)
                st.session_state.df_escala_history.sort_values(by=['Nome do agente', 'Dia da Semana Num', 'Data Início Vigência'], inplace=True)
                st.session_state.df_escala_history.reset_index(drop=True, inplace=True)
                st.success(f"Escala para {agent_to_manage} no(a) {day_of_week_str} salva com sucesso!")
                st.rerun() # Recarregar para mostrar a escala atualizada
    else:
        st.info("Nenhum agente disponível para gerenciar escalas. Faça o upload de um arquivo de escala primeiro.")

with tab_manage_groups:
    st.header("Gerenciar Grupos de Agentes")

    group_name = st.text_input("Nome do Novo Grupo:")

    all_available_agents_for_groups = []
    if not st.session_state.df_escala_history.empty:
        all_available_agents_for_groups = sorted(st.session_state.df_escala_history['Nome do agente'].unique())
    elif not st.session_state.df_real_status_history.empty:
        all_available_agents_for_groups = sorted(st.session_state.df_real_status_history['Nome do agente'].unique())

    selected_agents_for_group = st.multiselect(
        "Selecione os agentes para este grupo:",
        options=all_available_agents_for_groups,
        key="agents_for_group_multiselect"
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
            st.write(f"**{name}**: {', '.join(agents)}")
            if st.button(f"Excluir Grupo '{name}'", key=f"delete_group_{name}"):
                del st.session_state.agent_groups[name]
                st.success(f"Grupo '{name}' excluído.")
                st.rerun()
    else:
        st.info("Nenhum grupo criado ainda.")

with tab_visualization:
    st.header("Visualização da Linha do Tempo e Métricas")

    all_available_agents = []
    if not st.session_state.df_escala_history.empty:
        all_available_agents = sorted(st.session_state.df_escala_history['Nome do agente'].unique())
    elif not st.session_state.df_real_status_history.empty:
        all_available_agents = sorted(st.session_state.df_real_status_history['Nome do agente'].unique())

    if not all_available_agents:
        st.info("Por favor, faça o upload de dados de escala ou status real na aba 'Upload de Dados' primeiro para ver os agentes.")
        selected_agents = []
    else:
        filter_by_group = st.checkbox("Filtrar por Grupo?", key="filter_by_group_checkbox")
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
                    selected_agents = [] # Nenhum grupo selecionado
            else:
                st.warning("Nenhum grupo disponível. Crie grupos na aba 'Gerenciar Grupos'.")
                selected_agents = []
        else:
            selected_agents = st.multiselect(
                "Selecione os agentes para visualizar:",
                options=all_available_agents,
                default=all_available_agents if len(all_available_agents) <= 5 else [],
                key="agent_multiselect"
            )

    # Definir min_date_data e max_date_data com base nos dados disponíveis
    min_date_data = datetime.now().date()
    max_date_data = datetime.now().date()

    if not st.session_state.df_real_status_history.empty:
        # Garantir que a coluna é datetime64[ns] antes de usar .dt
        if pd.api.types.is_datetime64_any_dtype(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora']):
            min_date_data = min(min_date_data, st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].min().date())
            max_date_data = max(max_date_data, st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].max().date())
        else:
            st.warning("Coluna 'Hora de início do estado - Carimbo de data/hora' não é do tipo datetime. Verifique o arquivo de status real.")

    if not st.session_state.df_escala_history.empty and not st.session_state.df_escala_history['Data Início Vigência'].empty:
        # Garantir que a coluna é datetime64[ns] antes de usar .dt
        if pd.api.types.is_datetime64_any_dtype(st.session_state.df_escala_history['Data Início Vigência']):
            min_date_data = min(min_date_data, st.session_state.df_escala_history['Data Início Vigência'].min().date())
        else:
            st.warning("Coluna 'Data Início Vigência' não é do tipo datetime. Verifique o arquivo de escala.")


    start_date = st.date_input("Data de Início", value=min_date_data, min_value=min_date_data, max_value=max_date_data)
    end_date = st.date_input("Data de Fim", value=max_date_data, min_value=min_date_data, max_value=max_date_data)

    if selected_agents:
        df_chart_data = pd.DataFrame()

        # Adicionar dados de status real
        if not st.session_state.df_real_status_history.empty and pd.api.types.is_datetime64_any_dtype(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora']):
            df_real_status_filtered_chart = st.session_state.df_real_status_history[
                (st.session_state.df_real_status_history['Nome do agente'].isin(selected_agents)) &
                (st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
                (st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
            ].copy()
            if not df_real_status_filtered_chart.empty:
                df_real_status_filtered_chart['Start'] = df_real_status_filtered_chart['Hora de início do estado - Carimbo de data/hora']
                df_real_status_filtered_chart['Finish'] = df_real_status_filtered_chart['Hora de término do estado - Carimbo de data/hora']
                df_real_status_filtered_chart['Tipo'] = df_real_status_filtered_chart['Estado']
                df_real_status_filtered_chart['Data'] = df_real_status_filtered_chart['Start'].dt.date
                df_real_status_filtered_chart['Y_Axis_Label'] = df_real_status_filtered_chart.apply(
                    lambda row: f"{row['Nome do agente']} - {row['Data'].strftime('%Y-%m-%d')} - Status Real",
                    axis=1
                )
                df_chart_data = pd.concat([df_chart_data, df_real_status_filtered_chart[['Y_Axis_Label', 'Start', 'Finish', 'Tipo', 'Nome do agente', 'Data']]])

        # Adicionar dados de escala (dinamicamente com base na data de vigência)
        if not st.session_state.df_escala_history.empty and pd.api.types.is_datetime64_any_dtype(st.session_state.df_escala_history['Data Início Vigência']):
            expanded_scale_for_chart = []
            for agent in selected_agents:
                current_date_chart = start_date
                while current_date_chart <= end_date:
                    daily_escala = get_effective_scale_for_day(agent, current_date_chart, st.session_state.df_escala_history)

                    for _, scale_row in daily_escala.iterrows():
                        scale_start_time = scale_row['Entrada']
                        scale_end_time = scale_row['Saída']

                        scale_start_dt = datetime.combine(current_date_chart, scale_start_time)
                        scale_end_dt = datetime.combine(current_date_chart, scale_end_time)

                        if scale_end_dt < scale_start_dt:
                            scale_end_dt += timedelta(days=1)

                        day_end_limit = datetime.combine(current_date_chart, time.max)
                        effective_scale_end_for_chart = min(scale_end_dt, day_end_limit)

                        if effective_scale_end_for_chart > scale_start_dt:
                            expanded_scale_for_chart.append({
                                'Nome do agente': agent,
                                'Start': scale_start_dt,
                                'Finish': effective_scale_end_for_chart,
                                'Tipo': 'Escala Planejada',
                                'Data': current_date_chart,
                                'Y_Axis_Label': f"{agent} - {current_date_chart.strftime('%Y-%m-%d')} - Escala Planejada"
                            })
                    current_date_chart += timedelta(days=1)

            if expanded_scale_for_chart:
                df_expanded_scale_chart = pd.DataFrame(expanded_scale_for_chart)
                df_chart_data = pd.concat([df_chart_data, df_expanded_scale_chart[['Y_Axis_Label', 'Start', 'Finish', 'Tipo', 'Nome do agente', 'Data']]])

        if not df_chart_data.empty:
            y_order_base = sorted(df_chart_data['Nome do agente'].unique())
            y_order_final = []
            for agent in y_order_base:
                dates_for_agent = sorted(df_chart_data[df_chart_data['Nome do agente'] == agent]['Data'].unique())
                for date_obj in dates_for_agent:
                    date_str = date_obj.strftime('%Y-%m-%d')
                    if f"{agent} - {date_str} - Escala Planejada" in df_chart_data['Y_Axis_Label'].unique():
                        y_order_final.append(f"{agent} - {date_str} - Escala Planejada")
                    if f"{agent} - {date_str} - Status Real" in df_chart_data['Y_Axis_Label'].unique():
                        y_order_final.append(f"{agent} - {date_str} - Status Real")

            y_order_final = list(dict.fromkeys(y_order_final))

            num_unique_rows = len(df_chart_data['Y_Axis_Label'].unique())
            chart_height = max(400, num_unique_rows * 30)

            fig = px.timeline(
                df_chart_data,
                x_start="Start",
                x_end="Finish",
                y="Y_Axis_Label",
                color="Tipo",
                color_discrete_map={
                    'Escala Planejada': 'lightgray',
                    'Unified online': 'green',
                    'Unified away': 'orange',
                    'Unified offline': 'red',
                    'Unified transfers only': 'purple',
                    'Unified busy': 'blue',
                    'Unified not available': 'darkred',
                    'Unified wrap up': 'brown'
                },
                title="Linha do Tempo de Status e Escala dos Agentes",
                height=chart_height
            )

            fig.update_yaxes(categoryorder='array', categoryarray=y_order_final)
            fig.update_xaxes(
                title_text="Hora do Dia",
                tickformat="%H:%M",
                showgrid=True,
                gridcolor='lightgray',
                griddash='dot'
            )
            fig.update_yaxes(
                title_text="Agente - Data (Tipo de Registro)",
                showgrid=True,
                gridcolor='lightgray',
                griddash='dot'
            )
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Métricas de Disponibilidade na Escala")
            if not st.session_state.df_real_status_history.empty and not st.session_state.df_escala_history.empty:
                df_metrics = calculate_metrics(
                    st.session_state.df_real_status_history,
                    st.session_state.df_escala_history,
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
