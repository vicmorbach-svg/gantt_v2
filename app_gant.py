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

# Função auxiliar para converter string para objeto time
def to_time(time_str):
    if pd.isna(time_str):
        return None
    try:
        return datetime.strptime(str(time_str), '%H:%M:%S').time()
    except ValueError:
        try:
            return datetime.strptime(str(time_str), '%H:%M').time()
        except ValueError:
            return None

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
            df_real_status['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
            df_real_status['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status['Hora de término do estado - Carimbo de data/hora'], errors='coerce')
            df_real_status.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'], inplace=True)
        except Exception as e:
            st.error(f"Erro ao carregar histórico de status real: {e}. O arquivo pode estar corrompido ou com formato inválido.")
            df_real_status = pd.DataFrame()

    # Carregar histórico de escala
    if os.path.exists(ESCALA_HISTORY_FILE):
        try:
            df_escala = pd.read_csv(
                ESCALA_HISTORY_FILE,
                parse_dates=['Data Início Vigência', 'Data Fim Vigência'],
                dtype={'Nome do agente': str, 'Dias de Atendimento': str, 'Dia da Semana Num': int}
            )
            df_escala['Data Início Vigência'] = pd.to_datetime(df_escala['Data Início Vigência'], errors='coerce')
            df_escala['Data Fim Vigência'] = pd.to_datetime(df_escala['Data Fim Vigência'], errors='coerce')

            df_escala['Entrada'] = df_escala['Entrada'].apply(to_time)
            df_escala['Saída'] = df_escala['Saída'].apply(to_time)

            df_escala.dropna(subset=['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída', 'Dia da Semana Num', 'Data Início Vigência'], inplace=True)
        except Exception as e:
            st.error(f"Erro ao carregar histórico de escala: {e}. O arquivo pode estar corrompido ou com formato inválido.")
            df_escala = pd.DataFrame()

    return df_real_status, df_escala

def save_history_dataframes(df_real_status, df_escala):
    try:
        if not df_real_status.empty:
            df_real_status.to_csv(REAL_STATUS_HISTORY_FILE, index=False)
        else:
            if os.path.exists(REAL_STATUS_HISTORY_FILE):
                os.remove(REAL_STATUS_HISTORY_FILE)

        if not df_escala.empty:
            df_escala_to_save = df_escala.copy()
            df_escala_to_save['Entrada'] = df_escala_to_save['Entrada'].apply(lambda x: x.strftime('%H:%M:%S') if x is not None else None)
            df_escala_to_save['Saída'] = df_escala_to_save['Saída'].apply(lambda x: x.strftime('%H:%M:%S') if x is not None else None)
            df_escala_to_save.to_csv(ESCALA_HISTORY_FILE, index=False)
        else:
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

def process_uploaded_scale(df_scale_raw, start_effective_date, end_effective_date):
    df = df_scale_raw.copy()
    dias_map = get_dias_map()

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
        st.error(f"Colunas obrigatórias ausentes no arquivo de escala após renomear: {', '.join(missing)}. Verifique o cabeçalho do arquivo.")
        return pd.DataFrame()

    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)
    df['Dias de Atendimento'] = df['Dias de Atendimento'].astype(str).str.upper().apply(
        lambda x: unicodedata.normalize('NFKD', x).encode('ascii', 'ignore').decode('utf-8')
    )

    df['Dia da Semana Num'] = df['Dias de Atendimento'].map(dias_map)
    df.dropna(subset=['Dia da Semana Num'], inplace=True)
    df['Dia da Semana Num'] = df['Dia da Semana Num'].astype(int)

    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    df.dropna(subset=['Entrada', 'Saída'], inplace=True)

    df['Data Início Vigência'] = pd.to_datetime(start_effective_date)
    df['Data Fim Vigência'] = pd.to_datetime(end_effective_date) if end_effective_date else pd.NaT

    return df[['Nome do agente', 'Dias de Atendimento', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência', 'Data Fim Vigência']]

def get_effective_scale_for_day(df_escala_history, agent_name, current_date):
    if df_escala_history.empty:
        return pd.DataFrame()

    # Converter current_date para Timestamp para comparação consistente
    current_timestamp = pd.Timestamp(current_date)

    # Filtrar escalas para o agente e dia da semana
    filtered_scales = df_escala_history[
        (df_escala_history['Nome do agente'] == agent_name) &
        (df_escala_history['Dia da Semana Num'] == current_date.weekday())
    ].copy()

    if filtered_scales.empty:
        return pd.DataFrame()

    # Filtrar escalas que estão ativas na current_date
    # Data Início Vigência <= current_date
    # E (Data Fim Vigência é NaT OU Data Fim Vigência >= current_date)
    active_scales = filtered_scales[
        (filtered_scales['Data Início Vigência'] <= current_timestamp) &
        (filtered_scales['Data Fim Vigência'].isna() | (filtered_scales['Data Fim Vigência'] >= current_timestamp))
    ].copy()

    if active_scales.empty:
        return pd.DataFrame()

    # Se houver múltiplas escalas ativas, pegar a mais recente (maior Data Início Vigência)
    # Isso resolve conflitos onde uma escala mais nova substitui uma antiga
    effective_scale = active_scales.loc[active_scales['Data Início Vigência'].idxmax()]

    return pd.DataFrame([effective_scale])

def calculate_metrics(df_real_status, df_escala_history, selected_agents, start_date, end_date):
    metrics_data = []

    # Converter start_date e end_date para Timestamp para comparação consistente
    start_timestamp = pd.Timestamp(start_date)
    end_timestamp = pd.Timestamp(end_date)

    # Filtrar df_real_status para o período e agentes selecionados
    df_real_status_filtered = df_real_status[
        (df_real_status['Nome do agente'].isin(selected_agents)) &
        (df_real_status['Hora de início do estado - Carimbo de data/hora'] >= start_timestamp) &
        (df_real_status['Hora de início do estado - Carimbo de data/hora'] <= end_timestamp.replace(hour=23, minute=59, second=59))
    ].copy()

    if df_real_status_filtered.empty:
        return pd.DataFrame()

    for agent in selected_agents:
        current_date = start_date
        while current_date <= end_date:
            effective_scale_df = get_effective_scale_for_day(df_escala_history, agent, current_date)

            if not effective_scale_df.empty:
                scale_entry_time = effective_scale_df['Entrada'].iloc[0]
                scale_exit_time = effective_scale_df['Saída'].iloc[0]

                # Criar objetos datetime para o início e fim da escala no dia atual
                scale_start_dt = datetime.combine(current_date, scale_entry_time)
                scale_end_dt = datetime.combine(current_date, scale_exit_time)

                # Ajustar para escalas que terminam no dia seguinte (ex: 22:00 - 06:00)
                if scale_end_dt < scale_start_dt:
                    scale_end_dt += timedelta(days=1)

                # Filtrar status real para o agente e o dia atual
                agent_status_for_day = df_real_status_filtered[
                    (df_real_status_filtered['Nome do agente'] == agent) &
                    (df_real_status_filtered['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date)
                ].copy()

                total_available_time_in_scale = timedelta(minutes=0)
                total_scheduled_time = (scale_end_dt - scale_start_dt).total_seconds() / 60 # em minutos

                if total_scheduled_time > 0:
                    for _, status_row in agent_status_for_day.iterrows():
                        status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                        status_end = status_row['Hora de término do estado - Carimbo de data/hora']
                        state = status_row['Estado']

                        # Intersecção do status com a escala
                        overlap_start = max(scale_start_dt, status_start)
                        overlap_end = min(scale_end_dt, status_end)

                        if overlap_end > overlap_start:
                            overlap_duration = (overlap_end - overlap_start).total_seconds() / 60 # em minutos

                            # Considerar 'online' como disponível. Ajuste conforme seus estados de disponibilidade.
                            if state == 'Unified online':
                                total_available_time_in_scale += timedelta(minutes=overlap_duration)

                    availability_percentage = (total_available_time_in_scale.total_seconds() / 60 / total_scheduled_time) * 100
                else:
                    availability_percentage = 0 # Nenhuma escala definida para o dia

                metrics_data.append({
                    'Agente': agent,
                    'Data': current_date.strftime('%Y-%m-%d'),
                    'Escala (Início)': scale_entry_time.strftime('%H:%M'),
                    'Escala (Fim)': scale_exit_time.strftime('%H:%M'),
                    'Tempo Escala (min)': round(total_scheduled_time, 2),
                    'Tempo Disponível na Escala (min)': round(total_available_time_in_scale.total_seconds() / 60, 2),
                    'Disponibilidade (%)': round(availability_percentage, 2)
                })
            else:
                metrics_data.append({
                    'Agente': agent,
                    'Data': current_date.strftime('%Y-%m-%d'),
                    'Escala (Início)': 'N/A',
                    'Escala (Fim)': 'N/A',
                    'Tempo Escala (min)': 0,
                    'Tempo Disponível na Escala (min)': 0,
                    'Disponibilidade (%)': 0
                })
            current_date += timedelta(days=1)

    return pd.DataFrame(metrics_data)

# --- Inicialização do Streamlit ---
st.set_page_config(layout="wide", page_title="Análise de Escala e Status de Agentes")
st.title("Análise de Escala e Status de Agentes")

# --- Inicialização do Session State ---
if 'df_real_status_history' not in st.session_state:
    st.session_state.df_real_status_history, st.session_state.df_escala_history = load_history_dataframes()

# A lista de agentes para seleção deve vir APENAS do df_escala_history
if 'df_escala_history' in st.session_state and not st.session_state.df_escala_history.empty:
    st.session_state.all_unique_agents = sorted(st.session_state.df_escala_history['Nome do agente'].unique())
else:
    st.session_state.all_unique_agents = []

# --- Abas do Aplicativo ---
tab_upload, tab_manage_scales, tab_visualization = st.tabs(["Upload de Dados", "Gerenciar Escalas", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos de Dados")

    st.subheader("Upload de Arquivo de Status Real")
    uploaded_report_file = st.file_uploader("Escolha um arquivo CSV ou Excel para o Status Real", type=["csv", "xlsx"], key="report_uploader")
    if uploaded_report_file:
        try:
            if uploaded_report_file.name.endswith('.csv'):
                df_report_raw = pd.read_csv(uploaded_report_file)
            else:
                df_report_raw = pd.read_excel(uploaded_report_file)

            df_processed_report = process_uploaded_report(df_report_raw)

            if not df_processed_report.empty:
                # Remover duplicatas antes de adicionar ao histórico
                if not st.session_state.df_real_status_history.empty:
                    combined_df = pd.concat([st.session_state.df_real_status_history, df_processed_report])
                    st.session_state.df_real_status_history = combined_df.drop_duplicates(
                        subset=['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado'],
                        keep='last'
                    ).reset_index(drop=True)
                else:
                    st.session_state.df_real_status_history = df_processed_report.drop_duplicates(
                        subset=['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado'],
                        keep='last'
                    ).reset_index(drop=True)

                st.success("Arquivo de status real processado e adicionado ao histórico!")
                save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
            else:
                st.error("O arquivo de status real processado está vazio ou com erros.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de status real. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Upload de Arquivo de Escala")
    uploaded_scale_file = st.file_uploader("Escolha um arquivo CSV ou Excel para a Escala", type=["csv", "xlsx"], key="scale_uploader")
    if uploaded_scale_file:
        st.info("Para o arquivo de escala, a data de vigência será aplicada a todas as entradas do arquivo.")
        scale_start_date = st.date_input("Data de Início da Vigência para o arquivo de escala", value=date.today(), key="scale_file_start_date")
        scale_end_date = st.date_input("Data de Fim da Vigência para o arquivo de escala (opcional)", value=None, key="scale_file_end_date")

        try:
            if uploaded_scale_file.name.endswith('.csv'):
                df_scale_raw = pd.read_csv(uploaded_scale_file)
            else:
                df_scale_raw = pd.read_excel(uploaded_scale_file)

            df_processed_scale = process_uploaded_scale(df_scale_raw, scale_start_date, scale_end_date)

            if not df_processed_scale.empty:
                # Lógica para atualizar o histórico de escalas, ajustando Data Fim Vigência de escalas antigas
                if not st.session_state.df_escala_history.empty:
                    for _, new_row in df_processed_scale.iterrows():
                        agent = new_row['Nome do agente']
                        dia_num = new_row['Dia da Semana Num']
                        new_vig_start = new_row['Data Início Vigência']

                        # Encontrar escalas existentes para o mesmo agente e dia da semana que se sobrepõem
                        # e cuja vigência termina ANTES ou no mesmo dia que a nova escala começa
                        overlapping_mask = (st.session_state.df_escala_history['Nome do agente'] == agent) & \
                                           (st.session_state.df_escala_history['Dia da Semana Num'] == dia_num) & \
                                           (st.session_state.df_escala_history['Data Início Vigência'] < new_vig_start) & \
                                           (st.session_state.df_escala_history['Data Fim Vigência'].isna() | \
                                            (st.session_state.df_escala_history['Data Fim Vigência'] >= new_vig_start))

                        # Ajustar a Data Fim Vigência das escalas antigas
                        st.session_state.df_escala_history.loc[overlapping_mask, 'Data Fim Vigência'] = new_vig_start - timedelta(days=1)

                    # Adicionar as novas escalas
                    st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, df_processed_scale]).reset_index(drop=True)
                    # Remover duplicatas (se houver, mantendo a mais recente pela Data Início Vigência)
                    st.session_state.df_escala_history.sort_values(by=['Nome do agente', 'Dia da Semana Num', 'Data Início Vigência'], ascending=True, inplace=True)
                    st.session_state.df_escala_history.drop_duplicates(
                        subset=['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência'],
                        keep='last', # Manter a entrada mais recente se houver duplicação exata
                        inplace=True
                    )
                else:
                    st.session_state.df_escala_history = df_processed_scale.copy()

                st.success("Arquivo de escala processado e adicionado ao histórico!")
                # Atualizar a lista de agentes únicos baseada APENAS na escala
                st.session_state.all_unique_agents = sorted(st.session_state.df_escala_history['Nome do agente'].unique())
                save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
            else:
                st.error("O arquivo de escala processado está vazio ou com erros.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de escala. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Gerenciamento de Histórico")
    if st.button("Limpar todo o Histórico de Dados"):
        st.session_state.df_real_status_history = pd.DataFrame()
        st.session_state.df_escala_history = pd.DataFrame()
        st.session_state.all_unique_agents = [] # Limpar também a lista de agentes
        save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
        st.success("Todo o histórico de dados foi limpo.")
        st.rerun()

with tab_manage_scales:
    st.header("Gerenciar Escalas Manuais")

    # Dropdown para selecionar agente existente ou adicionar novo
    current_agents_in_scale = sorted(st.session_state.df_escala_history['Nome do agente'].unique()) if not st.session_state.df_escala_history.empty else []
    selected_agent_for_manual_scale = st.selectbox("Selecione um agente existente ou digite um novo", 
                                                   options=["-- Novo Agente --"] + current_agents_in_scale,
                                                   key="manual_scale_agent_select")

    new_agent_name = ""
    if selected_agent_for_manual_scale == "-- Novo Agente --":
        new_agent_name = st.text_input("Nome do Novo Agente", key="new_agent_name_input")
        agent_to_manage = normalize_agent_name(new_agent_name) if new_agent_name else None
    else:
        agent_to_manage = selected_agent_for_manual_scale

    if agent_to_manage:
        st.subheader(f"Gerenciar Escala para: {agent_to_manage}")

        col1, col2 = st.columns(2)
        with col1:
            dia_semana_str = st.selectbox("Dia da Semana", list(get_dias_map().keys()), key="manual_scale_day")
            entrada_str = st.text_input("Hora de Entrada (HH:MM)", value="09:00", key="manual_scale_entry")
        with col2:
            saida_str = st.text_input("Hora de Saída (HH:MM)", value="18:00", key="manual_scale_exit")
            manual_start_date = st.date_input("Data de Início da Vigência", value=date.today(), key="manual_scale_start_date")
            manual_end_date = st.date_input("Data de Fim da Vigência (opcional)", value=None, key="manual_scale_end_date")

        if st.button("Adicionar/Atualizar Escala Manualmente"):
            try:
                entrada_time = datetime.strptime(entrada_str, '%H:%M').time()
                saida_time = datetime.strptime(saida_str, '%H:%M').time()
                dia_num = get_dias_map()[dia_semana_str]

                new_scale_entry = pd.DataFrame([{
                    'Nome do agente': agent_to_manage,
                    'Dias de Atendimento': dia_semana_str,
                    'Dia da Semana Num': dia_num,
                    'Entrada': entrada_time,
                    'Saída': saida_time,
                    'Data Início Vigência': pd.Timestamp(manual_start_date),
                    'Data Fim Vigência': pd.Timestamp(manual_end_date) if manual_end_date else pd.NaT
                }])

                # Lógica para atualizar o histórico de escalas, ajustando Data Fim Vigência de escalas antigas
                if not st.session_state.df_escala_history.empty:
                    new_vig_start = new_scale_entry['Data Início Vigência'].iloc[0]

                    overlapping_mask = (st.session_state.df_escala_history['Nome do agente'] == agent_to_manage) & \
                                       (st.session_state.df_escala_history['Dia da Semana Num'] == dia_num) & \
                                       (st.session_state.df_escala_history['Data Início Vigência'] < new_vig_start) & \
                                       (st.session_state.df_escala_history['Data Fim Vigência'].isna() | \
                                        (st.session_state.df_escala_history['Data Fim Vigência'] >= new_vig_start))

                    st.session_state.df_escala_history.loc[overlapping_mask, 'Data Fim Vigência'] = new_vig_start - timedelta(days=1)

                # Adicionar a nova escala
                st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, new_scale_entry]).reset_index(drop=True)

                # Remover duplicatas (se houver, mantendo a mais recente pela Data Início Vigência)
                st.session_state.df_escala_history.sort_values(by=['Nome do agente', 'Dia da Semana Num', 'Data Início Vigência'], ascending=True, inplace=True)
                st.session_state.df_escala_history.drop_duplicates(
                    subset=['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência'],
                    keep='last',
                    inplace=True
                )

                st.success(f"Escala para {agent_to_manage} no {dia_semana_str} adicionada/atualizada com sucesso!")
                # Atualizar a lista de agentes únicos baseada APENAS na escala
                st.session_state.all_unique_agents = sorted(st.session_state.df_escala_history['Nome do agente'].unique())
                save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
                st.rerun()
            except ValueError as ve:
                st.error(f"Erro de formato de hora: {ve}. Use o formato HH:MM.")
            except Exception as e:
                st.error(f"Erro ao adicionar/atualizar escala: {e}")

        st.subheader("Escalas Atuais para o Agente")
        if not st.session_state.df_escala_history.empty:
            agent_scales = st.session_state.df_escala_history[st.session_state.df_escala_history['Nome do agente'] == agent_to_manage].copy()
            if not agent_scales.empty:
                # Formatar as colunas de tempo para exibição
                agent_scales['Entrada'] = agent_scales['Entrada'].apply(lambda x: x.strftime('%H:%M') if x is not None else 'N/A')
                agent_scales['Saída'] = agent_scales['Saída'].apply(lambda x: x.strftime('%H:%M') if x is not None else 'N/A')
                st.dataframe(agent_scales[['Dias de Atendimento', 'Entrada', 'Saída', 'Data Início Vigência', 'Data Fim Vigência']], use_container_width=True)
            else:
                st.info(f"Nenhuma escala definida para {agent_to_manage}.")
        else:
            st.info("Nenhuma escala no histórico para gerenciar.")

with tab_visualization:
    st.header("Visualização e Métricas")

    if not st.session_state.df_escala_history.empty:
        # A lista de agentes para seleção vem APENAS dos agentes que têm escala
        available_agents_for_selection = st.session_state.all_unique_agents

        if not available_agents_for_selection:
            st.warning("Nenhum agente com escala definida no histórico. Por favor, faça o upload de um arquivo de escala ou adicione escalas manualmente.")
        else:
            selected_agents = st.multiselect(
                "Selecione os agentes para análise (apenas agentes com escala)",
                options=available_agents_for_selection,
                default=available_agents_for_selection[0] if available_agents_for_selection else []
            )

            if selected_agents:
                col1_vis, col2_vis = st.columns(2)
                with col1_vis:
                    start_date = st.date_input("Data de Início", value=date.today() - timedelta(days=7))
                with col2_vis:
                    end_date = st.date_input("Data de Fim", value=date.today())

                if start_date > end_date:
                    st.error("A data de início não pode ser posterior à data de fim.")
                else:
                    df_chart_data = pd.DataFrame()

                    # Filtrar status real para o período e agentes selecionados
                    df_real_status_filtered_for_chart = st.session_state.df_real_status_history[
                        (st.session_state.df_real_status_history['Nome do agente'].isin(selected_agents)) &
                        (st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
                        (st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
                    ].copy()

                    if not df_real_status_filtered_for_chart.empty:
                        df_real_status_filtered_for_chart['Data'] = df_real_status_filtered_for_chart['Hora de início do estado - Carimbo de data/hora'].dt.date
                        df_real_status_filtered_for_chart['Y_Axis_Label'] = df_real_status_filtered_for_chart.apply(
                            lambda row: f"{row['Nome do agente']} - {row['Data'].strftime('%Y-%m-%d')} - Status Real", axis=1
                        )
                        df_real_status_filtered_for_chart['Start'] = df_real_status_filtered_for_chart['Hora de início do estado - Carimbo de data/hora']
                        df_real_status_filtered_for_chart['Finish'] = df_real_status_filtered_for_chart['Hora de término do estado - Carimbo de data/hora']
                        df_real_status_filtered_for_chart['Tipo'] = df_real_status_filtered_for_chart['Estado']
                        df_chart_data = pd.concat([df_chart_data, df_real_status_filtered_for_chart[['Y_Axis_Label', 'Start', 'Finish', 'Tipo', 'Nome do agente', 'Data']]])

                    # Adicionar dados da escala ao gráfico
                    if pd.api.types.is_datetime64_any_dtype(st.session_state.df_escala_history['Data Início Vigência']):
                        expanded_scale_for_chart = []
                        for agent in selected_agents:
                            current_date_chart = start_date
                            while current_date_chart <= end_date:
                                effective_scale_df = get_effective_scale_for_day(st.session_state.df_escala_history, agent, current_date_chart)
                                if not effective_scale_df.empty:
                                    scale_entry_time = effective_scale_df['Entrada'].iloc[0]
                                    scale_exit_time = effective_scale_df['Saída'].iloc[0]

                                    scale_start_dt = datetime.combine(current_date_chart, scale_entry_time)
                                    scale_end_dt = datetime.combine(current_date_chart, scale_exit_time)

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
    else:
        st.info("Não há dados de escala no histórico. Por favor, faça o upload de um arquivo de escala ou adicione escalas manualmente na aba 'Gerenciar Escalas'.")
