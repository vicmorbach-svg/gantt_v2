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
                    'Data Início Vigência': pd.Timestamp(start_effective_date), # Convert to Timestamp
                    'Data Fim Vigência': pd.Timestamp(end_effective_date) if end_effective_date else pd.NaT # Convert to Timestamp or NaT
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
    # current_date é um date object, convertemos para Timestamp para comparação consistente
    current_date_ts = pd.Timestamp(current_date)

    # Filtra escalas para o agente, dia da semana e onde current_date está dentro do período de vigência
    agent_scales = df_escala_history[
        (df_escala_history['Nome do agente'] == agent_name) &
        (df_escala_history['Dia da Semana Num'] == current_date.weekday()) &
        (df_escala_history['Data Início Vigência'] <= current_date_ts) & # Comparação com Timestamp
        (
            (df_escala_history['Data Fim Vigência'].isna()) | # Se Data Fim Vigência é NaT (indefinido)
            (df_escala_history['Data Fim Vigência'] >= current_date_ts) # OU a data de fim é maior ou igual à current_date_ts
        )
    ].copy()

    if agent_scales.empty:
        return pd.DataFrame()

    # Se houver múltiplas escalas válidas, pega a que começou mais recentemente
    # Isso resolve o caso de uma escala ser substituída por outra
    latest_start_date = agent_scales['Data Início Vigência'].max()
    return agent_scales[agent_scales['Data Início Vigência'] == latest_start_date]

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

                    # Tempo total agendado para o dia
                    total_scheduled_time_minutes += (scale_end_dt - scale_start_dt).total_seconds() / 60

                    # Calcular tempo online dentro da escala
                    agent_status_on_day = agent_real_status[
                        (agent_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date_metrics)
                    ]

                    for _, status_row in agent_status_on_day.iterrows():
                        status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                        status_end = status_row['Hora de término do estado - Carimbo de data/hora']
                        status_type = status_row['Estado']

                        # Considerar apenas estados "online" para disponibilidade
                        if status_type in ['Unified online', 'Unified transfers only', 'Unified busy', 'Unified wrap up']:
                            # Interseção do período de status com o período de escala
                            overlap_start = max(scale_start_dt, status_start)
                            overlap_end = min(scale_end_dt, status_end)

                            if overlap_end > overlap_start:
                                total_online_in_schedule_minutes += (overlap_end - overlap_start).total_seconds() / 60

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

# --- Inicialização do Streamlit ---
st.set_page_config(layout="wide", page_title="Análise de Produtividade de Agentes")

# Inicializa session_state
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
    # Garante que as colunas de data sejam datetime64[ns] desde o início
    st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'])
    st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'])

if 'all_unique_agents' not in st.session_state:
    st.session_state.all_unique_agents = set()
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}

st.title("Dashboard de Produtividade de Agentes")

tab_upload, tab_manage_scales, tab_groups, tab_visualization = st.tabs([
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
            # Considera Nome do agente, Hora de início, Estado como identificadores únicos para um status
            df_processed_report_unique = df_processed_report.drop_duplicates(subset=[
                'Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado'
            ])

            # Adicionar apenas novos registros ao histórico
            # Isso é um pouco complexo, uma abordagem mais simples é concatenar e depois dropar duplicatas no histórico total
            st.session_state.df_real_status_history = pd.concat([st.session_state.df_real_status_history, df_processed_report_unique], ignore_index=True)
            st.session_state.df_real_status_history.drop_duplicates(subset=[
                'Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Estado'
            ], inplace=True)
            st.session_state.df_real_status_history.reset_index(drop=True, inplace=True)

            st.success("Relatório de status real processado e adicionado ao histórico!")
            st.dataframe(df_processed_report_unique.head())
        else:
            st.error("Falha ao processar o relatório de status real. Verifique o formato do arquivo.")

    st.subheader("Upload de Arquivo de Escala")
    uploaded_file_scale = st.file_uploader("Escolha um arquivo Excel (.xlsx) para a escala", type=["xlsx"], key="scale_uploader")
    if uploaded_file_scale:
        st.info("Para o arquivo de escala, você precisa definir a data de início e, opcionalmente, a data de fim de vigência.")
        new_start_effective_date = st.date_input("Data de Início de Vigência para esta escala:", value=datetime.now().date(), key="scale_start_date_input")
        new_end_effective_date = st.date_input("Data de Fim de Vigência para esta escala (opcional):", value=None, key="scale_end_date_input")

        if st.button("Processar e Adicionar Escala"):
            df_scale_raw = pd.read_excel(uploaded_file_scale)
            df_processed_scale = process_uploaded_scale(df_scale_raw, new_start_effective_date, new_end_effective_date)

            if not df_processed_scale.empty:
                # Lógica para atualizar escalas existentes:
                # Para cada linha na nova escala, verifica se há escalas antigas que se sobrepõem
                # e ajusta a Data Fim Vigência das escalas antigas.
                df_escala_history_copy = st.session_state.df_escala_history.copy()

                for _, new_scale_row in df_processed_scale.iterrows():
                    agent = new_scale_row['Nome do agente']
                    day_num = new_scale_row['Dia da Semana Num']
                    new_start = new_scale_row['Data Início Vigência'] # Já é Timestamp
                    new_end = new_scale_row['Data Fim Vigência'] # Já é Timestamp ou NaT

                    # Encontra escalas antigas para o mesmo agente e dia da semana que se sobrepõem
                    # e cuja data de início é anterior à nova data de início
                    overlapping_old_scales_idx = df_escala_history_copy[
                        (df_escala_history_copy['Nome do agente'] == agent) &
                        (df_escala_history_copy['Dia da Semana Num'] == day_num) &
                        (df_escala_history_copy['Data Início Vigência'] < new_start) & # Comparação Timestamp com Timestamp
                        (
                            (df_escala_history_copy['Data Fim Vigência'].isna()) | # Se a antiga é indefinida
                            (df_escala_history_copy['Data Fim Vigência'] >= new_start) # Ou termina depois/no mesmo dia da nova
                        )
                    ].index

                    # Ajusta a Data Fim Vigência das escalas antigas
                    if not overlapping_old_scales_idx.empty:
                        df_escala_history_copy.loc[overlapping_old_scales_idx, 'Data Fim Vigência'] = new_start - timedelta(days=1)

                # Adiciona a nova escala ao histórico
                st.session_state.df_escala_history = pd.concat([df_escala_history_copy, df_processed_scale], ignore_index=True)

                # Atualiza a lista de agentes únicos a partir da escala
                st.session_state.all_unique_agents.update(df_processed_scale['Nome do agente'].unique())

                st.success("Arquivo de escala processado e adicionado ao histórico!")
                st.dataframe(df_processed_scale.head())
            else:
                st.error("Falha ao processar o arquivo de escala. Verifique o formato do arquivo.")

    st.subheader("Dados Atuais no Histórico")
    if not st.session_state.df_real_status_history.empty:
        st.write("Últimos registros de Status Real:")
        st.dataframe(st.session_state.df_real_status_history.tail())
    if not st.session_state.df_escala_history.empty:
        st.write("Últimos registros de Escala:")
        st.dataframe(st.session_state.df_escala_history.tail())

    if st.button("Limpar todo o Histórico de Dados (Status e Escala)"):
        st.session_state.df_real_status_history = pd.DataFrame(columns=[
            'Nome do agente', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado',
            'Tempo do agente no estado / Minutos'
        ])
        st.session_state.df_escala_history = pd.DataFrame(columns=[
            'Nome do agente', 'Dia da Semana Num', 'Entrada', 'Saída', 'Carga',
            'Data Início Vigência', 'Data Fim Vigência'
        ])
        st.session_state.df_escala_history['Data Início Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Início Vigência'])
        st.session_state.df_escala_history['Data Fim Vigência'] = pd.to_datetime(st.session_state.df_escala_history['Data Fim Vigência'])
        st.session_state.all_unique_agents = set()
        st.session_state.agent_groups = {}
        st.success("Histórico de dados limpo com sucesso!")
        st.rerun()

with tab_manage_scales:
    st.header("Gerenciar Escalas Individualmente")
    if st.session_state.all_unique_agents:
        selected_agent_for_scale = st.selectbox(
            "Selecione o agente para gerenciar a escala:",
            options=[""] + sorted(list(st.session_state.all_unique_agents)),
            key="manage_scale_agent_select"
        )

        if selected_agent_for_scale:
            st.subheader(f"Escalas para {selected_agent_for_scale}")
            agent_scales_df = st.session_state.df_escala_history[
                st.session_state.df_escala_history['Nome do agente'] == selected_agent_for_scale
            ].sort_values(by=['Dia da Semana Num', 'Data Início Vigência'])

            if not agent_scales_df.empty:
                st.dataframe(agent_scales_df.style.format({
                    'Entrada': lambda t: t.strftime('%H:%M') if t else '',
                    'Saída': lambda t: t.strftime('%H:%M') if t else '',
                    'Data Início Vigência': '{:%Y-%m-%d}'.format,
                    'Data Fim Vigência': lambda d: '{:%Y-%m-%d}'.format(d) if pd.notna(d) else 'Indefinido'
                }), use_container_width=True)
            else:
                st.info("Nenhuma escala definida para este agente.")

            st.subheader("Adicionar/Atualizar Escala")
            col1, col2 = st.columns(2)
            with col1:
                new_day_of_week = st.selectbox("Dia da Semana:", options=["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"])
                new_entrada = st.time_input("Hora de Entrada:", value=time(9, 0))
                new_start_effective_date = st.date_input("Data de Início de Vigência:", value=datetime.now().date())
            with col2:
                new_saida = st.time_input("Hora de Saída:", value=time(18, 0))
                new_carga = st.text_input("Carga (opcional):", value="")
                new_end_effective_date = st.date_input("Data de Fim de Vigência (opcional):", value=None)

            if st.button("Salvar Escala"):
                if new_entrada and new_saida and selected_agent_for_scale and new_day_of_week and new_start_effective_date:
                    day_num_map = {"Segunda":0, "Terça":1, "Quarta":2, "Quinta":3, "Sexta":4, "Sábado":5, "Domingo":6}
                    selected_day_num = day_num_map[new_day_of_week]

                    # Convertendo datas para Timestamp para consistência
                    new_start_ts = pd.Timestamp(new_start_effective_date)
                    new_end_ts = pd.Timestamp(new_end_effective_date) if new_end_effective_date else pd.NaT

                    # Lógica para atualizar escalas existentes:
                    df_escala_history_copy = st.session_state.df_escala_history.copy()

                    # Encontra escalas antigas para o mesmo agente e dia da semana que se sobrepõem
                    # e cuja data de início é anterior à nova data de início
                    overlapping_old_scales_idx = df_escala_history_copy[
                        (df_escala_history_copy['Nome do agente'] == selected_agent_for_scale) &
                        (df_escala_history_copy['Dia da Semana Num'] == selected_day_num) &
                        (df_escala_history_copy['Data Início Vigência'] < new_start_ts) & # Comparação Timestamp com Timestamp
                        (
                            (df_escala_history_copy['Data Fim Vigência'].isna()) | # Se a antiga é indefinida
                            (df_escala_history_copy['Data Fim Vigência'] >= new_start_ts) # Ou termina depois/no mesmo dia da nova
                        )
                    ].index

                    # Ajusta a Data Fim Vigência das escalas antigas
                    if not overlapping_old_scales_idx.empty:
                        df_escala_history_copy.loc[overlapping_old_scales_idx, 'Data Fim Vigência'] = new_start_ts - timedelta(days=1)

                    new_scale_df_row = pd.DataFrame([{
                        'Nome do agente': selected_agent_for_scale,
                        'Dia da Semana Num': selected_day_num,
                        'Entrada': new_entrada,
                        'Saída': new_saida,
                        'Carga': new_carga,
                        'Data Início Vigência': new_start_ts,
                        'Data Fim Vigência': new_end_ts
                    }])
                    st.session_state.df_escala_history = pd.concat([df_escala_history_copy, new_scale_df_row], ignore_index=True)
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
