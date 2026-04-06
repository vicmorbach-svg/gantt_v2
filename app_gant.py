import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, time, date
import numpy as np
import unicodedata
import os

# --- Constantes para persistência de dados ---
HISTORY_DIR = "data_history"
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

def normalize_column_name(col_name):
    if pd.isna(col_name):
        return col_name
    col_name = str(col_name).strip().upper()
    col_name = unicodedata.normalize('NFKD', col_name).encode('ascii', 'ignore').decode('utf-8')
    col_name = ''.join(c for c in col_name if c.isalnum() or c == ' ')
    col_name = col_name.replace(' ', '_')
    return col_name

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

# --- Funções de Carregamento e Salvamento de Histórico ---
def load_history_dataframes():
    df_real_status = pd.DataFrame()
    df_escala = pd.DataFrame()

    # Carregar histórico de status real
    if os.path.exists(REAL_STATUS_HISTORY_FILE):
        try:
            df_real_status = pd.read_csv(
                REAL_STATUS_HISTORY_FILE,
                parse_dates=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'],
                dtype={'Nome do agente': str, 'Estado': str, 'Tempo do agente no estado / Minutos': float}
            )
            # Garantir que as colunas de data/hora tenham o tipo correto após o carregamento
            df_real_status['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
            df_real_status['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status['Hora de término do estado - Carimbo de data/hora'], errors='coerce')
            df_real_status.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'], inplace=True)
        except Exception as e:
            st.error(f"Erro ao carregar histórico de status real: {e}. O arquivo pode estar corrompido ou com formato inválido.")
            df_real_status = pd.DataFrame() # Resetar se houver erro

    # Carregar histórico de escala
    if os.path.exists(ESCALA_HISTORY_FILE):
        try:
            df_escala = pd.read_csv(
                ESCALA_HISTORY_FILE,
                parse_dates=['Data Início Vigência', 'Data Fim Vigência'],
                dtype={'Nome do agente': str, 'Dias de Atendimento': str, 'Dia da Semana Num': int}
            )
            # Garantir que as colunas de data/hora tenham o tipo correto após o carregamento
            df_escala['Data Início Vigência'] = pd.to_datetime(df_escala['Data Início Vigência'], errors='coerce')
            df_escala['Data Fim Vigência'] = pd.to_datetime(df_escala['Data Fim Vigência'], errors='coerce')

            # Converter colunas de tempo (Entrada, Saída) de string para datetime.time
            df_escala['Entrada'] = df_escala['Entrada'].apply(to_time)
            df_escala['Saída'] = df_escala['Saída'].apply(to_time)

            df_escala.dropna(subset=['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída', 'Dia da Semana Num', 'Data Início Vigência'], inplace=True)
        except Exception as e:
            st.error(f"Erro ao carregar histórico de escala: {e}. O arquivo pode estar corrompido ou com formato inválido.")
            df_escala = pd.DataFrame() # Resetar se houver erro

    return df_real_status, df_escala

def save_history_dataframes(df_real_status, df_escala):
    try:
        # Salvar status real
        if not df_real_status.empty:
            df_real_status.to_csv(REAL_STATUS_HISTORY_FILE, index=False)
        else: # Se o DataFrame estiver vazio, podemos remover o arquivo para "limpar"
            if os.path.exists(REAL_STATUS_HISTORY_FILE):
                os.remove(REAL_STATUS_HISTORY_FILE)

        # Salvar escala
        if not df_escala.empty:
            # Converter objetos time para string antes de salvar para CSV
            df_escala_to_save = df_escala.copy()
            df_escala_to_save['Entrada'] = df_escala_to_save['Entrada'].apply(lambda x: x.strftime('%H:%M:%S') if x is not None else None)
            df_escala_to_save['Saída'] = df_escala_to_save['Saída'].apply(lambda x: x.strftime('%H:%M:%S') if x is not None else None)
            df_escala_to_save.to_csv(ESCALA_HISTORY_FILE, index=False)
        else: # Se o DataFrame estiver vazio, podemos remover o arquivo para "limpar"
            if os.path.exists(ESCALA_HISTORY_FILE):
                os.remove(ESCALA_HISTORY_FILE)
        st.success("Dados de histórico salvos com sucesso!")
    except Exception as e:
        st.error(f"Erro ao salvar dados de histórico: {e}")

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

    df.columns = [normalize_column_name(col) for col in df.columns]

    normalized_expected_columns_report = {
        normalize_column_name(original): new_name
        for original, new_name in expected_columns_report.items()
    }

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

    df['Hora de término do estado - Carimbo de data/hora'] = df.apply(
        lambda row: row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
        if pd.isna(row['Hora de término do estado - Carimbo de data/hora']) and pd.notna(row['Hora de início do estado - Carimbo de data/hora'])
        else row['Hora de término do estado - Carimbo de data/hora'],
        axis=1
    )

    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'], inplace=True)

    df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
    df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

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

    expected_columns_scale = {
        'Nome do agente': 'Nome do agente',
        'Dias de Atendimento': 'Dias de Atendimento',
        'Entrada': 'Entrada',
        'Saída': 'Saída'
    }

    df.columns = [normalize_column_name(col) for col in df.columns]

    normalized_expected_columns_scale = {
        normalize_column_name(original): new_name
        for original, new_name in expected_columns_scale.items()
    }

    rename_map = {
        col_in_df: normalized_expected_columns_scale[col_in_df]
        for col_in_df in df.columns if col_in_df in normalized_expected_columns_scale
    }
    df = df.rename(columns=rename_map)

    required_cols = ['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída']
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        st.error(f"Colunas obrigatórias não encontradas no arquivo de escala após renomear: {missing}. Verifique o cabeçalho do arquivo.")
        return pd.DataFrame()

    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)
    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    df.dropna(subset=['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída'], inplace=True)

    # Expandir dias de atendimento
    expanded_data = []
    dias_map = get_dias_map()
    for _, row in df.iterrows():
        agente = row['Nome do agente']
        dias_str = row['Dias de Atendimento']
        entrada = row['Entrada']
        saida = row['Saída']

        dias_list = [d.strip().upper() for d in dias_str.split(',')]

        for dia_str in dias_list:
            dia_num = dias_map.get(dia_str)
            if dia_num is not None:
                expanded_data.append({
                    'Nome do agente': agente,
                    'Dias de Atendimento': dia_str,
                    'Dia da Semana Num': dia_num,
                    'Entrada': entrada,
                    'Saída': saida,
                    'Data Início Vigência': pd.Timestamp(start_effective_date),
                    'Data Fim Vigência': pd.Timestamp(end_effective_date) if end_effective_date else pd.NaT
                })

    df_processed = pd.DataFrame(expanded_data)

    # Garantir dtypes corretos para as colunas de data/hora
    df_processed['Data Início Vigência'] = pd.to_datetime(df_processed['Data Início Vigência'], errors='coerce')
    df_processed['Data Fim Vigência'] = pd.to_datetime(df_processed['Data Fim Vigência'], errors='coerce')

    return df_processed

def get_effective_scale_for_day(agent_name, current_date, df_escala_history):
    if df_escala_history.empty:
        return pd.DataFrame()

    # Converter current_date para Timestamp para comparação consistente
    current_date_ts = pd.Timestamp(current_date)

    # Filtrar escalas para o agente e dia da semana
    filtered_scales = df_escala_history[
        (df_escala_history['Nome do agente'] == agent_name) &
        (df_escala_history['Dia da Semana Num'] == current_date.weekday())
    ].copy() # Usar .copy() para evitar SettingWithCopyWarning

    if filtered_scales.empty:
        return pd.DataFrame()

    # Filtrar escalas que são válidas para a current_date
    # Data Início Vigência <= current_date
    # E (Data Fim Vigência é NaT OU Data Fim Vigência >= current_date)
    valid_scales = filtered_scales[
        (filtered_scales['Data Início Vigência'] <= current_date_ts) &
        (filtered_scales['Data Fim Vigência'].isna() | (filtered_scales['Data Fim Vigência'] >= current_date_ts))
    ]

    if valid_scales.empty:
        return pd.DataFrame()

    # Se houver múltiplas escalas válidas, pegar a mais recente (com Data Início Vigência mais próxima de current_date)
    # Ou a que tem a Data Início Vigência mais recente
    most_recent_scale = valid_scales.loc[valid_scales['Data Início Vigência'].idxmax()]

    return pd.DataFrame([most_recent_scale])

def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    if df_real_status.empty or df_escala.empty:
        return pd.DataFrame()

    # Filtrar status real pelo período e agentes selecionados
    df_real_filtered = df_real_status[
        (df_real_status['Nome do agente'].isin(selected_agents)) &
        (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
        (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
    ].copy()

    if df_real_filtered.empty:
        return pd.DataFrame()

    metrics_data = []
    current_date = start_date
    while current_date <= end_date:
        for agent in selected_agents:
            # Obter a escala efetiva para o agente no dia atual
            effective_scale = get_effective_scale_for_day(agent, current_date, df_escala)

            total_scheduled_time_minutes = 0
            if not effective_scale.empty:
                for _, scale_row in effective_scale.iterrows():
                    entrada = scale_row['Entrada']
                    saida = scale_row['Saída']

                    start_dt = datetime.combine(current_date, entrada)
                    end_dt = datetime.combine(current_date, saida)

                    if end_dt < start_dt: # Escala que vira o dia
                        end_dt += timedelta(days=1)

                    total_scheduled_time_minutes += (end_dt - start_dt).total_seconds() / 60

            # Calcular tempo em status "online" para o agente no dia atual
            agent_daily_status = df_real_filtered[
                (df_real_filtered['Nome do agente'] == agent) &
                (df_real_filtered['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date)
            ]

            total_online_time_minutes = 0
            if not agent_daily_status.empty:
                for _, status_row in agent_daily_status.iterrows():
                    status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                    status_end = status_row['Hora de término do estado - Carimbo de data/hora']
                    status_type = status_row['Estado']

                    if status_type == 'Unified online': # Apenas status online
                        # Interseção com o dia atual (para evitar contagem de status que viram o dia)
                        day_start = datetime.combine(current_date, time.min)
                        day_end = datetime.combine(current_date, time.max)

                        overlap_start = max(status_start, day_start)
                        overlap_end = min(status_end, day_end)

                        if overlap_end > overlap_start:
                            total_online_time_minutes += (overlap_end - overlap_start).total_seconds() / 60

            availability_percentage = (total_online_time_minutes / total_scheduled_time_minutes * 100) if total_scheduled_time_minutes > 0 else 0

            metrics_data.append({
                'Agente': agent,
                'Data': current_date.strftime('%Y-%m-%d'),
                'Tempo Online (min)': round(total_online_time_minutes, 2),
                'Tempo Escala (min)': round(total_scheduled_time_minutes, 2),
                'Disponibilidade (%)': round(availability_percentage, 2)
            })
        current_date += timedelta(days=1)

    df_metrics = pd.DataFrame(metrics_data)
    return df_metrics

# --- Inicialização do Streamlit ---
st.set_page_config(layout="wide", page_title="Análise de Produtividade de Agentes")

st.title("Análise de Produtividade de Agentes")

# Carregar dados de histórico na inicialização
if 'df_real_status_history' not in st.session_state:
    st.session_state.df_real_status_history, st.session_state.df_escala_history = load_history_dataframes()

# --- Abas ---
tab_upload, tab_manage_scales, tab_visualization = st.tabs(["Upload de Dados", "Gerenciar Escalas", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos de Dados")

    st.subheader("Upload de Relatório de Status Real")
    uploaded_report_file = st.file_uploader("Escolha o arquivo Excel/CSV do relatório de status real", type=["xlsx", "csv"], key="report_uploader")
    if uploaded_report_file:
        try:
            if uploaded_report_file.name.endswith('.csv'):
                df_report_raw = pd.read_csv(uploaded_report_file)
            else:
                df_report_raw = pd.read_excel(uploaded_report_file)

            df_processed_report = process_uploaded_report(df_report_raw)

            if not df_processed_report.empty:
                # Remover duplicatas antes de adicionar ao histórico
                # Usar um subconjunto de colunas para identificar duplicatas
                subset_cols_report = ['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado']
                df_processed_report_unique = df_processed_report.drop_duplicates(subset=subset_cols_report)

                # Concatenar e remover duplicatas do histórico
                st.session_state.df_real_status_history = pd.concat([st.session_state.df_real_status_history, df_processed_report_unique], ignore_index=True)
                st.session_state.df_real_status_history.drop_duplicates(subset=subset_cols_report, inplace=True)

                # Garantir que as colunas de data/hora tenham o tipo correto após a concatenação
                st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
                st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'], errors='coerce')
                st.session_state.df_real_status_history.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'], inplace=True)

                st.success("Relatório de status real processado e adicionado ao histórico!")
                st.dataframe(st.session_state.df_real_status_history.head())
                save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
            else:
                st.warning("Nenhum dado válido encontrado no relatório de status real após o processamento.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de relatório. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Upload de Arquivo de Escala")
    uploaded_scale_file = st.file_uploader("Escolha o arquivo Excel/CSV da escala", type=["xlsx", "csv"], key="scale_uploader")
    if uploaded_scale_file:
        st.info("A escala carregada será aplicada a partir da 'Data de Início de Vigência' especificada.")
        new_scale_start_date = st.date_input("Data de Início de Vigência da nova escala", value=date.today(), key="new_scale_start_date_upload")
        new_scale_end_date = st.date_input("Data de Fim de Vigência da nova escala (opcional)", value=None, key="new_scale_end_date_upload")

        if st.button("Processar e Adicionar Escala", key="process_scale_button"):
            try:
                if uploaded_scale_file.name.endswith('.csv'):
                    df_scale_raw = pd.read_csv(uploaded_scale_file)
                else:
                    df_scale_raw = pd.read_excel(uploaded_scale_file)

                df_processed_scale = process_uploaded_scale(df_scale_raw, new_scale_start_date, new_scale_end_date)

                if not df_processed_scale.empty:
                    # Lógica para gerenciar sobreposição de escalas no histórico
                    # Para cada linha em df_processed_scale, ajustar as Data Fim Vigência de escalas antigas
                    updated_escala_history = st.session_state.df_escala_history.copy()

                    for _, new_row in df_processed_scale.iterrows():
                        agent = new_row['Nome do agente']
                        dia_num = new_row['Dia da Semana Num']
                        new_start_ts = new_row['Data Início Vigência']
                        new_end_ts = new_row['Data Fim Vigência']

                        # Encontrar escalas existentes que seriam substituídas ou sobrepostas
                        # Uma escala antiga é substituída se for para o mesmo agente/dia da semana
                        # E sua vigência começa antes da nova escala
                        # E sua vigência termina depois ou no mesmo dia que a nova escala começa

                        # Escalas que terminam antes da nova escala começar não são afetadas
                        # Escalas que começam depois da nova escala começar não são afetadas

                        # Apenas escalas que se sobrepõem e começam antes da nova escala
                        # e terminam depois ou no mesmo dia que a nova escala começa

                        # Filtra escalas antigas para o mesmo agente e dia da semana
                        # cuja Data Início Vigência é anterior à nova escala
                        # e cuja Data Fim Vigência (se não for NaT) é igual ou posterior à nova Data Início Vigência

                        # Convert new_start_date to Timestamp for comparison
                        new_start_date_ts = pd.Timestamp(new_scale_start_date)

                        overlapping_old_scales_idx = updated_escala_history[
                            (updated_escala_history['Nome do agente'] == agent) &
                            (updated_escala_history['Dia da Semana Num'] == dia_num) &
                            (updated_escala_history['Data Início Vigência'] < new_start_date_ts) &
                            (updated_escala_history['Data Fim Vigência'].isna() | (updated_escala_history['Data Fim Vigência'] >= new_start_date_ts))
                        ].index

                        # Ajustar Data Fim Vigência das escalas antigas
                        if not overlapping_old_scales_idx.empty:
                            updated_escala_history.loc[overlapping_old_scales_idx, 'Data Fim Vigência'] = new_start_date_ts - timedelta(days=1)

                    # Remover quaisquer escalas antigas que agora terminam antes de começar (se a nova escala for muito antiga)
                    updated_escala_history = updated_escala_history[
                        updated_escala_history['Data Início Vigência'] <= updated_escala_history['Data Fim Vigência'].fillna(pd.Timestamp.max)
                    ]

                    # Concatenar a nova escala e remover duplicatas (para evitar adicionar a mesma escala duas vezes)
                    st.session_state.df_escala_history = pd.concat([updated_escala_history, df_processed_scale], ignore_index=True)

                    # Remover duplicatas exatas para evitar problemas
                    subset_cols_escala = ['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência', 'Data Fim Vigência']
                    st.session_state.df_escala_history.drop_duplicates(subset=subset_cols_escala, inplace=True)

                    # Garantir que as colunas de data/hora tenham o tipo correto após a concatenação
                    st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'], errors='coerce')
                    st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'], errors='coerce')

                    # Converter colunas de tempo (Entrada, Saída) de string para datetime.time
                    st.session_state.df_escala_history['Entrada'] = st.session_state.df_escala_history['Entrada'].apply(to_time)
                    st.session_state.df_escala_history['Saída'] = st.session_state.df_escala_history['Saída'].apply(to_time)

                    st.success("Arquivo de escala processado e adicionado ao histórico!")
                    st.dataframe(st.session_state.df_escala_history.head())
                    save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
                else:
                    st.warning("Nenhum dado válido encontrado no arquivo de escala após o processamento.")
            except Exception as e:
                st.error(f"Erro ao processar o arquivo de escala. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Limpar Histórico de Dados")
    st.warning("Esta ação removerá todos os dados de status real e escala do histórico. Use com cautela!")
    if st.button("Limpar Todo o Histórico", key="clear_history_button"):
        st.session_state.df_real_status_history = pd.DataFrame(columns=[
            'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado',
            'Tempo do agente no estado / Minutos'
        ]).astype({
            'Nome do agente': str,
            'Hora de início do estado - Carimbo de data/hora': 'datetime64[ns]',
            'Hora de término do estado - Carimbo de data/hora': 'datetime64[ns]',
            'Estado': str,
            'Tempo do agente no estado / Minutos': float
        })
        st.session_state.df_escala_history = pd.DataFrame(columns=[
            'Nome do agente', 'Dias de Atendimento', 'Dia da Semana Num',
            'Entrada', 'Saída', 'Data Início Vigência', 'Data Fim Vigência'
        ]).astype({
            'Nome do agente': str,
            'Dias de Atendimento': str,
            'Dia da Semana Num': int,
            'Entrada': object, # time objects will be stored as objects
            'Saída': object,   # time objects will be stored as objects
            'Data Início Vigência': 'datetime64[ns]',
            'Data Fim Vigência': 'datetime64[ns]'
        })
        save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
        st.success("Histórico de dados limpo com sucesso!")
        st.rerun()

with tab_manage_scales:
    st.header("Gerenciar Escalas Manuais")

    if st.session_state.df_escala_history.empty:
        st.info("Nenhuma escala no histórico. Adicione uma escala via upload ou manualmente.")
    else:
        st.subheader("Escalas Atuais no Histórico")
        st.dataframe(st.session_state.df_escala_history)

    st.subheader("Adicionar/Atualizar Escala Manualmente")

    # Obter agentes únicos do histórico de escalas ou status real
    all_unique_agents = []
    if not st.session_state.df_escala_history.empty:
        all_unique_agents.extend(st.session_state.df_escala_history['Nome do agente'].unique())
    if not st.session_state.df_real_status_history.empty:
        all_unique_agents.extend(st.session_state.df_real_status_history['Nome do agente'].unique())
    all_unique_agents = sorted(list(set(all_unique_agents)))

    selected_agent_manual = st.selectbox("Selecione o Agente", [''] + all_unique_agents, key="manual_agent_select")

    dias_map_reverse = {v: k for k, v in get_dias_map().items() if len(k) > 3} # Pegar nomes completos
    selected_day_manual = st.selectbox("Selecione o Dia da Semana", [''] + sorted(dias_map_reverse.values()), key="manual_day_select")

    manual_entrada = st.time_input("Hora de Entrada", value=time(9, 0), key="manual_entrada")
    manual_saida = st.time_input("Hora de Saída", value=time(18, 0), key="manual_saida")

    manual_start_date = st.date_input("Data de Início de Vigência", value=date.today(), key="manual_start_date")
    manual_end_date = st.date_input("Data de Fim de Vigência (opcional)", value=None, key="manual_end_date")

    if st.button("Adicionar/Atualizar Escala Manual", key="add_manual_scale_button"):
        if selected_agent_manual and selected_day_manual:
            try:
                dia_num_manual = get_dias_map().get(selected_day_manual.upper())
                if dia_num_manual is None:
                    st.error("Dia da semana selecionado inválido.")
                else:
                    new_scale_entry = pd.DataFrame([{
                        'Nome do agente': normalize_agent_name(selected_agent_manual),
                        'Dias de Atendimento': selected_day_manual.upper(),
                        'Dia da Semana Num': dia_num_manual,
                        'Entrada': manual_entrada,
                        'Saída': manual_saida,
                        'Data Início Vigência': pd.Timestamp(manual_start_date),
                        'Data Fim Vigência': pd.Timestamp(manual_end_date) if manual_end_date else pd.NaT
                    }])

                    # Lógica de sobreposição similar ao upload
                    updated_escala_history = st.session_state.df_escala_history.copy()

                    # Convert manual_start_date to Timestamp for comparison
                    manual_start_date_ts = pd.Timestamp(manual_start_date)

                    overlapping_old_scales_idx = updated_escala_history[
                        (updated_escala_history['Nome do agente'] == normalize_agent_name(selected_agent_manual)) &
                        (updated_escala_history['Dia da Semana Num'] == dia_num_manual) &
                        (updated_escala_history['Data Início Vigência'] < manual_start_date_ts) &
                        (updated_escala_history['Data Fim Vigência'].isna() | (updated_escala_history['Data Fim Vigência'] >= manual_start_date_ts))
                    ].index

                    if not overlapping_old_scales_idx.empty:
                        updated_escala_history.loc[overlapping_old_scales_idx, 'Data Fim Vigência'] = manual_start_date_ts - timedelta(days=1)

                    updated_escala_history = updated_escala_history[
                        updated_escala_history['Data Início Vigência'] <= updated_escala_history['Data Fim Vigência'].fillna(pd.Timestamp.max)
                    ]

                    st.session_state.df_escala_history = pd.concat([updated_escala_history, new_scale_entry], ignore_index=True)

                    subset_cols_escala = ['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência', 'Data Fim Vigência']
                    st.session_state.df_escala_history.drop_duplicates(subset=subset_cols_escala, inplace=True)

                    # Garantir que as colunas de data/hora tenham o tipo correto após a concatenação
                    st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'], errors='coerce')
                    st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'], errors='coerce')

                    # Converter colunas de tempo (Entrada, Saída) de string para datetime.time
                    st.session_state.df_escala_history['Entrada'] = st.session_state.df_escala_history['Entrada'].apply(to_time)
                    st.session_state.df_escala_history['Saída'] = st.session_state.df_escala_history['Saída'].apply(to_time)

                    st.success(f"Escala para {selected_agent_manual} no(a) {selected_day_manual} adicionada/atualizada com sucesso!")
                    save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
                    st.rerun()
            except Exception as e:
                st.error(f"Erro ao adicionar/atualizar escala manual: {e}")
        else:
            st.warning("Por favor, selecione um agente e um dia da semana.")

with tab_visualization:
    st.header("Visualização da Linha do Tempo e Métricas de Disponibilidade")

    if st.session_state.df_real_status_history.empty and st.session_state.df_escala_history.empty:
        st.info("Por favor, faça o upload dos arquivos na aba 'Upload de Dados' primeiro.")
    else:
        # Obter todos os agentes únicos do histórico de escalas e status real
        all_unique_agents = []
        if not st.session_state.df_escala_history.empty:
            all_unique_agents.extend(st.session_state.df_escala_history['Nome do agente'].unique())
        if not st.session_state.df_real_status_history.empty:
            all_unique_agents.extend(st.session_state.df_real_status_history['Nome do agente'].unique())
        all_unique_agents = sorted(list(set(all_unique_agents)))

        selected_agents = st.multiselect(
            "Selecione os Agentes para Análise",
            options=all_unique_agents,
            default=all_unique_agents if len(all_unique_agents) <= 5 else all_unique_agents[:5] # Seleciona até 5 por padrão
        )

        today = date.today()
        default_start_date = today - timedelta(days=7)
        default_end_date = today

        start_date = st.date_input("Data de Início", value=default_start_date)
        end_date = st.date_input("Data de Fim", value=default_end_date)

        if selected_agents:
            df_chart_data = pd.DataFrame()

            # Adicionar dados de status real
            if not st.session_state.df_real_status_history.empty and 'Hora de início do estado - Carimbo de data/hora' in st.session_state.df_real_status_history.columns:
                if pd.api.types.is_datetime64_any_dtype(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora']):
                    df_real_filtered_for_chart = st.session_state.df_real_status_history[
                        (st.session_state.df_real_status_history['Nome do agente'].isin(selected_agents)) &
                        (st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
                        (st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
                    ].copy()

                    if not df_real_filtered_for_chart.empty:
                        df_real_filtered_for_chart['Tipo'] = 'Status Real'
                        df_real_filtered_for_chart['Data'] = df_real_filtered_for_chart['Hora de início do estado - Carimbo de data/hora'].dt.date
                        df_real_filtered_for_chart['Y_Axis_Label'] = df_real_filtered_for_chart['Nome do agente'] + ' - ' + df_real_filtered_for_chart['Data'].dt.strftime('%Y-%m-%d') + ' - Status Real'
                        df_chart_data = pd.concat([df_chart_data, df_real_filtered_for_chart.rename(columns={
                            'Hora de início do estado - Carimbo de data/hora': 'Start',
                            'Hora de término do estado - Carimbo de data/hora': 'Finish'
                        })[['Y_Axis_Label', 'Start', 'Finish', 'Tipo', 'Nome do agente', 'Data']]])
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
