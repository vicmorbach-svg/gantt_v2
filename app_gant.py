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
                    'Data Início Vigência': pd.Timestamp(start_effective_date),
                    'Data Fim Vigência': pd.Timestamp(end_effective_date) if end_effective_date else pd.NaT
                })
            else:
                st.warning(f"Dia da semana '{dia_abbr}' não reconhecido para o agente {agent_name}. Ignorando.")

    df_escala_expanded = pd.DataFrame(expanded_scale_data)
    if df_escala_expanded.empty:
        st.warning("Nenhuma escala válida foi encontrada após o processamento. Verifique a coluna 'DIAS DE ATENDIMENTO'.")
        return pd.DataFrame()

    return df_escala_expanded

# Função para obter a escala vigente para um agente em uma data específica
def get_effective_scale_for_day(agent_name, current_date, df_escala_history):
    current_date_ts = pd.Timestamp(current_date)

    agent_scales = df_escala_history[
        (df_escala_history['Nome do agente'] == agent_name) &
        (df_escala_history['Dia da Semana Num'] == current_date.weekday()) &
        (df_escala_history['Data Início Vigência'] <= current_date_ts) &
        (
            (df_escala_history['Data Fim Vigência'].isna()) |
            (df_escala_history['Data Fim Vigência'] >= current_date_ts)
        )
    ].copy()

    if agent_scales.empty:
        return pd.DataFrame()

    latest_start_date = agent_scales['Data Início Vigência'].max()
    return agent_scales[agent_scales['Data Início Vigência'] == latest_start_date]

def calculate_metrics(df_real_status_history, df_escala_history, selected_agents, start_date, end_date):
    analysis_results = []

    df_real_status_filtered = df_real_status_history[
        (df_real_status_history['Nome do agente'].isin(selected_agents)) &
        (df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
        (df_real_status_history['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
    ].copy()

    if df_real_status_filtered.empty and df_escala_history.empty:
        return pd.DataFrame()

    for agent in selected_agents:
        agent_real_status = df_real_status_filtered[df_real_status_filtered['Nome do agente'] == agent]

        total_scheduled_time_minutes = 0
        total_online_in_schedule_minutes = 0

        current_date_metrics = start_date
        while current_date_metrics <= end_date:
            daily_escala = get_effective_scale_for_day(agent, current_date_metrics, df_escala_history)

            if not daily_escala.empty:
                for _, scale_row in daily_escala.iterrows():
                    scale_start_time = scale_row['Entrada']
                    scale_end_time = scale_row['Saída']

                    scale_start_dt = datetime.combine(current_date_metrics, scale_start_time)
                    scale_end_dt = datetime.combine(current_date_metrics, scale_end_time)

                    if scale_end_dt < scale_start_dt:
                        scale_end_dt += timedelta(days=1)

                    # Tempo total agendado para o dia
                    scheduled_duration = (scale_end_dt - scale_start_dt).total_seconds() / 60
                    total_scheduled_time_minutes += scheduled_duration

                    # Calcular tempo online dentro da escala
                    agent_status_on_day = agent_real_status[
                        (agent_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date_metrics)
                    ]

                    for _, status_row in agent_status_on_day.iterrows():
                        status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                        status_end = status_row['Hora de término do estado - Carimbo de data/hora']
                        status_type = status_row['Estado']

                        # Considerar apenas estados "online" ou "disponíveis"
                        if status_type in ['Unified online', 'Unified transfers only', 'Unified busy', 'Unified wrap up']:
                            # Interseção do status com o período de escala
                            overlap_start = max(scale_start_dt, status_start)
                            overlap_end = min(scale_end_dt, status_end)

                            if overlap_end > overlap_start:
                                overlap_duration = (overlap_end - overlap_start).total_seconds() / 60
                                total_online_in_schedule_minutes += overlap_duration
            current_date_metrics += timedelta(days=1)

        availability_percentage = (total_online_in_schedule_minutes / total_scheduled_time_minutes * 100) if total_scheduled_time_minutes > 0 else 0

        analysis_results.append({
            'Agente': agent,
            'Período': f"{start_date.strftime('%Y-%m-%d')} a {end_date.strftime('%Y-%m-%d')}",
            'Tempo Agendado (min)': round(total_scheduled_time_minutes, 2),
            'Tempo Online na Escala (min)': round(total_online_in_schedule_minutes, 2),
            'Disponibilidade (%)': round(availability_percentage, 2)
        })

    return pd.DataFrame(analysis_results)

# --- Configuração do Streamlit ---
st.set_page_config(layout="wide", page_title="Análise de Produtividade de Agentes")

st.title("Análise de Produtividade de Agentes")

# Inicialização do session_state
if 'df_real_status_history' not in st.session_state:
    st.session_state.df_real_status_history = pd.DataFrame(columns=[
        'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
        'Hora de término do estado - Carimbo de data/hora', 'Estado',
        'Tempo do agente no estado / Minutos'
    ])
if 'df_escala_history' not in st.session_state:
    st.session_state.df_escala_history = pd.DataFrame(columns=[
        'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Carga',
        'Data Início Vigência', 'Data Fim Vigência'
    ])
    # Garantir que as colunas de data sejam do tipo datetime64[ns]
    st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'])
    st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'])

if 'all_unique_agents' not in st.session_state:
    st.session_state.all_unique_agents = set()
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}

tab_upload, tab_manage_scales, tab_manage_groups, tab_visualization = st.tabs([
    "Upload de Dados", "Gerenciar Escalas", "Gerenciar Grupos", "Visualização e Métricas"
])

with tab_upload:
    st.header("Upload de Arquivos")

    st.subheader("Upload de Relatório de Status Real")
    uploaded_file_report = st.file_uploader("Escolha um arquivo Excel (.xlsx) para o relatório de status", type=["xlsx"], key="report_uploader")
    if uploaded_file_report:
        df_report_raw = pd.read_excel(uploaded_file_report)
        df_processed_report = process_uploaded_report(df_report_raw)

        if not df_processed_report.empty:
            # Remover duplicatas antes de adicionar ao histórico
            # Definir um subconjunto de colunas para identificar duplicatas de forma mais robusta
            subset_cols = ['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado']
            df_processed_report_unique = df_processed_report.drop_duplicates(subset=subset_cols)

            # Identificar novos registros para adicionar
            if not st.session_state.df_real_status_history.empty:
                # Criar um 'key' para comparação de duplicatas
                df_processed_report_unique['temp_key'] = df_processed_report_unique[subset_cols].astype(str).agg('_'.join, axis=1)
                st.session_state.df_real_status_history['temp_key'] = st.session_state.df_real_status_history[subset_cols].astype(str).agg('_'.join, axis=1)

                new_records = df_processed_report_unique[
                    ~df_processed_report_unique['temp_key'].isin(st.session_state.df_real_status_history['temp_key'])
                ].drop(columns=['temp_key'])

                st.session_state.df_real_status_history = pd.concat([st.session_state.df_real_status_history.drop(columns=['temp_key']), new_records], ignore_index=True)
            else:
                st.session_state.df_real_status_history = df_processed_report_unique.drop(columns=['temp_key'], errors='ignore') # remove temp_key se existir

            st.success(f"Relatório de status processado. {len(new_records) if 'new_records' in locals() else len(df_processed_report_unique)} novos registros adicionados.")
            st.dataframe(st.session_state.df_real_status_history.head())
            st.session_state.all_unique_agents.update(df_processed_report['Nome do agente'].unique())
        else:
            st.error("Nenhum dado válido processado do relatório de status.")

    st.subheader("Upload de Arquivo de Escala")
    uploaded_file_escala = st.file_uploader("Escolha um arquivo Excel (.xlsx) para a escala", type=["xlsx"], key="escala_uploader")
    if uploaded_file_escala:
        st.info("Ao fazer upload de uma nova escala, você pode definir sua data de início e, opcionalmente, uma data de fim de vigência.")
        new_start_effective_date = st.date_input("Data de Início de Vigência da Escala", value=datetime.now().date(), key="escala_start_date_upload")
        new_end_effective_date = st.date_input("Data de Fim de Vigência da Escala (opcional)", value=None, key="escala_end_date_upload")

        df_escala_raw = pd.read_excel(uploaded_file_escala)
        df_processed_escala = process_uploaded_scale(df_escala_raw, new_start_effective_date, new_end_effective_date)

        if not df_processed_escala.empty:
            # Lógica para gerenciar sobreposição de escalas
            # Para cada agente/dia da semana na nova escala, ajustar a Data Fim Vigência de escalas antigas
            for _, new_row in df_processed_escala.iterrows():
                agent = new_row['Nome do agente']
                day_num = new_row['Dia da Semana Num']
                new_start_ts = new_row['Data Início Vigência']
                new_end_ts = new_row['Data Fim Vigência'] # Pode ser NaT

                # Encontrar escalas existentes para o mesmo agente e dia da semana que se sobrepõem
                # e cuja Data Início Vigência é anterior à nova escala
                overlapping_scales_mask = (
                    (st.session_state.df_escala_history['Nome do agente'] == agent) &
                    (st.session_state.df_escala_history['Dia da Semana Num'] == day_num) &
                    (st.session_state.df_escala_history['Data Início Vigência'] < new_start_ts) & # Escalas que começaram antes
                    (
                        (st.session_state.df_escala_history['Data Fim Vigência'].isna()) | # E são indefinidas
                        (st.session_state.df_escala_history['Data Fim Vigência'] >= new_start_ts) # Ou terminam depois/no mesmo dia da nova
                    )
                )

                # Ajustar a Data Fim Vigência das escalas sobrepostas para o dia anterior à nova escala
                st.session_state.df_escala_history.loc[overlapping_scales_mask, 'Data Fim Vigência'] = new_start_ts - timedelta(days=1)

            # Adicionar a nova escala ao histórico, removendo duplicatas exatas (agente, dia, entrada, saida, vigencia)
            # Para evitar adicionar a mesma escala várias vezes se o arquivo for carregado novamente
            df_processed_escala_unique = df_processed_escala.drop_duplicates(
                subset=['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência', 'Data Fim Vigência']
            )
            st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, df_processed_escala_unique], ignore_index=True)
            st.session_state.df_escala_history = st.session_state.df_escala_history.sort_values(by=['Nome do agente', 'Dia da Semana Num', 'Data Início Vigência']).reset_index(drop=True)


            st.success(f"Arquivo de escala processado. {len(df_processed_escala_unique)} registros de escala adicionados/atualizados.")
            st.dataframe(st.session_state.df_escala_history.head())
            st.session_state.all_unique_agents.update(df_processed_escala['Nome do agente'].unique())
        else:
            st.error("Nenhum dado válido processado do arquivo de escala.")

    if st.button("Limpar Histórico de Dados de Status Real"):
        st.session_state.df_real_status_history = pd.DataFrame(columns=[
            'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado',
            'Tempo do agente no estado / Minutos'
        ])
        st.success("Histórico de status real limpo.")
        st.rerun()

    if st.button("Limpar Histórico de Dados de Escala"):
        st.session_state.df_escala_history = pd.DataFrame(columns=[
            'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Carga',
            'Data Início Vigência', 'Data Fim Vigência'
        ])
        st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'])
        st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'])
        st.success("Histórico de escala limpo.")
        st.rerun()

with tab_manage_scales:
    st.header("Gerenciar Escalas Manuais")
    if not st.session_state.df_escala_history.empty:
        all_agents_in_scale = sorted(list(st.session_state.df_escala_history['Nome do agente'].unique()))

        st.subheader("Adicionar/Atualizar Escala para um Agente")
        selected_agent_manual = st.selectbox("Selecione o Agente", options=[""] + all_agents_in_scale, key="manual_agent_select")

        if selected_agent_manual:
            col1, col2 = st.columns(2)
            with col1:
                manual_day_of_week = st.selectbox("Dia da Semana", options=[
                    "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
                    "Sexta-feira", "Sábado", "Domingo"
                ], key="manual_day_select")
                manual_entrada = st.time_input("Hora de Entrada", value=time(9, 0), key="manual_entrada")
            with col2:
                manual_saida = st.time_input("Hora de Saída", value=time(18, 0), key="manual_saida")
                manual_carga = st.text_input("Carga Horária (opcional)", key="manual_carga")

            manual_start_date = st.date_input("Data de Início de Vigência", value=datetime.now().date(), key="manual_start_date")
            manual_end_date = st.date_input("Data de Fim de Vigência (opcional)", value=None, key="manual_end_date")

            dias_map_reverse = {
                "Segunda-feira": 0, "Terça-feira": 1, "Quarta-feira": 2, "Quinta-feira": 3,
                "Sexta-feira": 4, "Sábado": 5, "Domingo": 6
            }
            manual_day_num = dias_map_reverse.get(manual_day_of_week)

            if st.button("Salvar Escala Manual"):
                if manual_day_num is not None:
                    new_scale_entry = pd.DataFrame([{
                        'Nome do agente': selected_agent_manual,
                        'Dia da Semana Num': manual_day_num,
                        'Entrada': manual_entrada,
                        'Saída': manual_saida,
                        'Carga': manual_carga,
                        'Data Início Vigência': pd.Timestamp(manual_start_date),
                        'Data Fim Vigência': pd.Timestamp(manual_end_date) if manual_end_date else pd.NaT
                    }])

                    # Lógica de sobreposição similar ao upload
                    agent = selected_agent_manual
                    day_num = manual_day_num
                    new_start_ts = new_scale_entry.loc[0, 'Data Início Vigência']
                    new_end_ts = new_scale_entry.loc[0, 'Data Fim Vigência']

                    overlapping_scales_mask = (
                        (st.session_state.df_escala_history['Nome do agente'] == agent) &
                        (st.session_state.df_escala_history['Dia da Semana Num'] == day_num) &
                        (st.session_state.df_escala_history['Data Início Vigência'] < new_start_ts) &
                        (
                            (st.session_state.df_escala_history['Data Fim Vigência'].isna()) |
                            (st.session_state.df_escala_history['Data Fim Vigência'] >= new_start_ts)
                        )
                    )
                    st.session_state.df_escala_history.loc[overlapping_scales_mask, 'Data Fim Vigência'] = new_start_ts - timedelta(days=1)

                    # Adicionar a nova entrada
                    st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, new_scale_entry], ignore_index=True)
                    st.session_state.df_escala_history = st.session_state.df_escala_history.sort_values(by=['Nome do agente', 'Dia da Semana Num', 'Data Início Vigência']).reset_index(drop=True)
                    st.success(f"Escala para {selected_agent_manual} no(a) {manual_day_of_week} salva com sucesso!")
                    st.rerun()
                else:
                    st.error("Dia da semana inválido.")

        st.subheader("Escalas Atuais Registradas")
        if not st.session_state.df_escala_history.empty:
            st.dataframe(st.session_state.df_escala_history)
        else:
            st.info("Nenhuma escala registrada ainda.")

    else:
        st.info("Faça o upload do arquivo de escala na aba 'Upload de Dados' para gerenciar escalas manualmente.")

with tab_manage_groups:
    st.header("Gerenciar Grupos de Agentes")
    if not st.session_state.all_unique_agents:
        st.info("Faça o upload do arquivo de escala na aba 'Upload de Dados' para gerenciar grupos (apenas agentes com escala definida podem ser agrupados).")
    else:
        all_agents_for_groups = sorted(list(st.session_state.all_unique_agents))

        st.subheader("Criar Novo Grupo")
        group_name = st.text_input("Nome do Grupo")
        selected_agents_for_group = st.multiselect(
            "Selecione os agentes para este grupo:",
            options=all_agents_for_groups,
            key="group_agent_multiselect"
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
                st.write(f"**{name}** ({len(agents)} agentes)")
                with st.expander(f"Ver agentes em '{name}'"):
                    st.write(", ".join(agents))
            group_to_delete = st.selectbox("Selecione um grupo para excluir:", [""] + list(st.session_state.agent_groups.keys()))
            if st.button("Excluir Grupo") and group_to_delete:
                del st.session_state.agent_groups[group_to_delete]
                st.success(f"Grupo '{group_to_delete}' excluído.")
                st.rerun()
        else:
            st.info("Nenhum grupo criado ainda.")
    # Removido o else que informava para fazer upload, pois já está no início da aba

with tab_visualization:
    st.header("Visualização e Métricas")

    if not st.session_state.df_real_status_history.empty or not st.session_state.df_escala_history.empty:
        all_available_agents = sorted(list(st.session_state.all_unique_agents))

        filter_by_group = st.checkbox("Filtrar por Grupo de Agentes?")
        selected_agents = []

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
                st.warning("Nenhum grupo disponível. Crie grupos na aba 'Gerenciar Grupos'.")
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
            min_date_data = min(min_date_data, st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].min().date())
            max_date_data = max(max_date_data, st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].max().date())

        if not st.session_state.df_escala_history.empty and not st.session_state.df_escala_history['Data Início Vigência'].empty:
            min_date_data = min(min_date_data, st.session_state.df_escala_history['Data Início Vigência'].min().date())

        start_date = st.date_input("Data de Início", value=min_date_data, min_value=min_date_data, max_value=max_date_data)
        end_date = st.date_input("Data de Fim", value=max_date_data, min_value=min_date_data, max_value=max_date_data)

        if selected_agents:
            df_chart_data = pd.DataFrame()

            # Adicionar dados de status real
            if not st.session_state.df_real_status_history.empty:
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
            if not st.session_state.df_escala_history.empty:
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
    else:
        st.info("Por favor, faça o upload dos arquivos na aba 'Upload de Dados' primeiro.")
