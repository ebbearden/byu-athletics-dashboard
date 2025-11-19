import streamlit as st
import pandas as pd
import plotly.express as px
from github import Github
from io import StringIO
import requests
import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="BYU Historical Opponent Analysis",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 1. Helper Functions (Data Cleaning & NCAA Fetching) ---

def clean_opponent_name(name):
    """Standardizes opponent names to avoid duplicates."""
    name = str(name).strip()
    # This dictionary maps "Bad Name" : "Good Name"
    mappings = {
        "SDSU": "San Diego State",
        "San Diego St.": "San Diego State",
        "San Diego St": "San Diego State",
        "Boise St": "Boise State",          # <-- Added this
        "Boise St.": "Boise State",         # <-- Added this just in case
        "UVU": "Utah Valley",
        "Utah Valley State": "Utah Valley",
        "USC": "Southern California",
        "Southern Cal": "Southern California",
        "Ole Miss": "Mississippi",
        "LSU": "Louisiana State",
        "Wash St": "Washington State",      # <-- Likely another one you'll see
        "Fresno St": "Fresno State"         # <-- And another
    }
    if name in mappings: return mappings[name]
    name = name.replace(".", "")
    if name.endswith(" Univ"): name = name.replace(" Univ", "")
    return name

def fetch_ncaa_results(sport_slug="football", division="fbs", team_name="BYU"):
    """Fetches yesterday's scores from the official NCAA.com JSON feed."""
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    
    # URL Structure varies slightly by sport, but this works for most
    url = f"https://data.ncaa.com/casablanca/scoreboard/{sport_slug}/{division}/{yesterday.year}/{yesterday.month:02d}/{yesterday.day:02d}/scoreboard.json"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            games = data.get('games', [])
            found_games = []
            
            for game in games:
                # Look for BYU in the game names
                home = game['game']['home']['names']['short']
                away = game['game']['away']['names']['short']
                
                if team_name in home or team_name in away:
                    is_home = (team_name in home)
                    my_score = game['game']['home']['score'] if is_home else game['game']['away']['score']
                    op_score = game['game']['away']['score'] if is_home else game['game']['home']['score']
                    opponent = away if is_home else home
                    
                    # Determine Result
                    if int(my_score) > int(op_score): result = "Win"
                    elif int(my_score) < int(op_score): result = "Loss"
                    else: result = "Tie"
                        
                    found_games.append({
                        "Date": yesterday.strftime("%Y-%m-%d"),
                        "Sport": sport_slug.replace("-", " ").title().replace("Mens", "Men's").replace("Womens", "Women's"), # Clean formatting
                        "Opposing Team": opponent,
                        "Score": f"{my_score}-{op_score}",
                        "Result": result,
                        "Location": "Home" if is_home else "Away",
                        "Event": "Regular Season"
                    })
            return found_games
        else:
            return []
    except Exception as e:
        st.error(f"Error fetching NCAA data: {e}")
        return []

# --- 2. Data Loading & Saving ---

@st.cache_data(ttl=60) # Clears cache every 60 seconds to show updates
def load_data():
    try:
        df = pd.read_csv("Sporting_Events.csv")
        df.columns = df.columns.str.strip()
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        
        # Clean Names
        df['Opponent_Raw'] = df['Opposing Team'].fillna("Unknown").astype(str)
        df['Opposing Team'] = df['Opponent_Raw'].apply(clean_opponent_name)
        df['Result'] = df['Result'].astype(str).str.title()
        return df
    except FileNotFoundError:
        return pd.DataFrame()

def save_to_github(new_df):
    """Commits the updated dataframe back to GitHub."""
    try:
        g = Github(st.secrets["GITHUB_TOKEN"])
        repo = g.get_user().get_repo("byu-athletics-dashboard") # Your Repo Name
        contents = repo.get_contents("Sporting_Events.csv")
        repo.update_file(contents.path, "Update data via Streamlit Admin", new_df.to_csv(index=False), contents.sha)
        return True
    except Exception as e:
        st.error(f"GitHub Error: {e}")
        return False

# --- 3. Main Application ---

# Sidebar Navigation
mode = st.sidebar.radio("View Mode", ["Dashboard", "Admin Update"])
df = load_data()

# --- VIEW 1: ADMIN UPDATE ---
if mode == "Admin Update":
    st.title("🔐 Admin Data Portal")
    password = st.text_input("Enter Admin Password", type="password")
    
    if password == "cougars123": # Change this password!
        st.success("Access Granted")
        
        # SECTION A: NCAA FETCH
        st.subheader("🤖 Auto-Fetch from NCAA.com")
        st.info("Checks yesterday's games from official NCAA feeds.")
        
        c1, c2 = st.columns(2)
        # Map pretty names to NCAA URL slugs
        sport_map = {
            "Football (FBS)": ("football", "fbs"),
            "Men's Basketball (D1)": ("basketball-men", "d1"),
            "Women's Basketball (D1)": ("basketball-women", "d1"),
            "Women's Soccer (D1)": ("soccer-women", "d1"),
            "Women's Volleyball (D1)": ("volleyball-women", "d1"),
            "Baseball (D1)": ("baseball", "d1"),
            "Softball (D1)": ("softball", "d1")
        }
        
        sport_selection = c1.selectbox("Select Sport", list(sport_map.keys()))
        
        if c2.button("Check Yesterday's Scores"):
            slug, div = sport_map[sport_selection]
            results = fetch_ncaa_results(sport_slug=slug, division=div)
            
            if results:
                st.success(f"Found {len(results)} game(s)!")
                new_ncaa_df = pd.DataFrame(results)
                st.dataframe(new_ncaa_df)
                
                if st.button("Confirm & Save to Database"):
                    updated_df = pd.concat([df, new_ncaa_df], ignore_index=True)
                    updated_df = updated_df.drop_duplicates(subset=['Date', 'Sport', 'Opposing Team']) # Prevent doubles
                    
                    with st.spinner("Saving to GitHub..."):
                        if save_to_github(updated_df):
                            st.success("✅ Saved! Refreshing app...")
                            st.cache_data.clear()
            else:
                st.warning("No BYU games found yesterday for this sport.")

        st.divider()

        # SECTION B: MANUAL UPLOAD
        st.subheader("📂 Manual CSV Upload")
        st.info("Upload a CSV to bulk-add historical games.")
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
        
        if uploaded_file:
            new_data = pd.read_csv(uploaded_file)
            st.write("Preview:", new_data.head())
            
            if st.button("Merge Manual Upload"):
                updated_df = pd.concat([df, new_data], ignore_index=True)
                updated_df = updated_df.drop_duplicates(subset=['Date', 'Sport', 'Opposing Team'])
                
                with st.spinner("Saving to GitHub..."):
                    if save_to_github(updated_df):
                        st.success("✅ Database updated successfully!")
                        st.cache_data.clear()

    elif password:
        st.error("Incorrect password")

# --- VIEW 2: DASHBOARD (Public View) ---
else:
    if df.empty:
        st.error("No data found. Please upload 'Sporting_Events.csv' to GitHub.")
        st.stop()

    st.sidebar.header("Search Filters")
    
    # Opponent Selector
    all_opponents = sorted(df['Opposing Team'].unique())
    selected_opponent = st.sidebar.selectbox(
        "Select Opponent", 
        options=all_opponents, 
        index=None, 
        placeholder="Type to search (e.g. Utah)..."
    )

    # Landing Page
    if not selected_opponent:
        st.title("Historical Series Explorer")
        st.markdown("### Department-Wide Overview")
        st.info("👈 Select an opponent in the sidebar to see the head-to-head record.")
        
        # Big Stats
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Games Logged", len(df))
        c2.metric("Unique Opponents", df['Opposing Team'].nunique())
        c3.metric("Sports Tracked", df['Sport'].nunique())
        
        st.divider()
        
        # Leaderboard
        st.subheader("Most Frequent Opponents")
        top_opponents = df['Opposing Team'].value_counts().head(15).reset_index()
        top_opponents.columns = ['Opponent', 'Games Played']
        fig_top = px.bar(top_opponents, x='Games Played', y='Opponent', orientation='h', title="Top 15 Series")
        fig_top.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_top, use_container_width=True)

    # Head-to-Head Page
    else:
        # Filter Data
        filtered = df[df['Opposing Team'] == selected_opponent]
        
        # Calculate Record
        wins = len(filtered[filtered['Result'] == 'Win'])
        losses = len(filtered[filtered['Result'] == 'Loss'])
        ties = len(filtered[filtered['Result'] == 'Tie'])
        total = wins + losses + ties
        win_pct = (wins / total * 100) if total > 0 else 0
        
        # Header
        st.title(f"BYU vs. {selected_opponent}")
        
        # Metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Games", total)
        c2.metric("Overall Record", f"{wins}-{losses}-{ties}")
        c3.metric("Win Percentage", f"{win_pct:.1f}%")
        
        # Best Sport
        sport_wins = filtered[filtered['Result'] == 'Win'].groupby('Sport').size()
        if not sport_wins.empty:
            best_sport = sport_wins.idxmax()
            c4.metric("Most Success In", best_sport, f"{sport_wins.max()} Wins")
        
        st.divider()
        
        # Visuals
        c_left, c_right = st.columns(2)
        
        with c_left:
            st.subheader("Record by Sport")
            breakdown = filtered.groupby(['Sport', 'Result']).size().reset_index(name='Count')
            color_map = {"Win": "#002E62", "Loss": "#A9A9A9", "Tie": "#CCCCCC"}
            fig_bar = px.bar(breakdown, x='Sport', y='Count', color='Result', color_discrete_map=color_map, barmode='group')
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with c_right:
            st.subheader("Result Timeline")
            fig_scatter = px.scatter(filtered.sort_values('Date'), x='Date', y='Sport', color='Result', 
                                     color_discrete_map=color_map, hover_data=['Score', 'Location'])
            st.plotly_chart(fig_scatter, use_container_width=True)
            
        # Data Table
        st.subheader("Full Game Log")
        st.dataframe(
            filtered[['Date', 'Sport', 'Result', 'Score', 'Location']].sort_values('Date', ascending=False),
            use_container_width=True,
            hide_index=True
        )
