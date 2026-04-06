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
        st.error(f"Colunas necessárias não encontradas no arquivo de escala após renomear. Esperadas: {required_cols}. Encontradas: {df.columns.tolist()}")
        return pd.DataFrame()

    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)
    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    df.dropna(subset=['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída'], inplace=True)

    dias_map = get_dias_map()
    df['Dia da Semana Num'] = df['Dias de Atendimento'].str.upper().map(dias_map)
    df.dropna(subset=['Dia da Semana Num'], inplace=True)
    df['Dia da Semana Num'] = df['Dia da Semana Num'].astype(int)

    df['Data Início Vigência'] = pd.to_datetime(start_effective_date).normalize() # Garante que seja datetime à meia-noite
    df['Data Fim Vigência'] = pd.to_datetime(end_effective_date).normalize() if end_effective_date else pd.NaT # pd.NaT para indefinido

    return df

def get_effective_scale_for_day(agent_name, current_date, df_escala_history):
    if df_escala_history.empty:
        return pd.DataFrame()

    # Converter current_date para pd.Timestamp para comparação consistente
    current_date_ts = pd.Timestamp(current_date)

    # Filtrar escalas para o agente e dia da semana
    filtered_by_agent_day = df_escala_history[
        (df_escala_history['Nome do agente'] == agent_name) &
        (df_escala_history['Dia da Semana Num'] == current_date.weekday())
    ].copy()

    if filtered_by_agent_day.empty:
        return pd.DataFrame()

    # Filtrar por vigência: current_date deve estar entre Data Início Vigência e Data Fim Vigência
    # Data Início Vigência <= current_date
    # Data Fim Vigência >= current_date OU Data Fim Vigência é NaT (indefinido)

    # Garantir que as colunas de vigência são datetime para comparação
    filtered_by_agent_day['Data Início Vigência'] = pd.to_datetime(filtered_by_agent_day['Data Início Vigência'], errors='coerce')
    filtered_by_agent_day['Data Fim Vigência'] = pd.to_datetime(filtered_by_agent_day['Data Fim Vigência'], errors='coerce')

    effective_scales = filtered_by_agent_day[
        (filtered_by_agent_day['Data Início Vigência'] <= current_date_ts) &
        (
            (filtered_by_agent_day['Data Fim Vigência'].isna()) |
            (filtered_by_agent_day['Data Fim Vigência'] >= current_date_ts)
        )
    ]

    if effective_scales.empty:
        return pd.DataFrame()

    # Se houver múltiplas escalas válidas, pegar a mais recente (maior Data Início Vigência)
    # Isso resolve sobreposições, priorizando a regra mais nova
    effective_scales = effective_scales.sort_values(by='Data Início Vigência', ascending=False).drop_duplicates(subset=['Nome do agente', 'Dia da Semana Num'], keep='first')

    return effective_scales

def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    metrics_data = []

    # Converter start_date e end_date para pd.Timestamp para comparação consistente
    start_date_ts = pd.Timestamp(start_date)
    end_date_ts = pd.Timestamp(end_date)

    # Filtrar df_real_status uma vez para o período e agentes selecionados
    # Garantir que a coluna de data/hora seja datetime antes de usar .dt
    if not pd.api.types.is_datetime64_any_dtype(df_real_status['Hora de início do estado - Carimbo de data/hora']):
        df_real_status['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status['Hora de início do estado - Carimbo de data/hora'], errors='coerce')

    df_real_status_filtered = df_real_status[
        (df_real_status['Nome do agente'].isin(selected_agents)) &
        (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
        (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
    ].copy()

    for agent in selected_agents:
        total_scheduled_time_minutes = 0
        total_online_time_minutes = 0

        current_date = start_date
        while current_date <= end_date:
            daily_escala = get_effective_scale_for_day(agent, current_date, df_escala)

            if not daily_escala.empty:
                for _, scale_row in daily_escala.iterrows():
                    scale_start_time = scale_row['Entrada']
                    scale_end_time = scale_row['Saída']

                    scale_start_dt = datetime.combine(current_date, scale_start_time)
                    scale_end_dt = datetime.combine(current_date, scale_end_time)

                    if scale_end_dt < scale_start_dt: # Escala que vira o dia
                        scale_end_dt += timedelta(days=1)

                    # Limitar a escala ao dia atual para o cálculo diário
                    day_end_limit = datetime.combine(current_date, time.max)
                    effective_scale_end = min(scale_end_dt, day_end_limit)

                    scheduled_duration = (effective_scale_end - scale_start_dt).total_seconds() / 60
                    if scheduled_duration > 0:
                        total_scheduled_time_minutes += scheduled_duration

            # Calcular tempo online real para o agente no dia
            agent_daily_status = df_real_status_filtered[
                (df_real_status_filtered['Nome do agente'] == agent) &
                (df_real_status_filtered['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date)
            ].copy()

            if not agent_daily_status.empty:
                for _, status_row in agent_daily_status.iterrows():
                    status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                    status_end = status_row['Hora de término do estado - Carimbo de data/hora']
                    status_type = status_row['Estado']

                    # Considerar apenas estados "online" para disponibilidade
                    if status_type in ['Unified online', 'Unified transfers only', 'Unified busy', 'Unified wrap up']:
                        online_duration = (status_end - status_start).total_seconds() / 60
                        total_online_time_minutes += online_duration

            current_date += timedelta(days=1)

        availability_percentage = (total_online_time_minutes / total_scheduled_time_minutes * 100) if total_scheduled_time_minutes > 0 else 0

        metrics_data.append({
            'Agente': agent,
            'Tempo Agendado (min)': round(total_scheduled_time_minutes, 2),
            'Tempo Online (min)': round(total_online_time_minutes, 2),
            'Disponibilidade (%)': round(availability_percentage, 2)
        })

    return pd.DataFrame(metrics_data)

# --- Funções de Carregamento e Salvamento de Histórico ---
def load_history_dataframes():
    df_real_status_history = pd.DataFrame()
    df_escala_history = pd.DataFrame()

    # Carregar histórico de status real
    if os.path.exists(REAL_STATUS_HISTORY_FILE):
        try:
            df_real_status_history = pd.read_csv(
                REAL_STATUS_HISTORY_FILE,
                parse_dates=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora']
            )
            # Garantir que as colunas de data/hora são datetime64[ns]
            df_real_status_history['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status_history['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
            df_real_status_history['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status_history['Hora de término do estado - Carimbo de data/hora'], errors='coerce')
            st.success(f"Histórico de status real carregado de {REAL_STATUS_HISTORY_FILE}")
        except Exception as e:
            st.error(f"Erro ao carregar histórico de status real: {e}")
            df_real_status_history = pd.DataFrame(columns=[
                'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
                'Hora de término do estado - Carimbo de data/hora', 'Estado',
                'Tempo do agente no estado / Minutos', 'Tipo'
            ])

    # Carregar histórico de escala
    if os.path.exists(ESCALA_HISTORY_FILE):
        try:
            df_escala_history = pd.read_csv(
                ESCALA_HISTORY_FILE,
                parse_dates=['Data Início Vigência', 'Data Fim Vigência']
            )
            # Garantir que as colunas de data/hora são datetime64[ns]
            df_escala_history['Data Início Vigência'] = pd.to_datetime(df_escala_history['Data Início Vigência'], errors='coerce')
            df_escala_history['Data Fim Vigência'] = pd.to_datetime(df_escala_history['Data Fim Vigência'], errors='coerce')

            # Converter colunas de tempo de volta para datetime.time
            df_escala_history['Entrada'] = df_escala_history['Entrada'].apply(to_time)
            df_escala_history['Saída'] = df_escala_history['Saída'].apply(to_time)

            st.success(f"Histórico de escalas carregado de {ESCALA_HISTORY_FILE}")
        except Exception as e:
            st.error(f"Erro ao carregar histórico de escalas: {e}")
            df_escala_history = pd.DataFrame(columns=[
                'Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída',
                'Dia da Semana Num', 'Data Início Vigência', 'Data Fim Vigência'
            ])

    # Se os DataFrames ainda estiverem vazios, inicializá-los com os dtypes corretos
    if df_real_status_history.empty:
        df_real_status_history = pd.DataFrame(columns=[
            'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado',
            'Tempo do agente no estado / Minutos', 'Tipo'
        ]).astype({
            'Hora de início do estado - Carimbo de data/hora': 'datetime64[ns]',
            'Hora de término do estado - Carimbo de data/hora': 'datetime64[ns]'
        })
    if df_escala_history.empty:
        df_escala_history = pd.DataFrame(columns=[
            'Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída',
            'Dia da Semana Num', 'Data Início Vigência', 'Data Fim Vigência'
        ]).astype({
            'Data Início Vigência': 'datetime64[ns]',
            'Data Fim Vigência': 'datetime64[ns]'
        })


    return df_real_status_history, df_escala_history

def save_history_dataframes(df_real_status_history, df_escala_history):
    try:
        # Para salvar as colunas de tempo, converta-as para string antes de salvar
        df_escala_to_save = df_escala_history.copy()
        if 'Entrada' in df_escala_to_save.columns:
            df_escala_to_save['Entrada'] = df_escala_to_save['Entrada'].astype(str)
        if 'Saída' in df_escala_to_save.columns:
            df_escala_to_save['Saída'] = df_escala_to_save['Saída'].astype(str)

        df_real_status_history.to_csv(REAL_STATUS_HISTORY_FILE, index=False)
        df_escala_to_save.to_csv(ESCALA_HISTORY_FILE, index=False)
        st.success("Histórico de dados salvo com sucesso!")
    except Exception as e:
        st.error(f"Erro ao salvar histórico de dados: {e}")

# --- Inicialização do Streamlit ---
st.set_page_config(layout="wide", page_title="Análise de Produtividade de Agentes")

# Carregar dados históricos na inicialização do aplicativo
if 'df_real_status_history' not in st.session_state or 'df_escala_history' not in st.session_state:
    st.session_state.df_real_status_history, st.session_state.df_escala_history = load_history_dataframes()

st.title("Análise de Produtividade de Agentes")

tab_upload, tab_manage_scales, tab_visualization = st.tabs(["Upload de Dados", "Gerenciar Escalas", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos")

    st.subheader("Upload de Relatório de Status Real")
    uploaded_file_report = st.file_uploader("Escolha o arquivo Excel/CSV do relatório de status real", type=["xlsx", "csv"], key="report_upload")
    if uploaded_file_report:
        try:
            if uploaded_file_report.name.endswith('.csv'):
                df_report_raw = pd.read_csv(uploaded_file_report)
            else:
                df_report_raw = pd.read_excel(uploaded_file_report)

            df_processed_report = process_uploaded_report(df_report_raw)

            if not df_processed_report.empty:
                # Remover duplicatas antes de adicionar ao histórico
                # Considera Nome do agente, Hora de início, Hora de término, Estado como identificadores únicos
                unique_cols_report = ['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora', 'Estado']

                # Certificar-se de que as colunas de data/hora estão no formato datetime para comparação
                df_processed_report['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df_processed_report['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
                df_processed_report['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df_processed_report['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

                # Filtrar apenas as linhas que não existem no histórico
                if not st.session_state.df_real_status_history.empty:
                    # Alinhar colunas para merge
                    common_cols = list(set(st.session_state.df_real_status_history.columns) & set(df_processed_report.columns))
                    df_processed_report_aligned = df_processed_report[common_cols]
                    df_history_aligned = st.session_state.df_real_status_history[common_cols]

                    # Usar merge para identificar duplicatas
                    merged = pd.merge(
                        df_processed_report_aligned,
                        df_history_aligned,
                        on=unique_cols_report,
                        how='left',
                        indicator=True
                    )
                    new_rows = df_processed_report[merged['_merge'] == 'left_only']
                else:
                    new_rows = df_processed_report

                if not new_rows.empty:
                    st.session_state.df_real_status_history = pd.concat([st.session_state.df_real_status_history, new_rows], ignore_index=True)
                    st.session_state.df_real_status_history.drop_duplicates(subset=unique_cols_report, inplace=True) # Garantir unicidade final
                    st.session_state.df_real_status_history.reset_index(drop=True, inplace=True)
                    save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
                    st.success(f"Relatório de status real processado e {len(new_rows)} novas linhas adicionadas ao histórico.")
                else:
                    st.info("Nenhuma nova linha encontrada no relatório de status real para adicionar ao histórico.")
            else:
                st.warning("O arquivo de relatório de status real está vazio ou não pôde ser processado.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de relatório de status real. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Upload de Arquivo de Escala")
    uploaded_file_scale = st.file_uploader("Escolha o arquivo Excel/CSV da escala", type=["xlsx", "csv"], key="scale_upload")
    if uploaded_file_scale:
        st.info("Para o upload de escala, a data de início de vigência será a data de hoje. A data de fim de vigência será indefinida.")
        scale_start_date_upload = date.today()

        try:
            if uploaded_file_scale.name.endswith('.csv'):
                df_scale_raw = pd.read_csv(uploaded_file_scale)
            else:
                df_scale_raw = pd.read_excel(uploaded_file_scale)

            df_processed_scale = process_uploaded_scale(df_scale_raw, scale_start_date_upload, None) # Fim indefinido

            if not df_processed_scale.empty:
                # Lógica para atualizar o histórico de escalas com a nova vigência
                new_rows_scale = []
                for _, new_scale_row in df_processed_scale.iterrows():
                    agent = new_scale_row['Nome do agente']
                    day_num = new_scale_row['Dia da Semana Num']
                    new_start_vig = new_scale_row['Data Início Vigência']

                    # Encontrar escalas existentes para o mesmo agente e dia da semana que se sobrepõem
                    overlapping_scales_mask = (
                        (st.session_state.df_escala_history['Nome do agente'] == agent) &
                        (st.session_state.df_escala_history['Dia da Semana Num'] == day_num) &
                        (st.session_state.df_escala_history['Data Início Vigência'] < new_start_vig) &
                        (
                            (st.session_state.df_escala_history['Data Fim Vigência'].isna()) |
                            (st.session_state.df_escala_history['Data Fim Vigência'] >= new_start_vig)
                        )
                    )

                    # Ajustar a Data Fim Vigência das escalas antigas
                    st.session_state.df_escala_history.loc[overlapping_scales_mask, 'Data Fim Vigência'] = new_start_vig - timedelta(days=1)

                    # Adicionar a nova escala
                    new_rows_scale.append(new_scale_row)

                if new_rows_scale:
                    st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, pd.DataFrame(new_rows_scale)], ignore_index=True)
                    st.session_state.df_escala_history.drop_duplicates(subset=['Nome do agente', 'Dia da Semana Num', 'Data Início Vigência'], keep='last', inplace=True) # Remove duplicatas exatas
                    st.session_state.df_escala_history.reset_index(drop=True, inplace=True)
                    save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
                    st.success(f"Arquivo de escala processado e novas escalas adicionadas/atualizadas no histórico.")
                else:
                    st.info("Nenhuma nova escala encontrada para adicionar/atualizar no histórico.")
            else:
                st.warning("O arquivo de escala está vazio ou não pôde ser processado.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de escala. Verifique o formato do arquivo. Erro: {e}")

    if st.button("Limpar todo o Histórico de Dados"):
        st.session_state.df_real_status_history = pd.DataFrame(columns=[
            'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado',
            'Tempo do agente no estado / Minutos', 'Tipo'
        ]).astype({
            'Hora de início do estado - Carimbo de data/hora': 'datetime64[ns]',
            'Hora de término do estado - Carimbo de data/hora': 'datetime64[ns]'
        })
        st.session_state.df_escala_history = pd.DataFrame(columns=[
            'Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída',
            'Dia da Semana Num', 'Data Início Vigência', 'Data Fim Vigência'
        ]).astype({
            'Data Início Vigência': 'datetime64[ns]',
            'Data Fim Vigência': 'datetime64[ns]'
        })
        save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
        st.success("Todo o histórico de dados foi limpo.")
        st.rerun()

with tab_manage_scales:
    st.header("Gerenciar Escalas Manuais")

    if st.session_state.df_escala_history.empty:
        st.info("Nenhuma escala no histórico. Adicione uma escala via upload ou manualmente.")
    else:
        st.subheader("Escalas Atuais no Histórico")
        st.dataframe(st.session_state.df_escala_history, use_container_width=True)

    st.subheader("Adicionar/Atualizar Escala Manualmente")

    all_agents_in_history = sorted(st.session_state.df_real_status_history['Nome do agente'].unique().tolist() + 
                                   st.session_state.df_escala_history['Nome do agente'].unique().tolist())
    all_agents_in_history = list(dict.fromkeys(all_agents_in_history)) # Remove duplicatas mantendo a ordem

    selected_agent_manual = st.selectbox("Selecione o Agente", [''] + all_agents_in_history, key="manual_agent_select")

    dias_semana_map = {
        'Segunda-feira': 0, 'Terça-feira': 1, 'Quarta-feira': 2,
        'Quinta-feira': 3, 'Sexta-feira': 4, 'Sábado': 5, 'Domingo': 6
    }
    selected_day_manual = st.selectbox("Selecione o Dia da Semana", list(dias_semana_map.keys()), key="manual_day_select")

    entrada_manual = st.time_input("Hora de Entrada", value=time(9, 0), key="manual_entrada")
    saida_manual = st.time_input("Hora de Saída", value=time(18, 0), key="manual_saida")

    new_start_date_manual = st.date_input("Data de Início da Vigência", value=date.today(), key="manual_start_date")
    new_end_date_manual = st.date_input("Data de Fim da Vigência (opcional)", value=None, key="manual_end_date")

    if st.button("Adicionar/Atualizar Escala"):
        if selected_agent_manual and selected_day_manual:
            new_scale_data = {
                'Nome do agente': normalize_agent_name(selected_agent_manual),
                'Dias de Atendimento': selected_day_manual, # Manter string para exibição
                'Entrada': entrada_manual,
                'Saída': saida_manual,
                'Dia da Semana Num': dias_semana_map[selected_day_manual],
                'Data Início Vigência': pd.Timestamp(new_start_date_manual).normalize(),
                'Data Fim Vigência': pd.Timestamp(new_end_date_manual).normalize() if new_end_date_manual else pd.NaT
            }
            new_scale_df = pd.DataFrame([new_scale_data])

            # Lógica para atualizar o histórico de escalas com a nova vigência
            agent = new_scale_data['Nome do agente']
            day_num = new_scale_data['Dia da Semana Num']
            new_start_vig = new_scale_data['Data Início Vigência']

            # Encontrar escalas existentes para o mesmo agente e dia da semana que se sobrepõem
            overlapping_scales_mask = (
                (st.session_state.df_escala_history['Nome do agente'] == agent) &
                (st.session_state.df_escala_history['Dia da Semana Num'] == day_num) &
                (st.session_state.df_escala_history['Data Início Vigência'] < new_start_vig) &
                (
                    (st.session_state.df_escala_history['Data Fim Vigência'].isna()) |
                    (st.session_state.df_escala_history['Data Fim Vigência'] >= new_start_vig)
                )
            )

            # Ajustar a Data Fim Vigência das escalas antigas
            st.session_state.df_escala_history.loc[overlapping_scales_mask, 'Data Fim Vigência'] = new_start_vig - timedelta(days=1)

            # Adicionar a nova escala
            st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, new_scale_df], ignore_index=True)
            st.session_state.df_escala_history.drop_duplicates(subset=['Nome do agente', 'Dia da Semana Num', 'Data Início Vigência'], keep='last', inplace=True) # Remove duplicatas exatas
            st.session_state.df_escala_history.reset_index(drop=True, inplace=True)
            save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
            st.success(f"Escala para {selected_agent_manual} em {selected_day_manual} adicionada/atualizada com sucesso!")
            st.rerun()
        else:
            st.warning("Por favor, selecione um agente e um dia da semana.")

with tab_visualization:
    st.header("Visualização e Métricas")

    if not st.session_state.df_real_status_history.empty or not st.session_state.df_escala_history.empty:
        all_unique_agents = sorted(
            st.session_state.df_escala_history['Nome do agente'].unique().tolist() if not st.session_state.df_escala_history.empty else []
        )

        if not all_unique_agents:
            st.info("Nenhum agente encontrado no histórico de escalas. Por favor, faça o upload de um arquivo de escala ou adicione uma escala manualmente.")
        else:
            selected_agents = st.multiselect("Selecione os Agentes para Análise", all_unique_agents, default=all_unique_agents[:5])

            today = date.today()
            start_date = st.date_input("Data de Início", value=today - timedelta(days=7))
            end_date = st.date_input("Data de Fim", value=today)

            if selected_agents:
                df_chart_data = pd.DataFrame()

                # Adicionar dados de status real
                if not st.session_state.df_real_status_history.empty and 'Hora de início do estado - Carimbo de data/hora' in st.session_state.df_real_status_history.columns:
                    if pd.api.types.is_datetime64_any_dtype(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora']):
                        df_real_status_filtered_chart = st.session_state.df_real_status_history[
                            (st.session_state.df_real_status_history['Nome do agente'].isin(selected_agents)) &
                            (st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
                            (st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
                        ].copy()
                        df_real_status_filtered_chart['Tipo'] = df_real_status_filtered_chart['Estado']
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
