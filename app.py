import streamlit as st
import pandas as pd
import plotly.express as px

# --- Page Configuration ---
st.set_page_config(
    page_title="BYU Historical Opponent Analysis",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Data Cleaning Functions ---

def clean_opponent_name(name):
    """
    Normalizes opponent names to handle variations like:
    'San Diego St.' -> 'San Diego State'
    'Utah State U.' -> 'Utah State'
    """
    name = str(name).strip()
    
    # 1. Manual Dictionary for known problem children
    # Add to this list as you find more issues in the data
    mappings = {
        "SDSU": "San Diego State",
        "San Diego St.": "San Diego State",
        "San Diego St": "San Diego State",
        "UVU": "Utah Valley",
        "Utah Valley State": "Utah Valley",
        "USC": "Southern California",
        "Southern Cal": "Southern California",
        "Ole Miss": "Mississippi",
        "LSU": "Louisiana State"
    }
    
    if name in mappings:
        return mappings[name]
    
    # 2. General cleanup rules
    # Remove periods (St. -> St)
    name = name.replace(".", "")
    
    # Standardize "University" abbreviations if they appear at the end
    if name.endswith(" Univ"):
        name = name.replace(" Univ", "")
    if name.endswith(" U"):
        name = name.replace(" U", "")
        
    return name

# --- Data Loading & Caching ---
@st.cache_data
def load_and_clean_data():
    file_path = "Sporting_Events.csv"
    
    try:
        df = pd.read_csv(file_path)
        
        # Standardize column names
        df.columns = df.columns.str.strip()
        
        # Date conversion
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        
        # --- NEW: Apply the Name Cleaning ---
        # We create a new column 'Opponent_Clean' for the app to use, 
        # but keep 'Opposing Team' if you need the original for reference.
        df['Opponent_Raw'] = df['Opposing Team'].fillna("Unknown").astype(str)
        df['Opposing Team'] = df['Opponent_Raw'].apply(clean_opponent_name)
        
        # Standardize Result
        df['Result'] = df['Result'].astype(str).str.title()
        
        return df
    except FileNotFoundError:
        return pd.DataFrame()

df = load_and_clean_data()

# --- Sidebar Controls ---
st.sidebar.title("Search Filters")

if not df.empty:
    # 1. Opponent Selector
    all_opponents = sorted(df['Opposing Team'].unique())
    
    selected_opponent = st.sidebar.selectbox(
        "Select Opponent",
        options=all_opponents,
        index=None,
        placeholder="Type to search (e.g., San Diego State)..."
    )
    
    # 2. Date Range
    min_date = df['Date'].min()
    max_date = df['Date'].max()
    
    start_date, end_date = st.sidebar.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    
    # Filter Logic
    mask = (df['Date'] >= pd.to_datetime(start_date)) & (df['Date'] <= pd.to_datetime(end_date))
    
    if selected_opponent:
        mask = mask & (df['Opposing Team'] == selected_opponent)
        
    filtered_df = df.loc[mask]

else:
    st.error("Data file not found. Please ensure the CSV is in the folder.")
    st.stop()

# --- Main Dashboard Logic ---

if not selected_opponent:
    st.title("Historical Series Explorer")
    st.info("👈 Select an opponent in the sidebar to see a detailed head-to-head breakdown.")
    
    # Show the top variations to help you debug names
    st.subheader("Data Quality Check")
    st.write("If you see duplicate schools below, add them to the 'mappings' dictionary in the code.")
    
    top_opponents = df['Opposing Team'].value_counts().head(20).reset_index()
    top_opponents.columns = ['Opponent', 'Games Played']
    st.dataframe(top_opponents, use_container_width=True, hide_index=True)

else:
    st.title(f"BYU vs. {selected_opponent}")
    
    # --- Metrics Row ---
    wins = len(filtered_df[filtered_df['Result'] == 'Win'])
    losses = len(filtered_df[filtered_df['Result'] == 'Loss'])
    ties = len(filtered_df[filtered_df['Result'] == 'Tie'])
    total = wins + losses + ties
    win_pct = (wins / total * 100) if total > 0 else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Matchups", total)
    c2.metric("Overall Record", f"{wins}-{losses}-{ties}")
    c3.metric("Win Percentage", f"{win_pct:.1f}%")
    
    st.divider()

    # --- Visualizations ---
    c_left, c_right = st.columns([1, 1])
    
    with c_left:
        st.subheader("Win/Loss by Sport")
        breakdown = filtered_df.groupby(['Sport', 'Result']).size().reset_index(name='Count')
        color_map = {"Win": "#002E62", "Loss": "#A9A9A9", "Tie": "#CCCCCC"}
        
        fig_breakdown = px.bar(
            breakdown,
            x="Sport",
            y="Count",
            color="Result",
            color_discrete_map=color_map,
            barmode='group'
        )
        st.plotly_chart(fig_breakdown, use_container_width=True)

    with c_right:
        st.subheader("Timeline")
        fig_timeline = px.scatter(
            filtered_df.sort_values('Date'),
            x="Date",
            y="Sport",
            color="Result",
            color_discrete_map=color_map,
            hover_data=['Score', 'Location', 'Opponent_Raw'], # Show original name on hover
            title="Hover to see original data source details"
        )
        st.plotly_chart(fig_timeline, use_container_width=True)
