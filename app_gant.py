import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time

st.set_page_config(layout="wide", page_title="Dashboard de Escala e Status de Agentes")

st.title("📊 Dashboard de Escala e Status de Agentes")

# --- Mapeamento de dias da semana para facilitar a comparação ---
dias_semana_map = {
    'Seg': 'Monday', 'Ter': 'Tuesday', 'Qua': 'Wednesday', 'Qui': 'Thursday',
    'Sex': 'Friday', 'Sab': 'Saturday', 'Dom': 'Sunday',
    'Segunda': 'Monday', 'Terça': 'Tuesday', 'Quarta': 'Wednesday', 'Quinta': 'Thursday',
    'Sexta': 'Friday', 'Sábado': 'Saturday', 'Domingo': 'Sunday'
}

# --- Função para dividir status que atravessam a meia-noite ---
def split_status_across_days(df):
    """
    Divide entradas de status que atravessam a meia-noite em múltiplas entradas,
    uma para cada dia.
    """
    new_rows = []
    for _, row in df.iterrows():
        start = row['Inicio']
        end = row['Fim']

        # Se o status termina no dia seguinte ou depois
        while end.date() > start.date():
            # Cria uma entrada para o dia atual até o final do dia
            new_rows.append({
                'Agente': row['Agente'],
                'Status': row['Status'],
                'Inicio': start,
                'Fim': datetime.combine(start.date(), time(23, 59, 59)),
                'Tipo': row['Tipo'] # Mantém o tipo para o gráfico
            })
            # Move o início para o começo do próximo dia
            start = datetime.combine(start.date() + timedelta(days=1), time(0, 0, 0))

        # Adiciona a parte final do status (ou o status completo se não atravessou a meia-noite)
        new_rows.append({
            'Agente': row['Agente'],
            'Status': row['Status'],
            'Inicio': start,
            'Fim': end,
            'Tipo': row['Tipo']
        })
    return pd.DataFrame(new_rows)

# --- Cores para os status e escala ---
status_colors = {
    'Unified online': '#28a745',  # Verde
    'Unified away': '#ffc107',    # Amarelo
    'Unified offline': '#dc3545', # Vermelho
    'Unified transfers only': '#17a2b8', # Azul claro
    'Escala': '#6f42c1',          # Roxo
    'Outro': '#6c757d'            # Cinza para outros status não mapeados
}

# Inicializa session_state para armazenar dados
if 'df_real_status' not in st.session_state:
    st.session_state.df_real_status = pd.DataFrame(columns=['Agente', 'Status', 'Inicio', 'Fim', 'Tipo'])
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame(columns=['Agente', 'Dia da Semana', 'Inicio', 'Fim', 'Grupo'])
if 'grupos_agentes' not in st.session_state:
    st.session_state.grupos_agentes = {} # {nome_grupo: [agente1, agente2]}

# --- Abas do aplicativo ---
tab1, tab2, tab3 = st.tabs(["Upload de Relatório", "Criar/Editar Escala", "Visualização da Escala"])

with tab1:
    st.header("Upload do Relatório de Status dos Agentes")
    uploaded_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) ou CSV (.csv)", type=["xlsx", "csv"])

    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                df_raw = pd.read_csv(uploaded_file)
            else:
                df_raw = pd.read_excel(uploaded_file)

            st.write("Prévia do relatório carregado:")
            st.dataframe(df_raw.head())

            # Mapeamento das colunas do relatório
            required_columns = [
                'Nome do agente',
                'Hora de início do estado - Carimbo de data/hora',
                'Hora de término do estado - Carimbo de data/hora',
                'Estado'
            ]

            if all(col in df_raw.columns for col in required_columns):
                df_processed = df_raw.rename(columns={
                    'Nome do agente': 'Agente',
                    'Hora de início do estado - Carimbo de data/hora': 'Inicio',
                    'Hora de término do estado - Carimbo de data/hora': 'Fim',
                    'Estado': 'Status'
                })

                # Converte para datetime, tratando erros
                df_processed['Inicio'] = pd.to_datetime(df_processed['Inicio'], errors='coerce')
                df_processed['Fim'] = pd.to_datetime(df_processed['Fim'], errors='coerce')

                # Remove linhas onde a conversão de data/hora falhou
                df_processed.dropna(subset=['Inicio', 'Fim'], inplace=True)

                # Filtra status vazios ou nulos
                df_processed.dropna(subset=['Status'], inplace=True)

                # Adiciona coluna de tipo para diferenciar no gráfico
                df_processed['Tipo'] = 'Status Real'

                # Aplica a função para dividir status que atravessam a meia-noite
                df_final_status = split_status_across_days(df_processed[['Agente', 'Status', 'Inicio', 'Fim', 'Tipo']])

                st.session_state.df_real_status = df_final_status
                st.success("Relatório de status processado e carregado com sucesso!")
                st.dataframe(st.session_state.df_real_status.head())
            else:
                st.error(f"O arquivo não contém todas as colunas esperadas. Certifique-se de que as colunas '{', '.join(required_columns)}' estão presentes.")
        except Exception as e:
            st.error(f"Ocorreu um erro ao carregar o arquivo: {e}")

with tab2:
    st.header("Criar/Editar Escala de Agentes")

    st.subheader("Upload de Escala via Arquivo Excel")
    uploaded_escala_file = st.file_uploader("Escolha um arquivo Excel (.xlsx) para a escala", type=["xlsx"], key="escala_upload")

    if uploaded_escala_file:
        try:
            df_escala_uploaded = pd.read_excel(uploaded_escala_file)
            st.write("Prévia da escala carregada:")
            st.dataframe(df_escala_uploaded.head())

            # Mapeamento das colunas do arquivo de escala
            escala_required_columns = ['NOME', 'DIAS DE ATENDIMENTO', 'ENTRADA', 'SAÍDA']

            if all(col in df_escala_uploaded.columns for col in escala_required_columns):
                new_escala_entries = []
                for _, row in df_escala_uploaded.iterrows():
                    agente = row['NOME']
                    dias_str = str(row['DIAS DE ATENDIMENTO']) # Garante que é string
                    entrada_raw = row['ENTRADA']
                    saida_raw = row['SAÍDA']

                    # Trata valores NaN ou formatos inválidos para ENTRADA/SAÍDA
                    try:
                        if pd.isna(entrada_raw) or pd.isna(saida_raw):
                            st.warning(f"Agente '{agente}' tem horários de ENTRADA/SAÍDA ausentes ou inválidos. Linha ignorada.")
                            continue

                        # Converte para time, tratando diferentes formatos (datetime.time ou string)
                        if isinstance(entrada_raw, datetime):
                            entrada = entrada_raw.time()
                        elif isinstance(entrada_raw, time):
                            entrada = entrada_raw
                        else: # Assume string
                            entrada = datetime.strptime(str(entrada_raw), '%H:%M:%S').time()

                        if isinstance(saida_raw, datetime):
                            saida = saida_raw.time()
                        elif isinstance(saida_raw, time):
                            saida = saida_raw
                        else: # Assume string
                            saida = datetime.strptime(str(saida_raw), '%H:%M:%S').time()

                    except ValueError:
                        st.warning(f"Agente '{agente}' tem horários de ENTRADA/SAÍDA em formato inválido. Linha ignorada.")
                        continue

                    # Processa os dias da semana
                    dias = [d.strip() for d in dias_str.split(',') if d.strip()]
                    for dia in dias:
                        new_escala_entries.append({
                            'Agente': agente,
                            'Dia da Semana': dia,
                            'Inicio': entrada,
                            'Fim': saida,
                            'Grupo': 'Padrão' # Pode adicionar uma coluna de grupo no Excel se desejar
                        })

                if new_escala_entries:
                    df_new_escala = pd.DataFrame(new_escala_entries)
                    st.session_state.df_escala = pd.concat([st.session_state.df_escala, df_new_escala], ignore_index=True).drop_duplicates(subset=['Agente', 'Dia da Semana', 'Inicio', 'Fim'])
                    st.success("Escala carregada e adicionada com sucesso!")
                    st.dataframe(st.session_state.df_escala)
                else:
                    st.warning("Nenhuma entrada de escala válida foi encontrada no arquivo.")

            else:
                st.error(f"O arquivo de escala não contém todas as colunas esperadas. Certifique-se de que as colunas '{', '.join(escala_required_columns)}' estão presentes.")
        except Exception as e:
            st.error(f"Ocorreu um erro ao carregar o arquivo de escala: {e}")

    st.subheader("Adicionar Entrada de Escala Manualmente")
    with st.form("form_escala"):
        agente_escala = st.text_input("Nome do Agente (Escala)")
        dia_semana = st.multiselect("Dia(s) da Semana", list(dias_semana_map.keys()))
        hora_inicio = st.time_input("Hora de Início (Escala)", value=time(9, 0))
        hora_fim = st.time_input("Hora de Fim (Escala)", value=time(17, 0))
        grupo_escala = st.text_input("Grupo (opcional)", value="Padrão")

        submitted_escala = st.form_submit_button("Adicionar Escala")
        if submitted_escala:
            if agente_escala and dia_semana:
                for dia in dia_semana:
                    new_entry = pd.DataFrame([{
                        'Agente': agente_escala,
                        'Dia da Semana': dia,
                        'Inicio': hora_inicio,
                        'Fim': hora_fim,
                        'Grupo': grupo_escala
                    }])
                    st.session_state.df_escala = pd.concat([st.session_state.df_escala, new_entry], ignore_index=True).drop_duplicates(subset=['Agente', 'Dia da Semana', 'Inicio', 'Fim'])
                st.success(f"Escala para {agente_escala} adicionada com sucesso!")
            else:
                st.warning("Por favor, preencha o nome do agente e selecione pelo menos um dia da semana.")

    st.subheader("Escalas Atuais")
    if not st.session_state.df_escala.empty:
        st.dataframe(st.session_state.df_escala)
        if st.button("Limpar Todas as Escalas Manuais"):
            st.session_state.df_escala = pd.DataFrame(columns=['Agente', 'Dia da Semana', 'Inicio', 'Fim', 'Grupo'])
            st.success("Todas as escalas foram limpas.")
    else:
        st.info("Nenhuma escala adicionada ainda.")

    st.subheader("Gerenciar Grupos de Agentes")
    todos_agentes = sorted(st.session_state.df_real_status['Agente'].unique().tolist() + st.session_state.df_escala['Agente'].unique().tolist())

    grupo_selecionado = st.selectbox("Selecione um grupo para editar ou 'Novo Grupo'", 
                                     ['Novo Grupo'] + list(st.session_state.grupos_agentes.keys()))

    if grupo_selecionado == 'Novo Grupo':
        novo_nome_grupo = st.text_input("Nome do Novo Grupo")
        agentes_no_grupo = st.multiselect(f"Selecione os agentes para '{novo_nome_grupo}'", todos_agentes)
        if st.button("Salvar Novo Grupo") and novo_nome_grupo:
            st.session_state.grupos_agentes[novo_nome_grupo] = agentes_no_grupo
            st.success(f"Grupo '{novo_nome_grupo}' salvo com {len(agentes_no_grupo)} agentes.")
    else:
        agentes_atuais_grupo = st.session_state.grupos_agentes.get(grupo_selecionado, [])
        agentes_selecionados_edicao = st.multiselect(f"Editar agentes para '{grupo_selecionado}'", todos_agentes, default=agentes_atuais_grupo)
        if st.button(f"Atualizar Grupo '{grupo_selecionado}'"):
            st.session_state.grupos_agentes[grupo_selecionado] = agentes_selecionados_edicao
            st.success(f"Grupo '{grupo_selecionado}' atualizado com {len(agentes_selecionados_edicao)} agentes.")
        if st.button(f"Remover Grupo '{grupo_selecionado}'"):
            del st.session_state.grupos_agentes[grupo_selecionado]
            st.success(f"Grupo '{grupo_selecionado}' removido.")

    st.subheader("Grupos Atuais")
    if st.session_state.grupos_agentes:
        for grupo, agentes in st.session_state.grupos_agentes.items():
            st.write(f"**{grupo}**: {', '.join(agentes)}")
    else:
        st.info("Nenhum grupo de agentes configurado ainda.")

with st.sidebar:
    st.header("Filtros de Visualização")

    # Obter todos os agentes únicos do status real e da escala
    all_agents = sorted(list(set(st.session_state.df_real_status['Agente'].unique().tolist() + st.session_state.df_escala['Agente'].unique().tolist())))

    selected_agents = st.multiselect("Selecionar Agentes", all_agents, default=all_agents)

    # Filtro por grupo
    group_options = ['Todos os Grupos'] + list(st.session_state.grupos_agentes.keys())
    selected_group_filter = st.selectbox("Filtrar por Grupo", group_options)

    # Ajustar a lista de agentes selecionados se um grupo for escolhido
    if selected_group_filter != 'Todos os Grupos':
        agents_in_selected_group = st.session_state.grupos_agentes.get(selected_group_filter, [])
        # Intersect with already selected agents if any, otherwise use group agents
        if selected_agents:
            selected_agents = list(set(selected_agents) & set(agents_in_selected_group))
        else:
            selected_agents = agents_in_selected_group
        st.info(f"Agentes filtrados pelo grupo '{selected_group_filter}'.")
        if not selected_agents:
            st.warning("Nenhum agente selecionado após aplicar o filtro de grupo.")

    # Filtro de data
    min_date_status = st.session_state.df_real_status['Inicio'].min().date() if not st.session_state.df_real_status.empty else datetime.now().date()
    max_date_status = st.session_state.df_real_status['Fim'].max().date() if not st.session_state.df_real_status.empty else datetime.now().date() + timedelta(days=7)

    # Ajusta min_date e max_date para evitar erro se min_date_status for posterior a max_date_status
    if min_date_status > max_date_status:
        min_date_status = max_date_status - timedelta(days=7) # Garante um intervalo mínimo

    date_range = st.date_input(
        "Selecionar Intervalo de Datas",
        value=(min_date_status, max_date_status),
        min_value=min_date_status,
        max_value=max_date_status + timedelta(days=365) # Permite visualizar um ano à frente
    )

    start_date_filter = date_range[0] if len(date_range) > 0 else min_date_status
    end_date_filter = date_range[1] if len(date_range) > 1 else (start_date_filter + timedelta(days=7))

    # Garante que end_date_filter não seja anterior a start_date_filter
    if end_date_filter < start_date_filter:
        end_date_filter = start_date_filter


with tab3:
    st.header("Visualização da Escala e Status Real")

    if st.session_state.df_real_status.empty and st.session_state.df_escala.empty:
        st.info("Por favor, carregue o relatório de status e/ou crie a escala nas abas anteriores para visualizar.")
    else:
        df_display = pd.DataFrame(columns=['Agente', 'Status', 'Inicio', 'Fim', 'Tipo'])

        # Processar status real
        if not st.session_state.df_real_status.empty:
            df_filtered_status = st.session_state.df_real_status[
                (st.session_state.df_real_status['Agente'].isin(selected_agents)) &
                (st.session_state.df_real_status['Inicio'].dt.date >= start_date_filter) &
                (st.session_state.df_real_status['Fim'].dt.date <= end_date_filter)
            ].copy()
            df_display = pd.concat([df_display, df_filtered_status], ignore_index=True)

        # Processar escala
        if not st.session_state.df_escala.empty:
            df_filtered_escala = st.session_state.df_escala[
                st.session_state.df_escala['Agente'].isin(selected_agents)
            ].copy()

            escala_expanded = []
            current_date = start_date_filter
            while current_date <= end_date_filter:
                day_of_week_pt = current_date.strftime('%A') # Ex: 'Monday'

                # Mapeia o nome do dia da semana de volta para português para a comparação
                # Inverte o dicionário para buscar o dia em português
                reverse_dias_semana_map = {v: k for k, v in dias_semana_map.items()}
                day_of_week_excel_format = reverse_dias_semana_map.get(day_of_week_pt, day_of_week_pt) # Pega 'Seg', 'Ter', etc.

                # Filtra a escala para o dia da semana atual
                daily_escala = df_filtered_escala[
                    df_filtered_escala['Dia da Semana'].str.contains(day_of_week_excel_format, na=False)
                ]

                for _, row in daily_escala.iterrows():
                    start_dt = datetime.combine(current_date, row['Inicio'])
                    end_dt = datetime.combine(current_date, row['Fim'])

                    # Se a hora de término for 00:00:00 e a hora de início não for 00:00:00,
                    # significa que a escala termina no dia seguinte.
                    if row['Fim'] == time(0, 0, 0) and row['Inicio'] != time(0, 0, 0):
                        end_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0, 0))

                    escala_expanded.append({
                        'Agente': row['Agente'],
                        'Status': 'Escala',
                        'Inicio': start_dt,
                        'Fim': end_dt,
                        'Tipo': 'Escala'
                    })
                current_date += timedelta(days=1)

            if escala_expanded:
                df_escala_expanded = pd.DataFrame(escala_expanded)
                df_display = pd.concat([df_display, df_escala_expanded], ignore_index=True)

        if not df_display.empty:
            # Ordena para melhor visualização
            df_display = df_display.sort_values(by=['Agente', 'Inicio']).reset_index(drop=True)

            # Define a altura do gráfico dinamicamente
            num_unique_agents = df_display['Agente'].nunique()
            num_days_in_range = (end_date_filter - start_date_filter).days + 1

            # Ajusta a altura baseada no número de agentes e dias
            # Cada agente pode ter múltiplas barras por dia, então uma altura base + ajuste
            base_height = 200
            agent_height_factor = 30 # Altura por agente
            day_height_factor = 5 # Ajuste extra por dia para espacamento

            chart_height = base_height + (num_unique_agents * agent_height_factor) + (num_days_in_range * day_height_factor)
            chart_height = min(max(chart_height, 400), 1500) # Limita a altura para não ficar muito pequeno ou muito grande

            fig = px.timeline(
                df_display,
                x_start="Inicio",
                x_end="Fim",
                y="Agente",
                color="Status",
                color_discrete_map=status_colors,
                title="Comparativo de Escala vs. Status Real dos Agentes",
                hover_name="Status",
                height=chart_height
            )

            fig.update_yaxes(categoryorder="array", categoryarray=sorted(selected_agents))
            fig.update_layout(xaxis_title="Período", yaxis_title="Agente")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhum dado para exibir com os filtros selecionados.")
