import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import numpy as np

# Configurações iniciais do Streamlit
st.set_page_config(layout="wide")
st.title("Análise de Escalas e Status de Agentes")

# Inicializa session_state para armazenar DataFrames e outras variáveis
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame()
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame()
if 'all_agents' not in st.session_state:
    st.session_state.all_agents = []
if 'normalized_agents_escala' not in st.session_state:
    st.session_state.normalized_agents_escala = set()
if 'normalized_agents_real_status' not in st.session_state:
    st.session_state.normalized_agents_real_status = set()

# Função para normalizar nomes de agentes
def normalize_agent_name(name):
    if isinstance(name, str):
        return name.strip().upper()
    return name

# --- Abas de Navegação ---
tab1, tab2, tab3, tab4 = st.tabs(["Upload de Dados", "Criar Escalas", "Visualizar Escalas e Status", "Análise de Aderência"])

with tab1:
    st.header("Upload de Arquivos")

    uploaded_file_escala = st.file_uploader("Escolha o arquivo da Escala (Excel)", type=["xlsx"], key="escala_upload")
    if uploaded_file_escala is not None:
        st.session_state.df_escala = pd.read_excel(uploaded_file_escala)
        st.success("Arquivo de Escala carregado com sucesso!")
        st.write("Prévia do arquivo de Escala:")
        st.dataframe(st.session_state.df_escala.head())

        # Normaliza os nomes dos agentes na escala
        if 'NOME' in st.session_state.df_escala.columns:
            st.session_state.df_escala['NOME'] = st.session_state.df_escala['NOME'].apply(normalize_agent_name)
            st.session_state.normalized_agents_escala = set(st.session_state.df_escala['NOME'].unique())
        else:
            st.warning("Coluna 'NOME' não encontrada no arquivo de escala. Verifique o nome da coluna.")

    uploaded_file_status = st.file_uploader("Escolha o arquivo de Status Real (Excel)", type=["xlsx"], key="status_upload")
    if uploaded_file_status is not None:
        st.session_state.df_real_status = pd.read_excel(uploaded_file_status)
        st.success("Arquivo de Status Real carregado com sucesso!")
        st.write("Prévia do arquivo de Status Real:")
        st.dataframe(st.session_state.df_real_status.head())

        # Normaliza os nomes dos agentes no status real
        if 'Nome do agente' in st.session_state.df_real_status.columns:
            st.session_state.df_real_status['Nome do agente'] = st.session_state.df_real_status['Nome do agente'].apply(normalize_agent_name)
            st.session_state.normalized_agents_real_status = set(st.session_state.df_real_status['Nome do agente'].unique())
        else:
            st.warning("Coluna 'Nome do agente' não encontrada no arquivo de status real. Verifique o nome da coluna.")

    # Comparar e normalizar nomes de agentes após o upload de ambos os arquivos
    if not st.session_state.df_escala.empty and not st.session_state.df_real_status.empty:
        all_agents_escala = st.session_state.normalized_agents_escala
        all_agents_real_status = st.session_state.normalized_agents_real_status

        st.session_state.all_agents = sorted(list(all_agents_escala.union(all_agents_real_status)))

        agents_only_escala = all_agents_escala - all_agents_real_status
        agents_only_real_status = all_agents_real_status - all_agents_escala

        if agents_only_escala:
            st.subheader("Agentes apenas na Escala:")
            st.write(", ".join(sorted(list(agents_only_escala))))
        if agents_only_real_status:
            st.subheader("Agentes apenas no Status Real:")
            st.write(", ".join(sorted(list(agents_only_real_status))))
        if not agents_only_escala and not agents_only_real_status:
            st.info("Todos os agentes estão presentes em ambos os arquivos ou não há agentes em um dos arquivos.")

with tab2:
    st.header("Criar Escalas Personalizadas")

    if not st.session_state.df_escala.empty:
        st.subheader("Visualizar Escalas Existentes")
        st.dataframe(st.session_state.df_escala)

        st.subheader("Adicionar Nova Escala")
        with st.form("nova_escala_form"):
            # Campo de escolha para o nome do agente
            agent_name = st.selectbox("Nome do Agente", options=st.session_state.all_agents if st.session_state.all_agents else ["Nenhum agente disponível"], key="new_agent_name")

            dias_atendimento = st.multiselect("Dias de Atendimento", ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"], key="new_dias_atendimento")
            entrada = st.time_input("Hora de Entrada", datetime.time(8, 0), key="new_entrada")
            saida = st.time_input("Hora de Saída", datetime.time(17, 0), key="new_saida")

            # Grupos pré-definidos
            grupo_options = ['6h20min', '8h12min', 'Personalizado']
            selected_grupo = st.selectbox("Grupo de Carga Horária", options=grupo_options, key="new_grupo")

            carga_horaria = None
            if selected_grupo == '6h20min':
                carga_horaria = datetime.time(6, 20)
            elif selected_grupo == '8h12min':
                carga_horaria = datetime.time(8, 12)
            else: # Personalizado
                carga_horaria = st.time_input("Carga Horária (HH:MM)", datetime.time(8, 0), key="new_carga_horaria_custom")

            submitted = st.form_submit_button("Adicionar Escala")
            if submitted:
                if agent_name and dias_atendimento and entrada and saida and carga_horaria:
                    new_entry = {
                        "NOME": normalize_agent_name(agent_name),
                        "DIAS DE ATENDIMENTO": ", ".join(dias_atendimento),
                        "ENTRADA": entrada,
                        "SAÍDA": saida,
                        "CARGA": carga_horaria
                    }
                    st.session_state.df_escala = pd.concat([st.session_state.df_escala, pd.DataFrame([new_entry])], ignore_index=True)
                    st.success(f"Escala para {agent_name} adicionada com sucesso!")
                    st.dataframe(st.session_state.df_escala)
                    # Atualiza a lista de agentes normalizados
                    st.session_state.normalized_agents_escala = set(st.session_state.df_escala['NOME'].unique())
                    st.session_state.all_agents = sorted(list(st.session_state.normalized_agents_escala.union(st.session_state.normalized_agents_real_status)))
                else:
                    st.error("Por favor, preencha todos os campos para adicionar a escala.")
    else:
        st.warning("Por favor, faça o upload do arquivo de escala na aba 'Upload de Dados' primeiro.")

with tab3:
    st.header("Visualizar Escalas e Status Real")

    if not st.session_state.df_escala.empty and not st.session_state.df_real_status.empty:
        # Filtro por agente
        selected_agents = st.multiselect(
            "Selecione os Agentes",
            options=st.session_state.all_agents,
            default=st.session_state.all_agents[:min(5, len(st.session_state.all_agents))] # Seleciona os 5 primeiros por padrão
        )

        # Filtro por data usando calendário
        col_start_date, col_end_date = st.columns(2)
        with col_start_date:
            start_date = st.date_input("Data de Início", value=datetime.date(2026, 3, 1))
        with col_end_date:
            end_date = st.date_input("Data de Fim", value=datetime.date(2026, 3, 19))

        if selected_agents:
            # Processar df_escala
            df_escala_filtered = st.session_state.df_escala[
                st.session_state.df_escala['NOME'].isin(selected_agents)
            ].copy()

            # Processar df_real_status
            df_real_status_filtered = st.session_state.df_real_status[
                st.session_state.df_real_status['Nome do agente'].isin(selected_agents)
            ].copy()

            # Conversão de tipos e tratamento de NaT para df_real_status
            df_real_status_filtered['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status_filtered['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
            df_real_status_filtered['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status_filtered['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

            # Preencher NaT em 'Hora de término do estado - Carimbo de data/hora' com a data/hora atual para visualização
            df_real_status_filtered['Hora de término do estado - Carimbo de data/hora'] = df_real_status_filtered['Hora de término do estado - Carimbo de data/hora'].fillna(pd.Timestamp.now())

            # Filtrar por datas
            df_real_status_filtered = df_real_status_filtered[
                (df_real_status_filtered['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date) &
                (df_real_status_filtered['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date)
            ]

            # Criar DataFrame para o Gantt Chart
            df_gantt = pd.DataFrame()

            # Adicionar dados da escala
            for index, row in df_escala_filtered.iterrows():
                dias = [d.strip() for d in row['DIAS DE ATENDIMENTO'].split(',')]
                for single_date in pd.date_range(start=start_date, end=end_date):
                    if single_date.strftime('%a')[:3] in dias: # Verifica se o dia da semana está na escala
                        start_datetime = single_date.replace(
                            hour=row['ENTRADA'].hour,
                            minute=row['ENTRADA'].minute,
                            second=row['ENTRADA'].second
                        )
                        end_datetime = single_date.replace(
                            hour=row['SAÍDA'].hour,
                            minute=row['SAÍDA'].minute,
                            second=row['SAÍDA'].second
                        )
                        df_gantt = pd.concat([df_gantt, pd.DataFrame([{
                            'Nome do agente': row['NOME'],
                            'Start': start_datetime,
                            'Finish': end_datetime,
                            'Status': 'Escala',
                            'Tipo': 'Escala',
                            'Data': single_date
                        }])], ignore_index=True)

            # Adicionar dados de status real
            df_real_status_filtered = df_real_status_filtered.rename(columns={
                'Hora de início do estado - Carimbo de data/hora': 'Start',
                'Hora de término do estado - Carimbo de data/hora': 'Finish',
                'Estado': 'Status',
                'Nome do agente': 'Nome do agente'
            })
            df_real_status_filtered['Tipo'] = 'Status Real'
            df_real_status_filtered['Data'] = df_real_status_filtered['Start'].dt.date

            # Filtrar apenas o status 'Unified online' para o gráfico de status real
            df_real_status_online = df_real_status_filtered[df_real_status_filtered['Status'] == 'Unified online'].copy()

            # Combinar os DataFrames para o gráfico
            df_chart = pd.concat([df_gantt, df_real_status_online], ignore_index=True)

            # Criar uma coluna para agrupar por agente e data, e tipo para que apareçam um acima do outro
            df_chart['Agente_Data_Tipo'] = df_chart['Nome do agente'] + ' - ' + df_chart['Data'].astype(str) + ' (' + df_chart['Tipo'] + ')'

            # Definir cores para os status
            color_map = {
                'Escala': 'blue',
                'Unified online': 'green',
                'Unified away': 'orange',
                'Unified offline': 'red',
                'Unified transfers only': 'purple'
            }

            # Criar o gráfico de Gantt
            fig = px.timeline(
                df_chart,
                x_start="Start",
                x_end="Finish",
                y="Agente_Data_Tipo",
                color="Status",
                color_discrete_map=color_map,
                title="Escala vs. Status Real dos Agentes",
                hover_name="Nome do agente",
                hover_data={
                    "Start": "|%Y-%m-%d %H:%M:%S",
                    "Finish": "|%Y-%m-%d %H:%M:%S",
                    "Status": True,
                    "Tipo": True,
                    "Nome do agente": False,
                    "Data": False,
                    "Agente_Data_Tipo": False
                }
            )

            fig.update_yaxes(autorange="reversed") # Inverte a ordem para o mais recente aparecer no topo
            fig.update_layout(height=600 + len(df_chart['Agente_Data_Tipo'].unique()) * 20) # Ajusta a altura dinamicamente
            st.plotly_chart(fig, use_container_width=True)

        else:
            st.warning("Por favor, selecione pelo menos um agente para visualizar.")
    else:
        st.warning("Por favor, faça o upload de ambos os arquivos na aba 'Upload de Dados' primeiro.")

with tab4:
    st.header("Análise de Aderência e Disponibilidade")

    if not st.session_state.df_escala.empty and not st.session_state.df_real_status.empty:
        st.subheader("Cálculo de Disponibilidade e Aderência")

        # Filtro por agente
        selected_agents_analysis = st.multiselect(
            "Selecione os Agentes para Análise",
            options=st.session_state.all_agents,
            default=st.session_state.all_agents[:min(5, len(st.session_state.all_agents))],
            key="analysis_agents"
        )

        # Filtro por data usando calendário
        col_start_date_analysis, col_end_date_analysis = st.columns(2)
        with col_start_date_analysis:
            start_date_analysis = st.date_input("Data de Início para Análise", value=datetime.date(2026, 3, 1), key="analysis_start_date")
        with col_end_date_analysis:
            end_date_analysis = st.date_input("Data de Fim para Análise", value=datetime.date(2026, 3, 19), key="analysis_end_date")

        if selected_agents_analysis:
            # Preparar df_real_status para análise
            df_real_status_analysis = st.session_state.df_real_status[
                st.session_state.df_real_status['Nome do agente'].isin(selected_agents_analysis)
            ].copy()

            df_real_status_analysis['Hora de início do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status_analysis['Hora de início do estado - Carimbo de data/hora'], errors='coerce')
            df_real_status_analysis['Hora de término do estado - Carimbo de data/hora'] = pd.to_datetime(df_real_status_analysis['Hora de término do estado - Carimbo de data/hora'], errors='coerce')

            # Preencher NaT em 'Hora de término do estado - Carimbo de data/hora' com a data/hora atual para cálculo
            df_real_status_analysis['Hora de término do estado - Carimbo de data/hora'] = df_real_status_analysis['Hora de término do estado - Carimbo de data/hora'].fillna(pd.Timestamp.now())

            df_real_status_analysis = df_real_status_analysis[
                (df_real_status_analysis['Hora de início do estado - Carimbo de data/hora'].dt.date >= start_date_analysis) &
                (df_real_status_analysis['Hora de início do estado - Carimbo de data/hora'].dt.date <= end_date_analysis)
            ]

            # DataFrame para armazenar os resultados da análise
            analysis_results = []

            for agent in selected_agents_analysis:
                agent_escala = st.session_state.df_escala[st.session_state.df_escala['NOME'] == agent]
                agent_real_status = df_real_status_analysis[df_real_status_analysis['Nome do agente'] == agent]

                if not agent_escala.empty:
                    total_scheduled_time_minutes = 0
                    total_online_in_schedule_minutes = 0

                    for single_date in pd.date_range(start=start_date_analysis, end=end_date_analysis):
                        day_of_week_abbr = single_date.strftime('%a')[:3] # Ex: 'Mon', 'Tue'

                        # Mapeamento para os dias da semana em português
                        day_mapping = {
                            'Mon': 'Seg', 'Tue': 'Ter', 'Wed': 'Qua', 'Thu': 'Qui', 'Fri': 'Sex', 'Sat': 'Sab', 'Sun': 'Dom'
                        }
                        day_of_week_pt = day_mapping.get(day_of_week_abbr, '')

                        # Encontrar a escala para o dia da semana
                        escala_do_dia = agent_escala[agent_escala['DIAS DE ATENDIMENTO'].str.contains(day_of_week_pt, na=False)]

                        if not escala_do_dia.empty:
                            escala_start_time = escala_do_dia.iloc[0]['ENTRADA']
                            escala_end_time = escala_do_dia.iloc[0]['SAÍDA']

                            schedule_start_dt = single_date.replace(
                                hour=escala_start_time.hour,
                                minute=escala_start_time.minute,
                                second=escala_start_time.second
                            )
                            schedule_end_dt = single_date.replace(
                                hour=escala_end_time.hour,
                                minute=escala_end_time.minute,
                                second=escala_end_time.second
                            )

                            # Calcular tempo total agendado para o dia
                            scheduled_duration = (schedule_end_dt - schedule_start_dt).total_seconds() / 60
                            total_scheduled_time_minutes += scheduled_duration

                            # Calcular tempo online dentro da escala
                            for _, status_row in agent_real_status.iterrows():
                                status_start = status_row['Hora de início do estado - Carimbo de data/hora']
                                status_end = status_row['Hora de término do estado - Carimbo de data/hora']
                                status_state = status_row['Estado']

                                if status_state == 'Unified online':
                                    # Encontrar a interseção entre o período da escala e o período online
                                    overlap_start = max(schedule_start_dt, status_start)
                                    overlap_end = min(schedule_end_dt, status_end)

                                    if overlap_end > overlap_start:
                                        online_duration_in_overlap = (overlap_end - overlap_start).total_seconds() / 60
                                        total_online_in_schedule_minutes += online_duration_in_overlap

                    availability_percentage = (total_online_in_schedule_minutes / total_scheduled_time_minutes * 100) if total_scheduled_time_minutes > 0 else 0

                    analysis_results.append({
                        'Agente': agent,
                        'Total Tempo Escala (min)': total_scheduled_time_minutes,
                        'Total Tempo Online na Escala (min)': total_online_in_schedule_minutes,
                        'Disponibilidade na Escala (%)': f"{availability_percentage:.2f}%"
                    })
                else:
                    analysis_results.append({
                        'Agente': agent,
                        'Total Tempo Escala (min)': 0,
                        'Total Tempo Online na Escala (min)': 0,
                        'Disponibilidade na Escala (%)': "N/A - Sem escala definida"
                    })

            df_analysis = pd.DataFrame(analysis_results)
            st.dataframe(df_analysis)
        else:
            st.warning("Por favor, selecione pelo menos um agente para a análise.")
    else:
        st.warning("Por favor, faça o upload de ambos os arquivos na aba 'Upload de Dados' primeiro.")
