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

    df['Hora de término do estado - Carimbo de data/hora'] = df.apply(
        lambda row: row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
        if pd.isna(row['Hora de término do estado - Carimbo de data/hora']) and pd.notna(row['Hora de início do estado - Carimbo de data/hora'])
        else row['Hora de término do estado - Carimbo de data/hora'],
        axis=1
    )

    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'], inplace=True)

    # Forçar o dtype para datetime64[ns] após todas as operações
    df['Hora de início do estado - Carimbo de data/hora'] = df['Hora de início do estado - Carimbo de data/hora'].astype('datetime64[ns]')
    df['Hora de término do estado - Carimbo de data/hora'] = df['Hora de término do estado - Carimbo de data/hora'].astype('datetime64[ns]')

    return df

def process_uploaded_scale(df_scale_raw, start_effective_date, end_effective_date):
    df = df_scale_raw.copy()

    expected_columns_scale = {
        'Nome do agente': 'Nome do agente',
        'Dias de Atendimento': 'Dias de Atendimento',
        'Entrada': 'Entrada',
        'Saída': 'Saída'
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
    if not all(col in df.columns for col in required_cols):
        missing_cols = [col for col in required_cols if col not in df.columns]
        st.error(f"Colunas obrigatórias não encontradas no arquivo de escala após renomear: {', '.join(missing_cols)}. Verifique o cabeçalho do arquivo.")
        return pd.DataFrame()

    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)
    df['Dias de Atendimento'] = df['Dias de Atendimento'].astype(str).str.upper().str.strip()

    # Converter Entrada e Saída para objetos time
    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    df.dropna(subset=['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída'], inplace=True)

    # Expandir dias de atendimento para Dia da Semana Num
    df_expanded = []
    dias_map = get_dias_map()
    for _, row in df.iterrows():
        dias_atendimento = row['Dias de Atendimento'].split(',')
        for dia_str in dias_atendimento:
            dia_str_normalized = normalize_column_name(dia_str) # Reutiliza a normalização para o dia da semana
            if dia_str_normalized in dias_map:
                df_expanded.append({
                    'Nome do agente': row['Nome do agente'],
                    'Dias de Atendimento': dia_str, # Manter o original para exibição se necessário
                    'Dia da Semana Num': dias_map[dia_str_normalized],
                    'Entrada': row['Entrada'],
                    'Saída': row['Saída'],
                    'Data Início Vigência': pd.Timestamp(start_effective_date),
                    'Data Fim Vigência': pd.Timestamp(end_effective_date) if end_effective_date else pd.NaT
                })
            else:
                st.warning(f"Dia da semana '{dia_str}' para o agente '{row['Nome do agente']}' não reconhecido e foi ignorado.")

    df_processed_scale = pd.DataFrame(df_expanded)
    return df_processed_scale

# --- Funções de Lógica de Escala ---
def get_effective_scale_for_day(agent_name, current_date, df_escala_history):
    if df_escala_history.empty:
        return pd.DataFrame()

    # Converter current_date para Timestamp para comparação consistente
    current_date_ts = pd.Timestamp(current_date)

    # Filtrar escalas para o agente e dia da semana
    filtered_by_agent_day = df_escala_history[
        (df_escala_history['Nome do agente'] == agent_name) &
        (df_escala_history['Dia da Semana Num'] == current_date.weekday())
    ].copy() # Usar .copy() para evitar SettingWithCopyWarning

    if filtered_by_agent_day.empty:
        return pd.DataFrame()

    # Filtrar por vigência: Data Início Vigência <= current_date E (Data Fim Vigência é NaT OU Data Fim Vigência >= current_date)
    # Usar .dt.date para comparar apenas a parte da data
    effective_scales = filtered_by_agent_day[
        (filtered_by_agent_day['Data Início Vigência'].dt.date <= current_date_ts.date()) &
        (
            filtered_by_agent_day['Data Fim Vigência'].isna() |
            (filtered_by_agent_day['Data Fim Vigência'].dt.date >= current_date_ts.date())
        )
    ]

    if effective_scales.empty:
        return pd.DataFrame()

    # Se houver múltiplas escalas válidas, pegar a mais recente (com Data Início Vigência mais próxima de current_date)
    # Ordenar por Data Início Vigência em ordem decrescente e pegar a primeira
    effective_scales = effective_scales.sort_values(by='Data Início Vigência', ascending=False)

    # Retornar todas as entradas para o dia mais recente, caso haja múltiplas entradas (ex: turnos divididos)
    # Isso assume que se há múltiplas entradas para o mesmo dia e mesma data de vigência, todas são válidas.
    most_recent_vigencia_date = effective_scales['Data Início Vigência'].iloc[0]
    final_effective_scales = effective_scales[effective_scales['Data Início Vigência'] == most_recent_vigencia_date]

    return final_effective_scales

# --- Funções de Cálculo de Métricas ---
def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    metrics_data = []

    # Filtrar df_real_status e df_escala para o período e agentes selecionados
    df_real_status_filtered = df_real_status[
        (df_real_status['Nome do agente'].isin(selected_agents)) &
        (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
        (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
    ].copy()

    for agent in selected_agents:
        current_date = start_date
        while current_date <= end_date:
            # Obter a escala vigente para o agente no dia atual
            daily_escala = get_effective_scale_for_day(agent, current_date, df_escala)

            if not daily_escala.empty:
                total_planned_minutes = 0
                for _, scale_row in daily_escala.iterrows():
                    start_time = scale_row['Entrada']
                    end_time = scale_row['Saída']

                    # Criar objetos datetime para o dia atual
                    planned_start_dt = datetime.combine(current_date, start_time)
                    planned_end_dt = datetime.combine(current_date, end_time)

                    # Lidar com turnos que viram a noite
                    if planned_end_dt < planned_start_dt:
                        planned_end_dt += timedelta(days=1)

                    # Limitar a duração ao dia atual (até 23:59:59)
                    day_end_limit = datetime.combine(current_date, time.max)
                    planned_end_dt_limited = min(planned_end_dt, day_end_limit)

                    if planned_end_dt_limited > planned_start_dt:
                        total_planned_minutes += (planned_end_dt_limited - planned_start_dt).total_seconds() / 60

                # Calcular tempo real em status "online" para o agente no dia
                agent_daily_status = df_real_status_filtered[
                    (df_real_status_filtered['Nome do agente'] == agent) &
                    (df_real_status_filtered['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date)
                ]

                total_online_minutes = 0
                for _, status_row in agent_daily_status.iterrows():
                    if status_row['Estado'] == 'Unified online':
                        status_start_dt = status_row['Hora de início do estado - Carimbo de data/hora']
                        status_end_dt = status_row['Hora de término do estado - Carimbo de data/hora']

                        # Limitar o status ao dia atual
                        day_start_dt = datetime.combine(current_date, time.min)
                        day_end_dt = datetime.combine(current_date, time.max)

                        # Interseção do status com o dia atual
                        effective_start = max(status_start_dt, day_start_dt)
                        effective_end = min(status_end_dt, day_end_dt)

                        if effective_end > effective_start:
                            total_online_minutes += (effective_end - effective_start).total_seconds() / 60

                availability_percentage = (total_online_minutes / total_planned_minutes * 100) if total_planned_minutes > 0 else 0

                metrics_data.append({
                    'Agente': agent,
                    'Data': current_date.strftime('%Y-%m-%d'),
                    'Tempo Planejado (min)': round(total_planned_minutes, 2),
                    'Tempo Online (min)': round(total_online_minutes, 2),
                    'Disponibilidade (%)': round(availability_percentage, 2)
                })

            current_date += timedelta(days=1)

    return pd.DataFrame(metrics_data)

# --- Inicialização do Streamlit ---
st.set_page_config(layout="wide")
st.title("Análise de Produtividade de Agentes")

# Inicializar DataFrames de histórico na session_state se não existirem
if 'df_real_status_history' not in st.session_state:
    st.session_state.df_real_status_history, st.session_state.df_escala_history = load_history_dataframes()

# --- Abas ---
tab_upload, tab_manage_scales, tab_visualization = st.tabs(["Upload de Dados", "Gerenciar Escalas", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos de Dados")

    st.subheader("Upload de Relatório de Status Real")
    uploaded_report_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) ou CSV para o Relatório de Status Real", type=["xlsx", "csv"], key="report_uploader")
    if uploaded_report_file:
        try:
            if uploaded_report_file.name.endswith('.csv'):
                df_report_raw = pd.read_csv(uploaded_report_file)
            else:
                df_report_raw = pd.read_excel(uploaded_report_file)

            df_processed_report = process_uploaded_report(df_report_raw)

            if not df_processed_report.empty:
                # Anexar ao histórico, evitando duplicatas
                if not st.session_state.df_real_status_history.empty:
                    combined_df = pd.concat([st.session_state.df_real_status_history, df_processed_report])
                    # Remover duplicatas com base em colunas chave
                    st.session_state.df_real_status_history = combined_df.drop_duplicates(
                        subset=['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado'],
                        keep='last'
                    ).reset_index(drop=True)
                else:
                    st.session_state.df_real_status_history = df_processed_report

                save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
                st.success("Relatório de Status Real processado e adicionado ao histórico.")
                st.dataframe(st.session_state.df_real_status_history.head(), use_container_width=True)
            else:
                st.error("O arquivo de relatório de status real está vazio ou não pôde ser processado.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de relatório de status real. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Upload de Arquivo de Escala")
    uploaded_scale_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) ou CSV para a Escala", type=["xlsx", "csv"], key="scale_uploader")

    if uploaded_scale_file:
        st.info("Para o arquivo de escala, você precisa definir o período de vigência.")
        new_start_effective_date = st.date_input("Data de Início da Vigência para esta escala", value=date.today(), key="scale_start_date_input")
        new_end_effective_date = st.date_input("Data de Fim da Vigência para esta escala (opcional)", value=None, key="scale_end_date_input")

        if st.button("Processar e Adicionar Escala", key="add_scale_button"):
            try:
                if uploaded_scale_file.name.endswith('.csv'):
                    df_scale_raw = pd.read_csv(uploaded_scale_file)
                else:
                    df_scale_raw = pd.read_excel(uploaded_scale_file)

                df_processed_scale = process_uploaded_scale(df_scale_raw, new_start_effective_date, new_end_effective_date)

                if not df_processed_scale.empty:
                    # Lógica para gerenciar sobreposição de escalas
                    if not st.session_state.df_escala_history.empty:
                        # Identificar escalas existentes que são substituídas ou sobrepostas
                        # Para cada nova entrada de escala, ajustar a Data Fim Vigência das escalas antigas
                        for _, new_row in df_processed_scale.iterrows():
                            agent = new_row['Nome do agente']
                            dia_num = new_row['Dia da Semana Num']
                            new_start_ts = new_row['Data Início Vigência']

                            # Encontrar escalas antigas para o mesmo agente/dia que terminam antes da nova escala começar
                            # ou que se sobrepõem e precisam ser encerradas
                            overlapping_old_scales_mask = (
                                (st.session_state.df_escala_history['Nome do agente'] == agent) &
                                (st.session_state.df_escala_history['Dia da Semana Num'] == dia_num) &
                                (st.session_state.df_escala_history['Data Início Vigência'].dt.date < new_start_ts.date()) &
                                (
                                    st.session_state.df_escala_history['Data Fim Vigência'].isna() |
                                    (st.session_state.df_escala_history['Data Fim Vigência'].dt.date >= new_start_ts.date())
                                )
                            )

                            # Ajustar a Data Fim Vigência das escalas antigas para o dia anterior à nova escala
                            st.session_state.df_escala_history.loc[overlapping_old_scales_mask, 'Data Fim Vigência'] = new_start_ts - timedelta(days=1)

                        # Concatenar a nova escala
                        st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, df_processed_scale], ignore_index=True)
                        # Remover duplicatas exatas (se houver)
                        st.session_state.df_escala_history.drop_duplicates(inplace=True)
                    else:
                        st.session_state.df_escala_history = df_processed_scale

                    save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
                    st.success("Escala processada e adicionada ao histórico.")
                    st.dataframe(st.session_state.df_escala_history.head(), use_container_width=True)
                else:
                    st.error("O arquivo de escala está vazio ou não pôde ser processado.")
            except Exception as e:
                st.error(f"Erro ao processar o arquivo de escala. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Limpar Histórico de Dados")
    st.warning("Esta ação removerá todos os dados de histórico de status real e escalas salvas. Use com cautela.")
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
            'Entrada': object, # time objects
            'Saída': object,   # time objects
            'Data Início Vigência': 'datetime64[ns]',
            'Data Fim Vigência': 'datetime64[ns]'
        })
        save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
        st.success("Histórico de dados limpo com sucesso!")

with tab_manage_scales:
    st.header("Gerenciar Escalas Manuais")

    if st.session_state.df_escala_history.empty:
        st.info("Nenhuma escala carregada ainda. Faça o upload na aba 'Upload de Dados' ou adicione manualmente abaixo.")
    else:
        st.subheader("Escalas Atuais no Histórico")
        st.dataframe(st.session_state.df_escala_history, use_container_width=True)

    st.subheader("Adicionar/Atualizar Escala Manualmente")

    with st.form("add_manual_scale_form"):
        agent_name_manual = st.text_input("Nome do Agente", key="agent_name_manual").strip().upper()
        dias_atendimento_manual = st.multiselect(
            "Dias de Atendimento",
            options=['SEGUNDA', 'TERÇA', 'QUARTA', 'QUINTA', 'SEXTA', 'SÁBADO', 'DOMINGO'],
            key="dias_atendimento_manual"
        )
        entrada_manual = st.time_input("Hora de Entrada", value=time(9, 0), key="entrada_manual")
        saida_manual = st.time_input("Hora de Saída", value=time(17, 0), key="saida_manual")
        data_inicio_vigencia_manual = st.date_input("Data de Início da Vigência", value=date.today(), key="data_inicio_vigencia_manual")
        data_fim_vigencia_manual = st.date_input("Data de Fim da Vigência (opcional)", value=None, key="data_fim_vigencia_manual")

        submitted = st.form_submit_button("Adicionar/Atualizar Escala")

        if submitted:
            if not agent_name_manual or not dias_atendimento_manual:
                st.error("Por favor, preencha o nome do agente e selecione pelo menos um dia de atendimento.")
            else:
                new_scale_entries = []
                dias_map = get_dias_map()
                for dia_str in dias_atendimento_manual:
                    dia_str_normalized = normalize_column_name(dia_str)
                    if dia_str_normalized in dias_map:
                        new_scale_entries.append({
                            'Nome do agente': normalize_agent_name(agent_name_manual),
                            'Dias de Atendimento': dia_str,
                            'Dia da Semana Num': dias_map[dia_str_normalized],
                            'Entrada': entrada_manual,
                            'Saída': saida_manual,
                            'Data Início Vigência': pd.Timestamp(data_inicio_vigencia_manual),
                            'Data Fim Vigência': pd.Timestamp(data_fim_vigencia_manual) if data_fim_vigencia_manual else pd.NaT
                        })
                    else:
                        st.warning(f"Dia da semana '{dia_str}' não reconhecido e foi ignorado.")

                if new_scale_entries:
                    df_new_manual_scale = pd.DataFrame(new_scale_entries)

                    if not st.session_state.df_escala_history.empty:
                        # Lógica de sobreposição para escalas manuais
                        for _, new_row in df_new_manual_scale.iterrows():
                            agent = new_row['Nome do agente']
                            dia_num = new_row['Dia da Semana Num']
                            new_start_ts = new_row['Data Início Vigência']

                            overlapping_old_scales_mask = (
                                (st.session_state.df_escala_history['Nome do agente'] == agent) &
                                (st.session_state.df_escala_history['Dia da Semana Num'] == dia_num) &
                                (st.session_state.df_escala_history['Data Início Vigência'].dt.date < new_start_ts.date()) &
                                (
                                    st.session_state.df_escala_history['Data Fim Vigência'].isna() |
                                    (st.session_state.df_escala_history['Data Fim Vigência'].dt.date >= new_start_ts.date())
                                )
                            )
                            st.session_state.df_escala_history.loc[overlapping_old_scales_mask, 'Data Fim Vigência'] = new_start_ts - timedelta(days=1)

                        st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, df_new_manual_scale], ignore_index=True)
                        st.session_state.df_escala_history.drop_duplicates(inplace=True)
                    else:
                        st.session_state.df_escala_history = df_new_manual_scale

                    save_history_dataframes(st.session_state.df_real_status_history, st.session_state.df_escala_history)
                    st.success("Escala manual adicionada/atualizada com sucesso!")
                    st.dataframe(st.session_state.df_escala_history.head(), use_container_width=True)
                else:
                    st.error("Nenhuma entrada de escala válida foi gerada.")

with tab_visualization:
    st.header("Visualização da Linha do Tempo e Métricas")

    if not st.session_state.df_escala_history.empty:
        all_unique_agents_from_scale = sorted(st.session_state.df_escala_history['Nome do agente'].unique())
        selected_agents = st.multiselect(
            "Selecione os Agentes para Análise (apenas da escala)",
            options=all_unique_agents_from_scale,
            default=all_unique_agents_from_scale if all_unique_agents_from_scale else []
        )
    else:
        st.info("Faça o upload de um arquivo de escala para ver os agentes disponíveis.")
        selected_agents = []

    if selected_agents:
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Data de Início", value=date.today() - timedelta(days=7))
        with col2:
            end_date = st.date_input("Data de Fim", value=date.today())

        if st.button("Gerar Gráfico e Métricas"):
            df_chart_data = pd.DataFrame(columns=['Y_Axis_Label', 'Start', 'Finish', 'Tipo', 'Nome do agente', 'Data'])

            # Adicionar dados de status real
            if not st.session_state.df_real_status_history.empty and 'Hora de início do estado - Carimbo de data/hora' in st.session_state.df_real_status_history.columns:
                if pd.api.types.is_datetime64_any_dtype(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora']):
                    df_real_status_filtered_chart = st.session_state.df_real_status_history[
                        (st.session_state.df_real_status_history['Nome do agente'].isin(selected_agents)) &
                        (st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
                        (st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
                    ].copy()
                    df_real_status_filtered_chart['Start'] = df_real_status_filtered_chart['Hora de início do estado - Carimbo de data/hora']
                    df_real_status_filtered_chart['Finish'] = df_real_status_filtered_chart['Hora de término do estado - Carimbo de data/hora']
                    df_real_status_filtered_chart['Tipo'] = 'Status Real'
                    df_real_status_filtered_chart['Data'] = df_real_status_filtered_chart['Hora de início do estado - Carimbo de data/hora'].dt.date
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
                    dates_for_agent = sorted(df_chart_data[df_chart_data['Nome do agente'] == agent]['Data'].unique())
                    for date_obj in dates_for_agent:
                        date_str = date_obj.strftime('%Y-%m-%d')
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
