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
        dias_str_cleaned = unicodedata.normalize('NFKD', dias_str_cleaned).encode('ascii', 'ignore').decode('utf-8').upper()

        for dia_raw in dias_str_cleaned.split(','):
            dia = dia_raw.strip()
            if dia in dias_map:
                expanded_scale_data.append({
                    'Nome do agente': agent_name,
                    'Dia da Semana Num': dias_map[dia],
                    'Dia da Semana Nome': dia,
                    'Entrada': entrada,
                    'Saída': saida,
                    'Carga': carga,
                    'Data Início Vigência': pd.Timestamp(start_effective_date), # Convert to Timestamp
                    'Data Fim Vigência': pd.Timestamp(end_effective_date) if end_effective_date else pd.NaT # Convert to Timestamp or NaT
                })
            elif dia: # Se não for vazio e não mapeado, avisar
                st.warning(f"Dia da semana '{dia}' não reconhecido para o agente '{agent_name}'. Ignorando.")

    df_expanded_scale = pd.DataFrame(expanded_scale_data)

    # Garantir que as colunas de data/hora sejam do tipo datetime64[ns]
    df_expanded_scale['Data Início Vigência'] = pd.to_datetime(df_expanded_scale['Data Início Vigência'], errors='coerce')
    df_expanded_scale['Data Fim Vigência'] = pd.to_datetime(df_expanded_scale['Data Fim Vigência'], errors='coerce')

    return df_expanded_scale

def get_effective_scale_for_day(agent_name, current_date, df_escala_history):
    if df_escala_history.empty:
        return pd.DataFrame()

    # Converter current_date para pd.Timestamp para comparação consistente
    current_timestamp = pd.Timestamp(current_date)

    # Filtrar escalas para o agente e dia da semana
    filtered_by_agent_day = df_escala_history[
        (df_escala_history['Nome do agente'] == agent_name) &
        (df_escala_history['Dia da Semana Num'] == current_date.weekday())
    ].copy()

    if filtered_by_agent_day.empty:
        return pd.DataFrame()

    # Filtrar por vigência: current_date deve estar entre Data Início Vigência e Data Fim Vigência
    # Usar pd.Timestamp para Data Início Vigência e Data Fim Vigência para comparação
    # A Data Fim Vigência pode ser NaT (indefinida)
    effective_scales = filtered_by_agent_day[
        (filtered_by_agent_day['Data Início Vigência'] <= current_timestamp) &
        (
            (filtered_by_agent_day['Data Fim Vigência'].isna()) | # Vigência indefinida
            (filtered_by_agent_day['Data Fim Vigência'] >= current_timestamp) # Ou a data de fim é maior ou igual à current_date
        )
    ].copy()

    if effective_scales.empty:
        return pd.DataFrame()

    # Se houver múltiplas escalas válidas para o mesmo dia, pegar a mais recente
    # (com a Data Início Vigência mais recente)
    effective_scales = effective_scales.sort_values(by='Data Início Vigência', ascending=False)

    # Remover duplicatas para o mesmo agente/dia da semana, mantendo a mais recente
    # Isso é importante se houver sobreposição de escalas com diferentes entradas/saídas
    # Apenas a mais recente deve ser considerada
    effective_scales = effective_scales.drop_duplicates(subset=['Nome do agente', 'Dia da Semana Num'], keep='first')

    return effective_scales

def calculate_metrics(df_real_status, df_escala_history, selected_agents, start_date, end_date):
    metrics_data = []
    date_range = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]

    for agent in selected_agents:
        for current_date in date_range:
            # Obter a escala efetiva para o agente e o dia atual
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

            # Filtrar status real para o agente e o dia atual
            df_agent_day_status = df_real_status[
                (df_real_status['Nome do agente'] == agent) &
                (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date)
            ].copy()

            total_online_time_minutes = 0
            if not df_agent_day_status.empty:
                for _, status_row in df_agent_day_status.iterrows():
                    if status_row['Estado'] == 'Unified online':
                        start_status = status_row['Hora de início do estado - Carimbo de data/hora']
                        end_status = status_row['Hora de término do estado - Carimbo de data/hora']

                        # Limitar o tempo de status ao dia atual para o cálculo
                        start_of_day = datetime.combine(current_date, time.min)
                        end_of_day = datetime.combine(current_date, time.max)

                        effective_start = max(start_status, start_of_day)
                        effective_end = min(end_status, end_of_day)

                        if effective_end > effective_start:
                            total_online_time_minutes += (effective_end - effective_start).total_seconds() / 60

            availability_percentage = 0
            if total_scheduled_time_minutes > 0:
                availability_percentage = (total_online_time_minutes / total_scheduled_time_minutes) * 100

            metrics_data.append({
                'Agente': agent,
                'Data': current_date.strftime('%Y-%m-%d'),
                'Tempo Online (min)': round(total_online_time_minutes, 2),
                'Tempo Escala (min)': round(total_scheduled_time_minutes, 2),
                'Disponibilidade (%)': round(availability_percentage, 2)
            })

    return pd.DataFrame(metrics_data)

# --- Inicialização do Streamlit ---
st.set_page_config(layout="wide", page_title="Análise de Produtividade de Agentes")

st.title("📊 Análise de Produtividade de Agentes")

# Inicialização de session_state
if 'df_real_status_history' not in st.session_state:
    st.session_state.df_real_status_history = pd.DataFrame(columns=[
        'Nome do agente', 'Dia', 'Hora de início do estado - Carimbo de data/hora',
        'Hora de término do estado - Carimbo de data/hora', 'Estado', 'Tempo do agente no estado / Minutos'
    ]).astype({
        'Hora de início do estado - Carimbo de data/hora': 'datetime64[ns]',
        'Hora de término do estado - Carimbo de data/hora': 'datetime64[ns]'
    })

if 'df_escala_history' not in st.session_state:
    st.session_state.df_escala_history = pd.DataFrame(columns=[
        'Nome do agente', 'Dia da Semana Num', 'Dia da Semana Nome', 'Entrada', 'Saída', 'Carga',
        'Data Início Vigência', 'Data Fim Vigência'
    ]).astype({
        'Data Início Vigência': 'datetime64[ns]',
        'Data Fim Vigência': 'datetime64[ns]'
    })

if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}

# Abas
tab_upload, tab_manage_scales, tab_manage_groups, tab_visualization = st.tabs([
    "Upload de Dados", "Gerenciar Escalas", "Gerenciar Grupos", "Visualização e Métricas"
])

with tab_upload:
    st.header("Upload de Arquivos")

    st.subheader("Upload de Relatório de Status Real")
    uploaded_file_report = st.file_uploader("Escolha um arquivo Excel (.xlsx) ou CSV (.csv) para o relatório de status real", type=["xlsx", "csv"], key="report_uploader")
    if uploaded_file_report:
        try:
            if uploaded_file_report.name.endswith('.csv'):
                df_report_raw = pd.read_csv(uploaded_file_report)
            else:
                df_report_raw = pd.read_excel(uploaded_file_report)

            df_processed_report = process_uploaded_report(df_report_raw)

            if not df_processed_report.empty:
                # Remover duplicatas antes de adicionar ao histórico
                # Definir um subconjunto de colunas para identificar duplicatas de forma mais robusta
                subset_cols_report = ['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado']
                df_processed_report_unique = df_processed_report.drop_duplicates(subset=subset_cols_report, keep='first')

                # Concatenar e remover duplicatas do histórico completo
                df_combined = pd.concat([st.session_state.df_real_status_history, df_processed_report_unique], ignore_index=True)
                st.session_state.df_real_status_history = df_combined.drop_duplicates(subset=subset_cols_report, keep='first')

                st.success("Relatório de status real processado e adicionado ao histórico com sucesso!")
                st.dataframe(st.session_state.df_real_status_history.head(), use_container_width=True)
            else:
                st.warning("Nenhum dado válido processado do relatório de status real.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de status real. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Upload de Arquivo de Escala")
    uploaded_file_escala = st.file_uploader("Escolha um arquivo Excel (.xlsx) ou CSV (.csv) para a escala", type=["xlsx", "csv"], key="escala_uploader")
    if uploaded_file_escala:
        st.info("Ao fazer upload de uma nova escala, você pode definir sua data de início e fim de vigência.")
        new_scale_start_date = st.date_input("Data de Início de Vigência da Nova Escala", value=datetime.now().date(), key="new_scale_start_date_upload")
        new_scale_end_date = st.date_input("Data de Fim de Vigência da Nova Escala (opcional)", value=None, key="new_scale_end_date_upload")

        if st.button("Processar e Adicionar Escala", key="process_escala_button"):
            try:
                if uploaded_file_escala.name.endswith('.csv'):
                    df_escala_raw = pd.read_csv(uploaded_file_escala)
                else:
                    df_escala_raw = pd.read_excel(uploaded_file_escala)

                df_processed_escala = process_uploaded_scale(df_escala_raw, new_scale_start_date, new_scale_end_date)

                if not df_processed_escala.empty:
                    # Lógica para invalidar escalas antigas que se sobrepõem
                    # Apenas se a nova escala tem uma data de início de vigência definida
                    if new_scale_start_date:
                        # Identificar escalas antigas que terminam após a nova escala começar
                        # e que são para o mesmo agente e dia da semana
                        for _, new_row in df_processed_escala.iterrows():
                            agent = new_row['Nome do agente']
                            day_num = new_row['Dia da Semana Num']
                            new_start_ts = new_row['Data Início Vigência'] # Já é Timestamp

                            # Encontrar escalas antigas para o mesmo agente/dia da semana
                            # que começaram antes da nova e terminam depois ou são indefinidas
                            overlapping_old_scales_idx = st.session_state.df_escala_history[
                                (st.session_state.df_escala_history['Nome do agente'] == agent) &
                                (st.session_state.df_escala_history['Dia da Semana Num'] == day_num) &
                                (st.session_state.df_escala_history['Data Início Vigência'] < new_start_ts) &
                                (
                                    (st.session_state.df_escala_history['Data Fim Vigência'].isna()) |
                                    (st.session_state.df_escala_history['Data Fim Vigência'] >= new_start_ts)
                                )
                            ].index

                            # Atualizar a Data Fim Vigência das escalas antigas
                            if not overlapping_old_scales_idx.empty:
                                st.session_state.df_escala_history.loc[
                                    overlapping_old_scales_idx, 'Data Fim Vigência'
                                ] = new_start_ts - timedelta(days=1)
                                st.info(f"Escalas antigas para {agent} no dia {new_row['Dia da Semana Nome']} ajustadas para terminar em {new_start_ts.date() - timedelta(days=1)}.")

                    # Concatenar a nova escala
                    st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, df_processed_escala], ignore_index=True)

                    # Remover duplicatas exatas (caso o mesmo arquivo seja carregado duas vezes com as mesmas datas de vigência)
                    subset_cols_escala = ['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência', 'Data Fim Vigência']
                    st.session_state.df_escala_history = st.session_state.df_escala_history.drop_duplicates(subset=subset_cols_escala, keep='first')

                    st.success("Arquivo de escala processado e adicionado ao histórico com sucesso!")
                    st.dataframe(st.session_state.df_escala_history.tail(), use_container_width=True)
                else:
                    st.warning("Nenhum dado válido processado do arquivo de escala.")
            except Exception as e:
                st.error(f"Erro ao processar o arquivo de escala. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Limpar Histórico de Dados")
    if st.button("Limpar Histórico de Status Real"):
        st.session_state.df_real_status_history = pd.DataFrame(columns=[
            'Nome do agente', 'Dia', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado', 'Tempo do agente no estado / Minutos'
        ]).astype({
            'Hora de início do estado - Carimbo de data/hora': 'datetime64[ns]',
            'Hora de término do estado - Carimbo de data/hora': 'datetime64[ns]'
        })
        st.success("Histórico de status real limpo.")

    if st.button("Limpar Histórico de Escalas"):
        st.session_state.df_escala_history = pd.DataFrame(columns=[
            'Nome do agente', 'Dia da Semana Num', 'Dia da Semana Nome', 'Entrada', 'Saída', 'Carga',
            'Data Início Vigência', 'Data Fim Vigência'
        ]).astype({
            'Data Início Vigência': 'datetime64[ns]',
            'Data Fim Vigência': 'datetime64[ns]'
        })
        st.success("Histórico de escalas limpo.")

with tab_manage_scales:
    st.header("Gerenciar Escalas Manuais")

    if st.session_state.df_escala_history.empty:
        st.info("Nenhuma escala carregada. Faça o upload na aba 'Upload de Dados' ou adicione manualmente abaixo.")
    else:
        st.subheader("Escalas Atuais no Histórico")
        st.dataframe(st.session_state.df_escala_history, use_container_width=True)

    st.subheader("Adicionar/Atualizar Escala Manualmente")

    # Obter agentes únicos do histórico de escalas ou status real
    all_known_agents = []
    if not st.session_state.df_escala_history.empty:
        all_known_agents.extend(st.session_state.df_escala_history['Nome do agente'].unique())
    if not st.session_state.df_real_status_history.empty:
        all_known_agents.extend(st.session_state.df_real_status_history['Nome do agente'].unique())
    all_known_agents = sorted(list(set(all_known_agents)))

    new_agent_name = st.selectbox("Selecione ou digite o nome do agente", options=[""] + all_known_agents, key="manual_agent_name")
    if new_agent_name == "":
        new_agent_name = st.text_input("Ou digite um novo nome de agente", key="manual_agent_name_text")

    new_agent_name = normalize_agent_name(new_agent_name)

    new_day_of_week_name = st.selectbox("Dia da Semana", options=[""] + list(get_dias_map().keys()), key="manual_day_name")
    new_entry_time = st.time_input("Hora de Entrada", value=time(9, 0), key="manual_entry_time")
    new_exit_time = st.time_input("Hora de Saída", value=time(18, 0), key="manual_exit_time")
    new_carga = st.number_input("Carga Horária (minutos)", min_value=0, value=480, key="manual_carga")
    new_start_effective_date = st.date_input("Data de Início de Vigência", value=datetime.now().date(), key="manual_start_date")
    new_end_effective_date = st.date_input("Data de Fim de Vigência (opcional)", value=None, key="manual_end_date")

    if st.button("Adicionar/Atualizar Escala", key="add_manual_scale_button"):
        if new_agent_name and new_day_of_week_name:
            day_num = get_dias_map().get(new_day_of_week_name)
            if day_num is not None:
                # Converter datas para Timestamp para consistência
                start_ts = pd.Timestamp(new_start_effective_date)
                end_ts = pd.Timestamp(new_end_effective_date) if new_end_effective_date else pd.NaT

                # Lógica para invalidar escalas antigas que se sobrepõem
                # Encontrar escalas antigas para o mesmo agente/dia da semana
                # que começaram antes da nova e terminam depois ou são indefinidas
                overlapping_old_scales_idx = st.session_state.df_escala_history[
                    (st.session_state.df_escala_history['Nome do agente'] == new_agent_name) &
                    (st.session_state.df_escala_history['Dia da Semana Num'] == day_num) &
                    (st.session_state.df_escala_history['Data Início Vigência'] < start_ts) &
                    (
                        (st.session_state.df_escala_history['Data Fim Vigência'].isna()) |
                        (st.session_state.df_escala_history['Data Fim Vigência'] >= start_ts)
                    )
                ].index

                # Atualizar a Data Fim Vigência das escalas antigas
                if not overlapping_old_scales_idx.empty:
                    st.session_state.df_escala_history.loc[
                        overlapping_old_scales_idx, 'Data Fim Vigência'
                    ] = start_ts - timedelta(days=1)
                    st.info(f"Escalas antigas para {new_agent_name} no dia {new_day_of_week_name} ajustadas para terminar em {(start_ts - timedelta(days=1)).date()}.")

                # Adicionar a nova escala
                new_scale_row = pd.DataFrame([{
                    'Nome do agente': new_agent_name,
                    'Dia da Semana Num': day_num,
                    'Dia da Semana Nome': new_day_of_week_name,
                    'Entrada': new_entry_time,
                    'Saída': new_exit_time,
                    'Carga': new_carga,
                    'Data Início Vigência': start_ts,
                    'Data Fim Vigência': end_ts
                }])

                # Garantir que os dtypes da nova linha correspondam ao histórico
                new_scale_row['Data Início Vigência'] = pd.to_datetime(new_scale_row['Data Início Vigência'])
                new_scale_row['Data Fim Vigência'] = pd.to_datetime(new_scale_row['Data Fim Vigência'])

                st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, new_scale_row], ignore_index=True)

                # Remover duplicatas exatas (caso a mesma escala seja adicionada duas vezes)
                subset_cols_escala = ['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência', 'Data Fim Vigência']
                st.session_state.df_escala_history = st.session_state.df_escala_history.drop_duplicates(subset=subset_cols_escala, keep='first')

                st.success(f"Escala para {new_agent_name} no dia {new_day_of_week_name} adicionada/atualizada com sucesso!")
            else:
                st.error("Dia da semana não reconhecido.")
        else:
            st.warning("Por favor, preencha o nome do agente e o dia da semana.")

with tab_manage_groups:
    st.header("Gerenciar Grupos de Agentes")

    # Obter todos os agentes únicos do histórico de escalas e status real
    all_available_agents_for_groups = []
    if not st.session_state.df_escala_history.empty:
        all_available_agents_for_groups.extend(st.session_state.df_escala_history['Nome do agente'].unique())
    if not st.session_state.df_real_status_history.empty:
        all_available_agents_for_groups.extend(st.session_state.df_real_status_history['Nome do agente'].unique())
    all_available_agents_for_groups = sorted(list(set(all_available_agents_for_groups)))

    st.subheader("Criar Novo Grupo")
    new_group_name = st.text_input("Nome do Novo Grupo")
    selected_agents_for_group = st.multiselect(
        "Selecione os agentes para este grupo",
        options=all_available_agents_for_groups,
        key="select_agents_for_group"
    )
    if st.button("Salvar Grupo"):
        if new_group_name and selected_agents_for_group:
            st.session_state.agent_groups[new_group_name] = selected_agents_for_group
            st.success(f"Grupo '{new_group_name}' criado com sucesso!")
        else:
            st.warning("Por favor, insira um nome para o grupo e selecione pelo menos um agente.")

    st.subheader("Grupos Existentes")
    if st.session_state.agent_groups:
        for group_name, agents in st.session_state.agent_groups.items():
            st.write(f"**{group_name}**: {', '.join(agents)}")
            if st.button(f"Excluir {group_name}", key=f"delete_group_{group_name}"):
                del st.session_state.agent_groups[group_name]
                st.success(f"Grupo '{group_name}' excluído.")
                st.experimental_rerun()
    else:
        st.info("Nenhum grupo de agentes criado ainda.")

with tab_visualization:
    st.header("Visualização da Linha do Tempo e Métricas")

    if st.session_state.df_real_status_history.empty and st.session_state.df_escala_history.empty:
        st.info("Por favor, faça o upload dos arquivos na aba 'Upload de Dados' primeiro.")
    else:
        # Obter todos os agentes únicos do histórico de escalas
        all_available_agents = []
        if not st.session_state.df_escala_history.empty:
            all_available_agents.extend(st.session_state.df_escala_history['Nome do agente'].unique())
        all_available_agents = sorted(list(set(all_available_agents)))

        if not all_available_agents:
            st.warning("Nenhum agente com escala definida encontrado. Por favor, carregue um arquivo de escala ou adicione escalas manualmente.")
            selected_agents = []
        else:
            use_group_filter = st.checkbox("Filtrar por Grupo de Agentes", value=False)

            if use_group_filter and st.session_state.agent_groups:
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
                if use_group_filter: # Se checkbox marcado mas sem grupos
                    st.warning("Nenhum grupo disponível. Crie grupos na aba 'Gerenciar Grupos'.")
                selected_agents = st.multiselect(
                    "Selecione os agentes para visualizar:",
                    options=all_available_agents,
                    default=all_available_agents if len(all_available_agents) <= 5 else [],
                    key="agent_multiselect"
                )

        # Definir min_date_data e max_date_data com base nos dados disponíveis
        min_date_data = datetime.now().date()
        max_date_data = datetime.now().date()

        # Verificar e usar o tipo correto para as colunas de data/hora
        if not st.session_state.df_real_status_history.empty and 'Hora de início do estado - Carimbo de data/hora' in st.session_state.df_real_status_history.columns:
            if pd.api.types.is_datetime64_any_dtype(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora']):
                min_date_data = min(min_date_data, st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].min().date())
                max_date_data = max(max_date_data, st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'].max().date())
            else:
                st.warning("Coluna 'Hora de início do estado - Carimbo de data/hora' no histórico de status real não é do tipo datetime. Verifique o processamento.")

        if not st.session_state.df_escala_history.empty and 'Data Início Vigência' in st.session_state.df_escala_history.columns:
            if pd.api.types.is_datetime64_any_dtype(st.session_state.df_escala_history['Data Início Vigência']):
                min_date_data = min(min_date_data, st.session_state.df_escala_history['Data Início Vigência'].min().date())
            else:
                st.warning("Coluna 'Data Início Vigência' no histórico de escalas não é do tipo datetime. Verifique o processamento.")

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
