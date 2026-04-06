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
        st.error(f"Uma ou mais colunas essenciais ({', '.join(missing_cols)}) não foram encontradas no arquivo de escala após renomear. Verifique o cabeçalho do arquivo.")
        return pd.DataFrame()

    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)
    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    df.dropna(subset=['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída'], inplace=True)

    # Expandir os dias de atendimento
    expanded_data = []
    dias_map = get_dias_map()
    for index, row in df.iterrows():
        agent_name = row['Nome do agente']
        dias_atendimento_str = str(row['Dias de Atendimento']).upper().replace(' ', '')

        # Tratar casos como "SEG-SEX" ou "SEG,QUA,SEX"
        if '-' in dias_atendimento_str:
            start_day_str, end_day_str = dias_atendimento_str.split('-')
            start_day_num = dias_map.get(start_day_str)
            end_day_num = dias_map.get(end_day_str)

            if start_day_num is not None and end_day_num is not None:
                current_day_num = start_day_num
                while True:
                    expanded_data.append({
                        'Nome do agente': agent_name,
                        'Dia da Semana Num': current_day_num,
                        'Entrada': row['Entrada'],
                        'Saída': row['Saída'],
                        'Data Início Vigência': pd.Timestamp(start_effective_date), # Converter para Timestamp
                        'Data Fim Vigência': pd.Timestamp(end_effective_date) if end_effective_date else pd.NaT # Converter para Timestamp ou NaT
                    })
                    if current_day_num == end_day_num:
                        break
                    current_day_num = (current_day_num + 1) % 7
            else:
                st.warning(f"Formato de dias de atendimento inválido para agente {agent_name}: {row['Dias de Atendimento']}. Ignorando.")
        elif ',' in dias_atendimento_str:
            for day_str in dias_atendimento_str.split(','):
                day_num = dias_map.get(day_str)
                if day_num is not None:
                    expanded_data.append({
                        'Nome do agente': agent_name,
                        'Dia da Semana Num': day_num,
                        'Entrada': row['Entrada'],
                        'Saída': row['Saída'],
                        'Data Início Vigência': pd.Timestamp(start_effective_date),
                        'Data Fim Vigência': pd.Timestamp(end_effective_date) if end_effective_date else pd.NaT
                    })
                else:
                    st.warning(f"Dia da semana inválido '{day_str}' para agente {agent_name}. Ignorando.")
        else: # Dia único
            day_num = dias_map.get(dias_atendimento_str)
            if day_num is not None:
                expanded_data.append({
                    'Nome do agente': agent_name,
                    'Dia da Semana Num': day_num,
                    'Entrada': row['Entrada'],
                    'Saída': row['Saída'],
                    'Data Início Vigência': pd.Timestamp(start_effective_date),
                    'Data Fim Vigência': pd.Timestamp(end_effective_date) if end_effective_date else pd.NaT
                })
            else:
                st.warning(f"Dia da semana inválido '{dias_atendimento_str}' para agente {agent_name}. Ignorando.")

    if not expanded_data:
        return pd.DataFrame(columns=['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência', 'Data Fim Vigência'])

    df_expanded = pd.DataFrame(expanded_data)
    return df_expanded

def get_effective_scale_for_day(agent_name, current_date, df_escala_history):
    # Converter current_date para Timestamp para comparação consistente
    current_timestamp = pd.Timestamp(current_date)
    current_day_num = current_date.weekday() # 0 para segunda, 6 para domingo

    # Filtrar escalas para o agente e dia da semana
    agent_day_scales = df_escala_history[
        (df_escala_history['Nome do agente'] == agent_name) &
        (df_escala_history['Dia da Semana Num'] == current_day_num)
    ].copy()

    if agent_day_scales.empty:
        return pd.DataFrame()

    # Filtrar escalas que estão ativas na current_date
    # Data Início Vigência <= current_date
    # E (Data Fim Vigência é NaT OU Data Fim Vigência >= current_date)
    active_scales = agent_day_scales[
        (agent_day_scales['Data Início Vigência'] <= current_timestamp) &
        (
            agent_day_scales['Data Fim Vigência'].isna() |
            (agent_day_scales['Data Fim Vigência'] >= current_timestamp)
        )
    ]

    if active_scales.empty:
        return pd.DataFrame()

    # Se houver múltiplas escalas ativas, pegar a mais recente (maior Data Início Vigência)
    # Isso resolve sobreposições, priorizando a regra mais nova
    effective_scale = active_scales.loc[active_scales['Data Início Vigência'].idxmax()]

    return pd.DataFrame([effective_scale]) # Retorna como DataFrame para consistência

def calculate_metrics(df_real_status, df_escala_history, selected_agents, start_date, end_date):
    metrics_data = []

    # Certificar-se de que as colunas de data/hora são do tipo correto
    if not pd.api.types.is_datetime64_any_dtype(df_real_status['Hora de início do estado - Carimbo de data/hora']):
        st.warning("Coluna 'Hora de início do estado - Carimbo de data/hora' no histórico de status real não é do tipo datetime. Métricas não serão calculadas.")
        return pd.DataFrame()
    if not pd.api.types.is_datetime64_any_dtype(df_escala_history['Data Início Vigência']):
        st.warning("Coluna 'Data Início Vigência' no histórico de escalas não é do tipo datetime. Métricas não serão calculadas.")
        return pd.DataFrame()

    for agent in selected_agents:
        current_date = start_date
        while current_date <= end_date:
            # Obter a escala efetiva para o agente no dia atual
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

                    duration = (end_dt - start_dt).total_seconds() / 60
                    total_scheduled_time_minutes += duration

            # Filtrar status real para o agente e o dia atual
            agent_daily_status = df_real_status[
                (df_real_status['Nome do agente'] == agent) &
                (df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date)
            ].copy()

            total_online_time_minutes = 0
            if not agent_daily_status.empty:
                # Considerar apenas estados "online" ou produtivos para disponibilidade
                online_states = ['Unified online', 'Unified transfers only', 'Unified busy', 'Unified wrap up'] # Ajuste conforme seus estados produtivos
                agent_online_status = agent_daily_status[agent_daily_status['Estado'].isin(online_states)]

                for _, status_row in agent_online_status.iterrows():
                    status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                    status_end = status_row['Hora de término do estado - Carimbo de data/hora']

                    # Garantir que o status não exceda o final do dia para o cálculo diário
                    day_end = datetime.combine(current_date, time.max)
                    status_end_clipped = min(status_end, day_end)

                    duration = (status_end_clipped - status_start).total_seconds() / 60
                    total_online_time_minutes += duration

            availability_percentage = (total_online_time_minutes / total_scheduled_time_minutes * 100) if total_scheduled_time_minutes > 0 else 0

            metrics_data.append({
                'Agente': agent,
                'Data': current_date.strftime('%Y-%m-%d'),
                'Tempo Escala (min)': round(total_scheduled_time_minutes, 2),
                'Tempo Online (min)': round(total_online_time_minutes, 2),
                'Disponibilidade (%)': round(availability_percentage, 2)
            })
            current_date += timedelta(days=1)

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
        'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída',
        'Data Início Vigência', 'Data Fim Vigência'
    ]).astype({
        'Data Início Vigência': 'datetime64[ns]',
        'Data Fim Vigência': 'datetime64[ns]'
    })

# Abas
tab_upload, tab_manage_scales, tab_visualization = st.tabs(["Upload de Dados", "Gerenciar Escalas", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos")

    st.subheader("Upload de Relatório de Status Real")
    uploaded_report_file = st.file_uploader("Escolha o arquivo Excel do relatório de status real", type=["xlsx"], key="report_upload")
    if uploaded_report_file is not None:
        try:
            df_report_raw = pd.read_excel(uploaded_report_file)
            df_processed_report = process_uploaded_report(df_report_raw)

            if not df_processed_report.empty:
                # Remover duplicatas antes de adicionar ao histórico
                # Considera que a combinação de agente, início, fim e estado é única para um registro
                df_processed_report_unique = df_processed_report.drop_duplicates(
                    subset=['Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
                            'Hora de término do estado - Carimbo de data/hora', 'Estado']
                )

                # Concatenar e garantir dtypes consistentes
                st.session_state.df_real_status_history = pd.concat([
                    st.session_state.df_real_status_history,
                    df_processed_report_unique
                ]).drop_duplicates().reset_index(drop=True)

                # Forçar dtypes novamente após concatenação para garantir
                st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
                st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

                st.success("Relatório de status real processado e adicionado ao histórico com sucesso!")
                st.dataframe(st.session_state.df_real_status_history.head())
            else:
                st.warning("Nenhum dado válido encontrado no relatório de status real após o processamento.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de relatório de status real. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Upload de Arquivo de Escala")
    uploaded_scale_file = st.file_uploader("Escolha o arquivo Excel da escala", type=["xlsx"], key="scale_upload")
    if uploaded_scale_file is not None:
        st.info("Para o upload de escala, você deve definir a data de início de vigência para esta escala.")
        new_start_effective_date = st.date_input("Data de Início de Vigência da Escala", value=datetime.now().date(), key="scale_start_date_upload")
        new_end_effective_date = st.date_input("Data de Fim de Vigência da Escala (opcional)", value=None, key="scale_end_date_upload")

        if st.button("Processar e Adicionar Escala", key="process_scale_button"):
            try:
                df_scale_raw = pd.read_excel(uploaded_scale_file)
                df_processed_scale = process_uploaded_scale(df_scale_raw, new_start_effective_date, new_end_effective_date)

                if not df_processed_scale.empty:
                    # Lógica para invalidar escalas antigas que se sobrepõem
                    if not st.session_state.df_escala_history.empty:
                        # Identificar escalas existentes que são substituídas pela nova
                        # Uma escala antiga é substituída se:
                        # 1. É para o mesmo agente e dia da semana
                        # 2. Sua Data Início Vigência é anterior à nova Data Início Vigência
                        # 3. Sua Data Fim Vigência (ou NaT) se sobrepõe ou começa depois da nova Data Início Vigência

                        # Converter new_start_effective_date para Timestamp para comparação
                        new_start_ts = pd.Timestamp(new_start_effective_date)

                        # Encontrar índices das escalas a serem atualizadas
                        indices_to_update = st.session_state.df_escala_history[
                            (st.session_state.df_escala_history['Nome do agente'].isin(df_processed_scale['Nome do agente'].unique())) &
                            (st.session_state.df_escala_history['Dia da Semana Num'].isin(df_processed_scale['Dia da Semana Num'].unique())) &
                            (st.session_state.df_escala_history['Data Início Vigência'] < new_start_ts) &
                            (
                                st.session_state.df_escala_history['Data Fim Vigência'].isna() |
                                (st.session_state.df_escala_history['Data Fim Vigência'] >= new_start_ts)
                            )
                        ].index

                        # Atualizar Data Fim Vigência para o dia anterior à nova escala
                        st.session_state.df_escala_history.loc[indices_to_update, 'Data Fim Vigência'] = new_start_ts - timedelta(days=1)

                    # Adicionar a nova escala ao histórico
                    st.session_state.df_escala_history = pd.concat([
                        st.session_state.df_escala_history,
                        df_processed_scale
                    ]).drop_duplicates(
                        subset=['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência'] # Considerar Data Início Vigência para unicidade
                    ).reset_index(drop=True)

                    # Forçar dtypes novamente após concatenação para garantir
                    st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'], errors='coerce')
                    st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'], errors='coerce')

                    st.success("Escala processada e adicionada ao histórico com sucesso!")
                    st.dataframe(st.session_state.df_escala_history.head())
                else:
                    st.warning("Nenhum dado válido encontrado na escala após o processamento.")
            except Exception as e:
                st.error(f"Erro ao processar o arquivo de escala. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Dados Atualmente Carregados")
    if not st.session_state.df_real_status_history.empty:
        st.write("Histórico de Status Real:")
        st.dataframe(st.session_state.df_real_status_history.tail())
    if not st.session_state.df_escala_history.empty:
        st.write("Histórico de Escalas:")
        st.dataframe(st.session_state.df_escala_history.tail())

    if st.button("Limpar Todos os Dados Históricos", key="clear_all_data"):
        st.session_state.df_real_status_history = pd.DataFrame(columns=[
            'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado',
            'Tempo do agente no estado / Minutos'
        ]).astype({
            'Hora de início do estado - Carimbo de data/hora': 'datetime64[ns]',
            'Hora de término do estado - Carimbo de data/hora': 'datetime64[ns]'
        })
        st.session_state.df_escala_history = pd.DataFrame(columns=[
            'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída',
            'Data Início Vigência', 'Data Fim Vigência'
        ]).astype({
            'Data Início Vigência': 'datetime64[ns]',
            'Data Fim Vigência': 'datetime64[ns]'
        })
        st.success("Todos os dados históricos foram limpos.")
        st.rerun()

with tab_manage_scales:
    st.header("Gerenciar Escalas Manuais")

    st.write("Adicione ou atualize escalas manualmente para agentes específicos.")

    all_agents_in_history = []
    if not st.session_state.df_real_status_history.empty:
        all_agents_in_history.extend(st.session_state.df_real_status_history['Nome do agente'].unique())
    if not st.session_state.df_escala_history.empty:
        all_agents_in_history.extend(st.session_state.df_escala_history['Nome do agente'].unique())
    all_agents_in_history = sorted(list(set(all_agents_in_history)))

    if not all_agents_in_history:
        st.info("Nenhum agente encontrado no histórico de status real ou escalas. Faça o upload de dados primeiro.")
    else:
        selected_agent_manual = st.selectbox("Selecione o Agente", [''] + all_agents_in_history, key="manual_agent_select")

        if selected_agent_manual:
            st.subheader(f"Escalas para {selected_agent_manual}")

            # Exibir escalas existentes para o agente
            agent_current_scales = st.session_state.df_escala_history[
                st.session_state.df_escala_history['Nome do agente'] == selected_agent_manual
            ].sort_values(by=['Dia da Semana Num', 'Data Início Vigência'])

            if not agent_current_scales.empty:
                st.dataframe(agent_current_scales)
            else:
                st.info("Nenhuma escala definida para este agente.")

            st.subheader("Adicionar/Atualizar Escala")
            col1, col2 = st.columns(2)
            with col1:
                day_options = {v: k for k, v in get_dias_map().items()} # Inverter para exibir nome do dia
                selected_day_num = st.selectbox("Dia da Semana", sorted(day_options.keys()), format_func=lambda x: day_options[x], key="manual_day_select")
                manual_entry_time = st.time_input("Hora de Entrada", value=time(9, 0), key="manual_entry_time")
            with col2:
                manual_exit_time = st.time_input("Hora de Saída", value=time(18, 0), key="manual_exit_time")
                manual_start_date = st.date_input("Data de Início de Vigência", value=datetime.now().date(), key="manual_start_date")
                manual_end_date = st.date_input("Data de Fim de Vigência (opcional)", value=None, key="manual_end_date")

            if st.button("Salvar Escala", key="save_manual_scale"):
                if selected_agent_manual and selected_day_num is not None and manual_entry_time and manual_exit_time and manual_start_date:
                    new_scale_entry = pd.DataFrame([{
                        'Nome do agente': selected_agent_manual,
                        'Dia da Semana Num': selected_day_num,
                        'Entrada': manual_entry_time,
                        'Saída': manual_exit_time,
                        'Data Início Vigência': pd.Timestamp(manual_start_date),
                        'Data Fim Vigência': pd.Timestamp(manual_end_date) if manual_end_date else pd.NaT
                    }])

                    # Lógica para invalidar escalas antigas que se sobrepõem
                    if not st.session_state.df_escala_history.empty:
                        new_start_ts = pd.Timestamp(manual_start_date)

                        indices_to_update = st.session_state.df_escala_history[
                            (st.session_state.df_escala_history['Nome do agente'] == selected_agent_manual) &
                            (st.session_state.df_escala_history['Dia da Semana Num'] == selected_day_num) &
                            (st.session_state.df_escala_history['Data Início Vigência'] < new_start_ts) &
                            (
                                st.session_state.df_escala_history['Data Fim Vigência'].isna() |
                                (st.session_state.df_escala_history['Data Fim Vigência'] >= new_start_ts)
                            )
                        ].index
                        st.session_state.df_escala_history.loc[indices_to_update, 'Data Fim Vigência'] = new_start_ts - timedelta(days=1)

                    # Adicionar a nova escala
                    st.session_state.df_escala_history = pd.concat([
                        st.session_state.df_escala_history,
                        new_scale_entry
                    ]).drop_duplicates(
                        subset=['Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Data Início Vigência']
                    ).reset_index(drop=True)

                    # Forçar dtypes novamente após concatenação para garantir
                    st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'], errors='coerce')
                    st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'], errors='coerce')

                    st.success(f"Escala para {selected_agent_manual} no dia {day_options[selected_day_num]} salva com sucesso!")
                    st.rerun()
                else:
                    st.error("Por favor, preencha todos os campos obrigatórios para a escala manual.")

with tab_visualization:
    st.header("Visualização e Métricas")

    all_agents_in_scale = []
    if not st.session_state.df_escala_history.empty:
        all_agents_in_scale.extend(st.session_state.df_escala_history['Nome do agente'].unique())
    all_agents_in_scale = sorted(list(set(all_agents_in_scale)))

    if not all_agents_in_scale:
        st.info("Nenhum agente com escala definida. Por favor, faça o upload ou gerencie escalas primeiro.")
        selected_agents = []
    else:
        selected_agents = st.multiselect(
            "Selecione os Agentes para Análise (apenas agentes com escala)",
            all_agents_in_scale,
            default=all_agents_in_scale if len(all_agents_in_scale) <= 5 else [] # Seleciona todos se <=5, senão nenhum
        )

    col_date1, col_date2 = st.columns(2)
    with col_date1:
        start_date = st.date_input("Data de Início", value=datetime.now().date() - timedelta(days=7))
    with col_date2:
        end_date = st.date_input("Data de Fim", value=datetime.now().date())

    if st.button("Gerar Gráfico e Métricas", key="generate_chart_metrics"):
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
