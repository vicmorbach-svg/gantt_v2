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

    # Usar a função get_dias_map global
    dias_map = get_dias_map()
    df['Dia da Semana Num'] = df['Dias de Atendimento'].apply(
        lambda x: [dias_map[d.strip().upper()] for d in x.split(',') if d.strip().upper() in dias_map]
    )
    df = df.explode('Dia da Semana Num')
    df.dropna(subset=['Dia da Semana Num'], inplace=True)
    df['Dia da Semana Num'] = df['Dia da Semana Num'].astype(int)

    # Adicionar as datas de vigência como pd.Timestamp
    df['Data Início Vigência'] = pd.to_datetime(start_effective_date).normalize() # Garante que seja meia-noite
    if end_effective_date:
        df['Data Fim Vigência'] = pd.to_datetime(end_effective_date).normalize()
    else:
        df['Data Fim Vigência'] = pd.NaT # Usar NaT para vigência indefinida

    return df

def get_effective_scale_for_day(agent_name, current_date, df_escala_history):
    if df_escala_history.empty:
        return pd.DataFrame()

    # Converter current_date para pd.Timestamp para comparação consistente
    current_timestamp = pd.to_datetime(current_date).normalize()

    # Filtrar escalas para o agente e dia da semana
    filtered_by_agent_day = df_escala_history[
        (df_escala_history['Nome do agente'] == agent_name) &
        (df_escala_history['Dia da Semana Num'] == current_date.weekday())
    ]

    if filtered_by_agent_day.empty:
        return pd.DataFrame()

    # Filtrar por vigência: current_date deve estar entre Data Início Vigência e Data Fim Vigência
    # Data Fim Vigência pode ser NaT (indefinida)
    effective_scales = filtered_by_agent_day[
        (filtered_by_agent_day['Data Início Vigência'] <= current_timestamp) &
        (
            (filtered_by_agent_day['Data Fim Vigência'].isna()) |
            (filtered_by_agent_day['Data Fim Vigência'] >= current_timestamp)
        )
    ]

    if effective_scales.empty:
        return pd.DataFrame()

    # Se houver múltiplas escalas válidas para o mesmo dia, pegar a mais recente (pela Data Início Vigência)
    # Isso é importante se uma escala foi "substituída" mas a anterior ainda está no histórico
    if len(effective_scales) > 1:
        effective_scales = effective_scales.sort_values(by='Data Início Vigência', ascending=False).drop_duplicates(subset=['Nome do agente', 'Dia da Semana Num'], keep='first')

    return effective_scales

def calculate_metrics(df_real_status, df_escala_history, selected_agents, start_date, end_date):
    metrics_data = []
    date_range = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]

    for agent in selected_agents:
        total_scheduled_time_minutes = 0
        total_online_time_minutes = 0

        for current_date in date_range:
            # Obter a escala efetiva para o agente e o dia atual
            effective_scale = get_effective_scale_for_day(agent, current_date, df_escala_history)

            if not effective_scale.empty:
                for _, scale_row in effective_scale.iterrows():
                    scale_start_time = scale_row['Entrada']
                    scale_end_time = scale_row['Saída']

                    scale_start_dt = datetime.combine(current_date, scale_start_time)
                    scale_end_dt = datetime.combine(current_date, scale_end_time)

                    if scale_end_dt < scale_start_dt: # Escala que vira o dia
                        scale_end_dt += timedelta(days=1)

                    scheduled_duration = (scale_end_dt - scale_start_dt).total_seconds() / 60
                    total_scheduled_time_minutes += scheduled_duration

            # Filtrar status real para o agente e o dia atual
            agent_daily_status = df_real_status[
                (df_real_status['Nome do agente'] == agent) &
                (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date)
            ].copy()

            if not agent_daily_status.empty:
                # Calcular tempo online dentro do dia da escala
                # Consideramos 'Unified online' como o status de disponibilidade
                online_status_df = agent_daily_status[agent_daily_status['Estado'] == 'Unified online']

                for _, status_row in online_status_df.iterrows():
                    status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                    status_end = status_row['Hora de término do estado - Carimbo de data/hora']

                    # Interseção com o dia atual (para garantir que não conte tempo de outro dia)
                    day_start = datetime.combine(current_date, time.min)
                    day_end = datetime.combine(current_date, time.max)

                    # Ajustar status_start e status_end para ficarem dentro do dia
                    actual_start = max(status_start, day_start)
                    actual_end = min(status_end, day_end)

                    if actual_end > actual_start:
                        online_duration = (actual_end - actual_start).total_seconds() / 60
                        total_online_time_minutes += online_duration

        availability_percentage = (total_online_time_minutes / total_scheduled_time_minutes * 100) if total_scheduled_time_minutes > 0 else 0

        metrics_data.append({
            'Agente': agent,
            'Tempo Online (min)': round(total_online_time_minutes, 2),
            'Tempo Escala (min)': round(total_scheduled_time_minutes, 2),
            'Disponibilidade (%)': round(availability_percentage, 2)
        })

    return pd.DataFrame(metrics_data)


# --- Configuração do Streamlit ---
st.set_page_config(layout="wide", page_title="Análise de Produtividade de Agentes")
st.title("Análise de Produtividade de Agentes")

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
        'Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída', 'Carga',
        'Dia da Semana Num', 'Data Início Vigência', 'Data Fim Vigência'
    ]).astype({
        'Data Início Vigência': 'datetime64[ns]',
        'Data Fim Vigência': 'datetime64[ns]'
    })

# Abas
tab_upload, tab_manage_scales, tab_visualization = st.tabs(["Upload de Dados", "Gerenciar Escalas", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos")

    st.subheader("Upload de Relatório de Status Real")
    uploaded_report_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) para o Relatório de Status Real", type=["xlsx"], key="report_uploader")
    if uploaded_report_file:
        try:
            df_report_raw = pd.read_excel(uploaded_report_file)
            df_processed_report = process_uploaded_report(df_report_raw)

            if not df_processed_report.empty:
                # Remover duplicatas antes de adicionar ao histórico
                # Considera que um registro é duplicado se agente, início, fim e estado são os mesmos
                df_processed_report_unique = df_processed_report.drop_duplicates(
                    subset=['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora', 'Estado']
                )

                # Concatena e remove duplicatas novamente para garantir que não haja duplicatas entre o histórico e os novos dados
                st.session_state.df_real_status_history = pd.concat([st.session_state.df_real_status_history, df_processed_report_unique], ignore_index=True)
                st.session_state.df_real_status_history.drop_duplicates(
                    subset=['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora', 'Estado'],
                    inplace=True
                )
                st.session_state.df_real_status_history = st.session_state.df_real_status_history.reset_index(drop=True)

                st.success("Relatório de Status Real processado e adicionado ao histórico com sucesso!")
                st.dataframe(df_processed_report_unique.head())
            else:
                st.error("O arquivo de status real está vazio ou não pôde ser processado.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de status real. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Upload de Arquivo de Escala")
    uploaded_scale_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) para a Escala", type=["xlsx"], key="scale_uploader")
    if uploaded_scale_file:
        st.info("Para o arquivo de escala, a data de vigência será a data atual por padrão. Você pode ajustá-la na aba 'Gerenciar Escalas'.")
        default_start_date = date.today()
        default_end_date = None # Vigência indefinida por padrão

        try:
            df_scale_raw = pd.read_excel(uploaded_scale_file)
            df_processed_scale = process_uploaded_scale(df_scale_raw, default_start_date, default_end_date)

            if not df_processed_scale.empty:
                # Lógica para atualizar o histórico de escalas com a nova vigência
                for _, new_row in df_processed_scale.iterrows():
                    agent = new_row['Nome do agente']
                    dia_num = new_row['Dia da Semana Num']
                    new_start_vigencia = new_row['Data Início Vigência']
                    new_end_vigencia = new_row['Data Fim Vigência']

                    # Encontrar escalas existentes para o mesmo agente e dia da semana que se sobrepõem
                    # ou são anteriores e ainda ativas na data de início da nova escala
                    overlapping_scales_mask = (
                        (st.session_state.df_escala_history['Nome do agente'] == agent) &
                        (st.session_state.df_escala_history['Dia da Semana Num'] == dia_num) &
                        (st.session_state.df_escala_history['Data Início Vigência'] < new_start_vigencia) &
                        (
                            (st.session_state.df_escala_history['Data Fim Vigência'].isna()) |
                            (st.session_state.df_escala_history['Data Fim Vigência'] >= new_start_vigencia)
                        )
                    )

                    # Ajustar a Data Fim Vigência das escalas antigas
                    st.session_state.df_escala_history.loc[overlapping_scales_mask, 'Data Fim Vigência'] = new_start_vigencia - timedelta(days=1)

                # Adicionar as novas escalas ao histórico
                st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, df_processed_scale], ignore_index=True)
                # Remover duplicatas exatas (se uma linha idêntica foi carregada novamente)
                st.session_state.df_escala_history.drop_duplicates(inplace=True)
                st.session_state.df_escala_history = st.session_state.df_escala_history.reset_index(drop=True)

                st.success("Arquivo de Escala processado e adicionado ao histórico com sucesso!")
                st.dataframe(df_processed_scale.head())
            else:
                st.error("O arquivo de escala está vazio ou não pôde ser processado.")
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
            'Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída', 'Carga',
            'Dia da Semana Num', 'Data Início Vigência', 'Data Fim Vigência'
        ]).astype({
            'Data Início Vigência': 'datetime64[ns]',
            'Data Fim Vigência': 'datetime64[ns]'
        })
        st.success("Histórico de dados limpo com sucesso!")

with tab_manage_scales:
    st.header("Gerenciar Escalas Manuais")

    if st.session_state.df_escala_history.empty:
        st.info("Nenhuma escala carregada ainda. Faça o upload na aba 'Upload de Dados' ou adicione manualmente abaixo.")
        all_agents_from_history = []
    else:
        all_agents_from_history = sorted(st.session_state.df_escala_history['Nome do agente'].unique())

    with st.form("form_add_scale"):
        st.subheader("Adicionar/Atualizar Escala Manualmente")

        # Usar agentes existentes ou permitir novo
        new_agent_name = st.text_input("Nome do Agente", key="manual_agent_name").strip().upper()
        if not new_agent_name and all_agents_from_history:
            new_agent_name = st.selectbox("Ou selecione um agente existente", options=[""] + all_agents_from_history, key="select_existing_agent")

        new_day_of_week_name = st.selectbox("Dia da Semana", options=[""] + list(get_dias_map().keys()), key="manual_day_name")
        new_entry_time = st.time_input("Hora de Entrada", value=time(9, 0), key="manual_entry_time")
        new_exit_time = st.time_input("Hora de Saída", value=time(18, 0), key="manual_exit_time")
        new_start_date = st.date_input("Data de Início da Vigência", value=date.today(), key="manual_start_date")
        new_end_date = st.date_input("Data de Fim da Vigência (opcional)", value=None, key="manual_end_date")

        submitted = st.form_submit_button("Adicionar/Atualizar Escala")
        if submitted:
            if not new_agent_name or not new_day_of_week_name:
                st.error("Por favor, preencha o nome do agente e o dia da semana.")
            else:
                dias_map = get_dias_map()
                new_day_of_week_num = dias_map.get(new_day_of_week_name)
                if new_day_of_week_num is None:
                    st.error("Dia da semana inválido.")
                else:
                    new_scale_data = {
                        'Nome do agente': normalize_agent_name(new_agent_name),
                        'Dias de Atendimento': new_day_of_week_name, # Manter o nome para exibição
                        'Entrada': new_entry_time,
                        'Saída': new_exit_time,
                        'Carga': (datetime.combine(date.min, new_exit_time) - datetime.combine(date.min, new_entry_time)).total_seconds() / 3600,
                        'Dia da Semana Num': new_day_of_week_num,
                        'Data Início Vigência': pd.to_datetime(new_start_date).normalize(),
                        'Data Fim Vigência': pd.to_datetime(new_end_date).normalize() if new_end_date else pd.NaT
                    }
                    new_scale_df = pd.DataFrame([new_scale_data])

                    # Lógica para atualizar o histórico de escalas com a nova vigência
                    agent = new_scale_df.iloc[0]['Nome do agente']
                    dia_num = new_scale_df.iloc[0]['Dia da Semana Num']
                    new_start_vigencia = new_scale_df.iloc[0]['Data Início Vigência']
                    new_end_vigencia = new_scale_df.iloc[0]['Data Fim Vigência']

                    # Encontrar escalas existentes para o mesmo agente e dia da semana que se sobrepõem
                    # ou são anteriores e ainda ativas na data de início da nova escala
                    overlapping_scales_mask = (
                        (st.session_state.df_escala_history['Nome do agente'] == agent) &
                        (st.session_state.df_escala_history['Dia da Semana Num'] == dia_num) &
                        (st.session_state.df_escala_history['Data Início Vigência'] < new_start_vigencia) &
                        (
                            (st.session_state.df_escala_history['Data Fim Vigência'].isna()) |
                            (st.session_state.df_escala_history['Data Fim Vigência'] >= new_start_vigencia)
                        )
                    )

                    # Ajustar a Data Fim Vigência das escalas antigas
                    st.session_state.df_escala_history.loc[overlapping_scales_mask, 'Data Fim Vigência'] = new_start_vigencia - timedelta(days=1)

                    # Adicionar a nova escala ao histórico
                    st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, new_scale_df], ignore_index=True)
                    st.session_state.df_escala_history.drop_duplicates(inplace=True)
                    st.session_state.df_escala_history = st.session_state.df_escala_history.reset_index(drop=True)

                    st.success(f"Escala para {new_agent_name} em {new_day_of_week_name} adicionada/atualizada com sucesso!")
                    st.dataframe(st.session_state.df_escala_history)

    st.subheader("Escalas Atuais no Histórico")
    if not st.session_state.df_escala_history.empty:
        st.dataframe(st.session_state.df_escala_history.sort_values(by=['Nome do agente', 'Dia da Semana Num', 'Data Início Vigência']))
    else:
        st.info("Nenhuma escala no histórico.")

with tab_visualization:
    st.header("Visualização e Métricas")

    all_unique_agents = []
    if not st.session_state.df_escala_history.empty:
        all_unique_agents = sorted(st.session_state.df_escala_history['Nome do agente'].unique())

    selected_agents = st.multiselect("Selecione os Agentes para Análise", options=all_unique_agents)

    min_date_data = date.today()
    max_date_data = date.today()

    if not st.session_state.df_real_status_history.empty and 'Hora de início do estado - Carimbo de data/hora' in st.session_state.df_real_status_history.columns:
        if pd.api.types.is_datetime64_any_dtype(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora']):
            min_date_data = min(min_date_data, st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].min().date())
            max_date_data = max(max_date_data, st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].max().date())
        else:
            st.warning("Coluna 'Hora de início do estado - Carimbo de data/hora' no histórico de status real não é do tipo datetime. Ajuste as datas manualmente ou verifique o processamento.")

    if not st.session_state.df_escala_history.empty and 'Data Início Vigência' in st.session_state.df_escala_history.columns:
        if pd.api.types.is_datetime64_any_dtype(st.session_state.df_escala_history['Data Início Vigência']):
            min_date_data = min(min_date_data, st.session_state.df_escala_history['Data Início Vigência'].min().date())
        else:
            st.warning("Coluna 'Data Início Vigência' não é do tipo datetime. Verifique o arquivo de escala.")


    start_date = st.date_input("Data de Início", value=min_date_data, min_value=min_date_data, max_value=max_date_data)
    end_date = st.date_input("Data de Fim", value=max_date_data, min_value=min_date_data, max_value=max_date_data)

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
