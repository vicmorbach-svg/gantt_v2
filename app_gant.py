import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, time
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
    # O arquivo de status real TEM cabeçalhos na primeira linha.
    # Vamos renomear as colunas para os nomes esperados.
    df = df_report_raw.copy() # Trabalha com uma cópia para evitar SettingWithCopyWarning

    # Mapeamento explícito das colunas do arquivo de status real
    # Baseado no arquivo Tempo_em_Status_do_agente_por_dia_03202026_1006.xlsx
    expected_columns_report = {
        'Nome do agente': 'Nome do agente',
        'Hora de início do estado - Dia do mês': 'Dia',
        'Hora de início do estado - Carimbo de data/hora': 'Hora de início do estado - Carimbo de data/hora',
        'Hora de término do estado - Carimbo de data/hora': 'Hora de término do estado - Carimbo de data/hora',
        'Estado': 'Estado',
        'Tempo do agente no estado / Minutos': 'Tempo do agente no estado / Minutos'
    }

    # Renomear colunas
    df.rename(columns=expected_columns_report, inplace=True)

    # Verificar se as colunas essenciais existem após o renomeamento
    required_cols = ['Nome do agente', 'Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora', 'Estado']
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        st.error(f"Erro: O arquivo de status real está faltando as colunas essenciais: {', '.join(missing)}. Por favor, verifique o formato do arquivo.")
        st.stop()

    # Normalizar nomes dos agentes
    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Converter colunas de data/hora
    df['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
    df['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

    # Preencher NaT em 'Hora de término do estado - Carimbo de data/hora'
    # Se o término for NaT, assume-se que o status dura até o final do dia de início
    for index, row in df.iterrows():
        if pd.isna(row['Hora de término do estado - Carimbo de data/hora']):
            if pd.notna(row['Hora de início do estado - Carimbo de data/hora']):
                df.at[index, 'Hora de término do estado - Carimbo de data/hora'] = row['Hora de início do estado - Carimbo de data/hora'].replace(hour=23, minute=59, second=59)
            else:
                # Se o início também for NaT, não há como preencher, pode-se remover ou deixar como NaT
                df.at[index, 'Hora de término do estado - Carimbo de data/hora'] = pd.NaT

    # Remover linhas onde o início ou término do estado é NaT (após tentativas de preenchimento)
    df.dropna(subset=['Hora de início do estado - Carimbo de data/hora', 'Hora de término do estado - Carimbo de data/hora'], inplace=True)

    # Criar coluna 'Data' para facilitar o agrupamento
    df['Data'] = df['Hora de início do estado - Carimbo de data/hora'].dt.normalize()

    return df

def process_uploaded_scale(df_scale_raw):
    df = df_scale_raw.copy() # Trabalha com uma cópia para evitar SettingWithCopyWarning

    # Mapeamento explícito das colunas do arquivo de escala
    # Baseado no arquivo escala_gantt.xlsx
    expected_columns_scale = {
        'NOME': 'Nome do agente',
        'DIAS DE ATENDIMENTO': 'Dias de Atendimento',
        'ENTRADA': 'Entrada',
        'SAÍDA': 'Saída',
        'CARGA': 'Carga' # Incluindo a coluna CARGA
    }

    # Renomear colunas
    df.rename(columns=expected_columns_scale, inplace=True)

    # Verificar se as colunas essenciais existem após o renomeamento
    required_cols = ['Nome do agente', 'Dias de Atendimento', 'Entrada', 'Saída']
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        st.error(f"Erro: O arquivo de escala está faltando as colunas essenciais: {', '.join(missing)}. Por favor, verifique o formato do arquivo.")
        st.stop()

    # Normalizar nomes dos agentes
    df['Nome do agente'] = df['Nome do agente'].apply(normalize_agent_name)

    # Remover linhas onde o nome do agente é vazio após a normalização
    df.dropna(subset=['Nome do agente'], inplace=True)
    df = df[df['Nome do agente'] != ''].reset_index(drop=True)

    # Função auxiliar para converter valores para objetos time
    def to_time(val):
        if pd.isna(val):
            return None
        try:
            # Tenta converter para datetime e depois extrai a hora
            dt_obj = pd.to_datetime(val, errors='coerce')
            if pd.notna(dt_obj):
                return dt_obj.time()
            return None
        except Exception:
            return None

    # Aplicar a conversão para as colunas de horário
    df['Entrada'] = df['Entrada'].apply(to_time)
    df['Saída'] = df['Saída'].apply(to_time)

    # Remover linhas onde Entrada ou Saída são None após a conversão
    df.dropna(subset=['Entrada', 'Saída'], inplace=True)

    # Mapeamento de dias da semana (0=Segunda, 6=Domingo)
    dias_map = {
        'SEG': 0, 'SEGUNDA': 0, 'SEGUNDA-FEIRA': 0,
        'TER': 1, 'TERCA': 1, 'TERÇA': 1, 'TERCA-FEIRA': 1, 'TERÇA-FEIRA': 1,
        'QUA': 2, 'QUARTA': 2, 'QUARTA-FEIRA': 2,
        'QUI': 3, 'QUINTA': 3, 'QUINTA-FEIRA': 3,
        'SEX': 4, 'SEXTA': 4, 'SEXTA-FEIRA': 4,
        'SAB': 5, 'SABADO': 5, 'SÁBADO': 5,
        'DOM': 6, 'DOMINGO': 6
    }

    # Expandir a escala para cada dia da semana
    expanded_scale_data = []
    for index, row in df.iterrows():
        agent_name = row['Nome do agente']
        dias_str = str(row['Dias de Atendimento'])

        # Normalizar a string de dias para facilitar a divisão e mapeamento
        normalized_dias_str = unicodedata.normalize('NFKD', dias_str).encode('ascii', 'ignore').decode('utf-8').upper()
        normalized_dias_str = normalized_dias_str.replace(' E ', ',').replace(' CALL', '').replace(' LOJA', '') # Remove "Call" e "Loja"

        dias_list = [d.strip() for d in normalized_dias_str.split(',') if d.strip()]

        for dia_abbr in dias_list:
            if dia_abbr in dias_map:
                day_of_week_num = dias_map[dia_abbr]
                expanded_scale_data.append({
                    'Nome do agente': agent_name,
                    'Dia da Semana Num': day_of_week_num,
                    'Entrada': row['Entrada'],
                    'Saída': row['Saída'],
                    'Carga': row.get('Carga') # Usa .get() para acessar 'Carga' de forma segura
                })
            else:
                st.warning(f"Dia da semana '{dia_abbr}' não reconhecido para o agente {agent_name}. Ignorando.")

    if not expanded_scale_data:
        st.warning("Nenhuma escala válida foi encontrada após o processamento. Verifique a coluna 'DIAS DE ATENDIMENTO'.")
        return pd.DataFrame() # Retorna um DataFrame vazio se não houver dados válidos

    df_expanded_scale = pd.DataFrame(expanded_scale_data)
    return df_expanded_scale

def calculate_metrics(df_real_status, df_escala, selected_agents, start_date, end_date):
    analysis_results = []
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')

    for agent in selected_agents:
        agent_status = df_real_status[df_real_status['Nome do agente'] == agent]
        agent_scale = df_escala[df_escala['Nome do agente'] == agent]

        total_scheduled_time_minutes = 0
        total_online_in_schedule_minutes = 0

        for current_date_metrics in date_range:
            day_of_week_num = current_date_metrics.weekday() # 0=Segunda, 6=Domingo

            # Filtrar a escala para o dia da semana atual
            daily_scale = agent_scale[agent_scale['Dia da Semana Num'] == day_of_week_num]

            if not daily_scale.empty:
                # Assume a primeira entrada de escala para o dia (se houver múltiplas)
                scale_entry = daily_scale.iloc[0]
                scale_start_time = scale_entry['Entrada']
                scale_end_time = scale_entry['Saída']

                # Criar objetos datetime completos para a escala do dia
                scale_start_dt = datetime.combine(current_date_metrics, scale_start_time)
                scale_end_dt = datetime.combine(current_date_metrics, scale_end_time)

                # Se a escala termina no dia seguinte (ex: 23:00 - 07:00), ajustar o final para o dia seguinte
                if scale_end_dt < scale_start_dt:
                    scale_end_dt += timedelta(days=1)

                total_scheduled_time_minutes += (scale_end_dt - scale_start_dt).total_seconds() / 60

                # Filtrar status real para o agente e o dia atual
                daily_status = agent_status[agent_status['Data'] == current_date_metrics]

                for _, status_entry in daily_status.iterrows():
                    if status_entry['Estado'] == 'Unified online':
                        status_start = status_entry['Hora de início do estado - Carimbo de data/hora']
                        status_end = status_entry['Hora de término do estado - Carimbo de data/hora']

                        # Ajustar status_end se ele for para o dia seguinte mas a escala termina no dia atual
                        # ou se o status_end ultrapassa o final da escala no mesmo dia
                        if status_end.date() > current_date_metrics and scale_end_dt.date() == current_date_metrics:
                            status_end = datetime.combine(current_date_metrics, datetime(1,1,1,23,59,59).time()) # Fim do dia da escala
                        elif status_end > scale_end_dt and status_start < scale_end_dt: # Se o status termina depois da escala mas começou antes
                            status_end = scale_end_dt # Limita o fim do status ao fim da escala

                        # Calcular interseção entre o status online e a escala
                        overlap_start = max(scale_start_dt, status_start)
                        overlap_end = min(scale_end_dt, status_end)

                        if overlap_end > overlap_start:
                            total_online_in_schedule_minutes += (overlap_end - overlap_start).total_seconds() / 60
            # else:
            #     st.warning(f"Agente {agent} não tem escala definida para {current_date_metrics.strftime('%Y-%m-%d')}.") # Para debug

        availability_percentage = (total_online_in_schedule_minutes / total_scheduled_time_minutes * 100) if total_scheduled_time_minutes > 0 else 0

        analysis_results.append({
            'Agente': agent,
            'Total Tempo Escala (min)': total_scheduled_time_minutes,
            'Total Tempo Online na Escala (min)': total_online_in_schedule_minutes,
            'Disponibilidade na Escala (%)': f"{availability_percentage:.2f}%"
        })
    return pd.DataFrame(analysis_results)


# --- Configuração do Streamlit ---
st.set_page_config(layout="wide", page_title="Dashboard de Produtividade de Agentes")

st.title("Dashboard de Produtividade de Agentes")

# Inicializar session_state
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'all_unique_agents' not in st.session_state:
    st.session_state.all_unique_agents = set()
if 'agent_groups' not in st.session_state:
    st.session_state.agent_groups = {}

tab_upload, tab_groups, tab_view_metrics = st.tabs(["Upload de Dados", "Gerenciar Grupos", "Visualização e Métricas"])

with tab_upload:
    st.header("Upload de Arquivos")

    uploaded_report_file = st.file_uploader("Faça upload do arquivo de Status Real (Excel)", type=["xlsx"], key="report_uploader")
    uploaded_scale_file = st.file_uploader("Faça upload do arquivo de Escala (Excel)", type=["xlsx"], key="scale_uploader")

    if uploaded_report_file and uploaded_scale_file:
        try:
            df_report_raw = pd.read_excel(uploaded_report_file, header=0) # Assumindo cabeçalho na primeira linha
            st.session_state.df_real_status = process_uploaded_report(df_report_raw)
            st.success("Arquivo de Status Real processado com sucesso!")

            df_scale_raw = pd.read_excel(uploaded_scale_file, header=0) # Assumindo cabeçalho na primeira linha
            st.session_state.df_escala = process_uploaded_scale(df_scale_raw)
            st.success("Arquivo de Escala processado com sucesso!")

            # Atualizar a lista de agentes únicos após o upload e processamento
            all_agents_report = set(st.session_state.df_real_status['Nome do agente'].unique()) if not st.session_state.df_real_status.empty else set()
            all_agents_scale = set(st.session_state.df_escala['Nome do agente'].unique()) if not st.session_state.df_escala.empty else set()
            st.session_state.all_unique_agents = sorted(list(all_agents_report.union(all_agents_scale)))

        except Exception as e:
            st.error(f"Erro ao processar os arquivos: {e}")
            st.session_state.df_real_status = pd.DataFrame()
            st.session_state.df_escala = pd.DataFrame()
            st.session_state.all_unique_agents = set()

    elif uploaded_report_file:
        st.info("Por favor, faça upload do arquivo de Escala também.")
    elif uploaded_scale_file:
        st.info("Por favor, faça upload do arquivo de Status Real também.")
    else:
        st.info("Aguardando upload dos arquivos de Status Real e Escala.")

with tab_groups:
    st.header("Gerenciar Grupos de Agentes")

    if st.session_state.all_unique_agents:
        st.subheader("Criar Novo Grupo")
        group_name = st.text_input("Nome do Grupo")
        selected_agents_for_group = st.multiselect(
            "Selecione os agentes para este grupo",
            options=st.session_state.all_unique_agents,
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
            for name, agents in st.session_state.agent_groups.items():
                st.write(f"**{name}**: {', '.join(agents)}")
                if st.button(f"Excluir {name}", key=f"delete_group_{name}"):
                    del st.session_state.agent_groups[name]
                    st.success(f"Grupo '{name}' excluído.")
                    st.rerun()
        else:
            st.info("Nenhum grupo criado ainda.")
    else:
        st.warning("Faça o upload dos arquivos na aba 'Upload de Dados' para gerenciar grupos de agentes.")

with tab_view_metrics:
    st.header("Visualização e Métricas")

    if not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
        st.sidebar.subheader("Filtros")

        # Filtro de Agentes
        agent_filter_mode = st.sidebar.radio(
            "Filtrar por:",
            ("Agentes Individuais", "Grupos de Agentes"),
            key="agent_filter_mode"
        )

        selected_agents = []
        if agent_filter_mode == "Agentes Individuais":
            selected_agents = st.sidebar.multiselect(
                "Selecione os Agentes",
                options=st.session_state.all_unique_agents,
                default=list(st.session_state.all_unique_agents) if len(st.session_state.all_unique_agents) <= 10 else [],
                key="individual_agent_selector"
            )
        else:
            group_names = list(st.session_state.agent_groups.keys())
            selected_group_name = st.sidebar.selectbox(
                "Selecione um Grupo",
                options=[""] + group_names,
                key="group_selector"
            )
            if selected_group_name:
                selected_agents = st.session_state.agent_groups[selected_group_name]
                st.sidebar.info(f"Agentes no grupo '{selected_group_name}': {len(selected_agents)}")

        # Filtro de Data
        min_date_report = st.session_state.df_real_status['Data'].min().date() if not st.session_state.df_real_status.empty else datetime.now().date()
        max_date_report = st.session_state.df_real_status['Data'].max().date() if not st.session_state.df_real_status.empty else datetime.now().date()

        start_date = st.sidebar.date_input("Data de Início", value=min_date_report, min_value=min_date_report, max_value=max_date_report)
        end_date = st.sidebar.date_input("Data de Término", value=max_date_report, min_value=min_date_report, max_value=max_date_report)

        if start_date > end_date:
            st.sidebar.error("A data de início não pode ser posterior à data de término.")
            selected_agents = [] # Impede a geração do gráfico se as datas estiverem inválidas

        if selected_agents:
            st.subheader("Comparativo de Agentes: Escala vs. Status Real")

            # Filtrar dados de status real e escala pelos agentes e datas selecionadas
            filtered_df_real_status = st.session_state.df_real_status[
                (st.session_state.df_real_status['Nome do agente'].isin(selected_agents)) &
                (st.session_state.df_real_status['Data'] >= pd.to_datetime(start_date)) &
                (st.session_state.df_real_status['Data'] <= pd.to_datetime(end_date))
            ].copy()

            # Preparar dados da escala para o gráfico
            df_chart_data = []
            date_range_chart = pd.date_range(start=start_date, end=end_date, freq='D')

            for agent in selected_agents:
                agent_scale_df = st.session_state.df_escala[st.session_state.df_escala['Nome do agente'] == agent]
                if agent_scale_df.empty:
                    st.warning(f"Agente '{agent}' não possui escala definida. Não será incluído no gráfico de escala.")
                    continue

                for current_date_chart in date_range_chart:
                    day_of_week_num = current_date_chart.weekday() # 0=Segunda, 6=Domingo
                    daily_scale_entry = agent_scale_df[agent_scale_df['Dia da Semana Num'] == day_of_week_num]

                    if not daily_scale_entry.empty:
                        scale_start_time = daily_scale_entry.iloc[0]['Entrada']
                        scale_end_time = daily_scale_entry.iloc[0]['Saída']

                        scale_start_dt = datetime.combine(current_date_chart, scale_start_time)
                        scale_end_dt = datetime.combine(current_date_chart, scale_end_time)

                        if scale_end_dt < scale_start_dt: # Escala que atravessa a meia-noite
                            scale_end_dt += timedelta(days=1)

                        df_chart_data.append({
                            'Nome do agente': agent,
                            'Data': current_date_chart,
                            'Tipo': 'Escala Planejada',
                            'Start': scale_start_dt,
                            'Finish': scale_end_dt,
                            'Color': 'lightgray' # Cor para a escala
                        })

            # Adicionar dados de status real ao df_chart_data
            for _, row in filtered_df_real_status.iterrows():
                df_chart_data.append({
                    'Nome do agente': row['Nome do agente'],
                    'Data': row['Data'],
                    'Tipo': row['Estado'], # Usar o estado real
                    'Start': row['Hora de início do estado - Carimbo de data/hora'],
                    'Finish': row['Hora de término do estado - Carimbo de data/hora'],
                    'Color': 'blue' if row['Estado'] == 'Unified online' else 'red' # Cores diferentes para status
                })

            if df_chart_data:
                df_chart = pd.DataFrame(df_chart_data)

                # Criar uma coluna combinada para o eixo Y
                df_chart['Agente_Data_Tipo'] = df_chart['Nome do agente'] + ' - ' + df_chart['Data'].dt.strftime('%Y-%m-%d') + ' (' + df_chart['Tipo'] + ')'

                # Ordenar o eixo Y para melhor visualização
                # Primeiro por agente, depois por data, depois por tipo (Escala primeiro)
                df_chart['Tipo_Order'] = df_chart['Tipo'].apply(lambda x: 0 if x == 'Escala Planejada' else 1)
                df_chart = df_chart.sort_values(by=['Nome do agente', 'Data', 'Tipo_Order'])

                # Definir a ordem das categorias no eixo Y
                y_order = df_chart['Agente_Data_Tipo'].unique().tolist()

                # Altura dinâmica do gráfico
                chart_height = max(500, len(y_order) * 25) # 25 pixels por linha, mínimo de 500

                fig = px.timeline(
                    df_chart,
                    x_start="Start",
                    x_end="Finish",
                    y="Agente_Data_Tipo", # Usar a coluna combinada
                    color="Tipo", # Colorir por tipo (Escala, Online, Away, Offline)
                    color_discrete_map={
                        'Escala Planejada': 'lightgray',
                        'Unified online': 'green',
                        'Unified away': 'orange',
                        'Unified offline': 'red',
                        'Unified transfers only': 'purple'
                    },
                    title="Linha do Tempo de Status e Escala dos Agentes",
                    height=chart_height
                )

                fig.update_yaxes(categoryorder='array', categoryarray=y_order)
                fig.update_xaxes(
                    title_text="Hora do Dia",
                    tickformat="%H:%M",
                    showgrid=True, # Mostrar grade no eixo X
                    gridcolor='lightgray',
                    griddash='dot'
                )
                fig.update_yaxes(
                    title_text="Agente - Data (Tipo)",
                    showgrid=True, # Mostrar grade no eixo Y
                    gridcolor='lightgray',
                    griddash='dot'
                )
                fig.update_layout(hovermode="y unified") # Melhorar o hover

                st.plotly_chart(fig, use_container_width=True)

                st.subheader("Métricas de Disponibilidade na Escala")
                if not st.session_state.df_real_status.empty and not st.session_state.df_escala.empty:
                    df_metrics = calculate_metrics(
                        st.session_state.df_real_status,
                        st.session_state.df_escala,
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
        st.info("Por favor, faça o upload de ambos os arquivos na aba 'Upload de Dados' primeiro.")
