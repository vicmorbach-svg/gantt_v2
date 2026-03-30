import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time
import numpy as np
import unicodedata # Para normalização de strings

# --- Configurações Iniciais do Streamlit ---
st.set_page_config(layout="wide", page_title="Dashboard de Acompanhamento de Call Center")
st.title("Dashboard de Acompanhamento de Equipe de Call Center")

# --- Funções Auxiliares ---

def normalize_agent_name(name):
    """Normaliza o nome do agente (remove acentos, converte para maiúsculas, remove espaços extras)."""
    if pd.isna(name):
        return name
    name = str(name).strip().upper()
    name = ''.join(c for c in name if c.isalnum() or c.isspace())
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    return name

def calculate_time_overlap(start1, end1, start2, end2):
    """Calcula a sobreposição em segundos entre dois intervalos de tempo."""
    # Garante que os objetos sejam datetime para comparação
    if not isinstance(start1, datetime): start1 = datetime.combine(datetime.min.date(), start1)
    if not isinstance(end1, datetime): end1 = datetime.combine(datetime.min.date(), end1)
    if not isinstance(start2, datetime): start2 = datetime.combine(datetime.min.date(), start2)
    if not isinstance(end2, datetime): end2 = datetime.combine(datetime.min.date(), end2)

    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)

    if overlap_end > overlap_start:
        return (overlap_end - overlap_start).total_seconds()
    return 0

# --- Funções de Processamento de Dados ---

@st.cache_data(ttl=3600) # Cache para 1 hora
def process_uploaded_report(uploaded_file):
    """Processa o arquivo de relatório de status dos agentes."""
    try:
        df = pd.read_excel(uploaded_file, header=None)
        # Mapeamento das colunas do arquivo original
        df.columns = [
            'Nome do agente', 'Dia', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado', 'Duração'
        ]

        # Converte as colunas de data/hora para o tipo datetime
        df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(
            df['Hora de início do estado - Carimbo de data/hora'], errors='coerce'
        )
        df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(
            df['Hora de término do estado - Carimbo de data/hora'], errors='coerce'
        )

        # Preenche NaT na coluna de término com o final do dia de início
        # Isso é importante para status que ainda estão abertos ou não têm um fim definido
        df['Hora de término do estado - Carimbo de data/hora'] = df.apply(
            lambda row: row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
            if pd.isnat(row['Hora de término do estado - Carimbo de data/hora'])
            else row['Hora de término do estado - Carimbo de data/hora'],
            axis=1
        )

        # Remove linhas onde a data de início ainda é NaT após o preenchimento
        df.dropna(subset=['Hora de início do estado - Carimbo de data/hora'], inplace=True)

        # Cria a coluna 'Data' para o dia do evento
        df['Data'] = df['Hora de início do estado - Carimbo de data/hora'].dt.normalize() # Garante que 'Data' seja datetime

        # Normaliza os nomes dos agentes
        df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

        return df
    except Exception as e:
        st.error(f"Erro ao processar o relatório: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600) # Cache para 1 hora
def process_uploaded_scale(uploaded_file):
    """Processa o arquivo de escala dos agentes."""
    try:
        df_escala_raw = pd.read_excel(uploaded_file)

        # Verifica se a coluna 'NOME' existe e a renomeia para 'Nome do agente'
        if 'NOME' in df_escala_raw.columns:
            df_escala_raw.rename(columns={'NOME': 'Nome do agente'}, inplace=True)
        else:
            st.error("Coluna 'NOME' não encontrada no arquivo de escala. Certifique-se de que o cabeçalho está correto.")
            return pd.DataFrame()

        # Normaliza os nomes dos agentes
        df_escala_raw['Nome do agente'] = df_escala_raw['Nome do agente'].apply(normalize_agent_name)

        # Preenche valores NaN nas colunas de horário com '00:00:00' antes da conversão
        df_escala_raw['ENTRADA'] = df_escala_raw['ENTRADA'].fillna('00:00:00')
        df_escala_raw['SAÍDA'] = df_escala_raw['SAÍDA'].fillna('00:00:00')

        # Converte as colunas de horário para o tipo time, usando errors='coerce'
        df_escala_raw['Entrada'] = pd.to_datetime(df_escala_raw['ENTRADA'], format='%H:%M:%S', errors='coerce').dt.time
        df_escala_raw['Saída'] = pd.to_datetime(df_escala_raw['SAÍDA'], format='%H:%M:%S', errors='coerce').dt.time

        # Remove linhas onde a conversão de horário falhou
        df_escala_raw.dropna(subset=['Entrada', 'Saída'], inplace=True)

        # Mapeamento de dias da semana
        day_map = {
            'Seg': 'Monday', 'Ter': 'Tuesday', 'Qua': 'Wednesday', 'Qui': 'Thursday',
            'Sex': 'Friday', 'Sab': 'Saturday', 'Dom': 'Sunday'
        }
        df_escala_processed = []
        for _, row in df_escala_raw.iterrows():
            dias_atendimento = str(row['DIAS DE ATENDIMENTO']).replace(' ', '').split(',')
            for dia_abr in dias_atendimento:
                dia_extenso = day_map.get(dia_abr, None)
                if dia_extenso:
                    df_escala_processed.append({
                        'Nome do agente': row['Nome do agente'],
                        'Dia da Semana': dia_extenso,
                        'Entrada': row['Entrada'],
                        'Saída': row['Saída'],
                        'Grupo': row.get('Grupo', 'Padrão') # Adiciona grupo se existir
                    })
        return pd.DataFrame(df_escala_processed)
    except Exception as e:
        st.error(f"Erro ao processar o arquivo de escala: {e}")
        return pd.DataFrame()

# --- Inicialização do Session State ---
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}

# --- Abas do Aplicativo ---
tab1, tab2, tab3 = st.tabs(["Upload de Dados", "Gerenciar Grupos", "Visualização e Métricas"])

with tab1:
    st.header("📤 Upload de Relatório de Status e Escala")

    st.subheader("Relatório de Status dos Agentes")
    uploaded_report_file = st.file_uploader("Escolha o arquivo Excel do relatório de status", type=["xlsx"], key="report_uploader")
    if uploaded_report_file is not None:
        st.session_state.df_real_status = process_uploaded_report(uploaded_report_file)
        if not st.session_state.df_real_status.empty:
            st.success("Relatório de status carregado e processado com sucesso!")
            st.dataframe(st.session_state.df_real_status.head(), use_container_width=True)

    st.subheader("Arquivo de Escala dos Agentes")
    uploaded_scale_file = st.file_uploader("Escolha o arquivo Excel da escala de agentes", type=["xlsx"], key="scale_uploader")
    if uploaded_scale_file is not None:
        st.session_state.df_escala = process_uploaded_scale(uploaded_scale_file)
        if not st.session_state.df_escala.empty:
            st.success("Arquivo de escala carregado e processado com sucesso!")
            st.dataframe(st.session_state.df_escala.head(), use_container_width=True)

with tab2:
    st.header("👥 Gerenciar Grupos de Agentes")

    if st.session_state.df_real_status.empty and st.session_state.df_escala.empty:
        st.info("Carregue os arquivos de relatório e escala na aba 'Upload de Dados' para gerenciar os agentes.")
    else:
        all_agents_in_data = set()
        if not st.session_state.df_real_status.empty:
            all_agents_in_data.update(st.session_state.df_real_status['Nome do agente'].unique())
        if not st.session_state.df_escala.empty:
            all_agents_in_data.update(st.session_state.df_escala['Nome do agente'].unique())

        if not all_agents_in_data:
            st.info("Nenhum agente encontrado nos dados carregados para criar grupos.")
        else:
            st.subheader("Criar Novo Grupo")
            new_group_name = st.text_input("Nome do novo grupo:")
            if st.button("Criar Grupo"):
                if new_group_name and new_group_name not in st.session_state.agent_groups:
                    st.session_state.agent_groups[new_group_name] = []
                    st.success(f"Grupo '{new_group_name}' criado.")
                elif new_group_name:
                    st.warning(f"Grupo '{new_group_name}' já existe.")
                else:
                    st.warning("Por favor, insira um nome para o grupo.")

            st.subheader("Adicionar/Remover Agentes dos Grupos")
            if st.session_state.agent_groups:
                selected_group_to_manage = st.selectbox("Selecione um grupo para gerenciar:", list(st.session_state.agent_groups.keys()))
                if selected_group_to_manage:
                    current_group_agents = st.session_state.agent_groups[selected_group_to_manage]
                    available_agents = sorted(list(all_agents_in_data - set(current_group_agents)))
                    agents_to_add = st.multiselect(f"Adicionar agentes ao grupo '{selected_group_to_manage}':", available_agents)
                    if st.button(f"Adicionar Selecionados ao Grupo '{selected_group_to_manage}'"):
                        st.session_state.agent_groups[selected_group_to_manage].extend(agents_to_add)
                        st.success(f"Agentes adicionados ao grupo '{selected_group_to_manage}'.")
                        st.experimental_rerun() # Recarrega para atualizar a lista de agentes disponíveis

                    st.write(f"Agentes atualmente no grupo '{selected_group_to_manage}':")
                    if current_group_agents:
                        agents_to_remove = st.multiselect(f"Remover agentes do grupo '{selected_group_to_manage}':", sorted(current_group_agents))
                        if st.button(f"Remover Selecionados do Grupo '{selected_group_to_manage}'"):
                            st.session_state.agent_groups[selected_group_to_manage] = [
                                agent for agent in current_group_agents if agent not in agents_to_remove
                            ]
                            st.success(f"Agentes removidos do grupo '{selected_group_to_manage}'.")
                            st.experimental_rerun()
                    else:
                        st.info("Nenhum agente neste grupo ainda.")

            st.subheader("Grupos Existentes")
            if st.session_state.agent_groups:
                for group_name, agents in st.session_state.agent_groups.items():
                    st.write(f"**{group_name}**: {', '.join(sorted(agents)) if agents else 'Nenhum agente'}")
            else:
                st.info("Nenhum grupo criado ainda.")

with tab3:
    st.header("📈 Visualização e Métricas de Desempenho")

    # --- Barra Lateral de Filtros ---
    st.sidebar.header("Filtros")

    all_agents_normalized = set()
    if not st.session_state.df_real_status.empty:
        all_agents_normalized.update(st.session_state.df_real_status['Nome do agente'].unique())
    if not st.session_state.df_escala.empty:
        all_agents_normalized.update(st.session_state.df_escala['Nome do agente'].unique())

    if not all_agents_normalized:
        st.sidebar.warning("Carregue os dados para ver os agentes disponíveis.")
        selected_agents = []
    else:
        # Filtro por Grupo
        group_options = ["Todos os Agentes"] + list(st.session_state.agent_groups.keys())
        selected_group_filter = st.sidebar.selectbox("Filtrar por Grupo:", group_options)

        if selected_group_filter == "Todos os Agentes":
            agents_for_selection = sorted(list(all_agents_normalized))
        else:
            agents_for_selection = sorted(list(st.session_state.agent_groups.get(selected_group_filter, [])))

        selected_agents = st.sidebar.multiselect(
            "Selecione os Agentes:",
            agents_for_selection,
            default=agents_for_selection[:5] # Seleciona os 5 primeiros por padrão
        )

    # Filtro de Data
    today = datetime.now().date()
    default_start_date = today - timedelta(days=7)
    default_end_date = today

    date_range = st.sidebar.date_input(
        "Selecione o Intervalo de Datas:",
        value=(default_start_date, default_end_date),
        min_value=datetime(2020, 1, 1).date(),
        max_value=today
    )

    start_date = date_range[0] if date_range else None
    end_date = date_range[1] if len(date_range) > 1 else start_date

    if start_date and end_date:
        if (end_date - start_date).days > 14:
            st.sidebar.warning("Intervalo de datas muito longo. Limitando a 14 dias para melhor visualização.")
            end_date = start_date + timedelta(days=13)
            st.sidebar.date_input("Intervalo de Datas Ajustado:", value=(start_date, end_date), disabled=True)

    # --- Comparativo de Agentes entre Relatório e Escala ---
    st.subheader("Comparativo de Agentes entre Relatório e Escala")
    if not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
        agents_in_report = set(st.session_state.df_real_status['Nome do agente'].unique())
        agents_in_scale = set(st.session_state.df_escala['Nome do agente'].unique())

        only_in_report = sorted(list(agents_in_report - agents_in_scale))
        only_in_scale = sorted(list(agents_in_scale - agents_in_report))
        in_both = sorted(list(agents_in_report.intersection(agents_in_scale)))

        if only_in_report:
            st.warning(f"Agentes no relatório, mas **não na escala**: {', '.join(only_in_report)}")
        if only_in_scale:
            st.warning(f"Agentes na escala, mas **não no relatório**: {', '.join(only_in_scale)}")
        if in_both:
            st.success(f"Agentes presentes em ambos (relatório e escala): {', '.join(in_both)}")
        if not only_in_report and not only_in_scale:
            st.info("Todos os agentes estão presentes tanto no relatório quanto na escala.")
    else:
        st.info("Carregue ambos os arquivos (relatório e escala) para ver o comparativo de agentes.")

    # --- Lógica de Filtragem e Preparação de Dados para Gráfico e Métricas ---
    if selected_agents and start_date and end_date and (not st.session_state.df_real_status.empty or not st.session_state.df_escala.empty):
        # Filtrar df_real_status
        filtered_df_real_status = st.session_state.df_real_status[
            (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
            (st.session_state.df_real_status['Data'] >= pd.to_datetime(start_date)) &
            (st.session_state.df_real_status['Data'] <= pd.to_datetime(end_date))
        ].copy()

        # Filtrar df_escala
        filtered_df_escala = st.session_state.df_escala[
            st.session_state.df_escala['Nome do agente'].isin(selected_agents)
        ].copy()

        # Criar DataFrame para o gráfico
        df_chart_data = []

        # Adicionar dados da escala
        for _, row_escala in filtered_df_escala.iterrows():
            for single_date in pd.date_range(start=start_date, end=end_date):
                if single_date.strftime('%A') == row_escala['Dia da Semana']: # Verifica o dia da semana
                    start_dt = datetime.combine(single_date, row_escala['Entrada'])
                    end_dt = datetime.combine(single_date, row_escala['Saída'])
                    # Se a saída for antes da entrada (escala atravessa a meia-noite)
                    if end_dt < start_dt:
                        end_dt += timedelta(days=1)

                    df_chart_data.append({
                        'Nome do agente': row_escala['Nome do agente'],
                        'Data': single_date,
                        'Início': start_dt,
                        'Fim': end_dt,
                        'Tipo': 'Escala',
                        'Estado': 'Escala Prevista'
                    })

        # Adicionar dados de status real (apenas 'Unified online')
        for _, row_status in filtered_df_real_status.iterrows():
            if row_status['Estado'] == 'Unified online':
                start_dt = row_status['Hora de início do estado - Carimbo de data/hora']
                end_dt = row_status['Hora de término do estado - Carimbo de data/hora']

                # Ajusta o fim do status para o final do dia se ele atravessar a meia-noite
                if end_dt.date() > start_dt.date():
                    end_dt = start_dt.replace(hour=23, minute=59, second=59)

                df_chart_data.append({
                    'Nome do agente': row_status['Nome do agente'],
                    'Data': row_status['Data'],
                    'Início': start_dt,
                    'Fim': end_dt,
                    'Tipo': 'Status Real',
                    'Estado': row_status['Estado']
                })

        df_chart = pd.DataFrame(df_chart_data)

        if not df_chart.empty:
            # Garante que a coluna 'Data' é datetime para o .dt accessor
            df_chart['Data'] = pd.to_datetime(df_chart['Data']) # <--- ESSA É A LINHA CRÍTICA ADICIONADA/AJUSTADA

            # Cria uma coluna combinada para o eixo Y do gráfico
            df_chart['Agente_Data_Tipo'] = (
                df_chart['Nome do agente'] + ' - ' +
                df_chart['Data'].dt.strftime('%Y-%m-%d') + ' (' + # Agora .dt funciona
                df_chart['Tipo'] + ')'
            )

            # Ordena para melhor visualização
            df_chart = df_chart.sort_values(by=['Nome do agente', 'Data', 'Tipo'])

            # Calcula a altura do gráfico dinamicamente
            num_unique_rows = df_chart['Agente_Data_Tipo'].nunique()
            chart_height = max(300, num_unique_rows * 30) # Mínimo de 300px, 30px por linha única

            # --- Gráfico de Gantt Comparativo ---
            st.subheader("Gráfico de Escala vs. Status Real (Online)")
            if len(selected_agents) > 10:
                st.warning("Muitos agentes selecionados. Considere reduzir a seleção para uma melhor visualização do gráfico.")

            fig = px.timeline(
                df_chart,
                x_start="Início",
                x_end="Fim",
                y="Agente_Data_Tipo",
                color="Tipo", # Cores diferentes para Escala e Status Real
                color_discrete_map={'Escala': 'blue', 'Status Real': 'green'},
                title="Comparativo de Escala e Status Online por Agente e Dia",
                height=chart_height
            )

            fig.update_yaxes(autorange="reversed") # Inverte a ordem para o mais recente ficar no topo
            fig.update_layout(
                xaxis_title="Horário do Dia",
                yaxis_title="Agente - Data (Tipo)",
                xaxis_range=[datetime.combine(datetime.min.date(), time(0, 0)), datetime.combine(datetime.min.date(), time(23, 59, 59))]
            )
            st.plotly_chart(fig, use_container_width=True)

            # --- Cálculo e Exibição de Métricas ---
            st.subheader("Métricas de Disponibilidade e Aderência")
            metrics_data = []

            for agent in selected_agents:
                agent_df_status = filtered_df_real_status[filtered_df_real_status['Nome do agente'] == agent]
                agent_df_escala = filtered_df_escala[filtered_df_escala['Nome do agente'] == agent]

                for single_date in pd.date_range(start=start_date, end=end_date):
                    day_of_week = single_date.strftime('%A')
                    escala_do_dia = agent_df_escala[agent_df_escala['Dia da Semana'] == day_of_week]

                    total_escala_segundos = 0
                    total_online_na_escala_segundos = 0
                    total_online_segundos = 0

                    # Calcula o tempo total de escala para o dia
                    for _, row_escala in escala_do_dia.iterrows():
                        escala_start_time = row_escala['Entrada']
                        escala_end_time = row_escala['Saída']

                        escala_start_dt = datetime.combine(single_date, escala_start_time)
                        escala_end_dt = datetime.combine(single_date, escala_end_time)
                        if escala_end_dt < escala_start_dt: # Escala atravessa a meia-noite
                            escala_end_dt += timedelta(days=1)
                        total_escala_segundos += (escala_end_dt - escala_start_dt).total_seconds()

                    # Calcula o tempo online e o tempo online dentro da escala
                    status_do_dia = agent_df_status[agent_df_status['Data'] == single_date]
                    for _, row_status in status_do_dia.iterrows():
                        if row_status['Estado'] == 'Unified online':
                            status_start_dt = row_status['Hora de início do estado - Carimbo de data/hora']
                            status_end_dt = row_status['Hora de término do estado - Carimbo de data/hora']

                            # Ajusta o fim do status para o final do dia se ele atravessar a meia-noite
                            if status_end_dt.date() > status_start_dt.date():
                                status_end_dt = status_start_dt.replace(hour=23, minute=59, second=59)

                            total_online_segundos += (status_end_dt - status_start_dt).total_seconds()

                            for _, row_escala in escala_do_dia.iterrows():
                                escala_start_time = row_escala['Entrada']
                                escala_end_time = row_escala['Saída']

                                escala_start_dt = datetime.combine(single_date, escala_start_time)
                                escala_end_dt = datetime.combine(single_date, escala_end_time)
                                if escala_end_dt < escala_start_dt: # Escala atravessa a meia-noite
                                    escala_end_dt += timedelta(days=1)

                                total_online_na_escala_segundos += calculate_time_overlap(
                                    status_start_dt, status_end_dt,
                                    escala_start_dt, escala_end_dt
                                )

                    disponibilidade = (total_online_na_escala_segundos / total_escala_segundos * 100) if total_escala_segundos > 0 else 0
                    aderencia = (total_online_na_escala_segundos / total_online_segundos * 100) if total_online_segundos > 0 else 0

                    metrics_data.append({
                        'Agente': agent,
                        'Data': single_date.strftime('%Y-%m-%d'),
                        'Disponibilidade (%)': disponibilidade,
                        'Aderência (%)': aderencia
                    })

            if metrics_data:
                df_metrics = pd.DataFrame(metrics_data)

                # Agregação por agente (média diária)
                df_metrics_agg = df_metrics.groupby('Agente').agg(
                    {'Disponibilidade (%)': 'mean', 'Aderência (%)': 'mean'}
                ).reset_index()

                st.dataframe(df_metrics_agg.style.format({'Disponibilidade (%)': "{:.2f}%", 'Aderência (%)': "{:.2f}%"}), use_container_width=True)
            else:
                st.info("Nenhuma métrica calculada para os filtros selecionados. Verifique se há dados de escala e status real.")
        else:
            st.info("Não há dados de status real e/ou escala para calcular as métricas com os filtros selecionados.")
    else:
        st.info("Selecione os agentes e o intervalo de datas para visualizar o gráfico e as métricas.")
