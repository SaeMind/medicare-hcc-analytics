import streamlit as st
import polars as pl
import plotly.express as px

# --- CONFIGURATION ---
DATA_PATH = "data/processed/beneficiaries_scored.parquet"
PAGE_TITLE = "Medicare HCC Risk Analytics"
LAYOUT = "wide"

st.set_page_config(page_title=PAGE_TITLE, layout=LAYOUT)

# --- DATA LOADER ---
@st.cache_data
def load_data():
    return pl.read_parquet(DATA_PATH)

def main():
    # 1. Header
    st.title("🏥 Medicare Risk Adjustment (HCC) Analytics")
    st.markdown("""
    **Architect:** Andrew Lee | **Stack:** Polars, Python, Streamlit
    
    This dashboard analyzes the demographic risk profile of a synthetic Medicare population (CMS SynPUF).
    It calculates **Risk Adjustment Factor (RAF)** scores to project capitated reimbursement revenue.
    """)
    st.markdown("---")

    # 2. Load Data
    try:
        df = load_data()
    except FileNotFoundError:
        st.error("❌ Data not found. Please run 'src/scoring.py' first.")
        return

    # 3. Sidebar: Financial Simulator
    st.sidebar.header("💰 Financial Simulator")
    base_rate = st.sidebar.slider(
        "CMS Base Rate (Annual Capitation)", 
        min_value=8000, 
        max_value=15000, 
        value=11000, 
        step=500,
        help="The base amount Medicare pays per average beneficiary (1.0 RAF) per year."
    )
    
    # Calculate Financials
    # In Polars, we can do this lazily or eagerly. Since it's for UI, eager is fine.
    avg_score = df["demographic_risk_score"].mean()
    total_members = df.height
    projected_revenue = total_members * avg_score * base_rate

    # 4. Top Level KPIs
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Beneficiaries", f"{total_members:,}")
    c2.metric("Population Avg Risk (RAF)", f"{avg_score:.4f}")
    c3.metric("Est. Annual Revenue", f"${projected_revenue:,.0f}", delta="Projected")

    st.markdown("---")

    # 5. Visualizations
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Age Distribution")
        # Convert to Pandas for Plotly (Plotly doesn't natively support Polars yet)
        age_counts = df["age"].value_counts().sort("age")
        fig_age = px.bar(
            age_counts.to_pandas(), 
            x="age", 
            y="count", 
            labels={'age': "Age", 'count': "Beneficiaries"},
            template="plotly_white",
            color_discrete_sequence=["#333333"] # Stark Black
        )
        st.plotly_chart(fig_age, use_container_width=True)

    with col_right:
        st.subheader("Risk Score by Gender")
        # Group by Sex (1=Male, 2=Female)
        risk_by_sex = df.group_by("sex").agg(pl.col("demographic_risk_score").mean()).sort("sex")
        
        # Map 1/2 to Male/Female for display
        risk_pd = risk_by_sex.to_pandas()
        risk_pd["Gender"] = risk_pd["sex"].map({1: "Male", 2: "Female"})
        
        fig_risk = px.bar(
            risk_pd, 
            x="Gender", 
            y="demographic_risk_score",
            title="Average Risk Score (RAF)",
            template="plotly_white",
            text_auto=".3f",
            color="Gender",
            color_discrete_map={"Male": "#1f77b4", "Female": "#ff7f0e"}
        )
        st.plotly_chart(fig_risk, use_container_width=True)

    # 6. Data Preview
    with st.expander("🔍 View Raw Data Sample (Top 100)"):
        st.dataframe(df.head(100).to_pandas())

if __name__ == "__main__":
    main()