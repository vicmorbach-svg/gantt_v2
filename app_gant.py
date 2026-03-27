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
        return None
    name = str(name).strip().upper()
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    return name

def process_uploaded_report(uploaded_file):
    """Processa o arquivo de relatório de status do agente."""
    try:
        df = pd.read_excel(uploaded_file, header=None)

        # Renomear colunas com base na estrutura fornecida
        # Assumindo que a primeira coluna é o nome do agente, a segunda o dia, etc.
        # Ajuste estes índices se a estrutura do seu Excel mudar.
        df.columns = [
            'Nome do agente', 'Dia', 'Hora de início do estado - Carimbo de data/hora',
            'Hora de término do estado - Carimbo de data/hora', 'Estado', 'Outra Coluna' # Ajuste 'Outra Coluna' se houver mais
        ]

        # Remover a coluna 'Outra Coluna' se ela não for necessária
        if 'Outra Coluna' in df.columns:
            df = df.drop(columns=['Outra Coluna'])

        # Normalizar nomes dos agentes
        df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

        # Converter colunas de data/hora
        df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(
            df['Hora de início do estado - Carimbo de data/hora'], errors='coerce'
        )
        df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(
            df['Hora de término do estado - Carimbo de data/hora'], errors='coerce'
        )

        # Preencher NaT em 'Hora de término' para status que ainda estão ativos
        # Preenche com o final do dia da 'Hora de início'
        for idx, row in df.iterrows():
            if pd.isna(row['Hora de término do estado - Carimbo de data/hora']) and pd.notna(row['Hora de início do estado - Carimbo de data/hora']):
                df.at[idx, 'Hora de término do estado - Carimbo de data/hora'] = \
                    row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)

        # Remover linhas onde a conversão de data/hora falhou para o início
        df.dropna(subset=['Hora de início do estado - Carimbo de data/hora'], inplace=True)

        st.success("Relatório de status carregado e processado com sucesso!")
        return df
    except Exception as e:
        st.error(f"Erro ao processar o relatório de status: {e}")
        return None

def process_uploaded_scale(uploaded_file):
    """Processa o arquivo de escala de agentes."""
    try:
        df_escala_raw = pd.read_excel(uploaded_file)

        # Verificar se a coluna 'NOME' existe e renomeá-la para 'Nome do agente'
        if 'NOME' in df_escala_raw.columns:
            df_escala_raw.rename(columns={'NOME': 'Nome do agente'}, inplace=True)
        else:
            st.error("A coluna 'NOME' não foi encontrada no arquivo de escala. Por favor, verifique o cabeçalho.")
            return None

        # Normalizar nomes dos agentes
        df_escala_raw['Nome do agente'] = df_escala_raw['Nome do agente'].apply(normalize_agent_name)

        # Preencher NaN nas colunas de horário com um valor padrão antes da conversão
        df_escala_raw['ENTRADA'] = df_escala_raw['ENTRADA'].fillna('00:00:00')
        df_escala_raw['SAÍDA'] = df_escala_raw['SAÍDA'].fillna('00:00:00')

        # Converter 'ENTRADA' e 'SAÍDA' para objetos de tempo
        df_escala_raw['ENTRADA'] = pd.to_datetime(df_escala_raw['ENTRADA'], format='%H:%M:%S', errors='coerce').dt.time
        df_escala_raw['SAÍDA'] = pd.to_datetime(df_escala_raw['SAÍDA'], format='%H:%M:%S', errors='coerce').dt.time

        # Remover linhas onde a conversão de horário falhou
        df_escala_raw.dropna(subset=['ENTRADA', 'SAÍDA'], inplace=True)

        # Expandir a escala para cada dia da semana
        df_escala_expanded = pd.DataFrame()
        dias_map = {
            'SEG': 0, 'TER': 1, 'QUA': 2, 'QUI': 3, 'SEX': 4, 'SAB': 5, 'DOM': 6,
            'SEGUNDA': 0, 'TERÇA': 1, 'QUARTA': 2, 'QUINTA': 3, 'SEXTA': 4, 'SÁBADO': 5, 'DOMINGO': 6
        }

        for idx, row in df_escala_raw.iterrows():
            dias_atendimento_str = str(row['DIAS DE ATENDIMENTO']).upper().replace(' ', '').replace('.', '')

            # Tratar casos como "Seg e Qui loja, Ter, Qua e Sex Call"
            # Simplificar para apenas os dias da semana
            dias_validos = []
            for dia_abbr, dia_num in dias_map.items():
                if dia_abbr in dias_atendimento_str:
                    dias_validos.append(dia_num)

            for dia_num in dias_validos:
                temp_row = row.copy()
                temp_row['Dia da Semana Num'] = dia_num
                df_escala_expanded = pd.concat([df_escala_expanded, pd.DataFrame([temp_row])], ignore_index=True)

        st.success("Escala de agentes carregada e processada com sucesso!")
        return df_escala_expanded
    except Exception as e:
        st.error(f"Erro ao processar o arquivo de escala: {e}")
        return None

# --- Inicialização do Session State ---
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = None
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = None
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {} # Dicionário para armazenar grupos de agentes

# --- Abas do Aplicativo ---
tab1, tab2, tab3 = st.tabs(["⬆️ Upload de Dados", "📝 Gerenciar Grupos", "📊 Visualização e Métricas"])

with tab1:
    st.header("Upload de Relatório de Status e Escala")

    st.subheader("Upload do Relatório de Status dos Agentes")
    uploaded_report_file = st.file_uploader("Escolha um arquivo Excel para o relatório de status", type=["xlsx"], key="report_uploader")
    if uploaded_report_file is not None:
        st.session_state.df_real_status = process_uploaded_report(uploaded_report_file)

    st.subheader("Upload do Arquivo de Escala dos Agentes")
    uploaded_scale_file = st.file_uploader("Escolha um arquivo Excel para a escala dos agentes", type=["xlsx"], key="scale_uploader")
    if uploaded_scale_file is not None:
        st.session_state.df_escala = process_uploaded_scale(uploaded_scale_file)

with tab2:
    st.header("Gerenciar Grupos de Agentes")

    st.write("Crie e edite grupos de agentes para facilitar a filtragem.")

    # Obter todos os agentes únicos de ambos os DataFrames (se existirem)
    all_agents_combined = set()
    if st.session_state.df_real_status is not None:
        all_agents_combined.update(st.session_state.df_real_status['Nome do agente'].dropna().unique())
    if st.session_state.df_escala is not None:
        all_agents_combined.update(st.session_state.df_escala['Nome do agente'].dropna().unique())

    all_agents_list = sorted(list(all_agents_combined))

    if not all_agents_list:
        st.warning("Carregue os arquivos de relatório e/ou escala na aba 'Upload de Dados' para gerenciar agentes.")
    else:
        group_name = st.text_input("Nome do novo grupo:")
        selected_agents_for_group = st.multiselect(
            "Selecione os agentes para este grupo:",
            options=all_agents_list,
            key="group_agent_selector"
        )

        if st.button("Salvar Grupo"):
            if group_name and selected_agents_for_group:
                st.session_state.agent_groups[group_name] = selected_agents_for_group
                st.success(f"Grupo '{group_name}' salvo com {len(selected_agents_for_group)} agentes.")
            else:
                st.warning("Por favor, insira um nome para o grupo e selecione pelo menos um agente.")

        st.subheader("Grupos Existentes")
        if st.session_state.agent_groups:
            for group, agents in st.session_state.agent_groups.items():
                st.write(f"**{group}**: {', '.join(agents)}")

            group_to_delete = st.selectbox("Selecione um grupo para excluir:", options=[""] + list(st.session_state.agent_groups.keys()))
            if st.button("Excluir Grupo") and group_to_delete:
                del st.session_state.agent_groups[group_to_delete]
                st.success(f"Grupo '{group_to_delete}' excluído.")
                st.rerun()
        else:
            st.info("Nenhum grupo criado ainda.")

with tab3:
    st.header("Visualização da Escala e Status Real")

    # --- Barra Lateral para Filtros ---
    st.sidebar.header("Filtros")

    # Obter todos os agentes únicos de ambos os DataFrames (se existirem)
    all_agents_combined_for_filter = set()
    if st.session_state.df_real_status is not None:
        all_agents_combined_for_filter.update(st.session_state.df_real_status['Nome do agente'].dropna().unique())
    if st.session_state.df_escala is not None:
        all_agents_combined_for_filter.update(st.session_state.df_escala['Nome do agente'].dropna().unique())

    all_agents_list_for_filter = sorted(list(all_agents_combined_for_filter))

    selected_agents = st.sidebar.multiselect(
        "Selecione os Agentes:",
        options=all_agents_list_for_filter,
        default=all_agents_list_for_filter if len(all_agents_list_for_filter) <= 10 else [] # Limita default para não sobrecarregar
    )

    # Filtro por grupo
    group_options = ["Todos"] + list(st.session_state.agent_groups.keys())
    selected_group = st.sidebar.selectbox("Filtrar por Grupo:", options=group_options)

    if selected_group != "Todos" and selected_group in st.session_state.agent_groups:
        agents_in_group = st.session_state.agent_groups[selected_group]
        # Intersect selected_agents with agents_in_group
        selected_agents = list(set(selected_agents) & set(agents_in_group))
        if not selected_agents:
            st.sidebar.warning(f"Nenhum agente selecionado do grupo '{selected_group}' está nos dados carregados.")

    today = datetime.now().date()
    start_date = st.sidebar.date_input("Data de Início:", value=today - timedelta(days=7))
    end_date = st.sidebar.date_input("Data de Término:", value=today)

    # Limitar o intervalo de datas para o gráfico
    max_days_for_chart = 14
    if (end_date - start_date).days > max_days_for_chart:
        st.sidebar.warning(f"Intervalo de datas muito grande para o gráfico. Limitando a {max_days_for_chart} dias a partir da data de início.")
        end_date = start_date + timedelta(days=max_days_for_chart)
        st.sidebar.date_input("Data de Término (ajustada):", value=end_date, disabled=True) # Mostra a data ajustada

    # --- Comparativo de Agentes entre Arquivos ---
    st.subheader("Comparativo de Agentes entre Relatório e Escala")

    agents_in_report = set()
    if st.session_state.df_real_status is not None:
        agents_in_report = set(st.session_state.df_real_status['Nome do agente'].dropna().unique())

    agents_in_scale = set()
    if st.session_state.df_escala is not None:
        agents_in_scale = set(st.session_state.df_escala['Nome do agente'].dropna().unique())

    if agents_in_report or agents_in_scale:
        agents_only_in_report = sorted(list(agents_in_report - agents_in_scale))
        agents_only_in_scale = sorted(list(agents_in_scale - agents_in_report))
        agents_in_both = sorted(list(agents_in_report.intersection(agents_in_scale)))

        if agents_only_in_report:
            st.warning(f"**Agentes no Relatório de Status, mas NÃO na Escala ({len(agents_only_in_report)}):** {', '.join(agents_only_in_report)}")
        else:
            st.info("Todos os agentes do relatório de status estão na escala (ou não há relatório).")

        if agents_only_in_scale:
            st.warning(f"**Agentes na Escala, mas NÃO no Relatório de Status ({len(agents_only_in_scale)}):** {', '.join(agents_only_in_scale)}")
        else:
            st.info("Todos os agentes da escala estão no relatório de status (ou não há escala).")

        if agents_in_both:
            st.success(f"**Agentes presentes em AMBOS os arquivos ({len(agents_in_both)}):** {', '.join(agents_in_both)}")
        else:
            st.info("Nenhum agente encontrado em ambos os arquivos.")
    else:
        st.info("Carregue os arquivos de relatório e escala para ver o comparativo de agentes.")


    # --- Lógica de Filtragem e Geração do Gráfico ---
    if st.session_state.df_real_status is not None and st.session_state.df_escala is not None and selected_agents:

        # Filtrar df_real_status
        filtered_df_real_status = st.session_state.df_real_status[
            (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
            (st.session_state.df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
            (st.session_state.df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date) &
            (st.session_state.df_real_status['Estado'] == 'Unified online') # Apenas status online para comparação
        ].copy() # Adicionado .copy() para evitar SettingWithCopyWarning

        # Filtrar df_escala
        filtered_df_escala = st.session_state.df_escala[
            (st.session_state.df_escala['Nome do agente'].isin(selected_agents))
        ].copy() # Adicionado .copy()

        # Gerar todas as datas no intervalo selecionado
        all_dates = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]

        # DataFrame para o gráfico
        chart_data = []

        # Processar dados de escala
        for agent in selected_agents:
            agent_scale = filtered_df_escala[filtered_df_escala['Nome do agente'] == agent]
            for current_date in all_dates:
                day_of_week_num = current_date.weekday() # 0=Seg, 6=Dom

                # Encontrar a escala para o agente e dia da semana
                daily_scale = agent_scale[agent_scale['Dia da Semana Num'] == day_of_week_num]

                if not daily_scale.empty:
                    for _, row_scale in daily_scale.iterrows():
                        start_time_scale = row_scale['ENTRADA']
                        end_time_scale = row_scale['SAÍDA']

                        start_dt_scale = datetime.combine(current_date, start_time_scale)
                        end_dt_scale = datetime.combine(current_date, end_time_scale)

                        # Se a saída for menor que a entrada (ex: 23:00-07:00), significa que atravessa a meia-noite
                        if end_dt_scale < start_dt_scale:
                            # Parte da escala no dia atual
                            chart_data.append({
                                'Nome do agente': agent,
                                'Data': current_date,
                                'Tipo': 'Escala',
                                'Início': start_dt_scale,
                                'Término': datetime.combine(current_date, time(23, 59, 59))
                            })
                            # Parte da escala no dia seguinte (se o intervalo de datas permitir)
                            if current_date + timedelta(days=1) <= end_date:
                                chart_data.append({
                                    'Nome do agente': agent,
                                    'Data': current_date + timedelta(days=1),
                                    'Tipo': 'Escala',
                                    'Início': datetime.combine(current_date + timedelta(days=1), time(0, 0, 0)),
                                    'Término': end_dt_scale.replace(day=current_date.day + 1)
                                })
                        else:
                            chart_data.append({
                                'Nome do agente': agent,
                                'Data': current_date,
                                'Tipo': 'Escala',
                                'Início': start_dt_scale,
                                'Término': end_dt_scale
                            })

        # Processar dados de status real (Unified online)
        for _, row_status in filtered_df_real_status.iterrows():
            agent = row_status['Nome do agente']
            start_dt_status = row_status['Hora de início do estado - Carimbo de data/hora']
            end_dt_status = row_status['Hora de término do estado - Carimbo de data/hora']
            current_date_status = start_dt_status.date()

            # Ajustar o término se ele passar para o dia seguinte para o cálculo diário
            if end_dt_status.date() > current_date_status:
                end_dt_status_adjusted = datetime.combine(current_date_status, time(23, 59, 59))
            else:
                end_dt_status_adjusted = end_dt_status

            chart_data.append({
                'Nome do agente': agent,
                'Data': current_date_status,
                'Tipo': 'Status Real (Online)',
                'Início': start_dt_status,
                'Término': end_dt_status_adjusted
            })

        if chart_data:
            df_chart = pd.DataFrame(chart_data)
            df_chart['Duração'] = df_chart['Término'] - df_chart['Início']
            df_chart['Duração Horas'] = df_chart['Duração'].dt.total_seconds() / 3600

            # Criar uma coluna combinada para facet_row e y
            df_chart['Agente_Data_Tipo'] = df_chart['Nome do agente'] + ' - ' + df_chart['Data'].dt.strftime('%Y-%m-%d') + ' (' + df_chart['Tipo'] + ')'

            # Ordenar para que Escala venha antes de Status Real (Online)
            df_chart['Tipo_Ordenado'] = df_chart['Tipo'].map({'Escala': 0, 'Status Real (Online)': 1})
            df_chart = df_chart.sort_values(by=['Nome do agente', 'Data', 'Tipo_Ordenado'])

            # Ajustar a altura do gráfico dinamicamente
            num_unique_rows = df_chart['Agente_Data_Tipo'].nunique()
            chart_height = max(300, num_unique_rows * 40) # 40 pixels por linha, mínimo de 300

            st.subheader("Visualização Comparativa (Escala vs. Online)")
            if len(selected_agents) > 10:
                st.warning("Muitos agentes selecionados. O gráfico pode ficar sobrecarregado. Considere reduzir a seleção.")

            fig = px.timeline(
                df_chart,
                x_start="Início",
                x_end="Término",
                y="Agente_Data_Tipo", # Usar a coluna combinada para o eixo Y
                color="Tipo",
                color_discrete_map={'Escala': 'blue', 'Status Real (Online)': 'green'},
                title="Escala vs. Status Real (Online) por Agente e Dia",
                labels={"Início": "Hora de Início", "Término": "Hora de Término", "Agente_Data_Tipo": "Agente / Data / Tipo"},
                height=chart_height
            )

            fig.update_yaxes(categoryorder="array", categoryarray=df_chart['Agente_Data_Tipo'].unique())
            fig.update_xaxes(
                range=[datetime.combine(start_date, time(0, 0, 0)), datetime.combine(start_date, time(23, 59, 59))],
                tickformat="%H:%M",
                title_text="Horário do Dia"
            )
            fig.update_layout(xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

            # --- Cálculo e Exibição de Métricas ---
            st.subheader("Métricas de Disponibilidade e Aderência")
            metrics_data = []

            for agent in selected_agents:
                for current_date in all_dates:
                    # Escala para o dia
                    day_of_week_num = current_date.weekday()
                    daily_scale_entries = filtered_df_escala[
                        (filtered_df_escala['Nome do agente'] == agent) &
                        (filtered_df_escala['Dia da Semana Num'] == day_of_week_num)
                    ]

                    total_escala_segundos = 0
                    for _, row_scale in daily_scale_entries.iterrows():
                        start_time_scale = row_scale['ENTRADA']
                        end_time_scale = row_scale['SAÍDA']

                        start_dt_scale = datetime.combine(current_date, start_time_scale)
                        end_dt_scale = datetime.combine(current_date, end_time_scale)

                        # Ajustar escala que atravessa a meia-noite para o dia atual
                        if end_dt_scale < start_dt_scale:
                            end_dt_scale = datetime.combine(current_date, time(23, 59, 59))

                        total_escala_segundos += (end_dt_scale - start_dt_scale).total_seconds()

                    # Status online para o dia
                    daily_online_status = filtered_df_real_status[
                        (filtered_df_real_status['Nome do agente'] == agent) &
                        (filtered_df_real_status['Hora de início do estado - Carimbo de data/hora'].dt.date == current_date)
                    ]

                    total_online_na_escala_segundos = 0
                    total_online_segundos = 0

                    for _, row_status in daily_online_status.iterrows():
                        status_start = row_status['Hora de início do estado - Carimbo de data/hora']
                        status_end = row_status['Hora de término do estado - Carimbo de data/hora']

                        # Ajustar status_end se ele passar para o dia seguinte
                        if status_end.date() > current_date:
                            status_end = datetime.combine(current_date, time(23, 59, 59))

                        total_online_segundos += (status_end - status_start).total_seconds()

                        # Calcular interseção com a escala
                        for _, row_scale in daily_scale_entries.iterrows():
                            scale_start_time = row_scale['ENTRADA']
                            scale_end_time = row_scale['SAÍDA']

                            scale_start_dt = datetime.combine(current_date, scale_start_time)
                            scale_end_dt = datetime.combine(current_date, scale_end_time)

                            # Ajustar escala que atravessa a meia-noite para o dia atual
                            if scale_end_dt < scale_start_dt:
                                scale_end_dt = datetime.combine(current_date, time(23, 59, 59))

                            # Interseção
                            overlap_start = max(status_start, scale_start_dt)
                            overlap_end = min(status_end, scale_end_dt)

                            if overlap_end > overlap_start:
                                total_online_na_escala_segundos += (overlap_end - overlap_start).total_seconds()

                    disponibilidade = (total_online_na_escala_segundos / total_escala_segundos * 100) if total_escala_segundos > 0 else 0
                    aderencia = (total_online_na_escala_segundos / total_online_segundos * 100) if total_online_segundos > 0 else 0

                    metrics_data.append({
                        'Agente': agent,
                        'Data': current_date.strftime('%Y-%m-%d'),
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
