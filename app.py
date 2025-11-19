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
        "Boise St": "Boise State",
        "Boise St.": "Boise State",
        "UVU": "Utah Valley",
        "Utah Valley State": "Utah Valley",
        "USC": "Southern California",
        "Southern Cal": "Southern California",
        "Ole Miss": "Mississippi",
        "LSU": "Louisiana State",
        "Wash St": "Washington State",
        "Fresno St": "Fresno State"
    }
    
    if name in mappings: return mappings[name]
    
    # General Cleanup Rules
    name = name.replace(".", "")        # Turns "St." into "St"
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
                try:
                    home = game['game']['home']['names']['short']
                    away = game['game']['away']['names']['short']
                except KeyError:
                    continue
                
                if team_name in home or team_name in away:
                    is_home = (team_name in home)
                    try:
                        my_score = game['game']['home']['score'] if is_home else game['game']['away']['score']
                        op_score = game['game']['away']['score'] if is_home else game['game']['home']['score']
                    except (KeyError, ValueError):
                        continue # Skip if score is missing/empty
                    
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
        
        # Safety Net: Filter out future dates (e.g. 2074 errors)
        current_year = pd.Timestamp.now().year
        df = df[df['Date'].dt.year <= current_year + 1]

        # Clean Names
        df['Opponent_Raw'] = df['Opposing Team'].fillna("Unknown").astype(str)
        df['Opposing Team'] = df['Opponent_Raw'].apply(clean_opponent_name)
        df['Result'] = df['Result'].astype(str).str.title()
        
        # --- NEW: FILTER OUT JUNK NAMES ---
        df = df[~df['Opposing Team'].isin(['Opp', 'Opponent', 'TBD', 'Unknown', 'nan'])]
        # ----------------------------------

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

def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# --- 3. Main Application ---

# Sidebar Navigation
mode = st.sidebar.radio("View Mode", ["Dashboard", "Admin Update"])
df = load_data()

# --- VIEW 1: ADMIN UPDATE ---
if mode == "Admin Update":
    st.title("🔐 Admin Data Portal")
    password = st.text_input("Enter Admin Password", type="password")
    
    # Check for password in secrets, fallback to hardcoded for safety
    stored_password = st.secrets.get("ADMIN_PASSWORD", "cougars123")
    
    if password == stored_password:
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
                    # Put new data FIRST so it overrides old duplicates
                    updated_df = pd.concat([new_ncaa_df, df], ignore_index=True)
                    updated_df = updated_df.drop_duplicates(subset=['Date', 'Sport', 'Opposing Team'], keep='first')
                    
                    with st.spinner("Saving to GitHub..."):
                        if save_to_github(updated_df):
                            st.success("✅ Saved! Refreshing app...")
                            st.cache_data.clear()
            else:
                st.warning("No BYU games found yesterday for this sport.")

        st.divider()

        # SECTION B: MANUAL UPLOAD
        st.subheader("📂 Manual CSV Upload")
        
        # --- NEW: TEMPLATE DOWNLOAD BUTTON ---
        template_data = pd.DataFrame({
            "Date": ["2024-11-18"],
            "Sport": ["Football"],
            "Opposing Team": ["Utah"],
            "Score": ["22-21"],
            "Result": ["Win"],
            "Location": ["Away"],
            "Event": ["Regular Season"]
        })
        csv_template = convert_df_to_csv(template_data)
        
        st.download_button(
            label="📥 Download CSV Template",
            data=csv_template,
            file_name="upload_template.csv",
            mime="text/csv",
            help="Click to download an example file with the correct column headers."
        )
        # -------------------------------------

        st.info("Upload a CSV to bulk-add historical games.")
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
        
        if uploaded_file:
            new_data = pd.read_csv(uploaded_file)
            st.write("Preview:", new_data.head())
            
            if st.button("Merge Manual Upload"):
                # Put new data FIRST so it overrides old duplicates
                updated_df = pd.concat([new_data, df], ignore_index=True)
                updated_df = updated_df.drop_duplicates(subset=['Date', 'Sport', 'Opposing Team'], keep='first')
                
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
        
        st.title(f"BYU vs. {selected_opponent}")
        
        # --- 1. TOP ROW: COMPOSITE METRICS ---
        wins = len(filtered[filtered['Result'] == 'Win'])
        losses = len(filtered[filtered['Result'] == 'Loss'])
        ties = len(filtered[filtered['Result'] == 'Tie'])
        total = wins + losses + ties
        win_pct = (wins / total * 100) if total > 0 else 0
        
        # Best Sport Calculation
        sport_wins = filtered[filtered['Result'] == 'Win'].groupby('Sport').size()
        best_sport_name = "N/A"
        best_sport_count = 0
        if not sport_wins.empty:
            best_sport_name = sport_wins.idxmax()
            best_sport_count = sport_wins.max()

        # Display Metrics
        c1, c2, c3 = st.columns(3)
        c1.metric("Composite Record", f"{wins}-{losses}-{ties}")
        c2.metric("Composite Win %", f"{win_pct:.1f}%")
        c3.metric("Most Successful Sport", best_sport_name, f"{best_sport_count} Wins")
        
        st.divider()
        
        # --- 2. SPORT BREAKDOWN TABLE ---
        st.subheader("Record Breakdown by Sport")
        stats_rows = []
        for sport in sorted(filtered['Sport'].unique()):
            s_df = filtered[filtered['Sport'] == sport]
            s_wins = len(s_df[s_df['Result'] == 'Win'])
            s_losses = len(s_df[s_df['Result'] == 'Loss'])
            s_ties = len(s_df[s_df['Result'] == 'Tie'])
            s_total = s_wins + s_losses + s_ties
            s_pct = (s_wins / s_total * 100) if s_total > 0 else 0
            
            stats_rows.append({
                "Sport": sport,
                "Wins": s_wins,
                "Losses": s_losses,
                "Ties": s_ties,
                "Total Games": s_total,
                "Win %": f"{s_pct:.1f}%"
            })
            
        stats_df = pd.DataFrame(stats_rows)
        
        # Add Total Row to Table
        total_row = {
            "Sport": "TOTAL",
            "Wins": wins,
            "Losses": losses,
            "Ties": ties,
            "Total Games": total,
            "Win %": f"{win_pct:.1f}%"
        }
        final_table = pd.concat([stats_df, pd.DataFrame([total_row])], ignore_index=True)
        
        st.dataframe(
            final_table,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Sport": st.column_config.TextColumn("Sport", width="medium"),
                "Win %": st.column_config.TextColumn("Win %", width="small")
            }
        )

        st.divider()
        
        # --- 3. CHARTS & LOGS (Existing) ---
        
        st.subheader("Result Timeline")
        # Timeline Chart
        color_map = {"Win": "#002E62", "Loss": "#A9A9A9", "Tie": "#CCCCCC"}
        fig_scatter = px.scatter(
            filtered.sort_values('Date'), 
            x='Date', 
            y='Sport', 
            color='Result', 
            color_discrete_map=color_map, 
            hover_data=['Score', 'Location'],
            height=350
        )
        fig_scatter.update_traces(marker=dict(size=12))
        st.plotly_chart(fig_scatter, use_container_width=True)
            
        # Data Table
        st.subheader("Full Game Log")
        st.dataframe(
            filtered[['Date', 'Sport', 'Result', 'Score', 'Location']].sort_values('Date', ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD")
            }
        )
