import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time

st.set_page_config(layout="wide", page_title="Dashboard de Escala e Status de Agentes")

st.title("📊 Dashboard de Escala e Status de Agentes")

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

        # Se o fim for NaN, significa que o status ainda está ativo.
        # Para fins de visualização, podemos assumir que termina no final do dia atual
        # ou no momento atual se for o dia de hoje.
        if pd.isna(end):
            # Para simplificar, vamos assumir que um status sem fim termina no final do dia.
            # Você pode ajustar essa lógica conforme a necessidade (ex: terminar no datetime.now())
            end = datetime.combine(start.date(), time(23, 59, 59))
            if end < start: # Se o status começou e terminou no mesmo dia, mas o fim foi ajustado para 23:59:59
                end = datetime.combine(start.date() + timedelta(days=1), time(23, 59, 59))

        current_start_segment = start
        while current_start_segment.date() <= end.date():
            day_end = datetime.combine(current_start_segment.date(), time(23, 59, 59))

            segment_end = min(end, day_end)

            new_rows.append({
                'Agente': row['Agente'],
                'Status': row['Status'],
                'Inicio': current_start_segment,
                'Fim': segment_end,
                'Dia': current_start_segment.date(),
                'Grupo': row.get('Grupo', 'Não Definido') # Adiciona grupo se existir
            })

            current_start_segment = datetime.combine(current_start_segment.date() + timedelta(days=1), time(0, 0, 0))

            # Se o status já terminou, sai do loop
            if current_start_segment > end:
                break
    return pd.DataFrame(new_rows)

# --- Dicionário de cores para os status ---
status_colors = {
    'unified online': 'green',
    'unified away': 'orange',
    'unified offline': 'red',
    'unified transfers only': 'blue',
    'trabalho': 'darkgreen',
    'pausa': 'gold',
    'refeição': 'darkorange',
    'treinamento': 'purple',
    'folga': 'gray',
    'outro status': 'lightgray' # Cor padrão para status não mapeados
}

# --- Inicialização de estado para a escala ---
if 'df_escala' not in st.session_state:
    st.session_state.df_escala = pd.DataFrame(columns=['Agente', 'Status', 'Inicio', 'Fim', 'Dia', 'Grupo'])

# --- Abas para organizar o aplicativo ---
tab1, tab2, tab3 = st.tabs(["⬆️ Carregar Relatório", "📝 Criar Escala", "📊 Visualização"])

# --- Tab 1: Carregar Relatório ---
with tab1:
    st.header("1. Carregar Relatório de Status")
    uploaded_file = st.file_uploader("Escolha um arquivo Excel (.xlsx)", type=["xlsx"])

    df_real_status = pd.DataFrame()
    if uploaded_file is not None:
        try:
            df_raw = pd.read_excel(uploaded_file)

            # Renomear colunas do seu arquivo para os nomes esperados pelo código
            df_real_status = df_raw.rename(columns={
                'Nome do agente': 'Agente',
                'Estado': 'Status',
                'Hora de início do estado - Carimbo de data/hora': 'Inicio',
                'Hora de término do estado - Carimbo de data/hora': 'Fim',
                # Se você tiver uma coluna de grupo no seu Excel, adicione aqui:
                # 'Nome da Coluna de Grupo': 'Grupo'
            })

            # Converter colunas de data/hora para o formato datetime
            df_real_status['Inicio'] = pd.to_datetime(df_real_status['Inicio'], errors='coerce')
            df_real_status['Fim'] = pd.to_datetime(df_real_status['Fim'], errors='coerce')

            # Remover linhas com datas inválidas após a conversão
            df_real_status.dropna(subset=['Inicio'], inplace=True)

            # Adicionar coluna 'Dia' para facilitar a filtragem e a função split_status_across_days
            df_real_status['Dia'] = df_real_status['Inicio'].dt.date

            # Adicionar coluna 'Grupo' se não existir (para o filtro)
            if 'Grupo' not in df_real_status.columns:
                df_real_status['Grupo'] = 'Não Definido'

            # Aplicar a função para dividir status que atravessam a meia-noite
            df_real_status = split_status_across_days(df_real_status)

            st.session_state['df_real_status'] = df_real_status # Salva no session_state
            st.success("Relatório carregado e processado com sucesso!")
            st.dataframe(df_real_status.head())

        except Exception as e:
            st.error(f"Erro ao carregar ou processar o arquivo: {e}")
    else:
        st.info("Por favor, faça o upload de um relatório para começar.")

# --- Tab 2: Criar Escala ---
with tab2:
    st.header("2. Criar/Editar Escala de Agentes")

    # Obter lista de agentes do relatório carregado
    agentes_disponiveis = []
    if 'df_real_status' in st.session_state and not st.session_state['df_real_status'].empty:
        agentes_disponiveis = sorted(st.session_state['df_real_status']['Agente'].unique().tolist())

    # Grupos pré-definidos
    grupos_pre_definidos = ['6h20min', '8h12min', 'Outro Grupo']

    with st.expander("Adicionar nova entrada na escala"):
        with st.form("form_add_escala"):
            # Campo de agente como selectbox
            agente_escala = st.selectbox("Nome do Agente (Escala)", [''] + agentes_disponiveis, key="agente_escala_select")

            status_escala = st.selectbox("Status (Escala)", list(status_colors.keys()) + ['Outro Status'], key="status_escala_select")
            if status_escala == 'Outro Status':
                status_escala = st.text_input("Digite o novo Status", key="novo_status_escala_input")

            col1, col2 = st.columns(2)
            data_inicio_escala = col1.date_input("Data de Início (Escala)", datetime.now().date(), key="data_inicio_escala_input")
            hora_inicio_escala = col2.time_input("Hora de Início (Escala)", time(9, 0), key="hora_inicio_escala_input")

            col3, col4 = st.columns(2)
            data_fim_escala = col3.date_input("Data de Fim (Escala)", datetime.now().date(), key="data_fim_escala_input")
            hora_fim_escala = col4.time_input("Hora de Fim (Escala)", time(17, 0), key="hora_fim_escala_input")

            # Campo de grupo como selectbox com opções pré-definidas
            grupo_escala = st.selectbox("Grupo (Escala)", grupos_pre_definidos, key="grupo_escala_select")
            if grupo_escala == 'Outro Grupo':
                grupo_escala = st.text_input("Digite o novo Grupo", key="novo_grupo_escala_input")

            submitted_escala = st.form_submit_button("Adicionar à Escala")
            if submitted_escala:
                if agente_escala and status_escala:
                    inicio_dt = datetime.combine(data_inicio_escala, hora_inicio_escala)
                    fim_dt = datetime.combine(data_fim_escala, hora_fim_escala)

                    if fim_dt <= inicio_dt:
                        st.warning("A hora/data de fim da escala deve ser posterior à hora/data de início.")
                    else:
                        new_row_escala = pd.DataFrame([{
                            'Agente': agente_escala,
                            'Status': status_escala.lower(), # Normaliza para minúsculas
                            'Inicio': inicio_dt,
                            'Fim': fim_dt,
                            'Dia': inicio_dt.date(),
                            'Grupo': grupo_escala
                        }])
                        st.session_state.df_escala = pd.concat([st.session_state.df_escala, new_row_escala], ignore_index=True)
                        st.success(f"Escala para {agente_escala} adicionada.")
                else:
                    st.warning("Por favor, preencha o nome do agente e o status da escala.")

    st.subheader("Escala de Agentes Atual:")
    if not st.session_state.df_escala.empty:
        st.dataframe(st.session_state.df_escala)
        if st.button("Limpar Escala Completa"):
            st.session_state.df_escala = pd.DataFrame(columns=['Agente', 'Status', 'Inicio', 'Fim', 'Dia', 'Grupo'])
            st.success("Escala limpa com sucesso!")
    else:
        st.info("Nenhuma escala adicionada ainda.")

# --- Tab 3: Visualização ---
with tab3:
    st.header("3. Visualização Comparativa (Escala vs. Real)")

    df_combined = pd.DataFrame()
    df_real_status = st.session_state.get('df_real_status', pd.DataFrame())

    if not df_real_status.empty and not st.session_state.df_escala.empty:
        df_real_status['Tipo'] = 'Real'
        st.session_state.df_escala['Tipo'] = 'Escala'
        df_combined = pd.concat([df_real_status, st.session_state.df_escala], ignore_index=True)
    elif not df_real_status.empty:
        df_real_status['Tipo'] = 'Real'
        df_combined = df_real_status
    elif not st.session_state.df_escala.empty:
        st.session_state.df_escala['Tipo'] = 'Escala'
        df_combined = st.session_state.df_escala

    if not df_combined.empty:
        # Garantir que 'Status' esteja em minúsculas para o mapeamento de cores
        df_combined['Status'] = df_combined['Status'].str.lower()

        # --- Filtros ---
        st.subheader("Filtros")

        col_filtros1, col_filtros2 = st.columns(2)

        with col_filtros1:
            all_agents = sorted(df_combined['Agente'].unique())
            selected_agents = st.multiselect("Filtrar por Agente(s)", all_agents, default=all_agents)

            all_groups = sorted(df_combined['Grupo'].unique())
            selected_groups = st.multiselect("Filtrar por Grupo(s)", all_groups, default=all_groups)

        with col_filtros2:
            # Filtro de data com calendário para início e fim
            min_overall_date = df_combined['Inicio'].min().date() if not df_combined.empty else datetime.now().date()
            max_overall_date = df_combined['Fim'].max().date() if not df_combined.empty else datetime.now().date()

            # Ajustar max_overall_date para não ser menor que min_overall_date se o dataframe estiver vazio ou tiver apenas um dia
            if min_overall_date > max_overall_date:
                max_overall_date = min_overall_date + timedelta(days=1)

            date_range_filter = st.date_input(
                "Filtrar por Período (Início e Fim)",
                value=(min_overall_date, max_overall_date),
                min_value=min_overall_date,
                max_value=max_overall_date
            )

        df_filtered = df_combined.copy()

        # Aplicar filtros
        if selected_agents:
            df_filtered = df_filtered[df_filtered['Agente'].isin(selected_agents)]
        if selected_groups:
            df_filtered = df_filtered[df_filtered['Grupo'].isin(selected_groups)]

        if len(date_range_filter) == 2:
            start_date_filter, end_date_filter = date_range_filter
            df_filtered = df_filtered[
                (df_filtered['Inicio'].dt.date >= start_date_filter) &
                (df_filtered['Fim'].dt.date <= end_date_filter)
            ]
        else:
            st.warning("Por favor, selecione um período de data válido para o filtro.")
            df_filtered = pd.DataFrame() # Limpa o dataframe filtrado se o período não for válido

        if not df_filtered.empty:
            # Criar o gráfico Gantt
            st.subheader("Gráfico de Gantt: Escala vs. Status Real")

            # Garantir que todos os status no df_filtered tenham uma cor definida,
            # caso contrário, plotly atribuirá uma cor padrão.
            unique_statuses_in_data = df_filtered['Status'].unique()
            current_status_colors = status_colors.copy()
            for status in unique_statuses_in_data:
                if status not in current_status_colors:
                    current_status_colors[status] = 'lightgray' # Cor padrão para status não mapeados

            fig = px.timeline(
                df_filtered,
                x_start="Inicio",
                x_end="Fim",
                y="Agente",
                color="Status",
                facet_row="Dia", # Divide por dia
                color_discrete_map=current_status_colors,
                title="Comparativo de Escala e Status Real dos Agentes",
                hover_name="Status",
                hover_data={"Inicio": "|%Y-%m-%d %H:%M:%S", "Fim": "|%Y-%m-%d %H:%M:%S", "Tipo": True, "Grupo": True}
            )

            fig.update_yaxes(autorange="reversed") # Agentes em ordem alfabética

            # Ajusta a altura do gráfico dinamicamente com base no número de agentes e dias
            num_agentes = len(df_filtered['Agente'].unique())
            num_dias = len(df_filtered['Dia'].unique())
            altura_base = 150 # Altura para os títulos e eixos
            altura_por_linha = 30 # Altura estimada por linha de agente/dia
            fig.update_layout(height=max(600, altura_base + num_agentes * num_dias * altura_por_linha))

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhum dado para exibir com os filtros selecionados.")
    else:
        st.info("Por favor, carregue um relatório e/ou adicione entradas na escala para visualizar os dados.")
