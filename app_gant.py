import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time
import numpy as np

# --- Configurações Iniciais do Streamlit ---
st.set_page_config(layout="wide", page_title="Dashboard de Acompanhamento de Call Center")
st.title("Dashboard de Acompanhamento de Equipe de Call Center")

# --- Funções de Processamento de Dados ---

def process_uploaded_report(uploaded_file):
    """Processa o arquivo de relatório de status do agente."""
    try:
        # Ler o arquivo sem cabeçalho e atribuir nomes de coluna manualmente
        df = pd.read_excel(uploaded_file, header=None)

        # Mapear as colunas conforme o arquivo de exemplo
        df.columns = [
            'Nome do agente',
            'Dia',
            'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora',
            'Status',
            'Duração (min)'
        ]

        # Converter colunas de data/hora para o formato datetime, com tratamento de erros
        df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(
            df['Hora de início do estado - Carimbo de data/hora'], errors='coerce'
        )
        df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(
            df['Hora de término do estado - Carimbo de data/hora'], errors='coerce'
        )

        # Preencher NaT (Not a Time) na coluna de término com o início do dia seguinte
        # ou o final do dia atual se o início for o último registro do dia
        df['Hora de término do estado - Carimbo de data/hora'] = df.apply(
            lambda row: row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
            if pd.isna(row['Hora de término do estado - Carimbo de data/hora'])
            else row['Hora de término do estado - Carimbo de data/hora'],
            axis=1
        )

        # Remover linhas onde a data de início é inválida
        df.dropna(subset=['Hora de início do estado - Carimbo de data/hora'], inplace=True)

        # Ajustar a coluna 'Dia' para ser a data completa do início do estado
        df['Data'] = df['Hora de início do estado - Carimbo de data/hora'].dt.normalize()

        # Criar uma coluna 'ID do Agente' para o Plotly Gantt
        df['ID do Agente'] = df['Nome do agente'] + ' - ' + df['Data'].dt.strftime('%Y-%m-%d')

        st.session_state.df_real_status = df
        st.success("Relatório de status carregado e processado com sucesso!")
    except Exception as e:
        st.error(f"Erro ao processar o relatório: {e}")
        st.info("Verifique se o arquivo está no formato esperado e se as colunas de data/hora estão corretas.")

def process_uploaded_scale(uploaded_file):
    """Processa o arquivo de escala dos agentes."""
    try:
        df_escala_raw = pd.read_excel(uploaded_file)

        # Renomear a coluna 'NOME' para 'Nome do agente' para consistência
        if 'NOME' in df_escala_raw.columns:
            df_escala_raw.rename(columns={'NOME': 'Nome do agente'}, inplace=True)
        else:
            st.error("Coluna 'NOME' não encontrada no arquivo de escala. Verifique o cabeçalho.")
            return

        # Converter 'ENTRADA' e 'SAÍDA' para objetos time
        df_escala_raw['Entrada'] = pd.to_datetime(df_escala_raw['ENTRADA'], format='%H:%M:%S', errors='coerce').dt.time
        df_escala_raw['Saída'] = pd.to_datetime(df_escala_raw['SAÍDA'], format='%H:%M:%S', errors='coerce').dt.time

        df_escala_raw.dropna(subset=['Entrada', 'Saída'], inplace=True)

        # Expandir a escala para cada dia da semana
        escala_expandida = []
        dias_semana_map = {
            'Seg': 0, 'Ter': 1, 'Qua': 2, 'Qui': 3, 'Sex': 4, 'Sab': 5, 'Dom': 6
        }

        for index, row in df_escala_raw.iterrows():
            dias_atendimento_str = str(row['DIAS DE ATENDIMENTO'])
            dias_atendimento = [d.strip() for d in dias_atendimento_str.split(',')]

            for dia_str in dias_atendimento:
                if dia_str in dias_semana_map:
                    escala_expandida.append({
                        'Nome do agente': row['Nome do agente'],
                        'Dia da Semana Num': dias_semana_map[dia_str],
                        'Dia da Semana': dia_str,
                        'Entrada': row['Entrada'],
                        'Saída': row['Saída'],
                        'Grupo': row.get('GRUPO', 'Não Atribuído') # Adiciona a coluna Grupo se existir
                    })

        st.session_state.df_escala = pd.DataFrame(escala_expandida)
        st.success("Escala carregada e processada com sucesso!")
    except Exception as e:
        st.error(f"Erro ao processar o arquivo de escala: {e}")
        st.info("Verifique se o arquivo está no formato esperado (colunas NOME, DIAS DE ATENDIMENTO, ENTRADA, SAÍDA).")


# --- Inicialização do Session State ---
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame(columns=['Nome do agente', 'Dia da Semana Num', 'Dia da Semana', 'Entrada', 'Saída', 'Grupo'])
if 'grupos_agentes' not in st.session_state:
    st.session_state.grupos_agentes = {
        '6h20min': [],
        '8h12min': []
    }

# --- Abas do Aplicativo ---
tab1, tab2, tab3 = st.tabs(["Upload de Relatório", "Criar/Editar Escala", "Visualização da Escala"])

with tab1:
    st.header("Upload do Relatório de Status")
    uploaded_file_report = st.file_uploader("Escolha um arquivo Excel do relatório de status", type=["xlsx"])
    if uploaded_file_report is not None:
        process_uploaded_report(uploaded_file_report)

with tab2:
    st.header("Criar/Editar Escala de Agentes")

    st.subheader("Upload de Arquivo de Escala (Excel)")
    uploaded_file_scale = st.file_uploader("Escolha um arquivo Excel com a escala", type=["xlsx"])
    if uploaded_file_scale is not None:
        process_uploaded_scale(uploaded_file_scale)

    st.subheader("Adicionar Escala Manualmente")

    # Obter nomes de agentes do relatório de status, se disponível
    all_agents_in_data = set()
    if not st.session_state.df_real_status.empty:
        all_agents_in_data.update(st.session_state.df_real_status['Nome do agente'].unique())

    # Obter nomes de agentes da escala existente, se disponível
    if not st.session_state.df_escala.empty:
        all_agents_in_data.update(st.session_state.df_escala['Nome do agente'].unique())

    # Converter para lista e ordenar para o selectbox
    agent_options = sorted(list(all_agents_in_data))

    if not agent_options:
        st.warning("Carregue o relatório de status ou o arquivo de escala para popular a lista de agentes.")
        new_agent_name = st.text_input("Ou digite o nome do novo agente:")
        selected_agent_for_scale = new_agent_name if new_agent_name else ""
    else:
        selected_agent_for_scale = st.selectbox("Selecione o agente", [""] + agent_options)
        new_agent_name = st.text_input("Ou digite o nome do novo agente (se não estiver na lista):")
        if new_agent_name:
            selected_agent_for_scale = new_agent_name

    dias_semana_options = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
    selected_dias_semana = st.multiselect("Dias da Semana", dias_semana_options)

    col1, col2 = st.columns(2)
    with col1:
        start_time = st.time_input("Hora de Entrada", value=time(9, 0))
    with col2:
        end_time = st.time_input("Hora de Saída", value=time(18, 0))

    if st.button("Adicionar Escala"):
        if selected_agent_for_scale and selected_dias_semana and start_time and end_time:
            dias_semana_map = {
                'Seg': 0, 'Ter': 1, 'Qua': 2, 'Qui': 3, 'Sex': 4, 'Sab': 5, 'Dom': 6
            }
            for dia_str in selected_dias_semana:
                new_entry = {
                    'Nome do agente': selected_agent_for_scale,
                    'Dia da Semana Num': dias_semana_map[dia_str],
                    'Dia da Semana': dia_str,
                    'Entrada': start_time,
                    'Saída': end_time,
                    'Grupo': 'Não Atribuído' # Default para manual
                }
                st.session_state.df_escala = pd.concat([st.session_state.df_escala, pd.DataFrame([new_entry])], ignore_index=True)
            st.success(f"Escala adicionada para {selected_agent_for_scale} nos dias {', '.join(selected_dias_semana)}.")
        else:
            st.warning("Preencha todos os campos para adicionar a escala.")

    st.subheader("Gerenciar Grupos de Agentes")
    group_name_input = st.text_input("Nome do novo grupo (ex: '6h20min', '8h12min')")
    if st.button("Criar Grupo"):
        if group_name_input and group_name_input not in st.session_state.grupos_agentes:
            st.session_state.grupos_agentes[group_name_input] = []
            st.success(f"Grupo '{group_name_input}' criado.")
        elif group_name_input in st.session_state.grupos_agentes:
            st.warning(f"Grupo '{group_name_input}' já existe.")
        else:
            st.warning("Digite um nome para o grupo.")

    if st.session_state.grupos_agentes:
        selected_group_to_manage = st.selectbox("Selecione um grupo para gerenciar", list(st.session_state.grupos_agentes.keys()))

        # Obter todos os agentes disponíveis (do relatório e da escala)
        all_available_agents = set()
        if not st.session_state.df_real_status.empty:
            all_available_agents.update(st.session_state.df_real_status['Nome do agente'].unique())
        if not st.session_state.df_escala.empty:
            all_available_agents.update(st.session_state.df_escala['Nome do agente'].unique())

        # Agentes já no grupo selecionado
        agents_in_current_group = set(st.session_state.grupos_agentes[selected_group_to_manage])

        # Agentes que não estão no grupo selecionado
        agents_not_in_current_group = sorted(list(all_available_agents - agents_in_current_group))

        st.write(f"Agentes no grupo '{selected_group_to_manage}': {', '.join(agents_in_current_group) if agents_in_current_group else 'Nenhum'}")

        if agents_not_in_current_group:
            agent_to_add_to_group = st.selectbox(f"Adicionar agente ao grupo '{selected_group_to_manage}'", [""] + agents_not_in_current_group)
            if st.button(f"Adicionar {agent_to_add_to_group} ao grupo"):
                if agent_to_add_to_group:
                    st.session_state.grupos_agentes[selected_group_to_manage].append(agent_to_add_to_group)
                    # Atualizar a coluna 'Grupo' no df_escala para este agente
                    st.session_state.df_escala.loc[st.session_state.df_escala['Nome do agente'] == agent_to_add_to_group, 'Grupo'] = selected_group_to_manage
                    st.success(f"{agent_to_add_to_group} adicionado ao grupo '{selected_group_to_manage}'.")
                    st.rerun()
        else:
            st.info(f"Todos os agentes disponíveis já estão no grupo '{selected_group_to_manage}' ou não há agentes disponíveis para adicionar.")

        if agents_in_current_group:
            agent_to_remove_from_group = st.selectbox(f"Remover agente do grupo '{selected_group_to_manage}'", [""] + sorted(list(agents_in_current_group)))
            if st.button(f"Remover {agent_to_remove_from_group} do grupo"):
                if agent_to_remove_from_group:
                    st.session_state.grupos_agentes[selected_group_to_manage].remove(agent_to_remove_to_group)
                    # Atualizar a coluna 'Grupo' no df_escala para este agente
                    st.session_state.df_escala.loc[st.session_state.df_escala['Nome do agente'] == agent_to_remove_from_group, 'Grupo'] = 'Não Atribuído'
                    st.success(f"{agent_to_remove_from_group} removido do grupo '{selected_group_to_manage}'.")
                    st.rerun()

        if st.button(f"Remover Grupo '{selected_group_to_manage}'"):
            if selected_group_to_manage in st.session_state.grupos_agentes:
                # Antes de remover o grupo, resetar o grupo dos agentes no df_escala
                st.session_state.df_escala.loc[st.session_state.df_escala['Grupo'] == selected_group_to_manage, 'Grupo'] = 'Não Atribuído'
                del st.session_state.grupos_agentes[selected_group_to_manage]
                st.success(f"Grupo '{selected_group_to_manage}' removido.")
                st.rerun()


with tab3:
    st.header("Visualização da Escala e Status Real")

    if st.session_state.df_real_status.empty and st.session_state.df_escala.empty:
        st.warning("Por favor, carregue o relatório de status e/ou a escala dos agentes nas abas anteriores.")
    else:
        # --- Filtros na Barra Lateral ---
        st.sidebar.header("Filtros")

        # Filtro por Agente
        all_agents = set()
        if not st.session_state.df_real_status.empty:
            all_agents.update(st.session_state.df_real_status['Nome do agente'].unique())
        if not st.session_state.df_escala.empty:
            all_agents.update(st.session_state.df_escala['Nome do agente'].unique())

        selected_agents = st.sidebar.multiselect(
            "Filtrar por Agente",
            sorted(list(all_agents))
        )

        # Filtro por Grupo
        group_options = ["Todos"] + list(st.session_state.grupos_agentes.keys())
        selected_group = st.sidebar.selectbox("Filtrar por Grupo", group_options)

        # Filtro por Data
        min_date = datetime(2026, 1, 1).date() # Data mínima padrão
        max_date = datetime(2026, 12, 31).date() # Data máxima padrão

        if not st.session_state.df_real_status.empty:
            min_date_report = st.session_state.df_real_status['Data'].min().date()
            max_date_report = st.session_state.df_real_status['Data'].max().date()
            min_date = min(min_date, min_date_report)
            max_date = max(max_date, max_date_report)

        date_range = st.sidebar.date_input(
            "Selecione o Intervalo de Datas",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )

        start_date = date_range[0]
        end_date = date_range[1] if len(date_range) > 1 else date_range[0]

        # --- Aplicação dos Filtros ---
        filtered_df_real_status = st.session_state.df_real_status.copy()
        filtered_df_escala = st.session_state.df_escala.copy()

        if selected_agents:
            filtered_df_real_status = filtered_df_real_status[filtered_df_real_status['Nome do agente'].isin(selected_agents)]
            # CORREÇÃO AQUI: Usar 'Nome do agente' para filtrar df_escala
            filtered_df_escala = filtered_df_escala[filtered_df_escala['Nome do agente'].isin(selected_agents)]

        if selected_group != "Todos":
            agents_in_group = st.session_state.grupos_agentes.get(selected_group, [])
            if agents_in_group:
                filtered_df_real_status = filtered_df_real_status[filtered_df_real_status['Nome do agente'].isin(agents_in_group)]
                # CORREÇÃO AQUI: Usar 'Nome do agente' para filtrar df_escala
                filtered_df_escala = filtered_df_escala[filtered_df_escala['Nome do agente'].isin(agents_in_group)]
            else:
                filtered_df_real_status = pd.DataFrame() # Nenhum agente no grupo
                filtered_df_escala = pd.DataFrame() # Nenhum agente no grupo

        # Filtrar por data para o status real
        filtered_df_real_status = filtered_df_real_status[
            (filtered_df_real_status['Data'].dt.date >= start_date) &
            (filtered_df_real_status['Data'].dt.date <= end_date)
        ]

        # --- Preparar dados para o gráfico Gantt ---
        gantt_data = []

        # Adicionar dados da escala
        if not filtered_df_escala.empty:
            for index, row in filtered_df_escala.iterrows():
                # Gerar datas para cada dia da semana no intervalo selecionado
                current_date = start_date
                while current_date <= end_date:
                    if current_date.weekday() == row['Dia da Semana Num']:
                        start_dt = datetime.combine(current_date, row['Entrada'])
                        end_dt = datetime.combine(current_date, row['Saída'])
                        gantt_data.append({
                            'Agente': row['Nome do agente'],
                            'Data': current_date,
                            'Tipo': 'Escala',
                            'Status': 'Escala Prevista',
                            'Start': start_dt,
                            'Finish': end_dt,
                            'Cor': 'lightgray' # Cor para a escala
                        })
                    current_date += timedelta(days=1)

        # Adicionar dados de status real
        if not filtered_df_real_status.empty:
            for index, row in filtered_df_real_status.iterrows():
                gantt_data.append({
                    'Agente': row['Nome do agente'],
                    'Data': row['Data'].date(),
                    'Tipo': 'Real',
                    'Status': row['Status'],
                    'Start': row['Hora de início do estado - Carimbo de data/hora'],
                    'Finish': row['Hora de término do estado - Carimbo de data/hora'],
                    'Cor': 'blue' if row['Status'] == 'Unified online' else 'red' # Cores para status real
                })

        df_gantt = pd.DataFrame(gantt_data)

        if not df_gantt.empty:
            # Ordenar para melhor visualização
            df_gantt = df_gantt.sort_values(by=['Agente', 'Data', 'Start'])

            # Criar o gráfico Gantt
            fig = px.timeline(
                df_gantt,
                x_start="Start",
                x_end="Finish",
                y="Agente",
                color="Status",
                facet_row="Data",
                title="Comparativo de Escala e Status Real por Agente",
                color_discrete_map={
                    'Escala Prevista': 'lightgray',
                    'Unified online': 'green',
                    'Unified away': 'orange',
                    'Unified offline': 'red',
                    'Unified transfers only': 'purple',
                    'Unified wrap up': 'brown'
                }
            )
            fig.update_yaxes(autorange="reversed") # Inverte a ordem para o agente mais recente ficar no topo
            fig.update_layout(height=600 + len(df_gantt['Agente'].unique()) * 50) # Ajusta altura dinamicamente
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhum dado para exibir com os filtros selecionados.")

        # --- Cálculo e Exibição de Métricas de Disponibilidade e Aderência ---
        st.subheader("Métricas de Disponibilidade e Aderência")

        if not filtered_df_real_status.empty and not filtered_df_escala.empty:
            metrics_data = []

            # Iterar por cada agente e cada dia no intervalo filtrado
            for agent_name in filtered_df_real_status['Nome do agente'].unique():
                for current_date in pd.date_range(start_date, end_date):
                    current_date = current_date.date() # Apenas a data

                    # Escala para o agente no dia atual
                    escala_do_dia = filtered_df_escala[
                        (filtered_df_escala['Nome do agente'] == agent_name) &
                        (filtered_df_escala['Dia da Semana Num'] == current_date.weekday())
                    ]

                    if not escala_do_dia.empty:
                        escala_start_time = datetime.combine(current_date, escala_do_dia['Entrada'].iloc[0])
                        escala_end_time = datetime.combine(current_date, escala_do_dia['Saída'].iloc[0])

                        # Garantir que a escala não passe da meia-noite para o cálculo simples
                        if escala_end_time < escala_start_time:
                            escala_end_time += timedelta(days=1)

                        total_tempo_escala_segundos = (escala_end_time - escala_start_time).total_seconds()

                        # Status real do agente no dia atual
                        status_real_do_dia = filtered_df_real_status[
                            (filtered_df_real_status['Nome do agente'] == agent_name) &
                            (filtered_df_real_status['Data'].dt.date == current_date)
                        ].copy()

                        total_online_na_escala_segundos = 0
                        total_online_segundos = 0

                        for idx, status_row in status_real_do_dia.iterrows():
                            status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                            status_end = status_row['Hora de término do estado - Carimbo de data/hora']

                            # Garantir que o status não passe da meia-noite para o cálculo simples
                            if status_end < status_start:
                                status_end += timedelta(days=1)

                            if status_row['Status'] == 'Unified online':
                                total_online_segundos += (status_end - status_start).total_seconds()

                                # Calcular interseção com a escala
                                intersecao_start = max(status_start, escala_start_time)
                                intersecao_end = min(status_end, escala_end_time)

                                if intersecao_end > intersecao_start:
                                    total_online_na_escala_segundos += (intersecao_end - intersecao_start).total_seconds()

                        # Evitar divisão por zero
                        disponibilidade = (total_online_na_escala_segundos / total_tempo_escala_segundos) if total_tempo_escala_segundos > 0 else 0
                        aderencia = (total_online_na_escala_segundos / total_online_segundos) if total_online_segundos > 0 else 0

                        metrics_data.append({
                            'Agente': agent_name,
                            'Data': current_date,
                            'Disponibilidade (%)': disponibilidade * 100,
                            'Aderência (%)': aderencia * 100
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
