import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, time, date # Importar date explicitamente
import numpy as np
import unicodedata

# --- Funções de Normalização ---
def normalize_agent_name(name):
    if pd.isna(name):
        return name
    name = str(name).strip().upper()
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    return name

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

    df = df.rename(columns=expected_columns_report)

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

    expected_columns_scale = {
        'NOME': 'Nome do agente',
        'DIAS DE ATENDIMENTO': 'Dias de Atendimento',
        'ENTRADA': 'Entrada',
        'SAÍDA': 'Saída',
        'CARGA': 'Carga'
    }

    df = df.rename(columns=expected_columns_scale)

    required_cols = ['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída']
    if not all(col in df.columns for col in required_cols):
        st.error(f"Uma ou mais colunas essenciais ({', '.join(required_cols)}) não foram encontradas no arquivo de escala após renomear. Verifique os cabeçalhos do arquivo.")
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
                    'Data Início Vigência': start_effective_date, # Armazena como date object
                    'Data Fim Vigência': end_effective_date # Armazena como date object ou None
                })
            else:
                st.warning(f"Dia da semana '{dia_abbr}' não reconhecido para o agente {agent_name}. Ignorando.")

    df_escala_expanded = pd.DataFrame(expanded_scale_data)
    if df_escala_expanded.empty:
        st.warning("Nenhuma escala válida foi encontrada após o processamento. Verifique a coluna 'DIAS DE ATENDIMENTO'.")
        return pd.DataFrame()

    # Converter as colunas de vigência para datetime64[ns] após a criação do DataFrame
    # Isso garante que .dt.date funcione, e NaT será o valor para None
    df_escala_expanded['Data Início Vigência'] = pd.to_datetime(df_escala_expanded['Data Início Vigência'])
    df_escala_expanded['Data Fim Vigência'] = pd.to_datetime(df_escala_expanded['Data Fim Vigência'])

    return df_escala_expanded

# Função para obter a escala vigente para um agente em uma data específica
def get_effective_scale_for_day(agent_name, current_date, df_escala_history):
    # current_date é um date object
    # As colunas 'Data Início Vigência' e 'Data Fim Vigência' são datetime64[ns] (com NaT para indefinido)

    # Filtra escalas para o agente, dia da semana e onde current_date está dentro do período de vigência
    agent_scales = df_escala_history[
        (df_escala_history['Nome do agente'] == agent_name) &
        (df_escala_history['Dia da Semana Num'] == current_date.weekday()) &
        (df_escala_history['Data Início Vigência'].dt.date <= current_date) &
        (
            (df_escala_history['Data Fim Vigência'].isna()) | # Se Data Fim Vigência é NaT (indefinido)
            (df_escala_history['Data Fim Vigência'].dt.date >= current_date) # OU a data de fim é maior ou igual à current_date
        )
    ].copy()

    if agent_scales.empty:
        return pd.DataFrame()

    # Se houver múltiplas escalas válidas, pega a que começou mais recentemente
    # Isso resolve o caso de uma escala ser substituída por outra
    latest_start_date = agent_scales['Data Início Vigência'].dt.date.max()
    return agent_scales[agent_scales['Data Início Vigência'].dt.date == latest_start_date]

def calculate_metrics(df_real_status_history, df_escala_history, selected_agents, start_date, end_date):
    analysis_results = []

    # Filtrar df_real_status_history pelos agentes e datas selecionadas
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
            # Obtém a escala vigente para o agente no dia atual
            daily_escala = get_effective_scale_for_day(agent, current_date_metrics, df_escala_history)

            if not daily_escala.empty:
                for _, scale_row in daily_escala.iterrows():
                    scale_start_time = scale_row['Entrada']
                    scale_end_time = scale_row['Saída']

                    scale_start_dt = datetime.combine(current_date_metrics, scale_start_time)
                    scale_end_dt = datetime.combine(current_date_metrics, scale_end_time)

                    # Se a escala passa da meia-noite, ajusta o end_dt para o dia seguinte
                    if scale_end_dt < scale_start_dt:
                        scale_end_dt += timedelta(days=1)

                    # Garante que a escala não exceda o dia atual para o cálculo
                    day_end_limit = datetime.combine(current_date_metrics, time.max)
                    effective_scale_end = min(scale_end_dt, day_end_limit)

                    # Calcula o tempo total agendado para o dia dentro do limite do dia
                    if effective_scale_end > scale_start_dt:
                        total_scheduled_time_minutes += (effective_scale_end - scale_start_dt).total_seconds() / 60

                    # Status real para o agente no dia atual
                    daily_online_status = agent_real_status[
                        (agent_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date_metrics) &
                        (agent_real_status['Estado'] == 'Unified online')
                    ]

                    for _, status_row in daily_online_status.iterrows():
                        status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                        status_end = status_row['Hora de término do estado - Carimbo de data/hora']

                        # Garante que o status não exceda o dia atual para o cálculo
                        effective_status_end = min(status_end, day_end_limit)

                        # Calcular interseção entre o status online e a escala
                        overlap_start = max(scale_start_dt, status_start)
                        overlap_end = min(effective_scale_end, effective_status_end)

                        if overlap_end > overlap_start:
                            total_online_in_schedule_minutes += (overlap_end - overlap_start).total_seconds() / 60
            current_date_metrics += timedelta(days=1)

        availability_percentage = (total_online_in_schedule_minutes / total_scheduled_time_minutes * 100) if total_scheduled_time_minutes > 0 else 0

        analysis_results.append({
            'Agente': agent,
            'Total Tempo Escala (min)': total_scheduled_time_minutes,
            'Total Tempo Online na Escala (min)': total_online_in_schedule_minutes,
            'Disponibilidade na Escala (%)': f"{availability_percentage:.2f}%"
        })
    return pd.DataFrame(analysis_results)

# --- Configuração da Página Streamlit ---
st.set_page_config(layout="wide", page_title="Dashboard de Produtividade de Agentes")

st.title("Dashboard de Produtividade de Agentes")

# --- Inicialização do Session State para Histórico ---
if 'df_real_status_history' not in st.session_state:
    st.session_state.df_real_status_history = pd.DataFrame(columns=[
        'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
        'Hora de término do estado - Carimbo de data/hora', 'Estado',
        'Tempo do agente no estado / Minutos'
    ])
    st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'])
    st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'])

if 'df_escala_history' not in st.session_state:
    st.session_state.df_escala_history = pd.DataFrame(columns=[
        'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Carga',
        'Data Início Vigência', 'Data Fim Vigência'
    ])
    # Garante que as colunas de data sejam datetime64[ns] desde o início
    st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'])
    st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'])

if 'all_unique_agents' not in st.session_state:
    st.session_state.all_unique_agents = set()

if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}

# --- Abas ---
tab_upload, tab_manage_scales, tab_groups, tab_visualization = st.tabs([
    "Upload de Dados", "Gerenciar Escalas", "Gerenciar Grupos", "Visualização e Métricas"
])

with tab_upload:
    st.header("Upload de Arquivos de Dados")

    st.subheader("Upload de Relatório de Status Real")
    uploaded_report_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) para o relatório de status real", type=["xlsx"], key="report_uploader")
    if uploaded_report_file:
        try:
            df_report_raw = pd.read_excel(uploaded_report_file)
            df_processed_report = process_uploaded_report(df_report_raw)

            if not df_processed_report.empty:
                # Remover duplicatas antes de adicionar ao histórico
                # Considera 'Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado' como chaves únicas
                df_processed_report_unique = df_processed_report.drop_duplicates(subset=[
                    'Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado'
                ])

                # Anexar ao histórico, evitando duplicatas com base nas chaves acima
                if not st.session_state.df_real_status_history.empty:
                    combined_df = pd.concat([st.session_state.df_real_status_history, df_processed_report_unique], ignore_index=True)
                    st.session_state.df_real_status_history = combined_df.drop_duplicates(subset=[
                        'Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado'
                    ]).reset_index(drop=True)
                else:
                    st.session_state.df_real_status_history = df_processed_report_unique.reset_index(drop=True)

                st.success("Relatório de status real processado e adicionado ao histórico com sucesso!")
                st.write(f"Total de registros de status real no histórico: {len(st.session_state.df_real_status_history)}")
                st.dataframe(st.session_state.df_real_status_history.head())
            else:
                st.error("Nenhum dado válido encontrado no relatório de status real após o processamento.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo de relatório de status real. Verifique o formato do arquivo. Erro: {e}")

    st.subheader("Upload de Arquivo de Escala")
    uploaded_scale_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) para a escala", type=["xlsx"], key="scale_uploader")
    if uploaded_scale_file:
        st.info("Para o arquivo de escala, você precisa definir a data de início e, opcionalmente, a data de fim de vigência.")
        new_start_effective_date = st.date_input("Data de Início da Vigência da Escala", value=datetime.now().date(), key="scale_start_date_upload")
        new_end_effective_date = st.date_input("Data de Fim da Vigência da Escala (opcional)", value=None, key="scale_end_date_upload")

        if st.button("Processar e Adicionar Escala"):
            try:
                df_scale_raw = pd.read_excel(uploaded_scale_file)
                df_processed_scale = process_uploaded_scale(df_scale_raw, new_start_effective_date, new_end_effective_date)

                if not df_processed_scale.empty:
                    # Lógica para ajustar a Data Fim Vigência de escalas antigas que se sobrepõem
                    # Para cada nova entrada de escala, verificar se há escalas antigas para o mesmo agente/dia da semana
                    # que terminam depois da nova data de início de vigência.

                    # Criar uma cópia para iterar e modificar o original
                    df_escala_history_copy = st.session_state.df_escala_history.copy()

                    for _, new_row in df_processed_scale.iterrows():
                        agent = new_row['Nome do agente']
                        day_num = new_row['Dia da Semana Num']
                        new_start = new_row['Data Início Vigência'].date() # Apenas a data para comparação

                        # Encontrar escalas existentes que seriam substituídas/encerradas pela nova escala
                        overlapping_scales_mask = (
                            (df_escala_history_copy['Nome do agente'] == agent) &
                            (df_escala_history_copy['Dia da Semana Num'] == day_num) &
                            (df_escala_history_copy['Data Início Vigência'].dt.date < new_start) & # Começou antes da nova
                            (
                                (df_escala_history_copy['Data Fim Vigência'].isna()) | # E ainda está ativa
                                (df_escala_history_copy['Data Fim Vigência'].dt.date >= new_start) # Ou termina depois/no mesmo dia da nova
                            )
                        )

                        # Ajustar a Data Fim Vigência das escalas antigas para o dia anterior à nova escala
                        # Usar .loc para evitar SettingWithCopyWarning
                        st.session_state.df_escala_history.loc[overlapping_scales_mask, 'Data Fim Vigência'] = pd.to_datetime(new_start - timedelta(days=1))

                    # Anexar as novas escalas
                    st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, df_processed_scale], ignore_index=True)

                    # Atualizar a lista de agentes únicos a partir da escala
                    st.session_state.all_unique_agents.update(df_processed_scale['Nome do agente'].unique())

                    st.success("Arquivo de escala processado e adicionado ao histórico com sucesso!")
                    st.write(f"Total de registros de escala no histórico: {len(st.session_state.df_escala_history)}")
                    st.dataframe(st.session_state.df_escala_history.head())
                else:
                    st.error("Nenhum dado válido encontrado no arquivo de escala após o processamento.")
            except Exception as e:
                st.error(f"Erro ao processar o arquivo de escala. Verifique o formato do arquivo. Erro: {e}")
                st.exception(e) # Exibe o traceback completo para depuração

    st.subheader("Gerenciamento de Histórico")
    if st.button("Limpar Histórico de Status Real"):
        st.session_state.df_real_status_history = pd.DataFrame(columns=[
            'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado',
            'Tempo do agente no estado / Minutos'
        ])
        st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de início do estado - Carimbo de data/hora'])
        st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(st.session_state.df_real_status_history['Hora de término do estado - Carimbo de data/hora'])
        st.success("Histórico de status real limpo.")
        st.rerun()

    if st.button("Limpar Histórico de Escala"):
        st.session_state.df_escala_history = pd.DataFrame(columns=[
            'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Carga',
            'Data Início Vigência', 'Data Fim Vigência'
        ])
        st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'])
        st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'])
        st.session_state.all_unique_agents = set() # Limpa agentes únicos também
        st.success("Histórico de escala limpo.")
        st.rerun()

with tab_manage_scales:
    st.header("Gerenciar Escalas Individualmente")

    if st.session_state.all_unique_agents:
        selected_agent_for_scale = st.selectbox(
            "Selecione o agente para gerenciar a escala:",
            options=sorted(list(st.session_state.all_unique_agents)),
            key="manage_scale_agent_selector"
        )

        st.subheader(f"Escalas existentes para {selected_agent_for_scale}")
        agent_current_scales = st.session_state.df_escala_history[
            st.session_state.df_escala_history['Nome do agente'] == selected_agent_for_scale
        ].sort_values(by=['Dia da Semana Num', 'Data Início Vigência'])

        if not agent_current_scales.empty:
            st.dataframe(agent_current_scales.style.format({
                'Entrada': lambda t: t.strftime('%H:%M') if t else '',
                'Saída': lambda t: t.strftime('%H:%M') if t else '',
                'Data Início Vigência': '{:%Y-%m-%d}'.format,
                'Data Fim Vigência': lambda d: '{:%Y-%m-%d}'.format(d) if pd.notna(d) else 'Indefinido'
            }), use_container_width=True)
        else:
            st.info(f"Nenhuma escala encontrada para {selected_agent_for_scale}.")

        st.subheader(f"Adicionar/Atualizar Escala para {selected_agent_for_scale}")

        days_of_week_map = {
            "Segunda-feira": 0, "Terça-feira": 1, "Quarta-feira": 2,
            "Quinta-feira": 3, "Sexta-feira": 4, "Sábado": 5, "Domingo": 6
        }
        new_day_of_week = st.selectbox("Dia da Semana", options=list(days_of_week_map.keys()))
        new_day_of_week_num = days_of_week_map[new_day_of_week]

        col1, col2 = st.columns(2)
        with col1:
            new_entry_time_str = st.text_input("Hora de Entrada (HH:MM)", value="09:00")
        with col2:
            new_exit_time_str = st.text_input("Hora de Saída (HH:MM)", value="18:00")

        try:
            new_entry_time = datetime.strptime(new_entry_time_str, '%H:%M').time()
            new_exit_time = datetime.strptime(new_exit_time_str, '%H:%M').time()
        except ValueError:
            st.error("Formato de hora inválido. Use HH:MM.")
            new_entry_time = None
            new_exit_time = None

        new_carga = st.text_input("Carga Horária (opcional)")

        new_start_effective_date = st.date_input("Data de Início da Vigência", value=datetime.now().date(), key="manual_scale_start_date")
        new_end_effective_date = st.date_input("Data de Fim da Vigência (opcional)", value=None, key="manual_scale_end_date")

        if st.button("Salvar Alteração de Escala"):
            if new_entry_time and new_exit_time and selected_agent_for_scale:
                if new_end_effective_date and new_end_effective_date < new_start_effective_date:
                    st.error("A Data de Fim da Vigência não pode ser anterior à Data de Início da Vigência.")
                else:
                    new_scale_entry = {
                        'Nome do agente': selected_agent_for_scale,
                        'Dia da Semana Num': new_day_of_week_num,
                        'Entrada': new_entry_time,
                        'Saída': new_exit_time,
                        'Carga': new_carga if new_carga else None,
                        'Data Início Vigência': pd.to_datetime(new_start_effective_date), # Converter para datetime64[ns]
                        'Data Fim Vigência': pd.to_datetime(new_end_effective_date) if new_end_effective_date else pd.NaT # Converter para datetime64[ns] ou NaT
                    }
                    new_scale_df_row = pd.DataFrame([new_scale_entry])

                    # Lógica para ajustar a Data Fim Vigência de escalas antigas
                    overlapping_scales_mask = (
                        (st.session_state.df_escala_history['Nome do agente'] == selected_agent_for_scale) &
                        (st.session_state.df_escala_history['Dia da Semana Num'] == new_day_of_week_num) &
                        (st.session_state.df_escala_history['Data Início Vigência'].dt.date < new_start_effective_date) &
                        (
                            (st.session_state.df_escala_history['Data Fim Vigência'].isna()) |
                            (st.session_state.df_escala_history['Data Fim Vigência'].dt.date >= new_start_effective_date)
                        )
                    )
                    st.session_state.df_escala_history.loc[overlapping_scales_mask, 'Data Fim Vigência'] = pd.to_datetime(new_start_effective_date - timedelta(days=1))

                    # Adicionar a nova escala
                    st.session_state.df_escala_history = pd.concat([st.session_state.df_escala_history, new_scale_df_row], ignore_index=True)
                    st.success(f"Escala para {selected_agent_for_scale} no(a) {new_day_of_week} com vigência de {new_start_effective_date} a {new_end_effective_date if new_end_effective_date else 'indefinido'} salva com sucesso!")
                    st.rerun()
            else:
                st.warning("Por favor, preencha todos os campos de hora e selecione um agente.")
    else:
        st.info("Faça o upload do arquivo de escala na aba 'Upload de Dados' para gerenciar escalas.")


with tab_groups:
    st.header("Gerenciar Grupos de Agentes")
    if st.session_state.all_unique_agents:
        group_name = st.text_input("Nome do novo grupo:")
        selected_agents_for_group = st.multiselect(
            "Selecione os agentes para este grupo:",
            options=sorted(list(st.session_state.all_unique_agents)),
            key="group_agent_selector"
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
    else:
        st.info("Faça o upload do arquivo de escala na aba 'Upload de Dados' para gerenciar grupos (apenas agentes com escala definida podem ser agrupados).")

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

        # Para a escala, a data mínima de vigência pode ser o limite inferior
        if not st.session_state.df_escala_history.empty and not st.session_state.df_escala_history['Data Início Vigência'].empty:
            min_date_data = min(min_date_data, st.session_state.df_escala_history['Data Início Vigência'].min().date())
            # A data máxima de vigência da escala pode ser no futuro, não é um limite superior para o filtro de dados

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

                            # Garante que a escala não exceda o dia atual para o gráfico
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
                # Ordenar para visualização
                y_order_base = sorted(df_chart_data['Nome do agente'].unique())
                y_order_final = []
                for agent in y_order_base:
                    dates_for_agent = sorted(df_chart_data[df_chart_data['Nome do agente'] == agent]['Data'].unique())
                    for date_obj in dates_for_agent: # Renomeado para evitar conflito com datetime.date
                        date_str = date_obj.strftime('%Y-%m-%d')
                        # Garante que a Escala Planejada venha antes do Status Real para cada dia
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
