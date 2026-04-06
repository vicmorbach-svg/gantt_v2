import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, time, date
import numpy as np
import unicodedata
import os # Importar o módulo os para lidar com caminhos de arquivo

# --- Constantes para persistência de dados ---
HISTORY_DIR = "data_history" # Diretório para armazenar os arquivos de histórico
REAL_STATUS_HISTORY_FILE = os.path.join(HISTORY_DIR, "real_status_history.csv")
ESCALA_HISTORY_FILE = os.path.join(HISTORY_DIR, "escala_history.csv")

# Garantir que o diretório de histórico exista
os.makedirs(HISTORY_DIR, exist_ok=True)

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

# --- Função para mapear dias da semana (movida para o escopo global) ---
def get_dias_map():
    return {
        'DOM': 6, 'DOMINGO': 6,
        'SEG': 0, 'SEGUNDA': 0,
        'TER': 1, 'TERCA': 1, 'TERÇA': 1,
        'QUA': 2, 'QUARTA': 2,
        'QUI': 3, 'QUINTA': 3,
        'SEX': 4, 'SEXTA': 4,
        'SAB': 5, 'SABADO': 5, 'SÁBADO': 5
    }

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

    # Converter colunas de data/hora e forçar o tipo
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

    # Forçar o tipo da coluna para datetime64[ns] novamente após dropna, para garantir consistência
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
    }

    # Normalizar os nomes das colunas do DataFrame antes de tentar renomear
    df.columns = [normalize_column_name(col) for col in df.columns]

    # Criar um mapeamento reverso com os nomes normalizados esperados
    normalized_expected_columns_scale = {
        normalize_column_name(original): new_name
        for original, new_name in expected_columns_scale.items()
    }

    # Renomear colunas que existem no DataFrame e no mapeamento
    rename_map = {
        col_in_df: normalized_expected_columns_scale[col_in_df]
        for col_in_df in df.columns if col_in_df in normalized_expected_columns_scale
    }
    df = df.rename(columns=rename_map)

    required_cols = ['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.error(f"Colunas obrigatórias não encontradas no arquivo de escala após renomear: {', '.join(missing_cols)}. Verifique o cabeçalho do arquivo.")
        return pd.DataFrame()

    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Expande os dias de atendimento para linhas separadas
    expanded_data = []
    dias_map = get_dias_map()
    for index, row in df.iterrows():
        agent_name = row['Nome do agente']
        dias_atendimento_str = str(row['Dias de Atendimento']).upper().replace(' ', '')

        # Tratar múltiplos dias separados por vírgula ou barra
        if ',' in dias_atendimento_str:
            dias_list = dias_atendimento_str.split(',')
        elif '/' in dias_atendimento_str:
            dias_list = dias_atendimento_str.split('/')
        else:
            dias_list = [dias_atendimento_str]

        for dia_str in dias_list:
            dia_num = dias_map.get(dia_str.strip(), None)
            if dia_num is not None:
                expanded_data.append({
                    'Nome do agente': agent_name,
                    'Dia da Semana Num': dia_num,
                    'Entrada': row['Entrada'],
                    'Saída': row['Saída'],
                    'Data Início Vigência': start_effective_date,
                    'Data Fim Vigência': end_effective_date if end_effective_date else pd.NaT # Usar pd.NaT para vigência indefinida
                })

    df_expanded = pd.DataFrame(expanded_data)

    # Converter Entrada e Saída para objetos time
    df_expanded['Entrada'] = df_expanded['Entrada'].apply(to_time)
    df_expanded['Saída'] = df_expanded['Saída'].apply(to_time)

    # Remover linhas com Entrada/Saída inválidas
    df_expanded.dropna(subset=['Entrada', 'Saída'], inplace=True)

    # Converter colunas de vigência para datetime64[ns] para consistência
    df_expanded['Data Início Vigência'] = pd.to_datetime(df_expanded['Data Início Vigência'])
    df_expanded['Data Fim Vigência'] = pd.to_datetime(df_expanded['Data Fim Vigência'])

    return df_expanded

def get_effective_scale_for_day(agent_name, current_date, df_escala_history):
    if df_escala_history.empty:
        return pd.DataFrame()

    # Converter current_date para pd.Timestamp para comparação consistente
    current_timestamp = pd.Timestamp(current_date)

    # Filtrar escalas para o agente e dia da semana
    filtered_by_agent_day = df_escala_history[
        (df_escala_history['Nome do agente'] == agent_name) &
        (df_escala_history['Dia da Semana Num'] == current_date.weekday())
    ].copy() # Usar .copy() para evitar SettingWithCopyWarning

    if filtered_by_agent_day.empty:
        return pd.DataFrame()

    # Filtrar por vigência: current_date deve estar entre Data Início Vigência e Data Fim Vigência
    # Data Fim Vigência pode ser NaT (vigência indefinida)
    effective_scales = filtered_by_agent_day[
        (filtered_by_agent_day['Data Início Vigência'] <= current_timestamp) &
        (
            (filtered_by_agent_day['Data Fim Vigência'].isna()) | # Vigência indefinida
            (filtered_by_agent_day['Data Fim Vigência'] >= current_timestamp) # Vigência definida e ainda válida
        )
    ]

    if effective_scales.empty:
        return pd.DataFrame()

    # Se houver múltiplas escalas válidas, pegar a mais recente (com Data Início Vigência mais alta)
    # Isso é importante se uma escala foi alterada para o mesmo dia da semana
    effective_scales = effective_scales.sort_values(by='Data Início Vigência', ascending=False)

    # Retornar apenas a escala mais recente para cada agente/dia da semana
    # Se houver múltiplas entradas/saídas para o mesmo dia, todas devem ser consideradas
    # Então, não pegamos apenas a primeira, mas todas as que são válidas e mais recentes

    # Para simplificar, vamos considerar que a escala mais recente (pela Data Início Vigência)
    # é a que prevalece para todas as entradas/saídas daquele dia.
    # Se houver múltiplas entradas/saídas para o mesmo dia, elas devem vir do mesmo registro de escala.

    # A forma mais robusta seria agrupar por (Nome do agente, Dia da Semana Num, Data Início Vigência)
    # e pegar o grupo com a Data Início Vigência máxima.

    # Para o propósito atual, se houver múltiplas linhas para o mesmo agente/dia da semana com a mesma
    # Data Início Vigência (que é a mais recente), todas elas são consideradas parte da escala vigente.

    # Então, vamos pegar todas as escalas que têm a Data Início Vigência máxima entre as efetivas
    max_vigencia_date = effective_scales['Data Início Vigência'].max()
    final_effective_scales = effective_scales[effective_scales['Data Início Vigência'] == max_vigencia_date]

    return final_effective_scales


def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    metrics_data = []

    # Garantir que as colunas de data/hora estejam no formato correto
    df_real_status['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
    df_real_status['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status['Hora de término do estado - Carimbo de data/hora'], errors='coerce')
    df_real_status.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'], inplace=True)

    for agent in selected_agents:
        current_date = start_date
        while current_date <= end_date:
            # 1. Obter a escala vigente para o dia
            daily_escala = get_effective_scale_for_day(agent, current_date, df_escala)

            total_scheduled_time_minutes = 0
            if not daily_escala.empty:
                for _, scale_row in daily_escala.iterrows():
                    scale_start_time = scale_row['Entrada']
                    scale_end_time = scale_row['Saída']

                    scale_start_dt = datetime.combine(current_date, scale_start_time)
                    scale_end_dt = datetime.combine(current_date, scale_end_time)

                    # Ajustar para escalas que terminam no dia seguinte (ex: 22:00 - 06:00)
                    if scale_end_dt < scale_start_dt:
                        scale_end_dt += timedelta(days=1)

                    # Limitar a escala ao dia atual para o cálculo diário
                    day_start_dt = datetime.combine(current_date, time.min)
                    day_end_dt = datetime.combine(current_date, time.max)

                    # Interseção da escala com o dia atual
                    effective_start = max(scale_start_dt, day_start_dt)
                    effective_end = min(scale_end_dt, day_end_dt)

                    if effective_end > effective_start:
                        total_scheduled_time_minutes += (effective_end - effective_start).total_seconds() / 60

            # 2. Obter o tempo real em status "online" para o dia
            agent_status_for_day = df_real_status[
                (df_real_status['Nome do agente'] == agent) &
                (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date) &
                (df_real_status['Estado'] == 'Unified online') # Apenas status online
            ]

            total_online_time_minutes = 0
            if not agent_status_for_day.empty:
                for _, status_row in agent_status_for_day.iterrows():
                    status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                    status_end = status_row['Hora de término do estado - Carimbo de data/hora']

                    # Interseção do status com o dia atual
                    day_start_dt = datetime.combine(current_date, time.min)
                    day_end_dt = datetime.combine(current_date, time.max)

                    effective_status_start = max(status_start, day_start_dt)
                    effective_status_end = min(status_end, day_end_dt)

                    if effective_status_end > effective_status_start:
                        total_online_time_minutes += (effective_status_end - effective_status_start).total_seconds() / 60

            # 3. Calcular disponibilidade
            disponibilidade_percent = 0
            if total_scheduled_time_minutes > 0:
                disponibilidade_percent = (total_online_time_minutes / total_scheduled_time_minutes) * 100

            metrics_data.append({
                'Agente': agent,
                'Data': current_date.strftime('%Y-%m-%d'),
                'Tempo Escala (min)': round(total_scheduled_time_minutes, 2),
                'Tempo Online (min)': round(total_online_time_minutes, 2),
                'Disponibilidade (%)': round(disponibilidade_percent, 2)
            })

            current_date += timedelta(days=1)

    return pd.DataFrame(metrics_data)


# --- Inicialização do Streamlit ---
st.set_page_config(layout="wide", page_title="Análise de Produtividade de Agentes")

st.title("Análise de Produtividade de Agentes")

# --- Inicialização dos DataFrames de histórico na session_state (e carregamento persistente) ---
if 'df_real_status_history' not in st.session_state:
    if os.path.exists(REAL_STATUS_HISTORY_FILE):
        try:
            st.session_state.df_real_status_history = pd.read_csv(
                REAL_STATUS_HISTORY_FILE,
                parse_dates=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora']
            )
            st.success(f"Histórico de status real carregado de {REAL_STATUS_HISTORY_FILE}")
        except Exception as e:
            st.error(f"Erro ao carregar histórico de status real: {e}. Inicializando DataFrame vazio.")
            st.session_state.df_real_status_history = pd.DataFrame(columns=[
                'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
                'Hora de término do estado - Carimbo de data/hora', 'Estado', 'Tempo do agente no estado / Minutos'
            ])
            # Forçar dtypes para consistência
            st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'])
            st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'])
    else:
        st.session_state.df_real_status_history = pd.DataFrame(columns=[
            'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado', 'Tempo do agente no estado / Minutos'
        ])
        # Forçar dtypes para consistência
        st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'])
        st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'])


if 'df_escala_history' not in st.session_state:
    if os.path.exists(ESCALA_HISTORY_FILE):
        try:
            st.session_state.df_escala_history = pd.read_csv(
                ESCALA_HISTORY_FILE,
                parse_dates=['Data Início Vigência', 'Data Fim Vigência']
            )
            # Converter colunas de tempo manualmente, pois read_csv não as trata diretamente
            st.session_state.df_escala_history['Entrada'] = st.session_state.df_escala_history['Entrada'].apply(lambda x: datetime.strptime(x, '%H:%M:%S').time() if pd.notna(x) else None)
            st.session_state.df_escala_history['Saída'] = st.session_state.df_escala_history['Saída'].apply(lambda x: datetime.strptime(x, '%H:%M:%S').time() if pd.notna(x) else None)
            st.success(f"Histórico de escalas carregado de {ESCALA_HISTORY_FILE}")
        except Exception as e:
            st.error(f"Erro ao carregar histórico de escalas: {e}. Inicializando DataFrame vazio.")
            st.session_state.df_escala_history = pd.DataFrame(columns=[
                'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência', 'Data Fim Vigência'
            ])
            # Forçar dtypes para consistência
            st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'])
            st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'])
    else:
        st.session_state.df_escala_history = pd.DataFrame(columns=[
            'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência', 'Data Fim Vigência'
        ])
        # Forçar dtypes para consistência
        st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'])
        st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'])


# --- Abas do aplicativo ---
tab_upload, tab_manage_scales, tab_visualization = st.tabs(["Upload de Dados", "Gerenciar Escalas", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos de Dados")

    st.subheader("Upload de Relatório de Status Real")
    uploaded_report_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) ou CSV para o relatório de status real", type=["xlsx", "csv"], key="report_uploader")
    if uploaded_report_file:
        try:
            if uploaded_report_file.name.endswith('.csv'):
                df_report_raw = pd.read_csv(uploaded_report_file)
            else:
                df_report_raw = pd.read_excel(uploaded_report_file)

            df_processed_report = process_uploaded_report(df_report_raw)

            if not df_processed_report.empty:
                # Remover duplicatas antes de adicionar ao histórico
                # Considera 'Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado' como chaves únicas
                df_processed_report_unique = df_processed_report.drop_duplicates(
                    subset=['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado']
                )

                # Concatena e remove duplicatas do histórico completo
                combined_df = pd.concat([st.session_state.df_real_status_history, df_processed_report_unique], ignore_index=True)
                st.session_state.df_real_status_history = combined_df.drop_duplicates(
                    subset=['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado']
                )

                # SALVAR O HISTÓRICO ATUALIZADO
                st.session_state.df_real_status_history.to_csv(REAL_STATUS_HISTORY_FILE, index=False)
                st.success("Relatório de status real processado e adicionado ao histórico com sucesso!")
                st.dataframe(st.session_state.df_real_status_history.tail()) # Mostrar as últimas linhas
            else:
                st.error("Nenhum dado válido processado do relatório de status real.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de status real. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Upload de Arquivo de Escala")
    uploaded_scale_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) ou CSV para a escala", type=["xlsx", "csv"], key="scale_uploader")
    if uploaded_scale_file:
        st.info("Ao fazer upload de uma nova escala, você pode definir sua data de início e, opcionalmente, uma data de fim de vigência.")
        new_scale_start_date = st.date_input("Data de Início de Vigência da Nova Escala", value=datetime.now().date(), key="new_scale_start_date_upload")
        new_scale_end_date = st.date_input("Data de Fim de Vigência da Nova Escala (opcional)", value=None, key="new_scale_end_date_upload")

        if st.button("Processar e Adicionar Escala", key="process_scale_button"):
            try:
                if uploaded_scale_file.name.endswith('.csv'):
                    df_scale_raw = pd.read_csv(uploaded_scale_file)
                else:
                    df_scale_raw = pd.read_excel(uploaded_scale_file)

                df_processed_scale = process_uploaded_scale(df_scale_raw, new_scale_start_date, new_scale_end_date)

                if not df_processed_scale.empty:
                    # Lógica para invalidar escalas antigas que se sobrepõem
                    if not st.session_state.df_escala_history.empty:
                        # Identificar escalas antigas que a nova escala substitui
                        # Uma escala antiga é substituída se for para o mesmo agente/dia da semana
                        # e sua vigência se sobrepõe ou é anterior à nova escala

                        # Converter new_scale_start_date para pd.Timestamp para comparação
                        new_start_ts = pd.Timestamp(new_scale_start_date)

                        # Filtrar escalas no histórico que são para o mesmo agente/dia da semana
                        # e cuja vigência se estende até ou além da nova data de início
                        overlapping_old_scales_mask = st.session_state.df_escala_history.apply(
                            lambda row: (row['Nome do agente'] in df_processed_scale['Nome do agente'].unique() and
                                         row['Dia da Semana Num'] in df_processed_scale['Dia da Semana Num'].unique() and
                                         row['Data Início Vigência'] < new_start_ts and
                                         (row['Data Fim Vigência'].isna() or row['Data Fim Vigência'] >= new_start_ts - timedelta(days=1))),
                            axis=1
                        )

                        # Ajustar a Data Fim Vigência das escalas antigas
                        st.session_state.df_escala_history.loc[overlapping_old_scales_mask, 'Data Fim Vigência'] = new_start_ts - timedelta(days=1)
                        st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência']) # Forçar dtype

                    # Anexar a nova escala
                    # Remover duplicatas antes de adicionar ao histórico
                    # Considera 'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência' como chaves únicas
                    df_processed_scale_unique = df_processed_scale.drop_duplicates(
                        subset=['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência']
                    )

                    combined_df = pd.concat([st.session_state.df_escala_history, df_processed_scale_unique], ignore_index=True)
                    st.session_state.df_escala_history = combined_df.drop_duplicates(
                        subset=['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência']
                    )

                    # SALVAR O HISTÓRICO ATUALIZADO
                    # Converter objetos time para string antes de salvar em CSV
                    df_to_save = st.session_state.df_escala_history.copy()
                    df_to_save['Entrada'] = df_to_save['Entrada'].apply(lambda x: x.strftime('%H:%M:%S') if x else None)
                    df_to_save['Saída'] = df_to_save['Saída'].apply(lambda x: x.strftime('%H:%M:%S') if x else None)
                    df_to_save.to_csv(ESCALA_HISTORY_FILE, index=False)

                    st.success("Arquivo de escala processado e adicionado ao histórico com sucesso!")
                    st.dataframe(st.session_state.df_escala_history.tail()) # Mostrar as últimas linhas
                else:
                    st.error("Nenhum dado válido processado do arquivo de escala.")
            except Exception as e:
                st.error(f"Erro ao processar o arquivo de escala. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Limpar Histórico")
    st.warning("Cuidado: Limpar o histórico removerá todos os dados carregados e salvos permanentemente.")
    if st.button("Limpar Histórico de Status Real"):
        st.session_state.df_real_status_history = pd.DataFrame(columns=[
            'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado', 'Tempo do agente no estado / Minutos'
        ])
        st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'])
        st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'])
        if os.path.exists(REAL_STATUS_HISTORY_FILE):
            os.remove(REAL_STATUS_HISTORY_FILE)
        st.success("Histórico de status real limpo.")

    if st.button("Limpar Histórico de Escalas"):
        st.session_state.df_escala_history = pd.DataFrame(columns=[
            'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência', 'Data Fim Vigência'
        ])
        st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'])
        st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'])
        if os.path.exists(ESCALA_HISTORY_FILE):
            os.remove(ESCALA_HISTORY_FILE)
        st.success("Histórico de escalas limpo.")


with tab_manage_scales:
    st.header("Gerenciar Escalas Manuais")
    st.info("Aqui você pode adicionar ou modificar escalas manualmente para agentes específicos.")

    all_agents_in_history = []
    if not st.session_state.df_real_status_history.empty:
        all_agents_in_history.extend(st.session_state.df_real_status_history['Nome do agente'].unique())
    if not st.session_state.df_escala_history.empty:
        all_agents_in_history.extend(st.session_state.df_escala_history['Nome do agente'].unique())
    all_agents_in_history = sorted(list(set(all_agents_in_history)))

    if not all_agents_in_history:
        st.warning("Nenhum agente encontrado no histórico de status real ou escalas. Faça o upload de dados primeiro.")
    else:
        selected_agent_manage = st.selectbox("Selecione o Agente para Gerenciar Escala", all_agents_in_history, key="selected_agent_manage")

        st.subheader(f"Escalas Atuais para {selected_agent_manage}")
        if not st.session_state.df_escala_history.empty:
            agent_scales = st.session_state.df_escala_history[st.session_state.df_escala_history['Nome do agente'] == selected_agent_manage]
            if not agent_scales.empty:
                st.dataframe(agent_scales.sort_values(by=['Dia da Semana Num', 'Data Início Vigência']))
            else:
                st.info(f"Nenhuma escala definida para {selected_agent_manage}.")
        else:
            st.info("Nenhuma escala carregada no histórico.")

        st.subheader(f"Adicionar/Atualizar Escala para {selected_agent_manage}")

        dias_map_reverse = {v: k for k, v in get_dias_map().items() if isinstance(v, int)}
        selected_day_name = st.selectbox("Dia da Semana", list(dias_map_reverse.values()), key="selected_day_manage")
        selected_day_num = get_dias_map().get(selected_day_name.upper(), None)

        manual_entrada = st.time_input("Hora de Entrada", value=time(9, 0), key="manual_entrada")
        manual_saida = st.time_input("Hora de Saída", value=time(18, 0), key="manual_saida")
        manual_start_date = st.date_input("Data de Início de Vigência", value=datetime.now().date(), key="manual_start_date")
        manual_end_date = st.date_input("Data de Fim de Vigência (opcional)", value=None, key="manual_end_date")

        if st.button(f"Salvar Escala para {selected_agent_manage} em {selected_day_name}", key="save_manual_scale"):
            if selected_day_num is not None:
                new_scale_entry = pd.DataFrame([{
                    'Nome do agente': selected_agent_manage,
                    'Dia da Semana Num': selected_day_num,
                    'Entrada': manual_entrada,
                    'Saída': manual_saida,
                    'Data Início Vigência': pd.Timestamp(manual_start_date),
                    'Data Fim Vigência': pd.Timestamp(manual_end_date) if manual_end_date else pd.NaT
                }])

                # Lógica para invalidar escalas antigas que se sobrepõem
                if not st.session_state.df_escala_history.empty:
                    new_start_ts = pd.Timestamp(manual_start_date)

                    overlapping_old_scales_mask = st.session_state.df_escala_history.apply(
                        lambda row: (row['Nome do agente'] == selected_agent_manage and
                                     row['Dia da Semana Num'] == selected_day_num and
                                     row['Data Início Vigência'] < new_start_ts and
                                     (row['Data Fim Vigência'].isna() or row['Data Fim Vigência'] >= new_start_ts - timedelta(days=1))),
                        axis=1
                    )
                    st.session_state.df_escala_history.loc[overlapping_old_scales_mask, 'Data Fim Vigência'] = new_start_ts - timedelta(days=1)
                    st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência']) # Forçar dtype

                # Anexar a nova entrada
                combined_df = pd.concat([st.session_state.df_escala_history, new_scale_entry], ignore_index=True)
                st.session_state.df_escala_history = combined_df.drop_duplicates(
                    subset=['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência']
                )

                # SALVAR O HISTÓRICO ATUALIZADO
                df_to_save = st.session_state.df_escala_history.copy()
                df_to_save['Entrada'] = df_to_save['Entrada'].apply(lambda x: x.strftime('%H:%M:%S') if x else None)
                df_to_save['Saída'] = df_to_save['Saída'].apply(lambda x: x.strftime('%H:%M:%S') if x else None)
                df_to_save.to_csv(ESCALA_HISTORY_FILE, index=False)

                st.success(f"Escala para {selected_agent_manage} em {selected_day_name} salva com sucesso!")
                st.experimental_rerun() # Recarregar para mostrar a escala atualizada
            else:
                st.error("Dia da semana inválido selecionado.")


with tab_visualization:
    st.header("Visualização da Linha do Tempo e Métricas")

    all_agents_in_history = []
    if not st.session_state.df_real_status_history.empty:
        all_agents_in_history.extend(st.session_state.df_real_status_history['Nome do agente'].unique())
    if not st.session_state.df_escala_history.empty:
        all_agents_in_history.extend(st.session_state.df_escala_history['Nome do agente'].unique())
    all_agents_in_history = sorted(list(set(all_agents_in_history)))

    if not all_agents_in_history:
        st.info("Nenhum agente encontrado no histórico. Faça o upload de dados primeiro.")
    else:
        selected_agents = st.multiselect("Selecione os Agentes para Análise", all_agents_in_history, default=all_agents_in_history[:min(5, len(all_agents_in_history))])

        today = datetime.now().date()
        default_start_date = today - timedelta(days=7)
        default_end_date = today

        start_date = st.date_input("Data de Início", value=default_start_date)
        end_date = st.date_input("Data de Fim", value=default_end_date)

        if start_date > end_date:
            st.error("A data de início não pode ser posterior à data de fim.")
        elif not selected_agents:
            st.warning("Por favor, selecione pelo menos um agente para a análise.")
        elif st.button("Gerar Gráfico e Métricas"):
            df_chart_data = pd.DataFrame()

            # Adicionar dados de status real
            if not st.session_state.df_real_status_history.empty and 'Hora de início do estado - Carimbo de data/hora' in st.session_state.df_real_status_history.columns:
                if pd.api.types.is_datetime64_any_dtype(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora']):
                    df_real_status_filtered_chart = st.session_state.df_real_status_history[
                        (st.session_state.df_real_status_history['Nome do agente'].isin(selected_agents)) &
                        (st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
                        (st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
                    ].copy()
                    df_real_status_filtered_chart['Tipo'] = df_real_status_filtered_chart['Estado'] # Usar o estado real como tipo
                    df_real_status_filtered_chart['Start'] = df_real_status_filtered_chart['Hora de início do estado - Carimbo de data/hora']
                    df_real_status_filtered_chart['Finish'] = df_real_status_filtered_chart['Hora de término do estado - Carimbo de data/hora']
                    df_real_status_filtered_chart['Data'] = df_real_status_filtered_chart['Start'].dt.date
                    df_real_status_filtered_chart['Y_Axis_Label'] = df_real_status_filtered_chart.apply(
                        lambda row: f"{row['Nome do agente']} - {row['Data'].strftime('%Y-%m-%d')} - Status Real",
                        axis=1
                    )
                    df_chart_data = pd.concat([df_chart_data, df_real_status_filtered_chart[['Y_Axis_Label', 'Start', 'Finish', 'Tipo', 'Nome do agente', 'Data']]])
                else:
                    st.warning("Coluna 'Hora de início do estado - Carimbo de data/hora' no histórico de status real não é do tipo datetime. Dados de status real não serão exibidos no gráfico.")

            # Adicionar dados de escala (dinamicamente com base na data de vigência)
            if not st.session_state.df_escala_history.empty and 'Data Início Vigência' in st.session_state.df_escala_history.columns:
                if pd.api.types.is_datetime64_any_dtype(st.session_state.df_escala_history['Data Início Vigência']):
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
                else:
                    st.warning("Coluna 'Data Início Vigência' no histórico de escalas não é do tipo datetime. Dados de escala não serão exibidos no gráfico.")

            if not df_chart_data.empty:
                # Ordenação aprimorada para o eixo Y
                y_order_base = sorted(df_chart_data['Nome do agente'].unique())
                y_order_final = []
                for agent in y_order_base:
                    # Obter todas as datas para o agente e ordenar
                    dates_for_agent = sorted(df_chart_data[df_chart_data['Nome do agente'] == agent]['Data'].unique())
                    for date_obj in dates_for_agent:
                        date_str = date_obj.strftime('%Y-%m-%d')
                        # Garante que a Escala Planejada venha antes do Status Real para cada dia
                        # Verifica se a label existe antes de adicionar para evitar erros e manter a ordem
                        if f"{agent} - {date_str} - Escala Planejada" in df_chart_data['Y_Axis_Label'].unique():
                            y_order_final.append(f"{agent} - {date_str} - Escala Planejada")
                        if f"{agent} - {date_str} - Status Real" in df_chart_data['Y_Axis_Label'].unique():
                            y_order_final.append(f"{agent} - {date_str} - Status Real")

                y_order_final = list(dict.fromkeys(y_order_final)) # Remove duplicatas mantendo a ordem

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
                    # Adicionar verificação de dtype antes de chamar calculate_metrics
                    if pd.api.types.is_datetime64_any_dtype(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora']) and \
                       pd.api.types.is_datetime64_any_dtype(st.session_state.df_escala_history['Data Início Vigência']):
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
                        st.warning("Colunas de data/hora no histórico de status real ou escalas não são do tipo datetime. Métricas não serão calculadas.")
                else:
                    st.info("Não há dados de status real e/ou escala para calcular as métricas com os filtros selecionados.")
            else:
                st.info("Nenhum dado para exibir no gráfico com os filtros selecionados.")
        else:
            st.warning("Por favor, selecione pelo menos um agente para a análise.")
